"""Fábrica da aplicação Mesa do Mestre."""
import logging
import os
import sqlite3

from flask import Flask, g, jsonify, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from app import constants
from app.extensions import csrf, db, migrate
from app.utils import fmt_date, fmt_datetime, multiline
from config import CONFIGS, env_name

PUBLIC_ENDPOINTS = {"auth.login", "auth.register", "auth.reset", "static", "health"}


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    """SQLite não aplica chaves estrangeiras por padrão: ativa por conexão (Postgres já aplica)."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def create_app(config_name=None, test_config=None):
    app = Flask(__name__, instance_path=None)
    name = config_name or env_name()
    cfg_cls = CONFIGS.get(name)
    if cfg_cls is None:
        raise RuntimeError(f"MESA_ENV inválido: {name!r} (use development, production ou testing)")
    cfg = cfg_cls()
    for key in dir(cfg):
        if key.isupper():
            app.config[key] = getattr(cfg, key)
    if test_config:
        app.config.update(test_config)
    if os.environ.get("VERCEL") or os.environ.get("TRUST_PROXY") == "1":
        # Atrás do proxy da Vercel: usa X-Forwarded-* (IP real, esquema https).
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    # render_as_batch: necessário para ALTER TABLE no SQLite (no Postgres é transparente)
    migrate.init_app(app, db, render_as_batch=True, compare_type=True)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registra as tabelas)

    _register_blueprints(app)
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_security(app)

    from app.cli import register_cli
    register_cli(app)

    @app.get("/health")
    def health():
        return jsonify(ok=True)

    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)
    return app


def _register_blueprints(app):
    from app.routes import all_blueprints

    for bp in all_blueprints:
        app.register_blueprint(bp)


def _register_template_helpers(app):
    app.jinja_env.filters["datahora"] = fmt_datetime
    app.jinja_env.filters["data"] = fmt_date
    app.jinja_env.filters["texto"] = multiline

    @app.template_global()
    def rotulo(kind, key):
        return constants.label(constants.ALL_CHOICES[kind], key)

    @app.context_processor
    def inject_globals():
        from app.models import Campaign
        from app.services.campaigns import get_current_campaign

        user = getattr(g, "user", None)
        if user is None:
            return {"current_user": None, "current_campaign": None, "all_campaigns": [], "choices": constants.ALL_CHOICES}
        return {
            "current_user": user,
            "current_campaign": get_current_campaign(),
            "all_campaigns": Campaign.query.filter_by(owner_id=user.id).order_by(Campaign.status == "encerrada", Campaign.name).all(),
            "choices": constants.ALL_CHOICES,
        }


def _wants_json():
    return request.is_json or request.accept_mimetypes.best == "application/json" or request.path.startswith("/xp/api")


def _register_security(app):
    @app.before_request
    def require_login():
        """Toda rota exige login, exceto as públicas (login, cadastro, recuperação, estáticos)."""
        from app.services.auth import load_user

        g.user = load_user()
        if g.user is None and request.endpoint not in PUBLIC_ENDPOINTS:
            if _wants_json():
                return jsonify(ok=False, error="Sessão expirada. Entre novamente."), 401
            nxt = request.full_path.rstrip("?") if request.method == "GET" else ""
            return redirect(url_for("auth.login", next=nxt) if nxt and nxt != "/" else url_for("auth.login"))

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'; object-src 'none'",
        )
        if app.config.get("COOKIE_SECURE"):
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.endpoint not in ("static", "media.serve"):
            resp.headers.setdefault("Cache-Control", "no-store")   # páginas com dados pessoais nunca ficam em cache
        return resp


def _register_error_handlers(app):
    def respond(code, title, message):
        if _wants_json():
            return jsonify(ok=False, error=message), code
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return respond(400, "Sessão expirada", "O formulário expirou ou é inválido. Recarregue a página e tente novamente.")

    @app.errorhandler(404)
    def not_found(_e):
        return respond(404, "Não encontrado", "O registro ou a página que você procura não existe (ou foi removido).")

    @app.errorhandler(413)
    def too_large(_e):
        return respond(413, "Arquivo muito grande", "O arquivo enviado excede o tamanho permitido.")

    @app.errorhandler(HTTPException)
    def http_error(e):
        return respond(e.code or 500, e.name, e.description or "Erro na requisição.")

    @app.errorhandler(Exception)
    def unexpected(e):
        db.session.rollback()
        app.logger.exception("Erro inesperado: %s", e)
        return respond(500, "Erro interno", "Algo deu errado. Seus dados não foram corrompidos; tente novamente.")

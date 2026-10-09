"""Fábrica da aplicação Mesa do Mestre."""
import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path

from flask import Flask, g, has_request_context, jsonify, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from app import constants
from app.extensions import csrf, db
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


@event.listens_for(Engine, "before_cursor_execute")
def _query_start(conn, cursor, statement, parameters, context, executemany):
    if has_request_context():
        conn.info.setdefault("_qt", []).append(time.perf_counter())


@event.listens_for(Engine, "after_cursor_execute")
def _query_end(conn, cursor, statement, parameters, context, executemany):
    if has_request_context() and conn.info.get("_qt"):
        g.db_ms = g.get("db_ms", 0.0) + (time.perf_counter() - conn.info["_qt"].pop()) * 1000
        g.db_n = g.get("db_n", 0) + 1


@event.listens_for(Session, "after_flush")
def _blobs_flushed(session, _ctx):
    """Anota os blobs cujo registro (FileAsset) acabou de ser gravado nesta transação."""
    if has_request_context():
        from app.models import FileAsset

        urls = {o.storage_url for o in session.new if isinstance(o, FileAsset) and o.storage_url}
        if urls:
            g.setdefault("flushed_blob", set()).update(urls)


@event.listens_for(Session, "after_commit")
def _blobs_confirmed(session):
    """Commit feito: os blobs com registro gravado deixam de ser 'pendentes' (nenhum outro commit os confirma)."""
    if has_request_context():
        confirmed = g.pop("flushed_blob", set())
        if confirmed and g.get("pending_blob"):
            g.pending_blob = [u for u in g.pending_blob if u not in confirmed]


@event.listens_for(Session, "after_rollback")
def _blobs_rolled_back(session):
    if has_request_context():
        g.pop("flushed_blob", None)           # o registro foi desfeito: o blob continua pendente (e será apagado)


def create_app(config_name=None, test_config=None):
    app = Flask(__name__, instance_path=None)
    name = config_name or env_name()
    cfg_cls = CONFIGS.get(name)
    if cfg_cls is None:
        raise RuntimeError(f"MESA_ENV inválido: {name!r} (use development, production ou testing)")
    cfg = cfg_cls()
    app.config["ENV_NAME"] = name
    for key in dir(cfg):
        if key.isupper():
            app.config[key] = getattr(cfg, key)
    if test_config:
        app.config.update(test_config)
    if os.environ.get("VERCEL") or os.environ.get("TRUST_PROXY") == "1":
        # Atrás do proxy da Vercel: usa X-Forwarded-* (IP real, esquema https).
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    if app.config.get("CONFIG_ERROR"):
        return _config_error_app(app)         # configuração inválida: explica em vez de um "500" mudo
    if not os.environ.get("VERCEL"):
        # Migrations só rodam fora da Vercel (do seu PC): evita importar o Alembic a cada início a frio.
        from flask_migrate import Migrate

        # render_as_batch: necessário para ALTER TABLE no SQLite (no Postgres é transparente)
        Migrate(app, db, render_as_batch=True, compare_type=True)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registra as tabelas)

    _register_blueprints(app)
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_security(app)

    from app.cli import register_cli
    register_cli(app)

    @app.teardown_request
    def discard_unconfirmed_blobs(_exc):
        """Upload feito mas a requisição não confirmou no banco (erro/rollback): apaga o arquivo órfão."""
        urls = g.pop("pending_blob", None)
        if urls:
            from app.services import blobstore

            blobstore.delete(urls)

    @app.get("/health")
    def health():
        """Diagnóstico público e sem segredos: conexão com o banco e se as tabelas já existem."""
        from sqlalchemy import inspect, text

        status = {"ok": True, "env": app.config.get("ENV_NAME", "?")}
        try:
            db.session.execute(text("SELECT 1"))
            status["db"] = "ok"
            status["schema"] = "ok" if inspect(db.engine).has_table("users") else "faltando: rode flask db upgrade"
            status["ok"] = status["schema"] == "ok"
        except Exception:  # noqa: BLE001 - qualquer falha de conexão vira diagnóstico, nunca vaza detalhes
            app.logger.exception("Falha no /health")
            status.update(ok=False, db="erro de conexão: confira DATABASE_URL")
        return jsonify(status), (200 if status["ok"] else 503)

    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)
    return app


def _config_error_app(app):
    """App mínimo que responde a TODAS as rotas com a descrição do erro de configuração (sem segredos)."""
    app.logger.error("Configuração inválida: %s", app.config["CONFIG_ERROR"])
    message = app.config["CONFIG_ERROR"]

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def config_error(path):
        return (f"<!doctype html><meta charset=utf-8><title>Erro de configuração</title>"
                f"<h1>Mesa do Mestre — erro de configuração</h1><p>{message}</p>"
                f"<p>Depois de corrigir, faça um novo deploy (variáveis novas só valem após redeploy).</p>"), 500

    return app


def _register_blueprints(app):
    from app.routes import all_blueprints

    for bp in all_blueprints:
        app.register_blueprint(bp)


def _register_template_helpers(app):
    app.jinja_env.filters["datahora"] = fmt_datetime
    app.jinja_env.filters["data"] = fmt_date
    app.jinja_env.filters["texto"] = multiline
    versions: dict[str, str] = {}

    @app.template_global()
    def asset(path):
        """URL de arquivo estático com hash do conteúdo: pode ser cacheado para sempre pelo navegador/CDN."""
        v = versions.get(path)
        if v is None:
            try:
                v = hashlib.md5((Path(app.static_folder) / path).read_bytes()).hexdigest()[:10]  # noqa: S324
            except OSError:
                v = "0"
            if not app.debug:
                versions[path] = v
        return url_for("static", filename=path, v=v)

    @app.template_global()
    def rotulo(kind, key):
        return constants.label(constants.ALL_CHOICES[kind], key)

    @app.context_processor
    def inject_globals():
        from app.services.campaigns import get_current_campaign, user_campaigns

        user = getattr(g, "user", None)
        if user is None:
            return {"current_user": None, "current_campaign": None, "all_campaigns": [], "choices": constants.ALL_CHOICES}
        return {
            "current_user": user,
            "current_campaign": get_current_campaign(),
            "all_campaigns": user_campaigns(),            # já carregada: nenhuma consulta extra
            "choices": constants.ALL_CHOICES,
        }


def _wants_json():
    return request.is_json or request.accept_mimetypes.best == "application/json" or request.path.startswith("/xp/api")


def _register_security(app):
    @app.before_request
    def require_login():
        """Toda rota exige login, exceto as públicas (login, cadastro, recuperação, estáticos)."""
        from app.services.auth import load_user
        from app.services.campaigns import reset_request_cache

        g.t0, g.db_n, g.db_ms = time.perf_counter(), 0, 0.0
        reset_request_cache()
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
        if request.endpoint == "static":
            if request.args.get("v"):                               # URL versionada pelo conteúdo: cache eterno
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.endpoint != "media.serve":
            resp.headers.setdefault("Cache-Control", "no-store")   # páginas com dados pessoais nunca ficam em cache
        if "t0" in g:                                               # visível em DevTools → Network → Timing
            total = (time.perf_counter() - g.t0) * 1000
            resp.headers["Server-Timing"] = f'db;dur={g.db_ms:.1f};desc="{g.db_n} consultas", app;dur={total:.1f}'
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
        if isinstance(e, (ProgrammingError, OperationalError)):
            text = str(getattr(e, "orig", e)).lower()
            if "does not exist" in text or "no such table" in text:
                return respond(500, "Banco não inicializado", "As tabelas ainda não existem no banco. Rode «flask db upgrade» apontando para o seu banco (veja o README, seção Deploy).")
            return respond(500, "Banco indisponível", "Não foi possível usar o banco de dados. Confira a variável DATABASE_URL e tente novamente.")
        return respond(500, "Erro interno", "Algo deu errado. Seus dados não foram corrompidos; tente novamente.")

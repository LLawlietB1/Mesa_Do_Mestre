"""Login, cadastro, recuperação de senha e conta do usuário."""
from urllib.parse import urlparse

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from app.forms.auth import (ChangePasswordForm, DeleteAccountForm, LoginForm, RecoveryForm, RegisterForm,
                            ResetForm)
from app.models import UserSession
from app.services import auth as auth_service
from app.services.auth import RegistrationError
from app.services.common import safe_commit

bp = Blueprint("auth", __name__)
PUBLIC_ENDPOINTS = {"auth.login", "auth.register", "auth.reset"}


def _next_url():
    target = request.values.get("next") or ""
    parsed = urlparse(target)
    if target.startswith("/") and not target.startswith("//") and "\\" not in target and not parsed.netloc:
        return target
    return url_for("dashboard.index")


def _login_response(user, message=None):
    token, expires = auth_service.start_session(user)
    session.clear()                                   # evita fixação de sessão (antes do flash!)
    if message:
        flash(message, "success")
    resp = redirect(_next_url())
    auth_service.set_cookie(resp, token, expires)
    return resp


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user, error = auth_service.authenticate(form.email.data, form.password.data)
        if user:
            return _login_response(user)
        flash(error, "error")
    return render_template("auth/login.html", form=form, mode=auth_service.registration_mode())


@bp.route("/cadastro", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard.index"))
    mode = auth_service.registration_mode()
    form = RegisterForm()
    if mode == "closed":
        return render_template("auth/register.html", form=form, mode=mode), 403
    if form.validate_on_submit():
        if mode == "invite" and not auth_service.invite_ok(form.invite_code.data):
            form.invite_code.errors.append("Código de convite inválido.")
        else:
            try:
                user = auth_service.register_user(form.name.data, form.email.data, form.password.data, form.passphrase.data)
            except RegistrationError as exc:
                flash(str(exc), "error")
            except ValueError as exc:
                form.email.errors.append(str(exc))
            else:
                return _login_response(user, f"Bem-vindo, {user.name}! Sua conta foi criada.")
    return render_template("auth/register.html", form=form, mode=mode)


@bp.route("/esqueci-senha", methods=["GET", "POST"])
def reset():
    if g.user:
        return redirect(url_for("dashboard.index"))
    form = ResetForm()
    if form.validate_on_submit():
        error = auth_service.reset_password_with_passphrase(form.email.data, form.passphrase.data, form.password.data)
        if error:
            flash(error, "error")
        else:
            flash("Senha redefinida. Entre com a nova senha.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", form=form)


@bp.post("/sair")
def logout():
    auth_service.end_session()
    session.clear()
    resp = redirect(url_for("auth.login"))
    auth_service.clear_cookie(resp)
    return resp


# ---------------------------------------------------------------- conta

def _account_page(**overrides):
    forms = {"pw_form": ChangePasswordForm(), "rec_form": RecoveryForm(), "del_form": DeleteAccountForm()}
    forms.update(overrides)
    sessions = UserSession.query.filter_by(user_id=g.user.id).count()
    return render_template("auth/account.html", sessions=sessions, **forms)


@bp.get("/conta")
def account():
    return _account_page()


@bp.post("/conta/senha")
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        user = g.user
        if not auth_service.verify_secret(user.password_hash, form.current.data):
            form.current.errors.append("Senha atual incorreta.")
        elif (problem := auth_service.password_problem(form.password.data)):
            form.password.errors.append(problem)
        else:
            user.password_hash = auth_service.hash_secret(form.password.data)
            auth_service.end_all_sessions(user)       # encerra as outras sessões (e esta); entra de novo
            flash("Senha alterada. Entre novamente.", "success")
            resp = redirect(url_for("auth.login"))
            auth_service.clear_cookie(resp)
            return resp
    return _account_page(pw_form=form)


@bp.post("/conta/recuperacao")
def change_recovery():
    form = RecoveryForm()
    if form.validate_on_submit():
        if not auth_service.verify_secret(g.user.password_hash, form.current.data):
            form.current.errors.append("Senha atual incorreta.")
        elif (problem := auth_service.passphrase_problem(form.passphrase.data)):
            form.passphrase.errors.append(problem)
        else:
            g.user.recovery_hash = auth_service.hash_passphrase(form.passphrase.data)
            flash("Palavra-chave de recuperação atualizada." if safe_commit() else "Não foi possível salvar.", "success")
            return redirect(url_for("auth.account"))
    return _account_page(rec_form=form)


@bp.post("/conta/sair-de-todos")
def logout_all():
    auth_service.end_all_sessions(g.user)
    session.clear()
    flash("Todas as sessões foram encerradas.", "success")
    resp = redirect(url_for("auth.login"))
    auth_service.clear_cookie(resp)
    return resp


@bp.post("/conta/excluir")
def delete_account():
    form = DeleteAccountForm()
    if form.validate_on_submit():
        if not auth_service.verify_secret(g.user.password_hash, form.current.data):
            form.current.errors.append("Senha atual incorreta.")
        elif form.confirm_text.data.strip().upper() != "EXCLUIR":
            form.confirm_text.errors.append("Digite EXCLUIR para confirmar.")
        else:
            auth_service.delete_account(g.user)
            session.clear()
            flash("Sua conta e todos os seus dados foram excluídos.", "success")
            resp = redirect(url_for("auth.login"))
            auth_service.clear_cookie(resp)
            return resp
    return _account_page(del_form=form)

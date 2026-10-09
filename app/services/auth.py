"""Autenticação: Argon2id, sessões no banco com token hasheado, bloqueio por tentativas e recuperação
de senha por palavra-chave (sem e-mail). Mesmo modelo de segurança do Professor Helper."""
from __future__ import annotations

import functools
import hashlib
import hmac
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from email_validator import EmailNotValidError, validate_email
from flask import current_app, g, request
from sqlalchemy import delete
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Campaign, FileAsset, Player, User, UserSession
from app.services import blobstore
from app.models.mixins import utcnow

COOKIE = "mm_session"
_ph = PasswordHasher()


@functools.cache
def _dummy_hash() -> str:
    """Hash usado só para igualar o tempo de resposta quando o e-mail não existe (calculado sob demanda)."""
    return _ph.hash("senha-ficticia-para-igualar-tempo")


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_secret(value: str) -> str:
    return _ph.hash(value)


def verify_secret(hashed: str | None, value: str) -> bool:
    if not hashed:
        return False
    try:
        return _ph.verify(hashed, value)
    except (VerificationError, InvalidHashError):
        return False


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def check_email(email: str) -> str:
    try:
        return validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError("E-mail inválido.") from None


def password_problem(pw: str) -> str | None:
    if len(pw) < 8:
        return "A senha deve ter pelo menos 8 caracteres."
    if len(pw) > 200:
        return "A senha é longa demais."
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        return "A senha deve ter letras e números."
    return None


def passphrase_problem(p: str) -> str | None:
    if len((p or "").strip()) < 6:
        return "A palavra-chave deve ter pelo menos 6 caracteres."
    return None


def hash_passphrase(p: str) -> str:
    return hash_secret(p.strip().lower())


def verify_passphrase(hashed: str | None, p: str) -> bool:
    return verify_secret(hashed, p.strip().lower())


# ---------------------------------------------------------------- cadastro

def registration_mode() -> str:
    """'invite' (exige código), 'open' (aberto) ou 'closed'."""
    cfg = current_app.config
    if cfg["INVITE_CODE"]:
        return "invite"
    return "open" if cfg["ALLOW_OPEN_REGISTRATION"] else "closed"


def invite_ok(code: str) -> bool:
    expected = current_app.config["INVITE_CODE"]
    return bool(expected) and hmac.compare_digest(expected.encode(), (code or "").strip().encode())


class RegistrationError(ValueError):
    pass


def register_user(name: str, email: str, password: str, passphrase: str) -> User:
    email = check_email(email)
    if User.query.filter_by(email=email).first():
        raise RegistrationError("Já existe uma conta com este e-mail.")
    for problem in (password_problem(password), passphrase_problem(passphrase)):
        if problem:
            raise RegistrationError(problem)
    first = current_app.config.get("FIRST_USER_IS_ADMIN") and not db.session.query(User.id).first()
    user = User(name=name.strip(), email=email, password_hash=hash_secret(password), recovery_hash=hash_passphrase(passphrase),
                role="ADMIN" if first else "MESTRE")
    db.session.add(user)
    db.session.commit()
    return user


# ---------------------------------------------------------------- login / bloqueio

LOCKED_MSG = "Muitas tentativas. Aguarde alguns minutos e tente novamente."


def _register_failure(user: User) -> None:
    cfg = current_app.config
    failed = user.failed_logins + 1
    if failed >= cfg["MAX_FAILED_LOGINS"]:
        user.failed_logins, user.locked_until = 0, utcnow() + timedelta(minutes=cfg["LOCK_MINUTES"])
    else:
        user.failed_logins = failed
    db.session.commit()


def _locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > utcnow())


def authenticate(email: str, password: str):
    """Devolve (user, None) ou (None, mensagem). Mensagem de erro idêntica para e-mail/senha errados."""
    generic = "E-mail ou senha incorretos."
    user = User.query.filter_by(email=normalize_email(email)).first()
    if user is None:
        verify_secret(_dummy_hash(), password)   # tempo de resposta parecido: não revela se o e-mail existe
        return None, generic
    if _locked(user):
        return None, LOCKED_MSG
    if not verify_secret(user.password_hash, password):
        _register_failure(user)
        return None, generic
    user.failed_logins, user.locked_until = 0, None
    UserSession.query.filter(UserSession.expires_at < utcnow()).delete()   # limpeza oportunista
    db.session.commit()
    return user, None


def reset_password_with_passphrase(email: str, passphrase: str, new_password: str):
    """Troca a senha com e-mail + palavra-chave. Compartilha o contador de bloqueio do login."""
    generic = "E-mail ou palavra-chave incorretos."
    user = User.query.filter_by(email=normalize_email(email)).first()
    if user is None or not user.recovery_hash:
        verify_secret(_dummy_hash(), passphrase)
        return generic
    if _locked(user):
        return LOCKED_MSG
    if not verify_passphrase(user.recovery_hash, passphrase):
        _register_failure(user)
        return generic
    problem = password_problem(new_password)
    if problem:
        return problem
    user.password_hash = hash_secret(new_password)
    user.failed_logins, user.locked_until = 0, None
    UserSession.query.filter_by(user_id=user.id).delete()    # encerra todas as sessões
    db.session.commit()
    return None


# ---------------------------------------------------------------- sessões

def start_session(user: User) -> tuple[str, object]:
    token = secrets.token_urlsafe(32)
    expires = utcnow() + timedelta(days=current_app.config["SESSION_DAYS"])
    db.session.add(UserSession(
        user_id=user.id, token_hash=sha256(token), expires_at=expires,
        ip=(request.remote_addr or "")[:64], user_agent=(request.headers.get("User-Agent") or "")[:200],
    ))
    db.session.commit()
    return token, expires


def set_cookie(response, token: str, expires) -> None:
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="Lax", secure=current_app.config["COOKIE_SECURE"],
        path="/", expires=expires.replace(tzinfo=None) if hasattr(expires, "tzinfo") else expires,
    )


def clear_cookie(response) -> None:
    response.delete_cookie(COOKIE, path="/")


def end_session() -> None:
    token = request.cookies.get(COOKIE)
    if token:
        UserSession.query.filter_by(token_hash=sha256(token)).delete()
        db.session.commit()


def end_all_sessions(user: User) -> None:
    UserSession.query.filter_by(user_id=user.id).delete()
    db.session.commit()


def load_user() -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = UserSession.query.options(joinedload(UserSession.user)).filter_by(token_hash=sha256(token)).first()
    if row is None or row.expires_at < utcnow():
        return None
    return row.user


def current_user() -> User | None:
    return getattr(g, "user", None)


# ---------------------------------------------------------------- conta

def delete_account(user: User) -> None:
    """Apaga TODOS os dados do usuário (LGPD). Deletes em massa: o banco aplica os ON DELETE CASCADE."""
    uid = user.id
    blob_urls = [u for (u,) in db.session.query(FileAsset.storage_url).filter(FileAsset.owner_id == uid, FileAsset.storage_url.isnot(None))]
    for model in (Campaign, Player, FileAsset):          # campanhas primeiro: personagens referenciam jogadores
        db.session.execute(delete(model).where(model.owner_id == uid))
    db.session.execute(delete(User).where(User.id == uid))
    db.session.commit()
    blobstore.delete(blob_urls)

from functools import wraps
from urllib.parse import urlparse

from flask import abort, flash, redirect, request, url_for

from app.extensions import db
from app.services.campaigns import get_current_campaign
from app.services.ownership import is_owned
from app.services.uploads import delete_image


def get_or_404(model, ident):
    """Carrega por id e só devolve se pertencer ao usuário logado; senão 404 (não revela que existe)."""
    obj = db.session.get(model, ident) if ident is not None else None
    if obj is None or not is_owned(obj):
        abort(404)
    return obj


def require_campaign(view):
    """Injeta `campaign` (a campanha atual) ou redireciona para criar a primeira."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        campaign = get_current_campaign()
        if campaign is None:
            flash("Crie a primeira campanha para começar.", "info")
            return redirect(url_for("campaigns.new"))
        return view(*args, campaign=campaign, **kwargs)

    return wrapper


def safe_next(default):
    """Redirecionamento seguro: só aceita caminhos locais."""
    target = request.values.get("next") or ""
    parsed = urlparse(target)
    if target.startswith("/") and not target.startswith("//") and not parsed.netloc and "\\" not in target:
        return target
    return default


def assign(obj, form, names):
    """Copia campos do formulário para o modelo (sem populate_obj, que tocaria em campos de arquivo)."""
    for name in names:
        value = getattr(form, name).data
        if isinstance(value, str):
            value = value.strip() or None
        setattr(obj, name, value)


def finalize_images(ok, created=(), obsolete=()):
    """Após o commit: remove imagens antigas; se falhou, remove as recém-gravadas."""
    for name in (obsolete if ok else created):
        delete_image(name)


def flash_form_errors():
    flash("Verifique os campos destacados no formulário.", "error")


def id_or_none(value):
    return value or None


def search_filters(**kw):
    """Parâmetros de filtro ativos (para o botão «limpar filtros»)."""
    return {k: v for k, v in kw.items() if v not in (None, "", 0)}

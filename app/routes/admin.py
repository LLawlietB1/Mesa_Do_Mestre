"""Administração: liberar/revogar o envio de imagens. Só contas com papel ADMIN (senão 404)."""
from flask import Blueprint, abort, flash, g, redirect, render_template, url_for

from app.extensions import db
from app.models import User
from app.services.common import safe_commit
from app.services.uploads import used_bytes

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def only_admins():
    if g.get("user") is None or not g.user.is_admin:
        abort(404)                                   # não revela que a área existe


@bp.get("/imagens")
def images():
    users = User.query.order_by(User.images_requested_at.is_(None), User.images_requested_at.desc(), User.name).all()
    pending = [u for u in users if u.images_requested_at and not u.can_upload_images]
    usage = {u.id: used_bytes(u.id) for u in users}
    return render_template("admin/images.html", users=users, pending=pending, usage=usage)


def _set(user_id: int, enabled: bool):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    user.images_enabled = enabled
    if enabled:
        user.images_requested_at = None
    if safe_commit():
        flash(f"Envio de imagens {'liberado' if enabled else 'revogado'} para {user.name}.", "success")
    else:
        flash("Não foi possível salvar.", "error")
    return redirect(url_for("admin.images"))


@bp.post("/imagens/<int:user_id>/liberar")
def approve(user_id):
    return _set(user_id, True)


@bp.post("/imagens/<int:user_id>/revogar")
def revoke(user_id):
    return _set(user_id, False)

from flask import Blueprint, Response, flash, g, redirect, render_template, url_for

from app.forms.backup import BackupForm, RestoreForm
from app.services import backup as backup_service
from app.services.backup import BackupError

bp = Blueprint("backup", __name__, url_prefix="/backup")
MAX_DOWNLOAD = 4_200_000     # tamanho máximo do .zip baixado


@bp.get("/")
def index():
    return render_template("backup/index.html", backup_form=BackupForm(), restore_form=RestoreForm())


@bp.post("/baixar")
def download():
    """Gera e baixa o backup dos dados DO USUÁRIO logado (nada de outros usuários)."""
    form = BackupForm()
    if not form.validate_on_submit():
        flash("Requisição inválida.", "error")
        return redirect(url_for("backup.index"))
    try:
        name, payload = backup_service.create_backup(g.user)
    except BackupError as exc:
        flash(str(exc), "error")
        return redirect(url_for("backup.index"))
    if len(payload) > MAX_DOWNLOAD:
        flash("O backup passou do limite de download da hospedagem (4 MB). Remova imagens que não usa mais e tente de novo.", "error")
        return redirect(url_for("backup.index"))
    return Response(payload, mimetype="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store",
    })


@bp.post("/restaurar")
def restore():
    form = RestoreForm()
    if not form.validate_on_submit():
        flash("; ".join(e for errs in form.errors.values() for e in errs) or "Dados inválidos.", "error")
        return redirect(url_for("backup.index"))
    if not form.confirm.data:
        flash("Marque a confirmação para restaurar o backup.", "error")
        return redirect(url_for("backup.index"))
    try:
        info = backup_service.restore_backup(g.user, form.backup_file.data.stream)
    except BackupError as exc:
        flash(f"Restauração cancelada — nada foi alterado. Motivo: {exc}", "error")
    else:
        flash(f"Backup restaurado: {info['rows']} registros e {info['images']} imagem(ns) da sua conta.", "success")
    return redirect(url_for("backup.index"))

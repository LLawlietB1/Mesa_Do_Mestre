from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.constants import CHARACTER_STATUS, keys
from app.models import Character, ExperienceHistory
from app.routes.helpers import get_or_404, require_campaign
from app.services import xp as xp_service
from app.services.xp import XPError

bp = Blueprint("xp", __name__, url_prefix="/xp")

ACTIONS = {"add", "set", "reset", "complete", "new_cycle"}


@bp.get("/")
@require_campaign
def panel(campaign):
    status = request.args.get("status", "ativo")
    query = Character.query.filter_by(campaign_id=campaign.id)
    if status in keys(CHARACTER_STATUS):
        query = query.filter_by(status=status)
    characters = query.order_by(Character.name).all()
    return render_template("xp/panel.html", characters=characters, status=status)


@bp.post("/api/personagens/<int:character_id>")
def api_apply(character_id):
    """Altera o XP de UM personagem. Corpo JSON: {action, value?, reason?}. Devolve o valor persistido."""
    character = get_or_404(Character, character_id)
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in ACTIONS:
        return jsonify(ok=False, error="Ação de XP desconhecida."), 400
    reason = data.get("reason")
    try:
        if action == "add":
            result = xp_service.apply_delta(character, data.get("value"), reason)
        elif action == "set":
            result = xp_service.set_percent(character, data.get("value"), reason)
        elif action == "reset":
            result = xp_service.reset(character, reason)
        elif action == "complete":
            result = xp_service.complete(character, reason)
        else:
            result = xp_service.start_new_cycle(character, reason)
    except XPError as exc:
        return jsonify(ok=False, error=str(exc), percent=character.xp_percent), 400
    return jsonify(
        ok=True, percent=character.xp_percent, previous=result.previous, delta=result.delta,
        changed=result.changed, clamped=result.clamped, cycle=character.xp_cycle,
        complete=character.xp_percent == 100, message=xp_service.describe(result),
    )


@bp.post("/lote")
@require_campaign
def bulk(campaign):
    ids = request.form.getlist("character_ids")
    direction = request.form.get("direction")
    try:
        amount = xp_service.parse_int(request.form.get("amount"), "percentual")
        if amount <= 0:
            raise XPError("Informe um percentual maior que zero.")
        if direction not in ("up", "down"):
            raise XPError("Escolha aumentar ou reduzir.")
        results = xp_service.apply_bulk(campaign.id, ids, amount if direction == "up" else -amount, request.form.get("reason"))
    except XPError as exc:
        flash(str(exc), "error")
    else:
        flash("Alteração coletiva aplicada: " + "; ".join(xp_service.describe(r) for r in results), "success")
    return redirect(url_for("xp.panel", status=request.form.get("status_filter") or "ativo"))


@bp.get("/personagens/<int:character_id>/historico")
def history(character_id):
    character = get_or_404(Character, character_id)
    entries = ExperienceHistory.query.filter_by(character_id=character.id).order_by(ExperienceHistory.id.desc()).all()
    return render_template("xp/history.html", character=character, entries=entries)

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, url_for

from app.forms.messages import MessageForm
from app.models import CampaignPlayer, Player
from app.routes.helpers import get_or_404, require_campaign
from app.services import messaging
from app.services.messaging import MAX_BODY, SendError

bp = Blueprint("messages", __name__, url_prefix="/mensagens")


def _campaign_players(campaign):
    return (Player.query.join(CampaignPlayer).filter(
        CampaignPlayer.campaign_id == campaign.id, CampaignPlayer.status == "ativo",
        Player.owner_id == g.user.id, Player.status != "arquivado").order_by(Player.display_name).all())


def _sendable(p):
    return bool(p.phone and p.messaging_consent)


@bp.get("/")
@require_campaign
def index(campaign):
    players = _campaign_players(campaign)
    form = MessageForm(players=[p for p in players if _sendable(p)])
    preselect = request.args.get("jogador", type=int)
    if preselect and any(p.id == preselect for p in players):
        form.recipients.data = [preselect]
    return render_template("messages/index.html", form=form, players=players, sendable=_sendable)


@bp.post("/previa")
@require_campaign
def preview(campaign):
    players = _campaign_players(campaign)
    ok_players = [p for p in players if _sendable(p)]
    form = MessageForm(players=ok_players)
    if not form.validate_on_submit():
        flash("Escolha o tipo de mensagem e ao menos um destinatário.", "error")
        return render_template("messages/index.html", form=form, players=players, sendable=_sendable)
    by_id = {p.id: p for p in ok_players}            # só jogadores desta conta/campanha, com telefone e consentimento
    drafts, skipped = [], []
    for pid in form.recipients.data:
        player = by_id[pid]
        text = messaging.build_text(form.kind.data, player, campaign, form.extra.data or "")
        if text is None:
            skipped.append(player.display_name)
            continue
        drafts.append({"player": player, "text": text})
    if not drafts:
        flash("Não há dados para enviar a esses jogadores nesta categoria" + (f" ({', '.join(skipped)})." if skipped else "."), "warning")
        return render_template("messages/index.html", form=form, players=players, sendable=_sendable)
    if skipped:
        flash("Sem dados para: " + ", ".join(skipped) + ".", "info")
    return render_template(
        "messages/preview.html", drafts=drafts, wa_link=messaging.wa_link, sms_link=messaging.sms_link,
        server=messaging.server_channels() if g.user.can_send_messages else {"sms": False, "whatsapp": False},
        max_body=MAX_BODY,
    )


@bp.post("/enviar")
def send():
    """Envio direto pelo servidor (JSON). Exige conta liberada, configuração do provedor e consentimento."""
    data = request.get_json(silent=True) or {}
    channel, body = data.get("channel"), (data.get("body") or "").strip()
    if channel not in ("sms", "whatsapp"):
        return jsonify(ok=False, error="Canal inválido."), 400
    if not g.user.can_send_messages:
        return jsonify(ok=False, error="O envio pelo servidor não está liberado para a sua conta. Use os links de WhatsApp/SMS."), 403
    if not messaging.server_channels().get(channel):
        return jsonify(ok=False, error="O provedor de mensagens não está configurado para este canal."), 400
    if not body or len(body) > MAX_BODY:
        return jsonify(ok=False, error=f"A mensagem deve ter de 1 a {MAX_BODY} caracteres."), 400
    player = get_or_404(Player, data.get("player_id") if isinstance(data.get("player_id"), int) else None)
    if not _sendable(player):
        return jsonify(ok=False, error="Jogador sem telefone ou sem consentimento para receber mensagens."), 400
    if messaging.sent_last_24h(g.user.id) >= current_app.config["MESSAGES_PER_DAY"]:
        return jsonify(ok=False, error="Limite diário de mensagens atingido. Tente amanhã ou use os links."), 429
    try:
        sid = messaging.send_via_twilio(channel, player.phone, body)
    except SendError as exc:
        messaging.log_message(g.user.id, player.id, channel, False, error=str(exc), chars=len(body))
        return jsonify(ok=False, error=str(exc)), 502
    messaging.log_message(g.user.id, player.id, channel, True, provider_id=sid, chars=len(body))
    return jsonify(ok=True, message=f"Enviado para {player.display_name}.")

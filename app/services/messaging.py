"""Mensagens para jogadores: monta o texto (somente dados públicos, nunca anotações do mestre) e entrega por
(1) links de WhatsApp/SMS que abrem no celular/PC do mestre (sem custo, sem servidor) ou
(2) envio direto pelo servidor via Twilio (opcional, liberado por conta)."""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from flask import current_app

from app.extensions import db
from app.models import CharacterItem, GameSession, MessageLog, Player, Quest
from app.models.mixins import utcnow

MAX_BODY = 1500

KINDS = [
    ("personagem", "Ficha resumida e XP dos personagens do jogador"),
    ("inventario", "Inventário dos personagens do jogador"),
    ("proxima_sessao", "Aviso da próxima sessão"),
    ("sessao_resumo", "Resumo da última sessão"),
    ("missoes", "Missões em andamento e objetivos"),
    ("livre", "Mensagem livre"),
]


class PhoneError(ValueError):
    pass


def normalize_phone(raw: str, default_cc: str | None = None) -> str:
    """Converte para E.164 (+5511999998888). Números de 10-11 dígitos recebem o código do país padrão."""
    default_cc = default_cc or current_app.config["DEFAULT_COUNTRY_CODE"]
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if not digits:
        raise PhoneError("Informe um telefone.")
    if text.startswith("+"):
        pass
    elif digits.startswith("00"):
        digits = digits[2:]
    elif len(digits) in (10, 11):
        digits = default_cc + digits
    if not 10 <= len(digits) <= 15:
        raise PhoneError("Telefone inválido. Use DDD + número (ex.: 11 99999-8888) ou o formato internacional +55…")
    return "+" + digits


def wa_link(phone: str, text: str) -> str:
    return f"https://wa.me/{phone.lstrip('+')}?text={urllib.parse.quote(text)}"


def sms_link(phone: str, text: str) -> str:
    return f"sms:{phone}?body={urllib.parse.quote(text)}"


# ---------------------------------------------------------------- textos

def _character_lines(player: Player, campaign_id: int):
    return [c for c in player.characters if c.campaign_id == campaign_id and c.status == "ativo"]


def _fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def build_text(kind: str, player: Player, campaign, extra: str = "") -> str | None:
    """Texto para um jogador. Devolve None quando não há nada a enviar a ele nesta categoria."""
    cid = campaign.id
    head = f"Olá, {player.display_name}! ({campaign.name})\n"
    body: list[str] = []
    if kind == "personagem":
        chars = _character_lines(player, cid)
        if not chars:
            return None
        for c in chars:
            info = " ".join(x for x in (c.race, c.char_class) if x)
            lvl = f", nível {c.level}" if c.level is not None else ""
            body.append(f"• {c.name}{(' — ' + info) if info else ''}{lvl}\n  XP: {c.xp_percent}%"
                        + (" ✦ marco completo!" if c.xp_percent == 100 else ""))
    elif kind == "inventario":
        chars = _character_lines(player, cid)
        rows = []
        for c in chars:
            held = CharacterItem.query.filter_by(character_id=c.id).all()
            if held:
                rows.append(f"• {c.name}: " + ", ".join(f"{h.item.name} ×{h.quantity}" for h in held))
        if not rows:
            return None
        body = rows
    elif kind == "proxima_sessao":
        nxt = (GameSession.query.filter(GameSession.campaign_id == cid, GameSession.status == "agendada",
                                        GameSession.date >= date.today()).order_by(GameSession.date).first())
        if nxt is None:
            return None
        body.append(f"Próxima sessão: #{nxt.number} — {nxt.title}\nData: {_fmt_date(nxt.date)}")
        last = (GameSession.query.filter(GameSession.campaign_id == cid, GameSession.status == "realizada")
                .order_by(GameSession.number.desc()).first())
        if last and last.pending:
            body.append("Pendências da última sessão:\n" + last.pending.strip())
    elif kind == "sessao_resumo":
        last = (GameSession.query.filter(GameSession.campaign_id == cid, GameSession.status == "realizada")
                .order_by(GameSession.number.desc()).first())
        if last is None or not (last.summary or last.pending):
            return None
        body.append(f"Resumo da sessão #{last.number} — {last.title} ({_fmt_date(last.date)}):")
        if last.summary:
            body.append(last.summary.strip())
        if last.pending:
            body.append("Pendências:\n" + last.pending.strip())
    elif kind == "missoes":
        quests = (Quest.query.filter(Quest.campaign_id == cid, Quest.status.in_(["em_andamento", "disponivel"]))
                  .order_by(Quest.title).all())
        if not quests:
            return None
        for q in quests:
            lines = [f"• {q.title}" + (f" (prazo {_fmt_date(q.deadline)})" if q.deadline else "")]
            lines += [f"   {'✔' if o.done else '○'} {o.description}" for o in q.objectives]
            body.append("\n".join(lines))
    elif kind == "livre":
        pass
    else:
        raise ValueError("Tipo de mensagem desconhecido.")
    if extra.strip():
        body.append(extra.strip().replace("{jogador}", player.display_name).replace("{campanha}", campaign.name))
    if not body:
        return None
    text = head + "\n" + "\n\n".join(body)
    return text[:MAX_BODY]


# ---------------------------------------------------------------- envio pelo servidor (Twilio)

def server_channels() -> dict[str, bool]:
    c = current_app.config
    base = bool(c["TWILIO_ACCOUNT_SID"] and c["TWILIO_AUTH_TOKEN"])
    return {"sms": base and bool(c["TWILIO_SMS_FROM"]), "whatsapp": base and bool(c["TWILIO_WHATSAPP_FROM"])}


def sent_last_24h(owner_id: int) -> int:
    return MessageLog.query.filter(MessageLog.owner_id == owner_id, MessageLog.created_at >= utcnow() - timedelta(days=1)).count()


class SendError(Exception):
    pass


def send_via_twilio(channel: str, to_phone: str, body: str) -> str:
    """Envia uma mensagem e devolve o SID do Twilio. Levanta SendError com mensagem legível."""
    c = current_app.config
    if not server_channels().get(channel):
        raise SendError("Envio pelo servidor não está configurado para este canal.")
    sender = c["TWILIO_SMS_FROM"] if channel == "sms" else c["TWILIO_WHATSAPP_FROM"]
    if channel == "whatsapp":
        to_phone, sender = "whatsapp:" + to_phone, sender if sender.startswith("whatsapp:") else "whatsapp:" + sender
    url = f"https://api.twilio.com/2010-04-01/Accounts/{c['TWILIO_ACCOUNT_SID']}/Messages.json"
    payload = urllib.parse.urlencode({"To": to_phone, "From": sender, "Body": body}).encode()
    auth = base64.b64encode(f"{c['TWILIO_ACCOUNT_SID']}:{c['TWILIO_AUTH_TOKEN']}".encode()).decode()
    req = urllib.request.Request(url, data=payload, headers={"Authorization": f"Basic {auth}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:      # noqa: S310 (URL fixa https)
            return json.loads(resp.read()).get("sid", "")
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read()).get("message", "")
        except (ValueError, OSError):
            msg = ""
        raise SendError(f"O provedor recusou o envio: {msg or exc.code}"[:280]) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SendError("Não foi possível falar com o provedor de mensagens. Tente novamente.") from None


def log_message(owner_id: int, player_id: int | None, channel: str, ok: bool, provider_id: str = "", error: str = "", chars: int = 0):
    db.session.add(MessageLog(owner_id=owner_id, player_id=player_id, channel=channel, ok=ok,
                              provider_id=provider_id or None, error=(error or None), chars=chars))
    db.session.commit()

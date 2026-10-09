"""Mensagens aos jogadores: telefone, textos (sem vazar segredos), links e envio pelo servidor."""
import json
from datetime import date, timedelta

import pytest

from app.models import GameSession, MessageLog, NPC, Quest, QuestObjective
from app.services import messaging
from app.services.messaging import PhoneError, SendError, normalize_phone


@pytest.mark.parametrize("raw,expected", [
    ("(11) 99999-8888", "+5511999998888"),
    ("11 3333-4444", "+551133334444"),
    ("+55 11 99999-8888", "+5511999998888"),
    ("0055 11 99999-8888", "+5511999998888"),
    ("+1 (555) 123-4567", "+15551234567"),
])
def test_normalize_phone(app, raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "123", "+1234", "99999999999999999999"])
def test_normalize_phone_invalid(app, raw):
    with pytest.raises(PhoneError):
        normalize_phone(raw)


def test_links_are_url_encoded(app):
    assert messaging.wa_link("+5511999998888", "Olá & tchau\nlinha 2") == "https://wa.me/5511999998888?text=Ol%C3%A1%20%26%20tchau%0Alinha%202"
    assert messaging.sms_link("+5511999998888", "a b") == "sms:+5511999998888?body=a%20b"


def test_player_form_normalizes_and_requires_phone_for_consent(client, db):
    from app.models import Player
    r = client.post("/jogadores/novo", data={"display_name": "Ana", "status": "ativo", "phone": "(11) 98888-7777", "messaging_consent": "y"})
    assert r.status_code == 302
    p = Player.query.one()
    assert p.phone == "+5511988887777" and p.messaging_consent is True
    client.post(f"/jogadores/{p.id}/editar", data={"display_name": "Ana", "status": "ativo", "phone": "", "messaging_consent": "y"})
    db.session.refresh(p)
    assert p.phone is None and p.messaging_consent is False          # sem telefone não há consentimento
    r = client.post("/jogadores/novo", data={"display_name": "Bia", "status": "ativo", "phone": "123"})
    assert "Telefone inválido" in r.get_data(as_text=True) and Player.query.count() == 1


@pytest.fixture()
def table(db, make_campaign, make_character, make_player, select_campaign, user):
    """Campanha com 2 jogadores (um com consentimento, outro sem) e dados SECRETOS que nunca podem vazar."""
    c = make_campaign("Valdris")
    ana = make_player("Ana", phone="+5511999998888", messaging_consent=True)
    bia = make_player("Bia", phone="+5511977776666", messaging_consent=False)
    cris = make_player("Cris", messaging_consent=True)            # sem telefone
    lyra = make_character(c, "Lyra", player=ana, race="Elfa", char_class="Maga", level=5, xp_percent=100, master_notes="SEGREDO-PERSONAGEM")
    make_character(c, "Mira", player=bia)
    make_character(c, "Zed", player=cris)
    npc = NPC(name="Vilão", campaign_id=c.id, secrets="SEGREDO-NPC", master_notes="SEGREDO-NPC2")
    q = Quest(title="O Selo", campaign_id=c.id, status="em_andamento", master_notes="SEGREDO-MISSAO", rewards="SEGREDO-RECOMPENSA")
    db.session.add_all([npc, q]); db.session.flush()
    q.objectives.append(QuestObjective(description="Achar o mapa", done=True))
    q.objectives.append(QuestObjective(description="Entrar na torre", done=False))
    db.session.add_all([
        GameSession(campaign_id=c.id, number=1, title="Taverna", date=date.today() - timedelta(days=7), status="realizada",
                    summary="O grupo se conheceu.", pending="Comprar tochas", master_notes="SEGREDO-SESSAO"),
        GameSession(campaign_id=c.id, number=2, title="Estrada", date=date.today() + timedelta(days=5), status="agendada",
                    master_notes="SEGREDO-SESSAO2"),
    ])
    db.session.commit()
    select_campaign(c)
    return dict(c=c, ana=ana, bia=bia, cris=cris, lyra=lyra)


def _preview(client, table, kind, recipients, extra=""):
    return client.post("/mensagens/previa", data={"kind": kind, "recipients": recipients, "extra": extra})


@pytest.mark.parametrize("kind", [k for k, _ in messaging.KINDS])
def test_texts_never_contain_private_master_data(client, table, kind):
    r = _preview(client, table, kind, [table["ana"].id], extra="Até lá!")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "SEGREDO" not in html


def test_personagem_text_content(client, table):
    html = _preview(client, table, "personagem", [table["ana"].id]).get_data(as_text=True)
    assert "Lyra" in html and "Elfa Maga" in html and "nível 5" in html and "XP: 100%" in html and "marco completo" in html
    assert "https://wa.me/5511999998888?text=" in html and "sms:+5511999998888?body=" in html


def test_session_and_quest_texts(client, table):
    html = _preview(client, table, "proxima_sessao", [table["ana"].id]).get_data(as_text=True)
    assert "Estrada" in html and "Comprar tochas" in html
    html = _preview(client, table, "sessao_resumo", [table["ana"].id]).get_data(as_text=True)
    assert "O grupo se conheceu." in html
    html = _preview(client, table, "missoes", [table["ana"].id]).get_data(as_text=True)
    assert "O Selo" in html and "✔ Achar o mapa" in html and "○ Entrar na torre" in html


def test_free_message_placeholders(client, table):
    html = _preview(client, table, "livre", [table["ana"].id], extra="Oi {jogador}, sessão da {campanha} amanhã!").get_data(as_text=True)
    assert "Oi Ana, sessão da Valdris amanhã!" in html


def test_players_without_phone_or_consent_cannot_be_targeted(client, table):
    for key in ("bia", "cris"):
        r = _preview(client, table, "personagem", [table[key].id])
        assert r.status_code == 200 and "data-msg-text" not in r.get_data(as_text=True)


def test_nothing_to_send_is_reported(client, table, db):
    from app.models import CharacterItem
    r = _preview(client, table, "inventario", [table["ana"].id])
    assert "Não há dados para enviar" in r.get_data(as_text=True)


def test_send_requires_permission_config_and_valid_input(client, table, user, db, app):
    payload = {"player_id": table["ana"].id, "channel": "sms", "body": "oi"}
    assert client.post("/mensagens/enviar", json=payload).status_code == 403           # conta não liberada
    user.can_send_messages = True; db.session.commit()
    assert client.post("/mensagens/enviar", json=payload).status_code == 400            # Twilio não configurado
    app.config.update(TWILIO_ACCOUNT_SID="AC123", TWILIO_AUTH_TOKEN="tok", TWILIO_SMS_FROM="+15550001111", TWILIO_WHATSAPP_FROM="+15550002222")
    assert client.post("/mensagens/enviar", json={**payload, "channel": "fax"}).status_code == 400
    assert client.post("/mensagens/enviar", json={**payload, "body": ""}).status_code == 400
    assert client.post("/mensagens/enviar", json={**payload, "body": "x" * 1501}).status_code == 400
    assert client.post("/mensagens/enviar", json={**payload, "player_id": table["bia"].id}).status_code == 400   # sem consentimento
    assert client.post("/mensagens/enviar", json={**payload, "player_id": table["cris"].id}).status_code == 400   # sem telefone
    assert client.post("/mensagens/enviar", json={**payload, "player_id": "abc"}).status_code == 404
    assert MessageLog.query.count() == 0


def test_send_success_logs_without_body_and_enforces_daily_cap(client, table, user, db, app, monkeypatch):
    user.can_send_messages = True; db.session.commit()
    app.config.update(TWILIO_ACCOUNT_SID="AC123", TWILIO_AUTH_TOKEN="tok", TWILIO_SMS_FROM="+15550001111", MESSAGES_PER_DAY=2)
    sent = []
    monkeypatch.setattr(messaging, "send_via_twilio", lambda ch, to, body: sent.append((ch, to, body)) or "SM123")
    payload = {"player_id": table["ana"].id, "channel": "sms", "body": "Sessão amanhã"}
    r = client.post("/mensagens/enviar", json=payload)
    assert r.status_code == 200 and r.get_json()["ok"] and sent == [("sms", "+5511999998888", "Sessão amanhã")]
    log = MessageLog.query.one()
    assert log.ok and log.provider_id == "SM123" and log.chars == len("Sessão amanhã")
    assert not hasattr(log, "body")
    client.post("/mensagens/enviar", json=payload)
    assert client.post("/mensagens/enviar", json=payload).status_code == 429             # limite diário


def test_send_failure_is_logged_and_reported(client, table, user, db, app, monkeypatch):
    user.can_send_messages = True; db.session.commit()
    app.config.update(TWILIO_ACCOUNT_SID="AC123", TWILIO_AUTH_TOKEN="tok", TWILIO_SMS_FROM="+15550001111")

    def boom(*a):
        raise SendError("O provedor recusou o envio: número inválido")
    monkeypatch.setattr(messaging, "send_via_twilio", boom)
    r = client.post("/mensagens/enviar", json={"player_id": table["ana"].id, "channel": "sms", "body": "oi"})
    assert r.status_code == 502 and "recusou" in r.get_json()["error"]
    assert MessageLog.query.one().ok is False


def test_twilio_request_format(app, monkeypatch):
    app.config.update(TWILIO_ACCOUNT_SID="AC123", TWILIO_AUTH_TOKEN="tok", TWILIO_SMS_FROM="+15550001111", TWILIO_WHATSAPP_FROM="+15550002222")
    captured = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"sid": "SMabc"}).encode()

    def fake_urlopen(req, timeout):
        captured.update(url=req.full_url, data=req.data.decode(), auth=req.get_header("Authorization"), timeout=timeout)
        return Resp()

    monkeypatch.setattr(messaging.urllib.request, "urlopen", fake_urlopen)
    assert messaging.send_via_twilio("whatsapp", "+5511999998888", "Olá") == "SMabc"
    assert captured["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert "To=whatsapp%3A%2B5511999998888" in captured["data"] and "From=whatsapp%3A%2B15550002222" in captured["data"]
    assert captured["auth"].startswith("Basic ") and captured["timeout"] == 10


def test_server_send_ui_only_for_permitted_accounts(client, table, user, db, app):
    app.config.update(TWILIO_ACCOUNT_SID="AC123", TWILIO_AUTH_TOKEN="tok", TWILIO_SMS_FROM="+15550001111")
    assert "data-msg-send" not in _preview(client, table, "personagem", [table["ana"].id]).get_data(as_text=True)
    user.can_send_messages = True; db.session.commit()
    assert 'data-msg-send="sms"' in _preview(client, table, "personagem", [table["ana"].id]).get_data(as_text=True)


def test_messages_page_and_grant_cli(client, table, app, user, db):
    assert client.get("/mensagens/").status_code == 200
    runner = app.test_cli_runner()
    assert "liberado" in runner.invoke(args=["grant-messaging", user.email]).output
    db.session.refresh(user); assert user.can_send_messages
    assert "revogado" in runner.invoke(args=["grant-messaging", user.email, "--revoke"]).output
    assert "Nenhum usuário" in runner.invoke(args=["grant-messaging", "x@y.com"]).output

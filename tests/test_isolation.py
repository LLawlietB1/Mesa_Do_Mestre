"""Isolamento entre usuários: o usuário A nunca lê, altera ou apaga dados do usuário B (varredura de IDOR)."""
import pytest

from app.models import (Campaign, Character, CharacterItem, CharacterNPCRelationship, FileAsset, GameSession, Item,
                        Note, NPC, Player, Quest, QuestObjective, SessionEvent, UserSession)
from app.services.campaigns import enroll_player


@pytest.fixture()
def theirs(db, other_user):
    """Um universo completo de dados do usuário B."""
    c = Campaign(name="Campanha-do-B", status="ativa", owner_id=other_user.id)
    p = Player(display_name="Jogador-do-B", owner_id=other_user.id, phone="+5511999990000", messaging_consent=True)
    db.session.add_all([c, p]); db.session.flush()
    enroll_player(c.id, p.id)
    ch = Character(name="Personagem-do-B", campaign_id=c.id, player_id=p.id, xp_percent=33)
    npc = NPC(name="NPC-do-B", campaign_id=c.id)
    quest = Quest(title="Missao-do-B", campaign_id=c.id)
    item = Item(name="Item-do-B", campaign_id=c.id)
    note = Note(title="Nota-do-B", content="segredo do B", campaign_id=c.id)
    sess = GameSession(campaign_id=c.id, number=1, title="Sessao-do-B", date=__import__("datetime").date(2030, 1, 1))
    asset = FileAsset(id="b" * 32, owner_id=other_user.id, content_type="image/webp", size=4, data=b"RIFF")
    db.session.add_all([ch, npc, quest, item, note, sess, asset]); db.session.flush()
    obj = QuestObjective(quest_id=quest.id, description="obj-do-B")
    rel = CharacterNPCRelationship(character_id=ch.id, npc_id=npc.id, kind="alianca")
    hold = CharacterItem(item_id=item.id, character_id=ch.id, quantity=2)
    ev = SessionEvent(session_id=sess.id, campaign_id=c.id, description="evento-do-B")
    db.session.add_all([obj, rel, hold, ev]); db.session.commit()
    return dict(c=c, p=p, ch=ch, npc=npc, quest=quest, item=item, note=note, sess=sess, asset=asset, obj=obj, rel=rel,
                hold=hold, ev=ev)


def snapshot():
    return {m.__name__: m.query.count() for m in (Campaign, Player, Character, Note, GameSession, SessionEvent, NPC,
                                                  CharacterNPCRelationship, Quest, QuestObjective, Item, CharacterItem, FileAsset)}


def test_get_pages_of_other_user_are_404(client, theirs):
    t = theirs
    urls = [
        f"/campanhas/{t['c'].id}", f"/campanhas/{t['c'].id}/editar", f"/jogadores/{t['p'].id}", f"/jogadores/{t['p'].id}/editar",
        f"/personagens/{t['ch'].id}", f"/personagens/{t['ch'].id}/editar", f"/xp/personagens/{t['ch'].id}/historico",
        f"/notas/{t['note'].id}/editar", f"/sessoes/{t['sess'].id}", f"/sessoes/{t['sess'].id}/editar",
        f"/npcs/{t['npc'].id}", f"/npcs/{t['npc'].id}/editar", f"/missoes/{t['quest'].id}", f"/missoes/{t['quest'].id}/editar",
        f"/itens/{t['item'].id}", f"/itens/{t['item'].id}/editar", f"/media/{t['asset'].id}",
    ]
    for url in urls:
        assert client.get(url).status_code == 404, url


def test_mutating_requests_on_other_user_data_are_404_and_change_nothing(client, theirs, other_user, db):
    t = theirs
    before = snapshot()
    cid, pid, chid = t["c"].id, t["p"].id, t["ch"].id
    posts = [
        ("/campanhas/selecionar", {"campaign_id": cid}),
        (f"/campanhas/{cid}/status", {"status": "encerrada"}),
        (f"/campanhas/{cid}/excluir", {"confirm_name": "Campanha-do-B"}),
        (f"/campanhas/{cid}/jogadores", {"player_id": pid}),
        (f"/campanhas/{cid}/jogadores/{pid}/remover", {}),
        (f"/campanhas/{cid}/editar", {"name": "HACK", "status": "ativa"}),
        (f"/jogadores/{pid}/status", {"status": "arquivado"}),
        (f"/jogadores/{pid}/excluir", {}),
        (f"/jogadores/{pid}/editar", {"display_name": "HACK", "status": "ativo"}),
        (f"/personagens/{chid}/status", {"status": "morto"}),
        (f"/personagens/{chid}/excluir", {}),
        (f"/personagens/{chid}/editar", {"name": "HACK", "player_id": pid, "status": "ativo"}),
        (f"/notas/{t['note'].id}/alternar/important", {}),
        (f"/notas/{t['note'].id}/editar", {"title": "HACK", "content": "x", "category": "outros"}),
        (f"/notas/{t['note'].id}/excluir", {}),
        (f"/sessoes/{t['sess'].id}/excluir", {}),
        (f"/sessoes/{t['sess'].id}/editar", {"number": 1, "title": "HACK", "date": "2030-01-01", "status": "agendada"}),
        (f"/sessoes/{t['sess'].id}/acontecimentos", {"description": "HACK"}),
        (f"/sessoes/{t['sess'].id}/acontecimentos/{t['ev'].id}/excluir", {}),
        (f"/npcs/{t['npc'].id}/excluir", {}),
        (f"/npcs/{t['npc'].id}/editar", {"name": "HACK", "status": "ativo"}),
        (f"/npcs/{t['npc'].id}/relacoes", {"character_id": chid, "kind": "rivalidade"}),
        (f"/npcs/{t['npc'].id}/relacoes/{t['rel'].id}/excluir", {}),
        (f"/missoes/{t['quest'].id}/status", {"status": "concluida"}),
        (f"/missoes/{t['quest'].id}/excluir", {}),
        (f"/missoes/{t['quest'].id}/editar", {"title": "HACK", "status": "planejada"}),
        (f"/missoes/{t['quest'].id}/objetivos", {"description": "HACK"}),
        (f"/missoes/{t['quest'].id}/objetivos/{t['obj'].id}/alternar", {}),
        (f"/missoes/{t['quest'].id}/objetivos/{t['obj'].id}/excluir", {}),
        (f"/itens/{t['item'].id}/excluir", {}),
        (f"/itens/{t['item'].id}/editar", {"name": "HACK", "category": "outro"}),
        (f"/itens/{t['item'].id}/posses", {"character_id": chid, "quantity": 1}),
        (f"/itens/{t['item'].id}/posses/{t['hold'].id}/excluir", {}),
    ]
    for url, data in posts:
        assert client.post(url, data=data).status_code == 404, url
    r = client.post(f"/xp/api/personagens/{chid}", json={"action": "set", "value": 99})
    assert r.status_code == 404 and r.is_json
    assert snapshot() == before
    db.session.expire_all()
    assert db.session.get(Character, chid).xp_percent == 33 and db.session.get(Character, chid).status == "ativo"
    assert db.session.get(Campaign, cid).name == "Campanha-do-B" and db.session.get(Campaign, cid).status == "ativa"
    assert db.session.get(Player, pid).display_name == "Jogador-do-B"
    assert db.session.get(Note, t["note"].id).title == "Nota-do-B"
    assert db.session.get(Quest, t["quest"].id).title == "Missao-do-B"
    assert db.session.get(QuestObjective, t["obj"].id).done is False


def test_lists_never_show_other_users_data(client, theirs, make_campaign, make_character):
    mine = make_campaign("Minha-Campanha")
    make_character(mine, "Meu-Personagem")
    pages = ["/", "/campanhas/", "/jogadores/", "/personagens/", "/xp/?status=todos", "/notas/?campanha=todas", "/sessoes/",
             "/npcs/", "/missoes/", "/itens/", "/mensagens/", f"/notas/?campanha={theirs['c'].id}", f"/jogadores/?campanha={theirs['c'].id}",
             f"/personagens/?jogador={theirs['p'].id}", f"/missoes/?personagem={theirs['ch'].id}", f"/itens/?personagem={theirs['ch'].id}"]
    for url in pages:
        html = client.get(url).get_data(as_text=True)
        assert "do-B" not in html and "segredo do B" not in html, url


def test_cannot_reference_other_users_records_from_own_forms(client, theirs, make_campaign, make_character, db):
    mine = make_campaign("Minha")
    mychar = make_character(mine, "Meu")
    client.post("/campanhas/selecionar", data={"campaign_id": mine.id})
    before = snapshot()
    t = theirs
    # personagem apontando para jogador do B
    r = client.post("/personagens/novo", data={"name": "Intruso", "player_id": t["p"].id, "status": "ativo"})
    assert r.status_code == 200
    # nota, sessão, missão, item, relação e posse apontando para personagens/NPC do B
    assert client.post("/notas/nova", data={"title": "x", "content": "y", "category": "outros", "character_id": t["ch"].id, "player_id": 0}).status_code == 200
    assert client.post("/sessoes/nova", data={"number": 5, "title": "x", "date": "2030-01-01", "status": "agendada", "participants": [t["ch"].id], "npcs": [t["npc"].id], "quests": [t["quest"].id]}).status_code == 200
    assert client.post("/missoes/nova", data={"title": "x", "status": "planejada", "characters": [t["ch"].id], "npc_id": t["npc"].id}).status_code == 200
    assert client.post("/itens/novo", data={"name": "x", "category": "outro", "character_id": t["ch"].id, "quantity": 1}).status_code == 200
    assert client.post("/xp/lote", data={"character_ids": [t["ch"].id, mychar.id], "amount": "10", "direction": "up"}, follow_redirects=True).status_code == 200
    db.session.expire_all()
    assert db.session.get(Character, t["ch"].id).xp_percent == 33 and db.session.get(Character, mychar.id).xp_percent == 0
    assert snapshot() == before


def test_campaign_id_in_session_of_another_account_is_ignored(client, theirs, make_campaign):
    mine = make_campaign("Minha")
    with client.session_transaction() as s:
        s["campaign_id"] = theirs["c"].id
    html = client.get("/").get_data(as_text=True)
    assert "do-B" not in html and "Minha" in html


def test_two_users_have_independent_sessions(app, user, other_user):
    from tests.conftest import _logged_client
    a, b = _logged_client(app, user.email), _logged_client(app, other_user.email)
    a.post("/campanhas/nova", data={"name": "So-do-A", "status": "ativa"})
    assert "So-do-A" in a.get("/campanhas/").get_data(as_text=True)
    assert "So-do-A" not in b.get("/campanhas/").get_data(as_text=True)
    assert UserSession.query.count() == 2


def test_messaging_endpoint_cannot_target_other_users_players(client, theirs, user, db, app):
    user.can_send_messages = True
    app.config.update(TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="t", TWILIO_SMS_FROM="+15550001111")
    db.session.commit()
    r = client.post("/mensagens/enviar", json={"player_id": theirs["p"].id, "channel": "sms", "body": "oi"})
    assert r.status_code == 404

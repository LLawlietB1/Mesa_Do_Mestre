"""Notas, sessões, NPCs, missões, itens e isolamento entre campanhas."""
import io
from datetime import date

import pytest

from app.models import (CharacterItem, CharacterNPCRelationship, GameSession, Item, Note, NPC, Quest,
                        QuestObjective, SessionEvent)


@pytest.fixture()
def world(make_campaign, make_character, select_campaign):
    """Duas campanhas independentes, cada uma com um personagem; a A fica selecionada."""
    a, b = make_campaign("Campanha A"), make_campaign("Campanha B")
    ca, cb = make_character(a, "Aria"), make_character(b, "Brutus")
    select_campaign(a)
    return a, b, ca, cb


# ---------------------------------------------------------------- notas

def test_note_create_edit_search_delete(client, world, db):
    a, b, ca, cb = world
    r = client.post("/notas/nova", data={"title": "Segredo do rei", "content": "O rei é um impostor", "category": "segredo",
                                         "character_id": ca.id, "player_id": 0, "important": "y"})
    assert r.status_code == 302
    n = Note.query.one()
    assert n.campaign_id == a.id and n.character_id == ca.id and n.player_id == ca.player_id and n.important
    client.post(f"/notas/{n.id}/editar", data={"title": "Segredo revisado", "content": "Novo texto", "category": "gancho",
                                               "character_id": 0, "player_id": 0})
    db.session.refresh(n)
    assert n.title == "Segredo revisado" and n.character_id is None and not n.important
    assert "Segredo revisado" in client.get("/notas/?q=revisado").get_data(as_text=True)
    assert "Segredo revisado" not in client.get("/notas/?q=inexistente").get_data(as_text=True)
    assert "Segredo revisado" in client.get("/notas/?categoria=gancho").get_data(as_text=True)
    assert "Segredo revisado" not in client.get("/notas/?categoria=segredo").get_data(as_text=True)
    client.post(f"/notas/{n.id}/alternar/archived")
    assert "Segredo revisado" not in client.get("/notas/").get_data(as_text=True)
    assert "Segredo revisado" in client.get("/notas/?arquivadas=sim").get_data(as_text=True)
    client.post(f"/notas/{n.id}/excluir")
    assert Note.query.count() == 0


def test_note_rejects_character_from_other_campaign(client, world):
    a, b, ca, cb = world
    r = client.post("/notas/nova", data={"title": "T", "content": "C", "category": "outros", "character_id": cb.id, "player_id": 0})
    assert r.status_code == 200 and Note.query.count() == 0   # cb não está entre as opções válidas


def test_note_validation_and_filters_by_campaign(client, world, db):
    a, b, ca, cb = world
    assert "Campo obrigatório." in client.post("/notas/nova", data={"title": "", "content": "", "category": "outros"}).get_data(as_text=True)
    db.session.add_all([Note(title="Nota A", content="x", campaign_id=a.id), Note(title="Nota B", content="x", campaign_id=b.id)])
    db.session.commit()
    html = client.get("/notas/").get_data(as_text=True)
    assert "Nota A" in html and "Nota B" not in html
    assert "Nota B" in client.get("/notas/?campanha=todas").get_data(as_text=True)


# ---------------------------------------------------------------- sessões

def _session_data(**kw):
    data = {"number": 1, "title": "Chegada", "date": "2030-05-01", "status": "agendada", "summary": "", "pending": "", "master_notes": ""}
    data.update(kw)
    return data


def test_session_create_with_relations_and_events(client, world, db):
    a, b, ca, cb = world
    npc = NPC(name="Sábio", campaign_id=a.id); q = Quest(title="Q", campaign_id=a.id)
    db.session.add_all([npc, q]); db.session.commit()
    r = client.post("/sessoes/nova", data=_session_data(participants=[ca.id], npcs=[npc.id], quests=[q.id], summary="Tudo começou"))
    assert r.status_code == 302
    s = GameSession.query.one()
    assert [c.id for c in s.participants] == [ca.id] and [n.id for n in s.npcs] == [npc.id] and [x.id for x in s.quests] == [q.id]
    r = client.post(f"/sessoes/{s.id}/acontecimentos", data={"description": "Aria encontrou a espada", "character_id": ca.id})
    assert r.status_code == 302
    ev = SessionEvent.query.one()
    assert ev.character_id == ca.id and ev.campaign_id == a.id
    assert "espada" in client.get(f"/sessoes/{s.id}").get_data(as_text=True)
    rows = lambda url: client.get(url).get_data(as_text=True).count("card session-row")
    assert rows("/sessoes/?q=espada") == 1   # busca em acontecimentos
    assert rows("/sessoes/?q=dragao") == 0
    assert client.get("/sessoes/linha-do-tempo").status_code == 200


def test_session_number_unique_per_campaign(client, world):
    a, b, *_ = world
    client.post("/sessoes/nova", data=_session_data())
    r = client.post("/sessoes/nova", data=_session_data(title="Outra"))
    assert "Já existe uma sessão com este número" in r.get_data(as_text=True)
    assert GameSession.query.filter_by(campaign_id=a.id).count() == 1
    client.post("/campanhas/selecionar", data={"campaign_id": b.id})
    client.post("/sessoes/nova", data=_session_data())     # mesmo número em outra campanha é permitido
    assert GameSession.query.count() == 2


def test_session_rejects_foreign_campaign_participant(client, world):
    a, b, ca, cb = world
    r = client.post("/sessoes/nova", data=_session_data(participants=[cb.id]))
    assert r.status_code == 200 and GameSession.query.count() == 0


def test_session_service_level_isolation(world, db):
    from app.services.integrity import CampaignMismatchError, load_in_campaign
    from app.models import Character
    a, b, ca, cb = world
    with pytest.raises(CampaignMismatchError):
        load_in_campaign(Character, [cb.id], a.id, "personagens")
    with pytest.raises(CampaignMismatchError):
        load_in_campaign(Character, [99999], a.id, "personagens")


def test_session_filters_by_date_and_status(client, world, db):
    a, *_ = world
    db.session.add_all([
        GameSession(campaign_id=a.id, number=1, title="Antiga", date=date(2020, 1, 1), status="realizada"),
        GameSession(campaign_id=a.id, number=2, title="Futura", date=date(2999, 1, 1), status="agendada"),
    ])
    db.session.commit()
    import re
    titles = lambda url: re.findall(r"session-row__main.*?<strong>(.*?)</strong>", client.get(url).get_data(as_text=True), re.S)
    assert titles("/sessoes/?de=2025-01-01") == ["Futura"]
    assert titles("/sessoes/?ate=2021-01-01") == ["Antiga"]
    assert titles("/sessoes/?status=realizada") == ["Antiga"]


def test_session_edit_and_delete(client, world, db):
    client.post("/sessoes/nova", data=_session_data())
    s = GameSession.query.one()
    client.post(f"/sessoes/{s.id}/editar", data=_session_data(title="Renomeada", status="realizada"))
    db.session.refresh(s)
    assert (s.title, s.status) == ("Renomeada", "realizada")
    client.post(f"/sessoes/{s.id}/excluir")
    assert GameSession.query.count() == 0


# ---------------------------------------------------------------- NPCs

def test_npc_crud_and_relationships(client, world, db):
    a, b, ca, cb = world
    r = client.post("/npcs/novo", data={"name": "Mago Velho", "status": "ativo", "secrets": "É imortal"})
    assert r.status_code == 302
    npc = NPC.query.one()
    assert npc.campaign_id == a.id
    client.post(f"/npcs/{npc.id}/editar", data={"name": "Mago Ancião", "status": "desaparecido"})
    db.session.refresh(npc)
    assert (npc.name, npc.status) == ("Mago Ancião", "desaparecido")
    client.post(f"/npcs/{npc.id}/relacoes", data={"character_id": ca.id, "kind": "alianca", "description": "Salvou sua vida"})
    assert CharacterNPCRelationship.query.count() == 1
    client.post(f"/npcs/{npc.id}/relacoes", data={"character_id": ca.id, "kind": "alianca"})   # duplicada
    assert CharacterNPCRelationship.query.count() == 1
    client.post(f"/npcs/{npc.id}/relacoes", data={"character_id": cb.id, "kind": "rivalidade"})  # outra campanha
    assert CharacterNPCRelationship.query.count() == 1
    assert "Mago Ancião" in client.get("/npcs/?q=anci").get_data(as_text=True)
    assert "Mago Ancião" not in client.get("/npcs/?status=ativo").get_data(as_text=True)
    assert client.get(f"/npcs/{npc.id}").status_code == 200


def test_npc_requires_name(client, world):
    assert "Campo obrigatório." in client.post("/npcs/novo", data={"name": "", "status": "ativo"}).get_data(as_text=True)


# ---------------------------------------------------------------- missões

def test_quest_lifecycle(client, world, db):
    a, b, ca, cb = world
    npc = NPC(name="Rei", campaign_id=a.id); db.session.add(npc); db.session.commit()
    r = client.post("/missoes/nova", data={"title": "Resgate", "status": "planejada", "npc_id": npc.id, "characters": [ca.id],
                                           "rewards": "100 moedas", "deadline": "2030-01-01"})
    assert r.status_code == 302
    q = Quest.query.one()
    assert q.npc_id == npc.id and [c.id for c in q.characters] == [ca.id]
    client.post(f"/missoes/{q.id}/status", data={"status": "em_andamento"})
    client.post(f"/missoes/{q.id}/editar", data={"title": "Resgate!", "status": "concluida", "npc_id": 0, "characters": []})
    db.session.refresh(q)
    assert q.status == "concluida" and q.npc_id is None and q.characters == []
    hist = [(h.old_status, h.new_status) for h in sorted(q.status_history, key=lambda h: h.id)]
    assert hist == [(None, "planejada"), ("planejada", "em_andamento"), ("em_andamento", "concluida")]
    assert "Resgate!" in client.get("/missoes/?status=concluida").get_data(as_text=True)
    assert "Resgate!" not in client.get("/missoes/?status=planejada").get_data(as_text=True)


def test_quest_objectives_toggle(client, world, db):
    client.post("/missoes/nova", data={"title": "Q", "status": "planejada"})
    q = Quest.query.one()
    client.post(f"/missoes/{q.id}/objetivos", data={"description": "Achar o mapa"})
    client.post(f"/missoes/{q.id}/objetivos", data={"description": ""})        # inválido
    o = QuestObjective.query.one()
    assert not o.done
    client.post(f"/missoes/{q.id}/objetivos/{o.id}/alternar")
    db.session.refresh(o)
    assert o.done
    client.post(f"/missoes/{q.id}/objetivos/{o.id}/excluir")
    assert QuestObjective.query.count() == 0


def test_quest_filter_by_character_and_foreign_character_rejected(client, world, db):
    a, b, ca, cb = world
    client.post("/missoes/nova", data={"title": "Com Aria", "status": "planejada", "characters": [ca.id]})
    client.post("/missoes/nova", data={"title": "Sem ninguém", "status": "planejada"})
    import re
    titles = re.findall(r"<h3><a [^>]*>(.*?)</a></h3>", client.get(f"/missoes/?personagem={ca.id}").get_data(as_text=True))
    assert titles == ["Com Aria"]
    r = client.post("/missoes/nova", data={"title": "Invasora", "status": "planejada", "characters": [cb.id]})
    assert r.status_code == 200 and Quest.query.filter_by(title="Invasora").count() == 0


# ---------------------------------------------------------------- itens

def test_item_with_holder_and_validation(client, world, db):
    a, b, ca, cb = world
    r = client.post("/itens/novo", data={"name": "Moedas de ouro", "category": "moeda", "character_id": ca.id, "quantity": 50, "origin": "Missão Resgate"})
    assert r.status_code == 302
    item = Item.query.one()
    assert item.total_quantity == 50 and CharacterItem.query.one().character_id == ca.id
    r = client.post("/itens/novo", data={"name": "Espada", "category": "equipamento", "character_id": ca.id, "quantity": -2})
    assert "maior que zero" in r.get_data(as_text=True) and Item.query.count() == 1
    r = client.post("/itens/novo", data={"name": "Estranho", "category": "equipamento", "character_id": cb.id, "quantity": 1})
    assert Item.query.count() == 1                      # personagem de outra campanha não é aceito
    client.post("/itens/novo", data={"name": "Tesouro do grupo", "category": "tesouro", "quantity": 1})
    assert Item.query.count() == 2
    assert "Moedas de ouro" in client.get(f"/itens/?personagem={ca.id}").get_data(as_text=True)
    assert "Tesouro do grupo" not in client.get(f"/itens/?personagem={ca.id}").get_data(as_text=True)


def test_item_edit_holdings_delete(client, world, db):
    a, b, ca, cb = world
    client.post("/itens/novo", data={"name": "Poção", "category": "consumivel", "quantity": 1})
    item = Item.query.one()
    client.post(f"/itens/{item.id}/editar", data={"name": "Poção grande", "category": "consumivel"})
    db.session.refresh(item)
    assert item.name == "Poção grande"
    client.post(f"/itens/{item.id}/posses", data={"character_id": ca.id, "quantity": 3})
    client.post(f"/itens/{item.id}/posses", data={"character_id": cb.id, "quantity": 3})   # outra campanha
    assert CharacterItem.query.count() == 1
    client.post(f"/itens/{item.id}/excluir")
    assert Item.query.count() == 0 and CharacterItem.query.count() == 0


# ---------------------------------------------------------------- isolamento geral

def test_lists_are_isolated_between_campaigns(client, world, db, select_campaign):
    a, b, ca, cb = world
    db.session.add_all([NPC(name="NPC-A", campaign_id=a.id), NPC(name="NPC-B", campaign_id=b.id),
                        Quest(title="Quest-A", campaign_id=a.id), Quest(title="Quest-B", campaign_id=b.id),
                        Item(name="Item-A", campaign_id=a.id), Item(name="Item-B", campaign_id=b.id)])
    db.session.commit()
    for url, mine, other in [("/npcs/", "NPC-A", "NPC-B"), ("/missoes/", "Quest-A", "Quest-B"), ("/itens/", "Item-A", "Item-B"),
                             ("/personagens/", "Aria", "Brutus"), ("/xp/?status=todos", "Aria", "Brutus")]:
        html = client.get(url).get_data(as_text=True)
        assert mine in html and f">{other}<" not in html and f"{other}</" not in html, url
    select_campaign(b)
    assert "Brutus" in client.get("/personagens/").get_data(as_text=True)
    assert "NPC-B" in client.get("/npcs/").get_data(as_text=True)


def test_xp_panel_only_selected_campaign(client, world):
    a, b, ca, cb = world
    html = client.get("/xp/?status=todos").get_data(as_text=True)
    assert f'name="character_ids" value="{ca.id}"' in html and f'name="character_ids" value="{cb.id}"' not in html


def test_user_text_is_escaped(client, world, db):
    a, *_ = world
    db.session.add(Note(title="<script>alert(1)</script>", content="<img src=x onerror=alert(1)>", campaign_id=a.id))
    db.session.commit()
    html = client.get("/notas/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html


# ---------------------------------------------------------------- uploads

def png_bytes(size=(64, 48), color=(120, 80, 200)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_portrait_upload_validation_and_storage(client, world, app, db):
    from app.models import Character, FileAsset
    a, b, ca, cb = world
    url = f"/personagens/{ca.id}/editar"
    base = {"name": "Aria", "player_id": ca.player_id, "status": "ativo"}
    post = lambda data, name: client.post(url, data={**base, "portrait": (io.BytesIO(data), name)}, content_type="multipart/form-data")
    assert "Formato não permitido" in post(b"<svg onload=alert(1)>", "x.svg").get_data(as_text=True)
    assert "não corresponde a uma imagem válida" in post(b"not an image at all", "x.png").get_data(as_text=True)
    assert "não corresponde a uma imagem válida" in post(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "x.png").get_data(as_text=True)
    assert "muito grande" in post(png_bytes() + b"0" * (4 * 1024 * 1024), "x.png").get_data(as_text=True)
    ok = post(png_bytes(), "../../etc/evil.png")
    assert ok.status_code == 302
    asset_id = db.session.get(Character, ca.id).portrait
    assert len(asset_id) == 32 and FileAsset.query.count() == 1
    r = client.get(f"/media/{asset_id}")
    assert r.status_code == 200 and r.mimetype == "image/webp" and r.data[:4] == b"RIFF"
    assert client.get("/media/..%2f..%2fconfig.py").status_code == 404
    assert client.get("/media/config.py").status_code == 404
    # substituir remove o arquivo antigo
    post(png_bytes(color=(1, 2, 3)), "novo.png")
    assert db.session.get(FileAsset, asset_id) is None and FileAsset.query.count() == 1


def test_image_is_downscaled_and_exif_free(client, world, db):
    from PIL import Image
    from app.models import FileAsset
    a, b, ca, cb = world
    big = io.BytesIO(); Image.new("RGB", (3000, 2000), (9, 9, 9)).save(big, "JPEG")
    client.post(f"/personagens/{ca.id}/editar", data={"name": "Aria", "player_id": ca.player_id, "status": "ativo",
                "portrait": (io.BytesIO(big.getvalue()), "grande.jpg")}, content_type="multipart/form-data")
    img = Image.open(io.BytesIO(FileAsset.query.one().data))
    assert max(img.size) <= 800 and not img.getexif()


def test_image_quota_enforced(client, world, app, db):
    from app.models import FileAsset
    a, b, ca, cb = world
    app.config["USER_IMAGE_QUOTA_BYTES"] = 10
    r = client.post(f"/personagens/{ca.id}/editar", data={"name": "Aria", "player_id": ca.player_id, "status": "ativo",
                    "portrait": (io.BytesIO(png_bytes()), "a.png")}, content_type="multipart/form-data")
    assert r.status_code == 200 and "Limite de armazenamento" in r.get_data(as_text=True) and FileAsset.query.count() == 0

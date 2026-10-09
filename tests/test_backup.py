"""Backup e restauração por usuário."""
import io
import json
import zipfile

import pytest

from app.models import (Campaign, Character, CharacterItem, CharacterNPCRelationship, ExperienceHistory, FileAsset,
                        GameSession, Item, NPC, Note, Player, Quest, QuestObjective, SessionEvent)
from app.services import backup
from app.services.backup import BackupError
from app.services.campaigns import enroll_player
from tests.test_modules import png_bytes


@pytest.fixture()
def populated(db, user, make_campaign, make_character):
    """Dados completos e interligados do usuário A."""
    from datetime import date
    c = make_campaign("Crônicas", system="D&D", settings={"Marco": "3 sessões"})
    hero = make_character(c, "Lyra", xp_percent=40, extra={"Força": "14"})
    other = make_character(c, "Thorin")
    from app.services import xp
    xp.apply_delta(hero, 15, "teste")
    npc = NPC(name="Orin", campaign_id=c.id)
    quest = Quest(title="Selo", campaign_id=c.id, status="em_andamento")
    item = Item(name="Espada", campaign_id=c.id)
    db.session.add_all([npc, quest, item]); db.session.flush()
    quest.characters.append(hero)
    quest.objectives.append(QuestObjective(description="achar", done=True))
    s = GameSession(campaign_id=c.id, number=1, title="Taverna", date=date(2026, 1, 2), status="realizada", summary="oi")
    s.participants.append(hero); s.npcs.append(npc); s.quests.append(quest)
    db.session.add_all([s, CharacterNPCRelationship(character_id=hero.id, npc_id=npc.id, kind="alianca"),
                        CharacterItem(item_id=item.id, character_id=hero.id, quantity=3, quest_id=quest.id),
                        Note(title="Nota", content="conteúdo", campaign_id=c.id, character_id=hero.id, player_id=hero.player_id, important=True)])
    db.session.flush()
    db.session.add(SessionEvent(session_id=s.id, campaign_id=c.id, character_id=hero.id, description="evento"))
    asset = FileAsset(id="c" * 32, owner_id=user.id, content_type="image/webp", size=len(png_bytes()), data=png_bytes())
    db.session.add(asset); db.session.flush()
    hero.portrait = asset.id; c.cover_image = asset.id
    db.session.commit()
    return c


def fingerprint(owner_id):
    """Resumo comparável (independente dos ids, que mudam na restauração)."""
    camps = Campaign.query.filter_by(owner_id=owner_id).all()
    out = []
    for c in camps:
        chars = {x.name: (x.xp_percent, x.xp_cycle, x.extra, bool(x.portrait), x.player.display_name) for x in c.characters}
        out.append((c.name, c.system, c.settings, bool(c.cover_image), chars,
                    [(n.title, n.important, n.character.name if n.character else None) for n in c.notes_list],
                    [(s.number, [p.name for p in s.participants], [n.name for n in s.npcs], [q.title for q in s.quests],
                      [(e.description, e.character.name) for e in s.events]) for s in c.sessions],
                    [(q.title, [x.name for x in q.characters], [(o.description, o.done) for o in q.objectives]) for q in c.quests],
                    [(r.character.name, r.npc.name, r.kind) for n in c.npcs for r in n.relationships],
                    [(i.name, [(h.character.name, h.quantity, h.quest.title if h.quest else None) for h in i.holdings]) for i in c.items],
                    sorted((h.previous_percent, h.new_percent, h.reason) for x in c.characters for h in x.xp_history)))
    return out


def test_roundtrip_restores_everything(user, populated, db):
    name, payload = backup.create_backup(user)
    assert name.endswith(".zip")
    before = fingerprint(user.id)
    # estraga os dados depois do backup
    Campaign.query.filter_by(owner_id=user.id).first().name = "ALTERADA"
    db.session.add(Campaign(name="Nova depois do backup", status="ativa", owner_id=user.id)); db.session.commit()
    info = backup.restore_backup(user, io.BytesIO(payload))
    assert info["images"] == 1 and info["rows"] > 10
    db.session.expire_all()
    assert fingerprint(user.id) == before
    assert FileAsset.query.filter_by(owner_id=user.id).count() == 1
    assert ExperienceHistory.query.count() == 1
    hero = Character.query.filter_by(name="Lyra").one()
    assert hero.portrait and db.session.get(FileAsset, hero.portrait).owner_id == user.id


def test_backup_contains_only_own_data_and_restore_does_not_touch_others(user, other_user, populated, db, make_campaign, make_character):
    theirs = make_campaign("Do-B", owner=other_user)
    make_character(theirs, "Heroi-do-B")
    db.session.add(FileAsset(id="d" * 32, owner_id=other_user.id, content_type="image/webp", size=1, data=b"x")); db.session.commit()
    their_before = fingerprint(other_user.id)
    _, payload = backup.create_backup(user)
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        blob = zf.read("data.json").decode() + "".join(zf.namelist())
    assert "Do-B" not in blob and "Heroi-do-B" not in blob and "d" * 32 not in blob and other_user.email not in blob
    backup.restore_backup(user, io.BytesIO(payload))
    backup.restore_backup(user, io.BytesIO(payload))             # restaurar duas vezes é seguro
    db.session.expire_all()
    assert fingerprint(other_user.id) == their_before
    assert Campaign.query.count() == 2 and FileAsset.query.filter_by(owner_id=other_user.id).count() == 1
    assert Player.query.filter_by(owner_id=other_user.id).count() == 1


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n, d in entries.items():
            zf.writestr(n, d)
    return buf.getvalue()


MANIFEST = json.dumps({"app": "mesa-do-mestre", "format": 2})


def _data(tables=None, assets=None):
    return json.dumps({"tables": tables or {}, "assets": assets or []})


BAD = {
    "não é zip": b"isso nao e um zip",
    "sem manifesto": _zip({"data.json": _data()}),
    "app diferente": _zip({"manifest.json": json.dumps({"app": "outro", "format": 2}), "data.json": _data()}),
    "formato antigo": _zip({"manifest.json": json.dumps({"app": "mesa-do-mestre", "format": 1}), "data.json": _data()}),
    "path traversal": _zip({"manifest.json": MANIFEST, "data.json": _data(), "../evil.txt": "x"}),
    "entrada solta": _zip({"manifest.json": MANIFEST, "data.json": _data(), "extra.bin": "x"}),
    "json quebrado": _zip({"manifest.json": MANIFEST, "data.json": "{nao e json"}),
    "tabela desconhecida": _zip({"manifest.json": MANIFEST, "data.json": _data({"users": [{"id": 1}]})}),
    "coluna desconhecida": _zip({"manifest.json": MANIFEST, "data.json": _data({"campaigns": [{"id": 1, "name": "x", "status": "ativa", "is_admin": True}]})}),
    "owner forjado": _zip({"manifest.json": MANIFEST, "data.json": _data({"campaigns": [{"id": 1, "name": "x", "status": "ativa", "owner_id": 999}]})}),
    "fk inexistente": _zip({"manifest.json": MANIFEST, "data.json": _data({"characters": [{"id": 1, "name": "x", "campaign_id": 77, "player_id": 88, "status": "ativo"}]})}),
    "imagem ausente": _zip({"manifest.json": MANIFEST, "data.json": _data(assets=[{"id": "e" * 32, "content_type": "image/webp"}])}),
    "imagem falsa": _zip({"manifest.json": MANIFEST, "data.json": _data(assets=[{"id": "e" * 32, "content_type": "image/webp"}]), "files/" + "e" * 32: "<svg/>"}),
    "id de imagem malicioso": _zip({"manifest.json": MANIFEST, "data.json": _data(), "files/../../x": "x"}),
    "violação de CHECK": _zip({"manifest.json": MANIFEST, "data.json": _data({"campaigns": [{"id": 1, "name": "x", "status": "INVALIDO"}]})}),
    "valor de data inválido": _zip({"manifest.json": MANIFEST, "data.json": _data({"campaigns": [{"id": 1, "name": "x", "status": "ativa", "start_date": "ontem"}]})}),
}


@pytest.mark.parametrize("label", list(BAD))
def test_invalid_backups_are_rejected_and_nothing_changes(user, populated, db, label):
    before = fingerprint(user.id)
    with pytest.raises(BackupError):
        backup.restore_backup(user, io.BytesIO(BAD[label]))
    db.session.expire_all()
    assert fingerprint(user.id) == before


def test_failure_in_the_middle_rolls_back_everything(user, populated, db):
    """Primeira tabela válida, segunda inválida: os dados antigos não podem ter sido apagados."""
    payload = _zip({"manifest.json": MANIFEST, "data.json": _data({
        "campaigns": [{"id": 1, "name": "Nova", "status": "ativa"}],
        "players": [{"id": 1, "display_name": "P", "status": "ativo"}],
        "characters": [{"id": 1, "name": "C", "campaign_id": 1, "player_id": 1, "status": "ativo", "xp_percent": 500}],
    })})
    before = fingerprint(user.id)
    with pytest.raises(BackupError):
        backup.restore_backup(user, io.BytesIO(payload))
    db.session.expire_all()
    assert fingerprint(user.id) == before and Campaign.query.filter_by(name="Nova").count() == 0


def test_restore_route_download_route_and_confirmation(client, user, populated, db):
    r = client.post("/backup/baixar")
    assert r.status_code == 200 and r.mimetype == "application/zip" and "attachment" in r.headers["Content-Disposition"]
    payload = r.data
    r = client.post("/backup/restaurar", data={"backup_file": (io.BytesIO(payload), "b.zip")}, content_type="multipart/form-data", follow_redirects=True)
    assert "Marque a confirmação" in r.get_data(as_text=True)
    r = client.post("/backup/restaurar", data={"backup_file": (io.BytesIO(b"lixo"), "b.zip"), "confirm": "y"}, content_type="multipart/form-data", follow_redirects=True)
    assert "nada foi alterado" in r.get_data(as_text=True)
    r = client.post("/backup/restaurar", data={"backup_file": (io.BytesIO(payload), "b.zip"), "confirm": "y"}, content_type="multipart/form-data", follow_redirects=True)
    assert "Backup restaurado" in r.get_data(as_text=True)
    r = client.post("/backup/restaurar", data={"backup_file": (io.BytesIO(payload), "b.txt"), "confirm": "y"}, content_type="multipart/form-data", follow_redirects=True)
    assert "Envie um arquivo .zip" in r.get_data(as_text=True)


def test_anonymous_cannot_download_backup(anon_client, populated):
    r = anon_client.post("/backup/baixar")
    assert r.status_code == 302 and "/login" in r.headers["Location"]

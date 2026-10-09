"""Inicialização, banco, campanhas, jogadores, personagens, formulários e 404."""
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Campaign, Character, CampaignPlayer, Player


def test_app_starts_and_empty_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Criar primeira campanha" in r.get_data(as_text=True)


def test_database_connection_and_foreign_keys(db):
    assert db.session.execute(text("select 1")).scalar() == 1
    assert db.session.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]


@pytest.mark.parametrize("path", ["/", "/campanhas/", "/jogadores/", "/backup/"])
def test_pages_render_without_campaign(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/personagens/", "/xp/", "/notas/", "/sessoes/", "/npcs/", "/missoes/", "/itens/"])
def test_campaign_pages_redirect_without_campaign(client, path):
    assert client.get(path).status_code == 302


# ---------------------------------------------------------------- campanhas

def test_create_and_edit_campaign(client, db):
    r = client.post("/campanhas/nova", data={
        "name": "Reino Sombrio", "status": "ativa", "system": "D&D 5e", "settings_text": "Marco: 3 sessões",
    }, follow_redirects=True)
    assert r.status_code == 200
    c = Campaign.query.one()
    assert c.name == "Reino Sombrio" and c.settings == {"Marco": "3 sessões"}
    r = client.post(f"/campanhas/{c.id}/editar", data={"name": "Reino Renomeado", "status": "pausada"})
    assert r.status_code == 302
    db.session.refresh(c)
    assert c.name == "Reino Renomeado" and c.status == "pausada"


def test_campaign_form_validation_errors_near_fields(client):
    r = client.post("/campanhas/nova", data={"name": "", "status": "ativa"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Campo obrigatório." in html
    assert Campaign.query.count() == 0


def test_invalid_kv_settings_rejected(client):
    r = client.post("/campanhas/nova", data={"name": "X", "status": "ativa", "settings_text": "sem dois pontos"})
    assert "Linha inválida" in r.get_data(as_text=True)
    assert Campaign.query.count() == 0


def test_close_campaign_preserves_records(client, make_campaign, make_character, db):
    c = make_campaign()
    ch = make_character(c)
    client.post(f"/campanhas/{c.id}/status", data={"status": "encerrada"})
    db.session.refresh(c)
    assert c.status == "encerrada" and db.session.get(Character, ch.id) is not None
    assert client.get(f"/campanhas/{c.id}").status_code == 200


def test_delete_campaign_requires_exact_name(client, make_campaign, make_character, db):
    c = make_campaign("Apagar")
    make_character(c)
    client.post(f"/campanhas/{c.id}/excluir", data={"confirm_name": "errado"})
    assert Campaign.query.count() == 1
    client.post(f"/campanhas/{c.id}/excluir", data={"confirm_name": "Apagar"})
    assert Campaign.query.count() == 0 and Character.query.count() == 0
    assert Player.query.count() == 1  # jogadores sobrevivem à exclusão da campanha


def test_switch_campaign(client, make_campaign):
    a, b = make_campaign("A"), make_campaign("B")
    client.post("/campanhas/selecionar", data={"campaign_id": a.id})
    assert "<h1>A" in client.get("/").get_data(as_text=True).replace("\n", "")
    client.post("/campanhas/selecionar", data={"campaign_id": b.id})
    assert "<h1>B" in client.get("/").get_data(as_text=True).replace("\n", "")


def test_select_open_redirect_blocked(client, make_campaign):
    c = make_campaign()
    r = client.post("/campanhas/selecionar", data={"campaign_id": c.id, "next": "//evil.example/x"})
    assert r.headers["Location"].endswith("/")
    assert "evil" not in r.headers["Location"]


# ---------------------------------------------------------------- jogadores

def test_create_edit_player_and_search(client, make_player):
    r = client.post("/jogadores/novo", data={"display_name": "Bruno", "status": "ativo", "email": "b@x.com"})
    assert r.status_code == 302
    p = Player.query.one()
    client.post(f"/jogadores/{p.id}/editar", data={"display_name": "Bruno S.", "status": "inativo"})
    assert Player.query.one().display_name == "Bruno S."
    make_player("Carla")
    assert "Bruno S." in client.get("/jogadores/?q=bruno").get_data(as_text=True)
    assert "Carla" not in client.get("/jogadores/?q=bruno").get_data(as_text=True)
    assert "Bruno S." not in client.get("/jogadores/?status=ativo").get_data(as_text=True)


def test_player_invalid_email(client):
    r = client.post("/jogadores/novo", data={"display_name": "X", "status": "ativo", "email": "nao-e-email"})
    assert "E-mail inválido." in r.get_data(as_text=True) and Player.query.count() == 0


def test_player_search_escapes_wildcards(client, make_player):
    make_player("Maria")
    assert "Maria" not in client.get("/jogadores/?q=%25").get_data(as_text=True)


def test_player_with_characters_cannot_be_deleted(client, make_campaign, make_character):
    c = make_campaign()
    ch = make_character(c)
    client.post(f"/jogadores/{ch.player_id}/excluir")
    assert Player.query.count() == 1


def test_same_player_in_two_campaigns(client, make_campaign, make_character, make_player, db):
    a, b = make_campaign("A"), make_campaign("B")
    p = make_player("Dani")
    make_character(a, "Elfa", player=p)
    make_character(b, "Anão", player=p)
    assert CampaignPlayer.query.filter_by(player_id=p.id).count() == 2
    assert [x.name for x in Character.query.filter_by(campaign_id=a.id)] == ["Elfa"]


# ---------------------------------------------------------------- personagens

def test_create_character_enrolls_player(client, make_campaign, make_player, select_campaign):
    c, p = make_campaign(), make_player()
    select_campaign(c)
    r = client.post("/personagens/novo", data={
        "name": "Thorin", "player_id": p.id, "status": "ativo", "level": "3", "extra_text": "Força: 14",
    })
    assert r.status_code == 302
    ch = Character.query.one()
    assert ch.campaign_id == c.id and ch.xp_percent == 0 and ch.extra == {"Força": "14"}
    assert CampaignPlayer.query.filter_by(campaign_id=c.id, player_id=p.id).one().status == "ativo"


def test_character_requires_player_and_name(client, make_campaign, make_player, select_campaign):
    c = make_campaign(); make_player()
    select_campaign(c)
    r = client.post("/personagens/novo", data={"name": "", "player_id": 0, "status": "ativo"})
    html = r.get_data(as_text=True)
    assert "Campo obrigatório." in html and "Selecione o jogador responsável." in html
    assert Character.query.count() == 0


def test_character_level_optional_and_bounded(client, make_campaign, make_player, select_campaign):
    c, p = make_campaign(), make_player()
    select_campaign(c)
    r = client.post("/personagens/novo", data={"name": "A", "player_id": p.id, "status": "ativo", "level": "5000"})
    assert "entre 0 e 999" in r.get_data(as_text=True)
    client.post("/personagens/novo", data={"name": "A", "player_id": p.id, "status": "ativo"})
    assert Character.query.one().level is None


def test_edit_character_does_not_touch_others(client, make_campaign, make_character, db):
    c = make_campaign()
    a, b = make_character(c, "A"), make_character(c, "B")
    client.post(f"/personagens/{a.id}/editar", data={"name": "A2", "player_id": a.player_id, "status": "aposentado"})
    db.session.refresh(a); db.session.refresh(b)
    assert (a.name, a.status) == ("A2", "aposentado") and (b.name, b.status) == ("B", "ativo")


def test_status_change_keeps_xp_history(client, make_campaign, make_character, db):
    from app.services import xp
    ch = make_character(make_campaign())
    xp.apply_delta(ch, 20)
    client.post(f"/personagens/{ch.id}/status", data={"status": "morto"})
    db.session.refresh(ch)
    assert ch.status == "morto" and len(ch.xp_history) == 1


def test_missing_records_return_404(client):
    for path in ["/personagens/999", "/jogadores/999", "/campanhas/999", "/sessoes/999", "/npcs/999",
                 "/missoes/999", "/itens/999", "/xp/personagens/999/historico", "/personagens/999/editar"]:
        assert client.get(path).status_code == 404, path
    r = client.post("/xp/api/personagens/999", json={"action": "add", "value": 5})
    assert r.status_code == 404 and r.is_json


def test_character_filters_sort(client, make_campaign, make_character, select_campaign):
    c = make_campaign()
    select_campaign(c)
    make_character(c, "Zed", xp_percent=80); make_character(c, "Abel", xp_percent=10, status="morto")
    import re
    names = lambda url: re.findall(r"<h3>(.*?)</h3>", client.get(url).get_data(as_text=True))
    assert names("/personagens/?ordem=xp") == ["Zed", "Abel"]
    assert names("/personagens/?ordem=nome") == ["Abel", "Zed"]
    assert names("/personagens/?status=morto") == ["Abel"]
    assert names("/personagens/?q=ze") == ["Zed"]


def test_db_constraints_enforced(db, make_campaign, make_character):
    ch = make_character(make_campaign())
    ch.xp_percent = 101
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_dashboard_shows_real_data(client, make_campaign, make_character, select_campaign, db):
    from app.models import GameSession
    c = make_campaign("Minha Mesa")
    select_campaign(c)
    make_character(c, "Lyra", xp_percent=42)
    db.session.add(GameSession(campaign_id=c.id, number=1, title="Abertura", date=date(2999, 1, 1), status="agendada"))
    db.session.commit()
    html = client.get("/").get_data(as_text=True)
    assert "Minha Mesa" in html and "Lyra" in html and "42%" in html and "Abertura" in html

"""Barra de XP: limites, alterações individuais/coletivas, histórico e novo ciclo."""
import pytest

from app.models import ExperienceHistory
from app.services import xp
from app.services.xp import XPError


@pytest.fixture()
def hero(make_campaign, make_character):
    return make_character(make_campaign(), "Herói")


def test_increase_and_decrease(hero):
    assert xp.apply_delta(hero, 10).new == 10
    assert xp.apply_delta(hero, -5).new == 5
    assert hero.xp_percent == 5


@pytest.mark.parametrize("start,delta,expected", [(95, 10, 100), (3, -10, 0), (0, -5, 0), (100, 5, 100)])
def test_limits_clamp(hero, db, start, delta, expected):
    hero.xp_percent = start
    db.session.commit()
    assert xp.apply_delta(hero, delta).new == expected
    assert 0 <= hero.xp_percent <= 100


@pytest.mark.parametrize("bad", [-1, 101, 1000])
def test_set_out_of_range_rejected(hero, bad):
    with pytest.raises(XPError):
        xp.set_percent(hero, bad)
    assert hero.xp_percent == 0


@pytest.mark.parametrize("bad", ["abc", "", None, 5.5, True, "1e2"])
def test_non_integer_rejected(hero, bad):
    with pytest.raises(XPError):
        xp.set_percent(hero, bad)
    with pytest.raises(XPError):
        xp.apply_delta(hero, bad)


def test_zero_or_huge_delta_rejected(hero):
    for bad in (0, 101, -101):
        with pytest.raises(XPError):
            xp.apply_delta(hero, bad)


def test_set_reset_complete(hero):
    assert xp.set_percent(hero, "37").new == 37
    assert xp.complete(hero).new == 100
    assert xp.reset(hero).new == 0


def test_history_records_every_change(hero):
    xp.apply_delta(hero, 30, "fim da sessão")
    xp.set_percent(hero, 10)
    rows = ExperienceHistory.query.order_by(ExperienceHistory.id).all()
    assert len(rows) == 2
    first = rows[0]
    assert (first.previous_percent, first.new_percent, first.delta) == (0, 30, 30)
    assert first.reason == "fim da sessão" and first.origin == "individual"
    assert first.campaign_id == hero.campaign_id and first.created_at is not None
    assert (rows[1].previous_percent, rows[1].new_percent, rows[1].delta) == (30, 10, -20)


def test_clamped_change_records_requested_and_actual(hero, db):
    hero.xp_percent = 95; db.session.commit()
    r = xp.apply_delta(hero, 20)
    h = ExperienceHistory.query.one()
    assert (h.delta, h.requested_delta) == (5, 20) and r.clamped


def test_no_change_writes_no_history(hero):
    r = xp.apply_delta(hero, -10)
    assert not r.changed and ExperienceHistory.query.count() == 0


def test_reason_too_long(hero):
    with pytest.raises(XPError):
        xp.apply_delta(hero, 5, "x" * 301)


def test_independent_characters(make_campaign, make_character):
    c = make_campaign()
    a, b = make_character(c, "A"), make_character(c, "B")
    xp.apply_delta(a, 40)
    assert (a.xp_percent, b.xp_percent) == (40, 0)


def test_new_cycle_only_at_100_and_keeps_history(hero):
    with pytest.raises(XPError):
        xp.start_new_cycle(hero)
    xp.complete(hero)
    assert hero.level is None and hero.xp_percent == 100   # nível nunca sobe sozinho
    xp.start_new_cycle(hero)
    assert (hero.xp_percent, hero.xp_cycle, hero.level) == (0, 2, None)
    origins = [h.origin for h in ExperienceHistory.query.order_by(ExperienceHistory.id)]
    assert origins == ["individual", "novo_ciclo"]


# ---------------------------------------------------------------- coletiva

def test_bulk_affects_only_selected(make_campaign, make_character):
    c = make_campaign()
    a, b, other = make_character(c, "A"), make_character(c, "B"), make_character(c, "C")
    results = xp.apply_bulk(c.id, [a.id, b.id], 25, "bônus")
    assert [r.new for r in results] == [25, 25]
    assert other.xp_percent == 0
    rows = ExperienceHistory.query.all()
    assert len(rows) == 2 and {r.origin for r in rows} == {"coletiva"}
    assert len({r.batch_id for r in rows}) == 1 and rows[0].batch_id


def test_bulk_respects_each_bar_limit(make_campaign, make_character, db):
    c = make_campaign()
    a, b = make_character(c, "A", xp_percent=95), make_character(c, "B", xp_percent=10)
    xp.apply_bulk(c.id, [a.id, b.id], 20)
    assert (a.xp_percent, b.xp_percent) == (100, 30)
    xp.apply_bulk(c.id, [a.id, b.id], -50)
    assert (a.xp_percent, b.xp_percent) == (50, 0)


def test_bulk_is_atomic_on_error(make_campaign, make_character, monkeypatch, db):
    c = make_campaign()
    a, b = make_character(c, "A"), make_character(c, "B")
    calls = {"n": 0}
    real = xp._record

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("falha simulada")
        return real(*args, **kwargs)

    monkeypatch.setattr(xp, "_record", flaky)
    with pytest.raises(RuntimeError):
        xp.apply_bulk(c.id, [a.id, b.id], 10)
    db.session.rollback()
    db.session.refresh(a); db.session.refresh(b)
    assert (a.xp_percent, b.xp_percent) == (0, 0) and ExperienceHistory.query.count() == 0


def test_bulk_rejects_other_campaign_and_unknown(make_campaign, make_character):
    c1, c2 = make_campaign("1"), make_campaign("2")
    a, foreign = make_character(c1, "A"), make_character(c2, "X")
    with pytest.raises(XPError):
        xp.apply_bulk(c1.id, [a.id, foreign.id], 10)
    with pytest.raises(XPError):
        xp.apply_bulk(c1.id, [a.id, 9999], 10)
    with pytest.raises(XPError):
        xp.apply_bulk(c1.id, [], 10)
    assert a.xp_percent == 0 and foreign.xp_percent == 0


# ---------------------------------------------------------------- HTTP

def test_api_endpoint_returns_persisted_value(client, hero, db):
    r = client.post(f"/xp/api/personagens/{hero.id}", json={"action": "add", "value": 10})
    assert r.get_json()["percent"] == 10
    r = client.post(f"/xp/api/personagens/{hero.id}", json={"action": "set", "value": 100})
    j = r.get_json()
    assert j["percent"] == 100 and j["complete"]
    db.session.refresh(hero)
    assert hero.xp_percent == 100


def test_api_validation_errors(client, hero):
    assert client.post(f"/xp/api/personagens/{hero.id}", json={"action": "set", "value": 150}).status_code == 400
    assert client.post(f"/xp/api/personagens/{hero.id}", json={"action": "set", "value": "x"}).status_code == 400
    assert client.post(f"/xp/api/personagens/{hero.id}", json={"action": "boom"}).status_code == 400
    assert client.post(f"/xp/api/personagens/{hero.id}", data="não é json").status_code == 400
    assert client.post(f"/xp/api/personagens/{hero.id}", json={"action": "new_cycle"}).status_code == 400


def test_bulk_endpoint_and_panel(client, make_campaign, make_character, select_campaign, db):
    c = make_campaign()
    select_campaign(c)
    a, b = make_character(c, "Aria"), make_character(c, "Bela")
    r = client.post("/xp/lote", data={"character_ids": [a.id], "amount": "15", "direction": "up", "reason": "teste"}, follow_redirects=True)
    assert "Aria: 0% → 15%" in r.get_data(as_text=True)
    db.session.refresh(a); db.session.refresh(b)
    assert (a.xp_percent, b.xp_percent) == (15, 0)
    client.post("/xp/lote", data={"character_ids": [a.id], "amount": "50", "direction": "down"})
    db.session.refresh(a)
    assert a.xp_percent == 0
    r = client.post("/xp/lote", data={"amount": "5", "direction": "up"}, follow_redirects=True)
    assert "Selecione ao menos um personagem" in r.get_data(as_text=True)
    assert client.get("/xp/").status_code == 200
    assert client.get(f"/xp/personagens/{a.id}/historico").status_code == 200


def test_character_page_renders_xp_widget(client, hero):
    html = client.get(f"/personagens/{hero.id}").get_data(as_text=True)
    assert 'data-xp-action="add"' in html and 'role="progressbar"' in html

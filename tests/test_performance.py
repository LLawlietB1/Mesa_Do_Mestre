"""Desempenho: orçamento de consultas (sem N+1), cache de estáticos e Server-Timing."""
import re
from datetime import date

import pytest

from app.models import (Campaign, Character, CharacterItem, CharacterNPCRelationship, GameSession, Item, Note, NPC, Player,
                        Quest, QuestObjective, SessionEvent)
from app.services.campaigns import enroll_player


def queries(client, db, url):
    """Número de consultas SQL da requisição (lido do cabeçalho Server-Timing), com a sessão limpa como numa requisição real."""
    db.session.remove()
    r = client.get(url)
    assert r.status_code == 200, url
    return int(re.search(r'desc="(\d+) consultas"', r.headers["Server-Timing"]).group(1))


@pytest.fixture()
def world(db, user, make_campaign):
    c = make_campaign("Perf")
    npc, quest, item = NPC(campaign_id=c.id, name="n"), Quest(campaign_id=c.id, title="q"), Item(campaign_id=c.id, name="i")
    sess = GameSession(campaign_id=c.id, number=1, title="s", date=date.today(), status="agendada")
    db.session.add_all([npc, quest, item, sess]); db.session.commit()
    uid = user.id
    ids = dict(c=c.id, npc=npc.id, quest=quest.id, item=item.id, sess=sess.id)

    def grow(n):
        # a sessão é limpa entre requisições: recarrega os objetos pelos ids (nada de objetos desanexados)
        quest_, item_, npc_ = (db.session.get(Quest, ids["quest"]), db.session.get(Item, ids["item"]), db.session.get(NPC, ids["npc"]))
        for i in range(n):
            p = Player(owner_id=uid, display_name=f"P{i}-{Player.query.count()}", phone="+5511999990000", messaging_consent=True)
            db.session.add(p); db.session.flush()
            enroll_player(ids["c"], p.id)
            ch = Character(name=f"H{p.id}", campaign_id=ids["c"], player_id=p.id); db.session.add(ch); db.session.flush()
            db.session.add_all([
                Note(campaign_id=ids["c"], title=f"N{p.id}", content="x", character_id=ch.id, player_id=p.id),
                CharacterItem(item_id=item_.id, character_id=ch.id, quantity=1),
                CharacterNPCRelationship(character_id=ch.id, npc_id=npc_.id, kind="alianca"),
                SessionEvent(session_id=ids["sess"], campaign_id=ids["c"], character_id=ch.id, description="e"),
            ])
            quest_.objectives.append(QuestObjective(description=f"o{p.id}"))
            quest_.characters.append(ch)
        db.session.commit()
        return Character.query.first().id, Player.query.first().id

    return ids, grow


def pages(ids, char_id, player_id):
    return ["/", "/campanhas/", f"/campanhas/{ids['c']}", "/jogadores/", f"/jogadores/{player_id}", "/personagens/",
            f"/personagens/{char_id}", "/xp/", "/notas/", "/sessoes/", f"/sessoes/{ids['sess']}", "/sessoes/linha-do-tempo",
            "/npcs/", f"/npcs/{ids['npc']}", "/missoes/", f"/missoes/{ids['quest']}", "/itens/", f"/itens/{ids['item']}",
            "/mensagens/", "/backup/", "/conta"]


def test_query_count_does_not_grow_with_the_amount_of_data(client, db, world):
    ids, grow = world
    char_id, player_id = grow(2)
    small = {u: queries(client, db, u) for u in pages(ids, char_id, player_id)}
    grow(12)
    big = {u: queries(client, db, u) for u in pages(ids, char_id, player_id)}
    assert big == small, {u: (small[u], big[u]) for u in small if small[u] != big[u]}   # nenhuma página tem N+1


def test_every_page_stays_within_a_small_query_budget(client, db, world):
    ids, grow = world
    char_id, player_id = grow(5)
    for url in pages(ids, char_id, player_id):
        assert queries(client, db, url) <= 14, url


def test_base_overhead_is_two_queries(client, db, world):
    assert queries(client, db, "/backup/") <= 3        # sessão+usuário num JOIN + lista de campanhas


def test_server_timing_header_present(client):
    r = client.get("/conta")
    assert re.match(r'db;dur=[\d.]+;desc="\d+ consultas", app;dur=[\d.]+', r.headers["Server-Timing"])


def test_static_assets_are_versioned_and_cached_forever(client):
    html = client.get("/conta").get_data(as_text=True)
    urls = re.findall(r'(?:href|src)="(/static/[^"]+\?v=[0-9a-f]+)"', html)
    assert any("app.css" in u for u in urls) and any("app.js" in u for u in urls) and any("polish.css" in u for u in urls)
    for u in urls:
        r = client.get(u)
        assert r.status_code == 200 and "immutable" in r.headers["Cache-Control"] and "max-age=31536000" in r.headers["Cache-Control"]
    assert "immutable" not in client.get("/static/css/app.css").headers.get("Cache-Control", "")


def test_authenticated_pages_are_never_cacheable(client):
    assert client.get("/conta").headers["Cache-Control"] == "no-store"


def test_no_heavy_css_effects(app):
    import pathlib
    css = (pathlib.Path(app.static_folder) / "css" / "polish.css").read_text(encoding="utf-8")
    assert "backdrop-filter: blur" not in css.replace("sem backdrop-filter", "") and "background-attachment: fixed" not in css
    assert "@view-transition { navigation: auto" not in css
    assert len([l for l in css.splitlines() if "infinite" in l and not l.lstrip().startswith("/*")]) <= 2   # só spinner/skeleton

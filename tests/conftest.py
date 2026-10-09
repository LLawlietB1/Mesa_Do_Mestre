import os

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Campaign, Character, Player, User
from app.services import auth as auth_service
from app.services.campaigns import enroll_player

PASSWORD = "senha-forte-123"


@pytest.fixture()
def app(tmp_path):
    """Aplicação com banco TEMPORÁRIO (SQLite em arquivo; ou Postgres se TEST_DATABASE_URL estiver definida).
    Nunca toca nos dados reais."""
    cfg = {}
    pg = os.environ.get("TEST_DATABASE_URL")
    if pg:
        from config import normalize_database_url, engine_options
        url = normalize_database_url(pg)
        cfg = {"SQLALCHEMY_DATABASE_URI": url, "SQLALCHEMY_ENGINE_OPTIONS": engine_options(url)}
    else:
        cfg = {}   # SQLite em memória (rápido; o disco não é usado)
    app = create_app("testing", cfg)
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
        _db.engine.dispose()


@pytest.fixture()
def db(app):
    return _db


def _make_user(name, email):
    return auth_service.register_user(name, email, PASSWORD, "palavra secreta")


@pytest.fixture()
def user(db):
    return _make_user("Mestre A", "a@example.com")


@pytest.fixture()
def other_user(db):
    return _make_user("Mestre B", "b@example.com")


def _logged_client(app, email):
    c = app.test_client()
    r = c.post("/login", data={"email": email, "password": PASSWORD})
    assert r.status_code == 302, "login de teste falhou"
    return c


@pytest.fixture()
def client(app, user):
    """Cliente já logado como o usuário A."""
    return _logged_client(app, user.email)


@pytest.fixture()
def other_client(app, other_user):
    return _logged_client(app, other_user.email)


@pytest.fixture()
def anon_client(app):
    return app.test_client()


@pytest.fixture()
def make_campaign(db, user):
    def make(name="Campanha A", owner=None, **kw):
        c = Campaign(name=name, status=kw.pop("status", "ativa"), owner_id=(owner or user).id, **kw)
        db.session.add(c)
        db.session.commit()
        return c
    return make


@pytest.fixture()
def make_player(db, user):
    def make(name="Ana", owner=None, **kw):
        p = Player(display_name=name, owner_id=(owner or user).id, **kw)
        db.session.add(p)
        db.session.commit()
        return p
    return make


@pytest.fixture()
def make_character(db, make_player):
    def make(campaign, name="Herói", player=None, **kw):
        player = player or make_player(f"Jogador de {name}", owner=db.session.get(User, campaign.owner_id))
        enroll_player(campaign.id, player.id)
        ch = Character(name=name, campaign_id=campaign.id, player_id=player.id, **kw)
        db.session.add(ch)
        db.session.commit()
        return ch
    return make


@pytest.fixture()
def select_campaign(client):
    def select(campaign):
        client.post("/campanhas/selecionar", data={"campaign_id": campaign.id})
    return select

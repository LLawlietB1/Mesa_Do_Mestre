"""Login, cadastro, bloqueio, recuperação por palavra-chave, sessões e conta."""
from datetime import timedelta

import pytest

from app.models import Campaign, Player, User, UserSession
from app.models.mixins import utcnow
from app.services import auth as auth_service
from tests.conftest import PASSWORD

PROTECTED = ["/", "/campanhas/", "/jogadores/", "/personagens/", "/xp/", "/notas/", "/sessoes/", "/npcs/",
             "/missoes/", "/itens/", "/backup/", "/mensagens/", "/conta", "/campanhas/nova", "/jogadores/novo"]


@pytest.mark.parametrize("path", PROTECTED)
def test_anonymous_is_redirected_to_login(anon_client, path):
    r = anon_client.get(path)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_anonymous_cannot_post_or_use_json_api(anon_client, user):
    assert anon_client.post("/campanhas/nova", data={"name": "X", "status": "ativa"}).status_code == 302
    assert Campaign.query.count() == 0
    r = anon_client.post("/xp/api/personagens/1", json={"action": "add", "value": 5})
    assert r.status_code == 401 and r.get_json()["ok"] is False
    assert anon_client.get("/media/" + "a" * 32).status_code == 302


def test_public_pages_render(anon_client):
    for path in ("/login", "/cadastro", "/esqueci-senha", "/health"):
        assert anon_client.get(path).status_code == 200


def test_login_redirects_back_to_next_and_blocks_open_redirect(app, user):
    c = app.test_client()
    r = c.post("/login", data={"email": user.email, "password": PASSWORD, "next": "/jogadores/"})
    assert r.headers["Location"].endswith("/jogadores/")
    c = app.test_client()
    r = c.post("/login", data={"email": user.email, "password": PASSWORD, "next": "//evil.example/x"})
    assert "evil" not in r.headers["Location"]
    c = app.test_client()
    r = c.post("/login", data={"email": user.email, "password": PASSWORD, "next": "https://evil.example"})
    assert "evil" not in r.headers["Location"]


def test_password_and_session_token_are_never_stored_in_clear(app, user, client):
    assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash
    assert user.recovery_hash.startswith("$argon2id$")
    token = client.get_cookie("mm_session").value
    row = UserSession.query.one()
    assert row.token_hash != token and row.token_hash == auth_service.sha256(token)


def test_cookie_flags(app, user):
    c = app.test_client()
    r = c.post("/login", data={"email": user.email, "password": PASSWORD})
    cookie = [h for h in r.headers.getlist("Set-Cookie") if h.startswith("mm_session=")][0]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_wrong_password_is_generic_and_does_not_leak_account_existence(app, user):
    c = app.test_client()
    a = c.post("/login", data={"email": user.email, "password": "errada123"}).get_data(as_text=True)
    b = c.post("/login", data={"email": "naoexiste@example.com", "password": "errada123"}).get_data(as_text=True)
    assert "E-mail ou senha incorretos." in a and "E-mail ou senha incorretos." in b


def test_lockout_after_five_failures_then_unlock(app, user, db):
    c = app.test_client()
    for _ in range(5):
        c.post("/login", data={"email": user.email, "password": "errada123"})
    r = c.post("/login", data={"email": user.email, "password": PASSWORD})   # senha certa, mas bloqueado
    assert "Muitas tentativas" in r.get_data(as_text=True) and r.status_code == 200
    user = db.session.get(User, user.id)
    user.locked_until = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert c.post("/login", data={"email": user.email, "password": PASSWORD}).status_code == 302


def test_expired_session_is_rejected(app, user, client, db):
    UserSession.query.update({"expires_at": utcnow() - timedelta(seconds=1)})
    db.session.commit()
    assert client.get("/").status_code == 302


def test_logout_invalidates_session_token(app, user, client):
    old = client.get_cookie("mm_session").value
    assert client.post("/sair").status_code == 302
    assert UserSession.query.count() == 0
    stale = app.test_client()
    stale.set_cookie("mm_session", old)
    assert stale.get("/").status_code == 302


# ---------------------------------------------------------------- cadastro

def _register(client, **over):
    data = {"name": "Nova Pessoa", "email": "nova@example.com", "password": "senha-forte-1", "confirm": "senha-forte-1",
            "passphrase": "minha palavra"}
    data.update(over)
    return client.post("/cadastro", data=data)


def test_register_creates_account_and_logs_in(anon_client):
    r = _register(anon_client)
    assert r.status_code == 302
    assert User.query.filter_by(email="nova@example.com").one().role == "MESTRE"
    assert anon_client.get("/").status_code == 200       # já está logado


@pytest.mark.parametrize("over,msg", [
    ({"password": "curta1", "confirm": "curta1"}, "pelo menos 8"),
    ({"password": "somenteletras", "confirm": "somenteletras"}, "letras e números"),
    ({"confirm": "diferente-123"}, "não conferem"),
    ({"passphrase": "abc"}, "pelo menos 6"),
    ({"email": "isso-nao-e-email"}, "E-mail inválido"),
    ({"name": ""}, "Campo obrigatório"),
])
def test_register_validation(anon_client, over, msg):
    r = _register(anon_client, **over)
    assert r.status_code == 200 and msg in r.get_data(as_text=True)
    assert User.query.count() == 0


def test_register_duplicate_email(anon_client, user):
    r = _register(anon_client, email=user.email.upper())
    assert "Já existe uma conta" in r.get_data(as_text=True) and User.query.count() == 1


def test_registration_invite_code_mode(app, anon_client):
    app.config["INVITE_CODE"] = "segredo-do-grupo"
    assert _register(anon_client).status_code == 200 and User.query.count() == 0
    assert _register(anon_client, invite_code="errado").status_code == 200 and User.query.count() == 0
    assert _register(anon_client, invite_code="segredo-do-grupo").status_code == 302 and User.query.count() == 1


def test_registration_closed_without_invite_in_production_mode(app, anon_client):
    app.config.update(INVITE_CODE="", ALLOW_OPEN_REGISTRATION=False)
    assert anon_client.get("/cadastro").status_code == 403
    assert "INVITE_CODE" in anon_client.get("/cadastro").get_data(as_text=True)
    assert "/cadastro" in anon_client.get("/login").get_data(as_text=True)      # o link continua visível
    assert _register(anon_client).status_code == 403 and User.query.count() == 0


def test_production_without_secret_key_serves_explanatory_error(monkeypatch):
    from app import create_app
    monkeypatch.delenv("SECRET_KEY", raising=False)
    app = create_app("production")
    for path in ("/", "/login", "/qualquer/coisa"):
        r = app.test_client().get(path)
        assert r.status_code == 500 and "SECRET_KEY" in r.get_data(as_text=True)


# ---------------------------------------------------------------- recuperação

def test_reset_with_passphrase_changes_password_and_ends_sessions(app, user, client, db):
    anon = app.test_client()
    r = anon.post("/esqueci-senha", data={"email": user.email, "passphrase": "  PALAVRA Secreta ", "password": "nova-senha-9", "confirm": "nova-senha-9"})
    assert r.status_code == 302                          # a palavra-chave ignora caixa/espaços nas pontas
    assert UserSession.query.count() == 0 and client.get("/").status_code == 302
    assert anon.post("/login", data={"email": user.email, "password": PASSWORD}).status_code == 200
    assert anon.post("/login", data={"email": user.email, "password": "nova-senha-9"}).status_code == 302


def test_reset_wrong_passphrase_is_generic_and_counts_toward_lockout(app, user, db):
    anon = app.test_client()
    for _ in range(5):
        r = anon.post("/esqueci-senha", data={"email": user.email, "passphrase": "errada errada", "password": "nova-senha-9", "confirm": "nova-senha-9"})
        assert "incorretos" in r.get_data(as_text=True)
    r = anon.post("/esqueci-senha", data={"email": user.email, "passphrase": "palavra secreta", "password": "nova-senha-9", "confirm": "nova-senha-9"})
    assert "Muitas tentativas" in r.get_data(as_text=True)
    r = anon.post("/esqueci-senha", data={"email": "x@y.com", "passphrase": "qualquer coisa", "password": "nova-senha-9", "confirm": "nova-senha-9"})
    assert "E-mail ou palavra-chave incorretos." in r.get_data(as_text=True)


def test_reset_weak_new_password_rejected(app, user):
    r = app.test_client().post("/esqueci-senha", data={"email": user.email, "passphrase": "palavra secreta", "password": "fraca", "confirm": "fraca"})
    assert "pelo menos 8" in r.get_data(as_text=True)


# ---------------------------------------------------------------- conta

def test_change_password_requires_current_and_ends_sessions(app, user, client):
    r = client.post("/conta/senha", data={"current": "errada123", "password": "outra-senha-7", "confirm": "outra-senha-7"})
    assert "Senha atual incorreta" in r.get_data(as_text=True)
    r = client.post("/conta/senha", data={"current": PASSWORD, "password": "outra-senha-7", "confirm": "outra-senha-7"})
    assert r.status_code == 302 and client.get("/").status_code == 302
    assert app.test_client().post("/login", data={"email": user.email, "password": "outra-senha-7"}).status_code == 302


def test_change_recovery_phrase(app, user, client, db):
    old = user.recovery_hash
    assert "pelo menos 6" in client.post("/conta/recuperacao", data={"current": PASSWORD, "passphrase": "x"}).get_data(as_text=True)
    assert client.post("/conta/recuperacao", data={"current": PASSWORD, "passphrase": "frase nova longa"}).status_code == 302
    db.session.refresh(user)
    assert user.recovery_hash != old


def test_logout_all_devices(app, user, client):
    second = app.test_client()
    second.post("/login", data={"email": user.email, "password": PASSWORD})
    assert UserSession.query.count() == 2
    client.post("/conta/sair-de-todos")
    assert UserSession.query.count() == 0 and second.get("/").status_code == 302


def test_delete_account_removes_everything_of_that_user_only(app, user, other_user, client, make_campaign, make_character, db):
    from app.models import Character, FileAsset
    mine, theirs = make_campaign("Minha"), make_campaign("Dela", owner=other_user)
    make_character(mine, "Meu"); make_character(theirs, "Dela")
    db.session.add(FileAsset(id="a" * 32, owner_id=user.id, content_type="image/webp", size=1, data=b"x"))
    db.session.commit()
    assert "Digite EXCLUIR" in client.post("/conta/excluir", data={"current": PASSWORD, "confirm_text": "nao"}).get_data(as_text=True)
    assert "Senha atual incorreta" in client.post("/conta/excluir", data={"current": "errada123", "confirm_text": "EXCLUIR"}).get_data(as_text=True)
    assert User.query.count() == 2
    r = client.post("/conta/excluir", data={"current": PASSWORD, "confirm_text": "excluir"})
    assert r.status_code == 302
    assert User.query.filter_by(id=user.id).count() == 0
    assert [c.name for c in Campaign.query.all()] == ["Dela"]
    assert [c.name for c in Character.query.all()] == ["Dela"]
    assert Player.query.count() == 1 and FileAsset.query.count() == 0 and UserSession.query.filter_by(user_id=user.id).count() == 0


def test_account_page_renders(client):
    assert client.get("/conta").status_code == 200


def test_first_account_becomes_admin_only_when_database_is_empty(app, db):
    app.config["FIRST_USER_IS_ADMIN"] = True
    first = auth_service.register_user("Dono", "dono@example.com", PASSWORD, "palavra dono")
    second = auth_service.register_user("Amigo", "amigo@example.com", PASSWORD, "palavra amigo")
    assert first.role == "ADMIN" and first.can_upload_images
    assert second.role == "MESTRE" and not second.can_upload_images


def test_first_account_is_regular_when_flag_is_off(app, db):
    assert auth_service.register_user("A", "a1@example.com", PASSWORD, "palavra a").role == "MESTRE"

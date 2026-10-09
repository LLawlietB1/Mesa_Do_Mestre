"""Liberação do envio de imagens: pedido por e-mail ao administrador, página de administração e bloqueio."""
import io
import json

import pytest

from app.models import FileAsset, User
from app.models.mixins import utcnow
from app.services import emailer
from tests.conftest import PASSWORD, _logged_client
from tests.test_modules import png_bytes


@pytest.fixture()
def locked(db, user):
    """O usuário A, SEM liberação de imagens (por padrão os fixtures de teste já vêm liberados)."""
    user.images_enabled = False
    db.session.commit()
    return user


@pytest.fixture()
def admin(db, app):
    from app.services import auth as auth_service
    u = auth_service.register_user("Admin", "admin@example.com", PASSWORD, "palavra admin")
    u.role = "ADMIN"
    db.session.commit()
    return u


@pytest.fixture()
def admin_client(app, admin):
    return _logged_client(app, admin.email)


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr("app.routes.auth.send_admin_email", lambda subject, html: sent.append((subject, html)) or True)
    return sent


def _upload(client, character, name="a.png"):
    return client.post(f"/personagens/{character.id}/editar", data={
        "name": character.name, "player_id": character.player_id, "status": "ativo", "portrait": (io.BytesIO(png_bytes()), name)},
        content_type="multipart/form-data")


# ---------------------------------------------------------------- bloqueio

def test_upload_is_blocked_without_approval_even_with_crafted_request(client, locked, make_campaign, make_character, db):
    ch = make_character(make_campaign())
    r = _upload(client, ch)
    assert r.status_code == 200 and "ainda não foi liberado" in r.get_data(as_text=True)
    assert FileAsset.query.count() == 0


def test_forms_show_disabled_file_field_with_explanation(client, locked):
    import re
    html = client.get("/campanhas/nova").get_data(as_text=True)
    tag = re.search(r"<input[^>]*name=\"cover\"[^>]*>", html).group(0)
    assert "disabled" in tag and "Solicite a liberação" in html


def test_forms_without_image_fields_are_unaffected(client, locked):
    assert client.get("/jogadores/novo").status_code == 200
    assert client.post("/jogadores/novo", data={"display_name": "Ana", "status": "ativo"}).status_code == 302


def test_upload_works_after_approval_and_for_admins(client, locked, admin_client, admin, make_campaign, make_character, db):
    ch = make_character(make_campaign())
    assert _upload(client, ch).status_code == 200
    assert admin_client.post(f"/admin/imagens/{locked.id}/liberar").status_code == 302
    assert _upload(client, ch).status_code == 302 and FileAsset.query.count() == 1
    assert admin.images_enabled is False and admin.can_upload_images is True      # admin sempre pode


# ---------------------------------------------------------------- pedido por e-mail

def test_request_sends_email_to_admin_and_records_request(client, locked, outbox, db):
    r = client.post("/conta/imagens/pedir", follow_redirects=True)
    assert "Pedido enviado" in r.get_data(as_text=True)
    db.session.refresh(locked)
    assert locked.images_requested_at is not None and locked.images_enabled is False
    subject, html = outbox[0]
    assert "pedido de liberação de imagens" in subject
    assert locked.email in html and "/admin/imagens" in html and f"flask approve-images {locked.email}" in html


def test_email_escapes_user_supplied_text(client, locked, outbox, db):
    locked.name = '<script>alert(1)</script>'
    db.session.commit()
    client.post("/conta/imagens/pedir")
    assert "<script>" not in outbox[0][1] and "&lt;script&gt;" in outbox[0][1]


def test_request_cooldown_and_already_enabled(client, locked, outbox, db):
    client.post("/conta/imagens/pedir")
    r = client.post("/conta/imagens/pedir", follow_redirects=True)
    assert "já pediu" in r.get_data(as_text=True) and len(outbox) == 1
    locked.images_requested_at = utcnow().replace(year=2020)
    db.session.commit()
    client.post("/conta/imagens/pedir")
    assert len(outbox) == 2                                 # depois do intervalo, pode reenviar
    locked.images_enabled = True
    db.session.commit()
    r = client.post("/conta/imagens/pedir", follow_redirects=True)
    assert "já está liberado" in r.get_data(as_text=True) and len(outbox) == 2


def test_request_is_recorded_even_if_email_fails(client, locked, db):
    r = client.post("/conta/imagens/pedir", follow_redirects=True)      # sem RESEND_API_KEY nos testes
    assert "não foi possível enviar o e-mail" in r.get_data(as_text=True)
    db.session.refresh(locked)
    assert locked.images_requested_at is not None


def test_account_page_shows_status(client, locked, outbox):
    assert "Pedir liberação de imagens" in client.get("/conta").get_data(as_text=True)
    client.post("/conta/imagens/pedir")
    assert "Pedir liberação novamente" in client.get("/conta").get_data(as_text=True)


# ---------------------------------------------------------------- e-mail (Resend)

def test_resend_request_format(app, monkeypatch):
    app.config.update(RESEND_API_KEY="re_test", ADMIN_EMAIL="dono@example.com", RESEND_FROM="Mesa <onboarding@resend.dev>")
    seen = {}

    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout):
        seen.update(url=req.full_url, auth=req.get_header("Authorization"), body=json.loads(req.data), timeout=timeout)
        return Resp()

    monkeypatch.setattr(emailer.urllib.request, "urlopen", fake)
    assert emailer.send_admin_email("Assunto", "<p>oi</p>") is True
    assert seen["url"] == "https://api.resend.com/emails" and seen["auth"] == "Bearer re_test"
    assert seen["body"] == {"from": "Mesa <onboarding@resend.dev>", "to": ["dono@example.com"], "subject": "Assunto", "html": "<p>oi</p>"}


def test_resend_failures_return_false_and_never_raise(app, monkeypatch):
    import urllib.error
    assert emailer.send_admin_email("x", "y") is False                   # sem configuração
    app.config.update(RESEND_API_KEY="re_test", ADMIN_EMAIL="dono@example.com")

    def http_error(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "forbidden", {}, io.BytesIO(b"nope"))

    monkeypatch.setattr(emailer.urllib.request, "urlopen", http_error)
    assert emailer.send_admin_email("x", "y") is False
    monkeypatch.setattr(emailer.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("down")))
    assert emailer.send_admin_email("x", "y") is False


# ---------------------------------------------------------------- administração

def test_admin_pages_are_hidden_from_regular_users_and_anonymous(client, anon_client, other_user, db):
    other_user.images_enabled = False
    db.session.commit()
    for method, url in [("get", "/admin/imagens"), ("post", f"/admin/imagens/{other_user.id}/liberar"), ("post", f"/admin/imagens/{other_user.id}/revogar")]:
        assert getattr(client, method)(url).status_code == 404
    assert anon_client.get("/admin/imagens").status_code in (302, 404)   # anônimo vai ao login; nunca vê a página
    assert "Administração" not in client.get("/").get_data(as_text=True)
    assert User.query.get(other_user.id).images_enabled is False


def test_admin_lists_pending_approves_and_revokes(admin_client, locked, other_user, db, outbox, client):
    other_user.images_enabled = False
    db.session.commit()
    client.post("/conta/imagens/pedir")
    html = admin_client.get("/admin/imagens").get_data(as_text=True)
    assert "Pedidos pendentes (1)" in html and locked.email in html
    assert "Administração" in admin_client.get("/").get_data(as_text=True)
    admin_client.post(f"/admin/imagens/{locked.id}/liberar")
    db.session.refresh(locked); db.session.refresh(other_user)
    assert locked.images_enabled and locked.images_requested_at is None and other_user.images_enabled is False
    assert "Pedidos pendentes (0)" in admin_client.get("/admin/imagens").get_data(as_text=True)
    admin_client.post(f"/admin/imagens/{locked.id}/revogar")
    db.session.refresh(locked)
    assert locked.images_enabled is False
    assert admin_client.post("/admin/imagens/99999/liberar").status_code == 404


def test_admin_page_escapes_names(admin_client, other_user, db):
    other_user.name = "<img src=x onerror=alert(1)>"
    other_user.images_requested_at = utcnow()
    db.session.commit()
    html = admin_client.get("/admin/imagens").get_data(as_text=True)
    assert "<img src=x" not in html and "&lt;img" in html


def test_cli_approve_and_make_admin(app, user, db):
    runner = app.test_cli_runner()
    assert "liberado" in runner.invoke(args=["approve-images", user.email]).output
    db.session.refresh(user); assert user.images_enabled
    assert "revogado" in runner.invoke(args=["approve-images", user.email, "--revoke"]).output
    assert "ADMIN" in runner.invoke(args=["make-admin", user.email]).output
    db.session.refresh(user); assert user.is_admin
    assert "MESTRE" in runner.invoke(args=["make-admin", user.email, "--revoke"]).output
    assert "Nenhum usuário" in runner.invoke(args=["approve-images", "x@y.com"]).output

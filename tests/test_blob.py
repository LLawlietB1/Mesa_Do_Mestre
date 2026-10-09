"""Imagens no Vercel Blob privado (com um Blob falso em memória)."""
import io
import json
import re
import urllib.parse

import pytest

from app.models import Campaign, Character, FileAsset
from app.services import backup, blobstore
from app.services.backup import BackupError
from tests.test_backup import MANIFEST, _zip
from tests.test_modules import png_bytes

TOKEN = "vercel_blob_rw_store123_SEGREDOSEGREDO"
HOST = "https://store123.private.blob.vercel-storage.com/"


class FakeBlob:
    """Imita a API do Vercel Blob e confere o protocolo (token, privado, versão)."""

    def __init__(self):
        self.files, self.log = {}, []

    def __call__(self, req):
        method, url = req.get_method(), req.full_url
        h = {k.lower(): v for k, v in req.header_items()}
        self.log.append((method, url))
        assert h.get("authorization") == f"Bearer {TOKEN}", "token ausente/errado"
        if method == "PUT":
            assert url.startswith("https://vercel.com/api/blob?pathname="), url
            assert h["x-vercel-blob-access"] == "private" and h["x-api-version"] == "11" and h["x-allow-overwrite"] == "0"
            path = urllib.parse.unquote(url.split("pathname=", 1)[1])
            self.files[HOST + path] = (req.data, h["x-content-type"])
            return 200, {}, json.dumps({"url": HOST + path, "downloadUrl": HOST + path + "?download=1", "pathname": path,
                                        "contentType": h["x-content-type"], "contentDisposition": "inline"}).encode()
        if method == "POST":
            assert url == "https://vercel.com/api/blob/delete"
            for u in json.loads(req.data)["urls"]:
                self.files.pop(u, None)
            return 200, {}, b""
        if method == "GET":
            if url in self.files:
                data, ctype = self.files[url]
                return 200, {"Content-Type": ctype}, data
            return 404, {}, b"not found"
        raise AssertionError(method)


@pytest.fixture()
def blob(app, monkeypatch):
    fake = FakeBlob()
    app.config["BLOB_READ_WRITE_TOKEN"] = TOKEN
    monkeypatch.setattr(blobstore, "_http", fake)
    return fake


@pytest.fixture()
def hero(make_campaign, make_character):
    return make_character(make_campaign("Blob"), "Aria")


def upload(client, ch, data=None):
    return client.post(f"/personagens/{ch.id}/editar", data={
        "name": ch.name, "player_id": ch.player_id, "status": "ativo",
        "portrait": (io.BytesIO(data or png_bytes()), "a.png")}, content_type="multipart/form-data")


def test_upload_goes_to_private_blob_not_to_the_database(client, blob, hero, db):
    assert upload(client, hero).status_code == 302
    asset = FileAsset.query.one()
    assert asset.storage_url.startswith(HOST + "img/") and asset.data is None and asset.size > 0
    assert list(blob.files) == [asset.storage_url]


def test_media_is_served_through_the_app_with_ownership_and_never_exposes_blob_url(client, other_client, blob, hero, db):
    upload(client, hero)
    asset = FileAsset.query.one()
    r = client.get(f"/media/{asset.id}")
    assert r.status_code == 200 and r.mimetype == "image/webp" and r.data[:4] == b"RIFF"
    assert "immutable" in r.headers["Cache-Control"] and "private" in r.headers["Cache-Control"]
    before = len(blob.log)
    assert other_client.get(f"/media/{asset.id}").status_code == 404           # outro usuário: nem consulta o Blob
    assert len(blob.log) == before
    for page in (f"/personagens/{hero.id}", f"/personagens/{hero.id}/editar", "/personagens/", "/"):
        html = client.get(page).get_data(as_text=True)
        assert "blob.vercel-storage.com" not in html and TOKEN not in html and asset.storage_url not in html
    assert f"/media/{asset.id}" in client.get("/personagens/").get_data(as_text=True)


def test_replacing_and_deleting_remove_the_blob(client, blob, hero, db):
    upload(client, hero)
    first = FileAsset.query.one().storage_url
    upload(client, hero, png_bytes(color=(1, 2, 3)))
    second = FileAsset.query.one().storage_url
    assert first not in blob.files and list(blob.files) == [second]
    client.post(f"/personagens/{hero.id}/excluir")
    assert blob.files == {} and FileAsset.query.count() == 0


def test_blob_failure_gives_friendly_error_and_saves_nothing(client, blob, hero, monkeypatch):
    def down(req):
        raise blobstore.BlobError("Não foi possível falar com o armazenamento de arquivos.")
    monkeypatch.setattr(blobstore, "_http", down)
    r = upload(client, hero)
    assert r.status_code == 200 and "Não foi possível salvar a imagem" in r.get_data(as_text=True)
    assert FileAsset.query.count() == 0


def test_blob_rejection_status_is_reported(client, blob, hero, monkeypatch):
    monkeypatch.setattr(blobstore, "_http", lambda req: (403, {}, b'{"error":"forbidden"}'))
    assert "Não foi possível salvar a imagem" in upload(client, hero).get_data(as_text=True)
    assert FileAsset.query.count() == 0


def test_unconfirmed_upload_is_cleaned_up(client, blob, hero, db, monkeypatch):
    """Arquivo enviado ao Blob mas o commit falhou: nada pode ficar órfão no Blob."""
    def failing_commit():
        db.session.rollback()
        return False
    monkeypatch.setattr("app.routes.characters.safe_commit", failing_commit)
    r = upload(client, hero)
    assert r.status_code == 200
    assert FileAsset.query.count() == 0 and blob.files == {}


def test_quota_still_counts_blob_images(client, blob, hero, app):
    app.config["USER_IMAGE_QUOTA_BYTES"] = 10
    r = upload(client, hero)
    assert "Limite de armazenamento" in r.get_data(as_text=True) and blob.files == {}


def test_missing_blob_gives_502_not_a_crash(client, blob, hero, db):
    upload(client, hero)
    blob.files.clear()
    assert client.get(f"/media/{FileAsset.query.one().id}").status_code == 502


# ---------------------------------------------------------------- backup / conta

def test_backup_roundtrip_with_blob(user, blob, hero, client, db):
    upload(client, hero)
    old_url = FileAsset.query.one().storage_url
    name, payload = backup.create_backup(user)
    with __import__("zipfile").ZipFile(io.BytesIO(payload)) as zf:
        assert any(n.startswith("files/") for n in zf.namelist())
        assert "blob.vercel-storage.com" not in zf.read("data.json").decode()        # a URL privada não vai no backup
    backup.restore_backup(user, io.BytesIO(payload))
    db.session.expire_all()
    asset = FileAsset.query.one()
    assert asset.storage_url != old_url and asset.storage_url in blob.files and old_url not in blob.files
    assert Character.query.one().portrait == asset.id and client.get(f"/media/{asset.id}").status_code == 200


def test_failed_restore_removes_blobs_it_created(user, blob, hero, client, db):
    upload(client, hero)
    before = dict(blob.files)
    bad = _zip({"manifest.json": MANIFEST, "data.json": json.dumps({
        "tables": {"campaigns": [{"id": 1, "name": "x", "status": "INVALIDO"}]},
        "assets": [{"id": "e" * 32, "content_type": "image/webp"}]}), "files/" + "e" * 32: png_bytes()})
    with pytest.raises(BackupError):
        backup.restore_backup(user, io.BytesIO(bad))
    assert blob.files == before and FileAsset.query.count() == 1


def test_delete_account_removes_blobs(client, blob, hero, user, db):
    from tests.conftest import PASSWORD
    upload(client, hero)
    assert len(blob.files) == 1
    client.post("/conta/excluir", data={"current": PASSWORD, "confirm_text": "EXCLUIR"})
    assert blob.files == {} and FileAsset.query.count() == 0 and Campaign.query.count() == 0


def test_database_fallback_without_token(client, hero, db, app):
    app.config["BLOB_READ_WRITE_TOKEN"] = ""
    upload(client, hero)
    asset = FileAsset.query.one()
    assert asset.storage_url is None and asset.data and client.get(f"/media/{asset.id}").status_code == 200


# ---------------------------------------------------------------- cliente

def test_blob_client_refuses_foreign_hosts_and_never_sends_the_token_there(app, monkeypatch):
    app.config["BLOB_READ_WRITE_TOKEN"] = TOKEN
    calls = []
    monkeypatch.setattr(blobstore, "_http", lambda req: calls.append(req.full_url) or (200, {}, b""))
    for bad in ("https://evil.example/x", "http://store123.private.blob.vercel-storage.com/x", "file:///etc/passwd",
                "https://blob.vercel-storage.com.evil.example/x"):
        with pytest.raises(blobstore.BlobError):
            blobstore.fetch(bad)
    assert calls == []
    blobstore.delete(["https://evil.example/x"])                  # ignora URLs de fora
    assert calls == []


def test_blob_client_does_not_follow_redirect_to_other_host(app, monkeypatch):
    app.config["BLOB_READ_WRITE_TOKEN"] = TOKEN
    seen = []

    def http(req):
        seen.append(req.full_url)
        return 302, {"Location": "https://evil.example/steal"}, b""
    monkeypatch.setattr(blobstore, "_http", http)
    with pytest.raises(blobstore.BlobError):
        blobstore.fetch(HOST + "img/a.webp")
    assert seen == [HOST + "img/a.webp"]


def test_blob_put_rejects_foreign_url_in_response(app, monkeypatch):
    app.config["BLOB_READ_WRITE_TOKEN"] = TOKEN
    monkeypatch.setattr(blobstore, "_http", lambda req: (200, {}, json.dumps({"url": "https://evil.example/x"}).encode()))
    with pytest.raises(blobstore.BlobError):
        blobstore.put("img/a.webp", b"x", "image/webp")


def test_enabled_flag(app):
    app.config["BLOB_READ_WRITE_TOKEN"] = ""
    assert blobstore.enabled() is False
    app.config["BLOB_READ_WRITE_TOKEN"] = TOKEN
    assert blobstore.enabled() is True

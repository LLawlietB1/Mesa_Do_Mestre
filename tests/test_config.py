"""Configuração para Postgres/Vercel."""
import pytest

from config import engine_options, normalize_database_url


@pytest.mark.parametrize("raw,expected", [
    ("postgres://u:p@host/db?sslmode=require", "postgresql+psycopg://u:p@host/db?sslmode=require"),
    ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("sqlite:///x.db", "sqlite:///x.db"),
])
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected


def test_postgres_engine_options_are_serverless_safe():
    opts = engine_options("postgresql+psycopg://u:p@h/db")
    assert opts["connect_args"] == {"prepare_threshold": None}
    assert opts["poolclass"].__name__ == "NullPool"
    assert engine_options("sqlite:///x.db") == {}


def test_vercel_forces_production(monkeypatch):
    from config import env_name
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("MESA_ENV", "development")
    assert env_name() == "production"


def test_health_reports_missing_schema_and_ok(app, db, anon_client):
    r = anon_client.get("/health")
    assert r.status_code == 200 and r.get_json()["schema"] == "ok"
    db.drop_all()
    r = anon_client.get("/health")
    assert r.status_code == 503 and "flask db upgrade" in r.get_json()["schema"]


def test_missing_tables_show_helpful_message(app, db, anon_client):
    db.drop_all()
    r = anon_client.post("/login", data={"email": "a@example.com", "password": "senha-forte-1"})
    assert r.status_code == 500 and "flask db upgrade" in r.get_data(as_text=True)


def test_startup_error_page_names_the_problem(monkeypatch):
    import importlib, sys
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    sys.modules.pop("api.index", None)
    mod = importlib.import_module("api.index")
    r = mod.app.test_client().get("/qualquer")
    assert r.status_code == 500 and "SECRET_KEY" in r.get_data(as_text=True)
    sys.modules.pop("api.index", None)

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

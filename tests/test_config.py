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
    assert opts["connect_args"]["prepare_threshold"] is None
    assert opts["pool_pre_ping"] is True and opts["pool_recycle"] < 300 and opts["pool_size"] >= 1
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


def test_pyproject_dependencies_match_requirements():
    """A Vercel lê o pyproject.toml: as dependências precisam ser as mesmas do requirements.txt."""
    import tomllib
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["tool"]["vercel"]["entrypoint"] == "run:app"
    reqs = [l.strip() for l in (root / "requirements.txt").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    assert sorted(data["project"]["dependencies"]) == sorted(reqs)


def test_entrypoint_exposes_flask_app_at_top_level():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parent.parent / "run.py").read_text(encoding="utf-8"))
    assert any(isinstance(n, ast.Assign) and n.targets[0].id == "app" for n in tree.body if isinstance(n, ast.Assign))

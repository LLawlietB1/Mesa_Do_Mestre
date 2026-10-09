"""Funções auxiliares sem dependência de rotas."""
from __future__ import annotations

from datetime import date, datetime, timezone

from markupsafe import Markup, escape

MAX_KV_LINES = 40


def parse_kv_lines(text: str | None) -> dict:
    """Converte linhas `chave: valor` em dict (campos personalizados). Ignora linhas vazias."""
    result: dict = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Linha inválida (use «chave: valor»): {line[:40]}")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if not key or len(key) > 60 or len(value) > 300:
            raise ValueError(f"Chave ou valor inválido: {line[:40]}")
        result[key] = value
    if len(result) > MAX_KV_LINES:
        raise ValueError(f"Máximo de {MAX_KV_LINES} campos personalizados.")
    return result


def format_kv_lines(data: dict | None) -> str:
    return "\n".join(f"{k}: {v}" for k, v in (data or {}).items())


def like_pattern(term: str) -> str:
    """Padrão LIKE seguro (escapa %, _ e a barra); use com escape='\\'."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def to_local(value: datetime | None) -> datetime | None:
    """Datas são guardadas em UTC sem tzinfo; converte para o fuso do computador."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone()


def fmt_datetime(value: datetime | None) -> str:
    local = to_local(value)
    return local.strftime("%d/%m/%Y %H:%M") if local else "—"


def fmt_date(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = to_local(value)
    return value.strftime("%d/%m/%Y")


def multiline(value: str | None) -> Markup:
    """Escapa o texto (anti-XSS) e preserva quebras de linha."""
    if not value:
        return Markup("")
    return Markup("<br>").join(escape(line) for line in value.splitlines())


def to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

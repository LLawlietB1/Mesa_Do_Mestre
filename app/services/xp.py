"""Regras de negócio da barra de XP (0-100, controlada manualmente pelo mestre)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Character, ExperienceHistory

MIN_PERCENT, MAX_PERCENT = 0, 100
MAX_REASON = 300


class XPError(ValueError):
    """Entrada inválida ou operação não permitida na barra de XP."""


@dataclass
class XPResult:
    character: Character
    previous: int
    new: int
    requested: int | None
    changed: bool

    @property
    def delta(self) -> int:
        return self.new - self.previous

    @property
    def clamped(self) -> bool:
        return self.requested is not None and self.requested != self.delta


def clamp(value: int) -> int:
    return max(MIN_PERCENT, min(MAX_PERCENT, value))


def parse_int(value, field: str = "valor") -> int:
    if isinstance(value, bool):
        raise XPError(f"O {field} deve ser um número inteiro.")
    try:
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError
            return int(value)
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise XPError(f"O {field} deve ser um número inteiro.") from None


def _clean_reason(reason) -> str | None:
    reason = (reason or "").strip() or None
    if reason and len(reason) > MAX_REASON:
        raise XPError(f"O motivo deve ter no máximo {MAX_REASON} caracteres.")
    return reason


def _record(character, new, requested, origin, reason, batch_id=None) -> XPResult:
    """Aplica o novo percentual e grava o histórico (sem commit). Sem mudança, nada é gravado."""
    previous = character.xp_percent
    if new == previous:
        return XPResult(character, previous, new, requested, changed=False)
    character.xp_percent = new
    db.session.add(ExperienceHistory(
        character=character, campaign_id=character.campaign_id,
        previous_percent=previous, new_percent=new, delta=new - previous,
        requested_delta=requested, cycle=character.xp_cycle, reason=reason,
        origin=origin, batch_id=batch_id,
    ))
    return XPResult(character, previous, new, requested, changed=True)


def _commit():
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha ao gravar alteração de XP")
        raise XPError("Não foi possível salvar a alteração. Nenhum dado foi modificado.") from None


def _apply_delta(character, delta, reason, origin, batch_id=None) -> XPResult:
    if delta == 0:
        raise XPError("Informe uma variação diferente de zero.")
    if abs(delta) > MAX_PERCENT:
        raise XPError("A variação deve estar entre -100 e 100.")
    return _record(character, clamp(character.xp_percent + delta), delta, origin, reason, batch_id)


def apply_delta(character: Character, delta, reason=None) -> XPResult:
    """Soma/subtrai pontos percentuais, respeitando os limites 0 e 100."""
    result = _apply_delta(character, parse_int(delta, "valor da variação"), _clean_reason(reason), "individual")
    _commit()
    return result


def set_percent(character: Character, percent, reason=None) -> XPResult:
    """Define diretamente o percentual (0-100)."""
    percent = parse_int(percent, "percentual")
    if not MIN_PERCENT <= percent <= MAX_PERCENT:
        raise XPError("O percentual deve estar entre 0 e 100.")
    result = _record(character, percent, percent - character.xp_percent, "individual", _clean_reason(reason))
    _commit()
    return result


def reset(character: Character, reason=None) -> XPResult:
    return set_percent(character, 0, reason or "Progresso zerado")


def complete(character: Character, reason=None) -> XPResult:
    return set_percent(character, 100, reason or "Progresso completado")


def start_new_cycle(character: Character, reason=None) -> XPResult:
    """Inicia novo ciclo: só permitido com a barra em 100%. Não sobe o nível nem apaga o histórico."""
    if character.xp_percent != MAX_PERCENT:
        raise XPError("O novo ciclo só pode ser iniciado quando a barra estiver em 100%.")
    result = _record(character, 0, -MAX_PERCENT, "novo_ciclo", _clean_reason(reason) or "Novo ciclo de XP")
    character.xp_cycle += 1
    _commit()
    return result


def apply_bulk(campaign_id: int, character_ids, delta, reason=None) -> list[XPResult]:
    """Aplica a mesma variação a vários personagens da MESMA campanha, em uma única transação."""
    delta = parse_int(delta, "valor da variação")
    reason = _clean_reason(reason)
    ids = list(dict.fromkeys(parse_int(i, "personagem") for i in character_ids))
    if not ids:
        raise XPError("Selecione ao menos um personagem.")
    characters = Character.query.filter(Character.id.in_(ids)).all()
    if len(characters) != len(ids):
        raise XPError("Um ou mais personagens selecionados não existem.")
    if any(c.campaign_id != campaign_id for c in characters):
        raise XPError("Todos os personagens devem pertencer à campanha selecionada.")
    batch_id = str(uuid.uuid4())
    try:
        results = [_apply_delta(c, delta, reason, "coletiva", batch_id) for c in sorted(characters, key=lambda c: c.name.lower())]
        db.session.commit()
    except XPError:
        db.session.rollback()
        raise
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha na alteração coletiva de XP")
        raise XPError("Não foi possível salvar a alteração coletiva. Nenhum personagem foi modificado.") from None
    return results


def describe(result: XPResult) -> str:
    name = result.character.name
    if not result.changed:
        return f"{name}: sem alteração ({result.new}%)"
    note = " (limitado a 0–100%)" if result.clamped else ""
    return f"{name}: {result.previous}% → {result.new}%{note}"

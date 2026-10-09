"""Validações de coerência entre campanhas (nunca confie só nos filtros do front-end)."""


class CampaignMismatchError(ValueError):
    pass


def ensure_same_campaign(campaign_id: int, objects, what: str = "registro") -> None:
    """Garante que todos os objetos (com atributo campaign_id) pertencem à campanha informada."""
    for obj in objects:
        if obj is None:
            continue
        if obj.campaign_id != campaign_id:
            raise CampaignMismatchError(f"O {what} «{getattr(obj, 'name', None) or getattr(obj, 'title', obj.id)}» pertence a outra campanha.")


def load_in_campaign(model, ids, campaign_id: int, what: str):
    """Carrega registros por id exigindo que existam e sejam da campanha."""
    ids = list(dict.fromkeys(i for i in ids if i))
    if not ids:
        return []
    rows = model.query.filter(model.id.in_(ids)).all()
    if len(rows) != len(ids):
        raise CampaignMismatchError(f"Um ou mais {what} informados não existem.")
    ensure_same_campaign(campaign_id, rows, what)
    return rows

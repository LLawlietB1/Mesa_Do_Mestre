"""Campanha atual (guardada na sessão do navegador) e participação de jogadores."""
from __future__ import annotations

from flask import g, session

from app.extensions import db
from app.services.integrity import CampaignMismatchError
from app.models import Campaign, CampaignPlayer, Character, Player
from app.models.mixins import utcnow
from app.services.ownership import is_owned, my_campaigns, my_players

SESSION_KEY = "campaign_id"


def reset_request_cache() -> None:
    """Chamado no início de cada requisição (o `g` pode ser reaproveitado em testes/contextos longos)."""
    for key in ("_campaigns", "_current", "_current_set"):
        g.pop(key, None)


def user_campaigns() -> list[Campaign]:
    """Campanhas do usuário logado, numa única consulta por requisição (seletor do topo + campanha atual)."""
    cached = g.get("_campaigns")
    if cached is None:
        cached = my_campaigns().order_by(Campaign.status == "encerrada", Campaign.name).all()
        g._campaigns = cached
    return cached


def get_current_campaign() -> Campaign | None:
    """Campanha selecionada; se não houver (ou foi apagada), escolhe a mais recente não encerrada.
    Sai da lista já carregada: ids de outra conta guardados na sessão simplesmente não existem nela."""
    if g.get("_current_set"):
        return g._current
    campaigns = user_campaigns()
    campaign = next((c for c in campaigns if c.id == session.get(SESSION_KEY)), None)
    if campaign is None:
        pool = [c for c in campaigns if c.status != "encerrada"] or campaigns
        campaign = max(pool, key=lambda c: c.id) if pool else None
        if campaign is not None:
            session[SESSION_KEY] = campaign.id
        else:
            session.pop(SESSION_KEY, None)
    g._current, g._current_set = campaign, True
    return campaign


def set_current_campaign(campaign: Campaign) -> None:
    session[SESSION_KEY] = campaign.id
    g._current, g._current_set = campaign, True


def enroll_player(campaign_id: int, player_id: int) -> CampaignPlayer:
    """Registra (ou reativa) a participação do jogador na campanha. Não faz commit."""
    campaign, player = db.session.get(Campaign, campaign_id), db.session.get(Player, player_id)
    if campaign is None or player is None or campaign.owner_id != player.owner_id:
        raise CampaignMismatchError("Jogador e campanha precisam pertencer à mesma conta.")
    membership = CampaignPlayer.query.filter_by(campaign_id=campaign_id, player_id=player_id).first()
    if membership is None:
        membership = CampaignPlayer(campaign_id=campaign_id, player_id=player_id)
        db.session.add(membership)
    elif membership.status != "ativo":
        membership.status = "ativo"
        membership.left_at = None
    return membership


def leave_campaign(membership: CampaignPlayer) -> None:
    membership.status = "saiu"
    membership.left_at = utcnow()


def campaign_players(campaign_id: int, only_active: bool = True):
    q = (
        db.session.query(Player, CampaignPlayer)
        .join(CampaignPlayer, CampaignPlayer.player_id == Player.id)
        .filter(CampaignPlayer.campaign_id == campaign_id)
    )
    if only_active:
        q = q.filter(CampaignPlayer.status == "ativo")
    return q.order_by(Player.display_name).all()


def player_choices_for_campaign(campaign_id: int, include_player_id: int | None = None):
    """Jogadores elegíveis para novos personagens: não arquivados (ou o já associado)."""
    q = my_players().filter((Player.status != "arquivado") | (Player.id == include_player_id))
    return q.order_by(Player.display_name).all()


def character_choices(campaign_id: int, active_only: bool = False):
    q = Character.query.filter_by(campaign_id=campaign_id)
    if active_only:
        q = q.filter(Character.status == "ativo")
    return q.order_by(Character.name).all()

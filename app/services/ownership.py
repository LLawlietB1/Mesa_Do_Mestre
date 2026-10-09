"""Isolamento entre usuários: todo registro pertence a um usuário, direta ou indiretamente (via campanha)."""
from __future__ import annotations

from flask import g

from app.extensions import db
from app.models import (Campaign, CampaignPlayer, CharacterItem, CharacterNPCRelationship, FileAsset, MessageLog,
                        Player, QuestObjective, QuestStatusHistory)

DIRECT = (Campaign, Player, FileAsset, MessageLog)
# Modelos sem campaign_id: o dono vem do "pai".
PARENT_ATTR = {QuestObjective: "quest", QuestStatusHistory: "quest", CharacterNPCRelationship: "npc", CharacterItem: "item"}


def owner_id_of(obj) -> int | None:
    if isinstance(obj, DIRECT):
        return obj.owner_id
    campaign_id = getattr(obj, "campaign_id", None)
    if campaign_id is not None:
        campaign = db.session.get(Campaign, campaign_id)
        return campaign.owner_id if campaign else None
    attr = PARENT_ATTR.get(type(obj))
    if attr:
        return owner_id_of(getattr(obj, attr))
    return None   # tipo desconhecido: nunca autoriza


def is_owned(obj) -> bool:
    user = getattr(g, "user", None)
    return obj is not None and user is not None and owner_id_of(obj) == user.id


def user_id() -> int:
    return g.user.id


def my_campaigns():
    return Campaign.query.filter_by(owner_id=g.user.id)


def my_players():
    return Player.query.filter_by(owner_id=g.user.id)

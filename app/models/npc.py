from sqlalchemy import CheckConstraint, UniqueConstraint

from app.constants import NPC_RELATIONS, NPC_STATUS, in_clause
from app.extensions import db
from app.models.mixins import TimestampMixin


class NPC(TimestampMixin, db.Model):
    __tablename__ = "npcs"
    __table_args__ = (CheckConstraint(in_clause("status", NPC_STATUS), name="ck_npc_status"),)

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    nickname = db.Column(db.String(80))
    description = db.Column(db.Text)
    appearance = db.Column(db.Text)
    personality = db.Column(db.Text)
    goals = db.Column(db.Text)
    motivation = db.Column(db.Text)
    secrets = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="ativo", index=True)
    image = db.Column(db.String(100))
    master_notes = db.Column(db.Text)

    campaign = db.relationship("Campaign", back_populates="npcs")
    relationships = db.relationship(
        "CharacterNPCRelationship", back_populates="npc", cascade="all, delete-orphan", passive_deletes=True,
    )


class CharacterNPCRelationship(db.Model):
    __tablename__ = "character_npc_relationships"
    __table_args__ = (
        UniqueConstraint("character_id", "npc_id", "kind", name="uq_character_npc_kind"),
        CheckConstraint(in_clause("kind", NPC_RELATIONS), name="ck_relationship_kind"),
    )

    id = db.Column(db.Integer, primary_key=True)
    character_id = db.Column(db.Integer, db.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    npc_id = db.Column(db.Integer, db.ForeignKey("npcs.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False, default="neutro")
    description = db.Column(db.String(300))

    character = db.relationship("Character")
    npc = db.relationship("NPC", back_populates="relationships")

from sqlalchemy import CheckConstraint

from app.constants import QUEST_STATUS, in_clause
from app.extensions import db
from app.models.mixins import TimestampMixin, utcnow

# QuestCharacter da especificação = quest_characters
quest_characters = db.Table(
    "quest_characters",
    db.Column("quest_id", db.Integer, db.ForeignKey("quests.id", ondelete="CASCADE"), primary_key=True),
    db.Column("character_id", db.Integer, db.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
)


class Quest(TimestampMixin, db.Model):
    __tablename__ = "quests"
    __table_args__ = (CheckConstraint(in_clause("status", QUEST_STATUS), name="ck_quest_status"),)

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False, index=True)
    description = db.Column(db.Text)
    npc_id = db.Column(db.Integer, db.ForeignKey("npcs.id", ondelete="SET NULL"), index=True)
    rewards = db.Column(db.Text)  # registro administrativo; não altera fichas nem inventários
    deadline = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default="planejada", index=True)
    master_notes = db.Column(db.Text)

    campaign = db.relationship("Campaign", back_populates="quests")
    npc = db.relationship("NPC")
    characters = db.relationship("Character", secondary=quest_characters, order_by="Character.name")
    objectives = db.relationship(
        "QuestObjective", back_populates="quest", cascade="all, delete-orphan",
        passive_deletes=True, order_by="QuestObjective.position, QuestObjective.id",
    )
    status_history = db.relationship(
        "QuestStatusHistory", back_populates="quest", cascade="all, delete-orphan",
        passive_deletes=True, order_by="QuestStatusHistory.id.desc()",
    )


class QuestObjective(db.Model):
    __tablename__ = "quest_objectives"

    id = db.Column(db.Integer, primary_key=True)
    quest_id = db.Column(db.Integer, db.ForeignKey("quests.id", ondelete="CASCADE"), nullable=False, index=True)
    description = db.Column(db.String(300), nullable=False)
    done = db.Column(db.Boolean, nullable=False, default=False)
    position = db.Column(db.Integer, nullable=False, default=0)

    quest = db.relationship("Quest", back_populates="objectives")


class QuestStatusHistory(db.Model):
    __tablename__ = "quest_status_history"

    id = db.Column(db.Integer, primary_key=True)
    quest_id = db.Column(db.Integer, db.ForeignKey("quests.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status = db.Column(db.String(20))
    new_status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    quest = db.relationship("Quest", back_populates="status_history")

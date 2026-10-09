from sqlalchemy import CheckConstraint, UniqueConstraint

from app.constants import SESSION_STATUS, in_clause
from app.extensions import db
from app.models.mixins import TimestampMixin, utcnow

# Associações simples (sem atributos extras). SessionParticipant da especificação = session_participants.
session_participants = db.Table(
    "session_participants",
    db.Column("session_id", db.Integer, db.ForeignKey("game_sessions.id", ondelete="CASCADE"), primary_key=True),
    db.Column("character_id", db.Integer, db.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
)
session_npcs = db.Table(
    "session_npcs",
    db.Column("session_id", db.Integer, db.ForeignKey("game_sessions.id", ondelete="CASCADE"), primary_key=True),
    db.Column("npc_id", db.Integer, db.ForeignKey("npcs.id", ondelete="CASCADE"), primary_key=True),
)
session_quests = db.Table(
    "session_quests",
    db.Column("session_id", db.Integer, db.ForeignKey("game_sessions.id", ondelete="CASCADE"), primary_key=True),
    db.Column("quest_id", db.Integer, db.ForeignKey("quests.id", ondelete="CASCADE"), primary_key=True),
)


class GameSession(TimestampMixin, db.Model):
    __tablename__ = "game_sessions"
    __table_args__ = (
        UniqueConstraint("campaign_id", "number", name="uq_session_campaign_number"),
        CheckConstraint(in_clause("status", SESSION_STATUS), name="ck_session_status"),
        CheckConstraint("number > 0", name="ck_session_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(160), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="agendada", index=True)
    summary = db.Column(db.Text)
    pending = db.Column(db.Text)
    master_notes = db.Column(db.Text)

    campaign = db.relationship("Campaign", back_populates="sessions")
    participants = db.relationship("Character", secondary=session_participants, order_by="Character.name")
    npcs = db.relationship("NPC", secondary=session_npcs, order_by="NPC.name")
    quests = db.relationship("Quest", secondary=session_quests, order_by="Quest.title")
    events = db.relationship(
        "SessionEvent", back_populates="session", cascade="all, delete-orphan",
        passive_deletes=True, order_by="SessionEvent.id",
    )


class SessionEvent(db.Model):
    """Acontecimento importante de uma sessão, opcionalmente ligado a um personagem."""

    __tablename__ = "session_events"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    character_id = db.Column(db.Integer, db.ForeignKey("characters.id", ondelete="SET NULL"), index=True)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    session = db.relationship("GameSession", back_populates="events")
    character = db.relationship("Character")

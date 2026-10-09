from sqlalchemy import CheckConstraint, UniqueConstraint

from app.constants import CAMPAIGN_STATUS, PLAYER_STATUS, in_clause
from app.extensions import db
from app.models.mixins import TimestampMixin, utcnow


class Campaign(TimestampMixin, db.Model):
    __tablename__ = "campaigns"
    __table_args__ = (CheckConstraint(in_clause("status", CAMPAIGN_STATUS), name="ck_campaign_status"),)

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.Text)
    system = db.Column(db.String(80))
    setting = db.Column(db.String(120))
    start_date = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default="planejada", index=True)
    notes = db.Column(db.Text)
    settings = db.Column(db.JSON, nullable=False, default=dict)  # configurações específicas (chave/valor)
    cover_image = db.Column(db.String(100))

    memberships = db.relationship("CampaignPlayer", back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True)
    characters = db.relationship("Character", back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True, order_by="Character.name")
    notes_list = db.relationship("Note", back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True)
    sessions = db.relationship("GameSession", back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True, order_by="GameSession.number")
    npcs = db.relationship("NPC", back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True)
    quests = db.relationship("Quest", back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True)
    items = db.relationship("Item", back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def is_closed(self):
        return self.status == "encerrada"

    def __repr__(self):
        return f"<Campaign {self.id} {self.name!r}>"


class Player(TimestampMixin, db.Model):
    __tablename__ = "players"
    __table_args__ = (CheckConstraint(in_clause("status", PLAYER_STATUS), name="ck_player_status"),)

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False, index=True)
    real_name = db.Column(db.String(120))
    nickname = db.Column(db.String(80))
    email = db.Column(db.String(200))
    phone = db.Column(db.String(20))                     # E.164 (ex.: +5511999998888), opcional
    messaging_consent = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="ativo", index=True)

    memberships = db.relationship("CampaignPlayer", back_populates="player", cascade="all, delete-orphan", passive_deletes=True)
    characters = db.relationship("Character", back_populates="player", order_by="Character.name")

    def __repr__(self):
        return f"<Player {self.id} {self.display_name!r}>"


class CampaignPlayer(db.Model):
    """Participação de um jogador em uma campanha (um jogador pode estar em várias)."""

    __tablename__ = "campaign_players"
    __table_args__ = (
        UniqueConstraint("campaign_id", "player_id", name="uq_campaign_player"),
        CheckConstraint("status IN ('ativo','saiu')", name="ck_campaign_player_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default="ativo")
    joined_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    left_at = db.Column(db.DateTime)

    campaign = db.relationship("Campaign", back_populates="memberships")
    player = db.relationship("Player", back_populates="memberships")

from sqlalchemy import CheckConstraint

from app.constants import CHARACTER_STATUS, XP_ORIGINS, in_clause
from app.extensions import db
from app.models.mixins import TimestampMixin, utcnow


class Character(TimestampMixin, db.Model):
    __tablename__ = "characters"
    __table_args__ = (
        CheckConstraint(in_clause("status", CHARACTER_STATUS), name="ck_character_status"),
        CheckConstraint("xp_percent BETWEEN 0 AND 100", name="ck_character_xp_percent"),
        db.Index("ix_characters_campaign_name", "campaign_id", "name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id", ondelete="RESTRICT"), nullable=False, index=True)
    system = db.Column(db.String(80))
    race = db.Column(db.String(80))
    char_class = db.Column(db.String(80))
    level = db.Column(db.Integer)
    portrait = db.Column(db.String(100))
    backstory = db.Column(db.Text)
    personality = db.Column(db.Text)
    goals = db.Column(db.Text)
    background = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="ativo", index=True)
    master_notes = db.Column(db.Text)
    extra = db.Column(db.JSON, nullable=False, default=dict)  # atributos específicos do sistema (chave/valor)

    # Barra de XP manual (0-100). `xp_points` reserva espaço para XP numérica futura.
    xp_percent = db.Column(db.Integer, nullable=False, default=0)
    xp_cycle = db.Column(db.Integer, nullable=False, default=1)
    xp_points = db.Column(db.Integer)

    campaign = db.relationship("Campaign", back_populates="characters")
    player = db.relationship("Player", back_populates="characters")
    xp_history = db.relationship(
        "ExperienceHistory", back_populates="character", cascade="all, delete-orphan",
        passive_deletes=True, order_by="ExperienceHistory.id.desc()",
    )

    def __repr__(self):
        return f"<Character {self.id} {self.name!r}>"


class ExperienceHistory(db.Model):
    __tablename__ = "experience_history"
    __table_args__ = (
        CheckConstraint("previous_percent BETWEEN 0 AND 100 AND new_percent BETWEEN 0 AND 100", name="ck_xp_history_range"),
        CheckConstraint(in_clause("origin", XP_ORIGINS), name="ck_xp_history_origin"),
    )

    id = db.Column(db.Integer, primary_key=True)
    character_id = db.Column(db.Integer, db.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_percent = db.Column(db.Integer, nullable=False)
    new_percent = db.Column(db.Integer, nullable=False)
    delta = db.Column(db.Integer, nullable=False)              # variação efetivamente aplicada
    requested_delta = db.Column(db.Integer)                    # variação pedida (pode diferir se houve limite)
    cycle = db.Column(db.Integer, nullable=False, default=1)
    reason = db.Column(db.String(300))
    origin = db.Column(db.String(20), nullable=False, default="individual")
    batch_id = db.Column(db.String(36), index=True)            # agrupa alterações coletivas
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    character = db.relationship("Character", back_populates="xp_history")

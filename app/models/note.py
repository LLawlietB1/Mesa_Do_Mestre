from sqlalchemy import CheckConstraint

from app.constants import NOTE_CATEGORIES, in_clause
from app.extensions import db
from app.models.mixins import TimestampMixin


class Note(TimestampMixin, db.Model):
    __tablename__ = "notes"
    __table_args__ = (CheckConstraint(in_clause("category", NOTE_CATEGORIES), name="ck_note_category"),)

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(20), nullable=False, default="outros", index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id", ondelete="SET NULL"), index=True)
    character_id = db.Column(db.Integer, db.ForeignKey("characters.id", ondelete="SET NULL"), index=True)
    important = db.Column(db.Boolean, nullable=False, default=False)
    archived = db.Column(db.Boolean, nullable=False, default=False, index=True)

    campaign = db.relationship("Campaign", back_populates="notes_list")
    player = db.relationship("Player")
    character = db.relationship("Character")

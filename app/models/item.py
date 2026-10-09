from sqlalchemy import CheckConstraint

from app.constants import ITEM_CATEGORIES, in_clause
from app.extensions import db
from app.models.mixins import utcnow


class Item(db.Model):
    """Item/tesouro/moeda registrado na campanha. Quem o possui fica em CharacterItem."""

    __tablename__ = "items"
    __table_args__ = (CheckConstraint(in_clause("category", ITEM_CATEGORIES), name="ck_item_category"),)

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.Text)
    category = db.Column(db.String(20), nullable=False, default="outro", index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    campaign = db.relationship("Campaign", back_populates="items")
    holdings = db.relationship(
        "CharacterItem", back_populates="item", cascade="all, delete-orphan", passive_deletes=True,
    )

    @property
    def total_quantity(self):
        return sum(h.quantity for h in self.holdings)


class CharacterItem(db.Model):
    __tablename__ = "character_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_character_item_quantity"),)

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    character_id = db.Column(db.Integer, db.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    origin = db.Column(db.String(200))
    quest_id = db.Column(db.Integer, db.ForeignKey("quests.id", ondelete="SET NULL"))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    item = db.relationship("Item", back_populates="holdings")
    character = db.relationship("Character")
    quest = db.relationship("Quest")

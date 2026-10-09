from datetime import date

from flask import Blueprint, render_template
from sqlalchemy.orm import selectinload

from app.models import Campaign, CampaignPlayer, Character, GameSession, Note, Player, Quest, SessionEvent
from app.services.campaigns import get_current_campaign
from app.services.ownership import my_campaigns

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    total = my_campaigns().count()
    campaign = get_current_campaign()
    if campaign is None:
        return render_template("dashboard/empty.html")
    cid = campaign.id
    active_players = (
        Player.query.join(CampaignPlayer)
        .filter(CampaignPlayer.campaign_id == cid, CampaignPlayer.status == "ativo", Player.status == "ativo")
        .count()
    )
    party = (Character.query.filter_by(campaign_id=cid, status="ativo").options(selectinload(Character.player))
             .order_by(Character.name).all())
    stats = {
        "campaigns": total,
        "players": active_players,
        "characters": len(party),
        "quests": Quest.query.filter_by(campaign_id=cid, status="em_andamento").count(),
    }
    next_session = (
        GameSession.query.filter(GameSession.campaign_id == cid, GameSession.status == "agendada", GameSession.date >= date.today())
        .order_by(GameSession.date, GameSession.number).first()
    )
    notes = Note.query.filter_by(campaign_id=cid, archived=False).order_by(Note.important.desc(), Note.updated_at.desc()).limit(5).all()
    events = (SessionEvent.query.filter_by(campaign_id=cid).options(selectinload(SessionEvent.session), selectinload(SessionEvent.character))
              .order_by(SessionEvent.id.desc()).limit(6).all())
    return render_template("dashboard/index.html", campaign=campaign, stats=stats, party=party,
                           next_session=next_session, notes=notes, events=events)

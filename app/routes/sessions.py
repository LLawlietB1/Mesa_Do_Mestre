from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.constants import SESSION_STATUS, keys
from app.extensions import db
from app.forms.sessions import SessionEventForm, SessionForm
from app.models import Character, GameSession, NPC, Quest, SessionEvent
from app.routes.helpers import assign, flash_form_errors, get_or_404, require_campaign
from app.services.campaigns import character_choices
from app.services.common import safe_commit
from app.services.integrity import CampaignMismatchError, load_in_campaign
from app.utils import like_pattern

bp = Blueprint("sessions", __name__, url_prefix="/sessoes")


def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


@bp.get("/")
@require_campaign
def index(campaign):
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    d_from = _parse_date(request.args.get("de"))
    d_to = _parse_date(request.args.get("ate"))
    order = request.args.get("ordem", "recentes")
    query = GameSession.query.filter_by(campaign_id=campaign.id)
    if q:
        pat = like_pattern(q)
        query = query.filter(
            GameSession.title.ilike(pat, escape="\\") | GameSession.summary.ilike(pat, escape="\\")
            | GameSession.pending.ilike(pat, escape="\\")
            | GameSession.events.any(SessionEvent.description.ilike(pat, escape="\\"))
        )
    if status in keys(SESSION_STATUS):
        query = query.filter_by(status=status)
    if d_from:
        query = query.filter(GameSession.date >= d_from)
    if d_to:
        query = query.filter(GameSession.date <= d_to)
    sessions = query.order_by(GameSession.number.asc() if order == "antigas" else GameSession.number.desc()).all()
    upcoming = GameSession.query.filter(
        GameSession.campaign_id == campaign.id, GameSession.status == "agendada", GameSession.date >= date.today()
    ).order_by(GameSession.date).all()
    return render_template("sessions/index.html", sessions=sessions, upcoming=upcoming, q=q, status=status,
                           d_from=request.args.get("de", ""), d_to=request.args.get("ate", ""), order=order)


@bp.get("/linha-do-tempo")
@require_campaign
def timeline(campaign):
    sessions = (GameSession.query.filter_by(campaign_id=campaign.id)
                .options(selectinload(GameSession.events).selectinload(SessionEvent.character))
                .order_by(GameSession.date, GameSession.number).all())
    return render_template("sessions/timeline.html", sessions=sessions, today=date.today())


def _form(campaign_id, session=None):
    return SessionForm(
        obj=session, characters=character_choices(campaign_id),
        npcs=NPC.query.filter_by(campaign_id=campaign_id).order_by(NPC.name).all(),
        quests=Quest.query.filter_by(campaign_id=campaign_id).order_by(Quest.title).all(),
    )


def _fill(session, form):
    assign(session, form, ["number", "title", "date", "status", "summary", "pending", "master_notes"])
    cid = session.campaign_id
    session.participants = load_in_campaign(Character, form.participants.data, cid, "personagens")
    session.npcs = load_in_campaign(NPC, form.npcs.data, cid, "NPCs")
    session.quests = load_in_campaign(Quest, form.quests.data, cid, "missões")


def _number_taken(campaign_id, number, exclude_id=None):
    q = GameSession.query.filter_by(campaign_id=campaign_id, number=number)
    if exclude_id:
        q = q.filter(GameSession.id != exclude_id)
    return db.session.query(q.exists()).scalar()


def _save(session, form, is_new):
    if _number_taken(session.campaign_id, form.number.data, None if is_new else session.id):
        form.number.errors.append("Já existe uma sessão com este número nesta campanha.")
        return False
    try:
        _fill(session, form)
    except CampaignMismatchError as exc:
        form.participants.errors.append(str(exc))
        db.session.rollback()
        return False
    if is_new:
        db.session.add(session)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        form.number.errors.append("Já existe uma sessão com este número nesta campanha.")
        return False
    return True


@bp.route("/nova", methods=["GET", "POST"])
@require_campaign
def new(campaign):
    form = _form(campaign.id)
    if request.method == "GET":
        form.number.data = (db.session.query(func.max(GameSession.number)).filter_by(campaign_id=campaign.id).scalar() or 0) + 1
        form.date.data = date.today()
    if form.validate_on_submit():
        session = GameSession(campaign_id=campaign.id)
        if _save(session, form, True):
            flash(f"Sessão {session.number} registrada.", "success")
            return redirect(url_for("sessions.detail", session_id=session.id))
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title="Nova sessão", back_url=url_for("sessions.index"))


@bp.get("/<int:session_id>")
def detail(session_id):
    session = get_or_404(GameSession, session_id)
    event_form = SessionEventForm(characters=character_choices(session.campaign_id))
    events = SessionEvent.query.filter_by(session_id=session.id).options(selectinload(SessionEvent.character)).order_by(SessionEvent.id).all()
    return render_template("sessions/detail.html", session=session, event_form=event_form, events=events)


@bp.route("/<int:session_id>/editar", methods=["GET", "POST"])
def edit(session_id):
    session = get_or_404(GameSession, session_id)
    form = _form(session.campaign_id, session)
    if request.method == "GET":
        form.participants.data = [c.id for c in session.participants]
        form.npcs.data = [n.id for n in session.npcs]
        form.quests.data = [q.id for q in session.quests]
    if form.validate_on_submit():
        if _save(session, form, False):
            flash("Sessão atualizada.", "success")
            return redirect(url_for("sessions.detail", session_id=session.id))
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title=f"Editar sessão {session.number}",
                           back_url=url_for("sessions.detail", session_id=session.id))


@bp.post("/<int:session_id>/excluir")
def delete(session_id):
    session = get_or_404(GameSession, session_id)
    db.session.delete(session)
    flash("Sessão excluída." if safe_commit() else "Não foi possível excluir a sessão.", "success")
    return redirect(url_for("sessions.index"))


@bp.post("/<int:session_id>/acontecimentos")
def add_event(session_id):
    session = get_or_404(GameSession, session_id)
    form = SessionEventForm(characters=character_choices(session.campaign_id))
    if form.validate_on_submit():
        event = SessionEvent(session_id=session.id, campaign_id=session.campaign_id, description=form.description.data.strip())
        try:
            if form.character_id.data:
                (event.character,) = load_in_campaign(Character, [form.character_id.data], session.campaign_id, "personagens")
        except CampaignMismatchError as exc:
            flash(str(exc), "error")
            return redirect(url_for("sessions.detail", session_id=session.id))
        db.session.add(event)
        flash("Acontecimento registrado." if safe_commit() else "Não foi possível registrar.", "success")
    else:
        flash("Descreva o acontecimento (até 2000 caracteres).", "error")
    return redirect(url_for("sessions.detail", session_id=session.id))


@bp.post("/<int:session_id>/acontecimentos/<int:event_id>/excluir")
def delete_event(session_id, event_id):
    get_or_404(GameSession, session_id)
    event = SessionEvent.query.filter_by(id=event_id, session_id=session_id).first_or_404()
    db.session.delete(event)
    flash("Acontecimento removido." if safe_commit() else "Não foi possível remover.", "success")
    return redirect(url_for("sessions.detail", session_id=session_id))

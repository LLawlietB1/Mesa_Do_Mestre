from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.constants import QUEST_STATUS, keys
from app.extensions import db
from app.forms.quests import ObjectiveForm, QuestForm
from app.models import Character, NPC, Quest, QuestObjective, QuestStatusHistory, GameSession
from app.routes.helpers import assign, flash_form_errors, get_or_404, require_campaign, safe_next
from app.services.campaigns import character_choices
from app.services.common import safe_commit
from app.services.integrity import CampaignMismatchError, load_in_campaign
from app.utils import like_pattern

bp = Blueprint("quests", __name__, url_prefix="/missoes")

FIELDS = ["title", "status", "deadline", "description", "rewards", "master_notes"]


@bp.get("/")
@require_campaign
def index(campaign):
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    character_id = request.args.get("personagem", type=int)
    query = Quest.query.filter_by(campaign_id=campaign.id)
    if q:
        pat = like_pattern(q)
        query = query.filter(Quest.title.ilike(pat, escape="\\") | Quest.description.ilike(pat, escape="\\"))
    if status in keys(QUEST_STATUS):
        query = query.filter_by(status=status)
    if character_id:
        query = query.filter(Quest.characters.any(Character.id == character_id))
    quests = query.order_by(Quest.updated_at.desc()).all()
    return render_template("quests/index.html", quests=quests, q=q, status=status, character_id=character_id,
                           characters=character_choices(campaign.id))


def _form(campaign_id, quest=None):
    return QuestForm(obj=quest, npcs=NPC.query.filter_by(campaign_id=campaign_id).order_by(NPC.name).all(),
                     characters=character_choices(campaign_id))


def _fill(quest, form):
    old_status = quest.status
    assign(quest, form, FIELDS)
    cid = quest.campaign_id
    npc_id = form.npc_id.data or None
    if npc_id:
        (npc,) = load_in_campaign(NPC, [npc_id], cid, "NPCs")
        quest.npc = npc
    else:
        quest.npc = None
    quest.characters = load_in_campaign(Character, form.characters.data, cid, "personagens")
    return old_status


@bp.route("/nova", methods=["GET", "POST"])
@require_campaign
def new(campaign):
    form = _form(campaign.id)
    if form.validate_on_submit():
        quest = Quest(campaign_id=campaign.id)
        try:
            _fill(quest, form)
        except CampaignMismatchError as exc:
            db.session.rollback()
            form.characters.errors.append(str(exc))
        else:
            quest.status_history.append(QuestStatusHistory(old_status=None, new_status=quest.status))
            db.session.add(quest)
            if safe_commit():
                flash(f"Missão «{quest.title}» criada.", "success")
                return redirect(url_for("quests.detail", quest_id=quest.id))
            flash("Não foi possível salvar a missão.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title="Nova missão", back_url=url_for("quests.index"))


@bp.get("/<int:quest_id>")
def detail(quest_id):
    quest = get_or_404(Quest, quest_id)
    sessions = GameSession.query.filter(GameSession.quests.any(Quest.id == quest.id)).order_by(GameSession.number.desc()).all()
    return render_template("quests/detail.html", quest=quest, objective_form=ObjectiveForm(), sessions=sessions)


@bp.route("/<int:quest_id>/editar", methods=["GET", "POST"])
def edit(quest_id):
    quest = get_or_404(Quest, quest_id)
    form = _form(quest.campaign_id, quest)
    if request.method == "GET":
        form.characters.data = [c.id for c in quest.characters]
        form.npc_id.data = quest.npc_id or 0
    if form.validate_on_submit():
        try:
            old = _fill(quest, form)
        except CampaignMismatchError as exc:
            db.session.rollback()
            form.characters.errors.append(str(exc))
        else:
            if quest.status != old:
                quest.status_history.append(QuestStatusHistory(old_status=old, new_status=quest.status))
            if safe_commit():
                flash("Missão atualizada.", "success")
                return redirect(url_for("quests.detail", quest_id=quest.id))
            flash("Não foi possível salvar as alterações.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title=f"Editar missão — {quest.title}",
                           back_url=url_for("quests.detail", quest_id=quest.id))


@bp.post("/<int:quest_id>/status")
def set_status(quest_id):
    quest = get_or_404(Quest, quest_id)
    status = request.form.get("status", "")
    if status not in keys(QUEST_STATUS):
        flash("Status inválido.", "error")
    elif status != quest.status:
        quest.status_history.append(QuestStatusHistory(old_status=quest.status, new_status=status))
        quest.status = status
        flash("Status atualizado." if safe_commit() else "Não foi possível atualizar.", "success")
    return redirect(safe_next(url_for("quests.detail", quest_id=quest.id)))


@bp.post("/<int:quest_id>/excluir")
def delete(quest_id):
    quest = get_or_404(Quest, quest_id)
    db.session.delete(quest)
    if safe_commit():
        flash("Missão excluída.", "success")
        return redirect(url_for("quests.index"))
    flash("Não foi possível excluir a missão.", "error")
    return redirect(url_for("quests.detail", quest_id=quest_id))


@bp.post("/<int:quest_id>/objetivos")
def add_objective(quest_id):
    quest = get_or_404(Quest, quest_id)
    form = ObjectiveForm()
    if form.validate_on_submit():
        position = max((o.position for o in quest.objectives), default=0) + 1
        quest.objectives.append(QuestObjective(description=form.description.data.strip(), position=position))
        flash("Objetivo adicionado." if safe_commit() else "Não foi possível adicionar.", "success")
    else:
        flash("Descreva o objetivo (até 300 caracteres).", "error")
    return redirect(url_for("quests.detail", quest_id=quest.id))


@bp.post("/<int:quest_id>/objetivos/<int:objective_id>/alternar")
def toggle_objective(quest_id, objective_id):
    get_or_404(Quest, quest_id)
    objective = QuestObjective.query.filter_by(id=objective_id, quest_id=quest_id).first_or_404()
    objective.done = not objective.done
    if not safe_commit():
        flash("Não foi possível atualizar o objetivo.", "error")
    return redirect(url_for("quests.detail", quest_id=quest_id))


@bp.post("/<int:quest_id>/objetivos/<int:objective_id>/excluir")
def delete_objective(quest_id, objective_id):
    get_or_404(Quest, quest_id)
    objective = QuestObjective.query.filter_by(id=objective_id, quest_id=quest_id).first_or_404()
    db.session.delete(objective)
    flash("Objetivo removido." if safe_commit() else "Não foi possível remover.", "success")
    return redirect(url_for("quests.detail", quest_id=quest_id))

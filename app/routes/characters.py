from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload, selectinload

from app.constants import CHARACTER_STATUS, keys
from app.extensions import db
from app.forms.characters import CharacterForm
from app.models import Character, CharacterItem, ExperienceHistory, CharacterNPCRelationship, GameSession, Note, Player, Quest
from app.models.session import session_participants
from app.routes.helpers import assign, finalize_images, flash_form_errors, get_or_404, require_campaign
from app.services.campaigns import enroll_player, player_choices_for_campaign
from app.services.common import safe_commit
from app.services.uploads import UploadError, apply_image, delete_image
from app.utils import format_kv_lines, like_pattern, parse_kv_lines

bp = Blueprint("characters", __name__, url_prefix="/personagens")

FIELDS = ["name", "player_id", "status", "system", "race", "char_class", "level", "backstory",
          "personality", "goals", "background", "master_notes"]
SORTS = {"nome": Character.name, "xp": Character.xp_percent.desc(), "nivel": Character.level.desc(), "recentes": Character.id.desc()}


@bp.get("/")
@require_campaign
def index(campaign):
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    player_id = request.args.get("jogador", type=int)
    sort = request.args.get("ordem", "nome")
    query = Character.query.filter_by(campaign_id=campaign.id)
    if q:
        query = query.filter(Character.name.ilike(like_pattern(q), escape="\\"))
    if status in keys(CHARACTER_STATUS):
        query = query.filter_by(status=status)
    if player_id:
        query = query.filter_by(player_id=player_id)
    characters = query.options(selectinload(Character.player)).order_by(SORTS.get(sort, Character.name), Character.name).all()
    players = Player.query.join(Character).filter(Character.campaign_id == campaign.id).distinct().order_by(Player.display_name).all()
    return render_template("characters/index.html", characters=characters, players=players, q=q, status=status,
                           player_id=player_id, sort=sort)


def _form(campaign_id, character=None):
    players = player_choices_for_campaign(campaign_id, character.player_id if character else None)
    return CharacterForm(obj=character, players=players)


@bp.route("/novo", methods=["GET", "POST"])
@require_campaign
def new(campaign):
    form = _form(campaign.id)
    back = url_for("characters.index")
    if not form.player_id.choices[1:]:
        flash("Cadastre um jogador antes de criar personagens.", "info")
        return redirect(url_for("players.new"))
    if request.method == "GET":
        form.system.data = campaign.system
    if form.validate_on_submit():
        character = Character(campaign_id=campaign.id)
        assign(character, form, FIELDS)
        character.extra = parse_kv_lines(form.extra_text.data)
        try:
            character.portrait, _ = apply_image(form.portrait.data, None)
        except UploadError as exc:
            form.portrait.errors.append(str(exc))
            return render_template("form.html", form=form, title="Novo personagem", back_url=back, multipart=True)
        db.session.add(character)
        enroll_player(campaign.id, character.player_id)  # o responsável passa a participar da campanha
        ok = safe_commit()
        finalize_images(ok, created=[character.portrait])
        if ok:
            flash(f"Personagem «{character.name}» criado.", "success")
            return redirect(url_for("characters.detail", character_id=character.id))
        flash("Não foi possível salvar o personagem.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title=f"Novo personagem — {campaign.name}", back_url=back, multipart=True,
                           intro="Raça, classe, nível e atributos são opcionais e podem ser adaptados ao sistema da campanha.")


@bp.get("/<int:character_id>")
def detail(character_id):
    character = get_or_404(Character, character_id)
    cid = character.id
    return render_template(
        "characters/detail.html", character=character,
        history=ExperienceHistory.query.filter_by(character_id=cid).order_by(ExperienceHistory.id.desc()).limit(8).all(),
        notes=Note.query.filter_by(character_id=cid, archived=False).order_by(Note.updated_at.desc()).limit(5).all(),
        items=CharacterItem.query.filter_by(character_id=cid).options(joinedload(CharacterItem.item)).all(),
        quests=Quest.query.filter(Quest.characters.any(Character.id == cid)).order_by(Quest.title).all(),
        relations=CharacterNPCRelationship.query.filter_by(character_id=cid).options(joinedload(CharacterNPCRelationship.npc)).all(),
        sessions=GameSession.query.filter(GameSession.participants.any(Character.id == cid)).order_by(GameSession.number.desc()).limit(8).all(),
    )


@bp.route("/<int:character_id>/editar", methods=["GET", "POST"])
def edit(character_id):
    character = get_or_404(Character, character_id)
    form = _form(character.campaign_id, character)
    back = url_for("characters.detail", character_id=character.id)
    if request.method == "GET":
        form.extra_text.data = format_kv_lines(character.extra)
    if form.validate_on_submit():
        current = character.portrait
        assign(character, form, FIELDS)
        character.extra = parse_kv_lines(form.extra_text.data)
        try:
            new_img, old_img = apply_image(form.portrait.data, current)
        except UploadError as exc:
            db.session.rollback()
            form.portrait.errors.append(str(exc))
            return render_template("form.html", form=form, title="Editar personagem", back_url=back, multipart=True)
        character.portrait = new_img
        enroll_player(character.campaign_id, character.player_id)
        ok = safe_commit()
        finalize_images(ok, created=[new_img] if new_img != current else [], obsolete=[old_img])
        if ok:
            flash("Personagem atualizado.", "success")
            return redirect(back)
        flash("Não foi possível salvar as alterações.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title=f"Editar personagem — {character.name}", back_url=back, multipart=True)


@bp.post("/<int:character_id>/status")
def set_status(character_id):
    character = get_or_404(Character, character_id)
    status = request.form.get("status", "")
    if status not in keys(CHARACTER_STATUS):
        flash("Status inválido.", "error")
    else:
        character.status = status
        flash("Status atualizado; o histórico foi preservado." if safe_commit() else "Não foi possível atualizar.", "success")
    return redirect(url_for("characters.detail", character_id=character.id))


@bp.post("/<int:character_id>/excluir")
def delete(character_id):
    character = get_or_404(Character, character_id)
    name, portrait = character.name, character.portrait
    db.session.delete(character)
    if safe_commit():
        delete_image(portrait)
        flash(f"Personagem «{name}» e seu histórico de XP foram excluídos.", "success")
        return redirect(url_for("characters.index"))
    flash("Não foi possível excluir o personagem.", "error")
    return redirect(url_for("characters.detail", character_id=character_id))

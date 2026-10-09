from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.constants import NPC_STATUS, keys
from app.extensions import db
from app.forms.npcs import NPCForm, RelationshipForm
from app.models import Character, CharacterNPCRelationship, GameSession, NPC, Quest
from app.routes.helpers import assign, finalize_images, flash_form_errors, get_or_404, require_campaign
from app.services.campaigns import character_choices
from app.services.common import safe_commit
from app.services.integrity import CampaignMismatchError, load_in_campaign
from app.services.uploads import UploadError, apply_image, delete_image
from app.utils import like_pattern

bp = Blueprint("npcs", __name__, url_prefix="/npcs")

FIELDS = ["name", "nickname", "status", "description", "appearance", "personality", "goals", "motivation",
          "secrets", "master_notes"]


@bp.get("/")
@require_campaign
def index(campaign):
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    query = NPC.query.filter_by(campaign_id=campaign.id)
    if q:
        pat = like_pattern(q)
        query = query.filter(NPC.name.ilike(pat, escape="\\") | NPC.nickname.ilike(pat, escape="\\") | NPC.description.ilike(pat, escape="\\"))
    if status in keys(NPC_STATUS):
        query = query.filter_by(status=status)
    return render_template("npcs/index.html", npcs=query.order_by(NPC.name).all(), q=q, status=status)


@bp.route("/novo", methods=["GET", "POST"])
@require_campaign
def new(campaign):
    form = NPCForm()
    back = url_for("npcs.index")
    if form.validate_on_submit():
        npc = NPC(campaign_id=campaign.id)
        assign(npc, form, FIELDS)
        try:
            npc.image, _ = apply_image(form.image.data, None)
        except UploadError as exc:
            form.image.errors.append(str(exc))
            return render_template("form.html", form=form, title="Novo NPC", back_url=back, multipart=True)
        db.session.add(npc)
        ok = safe_commit()
        finalize_images(ok, created=[npc.image])
        if ok:
            flash(f"NPC «{npc.name}» cadastrado.", "success")
            return redirect(url_for("npcs.detail", npc_id=npc.id))
        flash("Não foi possível salvar o NPC.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title="Novo NPC", back_url=back, multipart=True,
                           intro="Registre o NPC agora; você decide depois como ele entra na história.")


@bp.get("/<int:npc_id>")
def detail(npc_id):
    npc = get_or_404(NPC, npc_id)
    rel_form = RelationshipForm(characters=character_choices(npc.campaign_id))
    sessions = GameSession.query.filter(GameSession.npcs.any(NPC.id == npc.id)).order_by(GameSession.number.desc()).all()
    quests = Quest.query.filter((Quest.npc_id == npc.id)).order_by(Quest.title).all()
    relationships = (CharacterNPCRelationship.query.filter_by(npc_id=npc.id)
                     .options(joinedload(CharacterNPCRelationship.character)).order_by(CharacterNPCRelationship.id).all())
    return render_template("npcs/detail.html", npc=npc, rel_form=rel_form, sessions=sessions, quests=quests, relationships=relationships)


@bp.route("/<int:npc_id>/editar", methods=["GET", "POST"])
def edit(npc_id):
    npc = get_or_404(NPC, npc_id)
    form = NPCForm(obj=npc)
    back = url_for("npcs.detail", npc_id=npc.id)
    if form.validate_on_submit():
        current = npc.image
        assign(npc, form, FIELDS)
        try:
            new_img, old_img = apply_image(form.image.data, current)
        except UploadError as exc:
            db.session.rollback()
            form.image.errors.append(str(exc))
            return render_template("form.html", form=form, title="Editar NPC", back_url=back, multipart=True)
        npc.image = new_img
        ok = safe_commit()
        finalize_images(ok, created=[new_img] if new_img != current else [], obsolete=[old_img])
        if ok:
            flash("NPC atualizado.", "success")
            return redirect(back)
        flash("Não foi possível salvar as alterações.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title=f"Editar NPC — {npc.name}", back_url=back, multipart=True)


@bp.post("/<int:npc_id>/excluir")
def delete(npc_id):
    npc = get_or_404(NPC, npc_id)
    name, image = npc.name, npc.image
    db.session.delete(npc)
    if safe_commit():
        delete_image(image)
        flash(f"NPC «{name}» excluído.", "success")
        return redirect(url_for("npcs.index"))
    flash("Não foi possível excluir o NPC.", "error")
    return redirect(url_for("npcs.detail", npc_id=npc_id))


@bp.post("/<int:npc_id>/relacoes")
def add_relationship(npc_id):
    npc = get_or_404(NPC, npc_id)
    form = RelationshipForm(characters=character_choices(npc.campaign_id))
    if form.validate_on_submit():
        try:
            (character,) = load_in_campaign(Character, [form.character_id.data], npc.campaign_id, "personagens")
        except CampaignMismatchError as exc:
            flash(str(exc), "error")
        else:
            db.session.add(CharacterNPCRelationship(
                character_id=character.id, npc_id=npc.id, kind=form.kind.data,
                description=(form.description.data or "").strip() or None,
            ))
            try:
                db.session.commit()
                flash("Relação registrada.", "success")
            except IntegrityError:
                db.session.rollback()
                flash("Essa relação já está registrada.", "error")
    else:
        flash("Selecione o personagem e o tipo de relação.", "error")
    return redirect(url_for("npcs.detail", npc_id=npc.id))


@bp.post("/<int:npc_id>/relacoes/<int:rel_id>/excluir")
def delete_relationship(npc_id, rel_id):
    get_or_404(NPC, npc_id)
    rel = CharacterNPCRelationship.query.filter_by(id=rel_id, npc_id=npc_id).first_or_404()
    db.session.delete(rel)
    flash("Relação removida." if safe_commit() else "Não foi possível remover.", "success")
    return redirect(url_for("npcs.detail", npc_id=npc_id))

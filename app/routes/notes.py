from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.constants import NOTE_CATEGORIES, keys
from app.extensions import db
from app.forms.notes import NoteForm
from app.models import Campaign, Character, Note, Player
from app.routes.helpers import assign, flash_form_errors, get_or_404, require_campaign, safe_next
from app.services.campaigns import character_choices
from app.services.common import safe_commit
from app.services.ownership import my_players
from app.services.integrity import CampaignMismatchError, load_in_campaign
from app.utils import like_pattern

bp = Blueprint("notes", __name__, url_prefix="/notas")

ORDER = {
    "recentes": (Note.updated_at.desc(),), "antigas": (Note.updated_at.asc(),),
    "criacao": (Note.created_at.desc(),), "titulo": (Note.title,),
}


@bp.get("/")
@require_campaign
def index(campaign):
    q = request.args.get("q", "").strip()
    category = request.args.get("categoria", "")
    scope = request.args.get("campanha", "")          # "" = campanha atual, "todas" ou id
    character_id = request.args.get("personagem", type=int)
    archived = request.args.get("arquivadas", "nao")  # nao | sim | todas
    order = request.args.get("ordem", "recentes")
    query = Note.query.join(Campaign, Campaign.id == Note.campaign_id).filter(Campaign.owner_id == g.user.id)
    if scope == "todas":
        pass
    elif scope.isdigit():
        query = query.filter(Note.campaign_id == int(scope))
    else:
        query = query.filter(Note.campaign_id == campaign.id)
    if q:
        pat = like_pattern(q)
        query = query.filter(Note.title.ilike(pat, escape="\\") | Note.content.ilike(pat, escape="\\"))
    if category in keys(NOTE_CATEGORIES):
        query = query.filter(Note.category == category)
    if character_id:
        query = query.filter(Note.character_id == character_id)
    if archived == "nao":
        query = query.filter(Note.archived.is_(False))
    elif archived == "sim":
        query = query.filter(Note.archived.is_(True))
    notes = query.order_by(Note.important.desc(), *ORDER.get(order, ORDER["recentes"])).all()
    return render_template(
        "notes/index.html", notes=notes, q=q, category=category, scope=scope, character_id=character_id,
        archived=archived, order=order, characters=character_choices(campaign.id),
    )


def _form(campaign_id, note=None):
    return NoteForm(obj=note, characters=character_choices(campaign_id), players=my_players().order_by(Player.display_name).all())


def _fill(note, form):
    """Aplica o formulário validando que o personagem pertence à campanha da nota."""
    assign(note, form, ["title", "content", "category", "important", "archived"])
    character_id = form.character_id.data or None
    if character_id:
        (character,) = load_in_campaign(Character, [character_id], note.campaign_id, "personagens")
        note.character_id, note.player_id = character.id, character.player_id
    else:
        note.character_id, note.player_id = None, form.player_id.data or None


@bp.route("/nova", methods=["GET", "POST"])
@require_campaign
def new(campaign):
    form = _form(campaign.id)
    if request.method == "GET":
        form.character_id.data = request.args.get("personagem", type=int) or 0
    if form.validate_on_submit():
        note = Note(campaign_id=campaign.id)
        try:
            _fill(note, form)
        except CampaignMismatchError as exc:
            form.character_id.errors.append(str(exc))
        else:
            db.session.add(note)
            if safe_commit():
                flash("Nota criada.", "success")
                return redirect(url_for("notes.index"))
            flash("Não foi possível salvar a nota.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title="Nova nota privada", back_url=url_for("notes.index"),
                           intro="Notas ficam visíveis apenas para você, dentro do sistema.")


@bp.route("/<int:note_id>/editar", methods=["GET", "POST"])
def edit(note_id):
    note = get_or_404(Note, note_id)
    form = _form(note.campaign_id, note)
    if form.validate_on_submit():
        try:
            _fill(note, form)
        except CampaignMismatchError as exc:
            form.character_id.errors.append(str(exc))
        else:
            if safe_commit():
                flash("Nota atualizada.", "success")
                return redirect(url_for("notes.index"))
            flash("Não foi possível salvar as alterações.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title="Editar nota", back_url=url_for("notes.index"))


@bp.post("/<int:note_id>/alternar/<string:flag>")
def toggle(note_id, flag):
    note = get_or_404(Note, note_id)
    if flag not in ("important", "archived"):
        flash("Ação inválida.", "error")
    else:
        setattr(note, flag, not getattr(note, flag))
        if not safe_commit():
            flash("Não foi possível atualizar a nota.", "error")
    return redirect(safe_next(url_for("notes.index")))


@bp.post("/<int:note_id>/excluir")
def delete(note_id):
    note = get_or_404(Note, note_id)
    db.session.delete(note)
    flash("Nota excluída." if safe_commit() else "Não foi possível excluir a nota.", "success")
    return redirect(url_for("notes.index"))

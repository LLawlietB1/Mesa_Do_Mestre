from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload, selectinload

from app.constants import ITEM_CATEGORIES, keys
from app.extensions import db
from app.forms.items import HoldingForm, ItemCreateForm, ItemForm
from app.models import Character, CharacterItem, Item, Quest
from app.routes.helpers import assign, flash_form_errors, get_or_404, require_campaign
from app.services.campaigns import character_choices
from app.services.common import safe_commit
from app.services.integrity import CampaignMismatchError, load_in_campaign
from app.utils import like_pattern

bp = Blueprint("items", __name__, url_prefix="/itens")


def _quests(campaign_id):
    return Quest.query.filter_by(campaign_id=campaign_id).order_by(Quest.title).all()


@bp.get("/")
@require_campaign
def index(campaign):
    q = request.args.get("q", "").strip()
    category = request.args.get("categoria", "")
    character_id = request.args.get("personagem", type=int)
    query = Item.query.filter_by(campaign_id=campaign.id)
    if q:
        pat = like_pattern(q)
        query = query.filter(Item.name.ilike(pat, escape="\\") | Item.description.ilike(pat, escape="\\"))
    if category in keys(ITEM_CATEGORIES):
        query = query.filter_by(category=category)
    if character_id:
        query = query.filter(Item.holdings.any(CharacterItem.character_id == character_id))
    return render_template("items/index.html", items=query.options(selectinload(Item.holdings).selectinload(CharacterItem.character)).order_by(Item.name).all(), q=q, category=category,
                           character_id=character_id, characters=character_choices(campaign.id))


def _add_holding(item, character_id, quantity, origin, quest_id, notes):
    (character,) = load_in_campaign(Character, [character_id], item.campaign_id, "personagens")
    quest = None
    if quest_id:
        (quest,) = load_in_campaign(Quest, [quest_id], item.campaign_id, "missões")
    item.holdings.append(CharacterItem(
        character=character, quantity=quantity, origin=(origin or "").strip() or None,
        quest=quest, notes=(notes or "").strip() or None,
    ))


@bp.route("/novo", methods=["GET", "POST"])
@require_campaign
def new(campaign):
    form = ItemCreateForm(characters=character_choices(campaign.id), quests=_quests(campaign.id))
    if form.validate_on_submit():
        item = Item(campaign_id=campaign.id)
        assign(item, form, ["name", "category", "description", "notes"])
        try:
            if form.character_id.data:
                _add_holding(item, form.character_id.data, form.quantity.data, form.origin.data, form.quest_id.data, None)
        except CampaignMismatchError as exc:
            db.session.rollback()
            form.character_id.errors.append(str(exc))
        else:
            db.session.add(item)
            if safe_commit():
                flash(f"Item «{item.name}» registrado.", "success")
                return redirect(url_for("items.detail", item_id=item.id))
            flash("Não foi possível salvar o item.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title="Novo item", back_url=url_for("items.index"),
                           intro="Moedas, tesouros, equipamentos e itens especiais. A quantidade só vale se você escolher um personagem.")


@bp.get("/<int:item_id>")
def detail(item_id):
    item = get_or_404(Item, item_id)
    form = HoldingForm(characters=character_choices(item.campaign_id), quests=_quests(item.campaign_id))
    holdings = (CharacterItem.query.filter_by(item_id=item.id)
                .options(joinedload(CharacterItem.character), joinedload(CharacterItem.quest)).order_by(CharacterItem.id).all())
    return render_template("items/detail.html", item=item, holding_form=form, holdings=holdings)


@bp.route("/<int:item_id>/editar", methods=["GET", "POST"])
def edit(item_id):
    item = get_or_404(Item, item_id)
    form = ItemForm(obj=item)
    if form.validate_on_submit():
        assign(item, form, ["name", "category", "description", "notes"])
        if safe_commit():
            flash("Item atualizado.", "success")
            return redirect(url_for("items.detail", item_id=item.id))
        flash("Não foi possível salvar as alterações.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title=f"Editar item — {item.name}",
                           back_url=url_for("items.detail", item_id=item.id))


@bp.post("/<int:item_id>/excluir")
def delete(item_id):
    item = get_or_404(Item, item_id)
    db.session.delete(item)
    if safe_commit():
        flash("Item excluído.", "success")
        return redirect(url_for("items.index"))
    flash("Não foi possível excluir o item.", "error")
    return redirect(url_for("items.detail", item_id=item_id))


@bp.post("/<int:item_id>/posses")
def add_holding(item_id):
    item = get_or_404(Item, item_id)
    form = HoldingForm(characters=character_choices(item.campaign_id), quests=_quests(item.campaign_id))
    if form.validate_on_submit():
        try:
            _add_holding(item, form.character_id.data, form.quantity.data, form.origin.data, form.quest_id.data, form.notes.data)
        except CampaignMismatchError as exc:
            db.session.rollback()
            flash(str(exc), "error")
        else:
            flash("Item atribuído ao personagem." if safe_commit() else "Não foi possível atribuir.", "success")
    else:
        flash("; ".join(e for errs in form.errors.values() for e in errs) or "Dados inválidos.", "error")
    return redirect(url_for("items.detail", item_id=item.id))


@bp.post("/<int:item_id>/posses/<int:holding_id>/excluir")
def delete_holding(item_id, holding_id):
    get_or_404(Item, item_id)
    holding = CharacterItem.query.filter_by(id=holding_id, item_id=item_id).first_or_404()
    db.session.delete(holding)
    flash("Posse removida." if safe_commit() else "Não foi possível remover.", "success")
    return redirect(url_for("items.detail", item_id=item_id))

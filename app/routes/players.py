from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.constants import PLAYER_STATUS, keys
from app.extensions import db
from app.forms.campaigns import PlayerForm
from app.models import Campaign, CampaignPlayer, Player
from app.routes.helpers import assign, flash_form_errors, get_or_404
from app.services.common import safe_commit
from app.services.messaging import normalize_phone
from app.services.ownership import my_players
from app.utils import like_pattern

bp = Blueprint("players", __name__, url_prefix="/jogadores")

FIELDS = ["display_name", "real_name", "nickname", "email", "status", "notes"]


def _apply_contact(player, form):
    phone = (form.phone.data or "").strip()
    player.phone = normalize_phone(phone) if phone else None
    player.messaging_consent = bool(form.messaging_consent.data and player.phone)


@bp.get("/")
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    campaign_id = request.args.get("campanha", type=int)
    query = my_players()
    if q:
        pat = like_pattern(q)
        query = query.filter(Player.display_name.ilike(pat, escape="\\") | Player.nickname.ilike(pat, escape="\\") | Player.real_name.ilike(pat, escape="\\"))
    if status in keys(PLAYER_STATUS):
        query = query.filter_by(status=status)
    if campaign_id:
        query = query.join(CampaignPlayer).filter(CampaignPlayer.campaign_id == campaign_id, CampaignPlayer.status == "ativo")
    players = query.order_by(Player.display_name).all()
    return render_template("players/index.html", players=players, q=q, status=status, campaign_id=campaign_id)


@bp.route("/novo", methods=["GET", "POST"])
def new():
    form = PlayerForm()
    if form.validate_on_submit():
        player = Player(owner_id=g.user.id)
        assign(player, form, FIELDS)
        _apply_contact(player, form)
        db.session.add(player)
        if safe_commit():
            flash(f"Jogador «{player.display_name}» cadastrado.", "success")
            return redirect(url_for("players.detail", player_id=player.id))
        flash("Não foi possível salvar o jogador.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title="Novo jogador", back_url=url_for("players.index"),
                           intro="Apenas o nome de exibição é obrigatório. Dados de contato são opcionais.")


@bp.get("/<int:player_id>")
def detail(player_id):
    player = get_or_404(Player, player_id)
    memberships = (
        CampaignPlayer.query.filter_by(player_id=player.id).join(Campaign).order_by(CampaignPlayer.joined_at.desc()).all()
    )
    return render_template("players/detail.html", player=player, memberships=memberships)


@bp.route("/<int:player_id>/editar", methods=["GET", "POST"])
def edit(player_id):
    player = get_or_404(Player, player_id)
    form = PlayerForm(obj=player)
    if form.validate_on_submit():
        assign(player, form, FIELDS)
        _apply_contact(player, form)
        if safe_commit():
            flash("Jogador atualizado.", "success")
            return redirect(url_for("players.detail", player_id=player.id))
        flash("Não foi possível salvar as alterações.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template("form.html", form=form, title=f"Editar jogador — {player.display_name}",
                           back_url=url_for("players.detail", player_id=player.id))


@bp.post("/<int:player_id>/status")
def set_status(player_id):
    player = get_or_404(Player, player_id)
    status = request.form.get("status", "")
    if status not in keys(PLAYER_STATUS):
        flash("Status inválido.", "error")
    else:
        player.status = status
        flash("Status atualizado." if safe_commit() else "Não foi possível atualizar.", "success")
    return redirect(url_for("players.detail", player_id=player.id))


@bp.post("/<int:player_id>/excluir")
def delete(player_id):
    player = get_or_404(Player, player_id)
    if player.characters:
        flash("Este jogador possui personagens e não pode ser excluído. Arquive-o para preservar o histórico.", "error")
        return redirect(url_for("players.detail", player_id=player.id))
    name = player.display_name
    db.session.delete(player)
    if safe_commit():
        flash(f"Jogador «{name}» excluído.", "success")
        return redirect(url_for("players.index"))
    flash("Não foi possível excluir o jogador.", "error")
    return redirect(url_for("players.detail", player_id=player_id))

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func

from app.constants import CAMPAIGN_STATUS, keys
from app.extensions import db
from app.forms.campaigns import AddPlayerToCampaignForm, CampaignForm
from app.models import Campaign, CampaignPlayer, Character, GameSession, NPC, Player, Quest
from app.routes.helpers import assign, finalize_images, flash_form_errors, get_or_404, safe_next
from app.services.campaigns import campaign_players, enroll_player, leave_campaign, set_current_campaign
from app.services.common import safe_commit
from app.services.ownership import my_campaigns, my_players
from app.services.uploads import UploadError, apply_image, delete_image
from app.utils import format_kv_lines, like_pattern, parse_kv_lines

bp = Blueprint("campaigns", __name__, url_prefix="/campanhas")

FIELDS = ["name", "status", "system", "setting", "start_date", "description", "notes"]


@bp.get("/")
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    query = my_campaigns()
    if q:
        query = query.filter(Campaign.name.ilike(like_pattern(q), escape="\\"))
    if status in keys(CAMPAIGN_STATUS):
        query = query.filter_by(status=status)
    campaigns = query.order_by(Campaign.status == "encerrada", Campaign.name).all()
    counts = {
        cid: n for cid, n in db.session.query(Character.campaign_id, func.count(Character.id))
        .join(Campaign, Campaign.id == Character.campaign_id).filter(Campaign.owner_id == g.user.id)
        .group_by(Character.campaign_id)
    }
    return render_template("campaigns/index.html", campaigns=campaigns, q=q, status=status, char_counts=counts)


@bp.route("/nova", methods=["GET", "POST"])
def new():
    form = CampaignForm()
    if form.validate_on_submit():
        campaign = Campaign(owner_id=g.user.id)
        assign(campaign, form, FIELDS)
        campaign.settings = parse_kv_lines(form.settings_text.data)
        created = None
        try:
            campaign.cover_image, _ = apply_image(form.cover.data, None)
            created = campaign.cover_image
        except UploadError as exc:
            form.cover.errors.append(str(exc))
            return render_template("form.html", form=form, title="Nova campanha", back_url=url_for("campaigns.index"), multipart=True)
        db.session.add(campaign)
        ok = safe_commit()
        finalize_images(ok, created=[created])
        if ok:
            set_current_campaign(campaign)
            flash(f"Campanha «{campaign.name}» criada e selecionada.", "success")
            return redirect(url_for("campaigns.detail", campaign_id=campaign.id))
        flash("Não foi possível salvar a campanha.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template(
        "form.html", form=form, title="Nova campanha", back_url=url_for("campaigns.index"), multipart=True,
        intro="Cada campanha é independente: jogadores, personagens, notas, sessões, NPCs, missões e itens ficam separados.",
    )


@bp.get("/<int:campaign_id>")
def detail(campaign_id):
    campaign = get_or_404(Campaign, campaign_id)
    members = campaign_players(campaign.id, only_active=False)
    member_ids = {p.id for p, _ in members}
    available = [p for p in my_players().filter(Player.status != "arquivado").order_by(Player.display_name) if p.id not in member_ids]
    add_form = AddPlayerToCampaignForm(available=available)
    stats = {
        "characters": Character.query.filter_by(campaign_id=campaign.id).count(),
        "sessions": GameSession.query.filter_by(campaign_id=campaign.id).count(),
        "quests": Quest.query.filter_by(campaign_id=campaign.id).count(),
        "npcs": NPC.query.filter_by(campaign_id=campaign.id).count(),
    }
    recent_sessions = GameSession.query.filter_by(campaign_id=campaign.id).order_by(GameSession.date.desc(), GameSession.number.desc()).limit(5).all()
    return render_template(
        "campaigns/detail.html", campaign=campaign, members=members, add_form=add_form,
        characters=campaign.characters, stats=stats, recent_sessions=recent_sessions, has_available=bool(available),
    )


@bp.route("/<int:campaign_id>/editar", methods=["GET", "POST"])
def edit(campaign_id):
    campaign = get_or_404(Campaign, campaign_id)
    form = CampaignForm(obj=campaign)
    if request.method == "GET":
        form.settings_text.data = format_kv_lines(campaign.settings)
    if form.validate_on_submit():
        assign(campaign, form, FIELDS)
        campaign.settings = parse_kv_lines(form.settings_text.data)
        current = campaign.cover_image
        try:
            new_cover, old_cover = apply_image(form.cover.data, current)
        except UploadError as exc:
            db.session.rollback()
            form.cover.errors.append(str(exc))
            return render_template("form.html", form=form, title="Editar campanha", back_url=url_for("campaigns.detail", campaign_id=campaign.id), multipart=True)
        campaign.cover_image = new_cover
        ok = safe_commit()
        uploaded = new_cover != current
        finalize_images(ok, created=[new_cover] if uploaded else [], obsolete=[old_cover])
        if ok:
            flash("Campanha atualizada.", "success")
            return redirect(url_for("campaigns.detail", campaign_id=campaign.id))
        flash("Não foi possível salvar as alterações.", "error")
    elif form.is_submitted():
        flash_form_errors()
    return render_template(
        "form.html", form=form, title=f"Editar campanha — {campaign.name}",
        back_url=url_for("campaigns.detail", campaign_id=campaign.id), multipart=True,
    )


@bp.post("/selecionar")
def select():
    campaign = get_or_404(Campaign, request.form.get("campaign_id", type=int))
    set_current_campaign(campaign)
    return redirect(safe_next(url_for("dashboard.index")))


@bp.post("/<int:campaign_id>/status")
def set_status(campaign_id):
    campaign = get_or_404(Campaign, campaign_id)
    status = request.form.get("status", "")
    if status not in keys(CAMPAIGN_STATUS):
        flash("Status inválido.", "error")
    else:
        campaign.status = status
        if safe_commit():
            flash(f"Campanha marcada como «{dict(CAMPAIGN_STATUS)[status]}». Os registros foram preservados.", "success")
        else:
            flash("Não foi possível alterar o status.", "error")
    return redirect(url_for("campaigns.detail", campaign_id=campaign.id))


@bp.post("/<int:campaign_id>/excluir")
def delete(campaign_id):
    campaign = get_or_404(Campaign, campaign_id)
    if request.form.get("confirm_name", "").strip() != campaign.name:
        flash("Para excluir definitivamente, digite o nome exato da campanha.", "error")
        return redirect(url_for("campaigns.detail", campaign_id=campaign.id))
    images = [campaign.cover_image] + [c.portrait for c in campaign.characters] + [n.image for n in campaign.npcs]
    name = campaign.name
    db.session.delete(campaign)
    if safe_commit():
        for img in images:
            delete_image(img)
        flash(f"Campanha «{name}» e todos os seus registros foram excluídos.", "success")
        return redirect(url_for("campaigns.index"))
    flash("Não foi possível excluir a campanha.", "error")
    return redirect(url_for("campaigns.detail", campaign_id=campaign_id))


@bp.post("/<int:campaign_id>/jogadores")
def add_player(campaign_id):
    campaign = get_or_404(Campaign, campaign_id)
    available = my_players().filter(Player.status != "arquivado").all()
    form = AddPlayerToCampaignForm(available=available)
    if form.validate_on_submit():
        enroll_player(campaign.id, form.player_id.data)
        flash("Jogador adicionado à campanha." if safe_commit() else "Não foi possível adicionar o jogador.", "success")
    else:
        flash("Selecione um jogador válido.", "error")
    return redirect(url_for("campaigns.detail", campaign_id=campaign.id))


@bp.post("/<int:campaign_id>/jogadores/<int:player_id>/remover")
def remove_player(campaign_id, player_id):
    get_or_404(Campaign, campaign_id)             # confere que a campanha é sua
    membership = CampaignPlayer.query.filter_by(campaign_id=campaign_id, player_id=player_id).first_or_404()
    leave_campaign(membership)
    flash("Participação encerrada (o histórico e os personagens foram mantidos)." if safe_commit() else "Não foi possível atualizar.", "success")
    return redirect(url_for("campaigns.detail", campaign_id=campaign_id))

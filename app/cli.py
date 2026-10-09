"""Comandos `flask ...` auxiliares."""
import click

from app.extensions import db


def register_cli(app):
    def _user(email):
        from app.models import User

        user = User.query.filter_by(email=email.strip().lower()).first()
        if user is None:
            raise click.ClickException(f"Nenhum usuário com o e-mail {email}.")
        return user

    @app.cli.command("list-users")
    def list_users():
        """Lista as contas cadastradas."""
        from app.models import User

        for u in User.query.order_by(User.id):
            click.echo(f"{u.id}\t{u.email}\t{u.name}\tmensagens={'sim' if u.can_send_messages else 'não'}")

    @app.cli.command("grant-messaging")
    @click.argument("email")
    @click.option("--revoke", is_flag=True, help="Remove a liberação.")
    def grant_messaging(email, revoke):
        """Libera (ou revoga) o envio de mensagens pelo servidor (Twilio) para uma conta."""
        user = _user(email)
        user.can_send_messages = not revoke
        db.session.commit()
        click.echo(f"Envio pelo servidor {'revogado' if revoke else 'liberado'} para {user.email}.")

    @app.cli.command("seed-demo")
    @click.argument("email")
    @click.option("--yes", is_flag=True, help="Confirma a criação de dados de demonstração.")
    def seed_demo(email, yes):
        """OPCIONAL: cria uma campanha de demonstração (marcada «[Demo]») na conta informada."""
        from datetime import date, timedelta

        from app.models import Campaign, Character, GameSession, NPC, Player, Quest
        from app.services.campaigns import enroll_player

        user = _user(email)
        if not yes:
            click.echo("Use --yes para criar a campanha de demonstração.")
            return
        campaign = Campaign(owner_id=user.id, name="[Demo] Campanha de exemplo", status="ativa", system="Sistema livre")
        player = Player(owner_id=user.id, display_name="[Demo] Jogador")
        db.session.add_all([campaign, player])
        db.session.flush()
        enroll_player(campaign.id, player.id)
        db.session.add_all([
            Character(name="[Demo] Personagem", campaign_id=campaign.id, player_id=player.id, xp_percent=40),
            NPC(name="[Demo] NPC", campaign_id=campaign.id),
            Quest(title="[Demo] Missão", campaign_id=campaign.id, status="em_andamento"),
            GameSession(campaign_id=campaign.id, number=1, title="[Demo] Primeira sessão",
                        date=date.today() + timedelta(days=7)),
        ])
        db.session.commit()
        click.echo("Dados de demonstração criados. Exclua a campanha «[Demo]» quando quiser.")

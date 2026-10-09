from sqlalchemy import CheckConstraint

from app.extensions import db
from app.models.mixins import TimestampMixin, utcnow


class User(TimestampMixin, db.Model):
    """Conta de um mestre. Todos os dados de negócio pertencem a um usuário (isolamento total)."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('MESTRE','ADMIN')", name="ck_user_role"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    recovery_hash = db.Column(db.String(255))          # palavra-chave de recuperação (hash)
    role = db.Column(db.String(10), nullable=False, default="MESTRE")
    failed_logins = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)
    # Envio de mensagens pelo servidor consome crédito do provedor: liberado manualmente (flask grant-messaging).
    can_send_messages = db.Column(db.Boolean, nullable=False, default=False)

    sessions = db.relationship("UserSession", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class UserSession(db.Model):
    """Sessão de login. Só o hash SHA-256 do token é guardado: ler o banco não permite forjar o cookie."""

    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    ip = db.Column(db.String(64))
    user_agent = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="sessions")


class FileAsset(db.Model):
    """Imagem enviada (retrato, capa, NPC). Guardada no banco e servida só pelo dono, em /media/<id>."""

    __tablename__ = "file_assets"

    id = db.Column(db.String(32), primary_key=True)    # uuid4 hex gerado no servidor
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content_type = db.Column(db.String(40), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    data = db.deferred(db.Column(db.LargeBinary, nullable=False))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class MessageLog(db.Model):
    """Registro de mensagens enviadas pelo servidor (sem o texto: só metadados)."""

    __tablename__ = "message_logs"
    __table_args__ = (CheckConstraint("channel IN ('sms','whatsapp')", name="ck_message_channel"),)

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id", ondelete="SET NULL"), index=True)
    channel = db.Column(db.String(10), nullable=False)
    ok = db.Column(db.Boolean, nullable=False)
    provider_id = db.Column(db.String(64))
    error = db.Column(db.String(300))
    chars = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

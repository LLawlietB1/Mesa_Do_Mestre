"""Configuração da aplicação (desenvolvimento, produção/Vercel e testes)."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


def _sqlite_uri(path: Path) -> str:
    return "sqlite:///" + str(path).replace("\\", "/")


def normalize_database_url(url: str) -> str:
    """Aceita postgres://, postgresql:// (Neon/Vercel) e converte para o driver psycopg 3."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def database_url() -> str:
    raw = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    return normalize_database_url(raw) if raw else _sqlite_uri(INSTANCE_DIR / "mesa.sqlite3")


def engine_options(url: str) -> dict:
    if url.startswith("postgresql"):
        return {
            # Instâncias "quentes" da Vercel atendem várias requisições: reaproveitar a conexão evita o custo de
            # TLS + autenticação (centenas de ms) em cada página. pre_ping/recycle descartam conexões que o
            # Neon suspendeu por inatividade.
            "pool_size": 1, "max_overflow": 2, "pool_pre_ping": True, "pool_recycle": 240,
            # pgbouncer em modo transação não suporta prepared statements automáticos do psycopg 3.
            "connect_args": {"prepare_threshold": None, "connect_timeout": 10},
        }
    return {}


def _load_dev_secret_key() -> str:
    """Só desenvolvimento: chave local persistente quando SECRET_KEY não está definida."""
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    key_file = INSTANCE_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


def env_name() -> str:
    """Na Vercel (variável VERCEL=1) o ambiente é sempre produção."""
    if os.environ.get("VERCEL"):
        return "production"
    return os.environ.get("MESA_ENV", "development")


class Config:
    DEBUG = False
    TESTING = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = None
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024        # a Vercel limita o corpo de requisições a ~4,5 MB
    MAX_IMAGE_BYTES = 3 * 1024 * 1024           # imagem enviada (é reduzida/recodificada ao salvar)
    USER_IMAGE_QUOTA_BYTES = int(os.environ.get("USER_IMAGE_QUOTA_MB", "3")) * 1024 * 1024
    SESSION_DAYS = 14
    MAX_FAILED_LOGINS = 5
    LOCK_MINUTES = 10
    INVITE_CODE = os.environ.get("INVITE_CODE", "")
    ALLOW_OPEN_REGISTRATION = os.environ.get("ALLOW_OPEN_REGISTRATION") == "1"
    # Envio de mensagens pelo servidor (opcional; os links de WhatsApp/SMS não precisam disso)
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_SMS_FROM = os.environ.get("TWILIO_SMS_FROM", "")
    TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")
    MESSAGES_PER_DAY = int(os.environ.get("MESSAGES_PER_DAY", "30"))
    DEFAULT_COUNTRY_CODE = os.environ.get("DEFAULT_COUNTRY_CODE", "55")
    COOKIE_SECURE = False
    # E-mail de aviso ao administrador (Resend). Sem domínio verificado, o Resend só envia para o e-mail da
    # própria conta Resend: use esse mesmo e-mail em ADMIN_EMAIL.
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RESEND_FROM = os.environ.get("RESEND_FROM", "Mesa do Mestre <onboarding@resend.dev>")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
    IMAGE_REQUEST_COOLDOWN_MIN = 30
    # Vercel Blob (arquivos privados). Criar um Blob store na aba Storage do projeto preenche esta variável.
    BLOB_READ_WRITE_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")

    def __init__(self):
        url = database_url()
        self.SQLALCHEMY_DATABASE_URI = url
        self.SQLALCHEMY_ENGINE_OPTIONS = engine_options(url)


class DevelopmentConfig(Config):
    DEBUG = True
    ALLOW_OPEN_REGISTRATION = True      # local: cadastro livre (em produção exige INVITE_CODE)

    def __init__(self):
        super().__init__()
        self.SECRET_KEY = os.environ.get("SECRET_KEY") or _load_dev_secret_key()


class ProductionConfig(Config):
    COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

    def __init__(self):
        super().__init__()
        key = os.environ.get("SECRET_KEY")
        self.SECRET_KEY = key or secrets.token_hex(32)       # chave efêmera: o app não serve nada sem a real
        self.CONFIG_ERROR = "" if key else (
            "A variável de ambiente SECRET_KEY não está definida. Gere uma com "
            "python -c \"import secrets; print(secrets.token_hex(32))\" e adicione em Settings → Environment Variables (Production).")


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "testing-secret"
    WTF_CSRF_ENABLED = False
    ALLOW_OPEN_REGISTRATION = True
    INVITE_CODE = ""
    TWILIO_ACCOUNT_SID = TWILIO_AUTH_TOKEN = TWILIO_SMS_FROM = TWILIO_WHATSAPP_FROM = ""
    RESEND_API_KEY = ADMIN_EMAIL = ""
    BLOB_READ_WRITE_TOKEN = ""

    def __init__(self):
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = "sqlite://"
        self.SQLALCHEMY_ENGINE_OPTIONS = {}


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}

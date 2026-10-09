from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField

from app.forms.base import BaseForm


class BackupForm(BaseForm):
    """Só carrega o token CSRF."""


class RestoreForm(BaseForm):
    backup_file = FileField("Arquivo de backup (.zip)", validators=[FileRequired("Selecione um arquivo."), FileAllowed(["zip"], "Envie um arquivo .zip.")])
    confirm = BooleanField("Entendo que TODOS os meus dados atuais serão substituídos e que baixei um backup recente antes.")

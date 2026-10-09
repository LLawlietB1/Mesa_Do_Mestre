from wtforms import PasswordField, StringField
from wtforms.validators import EqualTo

from app.forms.base import BaseForm, maxlen, optional, required


class LoginForm(BaseForm):
    email = StringField("E-mail", validators=[required(), maxlen(200)], render_kw={"autocomplete": "username", "inputmode": "email"})
    password = PasswordField("Senha", validators=[required(), maxlen(200)], render_kw={"autocomplete": "current-password"})


class RegisterForm(BaseForm):
    name = StringField("Seu nome", validators=[required(), maxlen(120)], render_kw={"autocomplete": "name"})
    email = StringField("E-mail", validators=[required(), maxlen(200)], render_kw={"autocomplete": "username", "inputmode": "email"})
    password = PasswordField("Senha", validators=[required(), maxlen(200)], description="Mínimo de 8 caracteres, com letras e números.", render_kw={"autocomplete": "new-password"})
    confirm = PasswordField("Confirmar senha", validators=[required(), EqualTo("password", "As senhas não conferem.")], render_kw={"autocomplete": "new-password"})
    passphrase = StringField(
        "Palavra-chave de recuperação", validators=[required(), maxlen(200)], render_kw={"autocomplete": "off"},
        description="Não há recuperação por e-mail: guarde esta palavra (mín. 6 caracteres). Ela redefine sua senha.",
    )
    invite_code = StringField("Código de convite", validators=[optional(), maxlen(100)], render_kw={"autocomplete": "off"})


class ResetForm(BaseForm):
    email = StringField("E-mail", validators=[required(), maxlen(200)], render_kw={"autocomplete": "username", "inputmode": "email"})
    passphrase = StringField("Palavra-chave de recuperação", validators=[required(), maxlen(200)], render_kw={"autocomplete": "off"})
    password = PasswordField("Nova senha", validators=[required(), maxlen(200)], description="Mínimo de 8 caracteres, com letras e números.", render_kw={"autocomplete": "new-password"})
    confirm = PasswordField("Confirmar nova senha", validators=[required(), EqualTo("password", "As senhas não conferem.")], render_kw={"autocomplete": "new-password"})


class ChangePasswordForm(BaseForm):
    current = PasswordField("Senha atual", validators=[required(), maxlen(200)], render_kw={"autocomplete": "current-password"})
    password = PasswordField("Nova senha", validators=[required(), maxlen(200)], render_kw={"autocomplete": "new-password"})
    confirm = PasswordField("Confirmar nova senha", validators=[required(), EqualTo("password", "As senhas não conferem.")], render_kw={"autocomplete": "new-password"})


class RecoveryForm(BaseForm):
    current = PasswordField("Senha atual", validators=[required(), maxlen(200)], render_kw={"autocomplete": "current-password"})
    passphrase = StringField("Nova palavra-chave de recuperação", validators=[required(), maxlen(200)], render_kw={"autocomplete": "off"})


class DeleteAccountForm(BaseForm):
    current = PasswordField("Senha atual", validators=[required(), maxlen(200)], render_kw={"autocomplete": "current-password"})
    confirm_text = StringField("Digite EXCLUIR para confirmar", validators=[required(), maxlen(20)], render_kw={"autocomplete": "off"})

from wtforms import BooleanField, DateField, SelectField, StringField, TextAreaField, ValidationError
from wtforms.validators import Email

from app.constants import CAMPAIGN_STATUS, PLAYER_STATUS
from app.forms.base import (BaseForm, FileField, OptionalIntSelect, image_check, kv_check, maxlen,
                            optional, required, set_choices)


class CampaignForm(BaseForm):
    name = StringField("Nome da campanha", validators=[required(), maxlen(120)])
    status = SelectField("Status", choices=CAMPAIGN_STATUS, default="planejada")
    system = StringField("Sistema de RPG", validators=[optional(), maxlen(80)])
    setting = StringField("Ambientação", validators=[optional(), maxlen(120)])
    start_date = DateField("Data de início", validators=[optional()])
    description = TextAreaField("Descrição", validators=[optional(), maxlen(5000)])
    notes = TextAreaField("Observações gerais", validators=[optional(), maxlen(10000)])
    settings_text = TextAreaField(
        "Configurações específicas", validators=[optional(), kv_check],
        description="Uma por linha, no formato «chave: valor» (ex.: Marco de XP: a cada 3 sessões).",
    )
    cover = FileField("Imagem de capa", validators=[image_check], description="PNG, JPG, GIF ou WEBP, até 2 MB.")


class PlayerForm(BaseForm):
    display_name = StringField("Nome de exibição", validators=[required(), maxlen(120)])
    real_name = StringField("Nome real (opcional)", validators=[optional(), maxlen(120)])
    nickname = StringField("Apelido (opcional)", validators=[optional(), maxlen(80)])
    email = StringField(
        "E-mail (opcional)",
        validators=[optional(), maxlen(200), Email(message="E-mail inválido.", check_deliverability=False)],
    )
    phone = StringField(
        "Telefone / WhatsApp (opcional)", validators=[optional(), maxlen(30)], render_kw={"inputmode": "tel", "autocomplete": "off"},
        description="Com DDD (ex.: 11 99999-8888). Usado só para você enviar mensagens a este jogador.",
    )
    messaging_consent = BooleanField("O jogador concordou em receber mensagens da mesa neste telefone")
    status = SelectField("Status", choices=PLAYER_STATUS, default="ativo")
    notes = TextAreaField("Observações administrativas", validators=[optional(), maxlen(5000)])


    def validate_phone(self, field):
        from app.services.messaging import PhoneError, normalize_phone

        if (field.data or "").strip():
            try:
                normalize_phone(field.data)
            except PhoneError as exc:
                raise ValidationError(str(exc)) from None


class AddPlayerToCampaignForm(BaseForm):
    player_id = OptionalIntSelect("Jogador", validators=[required("Selecione um jogador.")])

    def __init__(self, *args, available=(), **kwargs):
        super().__init__(*args, **kwargs)
        set_choices(self.player_id, [(p.id, p.display_name) for p in available], "Selecione…")

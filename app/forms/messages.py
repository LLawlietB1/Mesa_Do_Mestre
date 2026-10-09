from wtforms import SelectField, TextAreaField

from app.forms.base import BaseForm, IntMultiSelect, maxlen, optional
from app.services.messaging import KINDS


class MessageForm(BaseForm):
    kind = SelectField("O que enviar", choices=KINDS, default="personagem")
    extra = TextAreaField(
        "Texto adicional (opcional)", validators=[optional(), maxlen(800)],
        description="Aceita {jogador} e {campanha}. Em «Mensagem livre» este é o texto principal.",
    )
    recipients = IntMultiSelect("Destinatários")

    def __init__(self, *args, players=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.recipients.choices = [(p.id, p.display_name) for p in players]

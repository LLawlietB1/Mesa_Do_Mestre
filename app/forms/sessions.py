from wtforms import DateField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import NumberRange

from app.constants import SESSION_STATUS
from app.forms.base import BaseForm, IntMultiSelect, OptionalIntSelect, maxlen, required, set_choices


class SessionForm(BaseForm):
    number = IntegerField("Nº da sessão", validators=[required("Informe o número."), NumberRange(1, 9999, "Use um número entre 1 e 9999.")])
    title = StringField("Título", validators=[required(), maxlen(160)])
    date = DateField("Data", validators=[required("Informe a data da sessão.")])
    status = SelectField("Status", choices=SESSION_STATUS, default="agendada")
    summary = TextAreaField("Resumo", validators=[maxlen(20000)])
    pending = TextAreaField("Pendências para a próxima sessão", validators=[maxlen(10000)])
    master_notes = TextAreaField("Observações privadas do mestre", validators=[maxlen(10000)])
    participants = IntMultiSelect("Personagens participantes")
    npcs = IntMultiSelect("NPCs envolvidos")
    quests = IntMultiSelect("Missões relacionadas")

    def __init__(self, *args, characters=(), npcs=(), quests=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.participants.choices = [(c.id, c.name) for c in characters]
        self.npcs.choices = [(n.id, n.name) for n in npcs]
        self.quests.choices = [(q.id, q.title) for q in quests]


class SessionEventForm(BaseForm):
    description = TextAreaField("Acontecimento", validators=[required("Descreva o acontecimento."), maxlen(2000)])
    character_id = OptionalIntSelect("Personagem relacionado")

    def __init__(self, *args, characters=(), **kwargs):
        super().__init__(*args, **kwargs)
        set_choices(self.character_id, [(c.id, c.name) for c in characters], "— ninguém em especial —")

from wtforms import DateField, SelectField, StringField, TextAreaField

from app.constants import QUEST_STATUS
from app.forms.base import BaseForm, IntMultiSelect, OptionalIntSelect, maxlen, optional, required, set_choices


class QuestForm(BaseForm):
    title = StringField("Título", validators=[required(), maxlen(160)])
    status = SelectField("Status", choices=QUEST_STATUS, default="planejada")
    npc_id = OptionalIntSelect("NPC responsável / relacionado")
    deadline = DateField("Prazo (opcional)", validators=[optional()])
    characters = IntMultiSelect("Personagens relacionados")
    description = TextAreaField("Descrição", validators=[optional(), maxlen(10000)])
    rewards = TextAreaField(
        "Recompensas previstas", validators=[optional(), maxlen(5000)],
        description="Apenas registro: não altera fichas nem inventários.",
    )
    master_notes = TextAreaField("Observações privadas", validators=[optional(), maxlen(10000)])

    def __init__(self, *args, npcs=(), characters=(), **kwargs):
        super().__init__(*args, **kwargs)
        set_choices(self.npc_id, [(n.id, n.name) for n in npcs], "— nenhum —")
        self.characters.choices = [(c.id, c.name) for c in characters]


class ObjectiveForm(BaseForm):
    description = StringField("Novo objetivo", validators=[required("Descreva o objetivo."), maxlen(300)])

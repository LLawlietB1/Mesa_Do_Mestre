from wtforms import SelectField, StringField, TextAreaField

from app.constants import NPC_RELATIONS, NPC_STATUS
from app.forms.base import BaseForm, FileField, OptionalIntSelect, image_check, maxlen, optional, required, set_choices


class NPCForm(BaseForm):
    name = StringField("Nome", validators=[required(), maxlen(120)])
    nickname = StringField("Apelido", validators=[optional(), maxlen(80)])
    status = SelectField("Status", choices=NPC_STATUS, default="ativo")
    image = FileField("Imagem", validators=[image_check], description="PNG, JPG, GIF ou WEBP, até 2 MB.")
    description = TextAreaField("Descrição", validators=[optional(), maxlen(5000)])
    appearance = TextAreaField("Aparência", validators=[optional(), maxlen(5000)])
    personality = TextAreaField("Personalidade", validators=[optional(), maxlen(5000)])
    goals = TextAreaField("Objetivos", validators=[optional(), maxlen(5000)])
    motivation = TextAreaField("Motivação", validators=[optional(), maxlen(5000)])
    secrets = TextAreaField("Segredos", validators=[optional(), maxlen(5000)])
    master_notes = TextAreaField("Observações privadas", validators=[optional(), maxlen(10000)])


class RelationshipForm(BaseForm):
    character_id = OptionalIntSelect("Personagem", validators=[required("Selecione o personagem.")])
    kind = SelectField("Tipo de relação", choices=NPC_RELATIONS, default="neutro")
    description = StringField("Detalhes", validators=[optional(), maxlen(300)])

    def __init__(self, *args, characters=(), **kwargs):
        super().__init__(*args, **kwargs)
        set_choices(self.character_id, [(c.id, c.name) for c in characters], "Selecione…")

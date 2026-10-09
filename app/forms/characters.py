from wtforms import IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import NumberRange

from app.constants import CHARACTER_STATUS
from app.forms.base import (BaseForm, FileField, OptionalIntSelect, image_check, kv_check, maxlen,
                            optional, required, set_choices)


class CharacterForm(BaseForm):
    name = StringField("Nome do personagem", validators=[required(), maxlen(120)])
    player_id = OptionalIntSelect("Jogador responsável", validators=[required("Selecione o jogador responsável.")])
    status = SelectField("Status", choices=CHARACTER_STATUS, default="ativo")
    system = StringField("Sistema de RPG", validators=[optional(), maxlen(80)])
    race = StringField("Raça / espécie", validators=[optional(), maxlen(80)])
    char_class = StringField("Classe / arquétipo", validators=[optional(), maxlen(80)])
    level = IntegerField(
        "Nível", validators=[optional(), NumberRange(0, 999, "O nível deve estar entre 0 e 999.")],
        description="Opcional e sempre alterado manualmente.",
    )
    portrait = FileField("Retrato", validators=[image_check], description="PNG, JPG, GIF ou WEBP, até 2 MB.")
    backstory = TextAreaField("História", validators=[optional(), maxlen(10000)])
    personality = TextAreaField("Personalidade", validators=[optional(), maxlen(5000)])
    goals = TextAreaField("Objetivos", validators=[optional(), maxlen(5000)])
    background = TextAreaField("Antecedentes", validators=[optional(), maxlen(5000)])
    master_notes = TextAreaField("Observações do mestre", validators=[optional(), maxlen(10000)])
    extra_text = TextAreaField(
        "Atributos / campos do sistema", validators=[optional(), kv_check],
        description="Uma por linha, «chave: valor» (ex.: Força: 14). Adapte ao sistema da campanha.",
    )

    def __init__(self, *args, players=(), **kwargs):
        super().__init__(*args, **kwargs)
        set_choices(self.player_id, [(p.id, p.display_name) for p in players], "Selecione…")

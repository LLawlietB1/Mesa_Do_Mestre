from wtforms import BooleanField, SelectField, StringField, TextAreaField

from app.constants import NOTE_CATEGORIES
from app.forms.base import BaseForm, OptionalIntSelect, maxlen, required, set_choices


class NoteForm(BaseForm):
    title = StringField("Título", validators=[required(), maxlen(160)])
    category = SelectField("Categoria", choices=NOTE_CATEGORIES, default="outros")
    character_id = OptionalIntSelect("Personagem relacionado")
    player_id = OptionalIntSelect("Jogador relacionado", description="Se escolher um personagem, o jogador responsável é usado.")
    content = TextAreaField("Conteúdo", validators=[required(), maxlen(20000)])
    important = BooleanField("Marcar como importante")
    archived = BooleanField("Arquivada")

    def __init__(self, *args, characters=(), players=(), **kwargs):
        super().__init__(*args, **kwargs)
        set_choices(self.character_id, [(c.id, c.name) for c in characters], "— nenhum —")
        set_choices(self.player_id, [(p.id, p.display_name) for p in players], "— nenhum —")

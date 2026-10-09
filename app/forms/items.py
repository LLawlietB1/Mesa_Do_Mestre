from wtforms import IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import NumberRange

from app.constants import ITEM_CATEGORIES
from app.forms.base import BaseForm, OptionalIntSelect, maxlen, optional, required, set_choices


class ItemForm(BaseForm):
    name = StringField("Nome do item", validators=[required(), maxlen(120)])
    category = SelectField("Categoria", choices=ITEM_CATEGORIES, default="outro")
    description = TextAreaField("Descrição", validators=[optional(), maxlen(5000)])
    notes = TextAreaField("Observações", validators=[optional(), maxlen(5000)])


class HoldingForm(BaseForm):
    """Atribuição de uma quantidade do item a um personagem."""

    character_id = OptionalIntSelect("Personagem possuidor", validators=[required("Selecione o personagem.")])
    quantity = IntegerField("Quantidade", default=1, validators=[required("Informe a quantidade."), NumberRange(1, 1_000_000, "A quantidade deve ser maior que zero.")])
    origin = StringField("Origem / recompensa", validators=[optional(), maxlen(200)])
    quest_id = OptionalIntSelect("Missão relacionada")
    notes = TextAreaField("Observações", validators=[optional(), maxlen(2000)])

    def __init__(self, *args, characters=(), quests=(), **kwargs):
        super().__init__(*args, **kwargs)
        set_choices(self.character_id, [(c.id, c.name) for c in characters], "Selecione…")
        set_choices(self.quest_id, [(q.id, q.title) for q in quests], "— nenhuma —")


class ItemCreateForm(ItemForm, HoldingForm):
    """Cria o item e, opcionalmente, já atribui a um personagem."""

    character_id = OptionalIntSelect("Personagem possuidor (opcional)", description="Deixe em branco para um item do grupo / sem dono.")

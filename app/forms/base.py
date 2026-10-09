"""Base dos formulários e helpers de validação em português."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import SelectField, SelectMultipleField, ValidationError
from wtforms.validators import DataRequired, Length, Optional

from app.services.uploads import UploadError, validate_image
from app.utils import parse_kv_lines


class BaseForm(FlaskForm):
    class Meta:
        locales = ["pt"]


def required(msg="Campo obrigatório."):
    return DataRequired(message=msg)


def maxlen(n):
    return Length(max=n, message=f"Use no máximo {n} caracteres.")


def optional():
    return Optional()


def image_check(_form, field):
    """Valida tipo, extensão e tamanho da imagem enviada (se houver)."""
    storage = field.data
    if storage is None or not getattr(storage, "filename", ""):
        return
    try:
        validate_image(storage)
    except UploadError as exc:
        raise ValidationError(str(exc)) from None


def kv_check(_form, field):
    try:
        parse_kv_lines(field.data)
    except ValueError as exc:
        raise ValidationError(str(exc)) from None


def set_choices(field, pairs, blank=None):
    """Define as opções de um select. `blank` adiciona a opção vazia (valor 0)."""
    choices = [(0, blank)] if blank else []
    field.choices = choices + list(pairs)


class OptionalIntSelect(SelectField):
    """Select de ids que aceita 0 como «nenhum»."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("coerce", int)
        kwargs.setdefault("default", 0)
        super().__init__(*args, **kwargs)


class IntMultiSelect(SelectMultipleField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("coerce", int)
        super().__init__(*args, **kwargs)


__all__ = [
    "BaseForm", "FileField", "OptionalIntSelect", "IntMultiSelect", "required", "maxlen", "optional",
    "image_check", "kv_check", "set_choices",
]

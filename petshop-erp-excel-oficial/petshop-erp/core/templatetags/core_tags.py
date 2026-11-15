from django import template

from core.mixins import eh_administrador as _eh_administrador
from core.utils import moeda as _moeda

register = template.Library()


@register.filter
def eh_administrador(usuario):
    """Uso: {% if user|eh_administrador %}"""
    return _eh_administrador(usuario)


@register.filter
def moeda(valor):
    """Uso: {{ valor|moeda }}  ->  R$ 1.234,56"""
    return _moeda(valor)
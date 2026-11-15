from decimal import Decimal

from django.utils.formats import number_format


def moeda(valor):
    """Formata um valor como moeda brasileira, por exemplo: R$ 1.234,56."""
    if valor is None:
        return "-"
    return "R$ " + number_format(Decimal(valor), decimal_pos=2, force_grouping=True)
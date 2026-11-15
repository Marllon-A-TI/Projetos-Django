"""
Formulários e campos reutilizáveis por todos os apps.
"""

from django import forms
from django.contrib.auth import get_user_model


class DateInput(forms.DateInput):
    """Campo de data nativo do navegador (type=date)."""

    input_type = "date"

    def __init__(self, attrs=None, format=None):
        super().__init__(attrs=attrs, format=format or "%Y-%m-%d")


def aplicar_classe_bootstrap(widget):
    """Aplica a classe CSS do Bootstrap 5 adequada ao tipo do widget."""
    if widget.is_hidden:
        return

    if isinstance(
        widget,
        (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple),
    ):
        classe = "form-check-input"
    elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
        classe = "form-select"
    else:
        classe = "form-control"

    existentes = widget.attrs.get("class", "")
    if classe not in existentes.split():
        widget.attrs["class"] = f"{existentes} {classe}".strip()


class BootstrapFormMixin:
    """
    Estiliza todos os campos com Bootstrap 5 e marca com `is-invalid`
    os campos que tiveram erro de validação.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            aplicar_classe_bootstrap(campo.widget)

    def full_clean(self):
        super().full_clean()
        for nome in self._errors or {}:
            campo = self.fields.get(nome)
            if campo is None or campo.widget.is_hidden:
                continue
            existentes = campo.widget.attrs.get("class", "")
            if "is-invalid" not in existentes.split():
                campo.widget.attrs["class"] = f"{existentes} is-invalid".strip()


class UsuarioChoiceField(forms.ModelChoiceField):
    """Seleção de usuário mostrando o nome completo (ou o login)."""

    def __init__(self, queryset=None, **kwargs):
        if queryset is None:
            queryset = get_user_model().objects.order_by("first_name", "username")
        kwargs.setdefault("label", "Usuário")
        super().__init__(queryset, **kwargs)

    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.get_username()


class PeriodoForm(BootstrapFormMixin, forms.Form):
    """Base de filtros com data inicial e final (ambas opcionais)."""

    data_inicial = forms.DateField(label="De", required=False, widget=DateInput())
    data_final = forms.DateField(label="Até", required=False, widget=DateInput())

    def clean(self):
        dados = super().clean()
        inicial = dados.get("data_inicial")
        final = dados.get("data_final")
        if inicial and final and inicial > final:
            self.add_error(
                "data_final", "A data final não pode ser anterior à data inicial."
            )
        return dados

    def filtrar_periodo(self, queryset, campo):
        """
        Aplica o período ao queryset.
        Use campo="data" para DateField e campo="data__date" para DateTimeField.
        Só deve ser chamado depois de is_valid().
        """
        inicial = self.cleaned_data.get("data_inicial")
        final = self.cleaned_data.get("data_final")
        if inicial:
            queryset = queryset.filter(**{f"{campo}__gte": inicial})
        if final:
            queryset = queryset.filter(**{f"{campo}__lte": final})
        return queryset
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory

from core.forms import (
    BootstrapFormMixin,
    PeriodoForm,
    UsuarioChoiceField,
    aplicar_classe_bootstrap,
)
from produtos.forms import ProdutoChoiceField


class ItemVendaForm(BootstrapFormMixin, forms.Form):
    produto = ProdutoChoiceField()
    quantidade = forms.IntegerField(label="Quantidade", min_value=1, initial=1)
    preco = forms.DecimalField(
        label="Preço unitário (R$)",
        required=False,
        min_value=Decimal("0"),
        max_digits=10,
        decimal_places=2,
        help_text="Em branco usa o preço cadastrado.",
    )

    def __init__(self, *args, pode_alterar_preco=False, **kwargs):
        self.pode_alterar_preco = pode_alterar_preco
        super().__init__(*args, **kwargs)
        if not pode_alterar_preco:
            # Vendedor não altera preço: o campo nem existe no formulário.
            del self.fields["preco"]

    def clean(self):
        dados = super().clean()
        produto = dados.get("produto")
        quantidade = dados.get("quantidade")

        if produto is None:
            return dados

        preco = dados.get("preco") if self.pode_alterar_preco else None
        if preco is None:
            preco = produto.preco_venda
        if preco is None:
            self.add_error(
                "produto", f"O produto '{produto}' não tem preço de venda cadastrado."
            )
            return dados
        dados["preco"] = preco

        disponivel = produto.quantidade or 0
        if quantidade is not None and quantidade > disponivel:
            self.add_error(
                "quantidade", f"Estoque insuficiente. Disponível: {disponivel}."
            )

        return dados


class BaseItemVendaFormSet(BaseFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        if "DELETE" in form.fields:
            aplicar_classe_bootstrap(form.fields["DELETE"].widget)

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        vistos = set()
        total = 0
        for form in self.forms:
            dados = form.cleaned_data
            if not dados or dados.get("DELETE"):
                continue
            total += 1
            produto = dados["produto"]
            if produto.pk in vistos:
                raise ValidationError(
                    f"O produto '{produto}' aparece mais de uma vez. "
                    "Some as quantidades em uma única linha."
                )
            vistos.add(produto.pk)

        if total == 0:
            raise ValidationError("Adicione pelo menos um item à venda.")

    def itens(self):
        """
        Lista de itens validados, no formato esperado por
        Venda.registrar_venda(). Só deve ser chamado depois de is_valid().
        """
        itens = []
        for form in self.forms:
            dados = getattr(form, "cleaned_data", None)
            if not dados or dados.get("DELETE") or not dados.get("produto"):
                continue
            itens.append(
                {
                    "produto": dados["produto"],
                    "quantidade": dados["quantidade"],
                    "preco": dados["preco"],
                }
            )
        return itens


ItemVendaFormSet = formset_factory(
    ItemVendaForm,
    formset=BaseItemVendaFormSet,
    extra=0,
    min_num=1,
    validate_min=False,
    can_delete=True,
)


class VendaFiltroForm(PeriodoForm):
    vendedor = UsuarioChoiceField(
        label="Vendedor", required=False, empty_label="Todos"
    )

    field_order = ["vendedor", "data_inicial", "data_final"]

    def filtrar(self, queryset):
        if not self.is_valid():
            return queryset

        if self.cleaned_data.get("vendedor"):
            queryset = queryset.filter(vendedor=self.cleaned_data["vendedor"])

        return self.filtrar_periodo(queryset, "data")
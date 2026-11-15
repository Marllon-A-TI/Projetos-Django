from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from core.forms import BootstrapFormMixin, DateInput, PeriodoForm

from .models import (
    CATEGORIAS_SAIDA_CHOICES,
    ContaPagar,
    ContaReceber,
    FluxoCaixa,
)


# ---------------------------------------------------------------------------
# Contas a pagar e a receber
# ---------------------------------------------------------------------------


class _ContaFormBase(BootstrapFormMixin, forms.ModelForm):
    """Só contas pendentes podem ser editadas."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.editavel = (
            self.instance.pk is None
            or self.instance.status == self.instance.Status.PENDENTE
        )
        if not self.editavel:
            for campo in self.fields.values():
                campo.disabled = True

    def clean(self):
        dados = super().clean()
        if not self.editavel:
            raise ValidationError("Somente contas pendentes podem ser editadas.")
        return dados


class ContaPagarForm(_ContaFormBase):
    class Meta:
        model = ContaPagar
        fields = ["fornecedor", "descricao", "categoria", "valor", "vencimento"]
        widgets = {"vencimento": DateInput()}


class ContaReceberForm(_ContaFormBase):
    class Meta:
        model = ContaReceber
        fields = ["cliente", "descricao", "valor", "vencimento"]
        widgets = {"vencimento": DateInput()}


class _BaixaContaForm(BootstrapFormMixin, forms.Form):
    """Base das baixas (pagamento / recebimento) de uma conta pendente."""

    rotulo_data = "Data"

    data_baixa = forms.DateField(
        label="Data", widget=DateInput(), initial=timezone.localdate
    )

    def __init__(self, *args, conta, **kwargs):
        self.conta = conta
        super().__init__(*args, **kwargs)
        self.fields["data_baixa"].label = self.rotulo_data

    def clean_data_baixa(self):
        data = self.cleaned_data["data_baixa"]
        if data > timezone.localdate():
            raise ValidationError("A data não pode estar no futuro.")
        return data

    def clean(self):
        dados = super().clean()
        if self.conta.status != self.conta.Status.PENDENTE:
            raise ValidationError("Somente contas pendentes podem ser baixadas.")
        return dados


class BaixaContaPagarForm(_BaixaContaForm):
    rotulo_data = "Data do pagamento"

    def salvar(self):
        return self.conta.marcar_como_paga(self.cleaned_data["data_baixa"])


class BaixaContaReceberForm(_BaixaContaForm):
    rotulo_data = "Data do recebimento"

    def salvar(self):
        return self.conta.marcar_como_recebida(self.cleaned_data["data_baixa"])


# ---------------------------------------------------------------------------
# Fluxo de caixa
# ---------------------------------------------------------------------------


class FluxoCaixaForm(BootstrapFormMixin, forms.ModelForm):
    """
    Lançamento manual de SAÍDA no caixa (aluguel, água, luz, internet,
    fornecedores, despesas). As entradas (vendas e recebimentos) são geradas
    automaticamente pelo sistema. Lançamentos são imutáveis: só há criação.
    """

    class Meta:
        model = FluxoCaixa
        fields = ["categoria", "valor", "descricao", "data"]
        widgets = {"data": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            raise ValueError(
                "Lançamentos do fluxo de caixa são imutáveis e não podem ser editados."
            )
        self.instance.tipo = FluxoCaixa.Tipo.SAIDA
        self.fields["categoria"].choices = [("", "Selecione")] + list(
            CATEGORIAS_SAIDA_CHOICES
        )
        self.fields["descricao"].required = True

    def clean_data(self):
        data = self.cleaned_data["data"]
        if data > timezone.localdate():
            raise ValidationError("A data do lançamento não pode estar no futuro.")
        return data


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------


class FluxoCaixaFiltroForm(PeriodoForm):
    tipo = forms.ChoiceField(
        label="Tipo", required=False, choices=[("", "Todos")] + FluxoCaixa.Tipo.choices
    )
    categoria = forms.ChoiceField(
        label="Categoria",
        required=False,
        choices=[("", "Todas")] + FluxoCaixa.Categoria.choices,
    )

    field_order = ["tipo", "categoria", "data_inicial", "data_final"]

    def filtrar(self, queryset):
        if not self.is_valid():
            return queryset

        dados = self.cleaned_data
        if dados.get("tipo"):
            queryset = queryset.filter(tipo=dados["tipo"])
        if dados.get("categoria"):
            queryset = queryset.filter(categoria=dados["categoria"])

        return self.filtrar_periodo(queryset, "data")


class _ContaFiltroForm(PeriodoForm):
    modelo = None
    campos_busca = ()

    q = forms.CharField(label="Buscar", required=False)
    status = forms.ChoiceField(label="Situação", required=False)

    field_order = ["q", "status", "data_inicial", "data_final"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = (
            [("", "Todas")]
            + list(self.modelo.Status.choices)
            + [("ATRASADA", "Atrasadas")]
        )
        self.fields["data_inicial"].label = "Vencimento de"
        self.fields["data_final"].label = "Vencimento até"

    def filtrar(self, queryset):
        if not self.is_valid():
            return queryset

        dados = self.cleaned_data

        termo = dados.get("q")
        if termo:
            condicao = Q()
            for campo in self.campos_busca:
                condicao |= Q(**{f"{campo}__icontains": termo})
            queryset = queryset.filter(condicao)

        status = dados.get("status")
        if status == "ATRASADA":
            queryset = queryset.atrasadas()
        elif status:
            queryset = queryset.filter(status=status)

        return self.filtrar_periodo(queryset, "vencimento")


class ContaPagarFiltroForm(_ContaFiltroForm):
    modelo = ContaPagar
    campos_busca = ("fornecedor", "descricao")


class ContaReceberFiltroForm(_ContaFiltroForm):
    modelo = ContaReceber
    campos_busca = ("cliente", "descricao")
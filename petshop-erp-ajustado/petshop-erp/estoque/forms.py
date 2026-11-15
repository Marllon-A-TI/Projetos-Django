from django import forms
from django.forms import Textarea

from core.forms import BootstrapFormMixin, PeriodoForm, UsuarioChoiceField
from produtos.forms import ProdutoChoiceField
from produtos.models import Produto

from .models import MovimentacaoEstoque

# VENDA é gerada automaticamente pela venda; não pode ser lançada à mão.
TIPOS_MANUAIS = [
    (valor, rotulo)
    for valor, rotulo in MovimentacaoEstoque.Tipo.choices
    if valor != MovimentacaoEstoque.Tipo.VENDA
]


class MovimentacaoEstoqueForm(BootstrapFormMixin, forms.Form):
    produto = ProdutoChoiceField()
    tipo = forms.ChoiceField(
        label="Tipo de movimentação",
        choices=[("", "Selecione o tipo")] + TIPOS_MANUAIS,
    )
    quantidade = forms.IntegerField(
        label="Quantidade",
        min_value=0,
        help_text="No AJUSTE, informe o novo estoque contado.",
    )
    observacao = forms.CharField(
        label="Observação",
        required=False,
        widget=Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, usuario, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean(self):
        dados = super().clean()
        produto = dados.get("produto")
        tipo = dados.get("tipo")
        quantidade = dados.get("quantidade")

        if not tipo or quantidade is None:
            return dados

        if tipo != MovimentacaoEstoque.Tipo.AJUSTE and quantidade == 0:
            self.add_error("quantidade", "A quantidade deve ser maior que zero.")

        elif (
            tipo == MovimentacaoEstoque.Tipo.SAIDA
            and produto is not None
            and quantidade > (produto.quantidade or 0)
        ):
            self.add_error(
                "quantidade",
                f"Estoque insuficiente. Disponível: {produto.quantidade or 0}.",
            )

        if tipo == MovimentacaoEstoque.Tipo.AJUSTE and not (
            dados.get("observacao") or ""
        ).strip():
            self.add_error("observacao", "Informe o motivo do ajuste.")

        return dados

    def save(self):
        """
        Registra a movimentação e atualiza o estoque.
        Pode lançar ValidationError (ex.: outra venda consumiu o estoque
        no mesmo instante); a view deve capturá-la.
        """
        dados = self.cleaned_data
        return MovimentacaoEstoque.registrar(
            produto=dados["produto"],
            tipo=dados["tipo"],
            quantidade=dados["quantidade"],
            usuario=self.usuario,
            observacao=(dados.get("observacao") or "").strip(),
        )


class MovimentacaoEstoqueFiltroForm(PeriodoForm):
    produto = ProdutoChoiceField(
        queryset=Produto.objects.order_by("nome", "id"),
        required=False,
        empty_label="Todos os produtos",
    )
    tipo = forms.ChoiceField(
        label="Tipo",
        required=False,
        choices=[("", "Todos")] + MovimentacaoEstoque.Tipo.choices,
    )
    usuario = UsuarioChoiceField(
        label="Responsável", required=False, empty_label="Todos"
    )

    field_order = ["produto", "tipo", "usuario", "data_inicial", "data_final"]

    def filtrar(self, queryset):
        if not self.is_valid():
            return queryset

        dados = self.cleaned_data
        if dados.get("produto"):
            queryset = queryset.filter(produto=dados["produto"])
        if dados.get("tipo"):
            queryset = queryset.filter(tipo=dados["tipo"])
        if dados.get("usuario"):
            queryset = queryset.filter(usuario=dados["usuario"])

        return self.filtrar_periodo(queryset, "data__date")
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.text import Truncator

from core.admin import ImutavelAdminMixin
from produtos.models import Produto

from .forms import TIPOS_MANUAIS
from .models import MovimentacaoEstoque


class MovimentacaoEstoqueAdminForm(forms.ModelForm):
    class Meta:
        model = MovimentacaoEstoque
        fields = ("produto", "tipo", "quantidade", "observacao")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["produto"].queryset = Produto.objects.ativos().order_by(
            "nome", "id"
        )
        self.fields["tipo"].choices = [("", "---------")] + TIPOS_MANUAIS

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


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(ImutavelAdminMixin, admin.ModelAdmin):
    form = MovimentacaoEstoqueAdminForm

    list_display = (
        "data",
        "produto",
        "tipo",
        "quantidade",
        "quantidade_anterior",
        "quantidade_nova",
        "variacao_fmt",
        "usuario",
        "observacao_resumo",
    )
    list_filter = ("tipo", ("data", admin.DateFieldListFilter), "usuario")
    search_fields = (
        "produto__nome",
        "produto__codigo_barras",
        "observacao",
        "usuario__username",
    )
    date_hierarchy = "data"
    list_select_related = ("produto", "usuario")
    list_per_page = 50
    autocomplete_fields = ("produto",)
    readonly_fields = (
        "data",
        "usuario",
        "quantidade_anterior",
        "quantidade_nova",
        "variacao_fmt",
    )

    def get_fieldsets(self, request, obj=None):
        movimentacao = ("produto", "tipo", "quantidade", "observacao")
        if obj is None:
            return (("Movimentação", {"fields": movimentacao}),)
        return (
            ("Movimentação", {"fields": movimentacao}),
            (
                "Histórico",
                {
                    "fields": (
                        "quantidade_anterior",
                        "quantidade_nova",
                        "variacao_fmt",
                        "usuario",
                        "data",
                    )
                },
            ),
        )

    def save_model(self, request, obj, form, change):
        """
        Em vez de gravar o objeto direto, passa pelo único caminho permitido
        para alterar estoque: MovimentacaoEstoque.registrar().
        """
        if change:
            return

        movimentacao = MovimentacaoEstoque.registrar(
            produto=obj.produto,
            tipo=obj.tipo,
            quantidade=obj.quantidade,
            usuario=request.user,
            observacao=obj.observacao,
        )

        # Copia os valores gravados para o objeto que o admin usa na resposta.
        obj.pk = movimentacao.pk
        obj.usuario = request.user
        obj.data = movimentacao.data
        obj.quantidade_anterior = movimentacao.quantidade_anterior
        obj.quantidade_nova = movimentacao.quantidade_nova
        obj._state.adding = False
        obj._state.db = movimentacao._state.db

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as erro:
            # Ex.: outra venda consumiu o estoque no mesmo instante.
            # A transação do admin já foi desfeita.
            self.message_user(request, " ".join(erro.messages), level=messages.ERROR)
            return HttpResponseRedirect(request.path)

    @admin.display(description="Variação")
    def variacao_fmt(self, obj):
        if obj.quantidade_anterior is None or obj.quantidade_nova is None:
            return "-"
        variacao = obj.variacao
        if variacao > 0:
            return format_html(
                '<span style="color:#198754;font-weight:600">+{}</span>', variacao
            )
        if variacao < 0:
            return format_html(
                '<span style="color:#b02a37;font-weight:600">{}</span>', variacao
            )
        return "0"

    @admin.display(description="Observação")
    def observacao_resumo(self, obj):
        return Truncator(obj.observacao).chars(60) or "-"
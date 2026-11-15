from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from core.utils import moeda
from estoque.models import MovimentacaoEstoque

from .forms import ProdutoForm
from .models import Produto


class EstoqueBaixoFilter(admin.SimpleListFilter):
    title = "estoque"
    parameter_name = "estoque"

    def lookups(self, request, model_admin):
        return (("baixo", "Estoque baixo"), ("zerado", "Zerado"))

    def queryset(self, request, queryset):
        if self.value() == "baixo":
            return queryset.estoque_baixo()
        if self.value() == "zerado":
            return queryset.filter(quantidade=0)
        return queryset


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    form = ProdutoForm

    list_display = (
        "nome_exibicao",
        "codigo_barras",
        "categoria",
        "fornecedor",
        "quantidade",
        "estoque_minimo",
        "alerta_estoque",
        "preco_custo_moeda",
        "preco_venda_moeda",
        "ativo",
    )
    list_display_links = ("nome_exibicao",)
    list_filter = ("ativo", EstoqueBaixoFilter, "categoria", "fornecedor")
    search_fields = ("nome", "codigo_barras", "categoria", "fornecedor")
    ordering = ("nome", "id")
    list_per_page = 50
    actions = ("ativar_produtos", "desativar_produtos")
    readonly_fields = (
        "quantidade",
        "valor_em_estoque_moeda",
        "historico_estoque",
        "criado_em",
        "atualizado_em",
    )

    # --- Formulário -------------------------------------------------------

    def get_form(self, request, obj=None, change=False, **kwargs):
        form_base = super().get_form(request, obj, change=change, **kwargs)

        class ProdutoAdminForm(form_base):
            def __init__(self, *args, **kw):
                # O ProdutoForm precisa saber quem registra o estoque inicial.
                kw.setdefault("usuario", request.user)
                super().__init__(*args, **kw)

        return ProdutoAdminForm

    def get_fieldsets(self, request, obj=None):
        identificacao = ("nome", "codigo_barras", "categoria", "fornecedor")
        precos = ("preco_custo", "preco_venda")

        if obj is None:
            return (
                ("Identificação", {"fields": identificacao}),
                ("Estoque", {"fields": ("quantidade_inicial", "estoque_minimo")}),
                ("Preços", {"fields": precos}),
                ("Situação", {"fields": ("ativo",)}),
            )

        return (
            ("Identificação", {"fields": identificacao}),
            (
                "Estoque",
                {
                    "fields": (
                        "quantidade",
                        "estoque_minimo",
                        "valor_em_estoque_moeda",
                        "historico_estoque",
                    )
                },
            ),
            ("Preços", {"fields": precos}),
            ("Situação", {"fields": ("ativo", "criado_em", "atualizado_em")}),
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            quantidade = form.cleaned_data.get("quantidade_inicial") or 0
            if quantidade > 0:
                MovimentacaoEstoque.registrar(
                    produto=obj,
                    tipo=MovimentacaoEstoque.Tipo.ENTRADA,
                    quantidade=quantidade,
                    usuario=request.user,
                    observacao="Estoque inicial",
                )

    # --- Colunas e campos calculados -------------------------------------

    @admin.display(description="Produto", ordering="nome")
    def nome_exibicao(self, obj):
        return str(obj)

    @admin.display(description="Alerta")
    def alerta_estoque(self, obj):
        if obj.estoque_baixo:
            return format_html(
                '<span style="color:#b02a37;font-weight:600">Estoque baixo</span>'
            )
        return "-"

    @admin.display(description="Preço de custo", ordering="preco_custo")
    def preco_custo_moeda(self, obj):
        return moeda(obj.preco_custo)

    @admin.display(description="Preço de venda", ordering="preco_venda")
    def preco_venda_moeda(self, obj):
        return moeda(obj.preco_venda)

    @admin.display(description="Valor em estoque (a preço de custo)")
    def valor_em_estoque_moeda(self, obj):
        if not obj.pk:
            return "-"
        return moeda(obj.valor_em_estoque)

    @admin.display(description="Histórico")
    def historico_estoque(self, obj):
        if not obj.pk:
            return "-"
        url = reverse("admin:estoque_movimentacaoestoque_changelist")
        return format_html(
            '<a href="{}?produto__id__exact={}">Ver movimentações deste produto</a>',
            url,
            obj.pk,
        )

    # --- Ações -----------------------------------------------------------

    @admin.action(description="Ativar produtos selecionados", permissions=["change"])
    def ativar_produtos(self, request, queryset):
        total = queryset.update(ativo=True, atualizado_em=timezone.now())
        self.message_user(request, f"{total} produto(s) ativado(s).", messages.SUCCESS)

    @admin.action(
        description="Desativar produtos selecionados", permissions=["change"]
    )
    def desativar_produtos(self, request, queryset):
        total = queryset.update(ativo=False, atualizado_em=timezone.now())
        self.message_user(
            request, f"{total} produto(s) desativado(s).", messages.SUCCESS
        )
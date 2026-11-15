from django.contrib import admin
from django.db.models import Count

from core.admin import SomenteLeituraAdminMixin
from core.utils import moeda

from .models import ItemVenda, Venda


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0
    can_delete = False
    fields = ("produto", "quantidade", "preco_moeda", "subtotal_moeda")
    readonly_fields = ("produto", "quantidade", "preco_moeda", "subtotal_moeda")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Preço unitário")
    def preco_moeda(self, obj):
        return moeda(obj.preco)

    @admin.display(description="Subtotal")
    def subtotal_moeda(self, obj):
        return moeda(obj.subtotal)


@admin.register(Venda)
class VendaAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = ("numero", "data", "hora", "vendedor", "qtd_itens", "total")
    list_display_links = ("numero",)
    list_filter = (("data", admin.DateFieldListFilter), "vendedor")
    search_fields = (
        "vendedor__username",
        "vendedor__first_name",
        "itens__produto__nome",
    )
    date_hierarchy = "data"
    list_select_related = ("vendedor",)
    list_per_page = 50
    inlines = [ItemVendaInline]
    readonly_fields = ("valor_total_moeda",)

    fieldsets = (
        (
            "Venda",
            {"fields": ("data", "hora", "vendedor", "valor_total_moeda")},
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            qtd_itens_anotada=Count("itens", distinct=True)
        )

    @admin.display(description="Venda", ordering="id")
    def numero(self, obj):
        return f"#{obj.pk}"

    @admin.display(description="Itens", ordering="qtd_itens_anotada")
    def qtd_itens(self, obj):
        return obj.qtd_itens_anotada

    @admin.display(description="Total", ordering="valor_total")
    def total(self, obj):
        return moeda(obj.valor_total)

    @admin.display(description="Valor total")
    def valor_total_moeda(self, obj):
        return moeda(obj.valor_total)


@admin.register(ItemVenda)
class ItemVendaAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = ("venda", "produto", "quantidade", "preco_moeda", "subtotal_moeda")
    search_fields = ("produto__nome", "produto__codigo_barras")
    list_select_related = ("venda", "produto")
    list_per_page = 50

    @admin.display(description="Preço unitário", ordering="preco")
    def preco_moeda(self, obj):
        return moeda(obj.preco)

    @admin.display(description="Subtotal")
    def subtotal_moeda(self, obj):
        return moeda(obj.subtotal)
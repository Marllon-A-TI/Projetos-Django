from django.contrib import admin
from django.utils.text import Truncator

from core.admin import SomenteLeituraAdminMixin

from .models import LogAcao


@admin.register(LogAcao)
class LogAcaoAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = ("data", "usuario", "acao", "ip", "descricao_resumo")
    list_filter = ("acao", ("data", admin.DateFieldListFilter), "usuario")
    search_fields = ("usuario__username", "ip", "descricao")
    date_hierarchy = "data"
    list_select_related = ("usuario",)
    list_per_page = 50
    readonly_fields = ("data",)

    fieldsets = (
        ("Registro", {"fields": ("data", "usuario", "acao", "ip", "descricao")}),
    )

    @admin.display(description="Descrição")
    def descricao_resumo(self, obj):
        return Truncator(obj.descricao).chars(80) or "-"
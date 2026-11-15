from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.html import format_html

from core.admin import ImutavelAdminMixin
from core.utils import moeda

from .forms import ContaPagarForm, ContaReceberForm, FluxoCaixaForm
from .models import ContaPagar, ContaReceber, FluxoCaixa

CORES_STATUS = {
    "PENDENTE": "#b58105",
    "PAGO": "#198754",
    "RECEBIDO": "#198754",
    "CANCELADO": "#6c757d",
}
COR_ATRASADA = "#b02a37"


# ---------------------------------------------------------------------------
# Fluxo de caixa
# ---------------------------------------------------------------------------


@admin.register(FluxoCaixa)
class FluxoCaixaAdmin(ImutavelAdminMixin, admin.ModelAdmin):
    list_display = ("data", "tipo_fmt", "categoria", "valor_assinado", "descricao")
    list_filter = ("tipo", "categoria", ("data", admin.DateFieldListFilter))
    search_fields = ("descricao",)
    date_hierarchy = "data"
    list_per_page = 50

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            # Lançamento manual: somente saídas (as entradas são automáticas).
            kwargs["form"] = FluxoCaixaForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                (
                    "Lançamento de saída",
                    {"fields": ("categoria", "valor", "descricao", "data")},
                ),
            )
        return (
            (
                "Lançamento",
                {"fields": ("tipo", "categoria", "valor", "descricao", "data")},
            ),
        )

    @admin.display(description="Tipo", ordering="tipo")
    def tipo_fmt(self, obj):
        cor = "#198754" if obj.tipo == FluxoCaixa.Tipo.ENTRADA else "#b02a37"
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            cor,
            obj.get_tipo_display(),
        )

    @admin.display(description="Valor", ordering="valor")
    def valor_assinado(self, obj):
        if obj.tipo == FluxoCaixa.Tipo.ENTRADA:
            return format_html(
                '<span style="color:#198754">+ {}</span>', moeda(obj.valor)
            )
        return format_html('<span style="color:#b02a37">- {}</span>', moeda(obj.valor))


# ---------------------------------------------------------------------------
# Contas a pagar e a receber
# ---------------------------------------------------------------------------


class VencimentoFilter(admin.SimpleListFilter):
    title = "vencimento"
    parameter_name = "situacao_vencimento"

    def lookups(self, request, model_admin):
        return (
            ("atrasadas", "Atrasadas"),
            ("hoje", "Vencem hoje"),
            ("7dias", "Próximos 7 dias"),
        )

    def queryset(self, request, queryset):
        hoje = timezone.localdate()
        if self.value() == "atrasadas":
            return queryset.atrasadas()
        if self.value() == "hoje":
            return queryset.pendentes().filter(vencimento=hoje)
        if self.value() == "7dias":
            return queryset.pendentes().filter(
                vencimento__gte=hoje, vencimento__lte=hoje + timedelta(days=7)
            )
        return queryset


class ContaAdminBase(admin.ModelAdmin):
    status_baixado = ""  # PAGO ou RECEBIDO: contas assim não são excluídas

    list_filter = ("status", VencimentoFilter, ("vencimento", admin.DateFieldListFilter))
    date_hierarchy = "vencimento"
    list_per_page = 50

    def get_actions(self, request):
        actions = super().get_actions(request)
        # QuerySet.delete() ignora a trava do model: sem exclusão em lote.
        actions.pop("delete_selected", None)
        return actions

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.status != "PENDENTE":
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.status == self.status_baixado:
            return False
        return super().has_delete_permission(request, obj)

    @admin.display(description="Valor", ordering="valor")
    def valor_moeda(self, obj):
        return moeda(obj.valor)

    @admin.display(description="Situação", ordering="status")
    def status_fmt(self, obj):
        if not obj.pk:
            return "-"
        if obj.atrasada:
            texto, cor = "Atrasada", COR_ATRASADA
        else:
            texto = obj.get_status_display()
            cor = CORES_STATUS.get(obj.status, "#6c757d")
        return format_html('<span style="color:{};font-weight:600">{}</span>', cor, texto)

    def _cancelar(self, request, queryset):
        total = 0
        for conta in queryset.filter(status="PENDENTE"):
            conta.status = "CANCELADO"
            conta.save(update_fields=["status", "atualizado_em"])
            total += 1
        self.message_user(
            request, f"{total} conta(s) pendente(s) cancelada(s).", messages.SUCCESS
        )


@admin.register(ContaPagar)
class ContaPagarAdmin(ContaAdminBase):
    form = ContaPagarForm
    status_baixado = "PAGO"

    list_display = (
        "fornecedor",
        "descricao",
        "categoria",
        "valor_moeda",
        "vencimento",
        "status_fmt",
        "data_pagamento",
    )
    search_fields = ("fornecedor", "descricao")
    actions = ("marcar_como_paga", "cancelar_contas")
    readonly_fields = ("status_fmt", "data_pagamento", "criado_em", "atualizado_em")

    fieldsets = (
        (
            "Conta",
            {"fields": ("fornecedor", "descricao", "categoria", "valor", "vencimento")},
        ),
        (
            "Situação",
            {"fields": ("status_fmt", "data_pagamento", "criado_em", "atualizado_em")},
        ),
    )

    @admin.action(description="Marcar como paga (data de hoje)", permissions=["change"])
    def marcar_como_paga(self, request, queryset):
        total = 0
        for conta in queryset:
            try:
                conta.marcar_como_paga()
                total += 1
            except ValidationError as erro:
                self.message_user(
                    request, f"{conta}: {' '.join(erro.messages)}", messages.WARNING
                )
        if total:
            self.message_user(
                request, f"{total} conta(s) marcada(s) como paga(s).", messages.SUCCESS
            )

    @admin.action(description="Cancelar contas pendentes", permissions=["change"])
    def cancelar_contas(self, request, queryset):
        self._cancelar(request, queryset)


@admin.register(ContaReceber)
class ContaReceberAdmin(ContaAdminBase):
    form = ContaReceberForm
    status_baixado = "RECEBIDO"

    list_display = (
        "cliente",
        "descricao",
        "valor_moeda",
        "vencimento",
        "status_fmt",
        "data_recebimento",
    )
    search_fields = ("cliente", "descricao")
    actions = ("marcar_como_recebida", "cancelar_contas")
    readonly_fields = ("status_fmt", "data_recebimento", "criado_em", "atualizado_em")

    fieldsets = (
        (
            "Conta",
            {"fields": ("cliente", "descricao", "valor", "vencimento")},
        ),
        (
            "Situação",
            {
                "fields": (
                    "status_fmt",
                    "data_recebimento",
                    "criado_em",
                    "atualizado_em",
                )
            },
        ),
    )

    @admin.action(
        description="Marcar como recebida (data de hoje)", permissions=["change"]
    )
    def marcar_como_recebida(self, request, queryset):
        total = 0
        for conta in queryset:
            try:
                conta.marcar_como_recebida()
                total += 1
            except ValidationError as erro:
                self.message_user(
                    request, f"{conta}: {' '.join(erro.messages)}", messages.WARNING
                )
        if total:
            self.message_user(
                request,
                f"{total} conta(s) marcada(s) como recebida(s).",
                messages.SUCCESS,
            )

    @admin.action(description="Cancelar contas pendentes", permissions=["change"])
    def cancelar_contas(self, request, queryset):
        self._cancelar(request, queryset)
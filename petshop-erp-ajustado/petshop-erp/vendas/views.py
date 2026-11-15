from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

from core.mixins import (
    FiltroListViewMixin,
    VendedorOuAdministradorRequiredMixin,
    eh_administrador,
)
from core.utils import moeda
from logs.models import LogAcao
from logs.utils import registrar_acao

from .forms import ItemVendaFormSet, VendaFiltroForm
from .models import Venda


class VendaCreateView(VendedorOuAdministradorRequiredMixin, View):
    """Tela de venda: várias linhas de produto em uma única venda."""

    template_name = "vendas/venda_form.html"

    def get_formset(self, dados=None):
        return ItemVendaFormSet(
            dados,
            form_kwargs={"pode_alterar_preco": eh_administrador(self.request.user)},
        )

    def renderizar(self, request, formset):
        return render(
            request,
            self.template_name,
            {
                "formset": formset,
                "eh_administrador": eh_administrador(request.user),
            },
        )

    def get(self, request):
        return self.renderizar(request, self.get_formset())

    def post(self, request):
        formset = self.get_formset(request.POST)

        if formset.is_valid():
            try:
                with transaction.atomic():
                    venda = Venda.registrar_venda(
                        vendedor=request.user, itens=formset.itens()
                    )
                    registrar_acao(
                        request,
                        LogAcao.Acao.VENDA,
                        f"Venda #{venda.pk}: {len(formset.itens())} item(ns), "
                        f"total {moeda(venda.valor_total)}",
                    )
            except ValidationError as erro:
                # Ex.: o estoque acabou entre a abertura da tela e o envio.
                messages.error(request, " ".join(erro.messages))
            else:
                messages.success(
                    request,
                    f"Venda #{venda.pk} registrada. Total: {moeda(venda.valor_total)}.",
                )
                return redirect("vendas:detail", pk=venda.pk)

        return self.renderizar(request, formset)


class VendaListView(
    VendedorOuAdministradorRequiredMixin, FiltroListViewMixin, ListView
):
    model = Venda
    template_name = "vendas/venda_list.html"
    context_object_name = "vendas"
    paginate_by = 25
    filtro_form_class = VendaFiltroForm

    def get_queryset(self):
        queryset = super().get_queryset().select_related("vendedor")
        if not eh_administrador(self.request.user):
            # Vendedor enxerga somente as próprias vendas.
            queryset = queryset.filter(vendedor=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        resumo = self.object_list.aggregate(
            total=Sum("valor_total"), quantidade=Count("id")
        )
        contexto["total_periodo"] = resumo["total"] or Decimal("0.00")
        contexto["qtd_periodo"] = resumo["quantidade"] or 0
        contexto["eh_administrador"] = eh_administrador(self.request.user)
        return contexto


class VendaDetailView(VendedorOuAdministradorRequiredMixin, DetailView):
    model = Venda
    template_name = "vendas/venda_detail.html"
    context_object_name = "venda"

    def get_queryset(self):
        queryset = Venda.objects.select_related("vendedor").prefetch_related(
            "itens__produto"
        )
        if not eh_administrador(self.request.user):
            queryset = queryset.filter(vendedor=self.request.user)
        return queryset
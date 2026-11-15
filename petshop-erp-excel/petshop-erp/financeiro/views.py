from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    FormView,
    ListView,
    UpdateView,
)

from core.mixins import AdministradorRequiredMixin, FiltroListViewMixin
from core.models import OperacaoNaoPermitidaError
from logs.models import LogAcao
from logs.utils import LogFormValidMixin, registrar_acao

from .forms import (
    BaixaContaPagarForm,
    BaixaContaReceberForm,
    ContaPagarFiltroForm,
    ContaPagarForm,
    ContaReceberFiltroForm,
    ContaReceberForm,
    FluxoCaixaFiltroForm,
    FluxoCaixaForm,
)
from .models import ContaPagar, ContaReceber, FluxoCaixa


# ---------------------------------------------------------------------------
# Bases reutilizadas por contas a pagar e a receber
# ---------------------------------------------------------------------------


class ContaListViewBase(AdministradorRequiredMixin, FiltroListViewMixin, ListView):
    context_object_name = "contas"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["total_filtrado"] = self.object_list.total()
        contexto["total_pendente"] = self.model.objects.pendentes().total()
        contexto["total_atrasado"] = self.model.objects.atrasadas().total()
        contexto["qtd_atrasadas"] = self.model.objects.atrasadas().count()
        return contexto


class ContaCreateViewBase(
    AdministradorRequiredMixin, LogFormValidMixin, SuccessMessageMixin, CreateView
):
    template_name = "financeiro/conta_form.html"
    acao_log = LogAcao.Acao.CRIACAO


class ContaUpdateViewBase(
    AdministradorRequiredMixin, LogFormValidMixin, SuccessMessageMixin, UpdateView
):
    template_name = "financeiro/conta_form.html"
    acao_log = LogAcao.Acao.EDICAO
    lista_url = ""

    def _conta_bloqueada(self):
        self.object = self.get_object()
        if self.object.status != "PENDENTE":
            messages.warning(
                self.request, "Somente contas pendentes podem ser editadas."
            )
            return redirect(self.lista_url)
        return None

    def get(self, request, *args, **kwargs):
        bloqueio = self._conta_bloqueada()
        if bloqueio is not None:
            return bloqueio
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        bloqueio = self._conta_bloqueada()
        if bloqueio is not None:
            return bloqueio
        return super().post(request, *args, **kwargs)


class ContaBaixaViewBase(AdministradorRequiredMixin, FormView):
    """Pagamento (contas a pagar) ou recebimento (contas a receber)."""

    template_name = "financeiro/conta_baixa.html"
    model = None
    lista_url = ""
    titulo = ""
    descricao_log = ""
    mensagem_sucesso = ""

    @cached_property
    def conta(self):
        return get_object_or_404(self.model, pk=self.kwargs["pk"])

    def _conta_bloqueada(self):
        if self.conta.status != "PENDENTE":
            messages.warning(
                self.request, "Somente contas pendentes podem ser baixadas."
            )
            return redirect(self.lista_url)
        return None

    def get(self, request, *args, **kwargs):
        bloqueio = self._conta_bloqueada()
        if bloqueio is not None:
            return bloqueio
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        bloqueio = self._conta_bloqueada()
        if bloqueio is not None:
            return bloqueio
        return super().post(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conta"] = self.conta
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["conta"] = self.conta
        contexto["titulo"] = self.titulo
        contexto["voltar_url"] = reverse(self.lista_url)
        return contexto

    def form_valid(self, form):
        try:
            with transaction.atomic():
                conta = form.salvar()
                registrar_acao(
                    self.request,
                    LogAcao.Acao.EDICAO,
                    f"{self.descricao_log}: {conta} (#{conta.pk})",
                )
        except ValidationError as erro:
            form.add_error(None, erro)
            return self.form_invalid(form)

        messages.success(self.request, self.mensagem_sucesso)
        return redirect(self.lista_url)


class ContaCancelarViewBase(AdministradorRequiredMixin, View):
    http_method_names = ["post"]
    model = None
    lista_url = ""

    def post(self, request, pk):
        with transaction.atomic():
            conta = get_object_or_404(self.model.objects.select_for_update(), pk=pk)
            if conta.status != "PENDENTE":
                messages.warning(
                    request, "Somente contas pendentes podem ser canceladas."
                )
                return redirect(self.lista_url)

            conta.status = "CANCELADO"
            conta.save(update_fields=["status", "atualizado_em"])
            registrar_acao(
                request,
                LogAcao.Acao.EDICAO,
                f"Conta cancelada: {conta} (#{conta.pk})",
            )

        messages.success(request, "Conta cancelada.")
        return redirect(self.lista_url)


class ContaDeleteViewBase(AdministradorRequiredMixin, DeleteView):
    template_name = "financeiro/conta_confirm_delete.html"
    lista_url = ""

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["voltar_url"] = reverse(self.lista_url)
        return contexto

    def form_valid(self, form):
        descricao = f"{self.object} (#{self.object.pk})"
        try:
            with transaction.atomic():
                resposta = super().form_valid(form)
                registrar_acao(
                    self.request,
                    LogAcao.Acao.EXCLUSAO,
                    f"Conta excluída: {descricao}",
                )
        except OperacaoNaoPermitidaError as erro:
            messages.error(self.request, str(erro))
            return redirect(self.lista_url)

        messages.success(self.request, "Conta excluída.")
        return resposta


# ---------------------------------------------------------------------------
# Contas a pagar
# ---------------------------------------------------------------------------


class ContaPagarListView(ContaListViewBase):
    model = ContaPagar
    template_name = "financeiro/contapagar_list.html"
    filtro_form_class = ContaPagarFiltroForm


class ContaPagarCreateView(ContaCreateViewBase):
    model = ContaPagar
    form_class = ContaPagarForm
    success_url = reverse_lazy("financeiro:pagar_list")
    success_message = "Conta a pagar cadastrada com sucesso."
    prefixo_log = "Conta a pagar criada: "
    extra_context = {
        "titulo": "Nova conta a pagar",
        "voltar_url": reverse_lazy("financeiro:pagar_list"),
    }


class ContaPagarUpdateView(ContaUpdateViewBase):
    model = ContaPagar
    form_class = ContaPagarForm
    success_url = reverse_lazy("financeiro:pagar_list")
    success_message = "Conta a pagar atualizada com sucesso."
    prefixo_log = "Conta a pagar editada: "
    lista_url = "financeiro:pagar_list"
    extra_context = {
        "titulo": "Editar conta a pagar",
        "voltar_url": reverse_lazy("financeiro:pagar_list"),
    }


class ContaPagarBaixaView(ContaBaixaViewBase):
    model = ContaPagar
    form_class = BaixaContaPagarForm
    lista_url = "financeiro:pagar_list"
    titulo = "Registrar pagamento"
    descricao_log = "Conta paga"
    mensagem_sucesso = "Pagamento registrado e lançado no caixa."


class ContaPagarCancelarView(ContaCancelarViewBase):
    model = ContaPagar
    lista_url = "financeiro:pagar_list"


class ContaPagarDeleteView(ContaDeleteViewBase):
    model = ContaPagar
    success_url = reverse_lazy("financeiro:pagar_list")
    lista_url = "financeiro:pagar_list"


# ---------------------------------------------------------------------------
# Contas a receber
# ---------------------------------------------------------------------------


class ContaReceberListView(ContaListViewBase):
    model = ContaReceber
    template_name = "financeiro/contareceber_list.html"
    filtro_form_class = ContaReceberFiltroForm


class ContaReceberCreateView(ContaCreateViewBase):
    model = ContaReceber
    form_class = ContaReceberForm
    success_url = reverse_lazy("financeiro:receber_list")
    success_message = "Conta a receber cadastrada com sucesso."
    prefixo_log = "Conta a receber criada: "
    extra_context = {
        "titulo": "Nova conta a receber",
        "voltar_url": reverse_lazy("financeiro:receber_list"),
    }


class ContaReceberUpdateView(ContaUpdateViewBase):
    model = ContaReceber
    form_class = ContaReceberForm
    success_url = reverse_lazy("financeiro:receber_list")
    success_message = "Conta a receber atualizada com sucesso."
    prefixo_log = "Conta a receber editada: "
    lista_url = "financeiro:receber_list"
    extra_context = {
        "titulo": "Editar conta a receber",
        "voltar_url": reverse_lazy("financeiro:receber_list"),
    }


class ContaReceberBaixaView(ContaBaixaViewBase):
    model = ContaReceber
    form_class = BaixaContaReceberForm
    lista_url = "financeiro:receber_list"
    titulo = "Registrar recebimento"
    descricao_log = "Conta recebida"
    mensagem_sucesso = "Recebimento registrado e lançado no caixa."


class ContaReceberCancelarView(ContaCancelarViewBase):
    model = ContaReceber
    lista_url = "financeiro:receber_list"


class ContaReceberDeleteView(ContaDeleteViewBase):
    model = ContaReceber
    success_url = reverse_lazy("financeiro:receber_list")
    lista_url = "financeiro:receber_list"


# ---------------------------------------------------------------------------
# Fluxo de caixa
# ---------------------------------------------------------------------------


class FluxoCaixaListView(AdministradorRequiredMixin, FiltroListViewMixin, ListView):
    model = FluxoCaixa
    template_name = "financeiro/fluxocaixa_list.html"
    context_object_name = "lancamentos"
    paginate_by = 30
    filtro_form_class = FluxoCaixaFiltroForm

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        entradas = self.object_list.total_entradas()
        saidas = self.object_list.total_saidas()
        contexto["entradas"] = entradas
        contexto["saidas"] = saidas
        contexto["saldo_periodo"] = entradas - saidas
        contexto["saldo_atual"] = FluxoCaixa.saldo_atual()
        return contexto


class FluxoCaixaCreateView(
    AdministradorRequiredMixin, LogFormValidMixin, SuccessMessageMixin, CreateView
):
    """Lançamento manual de saída (aluguel, água, luz, internet, despesas...)."""

    model = FluxoCaixa
    form_class = FluxoCaixaForm
    template_name = "financeiro/fluxocaixa_form.html"
    success_url = reverse_lazy("financeiro:caixa_list")
    success_message = "Saída lançada no caixa."
    acao_log = LogAcao.Acao.CRIACAO
    prefixo_log = "Lançamento de caixa: "
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView

from core.mixins import AdministradorRequiredMixin, FiltroListViewMixin
from logs.models import LogAcao
from logs.utils import registrar_acao

from .forms import MovimentacaoEstoqueFiltroForm, MovimentacaoEstoqueForm
from .models import MovimentacaoEstoque


class MovimentacaoListView(
    AdministradorRequiredMixin, FiltroListViewMixin, ListView
):
    model = MovimentacaoEstoque
    queryset = MovimentacaoEstoque.objects.select_related("produto", "usuario")
    template_name = "estoque/movimentacao_list.html"
    context_object_name = "movimentacoes"
    paginate_by = 30
    filtro_form_class = MovimentacaoEstoqueFiltroForm


class MovimentacaoCreateView(AdministradorRequiredMixin, FormView):
    form_class = MovimentacaoEstoqueForm
    template_name = "estoque/movimentacao_form.html"
    success_url = reverse_lazy("estoque:list")

    def get_initial(self):
        initial = super().get_initial()
        produto_id = self.request.GET.get("produto", "")
        if produto_id.isdigit():
            initial["produto"] = int(produto_id)
        tipo = self.request.GET.get("tipo", "")
        if tipo in dict(MovimentacaoEstoque.Tipo.choices):
            initial["tipo"] = tipo
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            with transaction.atomic():
                movimentacao = form.save()
                registrar_acao(
                    self.request,
                    LogAcao.Acao.CRIACAO,
                    f"Movimentação de estoque: {movimentacao}",
                )
        except ValidationError as erro:
            # Ex.: outra venda consumiu o estoque no mesmo instante.
            form.add_error(None, erro)
            return self.form_invalid(form)

        messages.success(self.request, "Movimentação registrada com sucesso.")
        return redirect(self.get_success_url())
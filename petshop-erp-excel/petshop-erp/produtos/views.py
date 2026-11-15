from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
)

from core.mixins import (
    AdministradorRequiredMixin,
    FiltroListViewMixin,
    VendedorOuAdministradorRequiredMixin,
    eh_administrador,
)
from logs.models import LogAcao
from logs.utils import LogFormValidMixin, registrar_acao

from .excel import PlanilhaInvalida, gerar_xlsx, ler_planilha
from .forms import ImportarProdutosForm, ProdutoFiltroForm, ProdutoForm
from .importacao import ImportacaoInvalida, importar_produtos
from .models import Produto


class ProdutoListView(
    VendedorOuAdministradorRequiredMixin, FiltroListViewMixin, ListView
):
    model = Produto
    template_name = "produtos/produto_list.html"
    context_object_name = "produtos"
    paginate_by = 25
    filtro_form_class = ProdutoFiltroForm

    def get_queryset(self):
        queryset = super().get_queryset()
        if not eh_administrador(self.request.user):
            queryset = queryset.filter(ativo=True)
        return queryset

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["eh_administrador"] = eh_administrador(self.request.user)
        return contexto


class ProdutoDetailView(VendedorOuAdministradorRequiredMixin, DetailView):
    model = Produto
    template_name = "produtos/produto_detail.html"
    context_object_name = "produto"

    def get_queryset(self):
        queryset = Produto.objects.all()
        if not eh_administrador(self.request.user):
            queryset = queryset.filter(ativo=True)
        return queryset

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        administrador = eh_administrador(self.request.user)
        contexto["eh_administrador"] = administrador
        if administrador:
            contexto["movimentacoes"] = self.object.movimentacoes.select_related(
                "usuario"
            )[:20]
        return contexto


class ProdutoCreateView(
    AdministradorRequiredMixin, LogFormValidMixin, SuccessMessageMixin, CreateView
):
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_message = "Produto cadastrado com sucesso."
    acao_log = LogAcao.Acao.CRIACAO
    prefixo_log = "Produto criado: "
    extra_context = {"titulo": "Novo produto"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("produtos:detail", kwargs={"pk": self.object.pk})


class ProdutoUpdateView(
    AdministradorRequiredMixin, LogFormValidMixin, SuccessMessageMixin, UpdateView
):
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_message = "Produto atualizado com sucesso."
    acao_log = LogAcao.Acao.EDICAO
    prefixo_log = "Produto editado: "
    extra_context = {"titulo": "Editar produto"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("produtos:detail", kwargs={"pk": self.object.pk})


class ProdutoAlternarAtivoView(AdministradorRequiredMixin, View):
    """Ativa ou desativa o produto (a forma segura de 'tirar de linha')."""

    http_method_names = ["post"]

    def post(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk)
        produto.ativo = not produto.ativo
        situacao = "ativado" if produto.ativo else "desativado"

        with transaction.atomic():
            produto.save(update_fields=["ativo", "atualizado_em"])
            registrar_acao(
                request,
                LogAcao.Acao.EDICAO,
                f"Produto {situacao}: {produto} (#{produto.pk})",
            )

        messages.success(request, f"Produto {situacao}.")
        return redirect("produtos:detail", pk=produto.pk)


class ProdutoDeleteView(AdministradorRequiredMixin, DeleteView):
    model = Produto
    template_name = "produtos/produto_confirm_delete.html"
    success_url = reverse_lazy("produtos:list")

    def form_valid(self, form):
        pk = self.object.pk
        descricao = f"{self.object} (#{pk})"
        try:
            with transaction.atomic():
                resposta = super().form_valid(form)
                registrar_acao(
                    self.request,
                    LogAcao.Acao.EXCLUSAO,
                    f"Produto excluído: {descricao}",
                )
        except ProtectedError:
            messages.error(
                self.request,
                "Este produto tem movimentações ou vendas e não pode ser "
                "excluído. Desative-o.",
            )
            return redirect("produtos:detail", pk=pk)

        messages.success(self.request, "Produto excluído.")
        return resposta


class ProdutoImportarView(AdministradorRequiredMixin, FormView):
    """Importa produtos de uma planilha XLSX (tudo ou nada)."""

    form_class = ImportarProdutosForm
    template_name = "produtos/produto_importar.html"
    success_url = reverse_lazy("produtos:list")

    def form_valid(self, form):
        arquivo = form.cleaned_data["arquivo"]

        try:
            linhas, erros = ler_planilha(arquivo)
        except PlanilhaInvalida as erro:
            form.add_error("arquivo", str(erro))
            return self.form_invalid(form)

        if not erros:
            try:
                with transaction.atomic():
                    resultado = importar_produtos(linhas, self.request.user)
                    registrar_acao(
                        self.request,
                        LogAcao.Acao.IMPORTACAO,
                        f"Importação Excel de produtos ({arquivo.name[:100]}): "
                        f"{resultado.criados} criado(s), "
                        f"{resultado.atualizados} atualizado(s), "
                        f"{resultado.sem_alteracao} sem alteração, "
                        f"{resultado.movimentacoes} movimentação(ões) de estoque.",
                    )
            except ImportacaoInvalida as erro:
                erros = erro.erros
            except ValidationError as erro:
                erros = erro.messages

        if erros:
            return self.render_to_response(
                self.get_context_data(form=form, erros_importacao=erros)
            )

        messages.success(
            self.request,
            f"Importação concluída: {resultado.criados} produto(s) criado(s), "
            f"{resultado.atualizados} atualizado(s) e "
            f"{resultado.sem_alteracao} sem alteração.",
        )
        return redirect(self.get_success_url())


class ProdutoExportarView(AdministradorRequiredMixin, View):
    """Baixa todos os produtos em XLSX (inclui preço de custo: só administrador)."""

    http_method_names = ["get"]

    def get(self, request):
        registros = list(
            Produto.objects.order_by("nome", "id").values_list(
                "codigo_barras",
                "nome",
                "categoria",
                "fornecedor",
                "quantidade",
                "estoque_minimo",
                "preco_custo",
                "preco_venda",
                "ativo",
            )
        )
        conteudo = gerar_xlsx(registros)
        registrar_acao(
            request,
            LogAcao.Acao.EXPORTACAO,
            f"Exportação Excel de produtos: {len(registros)} produto(s).",
        )

        nome = f"produtos_{timezone.localtime():%Y%m%d_%H%M}.xlsx"
        resposta = HttpResponse(
            conteudo,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        resposta["Cache-Control"] = "no-store"  # contém preço de custo
        return resposta

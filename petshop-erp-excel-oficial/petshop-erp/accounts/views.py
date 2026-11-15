from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.functional import cached_property
from django.views.generic import CreateView, FormView, ListView, UpdateView

from core.mixins import AdministradorRequiredMixin
from logs.models import LogAcao
from logs.utils import LogFormValidMixin, registrar_acao

from .forms import (
    AlterarSenhaForm,
    LoginForm,
    RedefinirSenhaForm,
    UsuarioCriarForm,
    UsuarioEditarForm,
)

User = get_user_model()


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class AlterarSenhaView(
    LoginRequiredMixin, SuccessMessageMixin, auth_views.PasswordChangeView
):
    form_class = AlterarSenhaForm
    template_name = "accounts/alterar_senha.html"
    success_url = reverse_lazy("core:home")
    success_message = "Senha alterada com sucesso."


class UsuarioListView(AdministradorRequiredMixin, ListView):
    model = User
    template_name = "accounts/usuario_list.html"
    context_object_name = "usuarios"
    paginate_by = 25

    def get_queryset(self):
        queryset = User.objects.prefetch_related("groups").order_by("username")
        termo = self.request.GET.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                Q(username__icontains=termo)
                | Q(first_name__icontains=termo)
                | Q(last_name__icontains=termo)
                | Q(email__icontains=termo)
            )
        return queryset

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["q"] = self.request.GET.get("q", "").strip()
        contexto["querystring"] = parametros.urlencode()
        return contexto


class UsuarioCreateView(
    AdministradorRequiredMixin, LogFormValidMixin, SuccessMessageMixin, CreateView
):
    model = User
    form_class = UsuarioCriarForm
    template_name = "accounts/usuario_form.html"
    success_url = reverse_lazy("accounts:usuario_list")
    success_message = "Usuário %(username)s criado com sucesso."
    acao_log = LogAcao.Acao.CRIACAO
    prefixo_log = "Usuário criado: "
    extra_context = {"titulo": "Novo usuário"}


class UsuarioUpdateView(
    AdministradorRequiredMixin, LogFormValidMixin, SuccessMessageMixin, UpdateView
):
    model = User
    form_class = UsuarioEditarForm
    template_name = "accounts/usuario_form.html"
    success_url = reverse_lazy("accounts:usuario_list")
    success_message = "Usuário %(username)s atualizado com sucesso."
    acao_log = LogAcao.Acao.EDICAO
    prefixo_log = "Usuário editado: "
    extra_context = {"titulo": "Editar usuário"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario_logado"] = self.request.user
        return kwargs


class UsuarioSenhaView(AdministradorRequiredMixin, FormView):
    """O administrador define uma nova senha para outro usuário."""

    form_class = RedefinirSenhaForm
    template_name = "accounts/usuario_senha.html"
    success_url = reverse_lazy("accounts:usuario_list")

    @cached_property
    def usuario_alvo(self):
        return get_object_or_404(User, pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.usuario_alvo
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["usuario_alvo"] = self.usuario_alvo
        return contexto

    def form_valid(self, form):
        with transaction.atomic():
            form.save()
            registrar_acao(
                self.request,
                LogAcao.Acao.EDICAO,
                f"Senha redefinida: {self.usuario_alvo.username} (#{self.usuario_alvo.pk})",
            )

        if self.usuario_alvo.pk == self.request.user.pk:
            # Evita deslogar o próprio administrador ao trocar a própria senha.
            update_session_auth_hash(self.request, self.usuario_alvo)

        messages.success(
            self.request,
            f"Senha de {self.usuario_alvo.username} redefinida com sucesso.",
        )
        return super().form_valid(form)
"""
Controle de acesso por perfil (grupo) e utilidades de listagem com filtro.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from accounts.models import GRUPO_ADMINISTRADOR, GRUPO_VENDEDOR


def usuario_tem_perfil(usuario, *grupos):
    """
    True se o usuário está ativo e é superusuário ou pertence a algum dos
    grupos informados. Os grupos são consultados uma única vez por requisição.
    """
    if not usuario.is_authenticated or not usuario.is_active:
        return False
    if usuario.is_superuser:
        return True

    nomes = getattr(usuario, "_nomes_grupos_cache", None)
    if nomes is None:
        nomes = set(usuario.groups.values_list("name", flat=True))
        usuario._nomes_grupos_cache = nomes
    return bool(nomes.intersection(grupos))


def eh_administrador(usuario):
    return usuario_tem_perfil(usuario, GRUPO_ADMINISTRADOR)


class PerfilRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Exige login e um dos perfis em `grupos_permitidos`.
    Sem login: redireciona para o login. Sem permissão: erro 403.
    """

    grupos_permitidos = ()

    def test_func(self):
        return usuario_tem_perfil(self.request.user, *self.grupos_permitidos)


class AdministradorRequiredMixin(PerfilRequiredMixin):
    grupos_permitidos = (GRUPO_ADMINISTRADOR,)


class VendedorOuAdministradorRequiredMixin(PerfilRequiredMixin):
    grupos_permitidos = (GRUPO_ADMINISTRADOR, GRUPO_VENDEDOR)


class FiltroListViewMixin:
    """
    Aplica um formulário de filtro (GET) à listagem.
    O formulário precisa ter o método filtrar(queryset).
    """

    filtro_form_class = None

    def get_filtro_form(self):
        if not hasattr(self, "_filtro_form"):
            self._filtro_form = self.filtro_form_class(self.request.GET or None)
        return self._filtro_form

    def get_queryset(self):
        return self.get_filtro_form().filtrar(super().get_queryset())

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["filtro"] = self.get_filtro_form()
        contexto["querystring"] = parametros.urlencode()
        return contexto
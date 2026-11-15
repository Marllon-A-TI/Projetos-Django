from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from accounts.models import GRUPO_ADMINISTRADOR, GRUPO_VENDEDOR

from .mixins import usuario_tem_perfil

SOMENTE_ADMINISTRADOR = (GRUPO_ADMINISTRADOR,)
VENDEDOR_OU_ADMINISTRADOR = (GRUPO_ADMINISTRADOR, GRUPO_VENDEDOR)

PERFIS_POR_APP = {
    "dashboard": SOMENTE_ADMINISTRADOR,
    "estoque": SOMENTE_ADMINISTRADOR,
    "financeiro": SOMENTE_ADMINISTRADOR,
    "logs": SOMENTE_ADMINISTRADOR,
    "produtos": VENDEDOR_OU_ADMINISTRADOR,
    "vendas": VENDEDOR_OU_ADMINISTRADOR,
}

# No app accounts, só estas rotas são liberadas para qualquer perfil
# (o login é público; as demais exigem Administrador).
ROTAS_LIVRES_ACCOUNTS = {"login", "logout", "alterar_senha"}


def perfis_exigidos(resolver_match):
    """Perfis que podem acessar a rota, ou None se esta camada não se aplica."""
    if resolver_match.namespace == "accounts":
        if resolver_match.url_name in ROTAS_LIVRES_ACCOUNTS:
            return None
        return SOMENTE_ADMINISTRADOR
    return PERFIS_POR_APP.get(resolver_match.namespace)


class ControleAcessoMiddleware:
    """
    Segunda camada de proteção por app. Mesmo que uma view nova esqueça o
    controle de acesso, a regra do app vale antes dela.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        resolvido = request.resolver_match
        if resolvido is None:
            return None

        perfis = perfis_exigidos(resolvido)
        if perfis is None:
            return None

        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if not usuario_tem_perfil(request.user, *perfis):
            raise PermissionDenied

        return None
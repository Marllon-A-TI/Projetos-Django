import logging

from django.shortcuts import render
from django.urls import reverse

from .seguranca import JANELA_LOGIN, interpretar_post_admin, login_bloqueado
from .utils import obter_ip, registrar_acao

logger = logging.getLogger(__name__)


class AuditoriaMiddleware:
    """
    1. Disponibiliza request.ip_cliente.
    2. Bloqueia (erro 429) tentativas repetidas de login errado.
    3. Registra no LogAcao as alterações feitas pelo painel /admin/.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.ip_cliente = obter_ip(request)

        if self._eh_post_de_login(request):
            username = request.POST.get("username", "")
            if login_bloqueado(request.ip_cliente, username):
                resposta = render(request, "429.html", status=429)
                resposta["Retry-After"] = str(int(JANELA_LOGIN.total_seconds()))
                return resposta

        resposta = self.get_response(request)
        self._auditar_admin(request, resposta)
        return resposta

    @staticmethod
    def _eh_post_de_login(request):
        if request.method != "POST":
            return False
        return request.path in (reverse("accounts:login"), reverse("admin:login"))

    @staticmethod
    def _auditar_admin(request, resposta):
        """Só audita POSTs que deram certo (o admin responde com redirecionamento)."""
        if request.method != "POST" or resposta.status_code != 302:
            return

        usuario = getattr(request, "user", None)
        if usuario is None or not usuario.is_authenticated:
            return

        prefixo = reverse("admin:index")
        if not request.path.startswith(prefixo):
            return

        try:
            partes = [p for p in request.path[len(prefixo):].split("/") if p]
            evento = interpretar_post_admin(partes, request.POST)
            if evento:
                registrar_acao(request, evento[0], evento[1])
        except Exception:
            # A auditoria nunca deve derrubar uma operação que já foi concluída.
            logger.exception("Falha ao registrar auditoria do admin.")
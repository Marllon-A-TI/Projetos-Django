"""
Utilidades de auditoria usadas pelas views dos demais apps.
"""

import ipaddress

from django.conf import settings
from django.db import transaction

from .models import LogAcao


def obter_ip(request):
    """
    IP do cliente. Lê o cabeçalho definido em settings.CLIENT_IP_HEADER
    (REMOTE_ADDR, HTTP_CF_CONNECTING_IP, ...) e, se ele não vier na
    requisição, usa REMOTE_ADDR. Retorna None se o valor não for um IP válido.
    """
    cabecalho = getattr(settings, "CLIENT_IP_HEADER", "REMOTE_ADDR")
    valor = request.META.get(cabecalho) or request.META.get("REMOTE_ADDR") or ""
    candidato = valor.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(candidato))
    except ValueError:
        return None


def registrar_acao(request, acao, descricao=""):
    """Grava um LogAcao com o usuário e o IP da requisição."""
    return LogAcao.registrar(
        usuario=getattr(request, "user", None),
        acao=acao,
        ip=obter_ip(request),
        descricao=descricao,
    )


class LogFormValidMixin:
    """
    Para CreateView e UpdateView: grava o objeto e o LogAcao na mesma
    transação. Deve vir antes da view genérica na lista de herança.
    """

    acao_log = LogAcao.Acao.EDICAO
    prefixo_log = ""

    def descricao_log(self):
        return f"{self.prefixo_log}{self.object} (#{self.object.pk})"

    def form_valid(self, form):
        with transaction.atomic():
            resposta = super().form_valid(form)
            registrar_acao(self.request, self.acao_log, self.descricao_log())
        return resposta
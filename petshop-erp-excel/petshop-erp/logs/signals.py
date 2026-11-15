from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .models import LogAcao
from .seguranca import descricao_falha_login
from .utils import obter_ip


@receiver(user_logged_in)
def registrar_login(sender, request, user, **kwargs):
    LogAcao.registrar(
        usuario=user,
        acao=LogAcao.Acao.LOGIN,
        ip=obter_ip(request) if request is not None else None,
        descricao="Login realizado",
    )


@receiver(user_logged_out)
def registrar_logout(sender, request, user, **kwargs):
    if user is None:
        return
    LogAcao.registrar(
        usuario=user,
        acao=LogAcao.Acao.LOGOUT,
        ip=obter_ip(request) if request is not None else None,
        descricao="Logout realizado",
    )


@receiver(user_login_failed)
def registrar_falha_login(sender, credentials, request=None, **kwargs):
    LogAcao.registrar(
        usuario=None,
        acao=LogAcao.Acao.LOGIN_ERRO,
        ip=obter_ip(request) if request is not None else None,
        descricao=descricao_falha_login(credentials.get("username")),
    )
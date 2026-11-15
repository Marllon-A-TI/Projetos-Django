"""
Regras de segurança e auditoria (sem dependência de request/response,
para serem fáceis de testar):

- limite de tentativas de login;
- interpretação dos POSTs do painel /admin/ para o log de auditoria.
"""

from datetime import timedelta

from django.utils import timezone

from .models import LogAcao

JANELA_LOGIN = timedelta(minutes=15)
MAX_FALHAS_POR_USUARIO = 5
MAX_FALHAS_POR_IP = 20


def descricao_falha_login(username):
    return f"Falha de login para o usuário '{(username or '').strip()[:150]}'"


def login_bloqueado(ip, username, agora=None):
    """
    True se o IP excedeu o limite de falhas na janela de tempo, seja para
    esse usuário (MAX_FALHAS_POR_USUARIO) ou no total (MAX_FALHAS_POR_IP).
    Um login bem-sucedido do usuário zera a contagem dele naquele IP.
    Sem IP identificado, nunca bloqueia.
    """
    if not ip:
        return False

    agora = agora or timezone.now()
    desde = agora - JANELA_LOGIN

    falhas = LogAcao.objects.filter(
        acao=LogAcao.Acao.LOGIN_ERRO, ip=ip, data__gte=desde
    )
    if falhas.count() >= MAX_FALHAS_POR_IP:
        return True

    ultimo_sucesso = (
        LogAcao.objects.filter(
            acao=LogAcao.Acao.LOGIN,
            ip=ip,
            usuario__username__iexact=(username or "").strip(),
        )
        .order_by("-data")
        .values_list("data", flat=True)
        .first()
    )
    if ultimo_sucesso and ultimo_sucesso > desde:
        falhas = falhas.filter(data__gt=ultimo_sucesso)

    falhas_do_usuario = falhas.filter(
        descricao__iexact=descricao_falha_login(username)
    ).count()
    return falhas_do_usuario >= MAX_FALHAS_POR_USUARIO


def interpretar_post_admin(partes, post):
    """
    Converte um POST bem-sucedido no admin em (ação, descrição) de auditoria.

    `partes` é o caminho depois do prefixo do admin, separado por "/"
    (ex.: ["produtos", "produto", "7", "change"]); `post` é o QueryDict.
    Retorna None para o que não precisa ser auditado.
    """
    if len(partes) < 2:
        return None

    alvo = f"{partes[0]}.{partes[1]}"

    if len(partes) == 2:
        nome_acao = post.get("action")
        if not nome_acao:
            return None
        quantidade = len(post.getlist("_selected_action"))
        if nome_acao == "delete_selected":
            if post.get("post") != "yes":
                return None
            return (
                LogAcao.Acao.EXCLUSAO,
                f"Admin: exclusão em lote em {alvo} ({quantidade} registro(s))",
            )
        return (
            LogAcao.Acao.EDICAO,
            f"Admin: ação '{nome_acao}' em {alvo} ({quantidade} registro(s))",
        )

    ultimo = partes[-1]
    if ultimo == "add":
        return (LogAcao.Acao.CRIACAO, f"Admin: novo registro em {alvo}")

    if len(partes) == 4:
        codigo = partes[2]
        if ultimo == "change":
            return (LogAcao.Acao.EDICAO, f"Admin: alteração em {alvo} #{codigo}")
        if ultimo == "delete":
            return (LogAcao.Acao.EXCLUSAO, f"Admin: exclusão em {alvo} #{codigo}")
        if ultimo == "password":
            return (
                LogAcao.Acao.EDICAO,
                f"Admin: senha alterada em {alvo} #{codigo}",
            )

    return None
from django.conf import settings
from django.db import models

from core.models import ModeloImutavel


class LogAcao(ModeloImutavel):
    class Acao(models.TextChoices):
        CRIACAO = "CRIACAO", "Criação"
        EDICAO = "EDICAO", "Edição"
        EXCLUSAO = "EXCLUSAO", "Exclusão"
        VENDA = "VENDA", "Venda"
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"
        LOGIN_ERRO = "LOGIN_ERRO", "Falha de login"
        IMPORTACAO = "IMPORTACAO", "Importação"
        EXPORTACAO = "EXPORTACAO", "Exportação"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="logs_acao",
        verbose_name="usuário",
    )
    acao = models.CharField("ação", max_length=10, choices=Acao.choices)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    data = models.DateTimeField("data", auto_now_add=True)
    descricao = models.TextField("descrição", blank=True, default="")

    class Meta:
        verbose_name = "log de ação"
        verbose_name_plural = "logs de ações"
        ordering = ["-data", "-id"]
        indexes = [
            models.Index(fields=["-data"], name="logacao_data_idx"),
            models.Index(fields=["usuario", "-data"], name="logacao_usuario_data_idx"),
            models.Index(fields=["acao"], name="logacao_acao_idx"),
        ]

    def __str__(self):
        nome = self.usuario.get_username() if self.usuario else "anônimo"
        return f"{self.data:%d/%m/%Y %H:%M} - {nome} - {self.get_acao_display()}"

    @classmethod
    def registrar(cls, *, usuario, acao, ip=None, descricao=""):
        """Cria um registro de auditoria. Aceita usuário anônimo (vira None)."""
        if usuario is not None and not getattr(usuario, "is_authenticated", False):
            usuario = None
        return cls.objects.create(
            usuario=usuario, acao=acao, ip=ip or None, descricao=descricao or ""
        )
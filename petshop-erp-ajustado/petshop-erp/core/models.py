"""
Blocos reutilizáveis para todos os apps do Pet Shop ERP.

- ModeloBase: carimbos de criação e atualização.
- ModeloProtegido: registro que nunca pode ser excluído.
- ModeloImutavel: registro que não pode ser excluído nem alterado
  depois de criado (histórico / livro-razão).
"""

from django.db import models
from django.utils import timezone


class OperacaoNaoPermitidaError(Exception):
    """Tentativa de alterar ou excluir um registro protegido."""


def hora_atual():
    """Hora local atual sem microssegundos (default de TimeField)."""
    return timezone.localtime().time().replace(microsecond=0)


class ModeloBase(models.Model):
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class ProtegidoQuerySet(models.QuerySet):
    def delete(self):
        raise OperacaoNaoPermitidaError(
            "A exclusão em lote não é permitida para este tipo de registro."
        )

    delete.alters_data = True
    delete.queryset_only = True


class HistoricoQuerySet(ProtegidoQuerySet):
    def update(self, **kwargs):
        raise OperacaoNaoPermitidaError(
            "A alteração em lote não é permitida para este tipo de registro."
        )

    update.alters_data = True
    update.queryset_only = True


ProtegidoManager = models.Manager.from_queryset(ProtegidoQuerySet)
HistoricoManager = models.Manager.from_queryset(HistoricoQuerySet)


class ModeloProtegido(models.Model):
    """Registro que nunca pode ser excluído."""

    objects = ProtegidoManager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise OperacaoNaoPermitidaError(
            f"{self._meta.verbose_name} não pode ser excluído: "
            "o histórico é preservado."
        )


class ModeloImutavel(ModeloProtegido):
    """Registro que só pode ser criado: nunca alterado nem excluído."""

    objects = HistoricoManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise OperacaoNaoPermitidaError(
                f"{self._meta.verbose_name} é imutável e não pode ser "
                "alterado depois de criado."
            )
        super().save(*args, **kwargs)
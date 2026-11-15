from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.models import (
    HistoricoQuerySet,
    ModeloBase,
    ModeloImutavel,
    OperacaoNaoPermitidaError,
)

CATEGORIAS_ENTRADA = ("VENDA", "RECEBIMENTO")
CATEGORIAS_SAIDA = (
    "FORNECEDOR",
    "ALUGUEL",
    "AGUA",
    "LUZ",
    "INTERNET",
    "DESPESA",
)

VALOR_MINIMO = Decimal("0.01")


class FluxoCaixaQuerySet(HistoricoQuerySet):
    def total_entradas(self):
        return self.filter(tipo="ENTRADA").aggregate(total=Sum("valor"))[
            "total"
        ] or Decimal("0.00")

    def total_saidas(self):
        return self.filter(tipo="SAIDA").aggregate(total=Sum("valor"))[
            "total"
        ] or Decimal("0.00")

    def saldo(self):
        return self.total_entradas() - self.total_saidas()


class FluxoCaixa(ModeloImutavel):
    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saída"

    class Categoria(models.TextChoices):
        # Entradas
        VENDA = "VENDA", "Vendas"
        RECEBIMENTO = "RECEBIMENTO", "Recebimentos"
        # Saídas
        FORNECEDOR = "FORNECEDOR", "Fornecedores"
        ALUGUEL = "ALUGUEL", "Aluguel"
        AGUA = "AGUA", "Água"
        LUZ = "LUZ", "Luz"
        INTERNET = "INTERNET", "Internet"
        DESPESA = "DESPESA", "Despesas"

    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices)
    categoria = models.CharField(
        "categoria", max_length=15, choices=Categoria.choices
    )
    valor = models.DecimalField(
        "valor",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(VALOR_MINIMO)],
    )
    descricao = models.CharField("descrição", max_length=255, blank=True, default="")
    data = models.DateField("data", default=timezone.localdate, db_index=True)

    objects = FluxoCaixaQuerySet.as_manager()

    class Meta:
        verbose_name = "lançamento do fluxo de caixa"
        verbose_name_plural = "fluxo de caixa"
        ordering = ["-data", "-id"]
        indexes = [
            models.Index(fields=["tipo", "data"], name="fluxo_tipo_data_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name="fluxo_caixa_valor_positivo",
            ),
            models.CheckConstraint(
                condition=(
                    Q(tipo="ENTRADA", categoria__in=list(CATEGORIAS_ENTRADA))
                    | Q(tipo="SAIDA", categoria__in=list(CATEGORIAS_SAIDA))
                ),
                name="fluxo_caixa_categoria_coerente",
            ),
        ]

    def __str__(self):
        sinal = "+" if self.tipo == self.Tipo.ENTRADA else "-"
        return f"{self.data:%d/%m/%Y} {sinal} R$ {self.valor} ({self.get_categoria_display()})"

    @classmethod
    def saldo_atual(cls):
        return cls.objects.saldo()


CATEGORIAS_SAIDA_CHOICES = [
    (valor, rotulo)
    for valor, rotulo in FluxoCaixa.Categoria.choices
    if valor in CATEGORIAS_SAIDA
]


class ContaQuerySet(models.QuerySet):
    def pendentes(self):
        return self.filter(status="PENDENTE")

    def atrasadas(self):
        return self.pendentes().filter(vencimento__lt=timezone.localdate())

    def total(self):
        return self.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")


class ContaPagar(ModeloBase):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        PAGO = "PAGO", "Pago"
        CANCELADO = "CANCELADO", "Cancelado"

    fornecedor = models.CharField("fornecedor", max_length=150)
    descricao = models.CharField("descrição", max_length=255)
    categoria = models.CharField(
        "categoria",
        max_length=15,
        choices=CATEGORIAS_SAIDA_CHOICES,
        default="FORNECEDOR",
    )
    valor = models.DecimalField(
        "valor",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(VALOR_MINIMO)],
    )
    vencimento = models.DateField("vencimento", db_index=True)
    status = models.CharField(
        "status",
        max_length=10,
        choices=Status.choices,
        default=Status.PENDENTE,
        db_index=True,
    )
    data_pagamento = models.DateField("data do pagamento", null=True, blank=True)

    objects = ContaQuerySet.as_manager()

    class Meta:
        verbose_name = "conta a pagar"
        verbose_name_plural = "contas a pagar"
        ordering = ["vencimento", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name="conta_pagar_valor_positivo",
            ),
        ]

    def __str__(self):
        return f"{self.fornecedor} - {self.descricao} (R$ {self.valor})"

    @property
    def atrasada(self):
        return (
            self.status == self.Status.PENDENTE
            and self.vencimento < timezone.localdate()
        )

    @transaction.atomic
    def marcar_como_paga(self, data_pagamento=None):
        """Quita a conta e lança a saída correspondente no fluxo de caixa."""
        conta = type(self).objects.select_for_update().get(pk=self.pk)
        if conta.status != self.Status.PENDENTE:
            raise ValidationError(
                "Somente contas pendentes podem ser marcadas como pagas.",
                code="status_invalido",
            )

        data_pagamento = data_pagamento or timezone.localdate()
        conta.status = self.Status.PAGO
        conta.data_pagamento = data_pagamento
        conta.save(update_fields=["status", "data_pagamento", "atualizado_em"])

        FluxoCaixa.objects.create(
            tipo=FluxoCaixa.Tipo.SAIDA,
            categoria=conta.categoria,
            valor=conta.valor,
            descricao=f"Pagamento: {conta.fornecedor} - {conta.descricao}"[:255],
            data=data_pagamento,
        )

        self.status = conta.status
        self.data_pagamento = conta.data_pagamento
        return conta

    def delete(self, *args, **kwargs):
        if self.status == self.Status.PAGO:
            raise OperacaoNaoPermitidaError(
                "Conta já paga não pode ser excluída: ela originou um "
                "lançamento no fluxo de caixa."
            )
        return super().delete(*args, **kwargs)


class ContaReceber(ModeloBase):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        RECEBIDO = "RECEBIDO", "Recebido"
        CANCELADO = "CANCELADO", "Cancelado"

    cliente = models.CharField("cliente", max_length=150)
    descricao = models.CharField("descrição", max_length=255)
    valor = models.DecimalField(
        "valor",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(VALOR_MINIMO)],
    )
    vencimento = models.DateField("vencimento", db_index=True)
    status = models.CharField(
        "status",
        max_length=10,
        choices=Status.choices,
        default=Status.PENDENTE,
        db_index=True,
    )
    data_recebimento = models.DateField("data do recebimento", null=True, blank=True)

    objects = ContaQuerySet.as_manager()

    class Meta:
        verbose_name = "conta a receber"
        verbose_name_plural = "contas a receber"
        ordering = ["vencimento", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name="conta_receber_valor_positivo",
            ),
        ]

    def __str__(self):
        return f"{self.cliente} - {self.descricao} (R$ {self.valor})"

    @property
    def atrasada(self):
        return (
            self.status == self.Status.PENDENTE
            and self.vencimento < timezone.localdate()
        )

    @transaction.atomic
    def marcar_como_recebida(self, data_recebimento=None):
        """Quita a conta e lança a entrada correspondente no fluxo de caixa."""
        conta = type(self).objects.select_for_update().get(pk=self.pk)
        if conta.status != self.Status.PENDENTE:
            raise ValidationError(
                "Somente contas pendentes podem ser marcadas como recebidas.",
                code="status_invalido",
            )

        data_recebimento = data_recebimento or timezone.localdate()
        conta.status = self.Status.RECEBIDO
        conta.data_recebimento = data_recebimento
        conta.save(update_fields=["status", "data_recebimento", "atualizado_em"])

        FluxoCaixa.objects.create(
            tipo=FluxoCaixa.Tipo.ENTRADA,
            categoria=FluxoCaixa.Categoria.RECEBIMENTO,
            valor=conta.valor,
            descricao=f"Recebimento: {conta.cliente} - {conta.descricao}"[:255],
            data=data_recebimento,
        )

        self.status = conta.status
        self.data_recebimento = conta.data_recebimento
        return conta

    def delete(self, *args, **kwargs):
        if self.status == self.Status.RECEBIDO:
            raise OperacaoNaoPermitidaError(
                "Conta já recebida não pode ser excluída: ela originou um "
                "lançamento no fluxo de caixa."
            )
        return super().delete(*args, **kwargs)
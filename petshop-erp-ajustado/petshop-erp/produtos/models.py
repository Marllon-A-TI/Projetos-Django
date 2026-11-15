from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from core.models import ModeloBase


class EstoqueProtegidoError(Exception):
    """Tentativa de alterar o estoque sem passar por MovimentacaoEstoque."""


class ProdutoQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(ativo=True)

    def estoque_baixo(self):
        return self.filter(
            estoque_minimo__isnull=False,
            quantidade__lte=F("estoque_minimo"),
        )


class Produto(ModeloBase):
    nome = models.CharField("nome", max_length=150, blank=True, default="")
    codigo_barras = models.CharField(
        "código de barras", max_length=50, blank=True, default=""
    )
    categoria = models.CharField(
        "categoria", max_length=100, blank=True, default=""
    )
    fornecedor = models.CharField(
        "fornecedor", max_length=150, blank=True, default=""
    )
    quantidade = models.PositiveIntegerField(
        "quantidade em estoque",
        null=True,
        blank=True,
        default=0,
        help_text="Somente leitura: altere apenas por movimentação de estoque.",
    )
    estoque_minimo = models.PositiveIntegerField(
        "estoque mínimo", null=True, blank=True, default=0
    )
    preco_custo = models.DecimalField(
        "preço de custo",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    preco_venda = models.DecimalField(
        "preço de venda",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    ativo = models.BooleanField("ativo", default=True)

    objects = ProdutoQuerySet.as_manager()

    # Ligado apenas por MovimentacaoEstoque.registrar().
    _estoque_liberado = False

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["nome", "id"]
        indexes = [
            models.Index(fields=["nome"], name="produto_nome_idx"),
            models.Index(fields=["codigo_barras"], name="produto_codbarras_idx"),
            models.Index(fields=["categoria"], name="produto_categoria_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(preco_custo__isnull=True) | Q(preco_custo__gte=0),
                name="produto_preco_custo_nao_negativo",
            ),
            models.CheckConstraint(
                condition=Q(preco_venda__isnull=True) | Q(preco_venda__gte=0),
                name="produto_preco_venda_nao_negativo",
            ),
        ]

    def __str__(self):
        return self.nome or f"Produto #{self.pk}"

    # --- Propriedades de apoio (dashboard e telas) -------------------------

    @property
    def estoque_baixo(self):
        if self.estoque_minimo is None:
            return False
        return (self.quantidade or 0) <= self.estoque_minimo

    @property
    def valor_em_estoque(self):
        """Valor do estoque a preço de custo."""
        return Decimal(self.quantidade or 0) * (self.preco_custo or Decimal("0"))

    # --- Proteção do estoque ----------------------------------------------

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        if "quantidade" in instance.__dict__:
            instance._quantidade_original = instance.quantidade
        return instance

    def refresh_from_db(self, using=None, fields=None, from_queryset=None):
        super().refresh_from_db(
            using=using, fields=fields, from_queryset=from_queryset
        )
        if fields is None or "quantidade" in fields:
            if "quantidade" not in self.get_deferred_fields():
                self._quantidade_original = self.quantidade

    def save(self, *args, **kwargs):
        if not self._estoque_liberado:
            update_fields = kwargs.get("update_fields")

            if self._state.adding:
                if (self.quantidade or 0) != 0:
                    raise EstoqueProtegidoError(
                        "Crie o produto com quantidade 0 e registre uma "
                        "movimentação de ENTRADA para o estoque inicial."
                    )
            else:
                if update_fields is not None and "quantidade" in update_fields:
                    raise EstoqueProtegidoError(
                        "O estoque só pode ser alterado por "
                        "MovimentacaoEstoque.registrar()."
                    )

                deferidos = self.get_deferred_fields()
                if "quantidade" not in deferidos and self.quantidade != getattr(
                    self, "_quantidade_original", self.quantidade
                ):
                    raise EstoqueProtegidoError(
                        "O estoque não pode ser alterado diretamente. "
                        "Use MovimentacaoEstoque.registrar()."
                    )

                if update_fields is None:
                    # Nunca grava "quantidade" em um save comum: evita
                    # sobrescrever o estoque com um valor desatualizado.
                    kwargs["update_fields"] = [
                        campo.attname
                        for campo in self._meta.concrete_fields
                        if not campo.primary_key
                        and campo.attname != "quantidade"
                        and campo.attname not in deferidos
                    ]

        super().save(*args, **kwargs)

        if "quantidade" not in self.get_deferred_fields():
            self._quantidade_original = self.quantidade
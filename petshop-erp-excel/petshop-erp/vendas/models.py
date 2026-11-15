from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import DecimalField, F, Q, Sum
from django.utils import timezone

from core.models import ModeloBase, ModeloImutavel, ModeloProtegido, hora_atual
from estoque.models import MovimentacaoEstoque
from financeiro.models import FluxoCaixa
from produtos.models import Produto

CENTAVOS = Decimal("0.01")


class Venda(ModeloBase, ModeloProtegido):
    data = models.DateField("data", default=timezone.localdate, db_index=True)
    hora = models.TimeField("hora", default=hora_atual)
    valor_total = models.DecimalField(
        "valor total", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="vendas",
        verbose_name="vendedor",
    )

    class Meta:
        verbose_name = "venda"
        verbose_name_plural = "vendas"
        ordering = ["-data", "-hora", "-id"]
        indexes = [
            models.Index(fields=["vendedor", "data"], name="venda_vendedor_data_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_total__gte=0),
                name="venda_valor_total_nao_negativo",
            ),
        ]

    def __str__(self):
        return f"Venda #{self.pk} - {self.data:%d/%m/%Y} {self.hora:%H:%M} - R$ {self.valor_total}"

    def recalcular_total(self):
        """Soma quantidade x preço de todos os itens e grava em valor_total."""
        total = self.itens.aggregate(
            total=Sum(
                F("quantidade") * F("preco"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )["total"] or Decimal("0.00")

        self.valor_total = total
        self.save(update_fields=["valor_total", "atualizado_em"])
        return total

    @classmethod
    @transaction.atomic
    def registrar_venda(cls, *, vendedor, itens):
        """
        Registra uma venda completa em uma única transação:

        1. cria a venda e os itens;
        2. baixa o estoque (movimentação do tipo VENDA por item);
        3. calcula o total;
        4. lança a entrada no fluxo de caixa.

        `itens` é uma lista de dicionários:
            {"produto": <Produto>, "quantidade": 2, "preco": Decimal("25.00")}
        O campo "preco" é opcional; se ausente, usa o preço de venda atual
        do produto. Qualquer erro desfaz tudo.
        """
        if vendedor is None or not getattr(vendedor, "pk", None):
            raise ValidationError(
                "É obrigatório informar o vendedor.", code="vendedor_obrigatorio"
            )
        if not itens:
            raise ValidationError(
                "A venda precisa ter ao menos um item.", code="sem_itens"
            )

        normalizados = []
        for item in itens:
            produto = item["produto"]

            if not produto.ativo:
                raise ValidationError(
                    f"O produto '{produto}' está inativo.", code="produto_inativo"
                )

            try:
                quantidade = int(item["quantidade"])
            except (TypeError, ValueError):
                raise ValidationError("Quantidade inválida.", code="quantidade_invalida")
            if quantidade <= 0:
                raise ValidationError(
                    "A quantidade deve ser maior que zero.", code="quantidade_invalida"
                )

            preco = item.get("preco")
            if preco is None:
                preco = produto.preco_venda
            if preco is None:
                raise ValidationError(
                    f"O produto '{produto}' não tem preço de venda definido.",
                    code="sem_preco",
                )
            preco = Decimal(str(preco)).quantize(CENTAVOS)
            if preco < 0:
                raise ValidationError("O preço não pode ser negativo.", code="preco_invalido")

            normalizados.append((produto, quantidade, preco))

        # Ordem fixa evita deadlock entre vendas simultâneas.
        normalizados.sort(key=lambda linha: linha[0].pk)

        venda = cls.objects.create(vendedor=vendedor)

        for produto, quantidade, preco in normalizados:
            ItemVenda.objects.create(
                venda=venda, produto=produto, quantidade=quantidade, preco=preco
            )
            MovimentacaoEstoque.registrar(
                produto=produto,
                tipo=MovimentacaoEstoque.Tipo.VENDA,
                quantidade=quantidade,
                usuario=vendedor,
                observacao=f"Venda #{venda.pk}",
            )

        total = venda.recalcular_total()
        if total <= 0:
            raise ValidationError(
                "O total da venda deve ser maior que zero.", code="total_invalido"
            )

        FluxoCaixa.objects.create(
            tipo=FluxoCaixa.Tipo.ENTRADA,
            categoria=FluxoCaixa.Categoria.VENDA,
            valor=total,
            descricao=f"Venda #{venda.pk}",
            data=venda.data,
        )

        return venda


class ItemVenda(ModeloImutavel):
    venda = models.ForeignKey(
        Venda,
        on_delete=models.PROTECT,
        related_name="itens",
        verbose_name="venda",
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name="itens_venda",
        verbose_name="produto",
    )
    quantidade = models.PositiveIntegerField("quantidade")
    preco = models.DecimalField(
        "preço unitário",
        max_digits=10,
        decimal_places=2,
        help_text="Preço praticado no momento da venda.",
    )

    class Meta:
        verbose_name = "item de venda"
        verbose_name_plural = "itens de venda"
        ordering = ["venda_id", "id"]
        indexes = [
            models.Index(fields=["produto"], name="itemvenda_produto_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantidade__gt=0),
                name="itemvenda_quantidade_positiva",
            ),
            models.CheckConstraint(
                condition=Q(preco__gte=0),
                name="itemvenda_preco_nao_negativo",
            ),
        ]

    def __str__(self):
        return f"{self.quantidade}x {self.produto} @ R$ {self.preco}"

    @property
    def subtotal(self):
        return self.quantidade * self.preco
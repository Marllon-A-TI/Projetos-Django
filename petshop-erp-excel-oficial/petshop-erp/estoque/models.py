from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from core.models import ModeloImutavel
from produtos.models import Produto


class MovimentacaoEstoque(ModeloImutavel):
    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saída"
        AJUSTE = "AJUSTE", "Ajuste"
        VENDA = "VENDA", "Venda"

    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name="movimentacoes",
        verbose_name="produto",
    )
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices)
    quantidade = models.PositiveIntegerField(
        "quantidade",
        help_text=(
            "Unidades movimentadas. No AJUSTE, é o novo estoque contado."
        ),
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimentacoes_estoque",
        verbose_name="usuário responsável",
    )
    data = models.DateTimeField("data", auto_now_add=True)
    observacao = models.TextField("observação", blank=True, default="")
    quantidade_anterior = models.PositiveIntegerField("quantidade anterior")
    quantidade_nova = models.PositiveIntegerField("quantidade nova")

    class Meta:
        verbose_name = "movimentação de estoque"
        verbose_name_plural = "movimentações de estoque"
        ordering = ["-data", "-id"]
        indexes = [
            models.Index(
                fields=["produto", "-data"], name="mov_estoque_produto_data_idx"
            ),
            models.Index(fields=["-data"], name="mov_estoque_data_idx"),
            models.Index(fields=["tipo"], name="mov_estoque_tipo_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo="AJUSTE") | Q(quantidade__gt=0),
                name="mov_estoque_quantidade_positiva",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        tipo="ENTRADA",
                        quantidade_nova=F("quantidade_anterior") + F("quantidade"),
                    )
                    | Q(
                        tipo__in=["SAIDA", "VENDA"],
                        quantidade_nova=F("quantidade_anterior") - F("quantidade"),
                    )
                    | Q(tipo="AJUSTE", quantidade_nova=F("quantidade"))
                ),
                name="mov_estoque_saldo_consistente",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_tipo_display()} de {self.quantidade} "
            f"- {self.produto} ({self.quantidade_anterior} → {self.quantidade_nova})"
        )

    @property
    def variacao(self):
        return self.quantidade_nova - self.quantidade_anterior

    @classmethod
    @transaction.atomic
    def registrar(cls, *, produto, tipo, quantidade, usuario, observacao=""):
        """
        ÚNICO caminho permitido para alterar o estoque de um produto.

        - ENTRADA: soma `quantidade` ao estoque.
        - SAIDA / VENDA: subtrai `quantidade` (erro se faltar estoque).
        - AJUSTE: define o estoque como `quantidade` (contagem).

        Bloqueia a linha do produto durante a operação para evitar
        corrida entre vendedores simultâneos.
        """
        if tipo not in cls.Tipo.values:
            raise ValidationError("Tipo de movimentação inválido.", code="tipo_invalido")

        if usuario is None or not getattr(usuario, "pk", None):
            raise ValidationError(
                "É obrigatório informar o usuário responsável pela movimentação.",
                code="usuario_obrigatorio",
            )

        try:
            quantidade = int(quantidade)
        except (TypeError, ValueError):
            raise ValidationError("Quantidade inválida.", code="quantidade_invalida")

        if quantidade < 0 or (tipo != cls.Tipo.AJUSTE and quantidade == 0):
            raise ValidationError(
                "A quantidade deve ser maior que zero.", code="quantidade_invalida"
            )

        bloqueado = Produto.objects.select_for_update().get(pk=produto.pk)
        anterior = bloqueado.quantidade or 0

        if tipo == cls.Tipo.ENTRADA:
            nova = anterior + quantidade
        elif tipo in (cls.Tipo.SAIDA, cls.Tipo.VENDA):
            if quantidade > anterior:
                raise ValidationError(
                    f"Estoque insuficiente para '{bloqueado}': "
                    f"disponível {anterior}, solicitado {quantidade}.",
                    code="estoque_insuficiente",
                )
            nova = anterior - quantidade
        else:
            nova = quantidade

        bloqueado._estoque_liberado = True
        try:
            bloqueado.quantidade = nova
            bloqueado.save(update_fields=["quantidade", "atualizado_em"])
        finally:
            bloqueado._estoque_liberado = False

        movimentacao = cls.objects.create(
            produto=bloqueado,
            tipo=tipo,
            quantidade=quantidade,
            usuario=usuario,
            observacao=observacao or "",
            quantidade_anterior=anterior,
            quantidade_nova=nova,
        )

        # Reflete o novo estoque no objeto recebido pelo chamador.
        produto.quantidade = nova
        produto._quantidade_original = nova

        return movimentacao

    @classmethod
    @transaction.atomic
    def registrar_lote(cls, *, movimentos, usuario, observacao=""):
        """
        Versão em lote de registrar(), para importações grandes.

        `movimentos` é uma lista de (produto_pk, tipo, quantidade), no máximo
        um por produto, com tipo ENTRADA (soma) ou AJUSTE (define o estoque).
        As mesmas regras de registrar() valem: as linhas dos produtos são
        bloqueadas, o saldo é conferido pelo banco (constraints) e cada
        movimento deixa seu histórico. Usa poucas consultas (bulk_create e
        bulk_update) em vez de uma por produto.

        Retorna a quantidade de movimentações gravadas.
        """
        if not movimentos:
            return 0

        if usuario is None or not getattr(usuario, "pk", None):
            raise ValidationError(
                "É obrigatório informar o usuário responsável pela movimentação.",
                code="usuario_obrigatorio",
            )

        pks = [pk for pk, _, _ in movimentos]
        if len(set(pks)) != len(pks):
            raise ValidationError(
                "Há mais de uma movimentação para o mesmo produto.",
                code="produto_repetido",
            )
        for _, tipo, quantidade in movimentos:
            if tipo not in (cls.Tipo.ENTRADA, cls.Tipo.AJUSTE):
                raise ValidationError(
                    "Tipo de movimentação inválido para lote.", code="tipo_invalido"
                )
            if quantidade < 0 or (tipo == cls.Tipo.ENTRADA and quantidade == 0):
                raise ValidationError(
                    "Quantidade inválida.", code="quantidade_invalida"
                )

        # Bloqueio em ordem de pk (evita deadlock) e em partes (limite de
        # parâmetros da consulta).
        produtos = {}
        ordenados = sorted(pks)
        for inicio in range(0, len(ordenados), 2000):
            consulta = (
                Produto.objects.select_for_update()
                .filter(pk__in=ordenados[inicio : inicio + 2000])
                .order_by("pk")
            )
            for produto in consulta:
                produtos[produto.pk] = produto
        if len(produtos) != len(pks):
            raise ValidationError("Produto não encontrado.", code="produto_inexistente")

        agora = timezone.now()
        historico, alterados = [], []
        for pk, tipo, quantidade in movimentos:
            produto = produtos[pk]
            anterior = produto.quantidade or 0
            nova = anterior + quantidade if tipo == cls.Tipo.ENTRADA else quantidade
            historico.append(
                cls(
                    produto_id=pk,
                    tipo=tipo,
                    quantidade=quantidade,
                    usuario=usuario,
                    observacao=observacao or "",
                    quantidade_anterior=anterior,
                    quantidade_nova=nova,
                )
            )
            produto.quantidade = nova
            produto.atualizado_em = agora
            alterados.append(produto)

        cls.objects.bulk_create(historico, batch_size=1000)
        # bulk_update não passa por Produto.save(): é o caminho autorizado aqui,
        # dentro desta transação e com as linhas bloqueadas.
        Produto.objects.bulk_update(
            alterados, ["quantidade", "atualizado_em"], batch_size=1000
        )
        return len(historico)

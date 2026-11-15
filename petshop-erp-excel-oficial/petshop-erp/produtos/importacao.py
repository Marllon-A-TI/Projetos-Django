"""
Gravação da importação de produtos no banco (as linhas já vêm validadas
por produtos/excel.py).

Regras:
- A chave de ligação é o código de barras.
- Produto existente: atualiza preço de venda, preço de custo (se informado)
  e estoque. Nome, categoria, fornecedor, estoque mínimo e situação são
  preservados.
- Produto novo: é criado com todos os campos da planilha.
- Estoque: sempre por MovimentacaoEstoque (a regra do projeto). Produto
  existente recebe um AJUSTE para o valor da planilha (contagem); produto
  novo recebe uma ENTRADA com o estoque inicial.
"""

from collections import defaultdict
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from estoque.models import MovimentacaoEstoque

from .models import Produto

LOTE_CONSULTA = 2000
OBSERVACAO = "Importação Excel"


class ImportacaoInvalida(Exception):
    """Problema encontrado ao confrontar a planilha com o cadastro."""

    def __init__(self, erros):
        super().__init__("; ".join(erros))
        self.erros = erros


@dataclass
class ResultadoImportacao:
    criados: int = 0
    atualizados: int = 0
    sem_alteracao: int = 0
    movimentacoes: int = 0


def _buscar_existentes(codigos):
    """Produtos já cadastrados, por código de barras (com a linha travada)."""
    encontrados = defaultdict(list)
    for inicio in range(0, len(codigos), LOTE_CONSULTA):
        parte = codigos[inicio : inicio + LOTE_CONSULTA]
        consulta = (
            Produto.objects.select_for_update()
            .filter(codigo_barras__in=parte)
            .order_by("pk")
        )
        for produto in consulta:
            encontrados[produto.codigo_barras].append(produto)
    return encontrados


@transaction.atomic
def importar_produtos(linhas, usuario):
    """
    Grava as linhas validadas. Tudo ou nada: qualquer exceção desfaz tudo.
    Levanta ImportacaoInvalida se o cadastro tiver código de barras repetido
    (a importação não tem como saber qual produto atualizar).
    """
    resultado = ResultadoImportacao()
    existentes = _buscar_existentes([linha["codigo"] for linha in linhas])

    ambiguos = [
        f"Linha {linha['linha']}: o código {linha['codigo']} está em "
        f"{len(existentes[linha['codigo']])} produtos do cadastro. "
        "Corrija o cadastro antes de importar."
        for linha in linhas
        if len(existentes.get(linha["codigo"], ())) > 1
    ]
    if ambiguos:
        raise ImportacaoInvalida(ambiguos)

    novos, linhas_novas = [], []
    para_atualizar, ajustes = [], []
    agora = timezone.now()

    for linha in linhas:
        lista = existentes.get(linha["codigo"])
        if lista:
            produto = lista[0]
            mudou = False
            if produto.preco_venda != linha["preco_venda"]:
                produto.preco_venda = linha["preco_venda"]
                mudou = True
            if linha["preco_custo"] is not None and produto.preco_custo != linha["preco_custo"]:
                produto.preco_custo = linha["preco_custo"]
                mudou = True
            if mudou:
                produto.atualizado_em = agora
                para_atualizar.append(produto)
            if (produto.quantidade or 0) != linha["estoque"]:
                ajustes.append(
                    (produto.pk, MovimentacaoEstoque.Tipo.AJUSTE, linha["estoque"])
                )
            if mudou or (produto.quantidade or 0) != linha["estoque"]:
                resultado.atualizados += 1
            else:
                resultado.sem_alteracao += 1
        else:
            novos.append(
                Produto(
                    nome=linha["nome"],
                    codigo_barras=linha["codigo"],
                    categoria=linha["categoria"] or "",
                    fornecedor=linha["fornecedor"] or "",
                    estoque_minimo=linha["estoque_minimo"] or 0,
                    preco_custo=linha["preco_custo"],
                    preco_venda=linha["preco_venda"],
                    ativo=True if linha["ativo"] is None else linha["ativo"],
                    quantidade=0,  # o estoque inicial entra por movimentação
                )
            )
            linhas_novas.append(linha)

    # Preços: bulk_update sem o campo "quantidade" (que só muda por movimentação).
    if para_atualizar:
        Produto.objects.bulk_update(
            para_atualizar,
            ["preco_venda", "preco_custo", "atualizado_em"],
            batch_size=1000,
        )

    if novos:
        Produto.objects.bulk_create(novos, batch_size=1000)
        resultado.criados = len(novos)
        for produto, linha in zip(novos, linhas_novas):
            if linha["estoque"] > 0:
                ajustes.append(
                    (produto.pk, MovimentacaoEstoque.Tipo.ENTRADA, linha["estoque"])
                )

    resultado.movimentacoes = MovimentacaoEstoque.registrar_lote(
        movimentos=ajustes, usuario=usuario, observacao=OBSERVACAO
    )
    return resultado

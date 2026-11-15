"""
Gravação da importação de produtos no banco (as linhas já vêm validadas
por produtos/excel.py).

Regras:
- A chave de ligação é o código de barras. Na linha sem código, é o nome
  (exatamente igual ao do cadastro).
- Produto existente: atualiza preço de venda, preço de custo e estoque, mas
  só os que a planilha informar (célula em branco não apaga nada). Nome,
  categoria, fornecedor, estoque mínimo e situação são preservados.
- Produto novo: é criado com todos os campos da planilha (os em branco
  ficam vazios, com estoque 0).
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


def _buscar_existentes(valores, campo="codigo_barras"):
    """Produtos já cadastrados, por código de barras ou nome (linha travada)."""
    encontrados = defaultdict(list)
    for inicio in range(0, len(valores), LOTE_CONSULTA):
        parte = valores[inicio : inicio + LOTE_CONSULTA]
        consulta = (
            Produto.objects.select_for_update()
            .filter(**{f"{campo}__in": parte})
            .order_by("pk")
        )
        for produto in consulta:
            encontrados[getattr(produto, campo)].append(produto)
    return encontrados


@transaction.atomic
def importar_produtos(linhas, usuario):
    """
    Grava as linhas validadas. Tudo ou nada: qualquer exceção desfaz tudo.
    Levanta ImportacaoInvalida se o cadastro tiver código de barras (ou nome,
    nas linhas sem código) repetido: a importação não tem como saber qual
    produto atualizar.
    """
    resultado = ResultadoImportacao()
    por_codigo = _buscar_existentes([l["codigo"] for l in linhas if l["codigo"]])
    por_nome = _buscar_existentes(
        [l["nome"] for l in linhas if not l["codigo"]], campo="nome"
    )

    def candidatos(linha):
        """(produtos do cadastro que casam com a linha, como ela é identificada)."""
        if linha["codigo"]:
            return por_codigo.get(linha["codigo"], []), f"o código {linha['codigo']}"
        return por_nome.get(linha["nome"], []), f'o nome "{linha["nome"]}"'

    ambiguos, usados = [], {}
    for linha in linhas:
        lista, quem = candidatos(linha)
        if len(lista) > 1:
            ambiguos.append(
                f"Linha {linha['linha']}: {quem} está em {len(lista)} produtos "
                "do cadastro. Corrija o cadastro antes de importar."
            )
        elif lista:
            if lista[0].pk in usados:
                ambiguos.append(
                    f"Linha {linha['linha']}: {quem} é o mesmo produto da linha "
                    f"{usados[lista[0].pk]}."
                )
            else:
                usados[lista[0].pk] = linha["linha"]
    if ambiguos:
        raise ImportacaoInvalida(ambiguos)

    novos, linhas_novas = [], []
    para_atualizar, ajustes = [], []
    agora = timezone.now()

    for linha in linhas:
        lista, _ = candidatos(linha)
        if lista:
            produto = lista[0]
            mudou = False
            if linha["preco_venda"] is not None and produto.preco_venda != linha["preco_venda"]:
                produto.preco_venda = linha["preco_venda"]
                mudou = True
            if linha["preco_custo"] is not None and produto.preco_custo != linha["preco_custo"]:
                produto.preco_custo = linha["preco_custo"]
                mudou = True
            if mudou:
                produto.atualizado_em = agora
                para_atualizar.append(produto)
            estoque_mudou = (
                linha["estoque"] is not None
                and (produto.quantidade or 0) != linha["estoque"]
            )
            if estoque_mudou:
                ajustes.append(
                    (produto.pk, MovimentacaoEstoque.Tipo.AJUSTE, linha["estoque"])
                )
            if mudou or estoque_mudou:
                resultado.atualizados += 1
            else:
                resultado.sem_alteracao += 1
        else:
            novos.append(
                Produto(
                    nome=linha["nome"] or "",
                    codigo_barras=linha["codigo"] or "",
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
            if (linha["estoque"] or 0) > 0:
                ajustes.append(
                    (produto.pk, MovimentacaoEstoque.Tipo.ENTRADA, linha["estoque"])
                )

    resultado.movimentacoes = MovimentacaoEstoque.registrar_lote(
        movimentos=ajustes, usuario=usuario, observacao=OBSERVACAO
    )
    return resultado

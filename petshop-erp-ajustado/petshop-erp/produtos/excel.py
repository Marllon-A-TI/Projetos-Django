"""
Leitura, validação e geração de planilhas XLSX de produtos.

Este módulo NÃO acessa o banco nem importa o Django: só trata a planilha.
A gravação no banco fica em produtos/importacao.py.

Usa apenas o openpyxl (a planilha é lida em modo somente leitura, linha a
linha, para gastar pouca memória).
"""

import unicodedata
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell

MAX_LINHAS = 20000
MAX_ERROS = 100
MAX_ESTOQUE = 2_147_483_647  # limite do PositiveIntegerField
MAX_PRECO = Decimal("99999999.99")  # DecimalField(max_digits=10, decimal_places=2)
CENTAVOS = Decimal("0.01")

# Ordem e títulos das colunas da exportação (e modelo da importação).
COLUNAS_EXPORTACAO = [
    ("codigo", "Código de barras"),
    ("nome", "Nome"),
    ("categoria", "Categoria"),
    ("fornecedor", "Fornecedor"),
    ("estoque", "Estoque"),
    ("estoque_minimo", "Estoque mínimo"),
    ("preco_custo", "Preço de custo"),
    ("preco_venda", "Preço de venda"),
    ("ativo", "Ativo"),
]

# Nomes aceitos no cabeçalho (comparados sem acento, em minúsculas).
ALIASES = {
    "codigo": {"codigo de barras", "codigo", "cod barras", "ean"},
    "nome": {"nome", "nome do produto", "produto", "descricao"},
    "categoria": {"categoria"},
    "fornecedor": {"fornecedor"},
    "estoque": {"estoque", "quantidade", "qtd"},
    "estoque_minimo": {"estoque minimo", "minimo"},
    "preco_custo": {"preco de custo", "custo", "preco custo"},
    "preco_venda": {"preco de venda", "venda", "preco venda", "preco"},
    "ativo": {"ativo", "situacao"},
}
# Nenhuma coluna é obrigatória: a planilha só precisa ter ao menos uma coluna
# reconhecida e, em cada linha, o código de barras ou o nome.
OBRIGATORIAS = ()
TITULO = dict(COLUNAS_EXPORTACAO)

LIMITES_TEXTO = {"codigo": 50, "nome": 150, "categoria": 100, "fornecedor": 150}

VERDADEIRO = {"sim", "s", "1", "true", "verdadeiro", "ativo", "x"}
FALSO = {"nao", "n", "0", "false", "falso", "inativo"}


class PlanilhaInvalida(Exception):
    """Arquivo que não pôde ser lido como planilha XLSX."""


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.lower().split())


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _texto(valor):
    """Texto limpo. Números inteiros viram '123', não '123.0'."""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def _inteiro(valor):
    """Inteiro >= 0 ou levanta ValueError com a mensagem para o usuário."""
    if isinstance(valor, bool):
        raise ValueError("deve ser um número inteiro")
    if isinstance(valor, str):
        bruto = valor.strip()
        try:
            numero = Decimal(bruto)
        except InvalidOperation:
            raise ValueError("deve ser um número inteiro") from None
    else:
        try:
            numero = Decimal(str(valor))
        except InvalidOperation:
            raise ValueError("deve ser um número inteiro") from None
    if not numero.is_finite() or numero != numero.to_integral_value():
        raise ValueError("deve ser um número inteiro")
    if numero < 0:
        raise ValueError("não pode ser negativo")
    if numero > MAX_ESTOQUE:
        raise ValueError("valor muito grande")
    return int(numero)


def _preco(valor):
    """Decimal >= 0 com até 2 casas, ou levanta ValueError."""
    if isinstance(valor, bool):
        raise ValueError("deve ser um valor numérico")
    if isinstance(valor, str):
        bruto = valor.upper().replace("R$", "").replace(" ", "").strip()
        if "," in bruto:  # formato brasileiro: 1.234,56
            bruto = bruto.replace(".", "").replace(",", ".")
    else:
        bruto = str(valor)
    try:
        numero = Decimal(bruto)
    except InvalidOperation:
        raise ValueError("deve ser um valor numérico") from None
    if not numero.is_finite():
        raise ValueError("deve ser um valor numérico")
    if numero < 0:
        raise ValueError("não pode ser negativo")
    if numero != numero.quantize(CENTAVOS):
        raise ValueError("use no máximo 2 casas decimais")
    if numero > MAX_PRECO:
        raise ValueError("valor muito grande")
    return numero.quantize(CENTAVOS)


def _booleano(valor):
    if isinstance(valor, bool):
        return valor
    chave = _normalizar(valor)
    if chave in VERDADEIRO:
        return True
    if chave in FALSO:
        return False
    raise ValueError("use Sim ou Não")


def _mapear_cabecalho(cabecalho):
    """Retorna ({campo: índice da coluna}, [erros])."""
    mapa, erros = {}, []
    for indice, titulo in enumerate(cabecalho):
        if _vazio(titulo):
            continue
        chave = _normalizar(titulo)
        for campo, nomes in ALIASES.items():
            if chave in nomes:
                if campo in mapa:
                    erros.append(f"A coluna '{TITULO[campo]}' aparece mais de uma vez.")
                else:
                    mapa[campo] = indice
                break
    faltando = [TITULO[c] for c in OBRIGATORIAS if c not in mapa]
    if faltando:
        erros.append("Colunas obrigatórias ausentes: " + ", ".join(faltando) + ".")
    if not mapa:
        erros.append(
            "Nenhuma coluna reconhecida na primeira linha. Use títulos como "
            + ", ".join(TITULO.values())
            + "."
        )
    return mapa, erros


def ler_planilha(arquivo):
    """
    Lê e valida o XLSX enviado. `arquivo` é qualquer objeto de arquivo
    (inclusive o UploadedFile do Django).

    Retorna (linhas, erros):
    - linhas: lista de dicionários prontos para gravar, cada um com a chave
      "linha" (número da linha na planilha) e os campos do produto.
      Campos em branco ficam como None.
    - erros: lista de mensagens amigáveis. Se houver qualquer erro, nada
      deve ser gravado.
    """
    try:
        pasta = load_workbook(arquivo, read_only=True, data_only=True)
    except Exception:
        raise PlanilhaInvalida(
            "Não foi possível ler o arquivo. Envie uma planilha Excel (.xlsx) válida."
        ) from None

    try:
        if not pasta.worksheets:
            raise PlanilhaInvalida("A planilha não tem nenhuma aba.")
        try:
            linhas_brutas = pasta.worksheets[0].iter_rows(values_only=True)
            cabecalho = next(linhas_brutas, None)
            if not cabecalho:
                raise PlanilhaInvalida("A planilha está vazia.")

            mapa, erros = _mapear_cabecalho(cabecalho)
            if erros:
                return [], erros

            linhas, vistos, vistos_nome = [], {}, {}
            total_erros = 0

            def registrar_erro(texto):
                nonlocal total_erros
                total_erros += 1
                if len(erros) < MAX_ERROS:
                    erros.append(texto)

            for numero, bruta in enumerate(linhas_brutas, start=2):
                if all(_vazio(c) for c in bruta):
                    continue
                if len(linhas) + total_erros >= MAX_LINHAS:
                    return [], [
                        f"A planilha tem mais de {MAX_LINHAS} linhas. "
                        "Divida em arquivos menores."
                    ]

                def celula(campo):
                    indice = mapa.get(campo)
                    if indice is None or indice >= len(bruta):
                        return None
                    return bruta[indice]

                registro = {"linha": numero}
                problemas = []

                for campo in ("codigo", "nome", "categoria", "fornecedor"):
                    valor = celula(campo)
                    if _vazio(valor):
                        registro[campo] = None
                        if campo in OBRIGATORIAS:
                            problemas.append(f"'{TITULO[campo]}' está vazio")
                        continue
                    texto = _texto(valor)
                    if len(texto) > LIMITES_TEXTO[campo]:
                        problemas.append(
                            f"'{TITULO[campo]}' passa de {LIMITES_TEXTO[campo]} caracteres"
                        )
                    registro[campo] = texto

                conversores = (
                    ("estoque", _inteiro),
                    ("estoque_minimo", _inteiro),
                    ("preco_custo", _preco),
                    ("preco_venda", _preco),
                    ("ativo", _booleano),
                )
                for campo, converter in conversores:
                    valor = celula(campo)
                    if _vazio(valor):
                        registro[campo] = None
                        if campo in OBRIGATORIAS:
                            problemas.append(f"'{TITULO[campo]}' está vazio")
                        continue
                    try:
                        registro[campo] = converter(valor)
                    except ValueError as erro:
                        problemas.append(f"'{TITULO[campo]}' {erro} (valor: {valor!r})")

                codigo = registro.get("codigo")
                if codigo:
                    if codigo in vistos:
                        problemas.append(
                            f"código de barras repetido (já usado na linha {vistos[codigo]})"
                        )
                    else:
                        vistos[codigo] = numero
                elif not registro.get("nome"):
                    problemas.append("informe pelo menos o código de barras ou o nome")
                else:
                    # Sem código, o produto é identificado pelo nome. Uma linha
                    # igual à anterior não acrescenta nada e é ignorada; com
                    # dados diferentes, não há como saber qual vale.
                    dados = {c: v for c, v in registro.items() if c != "linha"}
                    anterior = vistos_nome.get(registro["nome"])
                    if anterior is None:
                        vistos_nome[registro["nome"]] = (numero, dados)
                    elif anterior[1] == dados:
                        continue
                    else:
                        problemas.append(
                            "nome repetido sem código de barras e com dados diferentes "
                            f"(já usado na linha {anterior[0]})"
                        )

                if problemas:
                    registrar_erro(f"Linha {numero}: " + "; ".join(problemas) + ".")
                else:
                    linhas.append(registro)

            if total_erros > len(erros):
                erros.append(f"... e mais {total_erros - len(erros)} linha(s) com erro.")
            if not linhas and not erros:
                erros.append("A planilha não tem nenhum produto (só o cabeçalho).")
            return linhas, erros
        except PlanilhaInvalida:
            raise
        except Exception:
            raise PlanilhaInvalida(
                "O arquivo está corrompido ou fora do formato esperado."
            ) from None
    finally:
        pasta.close()


def gerar_xlsx(registros):
    """
    Gera o XLSX da exportação e devolve os bytes.

    `registros` é um iterável de tuplas na ordem de COLUNAS_EXPORTACAO:
    (codigo, nome, categoria, fornecedor, estoque, estoque_minimo,
     preco_custo, preco_venda, ativo).

    Usa o modo write_only do openpyxl (memória baixa) e grava textos sempre
    como texto: evita que um nome começando com "=" seja executado como
    fórmula no Excel e preserva zeros à esquerda do código de barras.
    """
    pasta = Workbook(write_only=True)
    folha = pasta.create_sheet("Produtos")
    folha.freeze_panes = "A2"
    for letra, largura in zip("ABCDEFGHI", (20, 40, 22, 26, 10, 15, 16, 16, 8)):
        folha.column_dimensions[letra].width = largura

    folha.append([titulo for _, titulo in COLUNAS_EXPORTACAO])

    def texto(valor):
        celula = WriteOnlyCell(folha, value=valor or "")
        celula.data_type = "s"
        return celula

    def dinheiro(valor):
        celula = WriteOnlyCell(folha, value=valor)
        celula.number_format = "#,##0.00"
        return celula

    for (codigo, nome, categoria, fornecedor, estoque, minimo, custo, venda, ativo) in registros:
        folha.append(
            [
                texto(codigo),
                texto(nome),
                texto(categoria),
                texto(fornecedor),
                estoque or 0,
                minimo,
                dinheiro(custo),
                dinheiro(venda),
                "Sim" if ativo else "Não",
            ]
        )

    saida = BytesIO()
    pasta.save(saida)
    return saida.getvalue()

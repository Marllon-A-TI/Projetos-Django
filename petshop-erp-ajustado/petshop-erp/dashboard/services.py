"""
Cálculo dos KPIs e dos dados dos gráficos do dashboard.
Todas as consultas usam agregação no banco (poucas queries, sem laços
sobre registros).
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from financeiro.models import ContaPagar, ContaReceber, FluxoCaixa
from produtos.models import Produto
from vendas.models import ItemVenda, Venda

ZERO = Decimal("0.00")

DIAS_GRAFICO_VENDAS = 30
MESES_GRAFICOS = 12
TOP_PRODUTOS = 15
TOP_MAIS_VENDIDOS = 10
DIAS_MAIS_VENDIDOS = 90
LIMITE_LISTA_ESTOQUE_BAIXO = 10

VALOR_ESTOQUE = ExpressionWrapper(
    F("quantidade") * F("preco_custo"),
    output_field=DecimalField(max_digits=16, decimal_places=2),
)


def _valor(numero):
    return numero if numero is not None else ZERO


def _numero(valor):
    """Converte Decimal/None em float, para serializar em JSON."""
    return float(valor or 0)


def _nome(produto):
    return produto.nome or f"Produto #{produto.pk}"


def _primeiro_dia_do_mes(data, deslocamento_meses):
    indice = data.year * 12 + (data.month - 1) + deslocamento_meses
    return data.replace(year=indice // 12, month=indice % 12 + 1, day=1)


def calcular_kpis(hoje):
    inicio_mes = hoje.replace(day=1)
    inicio_ano = hoje.replace(month=1, day=1)

    produtos = Produto.objects.aggregate(
        produtos_cadastrados=Count("id"),
        total_produtos=Sum("quantidade"),
    )
    valor_estoque = Produto.objects.filter(
        quantidade__gt=0, preco_custo__isnull=False
    ).aggregate(total=Sum(VALOR_ESTOQUE))["total"]

    vendas = Venda.objects.filter(data__gte=inicio_ano, data__lte=hoje).aggregate(
        vendas_dia=Count("id", filter=Q(data=hoje)),
        vendas_mes=Count("id", filter=Q(data__gte=inicio_mes)),
        vendas_ano=Count("id"),
        faturamento_dia=Sum("valor_total", filter=Q(data=hoje)),
        faturamento_mes=Sum("valor_total", filter=Q(data__gte=inicio_mes)),
        faturamento_ano=Sum("valor_total"),
    )

    return {
        "produtos_cadastrados": produtos["produtos_cadastrados"] or 0,
        "total_produtos": produtos["total_produtos"] or 0,
        "valor_total_estoque": _valor(valor_estoque),
        "produtos_estoque_baixo": Produto.objects.ativos().estoque_baixo().count(),
        "vendas_dia": vendas["vendas_dia"] or 0,
        "vendas_mes": vendas["vendas_mes"] or 0,
        "vendas_ano": vendas["vendas_ano"] or 0,
        "faturamento_dia": _valor(vendas["faturamento_dia"]),
        "faturamento_mes": _valor(vendas["faturamento_mes"]),
        "faturamento_ano": _valor(vendas["faturamento_ano"]),
        "contas_pagar": ContaPagar.objects.pendentes().total(),
        "contas_pagar_atrasadas": ContaPagar.objects.atrasadas().total(),
        "contas_receber": ContaReceber.objects.pendentes().total(),
        "contas_receber_atrasadas": ContaReceber.objects.atrasadas().total(),
        "saldo_caixa": FluxoCaixa.saldo_atual(),
    }


def calcular_graficos(hoje):
    # --- Produtos (estoque) ------------------------------------------------
    por_quantidade = list(
        Produto.objects.ativos()
        .filter(quantidade__gt=0)
        .order_by("-quantidade", "nome")[:TOP_PRODUTOS]
    )
    por_valor = list(
        Produto.objects.ativos()
        .filter(quantidade__gt=0, preco_custo__isnull=False)
        .annotate(valor_estoque=VALOR_ESTOQUE)
        .filter(valor_estoque__gt=0)
        .order_by("-valor_estoque", "nome")[:TOP_PRODUTOS]
    )

    # --- Vendas por dia (últimos N dias, com zeros nos dias sem venda) -----
    inicio_dias = hoje - timedelta(days=DIAS_GRAFICO_VENDAS - 1)
    linhas_dia = {
        linha["data"]: linha
        for linha in Venda.objects.filter(data__gte=inicio_dias, data__lte=hoje)
        .values("data")
        .annotate(quantidade=Count("id"), faturamento=Sum("valor_total"))
        .order_by("data")
    }
    dias = [inicio_dias + timedelta(days=i) for i in range(DIAS_GRAFICO_VENDAS)]

    # --- Vendas e faturamento por mês (últimos N meses) --------------------
    meses = [
        _primeiro_dia_do_mes(hoje, -i) for i in range(MESES_GRAFICOS - 1, -1, -1)
    ]
    linhas_mes = {
        linha["mes"]: linha
        for linha in Venda.objects.filter(data__gte=meses[0], data__lte=hoje)
        .annotate(mes=TruncMonth("data"))
        .values("mes")
        .annotate(quantidade=Count("id"), faturamento=Sum("valor_total"))
        .order_by("mes")
    }

    # --- Produtos mais vendidos --------------------------------------------
    inicio_vendidos = hoje - timedelta(days=DIAS_MAIS_VENDIDOS - 1)
    mais_vendidos = list(
        ItemVenda.objects.filter(
            venda__data__gte=inicio_vendidos, venda__data__lte=hoje
        )
        .values("produto_id", "produto__nome")
        .annotate(total=Sum("quantidade"))
        .order_by("-total", "produto__nome")[:TOP_MAIS_VENDIDOS]
    )

    return {
        "produtos_quantidade": {
            "labels": [_nome(p) for p in por_quantidade],
            "valores": [p.quantidade for p in por_quantidade],
        },
        "valor_estoque": {
            "labels": [_nome(p) for p in por_valor],
            "valores": [_numero(p.valor_estoque) for p in por_valor],
        },
        "vendas_dia": {
            "labels": [d.strftime("%d/%m") for d in dias],
            "valores": [linhas_dia.get(d, {}).get("quantidade", 0) for d in dias],
            "faturamento": [
                _numero(linhas_dia.get(d, {}).get("faturamento")) for d in dias
            ],
        },
        "vendas_mes": {
            "labels": [m.strftime("%m/%Y") for m in meses],
            "valores": [linhas_mes.get(m, {}).get("quantidade", 0) for m in meses],
        },
        "mais_vendidos": {
            "labels": [
                linha["produto__nome"] or f"Produto #{linha['produto_id']}"
                for linha in mais_vendidos
            ],
            "valores": [linha["total"] for linha in mais_vendidos],
        },
        "faturamento_mensal": {
            "labels": [m.strftime("%m/%Y") for m in meses],
            "valores": [
                _numero(linhas_mes.get(m, {}).get("faturamento")) for m in meses
            ],
        },
    }


def montar_dashboard(hoje=None):
    hoje = hoje or timezone.localdate()
    return {
        "kpis": calcular_kpis(hoje),
        "graficos": calcular_graficos(hoje),
        "estoque_baixo_lista": list(
            Produto.objects.ativos()
            .estoque_baixo()
            .order_by("quantidade", "nome")[:LIMITE_LISTA_ESTOQUE_BAIXO]
        ),
        "atualizado_em": timezone.localtime(),
    }
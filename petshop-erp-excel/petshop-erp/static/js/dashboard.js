(function () {
  "use strict";

  var elementoDados = document.getElementById("dados-graficos");
  var aviso = document.getElementById("graficos-erro");

  if (!elementoDados || typeof window.Chart === "undefined") {
    if (aviso) {
      aviso.classList.remove("d-none");
    }
    return;
  }

  var dados = JSON.parse(elementoDados.textContent);

  var formatoMoeda = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
  var formatoInteiro = new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: 0,
  });
  var formatoCompacto = new Intl.NumberFormat("pt-BR", {
    notation: "compact",
    maximumFractionDigits: 1,
  });

  var CORES = {
    azul: "#0d6efd",
    verde: "#198754",
    laranja: "#fd7e14",
    roxo: "#6f42c1",
  };

  Chart.defaults.font.family = window.getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = "#495057";
  Chart.defaults.maintainAspectRatio = false;

  // --- Utilidades ----------------------------------------------------------

  function transparente(hex, alfa) {
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return "rgba(" + r + ", " + g + ", " + b + ", " + alfa + ")";
  }

  function abreviar(texto, limite) {
    texto = String(texto);
    return texto.length > limite ? texto.slice(0, limite - 1) + "\u2026" : texto;
  }

  function textoMoeda(valor) {
    return formatoMoeda.format(valor);
  }

  function textoMoedaCompacta(valor) {
    return "R$ " + formatoCompacto.format(valor);
  }

  function textoInteiro(valor) {
    return formatoInteiro.format(valor);
  }

  function algumValorPositivo(listas) {
    return listas.some(function (lista) {
      return lista.some(function (valor) {
        return valor > 0;
      });
    });
  }

  function criarGrafico(idCanvas, configuracao, listasDeValores) {
    var canvas = document.getElementById(idCanvas);
    if (!canvas) {
      return;
    }
    var caixa = canvas.closest(".grafico-box");
    var vazio = caixa.parentElement.querySelector(".grafico-vazio");

    if (!algumValorPositivo(listasDeValores)) {
      caixa.classList.add("d-none");
      vazio.classList.remove("d-none");
      return;
    }
    new Chart(canvas, configuracao);
  }

  function barraHorizontal(rotulos, valores, cor, nomeSerie, textoValor, textoEixo, inteiro) {
    var configuracao = {
      type: "bar",
      data: {
        labels: rotulos,
        datasets: [
          {
            label: nomeSerie,
            data: valores,
            backgroundColor: cor,
            borderRadius: 3,
          },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (contexto) {
                return " " + textoValor(contexto.parsed.x);
              },
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: {
              callback: function (valor) {
                return textoEixo(valor);
              },
            },
          },
          y: {
            ticks: {
              callback: function (valor) {
                return abreviar(this.getLabelForValue(valor), 26);
              },
            },
          },
        },
      },
    };
    if (inteiro) {
      configuracao.options.scales.x.ticks.precision = 0;
    }
    return configuracao;
  }

  // --- 1) Vendas por dia: barras (vendas) + linha (faturamento) -----------

  var vendasDia = dados.vendas_dia;
  criarGrafico(
    "grafico-vendas-dia",
    {
      type: "bar",
      data: {
        labels: vendasDia.labels,
        datasets: [
          {
            type: "bar",
            label: "Vendas",
            data: vendasDia.valores,
            backgroundColor: transparente(CORES.azul, 0.7),
            borderRadius: 3,
            yAxisID: "y",
            order: 2,
          },
          {
            type: "line",
            label: "Faturamento",
            data: vendasDia.faturamento,
            borderColor: CORES.verde,
            backgroundColor: transparente(CORES.verde, 0.15),
            tension: 0.25,
            pointRadius: 2,
            yAxisID: "y1",
            order: 1,
          },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: true, position: "bottom" },
          tooltip: {
            callbacks: {
              label: function (contexto) {
                if (contexto.dataset.yAxisID === "y1") {
                  return " Faturamento: " + textoMoeda(contexto.parsed.y);
                }
                return " Vendas: " + textoInteiro(contexto.parsed.y);
              },
            },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            title: { display: true, text: "Vendas" },
          },
          y1: {
            beginAtZero: true,
            position: "right",
            grid: { drawOnChartArea: false },
            ticks: {
              callback: function (valor) {
                return textoMoedaCompacta(valor);
              },
            },
            title: { display: true, text: "Faturamento" },
          },
        },
      },
    },
    [vendasDia.valores, vendasDia.faturamento]
  );

  // --- 2) Produtos mais vendidos -------------------------------------------

  var maisVendidos = dados.mais_vendidos;
  criarGrafico(
    "grafico-mais-vendidos",
    barraHorizontal(
      maisVendidos.labels,
      maisVendidos.valores,
      CORES.laranja,
      "Unidades vendidas",
      function (valor) {
        return textoInteiro(valor) + " un.";
      },
      textoInteiro,
      true
    ),
    [maisVendidos.valores]
  );

  // --- 3) Vendas por mês ----------------------------------------------------

  var vendasMes = dados.vendas_mes;
  criarGrafico(
    "grafico-vendas-mes",
    {
      type: "bar",
      data: {
        labels: vendasMes.labels,
        datasets: [
          {
            label: "Vendas",
            data: vendasMes.valores,
            backgroundColor: transparente(CORES.roxo, 0.75),
            borderRadius: 3,
          },
        ],
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (contexto) {
                return " " + textoInteiro(contexto.parsed.y) + " venda(s)";
              },
            },
          },
        },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    },
    [vendasMes.valores]
  );

  // --- 4) Faturamento mensal ------------------------------------------------

  var faturamento = dados.faturamento_mensal;
  criarGrafico(
    "grafico-faturamento-mensal",
    {
      type: "line",
      data: {
        labels: faturamento.labels,
        datasets: [
          {
            label: "Faturamento",
            data: faturamento.valores,
            borderColor: CORES.verde,
            backgroundColor: transparente(CORES.verde, 0.15),
            fill: true,
            tension: 0.25,
            pointRadius: 3,
          },
        ],
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (contexto) {
                return " " + textoMoeda(contexto.parsed.y);
              },
            },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: function (valor) {
                return textoMoedaCompacta(valor);
              },
            },
          },
        },
      },
    },
    [faturamento.valores]
  );

  // --- 5) Quantidade de produtos por item -----------------------------------

  var porQuantidade = dados.produtos_quantidade;
  criarGrafico(
    "grafico-produtos-quantidade",
    barraHorizontal(
      porQuantidade.labels,
      porQuantidade.valores,
      CORES.azul,
      "Unidades em estoque",
      function (valor) {
        return textoInteiro(valor) + " un.";
      },
      textoInteiro,
      true
    ),
    [porQuantidade.valores]
  );

  // --- 6) Valor em estoque (a preço de custo) -------------------------------

  var porValor = dados.valor_estoque;
  criarGrafico(
    "grafico-valor-estoque",
    barraHorizontal(
      porValor.labels,
      porValor.valores,
      CORES.verde,
      "Valor em estoque",
      textoMoeda,
      textoMoedaCompacta,
      false
    ),
    [porValor.valores]
  );
})();
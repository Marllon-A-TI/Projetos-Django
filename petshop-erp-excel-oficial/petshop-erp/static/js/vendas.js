(function () {
  "use strict";

  var corpo = document.getElementById("itens");
  var modelo = document.getElementById("modelo-linha");
  var formulario = document.getElementById("form-venda");
  var totalForms = document.getElementById("id_form-TOTAL_FORMS");
  var totalTela = document.getElementById("total-venda");
  var leitor = document.getElementById("leitor-codigo");
  var aviso = document.getElementById("codigo-aviso");
  var botaoAdicionar = document.getElementById("adicionar-item");

  if (!corpo || !modelo || !formulario || !totalForms) {
    return;
  }

  var formatoMoeda = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  });

  function linhasAtivas() {
    return Array.prototype.filter.call(
      corpo.querySelectorAll("tr.item-venda"),
      function (linha) {
        return !linha.classList.contains("d-none");
      }
    );
  }

  function opcaoSelecionada(linha) {
    var select = linha.querySelector("select");
    if (!select || select.selectedIndex < 0) {
      return null;
    }
    return select.options[select.selectedIndex];
  }

  function campoQuantidade(linha) {
    return linha.querySelector("input[name$='-quantidade']");
  }

  function quantidadeDaLinha(linha) {
    var valor = parseInt(campoQuantidade(linha).value, 10);
    return isNaN(valor) ? 0 : valor;
  }

  function precoDaLinha(linha) {
    var campoPreco = linha.querySelector("input[name$='-preco']");
    if (campoPreco) {
      var digitado = parseFloat(campoPreco.value);
      return isNaN(digitado) ? 0 : digitado;
    }
    var opcao = opcaoSelecionada(linha);
    if (opcao && opcao.value !== "" && opcao.dataset.preco) {
      return parseFloat(opcao.dataset.preco);
    }
    return 0;
  }

  function recalcularTotal() {
    var total = 0;
    linhasAtivas().forEach(function (linha) {
      total += quantidadeDaLinha(linha) * precoDaLinha(linha);
    });
    totalTela.textContent = formatoMoeda.format(total);
  }

  function atualizarLinha(linha, produtoMudou) {
    var opcao = opcaoSelecionada(linha);
    var temProduto = opcao !== null && opcao.value !== "";
    var campoPreco = linha.querySelector("input[name$='-preco']");
    var textoPreco = linha.querySelector(".preco-texto");
    var infoEstoque = linha.querySelector(".estoque-info");
    var precoCadastrado = temProduto && opcao.dataset.preco ? opcao.dataset.preco : "";

    if (produtoMudou && campoPreco) {
      campoPreco.value = precoCadastrado;
    }
    if (textoPreco) {
      textoPreco.textContent = precoCadastrado
        ? formatoMoeda.format(parseFloat(precoCadastrado))
        : "-";
    }
    if (infoEstoque) {
      infoEstoque.textContent = temProduto ? "Estoque: " + opcao.dataset.estoque : "";
    }

    linha.querySelector(".subtotal").textContent = formatoMoeda.format(
      quantidadeDaLinha(linha) * precoDaLinha(linha)
    );
    recalcularTotal();
  }

  function adicionarLinha() {
    var indice = parseInt(totalForms.value, 10);
    corpo.insertAdjacentHTML(
      "beforeend",
      modelo.innerHTML.replace(/__prefix__/g, String(indice))
    );
    totalForms.value = String(indice + 1);
    return corpo.lastElementChild;
  }

  function removerLinha(linha) {
    var excluir = linha.querySelector("input[name$='-DELETE']");
    if (excluir) {
      excluir.checked = true;
    }
    linha.classList.add("d-none");
    if (linhasAtivas().length === 0) {
      adicionarLinha();
    }
    recalcularTotal();
  }

  function valorDoProdutoPorCodigo(codigo) {
    var select = modelo.content.querySelector("select");
    if (!select || codigo === "") {
      return null;
    }
    for (var i = 0; i < select.options.length; i++) {
      if (select.options[i].dataset.codigo === codigo) {
        return select.options[i].value;
      }
    }
    return null;
  }

  function selecionarProduto(valor) {
    var linhas = linhasAtivas();

    // Produto já está na venda: soma uma unidade.
    for (var i = 0; i < linhas.length; i++) {
      var select = linhas[i].querySelector("select");
      if (select && select.value === valor) {
        var campo = campoQuantidade(linhas[i]);
        campo.value = String(quantidadeDaLinha(linhas[i]) + 1);
        atualizarLinha(linhas[i], false);
        return;
      }
    }

    // Usa a primeira linha vazia ou cria uma nova.
    var vazia = linhas.filter(function (linha) {
      return linha.querySelector("select").value === "";
    })[0];
    var destino = vazia || adicionarLinha();
    destino.querySelector("select").value = valor;
    atualizarLinha(destino, true);
  }

  // --- Eventos -------------------------------------------------------------

  corpo.addEventListener("change", function (evento) {
    var linha = evento.target.closest("tr.item-venda");
    if (linha && evento.target.matches("select")) {
      atualizarLinha(linha, true);
    }
  });

  corpo.addEventListener("input", function (evento) {
    var linha = evento.target.closest("tr.item-venda");
    if (linha && evento.target.matches("input")) {
      atualizarLinha(linha, false);
    }
  });

  corpo.addEventListener("click", function (evento) {
    var botao = evento.target.closest(".remover-item");
    if (botao) {
      removerLinha(botao.closest("tr.item-venda"));
    }
  });

  if (botaoAdicionar) {
    botaoAdicionar.addEventListener("click", function () {
      var linha = adicionarLinha();
      var select = linha.querySelector("select");
      if (select) {
        select.focus();
      }
    });
  }

  if (leitor) {
    leitor.addEventListener("keydown", function (evento) {
      if (evento.key !== "Enter") {
        return;
      }
      evento.preventDefault();
      var codigo = leitor.value.trim();
      if (codigo === "") {
        return;
      }
      var valor = valorDoProdutoPorCodigo(codigo);
      if (valor === null) {
        aviso.textContent = "Código não encontrado: " + codigo;
        aviso.classList.remove("d-none");
      } else {
        aviso.classList.add("d-none");
        selecionarProduto(valor);
      }
      leitor.value = "";
      leitor.focus();
    });
  }

  // Enter nos campos da venda não envia o formulário por engano.
  formulario.addEventListener("keydown", function (evento) {
    if (evento.key === "Enter" && evento.target.tagName === "INPUT") {
      evento.preventDefault();
    }
  });

  linhasAtivas().forEach(function (linha) {
    atualizarLinha(linha, false);
  });
})();
document.addEventListener("DOMContentLoaded", function () {
  // Pede confirmação antes de enviar formulários marcados com data-confirm.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (evento) {
      if (!window.confirm(form.dataset.confirm)) {
        evento.preventDefault();
      }
    });
  });

  // Evita envio duplicado (duplo clique) em formulários marcados.
  document
    .querySelectorAll("form[data-evitar-duplo-envio]")
    .forEach(function (form) {
      form.addEventListener("submit", function (evento) {
        if (evento.defaultPrevented) {
          return;
        }
        form.querySelectorAll("button[type=submit]").forEach(function (botao) {
          botao.disabled = true;
        });
      });
    });

  // Botões com data-imprimir abrem a impressão do navegador.
  document.querySelectorAll("[data-imprimir]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      window.print();
    });
  });

  // Mensagens de sucesso somem sozinhas depois de alguns segundos.
  document.querySelectorAll(".alert-success").forEach(function (alerta) {
    window.setTimeout(function () {
      if (window.bootstrap && document.body.contains(alerta)) {
        window.bootstrap.Alert.getOrCreateInstance(alerta).close();
      }
    }, 6000);
  });
});
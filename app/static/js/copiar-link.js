// Copia conteudo de um input/code pro clipboard. CSP-safe (sem onclick inline).
// Suporta multiplos botoes na mesma pagina via [data-target].
(function () {
  "use strict";
  function setupBotao(btn) {
    btn.addEventListener("click", function () {
      var targetId = btn.getAttribute("data-target");
      var feedbackId = btn.getAttribute("data-feedback");
      var target = document.getElementById(targetId);
      if (!target) return;
      var texto = (target.value !== undefined) ? target.value : target.textContent;
      texto = texto.trim();

      var anuncia = function (msg) {
        if (!feedbackId) return;
        var el = document.getElementById(feedbackId);
        if (el) el.textContent = msg;
      };

      var done = function () {
        var original = btn.textContent;
        btn.textContent = "Copiado!";
        btn.disabled = true;
        anuncia("Copiado pra área de transferência");
        setTimeout(function () {
          btn.textContent = original;
          btn.disabled = false;
        }, 1800);
      };

      var fallback = function () {
        try {
          // Pra <input>, seleciona e copia. Pra <code>/<span>, usa Range.
          if (target.select) {
            target.select();
            target.setSelectionRange(0, 99999);
          } else {
            var range = document.createRange();
            range.selectNode(target);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
          }
          document.execCommand("copy");
          done();
        } catch (e) { /* noop */ }
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(texto).then(done, fallback);
      } else {
        fallback();
      }
    });
  }

  // Suporta multiplos botoes [id^="copiar-"] na mesma pagina.
  var botoes = document.querySelectorAll('[id^="copiar-"]');
  for (var i = 0; i < botoes.length; i++) setupBotao(botoes[i]);
})();

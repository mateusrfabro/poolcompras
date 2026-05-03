// Copiar link de indicacao pro clipboard. CSP-safe (sem onclick inline).
(function () {
  "use strict";
  var btn = document.getElementById("copiar-link");
  if (!btn) return;
  btn.addEventListener("click", function () {
    var targetId = btn.getAttribute("data-target");
    var input = document.getElementById(targetId);
    if (!input) return;
    input.select();
    input.setSelectionRange(0, 99999); // mobile

    var done = function () {
      var original = btn.textContent;
      btn.textContent = "Copiado!";
      btn.disabled = true;
      setTimeout(function () {
        btn.textContent = original;
        btn.disabled = false;
      }, 1800);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(input.value).then(done, function () {
        // fallback caso clipboard API falhe (HTTP, permissao negada)
        try { document.execCommand("copy"); done(); } catch (e) { /* noop */ }
      });
    } else {
      try { document.execCommand("copy"); done(); } catch (e) { /* noop */ }
    }
  });
})();

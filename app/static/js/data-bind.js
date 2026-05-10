/* data-bind.js — aplica valores dinamicos via data-* attributes em vez
   de style="..." inline. Permite remover 'unsafe-inline' do CSP
   style-src (defesa em profundidade contra XSS).

   [data-w-pct="42"] → element.style.width = "42%"
*/
(function () {
    document.querySelectorAll('[data-w-pct]').forEach(function (el) {
        var v = parseFloat(el.dataset.wPct);
        if (!isNaN(v)) {
            // setProperty/clamp 0..100 — defensivo contra valor malformado
            // ou extremos vindos de calculo de progresso.
            var pct = Math.min(Math.max(v, 0), 100);
            el.style.width = pct + "%";
        }
    });
})();

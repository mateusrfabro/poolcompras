// Loading state em forms (CSP-safe).
// Ao submeter qualquer form, desabilita os botoes de submit e troca o texto
// pra "Enviando..." (preserva original em data-original-text). Evita
// duplo-submit e da feedback imediato em conexao lenta.
//
// Skip via class="no-loading" no form (ex: filtros de busca, inline updates).
// Skip pra forms que abrem em new tab (Telegram OTP) — nao tem retorno na
// mesma aba pra reabilitar o botao.
(function () {
    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!form || form.tagName !== 'FORM') return;
        if (form.classList.contains('no-loading')) return;
        // Forms que abrem em nova aba: o navegador nao volta com response,
        // entao o botao ficaria preso em "Enviando...". Skip.
        if (form.target === '_blank') return;

        var botoes = form.querySelectorAll('button[type="submit"], input[type="submit"]');
        botoes.forEach(function (btn) {
            if (btn.disabled) return;
            btn.dataset.originalText = btn.textContent || btn.value || '';
            btn.disabled = true;
            // <button>: textContent. <input type=submit>: value.
            if (btn.tagName === 'BUTTON') {
                btn.textContent = 'Enviando…';
            } else {
                btn.value = 'Enviando…';
            }
        });

        // Se o submit for cancelado por alguma validacao client-side (HTML5
        // required, pattern, etc), reabilita imediatamente. Browser dispara
        // 'invalid' antes do submit em campo invalido — escutar isso seria
        // mais robusto, mas pra MVP, fallback de 8s.
        setTimeout(function () {
            botoes.forEach(function (btn) {
                if (btn.dataset.originalText !== undefined) {
                    btn.disabled = false;
                    if (btn.tagName === 'BUTTON') {
                        btn.textContent = btn.dataset.originalText;
                    } else {
                        btn.value = btn.dataset.originalText;
                    }
                    delete btn.dataset.originalText;
                }
            });
        }, 8000);
    }, true);  // capture=true: pega o submit antes de qualquer handler ad-hoc
})();

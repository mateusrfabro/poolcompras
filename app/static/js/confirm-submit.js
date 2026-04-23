// Intercepta clique em botoes com data-confirm e pede confirmacao antes
// de submeter o form. Substitui onclick="return confirm(...)" inline
// (bloqueado pela CSP script-src 'self').
//
// Uso no template:
//   <button type="submit" data-confirm="Deseja mesmo...?">Confirmar</button>

(function () {
    "use strict";
    document.addEventListener("click", function (ev) {
        var alvo = ev.target;
        // Suporta clique em <i>/<span> dentro do <button>
        while (alvo && alvo !== document.body) {
            if (alvo.hasAttribute && alvo.hasAttribute("data-confirm")) {
                var msg = alvo.getAttribute("data-confirm");
                if (!window.confirm(msg)) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                return;
            }
            alvo = alvo.parentNode;
        }
    }, true);
})();

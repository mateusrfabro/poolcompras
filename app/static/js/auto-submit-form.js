// Auto-submit em mudanca de selects/checkboxes marcados com data-auto-submit.
// Usado pelo filtro do Kanban CRM (admin escolhe vendedor -> form recarrega).
// CSP-safe: substitui onchange="this.form.submit()" inline que era proibido.
(function () {
    "use strict";

    function bindAutoSubmit() {
        var els = document.querySelectorAll("[data-auto-submit]");
        for (var i = 0; i < els.length; i++) {
            var el = els[i];
            el.addEventListener("change", function (e) {
                var form = e.target.form;
                if (form) {
                    form.submit();
                }
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bindAutoSubmit);
    } else {
        bindAutoSubmit();
    }
})();

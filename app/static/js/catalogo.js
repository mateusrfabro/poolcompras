// Toggle por categoria + contador de selecionados no catalogo da rodada
(function () {
    function updateCounter() {
        var n = document.querySelectorAll('input[name="produto_id"]:checked').length;
        var el = document.getElementById('counter');
        if (el) el.textContent = n;
    }

    window.toggleCategoria = function (cat) {
        var group = document.querySelector('.catalogo-produtos[data-cat="' + cat + '"]');
        if (!group) return;
        var checks = group.querySelectorAll('input[type="checkbox"]');
        var allChecked = Array.from(checks).every(function (c) { return c.checked; });
        checks.forEach(function (c) { c.checked = !allChecked; });
        updateCounter();
    };

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('input[name="produto_id"]').forEach(function (c) {
            c.addEventListener('change', updateCounter);
        });

        // Bind handlers nos botoes com data-toggle-cat (CSP: sem inline onclick)
        document.querySelectorAll('[data-toggle-cat]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                window.toggleCategoria(btn.getAttribute('data-toggle-cat'));
            });
        });
    });
})();
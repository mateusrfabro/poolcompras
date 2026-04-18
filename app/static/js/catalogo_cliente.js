// Filtros do catalogo do cliente (categoria, subcategoria, busca) + contador
(function () {
    var categorias = {};  // cat -> [subcategorias]

    function collectCategorias() {
        document.querySelectorAll('.cliente-categoria').forEach(function (catEl) {
            var cat = catEl.getAttribute('data-cat');
            var subs = [];
            catEl.querySelectorAll('.cliente-subcategoria').forEach(function (s) {
                var sub = s.getAttribute('data-subcat');
                if (sub && subs.indexOf(sub) === -1) subs.push(sub);
            });
            categorias[cat] = subs;
        });
    }

    function updateSubcatOptions() {
        var select = document.getElementById('filtro-subcategoria');
        var cat = document.getElementById('filtro-categoria').value;
        select.innerHTML = '<option value="">Todas</option>';
        if (cat && categorias[cat]) {
            categorias[cat].forEach(function (sub) {
                var opt = document.createElement('option');
                opt.value = sub;
                opt.textContent = sub;
                select.appendChild(opt);
            });
        }
    }

    function applyFilters() {
        var cat = document.getElementById('filtro-categoria').value;
        var sub = document.getElementById('filtro-subcategoria').value;
        var busca = document.getElementById('filtro-busca').value.toLowerCase().trim();

        document.querySelectorAll('.cliente-categoria').forEach(function (catEl) {
            var catMatch = !cat || catEl.getAttribute('data-cat') === cat;
            var hasVisibleRow = false;

            catEl.querySelectorAll('.cliente-subcategoria').forEach(function (subEl) {
                var subMatch = !sub || subEl.getAttribute('data-subcat') === sub;
                var subHasVisible = false;

                subEl.querySelectorAll('.cliente-linha').forEach(function (tr) {
                    var nome = tr.getAttribute('data-nome') || '';
                    var buscaMatch = !busca || nome.indexOf(busca) !== -1;
                    var visivel = catMatch && subMatch && buscaMatch;
                    tr.style.display = visivel ? '' : 'none';
                    if (visivel) subHasVisible = true;
                });

                subEl.style.display = subHasVisible ? '' : 'none';
                if (subHasVisible) hasVisibleRow = true;
            });

            catEl.style.display = hasVisibleRow ? '' : 'none';
        });
    }

    function updateCounter() {
        var n = 0;
        document.querySelectorAll('.input-qtd').forEach(function (inp) {
            var v = parseFloat((inp.value || '').replace(',', '.'));
            if (v > 0) n++;
        });
        var c = document.getElementById('counter-itens');
        if (c) c.textContent = n;
    }

    document.addEventListener('DOMContentLoaded', function () {
        collectCategorias();
        document.getElementById('filtro-categoria').addEventListener('change', function () {
            updateSubcatOptions();
            applyFilters();
        });
        document.getElementById('filtro-subcategoria').addEventListener('change', applyFilters);
        document.getElementById('filtro-busca').addEventListener('input', applyFilters);
        document.querySelectorAll('.input-qtd').forEach(function (inp) {
            inp.addEventListener('input', updateCounter);
        });
    });
})();
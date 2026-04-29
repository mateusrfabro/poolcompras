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

    // === Auto-save com debounce ===
    // Apos cada digitacao em .input-qtd, espera 1.5s sem alteracoes e salva
    // o item via POST AJAX. Evita perda de pedido se user fechar a aba.
    var AUTO_SAVE_DELAY_MS = 1500;
    var saveTimers = {};  // produto_id -> timeout handle

    function getCsrfToken() {
        var input = document.querySelector('input[name="csrf_token"]');
        return input ? input.value : '';
    }

    function pad2(n) { return n < 10 ? '0' + n : '' + n; }

    function feedbackSalvo() {
        var el = document.getElementById('auto-save-status');
        if (!el) return;
        var d = new Date();
        el.textContent = 'Salvo às ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
        el.classList.remove('auto-save-erro');
        el.classList.add('auto-save-ok');
    }
    function feedbackErro(msg) {
        var el = document.getElementById('auto-save-status');
        if (!el) return;
        el.textContent = msg || 'Erro ao salvar — tente novamente';
        el.classList.remove('auto-save-ok');
        el.classList.add('auto-save-erro');
    }
    function feedbackSalvando() {
        var el = document.getElementById('auto-save-status');
        if (!el) return;
        el.textContent = 'Salvando…';
        el.classList.remove('auto-save-ok', 'auto-save-erro');
    }

    function autoSave(input) {
        var produtoId = input.getAttribute('data-produto-id');
        var qtd = (input.value || '').replace(',', '.');
        var quantidade = parseFloat(qtd);
        if (isNaN(quantidade) || quantidade < 0) quantidade = 0;

        feedbackSalvando();

        var formData = new FormData();
        formData.append('csrf_token', getCsrfToken());
        formData.append('produto_id', produtoId);
        formData.append('quantidade', String(quantidade));

        fetch('/pedidos/catalogo/auto-save', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
        }).then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        }).then(function (data) {
            if (data && data.ok) feedbackSalvo();
            else feedbackErro(data && data.erro);
        }).catch(function () {
            feedbackErro('Sem conexão — mudança não foi salva');
        });
    }

    function scheduleAutoSave(input) {
        var produtoId = input.getAttribute('data-produto-id');
        if (saveTimers[produtoId]) clearTimeout(saveTimers[produtoId]);
        saveTimers[produtoId] = setTimeout(function () {
            autoSave(input);
        }, AUTO_SAVE_DELAY_MS);
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
            inp.addEventListener('input', function () {
                updateCounter();
                scheduleAutoSave(inp);
            });
        });
    });
})();
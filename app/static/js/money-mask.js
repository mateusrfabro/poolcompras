// Mascara R$ pra inputs com classe .money-input (CSP-safe, sem inline handlers)
(function () {
    function formatCentavos(centavos) {
        if (!centavos) return "";
        var n = parseInt(centavos, 10);
        if (isNaN(n)) return "";
        var inteiro = Math.floor(n / 100);
        var dec = n % 100;
        var decStr = (dec < 10 ? "0" : "") + dec;
        // Separador de milhar
        var intStr = inteiro.toString();
        var withSep = "";
        for (var i = 0; i < intStr.length; i++) {
            if (i && (intStr.length - i) % 3 === 0) withSep += ".";
            withSep += intStr[i];
        }
        return "R$ " + withSep + "," + decStr;
    }

    function rawDigits(val) {
        return (val || "").replace(/\D/g, "");
    }

    function applyMask(input) {
        var digits = rawDigits(input.value);
        // Limita a 10 digitos (99.999.999,99) pra nao travar
        if (digits.length > 10) digits = digits.slice(0, 10);
        input.value = formatCentavos(digits);
    }

    // Valor numerico puro pra submit (substitui o valor do input por "1234.56" so no submit)
    function toNumberString(masked) {
        var digits = rawDigits(masked);
        if (!digits) return "";
        var n = parseInt(digits, 10);
        return (n / 100).toFixed(2);
    }

    document.addEventListener("DOMContentLoaded", function () {
        var inputs = document.querySelectorAll(".money-input");
        inputs.forEach(function (inp) {
            // Formata valor inicial se existir (ex: edicao)
            if (inp.value) {
                // Valor pode vir como "12.50" ou "12,50" do backend
                var v = inp.value.replace(",", ".");
                var f = parseFloat(v);
                if (!isNaN(f)) {
                    inp.value = formatCentavos(Math.round(f * 100).toString());
                }
            }
            inp.addEventListener("input", function () { applyMask(inp); });
            inp.addEventListener("blur", function () { applyMask(inp); });
        });

        // No submit, transforma R$ 1.234,56 em 1234.56 pro backend
        document.querySelectorAll("form").forEach(function (form) {
            form.addEventListener("submit", function () {
                form.querySelectorAll(".money-input").forEach(function (inp) {
                    if (inp.value) inp.value = toNumberString(inp.value);
                });
            });
        });
    });
})();
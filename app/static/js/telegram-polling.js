// Polling pra detectar vinculacao Telegram via webhook (CSP-safe).
// Apos user clicar "Conectar Telegram" e abrir o bot em nova aba, esta pagina
// fica polando /perfil/telegram/status a cada 3s. Quando o webhook salvar
// chat_id (ao /start no bot), redireciona pra perfil — sem precisar do user
// clicar "Concluir" manualmente.
(function () {
    var formConectar = document.getElementById('form-conectar-telegram');
    var aviso = document.getElementById('telegram-aguardando');
    if (!formConectar || !aviso) return;

    var POLL_INTERVAL_MS = 3000;
    var MAX_TENTATIVAS = 60;  // ~3 min — alinhado ao TTL do token

    formConectar.addEventListener('submit', function () {
        // Mostra aviso "aguardando" depois do submit (form abre em nova aba).
        setTimeout(function () { aviso.classList.remove('d-none'); }, 500);

        var tentativas = 0;
        var intervalo = setInterval(function () {
            tentativas++;
            if (tentativas > MAX_TENTATIVAS) {
                clearInterval(intervalo);
                aviso.textContent =
                    'Tempo esgotado. Atualize a página ou clique "concluir manualmente".';
                return;
            }
            fetch('/perfil/telegram/status', { credentials: 'same-origin' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data && data.conectado) {
                        clearInterval(intervalo);
                        aviso.textContent = 'Telegram conectado! Recarregando…';
                        setTimeout(function () {
                            window.location.reload();
                        }, 800);
                    }
                })
                .catch(function () { /* falha de rede — continua tentando */ });
        }, POLL_INTERVAL_MS);
    });
})();

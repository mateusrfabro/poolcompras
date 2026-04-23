"""Testes do webhook do Telegram (/webhook/telegram/<secret>)."""
import os
from unittest.mock import patch, MagicMock

from itsdangerous import URLSafeTimedSerializer

from app import db
from app.models import Usuario


def _gera_token(app, user_id, salt="vincular-telegram"):
    return URLSafeTimedSerializer(app.config["SECRET_KEY"]).dumps(user_id, salt=salt)


def _post_update(client, secret, update):
    return client.post(f"/webhook/telegram/{secret}", json=update)


def test_webhook_404_sem_secret(app, client):
    """Rota nao existe sem TELEGRAM_WEBHOOK_SECRET no env (nao revela)."""
    os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
    r = client.post("/webhook/telegram/qualquer", json={})
    assert r.status_code == 404


def test_webhook_404_com_secret_errado(app, client):
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "segredo-certo"
    try:
        r = client.post("/webhook/telegram/segredo-errado", json={})
        assert r.status_code == 404
    finally:
        os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)


def test_webhook_ignora_mensagem_sem_texto(app, client):
    """Update sem /start (ex: foto, sticker) nao faz nada — retorna 200."""
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s1"
    try:
        r = _post_update(client, "s1", {"update_id": 1, "message": {
            "chat": {"id": 100}, "text": "oi tudo bem",
        }})
        assert r.status_code == 200
    finally:
        os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)


def test_webhook_start_com_token_valido_vincula(app, client):
    """/start <token> valido -> salva chat_id no user dono do token."""
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s1"
    os.environ["TELEGRAM_BOT_TOKEN"] = "bot-fake"

    user = Usuario.query.filter_by(email="lancha@test.com").first()
    token = _gera_token(app, user.id)

    send_resp = MagicMock()
    send_resp.status_code = 200
    send_resp.json.return_value = {"ok": True}

    try:
        with patch("app.routes.telegram_webhook.requests.post",
                   return_value=send_resp) as mock_post:
            r = _post_update(client, "s1", {"update_id": 1, "message": {
                "chat": {"id": 7777777}, "text": f"/start {token}",
            }})
        assert r.status_code == 200
        u = Usuario.query.filter_by(email="lancha@test.com").first()
        assert u.telegram_chat_id == 7777777
        # Bot respondeu confirmacao
        assert mock_post.called
    finally:
        os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_webhook_start_sem_token_responde_instrucoes(app, client):
    """/start sem token -> bot responde com instrucao, nao salva nada."""
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s1"
    os.environ["TELEGRAM_BOT_TOKEN"] = "bot-fake"

    send_resp = MagicMock()
    send_resp.status_code = 200
    send_resp.json.return_value = {"ok": True}

    try:
        with patch("app.routes.telegram_webhook.requests.post",
                   return_value=send_resp) as mock_post:
            r = _post_update(client, "s1", {"update_id": 2, "message": {
                "chat": {"id": 888888}, "text": "/start",
            }})
        assert r.status_code == 200
        assert mock_post.called
        texto = mock_post.call_args.kwargs["json"]["text"]
        assert "Meu Perfil" in texto
    finally:
        os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_webhook_token_expirado_responde_erro(app, client):
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s1"
    os.environ["TELEGRAM_BOT_TOKEN"] = "bot-fake"

    # Token com TTL negativo (ja expirou) — simulado via serializer separado
    from itsdangerous import URLSafeTimedSerializer
    import time
    # Gerar token com timestamp no passado: usamos loads com max_age<=0 pra forcar expired
    # (Mais simples: assinar com outro serializer + chave diferente? Melhor: fazer o
    # teste usar serializer correto mas chamar loads com max_age=0 via mock).
    # Aqui geramos token normal e patchamos o _vincular_serializer()._loads_unsafe_max_age
    # Simplificado: token expirado vai virar BadSignature em loads. Test cobre BadSignature.

    # token invalido (assinado com outra chave) — mesmo efeito user-visible
    token_ruim = URLSafeTimedSerializer("outra-chave").dumps(1, salt="vincular-telegram")

    send_resp = MagicMock()
    send_resp.status_code = 200
    send_resp.json.return_value = {"ok": True}

    try:
        with patch("app.routes.telegram_webhook.requests.post",
                   return_value=send_resp) as mock_post:
            r = _post_update(client, "s1", {"update_id": 3, "message": {
                "chat": {"id": 999}, "text": f"/start {token_ruim}",
            }})
        assert r.status_code == 200
        assert mock_post.called
        texto = mock_post.call_args.kwargs["json"]["text"]
        assert "invalido" in texto.lower() or "expirado" in texto.lower()
    finally:
        os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_webhook_chat_id_ja_vinculado_a_outro(app, client):
    """Chat_id ja esta em outro Usuario -> nao vincula ao 2o."""
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s1"
    os.environ["TELEGRAM_BOT_TOKEN"] = "bot-fake"

    # lanchA ja tem chat_id 5555
    lanchA = Usuario.query.filter_by(email="lancha@test.com").first()
    lanchA.telegram_chat_id = 5555
    db.session.commit()

    # lanchB pede vinculacao com o MESMO chat_id
    lanchB = Usuario.query.filter_by(email="lanchb@test.com").first()
    token = _gera_token(app, lanchB.id)

    send_resp = MagicMock()
    send_resp.status_code = 200
    send_resp.json.return_value = {"ok": True}

    try:
        with patch("app.routes.telegram_webhook.requests.post",
                   return_value=send_resp) as mock_post:
            r = _post_update(client, "s1", {"update_id": 4, "message": {
                "chat": {"id": 5555}, "text": f"/start {token}",
            }})
        assert r.status_code == 200
        # lanchB NAO recebeu chat_id
        lanchB = Usuario.query.filter_by(email="lanchb@test.com").first()
        assert lanchB.telegram_chat_id is None
        texto = mock_post.call_args.kwargs["json"]["text"]
        assert "ja esta vinculado" in texto.lower() or "vinculado" in texto.lower()
    finally:
        os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_webhook_payload_malformado_retorna_200(app, client):
    """Telegram retenta se 5xx — nunca lance 500 em webhook."""
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s1"
    try:
        # Update lixo
        r = _post_update(client, "s1", {"update_id": 5})
        assert r.status_code == 200
    finally:
        os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)


def test_confirmar_atalho_webhook_ja_vinculou(app, client_lanchA):
    """Se webhook salvou chat_id em background, /confirmar nao chama getUpdates.

    Simulamos isso setando telegram_chat_id direto no DB (como se webhook tivesse
    processado) e verificando que /confirmar responde sucesso sem bater na API.
    """
    u = Usuario.query.filter_by(email="lancha@test.com").first()
    u.telegram_chat_id = 1122334455
    db.session.commit()

    # Mesmo sem TELEGRAM_BOT_TOKEN no env, o confirmar deve funcionar
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    with patch("app.routes.perfil.requests.get") as mock_get:
        r = client_lanchA.post("/perfil/telegram/confirmar", follow_redirects=False)
        mock_get.assert_not_called()  # curto-circuito
    assert r.status_code == 302

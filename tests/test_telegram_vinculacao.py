"""Testes do fluxo de vinculacao de Telegram via deep link."""
import os
import re
from unittest.mock import patch, MagicMock

from itsdangerous import URLSafeTimedSerializer

from app import db
from app.models import Usuario


def _csrf(client, url="/perfil/"):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


def _gera_token(app, user_id, salt="vincular-telegram"):
    return URLSafeTimedSerializer(app.config["SECRET_KEY"]).dumps(user_id, salt=salt)


def test_iniciar_redireciona_pro_deep_link(app, client_lanchA):
    csrf = _csrf(client_lanchA)
    r = client_lanchA.post("/perfil/telegram/iniciar",
                           data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert loc.startswith("https://t.me/poolcomprasbot?start=")
    assert len(loc.split("?start=")[1]) > 20  # token assinado


def test_iniciar_exige_login(client):
    r = client.post("/perfil/telegram/iniciar", follow_redirects=False)
    # login_required redireciona pro /login
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_confirmar_sem_sessao_redireciona(app, client_lanchA):
    csrf = _csrf(client_lanchA)
    r = client_lanchA.post("/perfil/telegram/confirmar",
                           data={"csrf_token": csrf}, follow_redirects=False)
    # Sem sessao de token, volta pro perfil com flash
    assert r.status_code == 302
    assert "/perfil" in r.headers["Location"]
    usuario = Usuario.query.filter_by(email="lancha@test.com").first()
    assert usuario.telegram_chat_id is None  # nada salvo


def test_confirmar_encontra_chat_id_e_salva(app, client_lanchA):
    """Happy path: user deu /start <token> no bot, getUpdates retorna, sistema salva."""
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake:token"

    # Simula o iniciar: guarda token em sessao
    with client_lanchA.session_transaction() as sess:
        tok = _gera_token(app, Usuario.query.filter_by(email="lancha@test.com").first().id)
        sess["telegram_token"] = tok

    # getUpdates retorna uma mensagem /start <token>
    updates_resp = MagicMock()
    updates_resp.status_code = 200
    updates_resp.json.return_value = {
        "ok": True,
        "result": [{
            "update_id": 1,
            "message": {
                "text": f"/start {tok}",
                "chat": {"id": 98765432, "first_name": "LanchA"},
            },
        }],
    }
    send_resp = MagicMock()
    send_resp.status_code = 200
    send_resp.json.return_value = {"ok": True}

    try:
        # Stub de requests: .get (getUpdates) + .post (sendMessage da confirmacao)
        with patch("app.routes.perfil.requests.get", return_value=updates_resp), \
             patch("app.services.notificacoes.requests.post", return_value=send_resp):
            csrf = _csrf(client_lanchA)
            r = client_lanchA.post("/perfil/telegram/confirmar",
                                   data={"csrf_token": csrf}, follow_redirects=False)
        assert r.status_code == 302

        usuario = Usuario.query.filter_by(email="lancha@test.com").first()
        assert usuario.telegram_chat_id == "98765432"
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_confirmar_nao_encontra_token_nao_salva(app, client_lanchA):
    """getUpdates retorna mensagens SEM o token esperado -> flash warning, nao salva."""
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake:token"

    with client_lanchA.session_transaction() as sess:
        uid = Usuario.query.filter_by(email="lancha@test.com").first().id
        sess["telegram_token"] = _gera_token(app, uid)

    # getUpdates retorna /start SEM token (ou token errado)
    updates_resp = MagicMock()
    updates_resp.status_code = 200
    updates_resp.json.return_value = {
        "ok": True,
        "result": [{
            "update_id": 1,
            "message": {
                "text": "/start TOKEN_DE_OUTRO",
                "chat": {"id": 11111, "first_name": "Outro"},
            },
        }],
    }
    try:
        with patch("app.routes.perfil.requests.get", return_value=updates_resp):
            csrf = _csrf(client_lanchA)
            r = client_lanchA.post("/perfil/telegram/confirmar",
                                   data={"csrf_token": csrf}, follow_redirects=False)
        assert r.status_code == 302
        usuario = Usuario.query.filter_by(email="lancha@test.com").first()
        assert usuario.telegram_chat_id is None
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_confirmar_sem_bot_token_avisa_admin(app, client_lanchA):
    """Servidor sem TELEGRAM_BOT_TOKEN -> flash erro, nao chama getUpdates."""
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    with client_lanchA.session_transaction() as sess:
        uid = Usuario.query.filter_by(email="lancha@test.com").first().id
        sess["telegram_token"] = _gera_token(app, uid)

    csrf = _csrf(client_lanchA)
    with patch("app.routes.perfil.requests.get") as mock_get:
        r = client_lanchA.post("/perfil/telegram/confirmar",
                               data={"csrf_token": csrf}, follow_redirects=False)
        mock_get.assert_not_called()
    assert r.status_code == 302


def test_confirmar_token_de_outro_usuario_rejeitado(app, client_lanchA):
    """Se token na sessao pertence a outro user_id (atacante), nao vincula."""
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake:token"
    # Token assinado com user_id de outra lanchonete
    uid_outro = Usuario.query.filter_by(email="lanchb@test.com").first().id
    with client_lanchA.session_transaction() as sess:
        sess["telegram_token"] = _gera_token(app, uid_outro)

    try:
        with patch("app.routes.perfil.requests.get") as mock_get:
            csrf = _csrf(client_lanchA)
            r = client_lanchA.post("/perfil/telegram/confirmar",
                                   data={"csrf_token": csrf}, follow_redirects=False)
            mock_get.assert_not_called()  # rejeitou antes de chamar API
        assert r.status_code == 302
        usuario = Usuario.query.filter_by(email="lancha@test.com").first()
        assert usuario.telegram_chat_id is None
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_desvincular_limpa_chat_id(app, client_lanchA):
    u = Usuario.query.filter_by(email="lancha@test.com").first()
    u.telegram_chat_id = "999999"
    db.session.commit()

    csrf = _csrf(client_lanchA)
    r = client_lanchA.post("/perfil/telegram/desvincular",
                           data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 302
    assert Usuario.query.filter_by(email="lancha@test.com").first().telegram_chat_id is None

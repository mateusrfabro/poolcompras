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


def test_confirmar_encontra_chat_id_dispara_otp(app, client_lanchA):
    """Confirmar NAO salva chat_id diretamente — envia OTP e redireciona pra /codigo.

    chat_id so eh salvo apos user colar o OTP recebido no Telegram.
    """
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake:token"

    with client_lanchA.session_transaction() as sess:
        tok = _gera_token(app, Usuario.query.filter_by(email="lancha@test.com").first().id)
        sess["telegram_token"] = tok

    updates_resp = MagicMock()
    updates_resp.status_code = 200
    updates_resp.json.return_value = {
        "ok": True,
        "result": [{"update_id": 1, "message": {
            "text": f"/start {tok}",
            "chat": {"id": 98765432, "first_name": "LanchA"},
        }}],
    }
    send_resp = MagicMock()
    send_resp.status_code = 200
    send_resp.json.return_value = {"ok": True}

    try:
        with patch("app.routes.perfil.requests.get", return_value=updates_resp), \
             patch("app.services.notificacoes.requests.post", return_value=send_resp):
            csrf = _csrf(client_lanchA)
            r = client_lanchA.post("/perfil/telegram/confirmar",
                                   data={"csrf_token": csrf}, follow_redirects=False)
        assert r.status_code == 302
        assert "/perfil/telegram/codigo" in r.headers["Location"]

        # chat_id NAO salvo ainda — espera OTP
        usuario = Usuario.query.filter_by(email="lancha@test.com").first()
        assert usuario.telegram_chat_id is None

        # Sessao tem pendencia do OTP com o chat_id descoberto
        with client_lanchA.session_transaction() as sess:
            pend = sess.get("telegram_otp_pendente")
            assert pend is not None
            assert pend["chat_id"] == "98765432"
            assert "codigo_hash" in pend
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_codigo_correto_salva_chat_id(app, client_lanchA):
    """POST /telegram/codigo com codigo correto salva chat_id no Usuario."""
    import hmac, hashlib
    from datetime import datetime, timezone, timedelta

    secret = app.config["SECRET_KEY"]
    codigo = "123456"
    codigo_hash = hmac.new(secret.encode(), codigo.encode(), hashlib.sha256).hexdigest()
    futuro = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

    with client_lanchA.session_transaction() as sess:
        sess["telegram_otp_pendente"] = {
            "chat_id": "55555555",
            "codigo_hash": codigo_hash,
            "expira_em": futuro,
        }

    send_resp = MagicMock()
    send_resp.status_code = 200
    send_resp.json.return_value = {"ok": True}

    os.environ["TELEGRAM_BOT_TOKEN"] = "fake:token"
    try:
        with patch("app.services.notificacoes.requests.post", return_value=send_resp):
            csrf = _csrf(client_lanchA, "/perfil/telegram/codigo")
            r = client_lanchA.post("/perfil/telegram/codigo",
                                   data={"csrf_token": csrf, "codigo": codigo},
                                   follow_redirects=False)
        assert r.status_code == 302
        u = Usuario.query.filter_by(email="lancha@test.com").first()
        assert u.telegram_chat_id == 55555555  # BigInteger
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_codigo_errado_nao_salva(app, client_lanchA):
    import hmac, hashlib
    from datetime import datetime, timezone, timedelta

    secret = app.config["SECRET_KEY"]
    codigo_hash = hmac.new(secret.encode(), b"123456", hashlib.sha256).hexdigest()

    with client_lanchA.session_transaction() as sess:
        sess["telegram_otp_pendente"] = {
            "chat_id": "77777",
            "codigo_hash": codigo_hash,
            "expira_em": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        }

    csrf = _csrf(client_lanchA, "/perfil/telegram/codigo")
    r = client_lanchA.post("/perfil/telegram/codigo",
                           data={"csrf_token": csrf, "codigo": "999999"})
    # Renderiza template de volta (200), nao salva
    u = Usuario.query.filter_by(email="lancha@test.com").first()
    assert u.telegram_chat_id is None


def test_codigo_expirado_rejeita(app, client_lanchA):
    from datetime import datetime, timezone, timedelta

    with client_lanchA.session_transaction() as sess:
        sess["telegram_otp_pendente"] = {
            "chat_id": "77777",
            "codigo_hash": "x",
            "expira_em": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        }

    r = client_lanchA.get("/perfil/telegram/codigo", follow_redirects=False)
    assert r.status_code == 302  # redireciona com flash
    # Pendencia foi limpa
    with client_lanchA.session_transaction() as sess:
        assert "telegram_otp_pendente" not in sess


def test_manual_chat_id_exige_otp(app, client_lanchA):
    """Fluxo manual: user cola chat_id, sistema manda OTP (nao salva ainda)."""
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake:token"
    send_resp = MagicMock()
    send_resp.status_code = 200
    send_resp.json.return_value = {"ok": True}

    try:
        with patch("app.services.notificacoes.requests.post", return_value=send_resp):
            csrf = _csrf(client_lanchA)
            r = client_lanchA.post("/perfil/telegram/manual",
                                   data={"csrf_token": csrf, "chat_id": "12345678"},
                                   follow_redirects=False)
        assert r.status_code == 302
        assert "/perfil/telegram/codigo" in r.headers["Location"]
        # chat_id NAO salvo ainda
        u = Usuario.query.filter_by(email="lancha@test.com").first()
        assert u.telegram_chat_id is None
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_manual_chat_id_invalido_rejeita(app, client_lanchA):
    """Chat_id nao numerico eh rejeitado antes de bater na API."""
    csrf = _csrf(client_lanchA)
    with patch("app.services.notificacoes.requests.post") as mock_post:
        r = client_lanchA.post("/perfil/telegram/manual",
                               data={"csrf_token": csrf, "chat_id": "abc"},
                               follow_redirects=False)
        mock_post.assert_not_called()
    assert r.status_code == 302


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

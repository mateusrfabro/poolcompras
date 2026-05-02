"""Testes de integracao do canal Telegram (services/notificacoes.py)."""
import os
from unittest.mock import patch, MagicMock

from app import db
from app.models import Usuario
from app.services.notificacoes import (
    enviar_telegram, notificar_evento, enviar_link_recuperacao, _escape,
)


def _user_com_telegram(chat_id=12345678):
    u = Usuario.query.filter_by(email="lancha@test.com").first()
    u.telegram_chat_id = int(chat_id)
    db.session.commit()
    return u


def test_escape_html_basico():
    assert _escape("Lanch <A>") == "Lanch &lt;A&gt;"
    assert _escape("A & B") == "A &amp; B"
    assert _escape(None) == ""
    assert _escape("") == ""


def test_canal_inativo_sem_token(app):
    """Sem TELEGRAM_BOT_TOKEN, cai no fallback e retorna False."""
    u = _user_com_telegram()
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    assert enviar_telegram(u, "oi") is False


def test_canal_inativo_sem_chat_id(app):
    """Usuario sem chat_id, mesmo com TOKEN, cai no fallback."""
    u = Usuario.query.filter_by(email="lancha@test.com").first()
    u.telegram_chat_id = None
    db.session.commit()
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake-token"
    try:
        assert enviar_telegram(u, "oi") is False
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_envio_sucesso_chama_api(app):
    """Com TOKEN + chat_id, faz POST pra api.telegram.org e retorna True em 200."""
    u = _user_com_telegram(99999)
    os.environ["TELEGRAM_BOT_TOKEN"] = "abc:def"

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"ok": True, "result": {}}

    try:
        with patch("app.services.notificacoes.requests.post", return_value=resp) as mock_post:
            assert enviar_telegram(u, "msg teste") is True
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert "bot" in args[0] and args[0].endswith("/sendMessage")
            # chat_id vai como int (BigInteger no DB) ou str — aceita ambos
            assert str(kwargs["json"]["chat_id"]) == "99999"
            assert kwargs["json"]["text"] == "msg teste"
            assert kwargs["json"]["parse_mode"] == "HTML"
            assert kwargs["timeout"] == 5
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_envio_falha_api_cai_no_fallback(app, caplog):
    """API retorna 400 (chat_id invalido, bot bloqueado, etc) -> False + log."""
    import logging
    caplog.set_level(logging.WARNING, logger="app.services.notificacoes")
    u = _user_com_telegram(1000)
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"

    resp = MagicMock()
    resp.status_code = 400
    resp.text = '{"ok":false,"error_code":400,"description":"Bad Request"}'
    resp.json.return_value = {"ok": False}

    try:
        with patch("app.services.notificacoes.requests.post", return_value=resp):
            assert enviar_telegram(u, "msg") is False
        fails = [r for r in caplog.records if "TELEGRAM_FAIL" in r.getMessage()]
        assert len(fails) == 1
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_envio_timeout_nao_levanta(app, caplog):
    """api.telegram.org offline -> requests.Timeout capturado e nao propaga."""
    import logging
    import requests as req_module
    caplog.set_level(logging.WARNING, logger="app.services.notificacoes")
    u = _user_com_telegram(111)
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"

    try:
        with patch("app.services.notificacoes.requests.post",
                   side_effect=req_module.Timeout("timed out")):
            # Nao deve levantar excecao — notificacao eh best-effort
            assert enviar_telegram(u, "msg") is False
        excs = [r for r in caplog.records if "TELEGRAM_EXC" in r.getMessage()]
        assert len(excs) == 1
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_notificar_evento_inclui_titulo_e_detalhes(app):
    """notificar_evento formata HTML bold no titulo + separa detalhes."""
    u = _user_com_telegram(1)
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"

    capturado = {}

    def _fake(url, json, timeout):
        capturado["json"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"ok": True}
        return resp

    try:
        with patch("app.services.notificacoes.requests.post", side_effect=_fake):
            notificar_evento(u, "Proposta aprovada", "Rodada A")
        txt = capturado["json"]["text"]
        assert "<b>Proposta aprovada</b>" in txt
        assert "Rodada A" in txt
        assert "Aggron" in txt
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_link_recuperacao_usa_telegram_quando_disponivel(app):
    """enviar_link_recuperacao chama enviar_telegram se canal ativo."""
    u = _user_com_telegram(333)
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"ok": True}

    try:
        with patch("app.services.notificacoes.requests.post", return_value=resp) as mock_post:
            ret = enviar_link_recuperacao(u, "https://aggron.com.br/redefinir-senha/tok123")
        assert ret is True
        # Mensagem tem o link completo
        assert "redefinir-senha/tok123" in mock_post.call_args.kwargs["json"]["text"]
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

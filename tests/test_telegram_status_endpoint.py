"""Testes do endpoint GET /perfil/telegram/status.

Front-end do perfil chama esse endpoint a cada 3s (telegram-polling.js)
pra detectar quando o webhook salva chat_id no DB. Retorna JSON simples:
{conectado: bool}.
"""
from app import db
from app.models import Usuario


def test_status_anonimo_redireciona_pra_login(client):
    """Sem login, GET deve redirecionar (login_required)."""
    r = client.get("/perfil/telegram/status", follow_redirects=False)
    assert r.status_code in (302, 401)


def test_status_sem_chat_id_retorna_false(app, client_lanchA):
    """Lanchonete sem telegram_chat_id -> {conectado: false}."""
    u = Usuario.query.filter_by(email="lancha@test.com").first()
    u.telegram_chat_id = None
    db.session.commit()

    r = client_lanchA.get("/perfil/telegram/status")
    assert r.status_code == 200
    assert r.get_json() == {"conectado": False}


def test_status_com_chat_id_retorna_true(app, client_lanchA):
    """Apos webhook salvar chat_id, polling detecta como true."""
    u = Usuario.query.filter_by(email="lancha@test.com").first()
    u.telegram_chat_id = 123456
    db.session.commit()

    r = client_lanchA.get("/perfil/telegram/status")
    assert r.status_code == 200
    assert r.get_json() == {"conectado": True}

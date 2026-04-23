"""Testes de recuperacao de senha: token valido, expirado, invalido + troca."""
import re
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from app.models import Usuario


def _get_csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


def _gera_token(app, user_id, salt="recuperar-senha"):
    return URLSafeTimedSerializer(app.config["SECRET_KEY"]).dumps(user_id, salt=salt)


def test_esqueci_senha_form_renderiza(client):
    r = client.get("/esqueci-senha")
    assert r.status_code == 200
    assert b"Esqueci minha senha" in r.data


def test_esqueci_senha_email_inexistente_nao_vaza(app, client):
    """Mesma resposta pra email existente e inexistente — evita enumeracao."""
    token = _get_csrf(client, "/esqueci-senha")
    r = client.post("/esqueci-senha",
                    data={"csrf_token": token, "email": "ninguem@lugar.nenhum"},
                    follow_redirects=False)
    assert r.status_code == 302
    # Redireciona pra login (mesmo comportamento do caso com email valido)
    assert "/login" in r.headers["Location"]


def test_esqueci_senha_email_valido_gera_token_via_notificacao(app, client, caplog):
    """Service de notificacao loga o link quando e-mail existe."""
    import logging
    caplog.set_level(logging.INFO, logger="app.services.notificacoes")

    token = _get_csrf(client, "/esqueci-senha")
    client.post("/esqueci-senha",
                data={"csrf_token": token, "email": "lancha@test.com"},
                follow_redirects=False)

    # Log deve conter NOTIF_FALLBACK com link redefinir-senha
    rec = [r for r in caplog.records if "NOTIF_FALLBACK" in r.getMessage()]
    assert len(rec) == 1
    assert "/redefinir-senha/" in rec[0].getMessage()


def test_redefinir_senha_token_valido_troca_senha(app, client):
    usuario = Usuario.query.filter_by(email="lancha@test.com").first()
    uid = usuario.id
    token = _gera_token(app, uid)

    # GET renderiza form
    r = client.get(f"/redefinir-senha/{token}")
    assert r.status_code == 200

    csrf = _get_csrf(client, f"/redefinir-senha/{token}")
    r = client.post(f"/redefinir-senha/{token}",
                    data={"csrf_token": csrf, "senha": "novasenha123",
                          "confirmacao": "novasenha123"},
                    follow_redirects=False)
    assert r.status_code == 302
    # Senha no DB foi trocada
    usuario = Usuario.query.filter_by(email="lancha@test.com").first()
    assert check_password_hash(usuario.senha_hash, "novasenha123")


def test_redefinir_senha_token_invalido_redireciona(client):
    r = client.get("/redefinir-senha/tokenfalso123", follow_redirects=False)
    assert r.status_code == 302
    assert "/esqueci-senha" in r.headers["Location"]


def test_redefinir_senha_senhas_diferentes_rejeita(app, client):
    uid = Usuario.query.filter_by(email="lancha@test.com").first().id
    token = _gera_token(app, uid)
    csrf = _get_csrf(client, f"/redefinir-senha/{token}")
    r = client.post(f"/redefinir-senha/{token}",
                    data={"csrf_token": csrf, "senha": "novasenha123",
                          "confirmacao": "outracoisa123"},
                    follow_redirects=True)
    assert r.status_code == 200
    # Senha permaneceu a original
    usuario = Usuario.query.filter_by(email="lancha@test.com").first()
    assert check_password_hash(usuario.senha_hash, "testpass")


def test_redefinir_senha_curta_rejeita(app, client):
    uid = Usuario.query.filter_by(email="lancha@test.com").first().id
    token = _gera_token(app, uid)
    csrf = _get_csrf(client, f"/redefinir-senha/{token}")
    r = client.post(f"/redefinir-senha/{token}",
                    data={"csrf_token": csrf, "senha": "curta", "confirmacao": "curta"},
                    follow_redirects=True)
    assert r.status_code == 200
    usuario = Usuario.query.filter_by(email="lancha@test.com").first()
    assert check_password_hash(usuario.senha_hash, "testpass")


def test_redefinir_senha_usuario_logado_redireciona_dashboard(client_lanchA):
    """Usuario ja autenticado nao acessa tela de recuperacao."""
    r = client_lanchA.get("/esqueci-senha", follow_redirects=False)
    assert r.status_code == 302
    r = client_lanchA.get("/redefinir-senha/qualquer", follow_redirects=False)
    assert r.status_code == 302


def test_redefinir_senha_token_one_use(app, client):
    """Token ja usado (senha_atualizada_em > timestamp do token) eh rejeitado."""
    usuario = Usuario.query.filter_by(email="lancha@test.com").first()
    token = _gera_token(app, usuario.id)

    # 1a tentativa: funciona
    csrf = _get_csrf(client, f"/redefinir-senha/{token}")
    client.post(f"/redefinir-senha/{token}",
                data={"csrf_token": csrf, "senha": "senha1_nova",
                      "confirmacao": "senha1_nova"},
                follow_redirects=False)

    # 2a tentativa com o MESMO token (como se atacante tivesse pego do log):
    # usuario.senha_atualizada_em >= timestamp do token -> rejeita
    from app import db as _db
    from app.models import Usuario as U
    u = _db.session.get(U, usuario.id)
    assert u.senha_atualizada_em is not None

    r = client.get(f"/redefinir-senha/{token}", follow_redirects=False)
    assert r.status_code == 302
    assert "/esqueci-senha" in r.headers["Location"]


def test_login_timing_equalizado(client):
    """Nao eh teste de timing de fato (instavel), so garante que email inexistente
    nao da erro de servidor e tem mesma resposta visivel (flash 'E-mail ou senha
    incorretos')."""
    r = client.post("/login",
                    data={"email": "ninguem@lugar.nenhum", "senha": "qualquer"},
                    follow_redirects=False)
    assert r.status_code == 200  # renderiza login de volta com flash
    assert b"incorretos" in r.data

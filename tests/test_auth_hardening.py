"""Testes de hardening de seguranca em auth.py.

Cobre 2 criticos fechados no ciclo 5:
1. Session fixation — login descarta cookie de sessao pre-autenticacao
2. Open redirect — ?next= so aceita paths/URLs do proprio host
"""
import re


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


# ---------- Open redirect ----------

def test_login_next_externo_rejeitado(app, client):
    """?next=https://evil.example/fake deve redirect pro dashboard, nao pro evil."""
    token = _csrf(client, "/login?next=https://evil.example/fake")
    r = client.post(
        "/login?next=https://evil.example/fake",
        data={"csrf_token": token, "email": "lancha@test.com", "senha": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    # Redirect NAO deve apontar pro host malicioso
    assert "evil.example" not in r.headers.get("Location", "")


def test_login_next_protocolo_javascript_rejeitado(app, client):
    """?next=javascript:alert(1) deve ser bloqueado."""
    token = _csrf(client, "/login")
    r = client.post(
        "/login?next=javascript:alert(1)",
        data={"csrf_token": token, "email": "lancha@test.com", "senha": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "javascript:" not in r.headers.get("Location", "")


def test_login_next_dupla_barra_rejeitado(app, client):
    """?next=//evil.example (protocol-relative) deve ser bloqueado."""
    token = _csrf(client, "/login")
    r = client.post(
        "/login?next=//evil.example/phish",
        data={"csrf_token": token, "email": "lancha@test.com", "senha": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    location = r.headers.get("Location", "")
    # Protocol-relative URL deve cair pro dashboard, nao pro host externo
    assert "evil.example" not in location


def test_login_next_path_relativo_aceito(app, client):
    """?next=/pedidos eh path interno legitimo, deve ser respeitado."""
    token = _csrf(client, "/login")
    r = client.post(
        "/login?next=/pedidos",
        data={"csrf_token": token, "email": "lancha@test.com", "senha": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get("Location", "").endswith("/pedidos")


def test_login_sem_next_redireciona_dashboard(app, client):
    """Sem ?next=, login vai pro main.dashboard (comportamento default)."""
    token = _csrf(client, "/login")
    r = client.post(
        "/login",
        data={"csrf_token": token, "email": "lancha@test.com", "senha": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    location = r.headers.get("Location", "")
    # Aceita tanto path relativo /dashboard quanto URL absoluta
    assert "dashboard" in location or location.endswith("/")


# ---------- Session fixation ----------

def test_login_descarta_sessao_pre_autenticacao(app, client):
    """Cookie plantado ANTES do login deve ser invalidado.

    Simulacao: setamos um valor na session antes de logar, confirmamos que ele
    some apos o login (session.clear() foi chamado).
    """
    # Planta um valor na sessao pre-login
    with client.session_transaction() as sess:
        sess["valor_plantado"] = "atacante-plantou-isso"

    token = _csrf(client, "/login")
    r = client.post(
        "/login",
        data={"csrf_token": token, "email": "lancha@test.com", "senha": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code == 302

    # Apos login, valor plantado NAO deve existir mais (session.clear limpou)
    with client.session_transaction() as sess:
        assert "valor_plantado" not in sess, (
            "Session fixation: valor plantado antes do login sobreviveu. "
            "session.clear() deveria ter zerado."
        )


def test_session_protection_strong_configurado(app):
    """login_manager.session_protection deve estar em 'strong'."""
    from app import login_manager
    assert login_manager.session_protection == "strong"

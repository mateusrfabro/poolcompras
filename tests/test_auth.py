"""Testes de autenticacao e autorizacao."""


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"Entrar" in r.data


def test_login_success_redirects(client):
    r = client.post("/login",
                     data={"email": "lancha@test.com", "senha": "testpass"},
                     follow_redirects=False)
    assert r.status_code == 302
    assert "/dashboard" in r.headers["Location"]


def test_login_wrong_password(client):
    r = client.post("/login",
                     data={"email": "lancha@test.com", "senha": "errada"},
                     follow_redirects=True)
    assert b"incorretos" in r.data or b"incorreta" in r.data


def test_login_wrong_email(client):
    r = client.post("/login",
                     data={"email": "naoexiste@test.com", "senha": "x"},
                     follow_redirects=True)
    assert b"incorret" in r.data


def test_dashboard_sem_auth_redireciona_para_login(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_logout(client_lanchA):
    """Logout via POST + CSRF token."""
    import re
    r0 = client_lanchA.get("/dashboard")
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r0.data)
    csrf = m.group(1).decode() if m else None

    r = client_lanchA.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 302
    # Apos logout, dashboard deve redirecionar pra /login
    r2 = client_lanchA.get("/dashboard", follow_redirects=False)
    assert r2.status_code == 302
    assert "/login" in r2.headers["Location"]


def test_logout_get_bloqueado(client_lanchA):
    """Defesa contra <img src='/logout'> derrubando sessao via CSRF."""
    r = client_lanchA.get("/logout", follow_redirects=False)
    assert r.status_code == 405  # Method Not Allowed


def test_historico_bloqueia_admin(client_admin):
    r = client_admin.get("/minhas-rodadas/", follow_redirects=False)
    # Admin eh redirecionado (warning + back to dashboard)
    assert r.status_code == 302


def test_historico_bloqueia_fornecedor(client_forn):
    r = client_forn.get("/minhas-rodadas/", follow_redirects=False)
    assert r.status_code == 302
"""Testes de seguranca: headers, CSRF (em app real) e IDOR."""


def test_security_headers_present(client):
    r = client.get("/login")
    h = r.headers
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert "Content-Security-Policy" in h
    assert "Referrer-Policy" in h


def test_csp_strict_em_scripts(client):
    csp = client.get("/login").headers.get("Content-Security-Policy", "")
    # script-src deve ser 'self' (sem unsafe-inline)
    assert "script-src 'self'" in csp
    # default-src tambem 'self'
    assert "default-src 'self'" in csp


def test_csrf_protege_post_em_app_real(app):
    """Testa em client separado com CSRF ligado (fixture desliga por padrao)."""
    app.config["WTF_CSRF_ENABLED"] = True
    c = app.test_client()
    r = c.post("/login", data={"email": "lancha@test.com", "senha": "testpass"})
    # Sem csrf_token no form deve dar 400
    assert r.status_code == 400


def test_idor_pedido_nao_pode_ser_removido_por_outra_lanchonete(
        app, client_lanchB):
    """Lanchonete A cria pedido; Lanchonete B (logada) nao deve conseguir remover."""
    from app.models import ItemPedido, Usuario, Rodada, Produto
    from app import db

    with app.app_context():
        lanchA = Usuario.query.filter_by(email="lancha@test.com").first().lanchonete
        rodada = Rodada.query.first()
        produto = Produto.query.first()
        item = ItemPedido(rodada_id=rodada.id, lanchonete_id=lanchA.id,
                           produto_id=produto.id, quantidade=5)
        db.session.add(item)
        db.session.commit()
        item_id = item.id
        lancha_id = lanchA.id

    # Lanchonete B tenta remover — deve falhar com flash error
    r = client_lanchB.post(f"/pedidos/remover/{item_id}", follow_redirects=False)
    assert r.status_code == 302  # redirect (nao permitido)

    # Confirma: item da lanchA ainda existe
    with app.app_context():
        ainda = db.session.get(ItemPedido, item_id)
        assert ainda is not None, "IDOR violado: item removido pela lanchonete errada"
        assert ainda.lanchonete_id == lancha_id


def test_upload_sem_auth_redireciona(client):
    """GET /uploads/<key> sem login vai pra /login."""
    r = client.get("/uploads/comprovantes/fake.pdf", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_upload_404_se_key_inexistente(client_lanchA):
    """Usuario autenticado mas key nao pertence a nenhuma participacao = 404."""
    r = client_lanchA.get("/uploads/comprovantes/inexistente.pdf")
    assert r.status_code == 404


def test_rate_limit_disabled_em_testes(client):
    """Sanity check: com RATELIMIT_ENABLED=False, login espamado nao da 429."""
    for _ in range(8):
        r = client.post("/login",
                         data={"email": "x@x.com", "senha": "y"},
                         follow_redirects=False)
        assert r.status_code != 429, "rate limit nao deveria disparar em testes"

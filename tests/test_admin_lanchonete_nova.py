"""Testes da rota admin /admin/lanchonetes/nova."""
import re
from werkzeug.security import check_password_hash

from app import db
from app.models import Lanchonete, Usuario


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


def test_form_nova_renderiza(client_admin):
    r = client_admin.get("/admin/lanchonetes/nova")
    assert r.status_code == 200
    assert b"Nova Lanchonete" in r.data
    assert b"E-mail de acesso" in r.data
    assert b"Senha inicial" in r.data


def test_admin_cria_lanchonete_com_login(app, client_admin):
    csrf = _csrf(client_admin, "/admin/lanchonetes/nova")
    r = client_admin.post("/admin/lanchonetes/nova", data={
        "csrf_token": csrf,
        "email": "novatese@demo.com",
        "senha": "senha12345",
        "nome_responsavel": "Fulano da Silva",
        "telefone": "(43) 99999-0000",
        "nome_fantasia": "Nova Lanchonete",
        "cnpj": "",
        "endereco": "Rua X",
        "bairro": "Centro",
        "cidade": "Londrina",
        "ativa": "on",
    }, follow_redirects=False)
    assert r.status_code == 302
    # Usuario + Lanchonete criados e vinculados
    u = Usuario.query.filter_by(email="novatese@demo.com").first()
    assert u is not None
    assert u.tipo == "lanchonete"
    assert check_password_hash(u.senha_hash, "senha12345")
    l = Lanchonete.query.filter_by(nome_fantasia="Nova Lanchonete").first()
    assert l is not None
    assert l.usuario_id == u.id
    assert l.ativa is True


def test_email_duplicado_rejeitado(app, client_admin):
    csrf = _csrf(client_admin, "/admin/lanchonetes/nova")
    r = client_admin.post("/admin/lanchonetes/nova", data={
        "csrf_token": csrf,
        "email": "lancha@test.com",  # ja existe no seed
        "senha": "novasenha123",
        "nome_responsavel": "Tentativa",
        "nome_fantasia": "Clone",
    })
    assert Lanchonete.query.filter_by(nome_fantasia="Clone").first() is None


def test_senha_curta_rejeitada(app, client_admin):
    csrf = _csrf(client_admin, "/admin/lanchonetes/nova")
    client_admin.post("/admin/lanchonetes/nova", data={
        "csrf_token": csrf,
        "email": "curta@demo.com",
        "senha": "123",
        "nome_responsavel": "Teste",
        "nome_fantasia": "CurtaSenha",
    })
    assert Usuario.query.filter_by(email="curta@demo.com").first() is None


def test_campos_obrigatorios(app, client_admin):
    csrf = _csrf(client_admin, "/admin/lanchonetes/nova")
    client_admin.post("/admin/lanchonetes/nova", data={
        "csrf_token": csrf,
        "email": "",
        "senha": "",
        "nome_responsavel": "",
        "nome_fantasia": "",
    })
    # Ainda 2 lanchonetes do seed (A e B), nenhuma criada
    assert Lanchonete.query.count() == 2


def test_lanchonete_nao_admin_nao_acessa(client_lanchA):
    r = client_lanchA.get("/admin/lanchonetes/nova", follow_redirects=False)
    assert r.status_code == 302  # admin_required redireciona

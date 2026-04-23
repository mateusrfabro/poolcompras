"""Testes das rotas /admin/produtos/novo e /editar.

Cobre:
- Campo subcategoria eh obrigatorio (regra de negocio do PoolCompras)
- Criacao/edicao com todos os campos validos
- Toggle ativo na edicao
- Authz (so admin)
"""
import re

from app import db
from app.models import Produto


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


# ---------- /produtos/novo ----------

def test_admin_cria_produto_ok(app, client_admin):
    token = _csrf(client_admin, "/admin/produtos/novo")
    r = client_admin.post(
        "/admin/produtos/novo",
        data={
            "csrf_token": token,
            "nome": "Bacon Fatiado",
            "categoria": "Carne",
            "subcategoria": "Bacon",
            "unidade": "kg",
            "descricao": "Premium defumado",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    p = Produto.query.filter_by(nome="Bacon Fatiado").first()
    assert p is not None
    assert p.categoria == "Carne"
    assert p.subcategoria == "Bacon"
    assert p.ativo is True  # Default ativo


def test_admin_cria_produto_sem_subcategoria_rejeita(app, client_admin):
    """Subcategoria eh obrigatoria — retorna 200 com form + flash error."""
    token = _csrf(client_admin, "/admin/produtos/novo")
    antes = Produto.query.count()
    r = client_admin.post(
        "/admin/produtos/novo",
        data={
            "csrf_token": token,
            "nome": "Produto Sem Sub",
            "categoria": "Outro",
            "subcategoria": "",
            "unidade": "un",
        },
        follow_redirects=False,
    )
    # Renderiza o form de volta (200), nao redireciona
    assert r.status_code == 200
    assert Produto.query.count() == antes
    assert Produto.query.filter_by(nome="Produto Sem Sub").first() is None


def test_lanchonete_nao_cria_produto(app, client_lanchA):
    r = client_lanchA.post(
        "/admin/produtos/novo",
        data={"nome": "X", "categoria": "Y", "subcategoria": "Z", "unidade": "un"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert Produto.query.filter_by(nome="X").first() is None


def test_fornecedor_nao_cria_produto(app, client_forn):
    r = client_forn.post(
        "/admin/produtos/novo",
        data={"nome": "Y", "categoria": "A", "subcategoria": "B", "unidade": "un"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert Produto.query.filter_by(nome="Y").first() is None


# ---------- /produtos/<id>/editar ----------

def test_admin_edita_produto_ok(app, client_admin):
    p = Produto.query.first()
    p_id = p.id
    token = _csrf(client_admin, f"/admin/produtos/{p_id}/editar")
    r = client_admin.post(
        f"/admin/produtos/{p_id}/editar",
        data={
            "csrf_token": token,
            "nome": "Blend 200g Renomeado",
            "categoria": "Carne",
            "subcategoria": "Hamburguer Premium",
            "unidade": "kg",
            "descricao": "Editado via teste",
            "ativo": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    atualizado = db.session.get(Produto, p_id)
    assert atualizado.nome == "Blend 200g Renomeado"
    assert atualizado.subcategoria == "Hamburguer Premium"
    assert atualizado.descricao == "Editado via teste"
    assert atualizado.ativo is True


def test_admin_desativa_produto_via_edicao(app, client_admin):
    """Nao enviar 'ativo' no form = produto fica inativo."""
    p = Produto.query.first()
    p.ativo = True
    db.session.commit()
    p_id = p.id

    token = _csrf(client_admin, f"/admin/produtos/{p_id}/editar")
    client_admin.post(
        f"/admin/produtos/{p_id}/editar",
        data={
            "csrf_token": token,
            "nome": p.nome,
            "categoria": p.categoria,
            "subcategoria": p.subcategoria or "X",
            "unidade": p.unidade,
            # 'ativo' nao enviado
        },
        follow_redirects=False,
    )
    assert db.session.get(Produto, p_id).ativo is False


def test_admin_edita_sem_subcategoria_rejeita(app, client_admin):
    p = Produto.query.first()
    nome_original = p.nome
    p_id = p.id

    token = _csrf(client_admin, f"/admin/produtos/{p_id}/editar")
    r = client_admin.post(
        f"/admin/produtos/{p_id}/editar",
        data={
            "csrf_token": token,
            "nome": "Nao deve salvar",
            "categoria": "Carne",
            "subcategoria": "",
            "unidade": "kg",
        },
        follow_redirects=False,
    )
    # Retorna 200 (re-renderiza form), nome nao muda
    assert r.status_code == 200
    assert db.session.get(Produto, p_id).nome == nome_original


def test_produto_inexistente_404(app, client_admin):
    r = client_admin.get("/admin/produtos/99999/editar", follow_redirects=False)
    assert r.status_code == 404

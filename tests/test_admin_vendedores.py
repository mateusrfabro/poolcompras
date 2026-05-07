"""CRUD admin de Vendedores + atribuicao em Lanchonete e Fornecedor."""
import re

from app import db
from app.models import Lanchonete, Fornecedor, Usuario, Vendedor


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


def test_listagem_vendedores_renderiza(client_admin):
    r = client_admin.get("/admin/vendedores")
    assert r.status_code == 200
    assert b"Vendedor Teste" in r.data


def test_form_novo_renderiza(client_admin):
    r = client_admin.get("/admin/vendedores/novo")
    assert r.status_code == 200
    assert b"Novo Vendedor" in r.data
    assert b"Meta mensal" in r.data


def test_admin_cria_vendedor_com_login(client_admin, app):
    r = client_admin.post("/admin/vendedores/novo", data={
        "csrf_token": _csrf(client_admin, "/admin/vendedores/novo"),
        "email": "novo.sdr@aggron.com.br",
        "nome": "SDR Novo",
        "telefone": "(43) 99999-9999",
        "meta_mensal_clientes": "12",
    }, follow_redirects=False)
    assert r.status_code == 302

    u = Usuario.query.filter_by(email="novo.sdr@aggron.com.br").first()
    assert u is not None
    assert u.tipo == "vendedor"
    v = Vendedor.query.filter_by(usuario_id=u.id).first()
    assert v is not None
    assert v.nome == "SDR Novo"
    assert v.meta_mensal_clientes == 12
    assert v.ativo is True


def test_email_duplicado_bloqueia_criacao(client_admin):
    r = client_admin.post("/admin/vendedores/novo", data={
        "csrf_token": _csrf(client_admin, "/admin/vendedores/novo"),
        "email": "vendedor@test.com",  # ja existe no seed
        "nome": "Outro",
        "meta_mensal_clientes": "10",
    }, follow_redirects=False)
    assert r.status_code == 200  # form re-renderizado


def test_admin_edita_vendedor(client_admin, app):
    v = Vendedor.query.first()
    r = client_admin.post(f"/admin/vendedores/{v.id}/editar", data={
        "csrf_token": _csrf(client_admin, f"/admin/vendedores/{v.id}/editar"),
        "nome": "Nome Atualizado",
        "meta_mensal_clientes": "20",
        "ativo": "on",
    }, follow_redirects=False)
    assert r.status_code == 302
    db.session.refresh(v)
    assert v.nome == "Nome Atualizado"
    assert v.meta_mensal_clientes == 20


def test_inativar_vendedor_inativa_usuario(client_admin, app):
    """Vendedor desativado tambem nao consegue logar (Usuario.ativo)."""
    v = Vendedor.query.first()
    assert v.responsavel.ativo is True
    r = client_admin.post(f"/admin/vendedores/{v.id}/editar", data={
        "csrf_token": _csrf(client_admin, f"/admin/vendedores/{v.id}/editar"),
        "nome": v.nome,
        "meta_mensal_clientes": "10",
        # 'ativo' NAO marcado = inativo
    }, follow_redirects=False)
    assert r.status_code == 302
    db.session.refresh(v)
    assert v.ativo is False
    assert v.responsavel.ativo is False


def test_lanchonete_atribuida_a_vendedor(client_admin, app):
    """Form admin de lanchonete tem dropdown e persiste vendedor_id."""
    lanch = Lanchonete.query.first()
    v = Vendedor.query.first()
    # GET pra confirmar que dropdown renderiza
    r = client_admin.get(f"/admin/lanchonetes/{lanch.id}/editar")
    assert r.status_code == 200
    assert b"Vendedor responsavel" in r.data or b"Vendedor respons" in r.data
    assert v.nome.encode() in r.data

    r = client_admin.post(f"/admin/lanchonetes/{lanch.id}/editar", data={
        "csrf_token": _csrf(client_admin, f"/admin/lanchonetes/{lanch.id}/editar"),
        "nome_fantasia": lanch.nome_fantasia,
        "cnpj": lanch.cnpj or "",
        "endereco": lanch.endereco or "",
        "bairro": lanch.bairro or "",
        "cidade": lanch.cidade or "Londrina",
        "vendedor_id": str(v.id),
        "ativa": "on",
    }, follow_redirects=False)
    assert r.status_code == 302
    db.session.refresh(lanch)
    assert lanch.vendedor_id == v.id


def test_fornecedor_atribuido_a_vendedor(client_admin, app):
    forn = Fornecedor.query.first()
    v = Vendedor.query.first()
    r = client_admin.post(f"/admin/fornecedores/{forn.id}/editar", data={
        "csrf_token": _csrf(client_admin, f"/admin/fornecedores/{forn.id}/editar"),
        "razao_social": forn.razao_social,
        "nome_contato": forn.nome_contato or "",
        "telefone": forn.telefone or "",
        "email": forn.email or "",
        "cidade": forn.cidade or "",
        "chave_pix": forn.chave_pix or "",
        "banco": forn.banco or "",
        "agencia": forn.agencia or "",
        "conta": forn.conta or "",
        "percentual_comissao": str(forn.percentual_comissao or 0),
        "vendedor_id": str(v.id),
        "ativo": "on",
    }, follow_redirects=False)
    assert r.status_code == 302
    db.session.refresh(forn)
    assert forn.vendedor_id == v.id


def test_lanchonete_lanchA_continua_logando(client_lanchA):
    """Sanity: alteracoes no conftest nao quebraram login da lanchonete."""
    r = client_lanchA.get("/dashboard")
    assert r.status_code == 200


def test_vendedor_loga_e_acessa_dashboard(client_vendedor):
    """Vendedor existe + loga + ve dashboard sem 403."""
    r = client_vendedor.get("/dashboard")
    # Pode redirecionar pra rota especifica do vendedor; aceitar 200 ou 302.
    assert r.status_code in (200, 302)

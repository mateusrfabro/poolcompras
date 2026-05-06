"""Calculo de comissao do fornecedor + telas /admin/comissoes e /fornecedor/comissoes."""
from decimal import Decimal

from app import db
from app.models import Fornecedor
from app.services.comissao_fornecedor import (
    calcular_comissao_fornecedor, calcular_comissoes_todos_fornecedores,
)


def test_comissao_zero_quando_pct_zero(app):
    """Fornecedor sem % configurada -> comissao_total = 0."""
    f = Fornecedor.query.first()
    f.percentual_comissao = Decimal("0")
    db.session.commit()
    dados = calcular_comissao_fornecedor(f.id)
    assert dados["percentual"] == Decimal("0")
    assert dados["comissao_total"] == 0


def test_calcular_comissoes_todos_lista_fornecedores_ativos(app):
    """Service de visao admin retorna 1 linha por fornecedor ativo."""
    linhas = calcular_comissoes_todos_fornecedores()
    assert len(linhas) >= 1
    nomes = [l["razao_social"] for l in linhas]
    assert "Fornec Teste" in nomes


def test_admin_get_comissoes_renderiza(client_admin):
    r = client_admin.get("/admin/comissoes")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Comiss" in body
    assert "Fornec Teste" in body


def test_admin_get_comissoes_detalhe(client_admin, app):
    f = Fornecedor.query.first()
    r = client_admin.get(f"/admin/comissoes/{f.id}")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Fornec Teste" in body
    assert "Por rodada" in body


def test_admin_get_comissoes_detalhe_404(client_admin):
    r = client_admin.get("/admin/comissoes/99999")
    assert r.status_code == 404


def test_fornecedor_ve_proprias_comissoes(client_forn):
    r = client_forn.get("/fornecedor/comissoes")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Comissão" in body or "Comiss" in body


def test_lanchonete_nao_acessa_comissoes(client_lanchA):
    r = client_lanchA.get("/admin/comissoes")
    assert r.status_code in (302, 403)
    r = client_lanchA.get("/fornecedor/comissoes")
    assert r.status_code in (302, 403)


def test_form_admin_aceita_pct(client_admin, app):
    """POST do form do fornecedor persiste percentual_comissao."""
    import re
    f = Fornecedor.query.first()
    rget = client_admin.get(f"/admin/fornecedores/{f.id}/editar")
    csrf = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', rget.data).group(1).decode()
    r = client_admin.post(f"/admin/fornecedores/{f.id}/editar", data={
        "csrf_token": csrf,
        "razao_social": f.razao_social,
        "nome_contato": f.nome_contato or "",
        "telefone": f.telefone or "",
        "email": f.email or "",
        "cidade": f.cidade or "",
        "chave_pix": f.chave_pix or "",
        "banco": f.banco or "",
        "agencia": f.agencia or "",
        "conta": f.conta or "",
        "percentual_comissao": "3.5",
        "ativo": "on",
    })
    assert r.status_code == 302
    db.session.refresh(f)
    assert f.percentual_comissao == Decimal("3.50")


def test_form_admin_clampa_pct_acima_de_100(client_admin, app):
    """Input > 100 vira 100 (clamp defensivo na rota)."""
    import re
    f = Fornecedor.query.first()
    rget = client_admin.get(f"/admin/fornecedores/{f.id}/editar")
    csrf = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', rget.data).group(1).decode()
    client_admin.post(f"/admin/fornecedores/{f.id}/editar", data={
        "csrf_token": csrf,
        "razao_social": f.razao_social,
        "percentual_comissao": "150",
        "ativo": "on",
    })
    db.session.refresh(f)
    assert f.percentual_comissao == Decimal("100")


def test_form_admin_clampa_pct_negativo(client_admin, app):
    import re
    f = Fornecedor.query.first()
    rget = client_admin.get(f"/admin/fornecedores/{f.id}/editar")
    csrf = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', rget.data).group(1).decode()
    client_admin.post(f"/admin/fornecedores/{f.id}/editar", data={
        "csrf_token": csrf,
        "razao_social": f.razao_social,
        "percentual_comissao": "-5",
        "ativo": "on",
    })
    db.session.refresh(f)
    assert f.percentual_comissao == Decimal("0")

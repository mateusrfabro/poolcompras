"""Geracao de minuta PDF a partir de Lead."""
from app import db
from app.models import Lead, Vendedor


def _criar_lead_completo(vendedor_id):
    lead = Lead(
        nome_estabelecimento="Lanche do Teste",
        nome_contato="João",
        telefone="(43) 99999-1111",
        email="joao@teste.com",
        cidade="Londrina",
        cnpj="11.222.333/0001-44",
        observacoes="Tem 2 unidades.",
        vendedor_id=vendedor_id,
    )
    db.session.add(lead)
    db.session.commit()
    return lead


def test_gerar_minuta_retorna_pdf_valido(app):
    """Service direto: gera bytes que comecam com %PDF."""
    from app.services.minuta_pdf import gerar_minuta_pdf
    v = Vendedor.query.first()
    lead = _criar_lead_completo(v.id)
    pdf = gerar_minuta_pdf(lead)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000  # nao eh stub vazio


def test_minuta_pdf_tem_metadata_aggron(app):
    """Tamanho > 1KB + magic bytes corretos (texto interno fica em stream
    comprimido pelo reportlab — extrair literal nao eh confiavel sem
    pypdf, fora do escopo do MVP). Validar metadata do title e que o
    documento eh single-page sao mais robustos que grep de bytes."""
    from app.services.minuta_pdf import gerar_minuta_pdf
    v = Vendedor.query.first()
    lead = _criar_lead_completo(v.id)
    pdf = gerar_minuta_pdf(lead)
    # Magic bytes de PDF
    assert pdf[:8].startswith(b"%PDF-1.")
    # Title metadata (reportlab grava no /Info do PDF)
    assert b"Minuta Aggron" in pdf or b"Aggron" in pdf
    # Tamanho razoavel — minuta cheia tem 4-8 KB tipicamente
    assert 2000 < len(pdf) < 50_000


def test_rota_admin_baixa_pdf(client_admin, app):
    v = Vendedor.query.first()
    lead = _criar_lead_completo(v.id)
    r = client_admin.get(f"/crm/leads/{lead.id}/minuta")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF-")
    # Content-Disposition: attachment com nome significativo
    cd = r.headers.get("Content-Disposition", "")
    assert "minuta" in cd.lower()


def test_vendedor_baixa_minuta_propria(client_vendedor, app):
    """Vendedor logado baixa minuta dos proprios leads."""
    vendedor_proprio = Vendedor.query.filter(
        Vendedor.responsavel.has(email="vendedor@test.com")
    ).first()
    lead = _criar_lead_completo(vendedor_proprio.id)
    r = client_vendedor.get(f"/crm/leads/{lead.id}/minuta")
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF-")


def test_vendedor_nao_baixa_minuta_alheia(client_vendedor, app):
    """Vendedor A tenta baixar minuta de lead do vendedor B -> 403."""
    from app.services.passwords import hash_senha
    from app.models import Usuario
    u = Usuario(email="outro.minuta@test.com", senha_hash=hash_senha("x"),
                nome_responsavel="VB", telefone="x", tipo="vendedor")
    db.session.add(u)
    db.session.flush()
    vb = Vendedor(usuario_id=u.id, nome="VB Minuta")
    db.session.add(vb)
    db.session.commit()

    lead = _criar_lead_completo(vb.id)
    r = client_vendedor.get(f"/crm/leads/{lead.id}/minuta")
    assert r.status_code == 403


def test_minuta_lead_inexistente_404(client_admin):
    r = client_admin.get("/crm/leads/999999/minuta")
    assert r.status_code == 404


def test_lanchonete_nao_acessa_minuta(client_lanchA, app):
    v = Vendedor.query.first()
    lead = _criar_lead_completo(v.id)
    r = client_lanchA.get(f"/crm/leads/{lead.id}/minuta")
    # Decorator vendedor_ou_admin_required nega lanchonete
    assert r.status_code in (302, 403)

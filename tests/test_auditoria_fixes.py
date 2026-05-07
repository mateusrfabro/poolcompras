"""Cobertura dos fixes da auditoria multi-agente (Commit B).

- Magic bytes %PDF- no upload NF + 0 bytes
- Lead cancelado nao pode ser convertido (guard explicito)
- Vendedor inativo nao recebe lead novo
- Idempotencia de gerar_contrato_retroativo (flash diferente em 2a chamada)
- Range Python no KPI pago_mes (sargable + bordas de mes corretas)
- Decimal preservado em comissao_fornecedor
"""
import io
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app import db
from app.models import (
    Lead, Vendedor, Lanchonete, Fatura, Usuario,
)
from app.services.assinatura import (
    criar_assinatura_inicial, criar_assinatura_inicial_idempotente,
)
from app.services.passwords import hash_senha


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


# ---------- Upload NF: magic bytes + 0 bytes ----------

def test_upload_nf_rejeita_arquivo_nao_pdf_com_extensao_pdf(client_admin, app):
    """HTML com nome .pdf e mime forjado deve ser barrado (magic bytes)."""
    lanch = Lanchonete.query.first()
    a = criar_assinatura_inicial(lanch)
    fatura = a.faturas[0]
    payload = b"<html><script>alert(1)</script></html>"
    r = client_admin.post(
        f"/admin/financeiro/fatura/{fatura.id}/nf",
        data={
            "csrf_token": _csrf(client_admin, "/admin/financeiro"),
            "nf": (io.BytesIO(payload), "fake.pdf", "application/pdf"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 302
    db.session.refresh(fatura)
    assert fatura.nf_pdf_key is None  # nao salvou


def test_upload_nf_rejeita_arquivo_vazio(client_admin, app):
    lanch = Lanchonete.query.first()
    a = criar_assinatura_inicial(lanch)
    fatura = a.faturas[0]
    r = client_admin.post(
        f"/admin/financeiro/fatura/{fatura.id}/nf",
        data={
            "csrf_token": _csrf(client_admin, "/admin/financeiro"),
            "nf": (io.BytesIO(b""), "vazio.pdf", "application/pdf"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 302
    db.session.refresh(fatura)
    assert fatura.nf_pdf_key is None


def test_upload_nf_aceita_pdf_real(client_admin, app):
    lanch = Lanchonete.query.first()
    a = criar_assinatura_inicial(lanch)
    fatura = a.faturas[0]
    pdf_real = b"%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\n%%EOF"
    r = client_admin.post(
        f"/admin/financeiro/fatura/{fatura.id}/nf",
        data={
            "csrf_token": _csrf(client_admin, "/admin/financeiro"),
            "nf": (io.BytesIO(pdf_real), "real.pdf", "application/pdf"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 302
    db.session.refresh(fatura)
    assert fatura.nf_pdf_key is not None


# ---------- Lead cancelado: guard contra conversao ----------

def test_lead_cancelado_nao_converte(client_admin, app):
    v = Vendedor.query.first()
    lead = Lead(
        nome_estabelecimento="Cancelado",
        telefone="(43) 99999-1111",
        email="cancelado@x.com",
        vendedor_id=v.id,
        status=Lead.STATUS_CANCELADO,
    )
    db.session.add(lead)
    db.session.commit()
    r = client_admin.post(f"/crm/leads/{lead.id}/converter", data={
        "csrf_token": _csrf(client_admin, f"/crm/leads/{lead.id}"),
    }, follow_redirects=False)
    assert r.status_code == 302
    db.session.refresh(lead)
    assert lead.lanchonete_id is None
    assert lead.status == Lead.STATUS_CANCELADO  # nao mudou


# ---------- Vendedor inativo: nao recebe lead novo ----------

def test_admin_nao_atribui_lead_a_vendedor_inativo(client_admin, app):
    """Lead a vendedor inativo viraria orfao — bloquear no submit."""
    u = Usuario(email="inativo.v@test.com", senha_hash=hash_senha("x"),
                nome_responsavel="VI", telefone="x", tipo="vendedor")
    db.session.add(u)
    db.session.flush()
    vi = Vendedor(usuario_id=u.id, nome="VI Inativo", ativo=False)
    db.session.add(vi)
    db.session.commit()

    r = client_admin.post("/crm/leads/novo", data={
        "csrf_token": _csrf(client_admin, "/crm/leads/novo"),
        "nome_estabelecimento": "Tentativa orfa",
        "vendedor_id": str(vi.id),
    }, follow_redirects=False)
    # Form re-renderizado com erro
    assert r.status_code == 200
    assert Lead.query.filter_by(nome_estabelecimento="Tentativa orfa").first() is None


# ---------- gerar_contrato_retroativo: idempotente com flash apropriado ----------

def test_gerar_contrato_retroativo_avisa_quando_ja_existe(client_admin, app):
    """2a chamada na mesma lanchonete: flash 'já tinha contrato', nao 'gerado'."""
    lanch = Lanchonete.query.first()
    # 1a chamada: cria
    r1 = client_admin.post(
        f"/admin/financeiro/lanchonete/{lanch.id}/gerar",
        data={"csrf_token": _csrf(client_admin, "/admin/financeiro")},
        follow_redirects=True,
    )
    assert r1.status_code == 200
    body1 = r1.data.decode("utf-8", errors="ignore")
    assert "Contrato gerado" in body1

    # 2a chamada: idempotente, mensagem diferente
    r2 = client_admin.post(
        f"/admin/financeiro/lanchonete/{lanch.id}/gerar",
        data={"csrf_token": _csrf(client_admin, "/admin/financeiro")},
        follow_redirects=True,
    )
    body2 = r2.data.decode("utf-8", errors="ignore")
    assert "já tinha contrato ativo" in body2


def test_criar_assinatura_inicial_idempotente_devolve_tupla(app):
    lanch = Lanchonete.query.first()
    a1, criada1 = criar_assinatura_inicial_idempotente(lanch)
    a2, criada2 = criar_assinatura_inicial_idempotente(lanch)
    assert criada1 is True
    assert criada2 is False
    assert a1.id == a2.id


# ---------- KPI pago_mes: range Python sargable ----------

def test_kpi_pago_mes_soma_so_pagamentos_do_mes_corrente(client_admin, app):
    """Fatura paga em mes anterior NAO entra; corrente SIM."""
    lanch = Lanchonete.query.first()
    a = criar_assinatura_inicial(lanch)
    f1 = a.faturas[0]
    f2 = a.faturas[1]
    agora = datetime.now(timezone.utc)
    inicio_mes = datetime(agora.year, agora.month, 1, tzinfo=timezone.utc)
    mes_anterior = inicio_mes - timedelta(days=5)

    f1.status = Fatura.STATUS_PAGA
    f1.pago_em = agora  # mes corrente
    f2.status = Fatura.STATUS_PAGA
    f2.pago_em = mes_anterior  # mes anterior — NAO entra no KPI
    db.session.commit()

    r = client_admin.get("/admin/financeiro")
    body = r.data.decode("utf-8", errors="ignore")
    # Apenas valor de f1 (R$ 500,00) deve aparecer no "pago no mes",
    # nao o dobro (1000,00).
    assert "500,00" in body
    assert "1.000,00" not in body and "1000,00" not in body


# ---------- Decimal em comissao_fornecedor ----------

def test_comissao_retorna_decimal_nao_float(app):
    """Auditoria: 'Float pra dinheiro' viola padrao do projeto."""
    from app.services.comissao_fornecedor import calcular_comissao_fornecedor
    from app.models import Fornecedor
    forn = Fornecedor.query.first()
    forn.percentual_comissao = Decimal("3.50")
    db.session.commit()

    dados = calcular_comissao_fornecedor(forn.id)
    assert isinstance(dados["receita_total"], Decimal)
    assert isinstance(dados["comissao_total"], Decimal)
    assert isinstance(dados["percentual"], Decimal)

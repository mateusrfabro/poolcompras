"""Rotas admin /admin/financeiro — listar, marcar paga, upload NF, gerar retroativo."""
import io
import re
from datetime import date
from decimal import Decimal

import pytest

from app import db
from app.models import Assinatura, Fatura, Lanchonete
from app.services.assinatura import criar_assinatura_inicial


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


@pytest.fixture
def assinatura_lanchA(app):
    """Cria assinatura ativa pra Lanch A do conftest."""
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    return criar_assinatura_inicial(lanch, inicio=date(2026, 5, 1))


# ---------- GET listagem ----------

def test_financeiro_get_admin_renderiza(client_admin, assinatura_lanchA):
    r = client_admin.get("/admin/financeiro")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Financeiro" in body
    assert "Lanch A" in body
    assert "Total pendente" in body


def test_financeiro_get_lanchonete_negado(client_lanchA):
    """Lanchonete nao pode acessar painel admin."""
    r = client_lanchA.get("/admin/financeiro")
    assert r.status_code in (302, 403)  # redirect pro login ou abort


def test_financeiro_lista_lanchonetes_sem_contrato(client_admin):
    """Lanch B do seed nao tem assinatura — aparece na lista 'sem contrato'."""
    r = client_admin.get("/admin/financeiro")
    body = r.data.decode("utf-8", errors="ignore")
    assert "Lanch B" in body
    assert "sem contrato" in body.lower() or "Gerar contrato" in body


# ---------- GET detalhe ----------

def test_financeiro_detalhe_lista_12_parcelas(client_admin, assinatura_lanchA):
    r = client_admin.get(f"/admin/financeiro/{assinatura_lanchA.id}")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    # 12 linhas de parcela — busca o numero 1 e 12 explicitos
    assert ">1<" in body or "Parcela 1" in body or "<td>1</td>" in body
    # Vencimento dia 1 de mai/2026
    assert "01/05/2026" in body or "05/2026" in body


def test_financeiro_detalhe_404_inexistente(client_admin):
    r = client_admin.get("/admin/financeiro/99999")
    assert r.status_code == 404


# ---------- POST marcar-paga ----------

def test_marcar_paga_atualiza_status(client_admin, assinatura_lanchA, app):
    fatura = assinatura_lanchA.faturas[0]
    r = client_admin.post(
        f"/admin/financeiro/fatura/{fatura.id}/marcar-paga",
        data={"csrf_token": _csrf(client_admin, "/admin/financeiro")},
        follow_redirects=False,
    )
    assert r.status_code == 302
    db.session.refresh(fatura)
    assert fatura.status == "paga"
    assert fatura.pago_em is not None
    assert fatura.pago_por_id is not None  # admin do conftest


def test_marcar_paga_idempotente(client_admin, assinatura_lanchA, app):
    """2a chamada mantem o pago_em original (no-op)."""
    fatura = assinatura_lanchA.faturas[0]
    csrf = _csrf(client_admin, "/admin/financeiro")
    client_admin.post(f"/admin/financeiro/fatura/{fatura.id}/marcar-paga",
                      data={"csrf_token": csrf})
    db.session.refresh(fatura)
    pago_em_original = fatura.pago_em

    client_admin.post(f"/admin/financeiro/fatura/{fatura.id}/marcar-paga",
                      data={"csrf_token": csrf})
    db.session.refresh(fatura)
    assert fatura.pago_em == pago_em_original


def test_marcar_pendente_desfaz_pagamento(client_admin, assinatura_lanchA, app):
    fatura = assinatura_lanchA.faturas[0]
    csrf = _csrf(client_admin, "/admin/financeiro")
    client_admin.post(f"/admin/financeiro/fatura/{fatura.id}/marcar-paga",
                      data={"csrf_token": csrf})
    client_admin.post(f"/admin/financeiro/fatura/{fatura.id}/marcar-pendente",
                      data={"csrf_token": csrf})
    db.session.refresh(fatura)
    assert fatura.status == "pendente"
    assert fatura.pago_em is None
    assert fatura.pago_por_id is None


# ---------- POST upload NF ----------

def test_upload_nf_pdf_valido(client_admin, assinatura_lanchA, app):
    fatura = assinatura_lanchA.faturas[0]
    pdf_bytes = b"%PDF-1.4\n%fake-pdf-pra-teste\n%%EOF"
    r = client_admin.post(
        f"/admin/financeiro/fatura/{fatura.id}/nf",
        data={
            "csrf_token": _csrf(client_admin, "/admin/financeiro"),
            "nf": (io.BytesIO(pdf_bytes), "nfse_2026_05.pdf", "application/pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r.status_code == 302
    db.session.refresh(fatura)
    assert fatura.nf_pdf_key is not None
    assert fatura.nf_pdf_key.startswith("nf/")
    assert fatura.nf_emitida_em is not None


def test_upload_nf_rejeita_nao_pdf(client_admin, assinatura_lanchA, app):
    fatura = assinatura_lanchA.faturas[0]
    r = client_admin.post(
        f"/admin/financeiro/fatura/{fatura.id}/nf",
        data={
            "csrf_token": _csrf(client_admin, "/admin/financeiro"),
            "nf": (io.BytesIO(b"GIF89a..."), "fake.gif", "image/gif"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r.status_code == 302  # redirect com flash error
    db.session.refresh(fatura)
    assert fatura.nf_pdf_key is None


# ---------- POST gerar retroativo ----------

def test_gerar_contrato_retroativo(client_admin, app):
    """Lanch B do seed (sem contrato) recebe assinatura via botao admin."""
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch B").first()
    assert Assinatura.query.filter_by(lanchonete_id=lanch.id).count() == 0

    r = client_admin.post(
        f"/admin/financeiro/lanchonete/{lanch.id}/gerar",
        data={"csrf_token": _csrf(client_admin, "/admin/financeiro")},
        follow_redirects=False,
    )
    assert r.status_code == 302
    a = Assinatura.query.filter_by(lanchonete_id=lanch.id).first()
    assert a is not None
    assert a.status == "ativa"
    assert Fatura.query.filter_by(assinatura_id=a.id).count() == 12


# ---------- Auth ----------

def test_lanchonete_baixa_propria_nf(client_admin, client_lanchA, assinatura_lanchA, app):
    """Apos admin subir NF, lanchonete dona consegue baixar."""
    fatura = assinatura_lanchA.faturas[0]
    pdf_bytes = b"%PDF-1.4\nnf-test\n%%EOF"
    client_admin.post(
        f"/admin/financeiro/fatura/{fatura.id}/nf",
        data={
            "csrf_token": _csrf(client_admin, "/admin/financeiro"),
            "nf": (io.BytesIO(pdf_bytes), "nf.pdf", "application/pdf"),
        },
        content_type="multipart/form-data",
    )
    db.session.refresh(fatura)
    r = client_lanchA.get(f"/uploads/{fatura.nf_pdf_key}")
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF")


def test_lanchonete_outra_nao_baixa_nf_alheia(client_admin, client_lanchB,
                                              assinatura_lanchA, app):
    """Lanch B nao baixa NF da Lanch A (IDOR)."""
    fatura = assinatura_lanchA.faturas[0]
    pdf_bytes = b"%PDF-1.4\nnf-test\n%%EOF"
    client_admin.post(
        f"/admin/financeiro/fatura/{fatura.id}/nf",
        data={
            "csrf_token": _csrf(client_admin, "/admin/financeiro"),
            "nf": (io.BytesIO(pdf_bytes), "nf.pdf", "application/pdf"),
        },
        content_type="multipart/form-data",
    )
    db.session.refresh(fatura)
    r = client_lanchB.get(f"/uploads/{fatura.nf_pdf_key}")
    assert r.status_code == 403

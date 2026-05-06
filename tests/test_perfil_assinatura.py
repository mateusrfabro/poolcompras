"""Tela /perfil/assinatura — lanchonete ve seu contrato + faturas."""
from datetime import date
from decimal import Decimal

from app import db
from app.models import Lanchonete, Fatura
from app.services.assinatura import criar_assinatura_inicial


def test_assinatura_get_lanchonete_ve_contrato(client_lanchA, app):
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    a = criar_assinatura_inicial(lanch, inicio=date(2026, 5, 1))

    r = client_lanchA.get("/perfil/assinatura")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Plano Aggron" in body
    assert "12x" in body
    assert "500,00" in body
    # Vigencia
    assert "01/05/2026" in body
    # 12 parcelas listadas
    assert "Parcela" in body or "<td>1</td>" in body
    # Status pendente
    assert "Pendente" in body


def test_assinatura_sem_contrato_mostra_mensagem(client_lanchA):
    """Lanchonete legacy sem assinatura ve aviso pra contatar Aggron."""
    r = client_lanchA.get("/perfil/assinatura")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Você ainda não tem contrato gerado" in body
    assert "WhatsApp" in body


def test_assinatura_admin_negado(client_admin):
    """Admin nao tem /perfil/assinatura — eh exclusivo de lanchonete."""
    r = client_admin.get("/perfil/assinatura")
    # lanchonete_required redireciona pra dashboard ou aborta 403
    assert r.status_code in (302, 403)


def test_assinatura_fornecedor_negado(client_forn):
    r = client_forn.get("/perfil/assinatura")
    assert r.status_code in (302, 403)


def test_assinatura_mostra_kpi_pagas_pendentes(client_lanchA, app):
    """Apos marcar 2 faturas como pagas, KPI 'Pagas' fica 2/12."""
    from datetime import datetime, timezone
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    a = criar_assinatura_inicial(lanch, inicio=date(2026, 5, 1))
    # Marca 2 como pagas
    for f in a.faturas[:2]:
        f.status = "paga"
        f.pago_em = datetime.now(timezone.utc)
    db.session.commit()

    r = client_lanchA.get("/perfil/assinatura")
    body = r.data.decode("utf-8", errors="ignore")
    assert "2 / 12" in body or "2/12" in body

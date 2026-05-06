"""Modelo Assinatura + Fatura — constraints e relationships."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Lanchonete, Assinatura, Fatura


def _criar_assinatura(lanch, **overrides):
    """Helper: cria assinatura padrao 12x R$500 com vigencia anual."""
    defaults = dict(
        lanchonete_id=lanch.id,
        valor_mensal=Decimal("500.00"),
        parcelas_total=12,
        vigencia_inicio=date(2026, 5, 1),
        vigencia_fim=date(2027, 4, 30),
        status=Assinatura.STATUS_ATIVA,
    )
    defaults.update(overrides)
    a = Assinatura(**defaults)
    db.session.add(a)
    db.session.commit()
    return a


# ---------- Assinatura ----------

def test_assinatura_criacao_basica(app):
    lanch = Lanchonete.query.first()
    a = _criar_assinatura(lanch)
    assert a.id is not None
    assert a.status == "ativa"
    assert a.parcelas_total == 12
    assert a.valor_mensal == Decimal("500.00")
    assert lanch.assinaturas[0].id == a.id


def test_assinatura_status_invalido_rejeitado(app):
    """CHECK constraint barra status fora da lista."""
    lanch = Lanchonete.query.first()
    a = Assinatura(
        lanchonete_id=lanch.id,
        valor_mensal=Decimal("500.00"),
        parcelas_total=12,
        vigencia_inicio=date(2026, 5, 1),
        vigencia_fim=date(2027, 4, 30),
        status="errado",
    )
    db.session.add(a)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_assinatura_valor_zero_rejeitado(app):
    """Valor mensal precisa ser > 0."""
    lanch = Lanchonete.query.first()
    a = Assinatura(
        lanchonete_id=lanch.id, valor_mensal=Decimal("0"),
        parcelas_total=12,
        vigencia_inicio=date(2026, 5, 1),
        vigencia_fim=date(2027, 4, 30),
    )
    db.session.add(a)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_assinatura_vigencia_invertida_rejeitada(app):
    """vigencia_fim < vigencia_inicio = rejeitado."""
    lanch = Lanchonete.query.first()
    a = Assinatura(
        lanchonete_id=lanch.id, valor_mensal=Decimal("500.00"),
        parcelas_total=12,
        vigencia_inicio=date(2027, 5, 1),
        vigencia_fim=date(2026, 4, 30),
    )
    db.session.add(a)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_assinatura_parcelas_fora_do_range(app):
    """parcelas_total tem que estar em 1..24."""
    lanch = Lanchonete.query.first()
    a = Assinatura(
        lanchonete_id=lanch.id, valor_mensal=Decimal("500.00"),
        parcelas_total=25,
        vigencia_inicio=date(2026, 5, 1),
        vigencia_fim=date(2027, 4, 30),
    )
    db.session.add(a)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ---------- Fatura ----------

def test_fatura_criacao_e_status_default(app):
    lanch = Lanchonete.query.first()
    a = _criar_assinatura(lanch)
    f = Fatura(
        assinatura_id=a.id, parcela_numero=1,
        mes_referencia=date(2026, 5, 1),
        valor=Decimal("500.00"),
        vencimento=date(2026, 5, 5),
    )
    db.session.add(f)
    db.session.commit()
    assert f.status == "pendente"
    assert f.pago_em is None
    assert f.nf_pdf_key is None


def test_fatura_unique_parcela_por_assinatura(app):
    """Parcela 1 da mesma assinatura nao pode ser duplicada."""
    lanch = Lanchonete.query.first()
    a = _criar_assinatura(lanch)
    db.session.add(Fatura(
        assinatura_id=a.id, parcela_numero=1,
        mes_referencia=date(2026, 5, 1),
        valor=Decimal("500.00"),
        vencimento=date(2026, 5, 5),
    ))
    db.session.commit()
    db.session.add(Fatura(
        assinatura_id=a.id, parcela_numero=1,
        mes_referencia=date(2026, 6, 1),
        valor=Decimal("500.00"),
        vencimento=date(2026, 6, 5),
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_fatura_status_invalido_rejeitado(app):
    lanch = Lanchonete.query.first()
    a = _criar_assinatura(lanch)
    f = Fatura(
        assinatura_id=a.id, parcela_numero=1,
        mes_referencia=date(2026, 5, 1),
        valor=Decimal("500.00"),
        vencimento=date(2026, 5, 5),
        status="errado",
    )
    db.session.add(f)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_fatura_cascade_delete_da_assinatura(app):
    """Apagar assinatura apaga as faturas em cascata."""
    lanch = Lanchonete.query.first()
    a = _criar_assinatura(lanch)
    for n in (1, 2, 3):
        db.session.add(Fatura(
            assinatura_id=a.id, parcela_numero=n,
            mes_referencia=date(2026, 4 + n, 1),
            valor=Decimal("500.00"),
            vencimento=date(2026, 4 + n, 5),
        ))
    db.session.commit()
    assert Fatura.query.filter_by(assinatura_id=a.id).count() == 3

    db.session.delete(a)
    db.session.commit()
    assert Fatura.query.filter_by(assinatura_id=a.id).count() == 0


def test_fatura_relationship_pago_por(app):
    """pago_por aponta pra Usuario admin que registrou."""
    from app.models import Usuario
    admin = Usuario.query.filter_by(tipo="admin").first()
    lanch = Lanchonete.query.first()
    a = _criar_assinatura(lanch)
    f = Fatura(
        assinatura_id=a.id, parcela_numero=1,
        mes_referencia=date(2026, 5, 1),
        valor=Decimal("500.00"),
        vencimento=date(2026, 5, 5),
        status=Fatura.STATUS_PAGA,
        pago_em=datetime.now(timezone.utc),
        pago_por_id=admin.id,
    )
    db.session.add(f)
    db.session.commit()
    assert f.pago_por.id == admin.id
    assert f.pago_por.tipo == "admin"


def test_assinatura_faturas_ordenadas_por_parcela(app):
    """relationship faturas vem ordenado por parcela_numero."""
    lanch = Lanchonete.query.first()
    a = _criar_assinatura(lanch)
    # Inserir fora de ordem
    for n in (3, 1, 2):
        db.session.add(Fatura(
            assinatura_id=a.id, parcela_numero=n,
            mes_referencia=date(2026, 4 + n, 1),
            valor=Decimal("500.00"),
            vencimento=date(2026, 4 + n, 5),
        ))
    db.session.commit()
    db.session.refresh(a)
    numeros = [f.parcela_numero for f in a.faturas]
    assert numeros == [1, 2, 3]

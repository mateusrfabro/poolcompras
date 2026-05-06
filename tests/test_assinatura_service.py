"""Service criar_assinatura_inicial — geracao automatica no signup."""
from datetime import date
from decimal import Decimal

from app import db
from app.models import Assinatura, Fatura, Lanchonete, Usuario
from app.services.assinatura import (
    VALOR_MENSAL_PADRAO, PARCELAS_PADRAO,
    criar_assinatura_inicial,
)
from app.services.passwords import hash_senha


def _criar_lanchonete_extra(nome="Lanch Extra", email="extra@test.com"):
    u = Usuario(email=email, senha_hash=hash_senha("testpass"),
                nome_responsavel=nome, telefone="(43) 99999-0000",
                tipo="lanchonete")
    db.session.add(u)
    db.session.flush()
    lanch = Lanchonete(usuario_id=u.id, nome_fantasia=nome)
    db.session.add(lanch)
    db.session.commit()
    return lanch


def test_criar_assinatura_inicial_default(app):
    """Default: 12 parcelas R$500 a partir de hoje."""
    lanch = _criar_lanchonete_extra()
    a = criar_assinatura_inicial(lanch)
    assert a.id is not None
    assert a.lanchonete_id == lanch.id
    assert a.parcelas_total == PARCELAS_PADRAO
    assert a.valor_mensal == VALOR_MENSAL_PADRAO
    assert a.status == "ativa"
    # 12 faturas geradas
    faturas = Fatura.query.filter_by(assinatura_id=a.id).all()
    assert len(faturas) == 12
    assert all(f.status == "pendente" for f in faturas)
    # Numeros 1..12, ordenados via relationship
    db.session.refresh(a)
    assert [f.parcela_numero for f in a.faturas] == list(range(1, 13))


def test_criar_assinatura_idempotente(app):
    """Chamar 2x na mesma lanchonete nao cria 2 assinaturas ativas."""
    lanch = _criar_lanchonete_extra("Lanch Idemp", "idemp@test.com")
    a1 = criar_assinatura_inicial(lanch)
    a2 = criar_assinatura_inicial(lanch)
    assert a1.id == a2.id
    assert Assinatura.query.filter_by(lanchonete_id=lanch.id).count() == 1
    assert Fatura.query.filter_by(assinatura_id=a1.id).count() == 12


def test_vigencia_inicio_e_fim_corretos(app):
    """Cadastro em 06/05/2026 + 12 parcelas -> fim 30/04/2027."""
    lanch = _criar_lanchonete_extra("Lanch Vig", "vig@test.com")
    a = criar_assinatura_inicial(lanch, inicio=date(2026, 5, 6))
    assert a.vigencia_inicio == date(2026, 5, 6)
    assert a.vigencia_fim == date(2027, 4, 30)


def test_vencimento_replica_dia_do_cadastro(app):
    """Cadastro dia 6 -> todas faturas vencem dia 6 do mes."""
    lanch = _criar_lanchonete_extra("Lanch V6", "v6@test.com")
    a = criar_assinatura_inicial(lanch, inicio=date(2026, 5, 6))
    assert all(f.vencimento.day == 6 for f in a.faturas)


def test_vencimento_dia_31_ajusta_para_28(app):
    """Cadastro dia 31 -> dia_vencimento cai pra 28 (evita drift fevereiro)."""
    lanch = _criar_lanchonete_extra("Lanch V31", "v31@test.com")
    a = criar_assinatura_inicial(lanch, inicio=date(2026, 1, 31))
    # Todas as faturas devem ter dia 28 (cap do DIA_VENCIMENTO_MAX)
    assert all(f.vencimento.day == 28 for f in a.faturas)


def test_mes_referencia_progride_corretamente(app):
    """Parcela N+1 cobre o mes seguinte de parcela N."""
    lanch = _criar_lanchonete_extra("Lanch MR", "mr@test.com")
    a = criar_assinatura_inicial(lanch, inicio=date(2026, 5, 6))
    f1 = next(f for f in a.faturas if f.parcela_numero == 1)
    f2 = next(f for f in a.faturas if f.parcela_numero == 2)
    f12 = next(f for f in a.faturas if f.parcela_numero == 12)
    assert f1.mes_referencia == date(2026, 5, 1)
    assert f2.mes_referencia == date(2026, 6, 1)
    assert f12.mes_referencia == date(2027, 4, 1)


def test_signup_cria_assinatura_automaticamente(app, client):
    """POST /registro -> nova lanchonete recebe assinatura + 12 faturas."""
    initial_assinaturas = Assinatura.query.count()
    r = client.post("/registro", data={
        "email": "novo@assina.com", "senha": "testpass8",
        "nome_responsavel": "Novo", "telefone": "(43) 99999-7777",
        "nome_fantasia": "Lanch Auto", "cnpj": "",
        "endereco": "", "bairro": "", "aceite_termos": "on",
    }, follow_redirects=False)
    assert r.status_code == 302

    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch Auto").first()
    assert lanch is not None
    assinaturas = Assinatura.query.filter_by(lanchonete_id=lanch.id).all()
    assert len(assinaturas) == 1
    assert assinaturas[0].status == "ativa"
    assert assinaturas[0].valor_mensal == Decimal("500.00")
    assert Fatura.query.filter_by(assinatura_id=assinaturas[0].id).count() == 12
    assert Assinatura.query.count() == initial_assinaturas + 1

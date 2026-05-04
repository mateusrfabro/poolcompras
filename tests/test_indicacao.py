"""Programa de indicacao: cadastro com ?ind, anti-fraude, dashboard, recompensa."""
import re
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.models import Lanchonete, Indicacao, Usuario
from app.services.indicacao import (
    garantir_codigo, registrar_indicacao, buscar_indicador_por_codigo,
    indicacoes_da_lanchonete, calcular_status_recompensa,
    RECOMPENSA_INDICADAS_NECESSARIAS, RECOMPENSA_DIAS_ATIVA_MINIMO,
)


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


# ---------- service: garantir_codigo ----------

def test_garantir_codigo_gera_lazy_quando_null(app):
    """Lanchonete legacy sem codigo recebe um no primeiro acesso."""
    lanch = Lanchonete.query.first()
    lanch.codigo_indicacao = None
    db.session.commit()

    cod = garantir_codigo(lanch)
    assert cod is not None
    assert len(cod) == 8
    # Idempotente: chamada subsequente devolve o mesmo
    assert garantir_codigo(lanch) == cod


def test_buscar_indicador_codigo_invalido_retorna_none(app):
    """Codigo malformado nao quebra — retorna None silencioso."""
    assert buscar_indicador_por_codigo("") is None
    assert buscar_indicador_por_codigo("XXX") is None  # curto
    assert buscar_indicador_por_codigo("0001IIIL") is None  # chars proibidos
    assert buscar_indicador_por_codigo("ABCDEFGZ") is None  # nao existe no DB


# ---------- service: registrar_indicacao (anti-fraude) ----------

def test_registrar_indicacao_codigo_invalido_silencioso(app):
    """Cadastro com codigo invalido nao gera Indicacao nem erro."""
    indicada = Lanchonete.query.first()
    ok = registrar_indicacao("XYZ99999", indicada)
    assert ok is False
    assert Indicacao.query.count() == 0


def test_registrar_indicacao_auto_indicacao_bloqueada(app):
    """Lanchonete nao pode indicar a si mesma (mesmo se passar o proprio codigo)."""
    lanch = Lanchonete.query.first()
    cod = garantir_codigo(lanch)
    ok = registrar_indicacao(cod, lanch)
    assert ok is False
    assert Indicacao.query.count() == 0


def test_registrar_indicacao_sucesso(app):
    """Caso happy: codigo valido + indicada diferente -> cria Indicacao."""
    lanchs = Lanchonete.query.limit(2).all()
    indicador, indicada = lanchs[0], lanchs[1]
    cod = garantir_codigo(indicador)

    ok = registrar_indicacao(cod, indicada)
    assert ok is True
    ind = Indicacao.query.filter_by(indicada_lanchonete_id=indicada.id).first()
    assert ind is not None
    assert ind.indicador_lanchonete_id == indicador.id
    assert ind.codigo_usado == cod


def _criar_lanchonete_extra(nome, email):
    """Helper: cria Usuario+Lanchonete adicionais (seed so tem 2)."""
    from app.services.passwords import hash_senha
    u = Usuario(email=email, senha_hash=hash_senha("testpass"),
                nome_responsavel=nome, telefone="(43) 99999-0000",
                tipo="lanchonete")
    db.session.add(u)
    db.session.flush()
    lanch = Lanchonete(usuario_id=u.id, nome_fantasia=nome)
    db.session.add(lanch)
    db.session.commit()
    return lanch


def test_registrar_indicacao_indicada_ja_tem_indicador(app):
    """UNIQUE(indicada_lanchonete_id) — nao reclassifica dono."""
    lanchs = Lanchonete.query.limit(2).all()
    a, b = lanchs[0], lanchs[1]
    c = _criar_lanchonete_extra("Lanch C", "lanchc@test.com")
    cod_a = garantir_codigo(a)
    cod_c = garantir_codigo(c)

    assert registrar_indicacao(cod_a, b) is True
    # Tenta indicar 'b' de novo via 'c' — deve falhar
    assert registrar_indicacao(cod_c, b) is False
    assert Indicacao.query.filter_by(indicada_lanchonete_id=b.id).count() == 1


# ---------- HTTP: registro com ?ind ----------

def test_registro_com_ind_query_param(app, client):
    """GET /registro?ind=ABC popula hidden field."""
    lanch = Lanchonete.query.first()
    cod = garantir_codigo(lanch)
    r = client.get(f"/registro?ind={cod}")
    assert r.status_code == 200
    assert cod.encode() in r.data
    assert b'name="ind"' in r.data


def test_registro_post_com_ind_valido_cria_indicacao(app, client):
    """POST com hidden ind valido + cadastro novo -> Indicacao registrada."""
    indicador = Lanchonete.query.first()
    cod = garantir_codigo(indicador)
    initial_count = Indicacao.query.count()

    r = client.post("/registro", data={
        "email": "novo@indicado.com", "senha": "novasenha123",
        "nome_responsavel": "Novo Indicado", "telefone": "(43) 99999-1234",
        "nome_fantasia": "Lanchonete Indicada", "cnpj": "",
        "endereco": "", "bairro": "",
        "aceite_termos": "on", "ind": cod,
    }, follow_redirects=False)
    assert r.status_code == 302

    nova_lanch = Lanchonete.query.filter_by(nome_fantasia="Lanchonete Indicada").first()
    assert nova_lanch is not None
    indicacao = Indicacao.query.filter_by(indicada_lanchonete_id=nova_lanch.id).first()
    assert indicacao is not None
    assert indicacao.indicador_lanchonete_id == indicador.id
    assert Indicacao.query.count() == initial_count + 1


def test_registro_sem_ind_nao_cria_indicacao(app, client):
    """Cadastro normal (sem ?ind) nao registra indicacao."""
    initial = Indicacao.query.count()
    r = client.post("/registro", data={
        "email": "semind@x.com", "senha": "novasenha123",
        "nome_responsavel": "Nada", "telefone": "(43) 99999-1111",
        "nome_fantasia": "Sem Ind", "cnpj": "",
        "endereco": "", "bairro": "", "aceite_termos": "on",
    }, follow_redirects=False)
    assert r.status_code == 302
    assert Indicacao.query.count() == initial


def test_registro_com_ind_invalido_nao_quebra(app, client):
    """ind=XYZ invalido nao bloqueia cadastro (silent fail)."""
    initial = Indicacao.query.count()
    r = client.post("/registro", data={
        "email": "indinval@x.com", "senha": "novasenha123",
        "nome_responsavel": "Y", "telefone": "(43) 99999-2222",
        "nome_fantasia": "Ind Invalido Lanch", "cnpj": "",
        "endereco": "", "bairro": "", "aceite_termos": "on",
        "ind": "INEXISTE",
    }, follow_redirects=False)
    assert r.status_code == 302  # cadastrou mesmo assim
    assert Indicacao.query.count() == initial  # mas nao gerou indicacao


# ---------- service: status recompensa ----------

def _indicar(indicador, indicada, dias_atras=0):
    """Helper: cria indicacao com criado_em manipulado pra simular tempo."""
    cod = garantir_codigo(indicador)
    ind = Indicacao(
        indicador_lanchonete_id=indicador.id,
        indicada_lanchonete_id=indicada.id,
        codigo_usado=cod,
        criado_em=datetime.now(timezone.utc) - timedelta(days=dias_atras),
    )
    db.session.add(ind)
    db.session.commit()
    return ind


def test_status_recompensa_zero_indicacoes(app):
    """Lanchonete sem indicacoes — pode_resgatar=False."""
    lanch = Lanchonete.query.first()
    s = calcular_status_recompensa(lanch.id)
    assert s["elegiveis"] == 0
    assert s["aguardando_30d"] == 0
    assert s["pode_resgatar"] is False


def test_status_recompensa_3_elegiveis_libera_resgate(app):
    """3 indicadas ativas ha 31 dias = pode_resgatar=True."""
    indicador = Lanchonete.query.first()
    indicada1 = Lanchonete.query.offset(1).first()
    indicada2 = _criar_lanchonete_extra("Lanch X", "lanchx@test.com")
    indicada3 = _criar_lanchonete_extra("Lanch Y", "lanchy@test.com")
    for ind in (indicada1, indicada2, indicada3):
        _indicar(indicador, ind, dias_atras=31)

    s = calcular_status_recompensa(indicador.id)
    assert s["elegiveis"] == 3
    assert s["pode_resgatar"] is True


def test_status_recompensa_indicada_inativa_nao_conta(app):
    """Indicada com ativa=False nao conta como elegivel."""
    lanchs = Lanchonete.query.limit(2).all()
    indicador, indicada = lanchs[0], lanchs[1]
    _indicar(indicador, indicada, dias_atras=31)
    indicada.ativa = False
    db.session.commit()

    s = calcular_status_recompensa(indicador.id)
    assert s["elegiveis"] == 0


def test_status_recompensa_carencia_30d(app):
    """Indicacao recente (< 30d) cai em aguardando_30d, nao em elegiveis."""
    lanchs = Lanchonete.query.limit(2).all()
    _indicar(lanchs[0], lanchs[1], dias_atras=15)

    s = calcular_status_recompensa(lanchs[0].id)
    assert s["elegiveis"] == 0
    assert s["aguardando_30d"] == 1


# ---------- HTTP: dashboard /perfil/indicacoes ----------

def test_dashboard_indicacoes_GET(app, client):
    """Dashboard renderiza com codigo + link copiavel + tabela."""
    # Login como Lanch A (smash@demo.com / demo123)
    csrf = _csrf(client, "/login")
    client.post("/login", data={
        "csrf_token": csrf, "email": "lancha@test.com", "senha": "testpass",
    })
    r = client.get("/perfil/indicacoes")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Indique outras hamburguerias" in body
    assert "/registro?ind=" in body  # link de indicacao montado
    assert "Resgatar" not in body or "Faltam" in body  # ainda sem 3 elegiveis


def test_notif_quase_la_dispara_em_n_menos_1(app, monkeypatch):
    """Apos a 2a indicacao (N-1=2), service tenta notificar via Telegram."""
    chamadas = []

    def fake_notificar(usuario, titulo, detalhes=""):
        chamadas.append((usuario.id if usuario else None, titulo))
        return True

    # Patch lazy import dentro de _notificar_quase_la_se_aplicavel
    import app.services.notificacoes as notif_mod
    monkeypatch.setattr(notif_mod, "notificar_evento", fake_notificar)

    indicador = Lanchonete.query.first()
    indicada1 = Lanchonete.query.offset(1).first()
    indicada2 = _criar_lanchonete_extra("Lanch QL", "lanchql@test.com")
    cod = garantir_codigo(indicador)

    # 1a indicacao — nao dispara notif
    registrar_indicacao(cod, indicada1)
    assert chamadas == []
    # 2a indicacao — N-1 = 2, deve disparar
    registrar_indicacao(cod, indicada2)
    assert len(chamadas) == 1
    assert "Falta 1 indicação" in chamadas[0][1]


def test_resgatar_recompensa_sem_elegiveis_negado(app, client):
    """POST /resgatar sem 3 elegiveis -> flash warning, sem mutacao."""
    csrf = _csrf(client, "/login")
    client.post("/login", data={
        "csrf_token": csrf, "email": "lancha@test.com", "senha": "testpass",
    })
    csrf2 = _csrf(client, "/perfil/indicacoes")
    r = client.post("/perfil/indicacoes/resgatar",
                    data={"csrf_token": csrf2}, follow_redirects=False)
    assert r.status_code == 302
    # Nenhuma indicacao foi marcada como recompensa_aplicada_em
    assert Indicacao.query.filter(Indicacao.recompensa_aplicada_em.isnot(None)).count() == 0

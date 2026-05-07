"""CRM: Kanban, criar/ver/mover/converter lead, IDOR, pipeline KPIs."""
import re

from app import db
from app.models import (
    Lead, LeadEvento, Vendedor, Lanchonete, Usuario, Assinatura,
)


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


# ---------- Acesso e renderizacao ----------

def test_kanban_admin_renderiza(client_admin):
    r = client_admin.get("/crm/")
    assert r.status_code == 200
    assert b"Pipeline comercial" in r.data
    # 5 colunas com labels
    for label in (b"Frio", b"Morno", b"Quente", b"Fechado", b"Cancelado"):
        assert label in r.data


def test_kanban_vendedor_renderiza(client_vendedor):
    r = client_vendedor.get("/crm/")
    assert r.status_code == 200
    assert b"Pipeline" in r.data


def test_kanban_fornecedor_negado(client_forn):
    r = client_forn.get("/crm/")
    # Decorator redireciona pra dashboard com flash
    assert r.status_code in (302, 403)


def test_kanban_lanchonete_negado(client_lanchA):
    r = client_lanchA.get("/crm/")
    assert r.status_code in (302, 403)


# ---------- Criar lead ----------

def test_admin_cria_lead_escolhendo_vendedor(client_admin, app):
    v = Vendedor.query.first()
    r = client_admin.post("/crm/leads/novo", data={
        "csrf_token": _csrf(client_admin, "/crm/leads/novo"),
        "nome_estabelecimento": "Hambúrgueria do Teste",
        "nome_contato": "João",
        "telefone": "(43) 99999-1111",
        "email": "joao@teste.com",
        "cidade": "Londrina",
        "vendedor_id": str(v.id),
    }, follow_redirects=False)
    assert r.status_code == 302

    lead = Lead.query.filter_by(nome_estabelecimento="Hambúrgueria do Teste").first()
    assert lead is not None
    assert lead.status == "frio"
    assert lead.vendedor_id == v.id
    # Evento de criacao registrado
    assert any(e.tipo == "nota" for e in lead.eventos)


def test_vendedor_cria_lead_atribui_pra_si_mesmo(client_vendedor, app):
    """Vendedor logado: vendedor_id forcado pro proprio (anti-IDOR no form)."""
    r = client_vendedor.post("/crm/leads/novo", data={
        "csrf_token": _csrf(client_vendedor, "/crm/leads/novo"),
        "nome_estabelecimento": "Lanche do Vendedor",
        "telefone": "(43) 99999-2222",
        "vendedor_id": "9999",  # tenta atribuir pra outro — ignorado
    }, follow_redirects=False)
    assert r.status_code == 302

    lead = Lead.query.filter_by(nome_estabelecimento="Lanche do Vendedor").first()
    assert lead is not None
    vendedor_proprio = Vendedor.query.filter_by(
        usuario_id=Usuario.query.filter_by(email="vendedor@test.com").first().id
    ).first()
    assert lead.vendedor_id == vendedor_proprio.id


def test_lead_sem_nome_bloqueado(client_admin):
    v = Vendedor.query.first()
    r = client_admin.post("/crm/leads/novo", data={
        "csrf_token": _csrf(client_admin, "/crm/leads/novo"),
        "nome_estabelecimento": "",
        "vendedor_id": str(v.id),
    }, follow_redirects=False)
    assert r.status_code == 200  # form re-renderizado


# ---------- IDOR: vendedor nao ve / nao mexe lead alheio ----------

def _criar_lead(vendedor_id, nome="Lead X"):
    lead = Lead(
        nome_estabelecimento=nome,
        telefone="(43) 99999-1234",
        email="lead@x.com",
        vendedor_id=vendedor_id,
        status=Lead.STATUS_FRIO,
    )
    db.session.add(lead)
    db.session.commit()
    return lead


def test_vendedor_nao_ve_lead_de_outro_vendedor(client_vendedor, client_admin, app):
    """Crio um vendedor B + lead dele. Vendedor logado (A) tenta abrir — 403."""
    # Cria vendedor B (separado do seed)
    from app.services.passwords import hash_senha
    u_b = Usuario(email="vendedor.b@test.com", senha_hash=hash_senha("testpass"),
                  nome_responsavel="Vend B", telefone="x", tipo="vendedor")
    db.session.add(u_b)
    db.session.flush()
    vb = Vendedor(usuario_id=u_b.id, nome="Vend B")
    db.session.add(vb)
    db.session.commit()

    lead_b = _criar_lead(vb.id, "Lead Privado B")
    # client_vendedor eh o vendedor do seed (vendedor@test.com)
    r = client_vendedor.get(f"/crm/leads/{lead_b.id}")
    assert r.status_code == 403


def test_vendedor_nao_muda_status_de_lead_alheio(client_vendedor, app):
    from app.services.passwords import hash_senha
    u_b = Usuario(email="outro.v@test.com", senha_hash=hash_senha("x"),
                  nome_responsavel="Outro V", telefone="x", tipo="vendedor")
    db.session.add(u_b)
    db.session.flush()
    vb = Vendedor(usuario_id=u_b.id, nome="Outro V")
    db.session.add(vb)
    db.session.commit()
    lead = _criar_lead(vb.id)

    r = client_vendedor.post(f"/crm/leads/{lead.id}/status", data={
        "csrf_token": _csrf(client_vendedor, "/crm/"),
        "status": "morno",
    }, follow_redirects=False)
    assert r.status_code == 403
    db.session.refresh(lead)
    assert lead.status == "frio"  # nao mudou


def test_admin_ve_qualquer_lead(client_admin, app):
    v = Vendedor.query.first()
    lead = _criar_lead(v.id, "Visivel ao admin")
    r = client_admin.get(f"/crm/leads/{lead.id}")
    assert r.status_code == 200
    assert b"Visivel ao admin" in r.data or "Visivel ao admin".encode() in r.data


# ---------- Mover de coluna ----------

def test_mudar_status_loga_evento(client_admin, app):
    v = Vendedor.query.first()
    lead = _criar_lead(v.id)
    r = client_admin.post(f"/crm/leads/{lead.id}/status", data={
        "csrf_token": _csrf(client_admin, "/crm/"),
        "status": "morno",
        "motivo": "Cliente respondeu mensagem",
    }, follow_redirects=False)
    assert r.status_code == 302
    db.session.refresh(lead)
    assert lead.status == "morno"
    eventos = LeadEvento.query.filter_by(lead_id=lead.id,
                                         tipo="mudanca_status").all()
    assert len(eventos) == 1
    assert "frio" in eventos[0].descricao
    assert "morno" in eventos[0].descricao
    assert "respondeu" in eventos[0].descricao


def test_mudar_status_idempotente(client_admin, app):
    """Mudar pro mesmo status: no-op silencioso, sem evento ruidoso."""
    v = Vendedor.query.first()
    lead = _criar_lead(v.id)
    eventos_antes = LeadEvento.query.filter_by(lead_id=lead.id).count()
    r = client_admin.post(f"/crm/leads/{lead.id}/status", data={
        "csrf_token": _csrf(client_admin, "/crm/"),
        "status": "frio",
    }, follow_redirects=False)
    assert r.status_code == 302
    eventos_depois = LeadEvento.query.filter_by(lead_id=lead.id).count()
    assert eventos_antes == eventos_depois


def test_status_invalido_rejeitado(client_admin, app):
    v = Vendedor.query.first()
    lead = _criar_lead(v.id)
    r = client_admin.post(f"/crm/leads/{lead.id}/status", data={
        "csrf_token": _csrf(client_admin, "/crm/"),
        "status": "invalido",
    }, follow_redirects=False)
    assert r.status_code == 302  # redirect com flash
    db.session.refresh(lead)
    assert lead.status == "frio"


# ---------- Adicionar nota ----------

def test_adicionar_nota(client_admin, app):
    v = Vendedor.query.first()
    lead = _criar_lead(v.id)
    r = client_admin.post(f"/crm/leads/{lead.id}/evento", data={
        "csrf_token": _csrf(client_admin, "/crm/"),
        "descricao": "Visitou hoje. Pediu pra voltar segunda.",
    }, follow_redirects=False)
    assert r.status_code == 302
    eventos = LeadEvento.query.filter_by(lead_id=lead.id, tipo="nota").all()
    assert any("Visitou" in e.descricao for e in eventos)


# ---------- Converter em cliente ----------

def test_converter_em_cliente_cria_lanchonete_e_assinatura(client_admin, app):
    v = Vendedor.query.first()
    lead = Lead(
        nome_estabelecimento="Converter Test",
        nome_contato="Dono",
        telefone="(43) 99999-3333",
        email="converter@test.com",
        cidade="Londrina",
        cnpj="11.222.333/0001-44",
        vendedor_id=v.id,
        status=Lead.STATUS_QUENTE,
    )
    db.session.add(lead)
    db.session.commit()

    r = client_admin.post(f"/crm/leads/{lead.id}/converter", data={
        "csrf_token": _csrf(client_admin, f"/crm/leads/{lead.id}"),
    }, follow_redirects=False)
    assert r.status_code == 302

    # Lanchonete criada
    db.session.refresh(lead)
    assert lead.lanchonete_id is not None
    assert lead.status == "fechado"
    lanch = db.session.get(Lanchonete, lead.lanchonete_id)
    assert lanch.nome_fantasia == "Converter Test"
    assert lanch.vendedor_id == v.id
    # Assinatura gerada (12 parcelas)
    a = Assinatura.query.filter_by(lanchonete_id=lanch.id).first()
    assert a is not None
    assert len(a.faturas) == 12
    # Evento de conversao registrado
    eventos = LeadEvento.query.filter_by(lead_id=lead.id,
                                          tipo="conversao").all()
    assert len(eventos) == 1


def test_converter_sem_email_bloqueia(client_admin, app):
    v = Vendedor.query.first()
    lead = Lead(
        nome_estabelecimento="Sem Email",
        telefone="(43) 99999-4444",
        email=None,
        vendedor_id=v.id,
        status=Lead.STATUS_QUENTE,
    )
    db.session.add(lead)
    db.session.commit()
    r = client_admin.post(f"/crm/leads/{lead.id}/converter", data={
        "csrf_token": _csrf(client_admin, f"/crm/leads/{lead.id}"),
    }, follow_redirects=False)
    assert r.status_code == 302
    db.session.refresh(lead)
    assert lead.lanchonete_id is None  # nao converteu


def test_converter_email_duplicado_bloqueia(client_admin, app):
    v = Vendedor.query.first()
    lead = Lead(
        nome_estabelecimento="Email Dup",
        telefone="(43) 99999-5555",
        email="lancha@test.com",  # ja existe no seed
        vendedor_id=v.id,
    )
    db.session.add(lead)
    db.session.commit()
    r = client_admin.post(f"/crm/leads/{lead.id}/converter", data={
        "csrf_token": _csrf(client_admin, f"/crm/leads/{lead.id}"),
    }, follow_redirects=False)
    assert r.status_code == 302
    db.session.refresh(lead)
    assert lead.lanchonete_id is None


def test_converter_lead_ja_convertido_no_op(client_admin, app):
    v = Vendedor.query.first()
    lanch = Lanchonete.query.first()
    lead = Lead(
        nome_estabelecimento="Ja Convertido",
        telefone="(43) 99999-6666",
        email="zzz@x.com",
        vendedor_id=v.id,
        lanchonete_id=lanch.id,  # ja amarrado
        status=Lead.STATUS_FECHADO,
    )
    db.session.add(lead)
    db.session.commit()
    r = client_admin.post(f"/crm/leads/{lead.id}/converter", data={
        "csrf_token": _csrf(client_admin, f"/crm/leads/{lead.id}"),
    }, follow_redirects=False)
    assert r.status_code == 302
    db.session.refresh(lead)
    assert lead.lanchonete_id == lanch.id  # nao trocou


# ---------- Pipeline KPIs ----------

def test_kpi_meta_realizado(client_admin, app):
    """Apos 1 lead fechado este mes, fechados=1."""
    v = Vendedor.query.first()
    lead = Lead(
        nome_estabelecimento="Fechado pra KPI",
        vendedor_id=v.id,
        status=Lead.STATUS_FECHADO,
        telefone="(43) 99999-7777",
        email="kpi@test.com",
    )
    db.session.add(lead)
    db.session.commit()
    r = client_admin.get("/crm/")
    body = r.data.decode("utf-8", errors="ignore")
    assert "1 / 10" in body or "1/10" in body


def test_kanban_filtro_por_vendedor_admin(client_admin, app):
    """Admin com ?vendedor_id= ve so leads desse vendedor."""
    from app.services.passwords import hash_senha
    u_b = Usuario(email="filtro.b@test.com", senha_hash=hash_senha("x"),
                  nome_responsavel="VB", telefone="x", tipo="vendedor")
    db.session.add(u_b)
    db.session.flush()
    vb = Vendedor(usuario_id=u_b.id, nome="VB Filtro")
    db.session.add(vb)
    db.session.commit()

    va = Vendedor.query.filter_by(nome="Vendedor Teste").first()
    db.session.add(Lead(nome_estabelecimento="LeadA",
                        telefone="x", vendedor_id=va.id))
    db.session.add(Lead(nome_estabelecimento="LeadB",
                        telefone="x", vendedor_id=vb.id))
    db.session.commit()

    r = client_admin.get(f"/crm/?vendedor_id={va.id}")
    body = r.data.decode("utf-8", errors="ignore")
    assert "LeadA" in body
    assert "LeadB" not in body

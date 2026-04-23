"""Testes de transicoes invalidas de status da rodada no painel admin.

Cobre gaps do tester:
- /admin/rodadas/<id>/finalizar  exige status='em_negociacao'
- /admin/rodadas/<id>/cancelar   idempotente se ja cancelada
- /admin/rodadas/<id>/liberar    exige aguardando_cotacao/aguardando_aprovacao
                                   e que nao haja produto pendente de aprovacao
"""
import re

from app import db
from app.models import Rodada, RodadaProduto, Fornecedor, Produto


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


# ---------- Finalizar ----------

def test_finalizar_rodada_preparando_rejeitado(app, client_admin):
    """Rodada em 'preparando' nao pode ser finalizada (precisa em_negociacao)."""
    rodada = Rodada.query.first()
    rodada.status = "preparando"
    db.session.commit()
    r_id = rodada.id

    token = _csrf(client_admin, f"/rodadas/{r_id}")
    r = client_admin.post(
        f"/admin/rodadas/{r_id}/finalizar",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert db.session.get(Rodada, r_id).status == "preparando"


def test_finalizar_rodada_aberta_rejeitado(app, client_admin):
    """Rodada em 'aberta' nao pode ser finalizada diretamente."""
    rodada = Rodada.query.first()
    rodada.status = "aberta"
    db.session.commit()
    r_id = rodada.id

    token = _csrf(client_admin, f"/rodadas/{r_id}")
    client_admin.post(
        f"/admin/rodadas/{r_id}/finalizar",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert db.session.get(Rodada, r_id).status == "aberta"


def test_finalizar_rodada_em_negociacao_ok(app, client_admin):
    """Caminho feliz: em_negociacao -> finalizada."""
    rodada = Rodada.query.first()
    rodada.status = "em_negociacao"
    db.session.commit()
    r_id = rodada.id

    token = _csrf(client_admin, f"/rodadas/{r_id}")
    r = client_admin.post(
        f"/admin/rodadas/{r_id}/finalizar",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert db.session.get(Rodada, r_id).status == "finalizada"


# ---------- Cancelar ----------

def test_cancelar_rodada_ja_cancelada_flash_warning(app, client_admin):
    """Cancelar rodada ja cancelada eh idempotente (nao quebra)."""
    rodada = Rodada.query.first()
    rodada.status = "cancelada"
    db.session.commit()
    r_id = rodada.id

    token = _csrf(client_admin, f"/rodadas/{r_id}")
    r = client_admin.post(
        f"/admin/rodadas/{r_id}/cancelar",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 302
    # Status continua 'cancelada' (idempotente)
    assert db.session.get(Rodada, r_id).status == "cancelada"


def test_cancelar_rodada_qualquer_status_funciona(app, client_admin):
    """Admin pode cancelar rodada em qualquer status (exceto ja cancelada)."""
    rodada = Rodada.query.first()
    rodada.status = "em_negociacao"
    db.session.commit()
    r_id = rodada.id

    token = _csrf(client_admin, f"/rodadas/{r_id}")
    client_admin.post(
        f"/admin/rodadas/{r_id}/cancelar",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert db.session.get(Rodada, r_id).status == "cancelada"


# ---------- Liberar ----------

def test_liberar_rodada_status_errado_rejeitado(app, client_admin):
    """Rodada em 'aberta' nao pode ser 'liberada' (ja esta aberta)."""
    rodada = Rodada.query.first()
    rodada.status = "aberta"
    db.session.commit()
    r_id = rodada.id

    token = _csrf(client_admin, f"/rodadas/{r_id}")
    r = client_admin.post(
        f"/admin/rodadas/{r_id}/liberar",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 302
    # Status inalterado
    assert db.session.get(Rodada, r_id).status == "aberta"


def test_liberar_bloqueada_por_produtos_pendentes(app, client_admin):
    """Com produto pendente aprovacao (aprovado=None + adicionado_por_fornecedor_id),
    liberar nao libera e redireciona pra aprovar-produtos."""
    rodada = Rodada.query.first()
    rodada.status = "aguardando_cotacao"
    forn = Fornecedor.query.first()

    # Produto sugerido pendente de aprovacao
    p = Produto(nome="Pao Pretzel", categoria="Pao", subcategoria="Artesanal",
                unidade="un", ativo=False)
    db.session.add(p); db.session.flush()
    db.session.add(RodadaProduto(
        rodada_id=rodada.id, produto_id=p.id,
        adicionado_por_fornecedor_id=forn.id, aprovado=None,
    ))
    db.session.commit()
    r_id = rodada.id

    token = _csrf(client_admin, f"/rodadas/{r_id}")
    r = client_admin.post(
        f"/admin/rodadas/{r_id}/liberar",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    # Redireciona pra aprovar-produtos, status NAO muda pra aberta
    assert r.status_code == 302
    assert db.session.get(Rodada, r_id).status == "aguardando_cotacao"


def test_liberar_sem_pendencias_muda_pra_aberta(app, client_admin):
    """aguardando_cotacao sem pendencias -> aberta."""
    rodada = Rodada.query.first()
    rodada.status = "aguardando_cotacao"
    db.session.commit()
    r_id = rodada.id

    token = _csrf(client_admin, f"/rodadas/{r_id}")
    r = client_admin.post(
        f"/admin/rodadas/{r_id}/liberar",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert db.session.get(Rodada, r_id).status == "aberta"


# ---------- Authz ----------

def test_lanchonete_nao_cancela_rodada(app, client_lanchA):
    rodada = Rodada.query.first()
    rodada.status = "aberta"
    db.session.commit()
    r_id = rodada.id

    r = client_lanchA.post(
        f"/admin/rodadas/{r_id}/cancelar",
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert db.session.get(Rodada, r_id).status == "aberta"


def test_fornecedor_nao_finaliza_rodada(app, client_forn):
    rodada = Rodada.query.first()
    rodada.status = "em_negociacao"
    db.session.commit()
    r_id = rodada.id

    r = client_forn.post(
        f"/admin/rodadas/{r_id}/finalizar",
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert db.session.get(Rodada, r_id).status == "em_negociacao"

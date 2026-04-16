"""Testes das transicoes de estado do fluxo da rodada."""
import io


def _preparar_rodada_finalizada(app):
    """Cria uma rodada finalizada com ItemPedido pra lanchA para permitir fluxo."""
    from app import db
    from app.models import Rodada, ItemPedido, Usuario, Produto

    with app.app_context():
        rodada = Rodada.query.first()
        rodada.status = "finalizada"
        lanchA = Usuario.query.filter_by(email="lancha@test.com").first().lanchonete
        produto = Produto.query.first()
        # Cria pedido pra lanchonete participar
        if not ItemPedido.query.filter_by(rodada_id=rodada.id, lanchonete_id=lanchA.id).first():
            db.session.add(ItemPedido(
                rodada_id=rodada.id, lanchonete_id=lanchA.id,
                produto_id=produto.id, quantidade=10,
            ))
        db.session.commit()
        return rodada.id


def test_aceitar_proposta(app, client_lanchA):
    rid = _preparar_rodada_finalizada(app)
    r = client_lanchA.post(f"/fluxo/rodada/{rid}/aceitar", follow_redirects=False)
    assert r.status_code == 302

    from app.models import ParticipacaoRodada, EventoRodada, Usuario
    with app.app_context():
        lanchA = Usuario.query.filter_by(email="lancha@test.com").first().lanchonete
        p = ParticipacaoRodada.query.filter_by(
            rodada_id=rid, lanchonete_id=lanchA.id).first()
        assert p is not None
        assert p.aceite_proposta is True
        assert p.aceite_em is not None
        # Evento registrado
        ev = EventoRodada.query.filter_by(
            rodada_id=rid, lanchonete_id=lanchA.id,
            tipo=EventoRodada.TIPO_PROPOSTA_ACEITA).first()
        assert ev is not None


def test_recusar_proposta(app, client_lanchA):
    rid = _preparar_rodada_finalizada(app)
    r = client_lanchA.post(f"/fluxo/rodada/{rid}/recusar", follow_redirects=False)
    assert r.status_code == 302

    from app.models import ParticipacaoRodada, Usuario
    with app.app_context():
        lanchA = Usuario.query.filter_by(email="lancha@test.com").first().lanchonete
        p = ParticipacaoRodada.query.filter_by(
            rodada_id=rid, lanchonete_id=lanchA.id).first()
        assert p.aceite_proposta is False


def test_upload_sem_aceite_bloqueado(app, client_lanchA):
    """Nao deve deixar subir comprovante sem ter aceitado a proposta."""
    rid = _preparar_rodada_finalizada(app)
    pdf = io.BytesIO(b"%PDF-1.4\nfake")
    r = client_lanchA.post(
        f"/fluxo/rodada/{rid}/comprovante",
        data={"comprovante": (pdf, "c.pdf")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    # Redireciona com flash error
    assert r.status_code == 302
    from app.models import ParticipacaoRodada, Usuario
    with app.app_context():
        lanchA = Usuario.query.filter_by(email="lancha@test.com").first().lanchonete
        p = ParticipacaoRodada.query.filter_by(
            rodada_id=rid, lanchonete_id=lanchA.id).first()
        # Participacao pode nem existir, mas se existir nao deve ter comprovante
        if p:
            assert p.comprovante_key is None


def test_upload_com_aceite_aceita_pdf(app, client_lanchA):
    rid = _preparar_rodada_finalizada(app)
    client_lanchA.post(f"/fluxo/rodada/{rid}/aceitar")
    # Agora upload
    pdf = io.BytesIO(b"%PDF-1.4\n" + b"0" * 500)
    r = client_lanchA.post(
        f"/fluxo/rodada/{rid}/comprovante",
        data={"comprovante": (pdf, "comp.pdf")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r.status_code == 302

    from app.models import ParticipacaoRodada, Usuario
    with app.app_context():
        lanchA = Usuario.query.filter_by(email="lancha@test.com").first().lanchonete
        p = ParticipacaoRodada.query.filter_by(
            rodada_id=rid, lanchonete_id=lanchA.id).first()
        assert p.comprovante_key is not None
        assert p.comprovante_key.endswith(".pdf")


def test_upload_rejeita_nao_pdf_disfarcado(app, client_lanchA):
    """Arquivo com extensao .pdf mas magic bytes invalidos deve ser rejeitado."""
    rid = _preparar_rodada_finalizada(app)
    client_lanchA.post(f"/fluxo/rodada/{rid}/aceitar")
    # Magic bytes de EXE (MZ) mas nome .pdf
    fake = io.BytesIO(b"MZ\x90\x00\x03exe fake content here")
    r = client_lanchA.post(
        f"/fluxo/rodada/{rid}/comprovante",
        data={"comprovante": (fake, "comp.pdf")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r.status_code == 302

    from app.models import ParticipacaoRodada, Usuario
    with app.app_context():
        lanchA = Usuario.query.filter_by(email="lancha@test.com").first().lanchonete
        p = ParticipacaoRodada.query.filter_by(
            rodada_id=rid, lanchonete_id=lanchA.id).first()
        # Comprovante NAO deve ter sido salvo
        assert p.comprovante_key is None


def test_confirmar_pagamento_requer_cotacao_do_fornecedor(app, client_forn):
    """Fornecedor que NAO cotou na rodada recebe 403."""
    rid = _preparar_rodada_finalizada(app)
    from app import db
    from app.models import Usuario
    with app.app_context():
        lanchA = Usuario.query.filter_by(email="lancha@test.com").first().lanchonete
        lid = lanchA.id

    r = client_forn.post(
        f"/fluxo/rodada/{rid}/lanchonete/{lid}/pagamento",
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_avaliar_sem_recebimento_bloqueado(app, client_lanchA):
    """Nao deixar avaliar antes de confirmar recebimento."""
    rid = _preparar_rodada_finalizada(app)
    # Aceita mas nao conclui o fluxo
    client_lanchA.post(f"/fluxo/rodada/{rid}/aceitar")

    r = client_lanchA.post(f"/fluxo/rodada/{rid}/avaliar",
                            data={"estrelas": "5"},
                            follow_redirects=False)
    assert r.status_code == 302

    from app.models import ParticipacaoRodada, Usuario
    with app.app_context():
        lanchA = Usuario.query.filter_by(email="lancha@test.com").first().lanchonete
        p = ParticipacaoRodada.query.filter_by(
            rodada_id=rid, lanchonete_id=lanchA.id).first()
        assert p.avaliacao_geral is None

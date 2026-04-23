"""Dashboard e analytics do fornecedor."""
from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import (
    Rodada, Cotacao, Produto, Lanchonete, AvaliacaoRodada,
)
from . import fornecedor_bp, fornecedor_required


@fornecedor_bp.route("/dashboard")
@login_required
@fornecedor_required
def dashboard():
    fornecedor = current_user.fornecedor

    rodadas_para_cotar = Rodada.query.filter(
        Rodada.status.in_(["aguardando_cotacao", "em_negociacao", "fechada", "cotando"])
    ).order_by(Rodada.data_fechamento.desc()).all()

    minhas_cotacoes = (
        Cotacao.query
        .filter_by(fornecedor_id=fornecedor.id)
        .order_by(Cotacao.criado_em.desc())
        .limit(20)
        .all()
    ) if fornecedor else []

    pendencias_por_rodada = []
    if fornecedor:
        from app.services.pendencias import pendencias_fornecedor
        pendencias_por_rodada = pendencias_fornecedor(fornecedor.id)

    participacoes_pendentes = [
        p for bloco in pendencias_por_rodada
        for p in (bloco["aguardando_pagamento"] + bloco["aguardando_entrega"])
    ]

    kpis = None
    if fornecedor:
        fid = fornecedor.id
        total_cot = Cotacao.query.filter_by(fornecedor_id=fid).count()
        vencedoras = Cotacao.query.filter_by(fornecedor_id=fid, selecionada=True).count()
        taxa_vitoria = round(vencedoras / total_cot * 100, 1) if total_cot else 0
        media_recebida = (
            db.session.query(func.avg(AvaliacaoRodada.estrelas))
            .filter(AvaliacaoRodada.fornecedor_id == fid)
            .scalar()
        )
        media_recebida = round(float(media_recebida), 1) if media_recebida else 0
        rodadas_a_cotar_ids = [r.id for r in rodadas_para_cotar if r.status == "aguardando_cotacao"]
        ja_cotei_nestas = set()
        if rodadas_a_cotar_ids:
            ja_cotei_nestas = {
                r for (r,) in db.session.query(Cotacao.rodada_id)
                    .filter(Cotacao.fornecedor_id == fid)
                    .filter(Cotacao.rodada_id.in_(rodadas_a_cotar_ids))
                    .distinct().all()
            }
        cotacoes_pendentes = len([r for r in rodadas_a_cotar_ids if r not in ja_cotei_nestas])

        kpis = {
            "cotacoes_pendentes": cotacoes_pendentes,
            "taxa_vitoria": taxa_vitoria,
            "media_recebida": media_recebida,
            "participacoes_pendentes": len(participacoes_pendentes),
        }

    ultimas_rodadas = []
    if fornecedor:
        rodadas_cotadas = (
            db.session.query(Rodada)
            .join(Cotacao, Cotacao.rodada_id == Rodada.id)
            .filter(Cotacao.fornecedor_id == fornecedor.id)
            .group_by(Rodada.id)
            .order_by(Rodada.data_abertura.desc())
            .limit(3)
            .all()
        )
        for r in rodadas_cotadas:
            total_cotado = (
                db.session.query(func.count(Cotacao.id))
                .filter(Cotacao.rodada_id == r.id, Cotacao.fornecedor_id == fornecedor.id)
                .scalar()
            ) or 0
            vitorias = (
                db.session.query(func.count(Cotacao.id))
                .filter(Cotacao.rodada_id == r.id,
                        Cotacao.fornecedor_id == fornecedor.id,
                        Cotacao.selecionada.is_(True))
                .scalar()
            ) or 0
            nota = (
                db.session.query(func.avg(AvaliacaoRodada.estrelas))
                .filter(AvaliacaoRodada.rodada_id == r.id,
                        AvaliacaoRodada.fornecedor_id == fornecedor.id)
                .scalar()
            )
            ultimas_rodadas.append({
                "rodada": r,
                "cotacoes": total_cotado,
                "vitorias": vitorias,
                "nota": round(float(nota), 1) if nota else None,
            })

    return render_template(
        "fornecedor/dashboard.html",
        fornecedor=fornecedor,
        rodadas_para_cotar=rodadas_para_cotar,
        minhas_cotacoes=minhas_cotacoes,
        participacoes_pendentes=participacoes_pendentes,
        pendencias_por_rodada=pendencias_por_rodada,
        kpis=kpis,
        ultimas_rodadas=ultimas_rodadas,
    )


@fornecedor_bp.route("/analytics")
@login_required
@fornecedor_required
def analytics():
    """Dashboard de KPIs do fornecedor logado."""
    fornecedor = current_user.fornecedor
    if not fornecedor:
        flash("Complete seu cadastro.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    fid = fornecedor.id

    total_cotacoes = Cotacao.query.filter_by(fornecedor_id=fid).count()
    cotacoes_vencedoras = Cotacao.query.filter_by(fornecedor_id=fid, selecionada=True).count()
    taxa_vitoria = round(cotacoes_vencedoras / total_cotacoes * 100, 1) if total_cotacoes else 0

    rodadas_participou = (
        db.session.query(func.count(func.distinct(Cotacao.rodada_id)))
        .filter(Cotacao.fornecedor_id == fid)
        .scalar()
    ) or 0

    media_recebida = (
        db.session.query(func.avg(AvaliacaoRodada.estrelas))
        .filter(AvaliacaoRodada.fornecedor_id == fid)
        .scalar()
    )
    total_avaliacoes = AvaliacaoRodada.query.filter_by(fornecedor_id=fid).count()
    media_recebida = round(float(media_recebida), 1) if media_recebida else 0

    top_produtos = (
        db.session.query(
            Produto.nome,
            func.count(Cotacao.id).label("vezes_cotado"),
            func.avg(Cotacao.preco_unitario).label("preco_medio"),
        )
        .join(Cotacao, Cotacao.produto_id == Produto.id)
        .filter(Cotacao.fornecedor_id == fid)
        .group_by(Produto.id)
        .order_by(func.count(Cotacao.id).desc())
        .limit(5)
        .all()
    )

    avaliacoes_recentes = (
        db.session.query(
            Rodada.nome,
            Lanchonete.nome_fantasia,
            AvaliacaoRodada.estrelas,
            AvaliacaoRodada.comentario,
        )
        .join(AvaliacaoRodada, AvaliacaoRodada.rodada_id == Rodada.id)
        .join(Lanchonete, AvaliacaoRodada.lanchonete_id == Lanchonete.id)
        .filter(AvaliacaoRodada.fornecedor_id == fid)
        .order_by(AvaliacaoRodada.criado_em.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "fornecedor/analytics.html",
        fornecedor=fornecedor,
        total_cotacoes=total_cotacoes,
        cotacoes_vencedoras=cotacoes_vencedoras,
        taxa_vitoria=taxa_vitoria,
        rodadas_participou=rodadas_participou,
        media_recebida=media_recebida,
        total_avaliacoes=total_avaliacoes,
        top_produtos=top_produtos,
        avaliacoes_recentes=avaliacoes_recentes,
    )

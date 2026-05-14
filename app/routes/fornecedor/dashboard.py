"""Dashboard e analytics do fornecedor."""
from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, case

from app import db
from app.models import (
    Rodada, Cotacao, Produto, Lanchonete, AvaliacaoRodada,
)
from app.services.pendencias import pendencias_fornecedor
from app.services.pnl_fornecedor import calcular_pnl
from app.services.kpis_fornecedor import (
    total_cotacoes, cotacoes_vencedoras, media_avaliacao_recebida,
    total_avaliacoes_recebidas,
)
from . import fornecedor_bp, fornecedor_required


@fornecedor_bp.route("/dashboard")
@login_required
@fornecedor_required
def dashboard():
    fornecedor = current_user.fornecedor

    rodadas_para_cotar = Rodada.query.filter(
        Rodada.status.in_([Rodada.STATUS_AGUARDANDO_COTACAO,
                           Rodada.STATUS_EM_NEGOCIACAO,
                           Rodada.STATUS_FECHADA,
                           Rodada.STATUS_COTANDO])
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
        pendencias_por_rodada = pendencias_fornecedor(fornecedor.id)

    participacoes_pendentes = [
        p for bloco in pendencias_por_rodada
        for p in (bloco["aguardando_pagamento"] + bloco["aguardando_entrega"])
    ]

    kpis = None
    if fornecedor:
        fid = fornecedor.id
        # KPIs cacheados (TTL 30s) — espelha kpis_admin.
        total_cot = total_cotacoes(fid)
        vencedoras = cotacoes_vencedoras(fid)
        taxa_vitoria = round(vencedoras / total_cot * 100, 1) if total_cot else 0
        media_recebida = media_avaliacao_recebida(fid)
        rodadas_a_cotar_ids = [r.id for r in rodadas_para_cotar if r.status == Rodada.STATUS_AGUARDANDO_COTACAO]
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
        # Pre-agrega em 2 queries (era 3) — consolidamos total + vitorias
        # num unico GROUP BY sobre Cotacao com SUM(CASE WHEN selecionada).
        # AvaliacaoRodada e tabela distinta, fica em query separada.
        rod_ids = [r.id for r in rodadas_cotadas]
        if rod_ids:
            cot_vits_rows = (
                db.session.query(
                    Cotacao.rodada_id,
                    func.count(Cotacao.id),
                    func.sum(case((Cotacao.selecionada.is_(True), 1), else_=0)),
                )
                .filter(Cotacao.rodada_id.in_(rod_ids),
                        Cotacao.fornecedor_id == fornecedor.id)
                .group_by(Cotacao.rodada_id).all()
            )
            cot_vits = {rid: (total, int(vits or 0)) for rid, total, vits in cot_vits_rows}
            notas = dict(
                db.session.query(AvaliacaoRodada.rodada_id, func.avg(AvaliacaoRodada.estrelas))
                .filter(AvaliacaoRodada.rodada_id.in_(rod_ids),
                        AvaliacaoRodada.fornecedor_id == fornecedor.id)
                .group_by(AvaliacaoRodada.rodada_id).all()
            )
        else:
            cot_vits, notas = {}, {}

        for r in rodadas_cotadas:
            nota = notas.get(r.id)
            total, vits = cot_vits.get(r.id, (0, 0))
            ultimas_rodadas.append({
                "rodada": r,
                "cotacoes": total,
                "vitorias": vits,
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


@fornecedor_bp.route("/pnl")
@login_required
@fornecedor_required
def pnl():
    """Meu P&L: receita efetiva, margem vs preco de partida, top clientes e produtos."""
    fornecedor = current_user.fornecedor
    if not fornecedor:
        flash("Complete seu cadastro.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    dados = calcular_pnl(fornecedor.id)

    return render_template(
        "fornecedor/pnl.html",
        fornecedor=fornecedor,
        kpis=dados["kpis"],
        top_clientes=dados["top_clientes"],
        top_produtos=dados["top_produtos"],
        por_rodada=dados["por_rodada"],
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

    # KPIs cacheados (TTL 30s) — `total_cotacoes` aqui sombreia o helper
    # importado, entao usamos os helpers via aliases inline pra clareza.
    total_cotacoes_n = total_cotacoes(fid)
    cotacoes_vencedoras_n = cotacoes_vencedoras(fid)
    taxa_vitoria = round(cotacoes_vencedoras_n / total_cotacoes_n * 100, 1) if total_cotacoes_n else 0

    rodadas_participou = (
        db.session.query(func.count(func.distinct(Cotacao.rodada_id)))
        .filter(Cotacao.fornecedor_id == fid)
        .scalar()
    ) or 0

    media_recebida = media_avaliacao_recebida(fid)
    total_avaliacoes = total_avaliacoes_recebidas(fid)

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
        total_cotacoes=total_cotacoes_n,
        cotacoes_vencedoras=cotacoes_vencedoras_n,
        taxa_vitoria=taxa_vitoria,
        rodadas_participou=rodadas_participou,
        media_recebida=media_recebida,
        total_avaliacoes=total_avaliacoes,
        top_produtos=top_produtos,
        avaliacoes_recentes=avaliacoes_recentes,
    )

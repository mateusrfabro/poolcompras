"""Rotas admin de analytics, funil de conversao, historico de aprovacoes e relatorio consolidado."""
from datetime import datetime
from flask import render_template, flash, request
from flask_login import login_required
from sqlalchemy import func

from app import db
from app.models import (
    Produto, Rodada, Fornecedor, Lanchonete,
    ParticipacaoRodada, AvaliacaoRodada, ItemPedido, Cotacao, RodadaProduto,
)
from app.services.csv_export import csv_response
from . import admin_bp, admin_required


@admin_bp.route("/analytics")
@login_required
@admin_required
def analytics():
    """Dashboard de KPIs do PoolCompras para o admin."""
    total_lanchonetes = Lanchonete.query.filter_by(ativa=True).count()
    total_fornecedores = Fornecedor.query.filter_by(ativo=True).count()
    total_produtos = Produto.query.filter_by(ativo=True).count()
    total_rodadas = Rodada.query.count()
    rodadas_finalizadas = Rodada.query.filter_by(status="finalizada").count()

    total_participacoes = ParticipacaoRodada.query.count()
    participacoes_completas = ParticipacaoRodada.query.filter(
        ParticipacaoRodada.avaliacao_geral.isnot(None)
    ).count()

    media_avaliacao = (
        db.session.query(func.avg(ParticipacaoRodada.avaliacao_geral))
        .filter(ParticipacaoRodada.avaliacao_geral.isnot(None))
        .scalar()
    ) or 0

    top_fornecedores = (
        db.session.query(
            Fornecedor.razao_social,
            func.avg(AvaliacaoRodada.estrelas).label("media"),
            func.count(AvaliacaoRodada.id).label("avaliacoes"),
        )
        .join(AvaliacaoRodada, AvaliacaoRodada.fornecedor_id == Fornecedor.id)
        .group_by(Fornecedor.id)
        .order_by(func.avg(AvaliacaoRodada.estrelas).desc())
        .limit(5)
        .all()
    )

    top_produtos = (
        db.session.query(
            Produto.nome,
            Produto.categoria,
            func.sum(ItemPedido.quantidade).label("total"),
            Produto.unidade,
        )
        .join(ItemPedido, ItemPedido.produto_id == Produto.id)
        .group_by(Produto.id)
        .order_by(func.sum(ItemPedido.quantidade).desc())
        .limit(10)
        .all()
    )

    top_lanchonetes = (
        db.session.query(
            Lanchonete.nome_fantasia,
            func.count(ParticipacaoRodada.id).label("participacoes"),
        )
        .join(ParticipacaoRodada, ParticipacaoRodada.lanchonete_id == Lanchonete.id)
        .group_by(Lanchonete.id)
        .order_by(func.count(ParticipacaoRodada.id).desc())
        .limit(5)
        .all()
    )

    taxa_conclusao = (
        round(participacoes_completas / total_participacoes * 100, 1)
        if total_participacoes else 0
    )

    return render_template(
        "admin/analytics.html",
        total_lanchonetes=total_lanchonetes,
        total_fornecedores=total_fornecedores,
        total_produtos=total_produtos,
        total_rodadas=total_rodadas,
        rodadas_finalizadas=rodadas_finalizadas,
        total_participacoes=total_participacoes,
        participacoes_completas=participacoes_completas,
        taxa_conclusao=taxa_conclusao,
        media_avaliacao=round(float(media_avaliacao), 1),
        top_fornecedores=top_fornecedores,
        top_produtos=top_produtos,
        top_lanchonetes=top_lanchonetes,
    )


@admin_bp.route("/rodadas/<int:rodada_id>/funil")
@login_required
@admin_required
def rodada_funil(rodada_id):
    """Onde os pedidos travam na rodada: convidadas -> iniciaram -> enviaram -> aprovadas -> aceitaram -> pagaram -> receberam -> avaliaram."""
    rodada = Rodada.query.get_or_404(rodada_id)

    convidadas = Lanchonete.query.filter_by(ativa=True).count()

    iniciaram_ids = {
        lid for (lid,) in db.session.query(ItemPedido.lanchonete_id)
        .filter_by(rodada_id=rodada_id)
        .distinct().all()
    }
    iniciaram = len(iniciaram_ids)

    parts = ParticipacaoRodada.query.filter_by(rodada_id=rodada_id).all()

    enviaram = sum(1 for p in parts if p.pedido_enviado_em)
    aprovadas = sum(1 for p in parts if p.pedido_aprovado_em)
    aceitaram = sum(1 for p in parts if p.aceite_proposta is True)
    pagaram = sum(1 for p in parts if p.comprovante_em)
    receberam = sum(1 for p in parts if p.entrega_informada_em)
    avaliaram = sum(1 for p in parts if p.avaliacao_em)

    etapas = [
        {"nome": "Lanchonetes ativas", "n": convidadas, "dica": "Universo total disponivel"},
        {"nome": "Iniciaram pedido", "n": iniciaram, "dica": "Ao menos 1 item salvo (rascunho)"},
        {"nome": "Enviaram pra moderacao", "n": enviaram, "dica": "Clicaram em 'Enviar pedido'"},
        {"nome": "Pedidos aprovados", "n": aprovadas, "dica": "Admin aprovou e entrou no pool"},
        {"nome": "Aceitaram proposta", "n": aceitaram, "dica": "Pos-finalizacao da rodada"},
        {"nome": "Enviaram comprovante", "n": pagaram, "dica": "Pagaram o fornecedor"},
        {"nome": "Receberam entrega", "n": receberam, "dica": "Fornecedor confirmou entrega"},
        {"nome": "Avaliaram a rodada", "n": avaliaram, "dica": "Fluxo completo"},
    ]

    topo = etapas[0]["n"] or 1
    prev = topo
    for e in etapas:
        e["pct_topo"] = round(e["n"] / topo * 100, 1) if topo else 0
        e["pct_prev"] = round(e["n"] / prev * 100, 1) if prev else 0
        e["drop"] = prev - e["n"]
        prev = e["n"] if e["n"] else 1

    return render_template(
        "admin/rodada_funil.html",
        rodada=rodada,
        etapas=etapas,
    )


@admin_bp.route("/historico-aprovacoes")
@login_required
@admin_required
def historico_aprovacoes():
    """Lista todos os produtos sugeridos por fornecedores, com status de aprovacao."""
    registros = (
        db.session.query(RodadaProduto, Produto, Rodada, Fornecedor)
        .join(Produto, RodadaProduto.produto_id == Produto.id)
        .join(Rodada, RodadaProduto.rodada_id == Rodada.id)
        .join(Fornecedor, RodadaProduto.adicionado_por_fornecedor_id == Fornecedor.id)
        .filter(RodadaProduto.adicionado_por_fornecedor_id.isnot(None))
        .order_by(RodadaProduto.criado_em.desc())
        .all()
    )

    if request.args.get("exportar") == "csv":
        rows = []
        for rp, p, r, f in registros:
            status = "Pendente" if rp.aprovado is None else ("Aprovado" if rp.aprovado else "Recusado")
            rows.append([
                rp.criado_em.strftime("%d/%m/%Y %H:%M") if rp.criado_em else "",
                r.nome, p.nome, p.categoria, p.subcategoria or "",
                p.unidade,
                f"{float(rp.preco_partida):.2f}".replace(".", ",") if rp.preco_partida else "",
                f.razao_social, status,
            ])
        return csv_response(
            filename="historico_aprovacoes.csv",
            headers=["Data", "Rodada", "Produto", "Categoria", "Subcategoria",
                     "Unidade", "Preco de partida (R$)", "Fornecedor", "Status"],
            rows=rows,
            delimiter=",",
        )

    return render_template("admin/historico_aprovacoes.html", registros=registros)


@admin_bp.route("/relatorio", methods=["GET"])
@login_required
@admin_required
def relatorio():
    """Relatorio consolidado com filtro por periodo. GET renderiza form; com params exporta CSV."""
    de = request.args.get("de")
    ate = request.args.get("ate")
    exportar = request.args.get("exportar") == "csv"

    if not de or not ate:
        return render_template("admin/relatorio.html", dados=None, de=de, ate=ate)

    try:
        dt_de = datetime.strptime(de, "%Y-%m-%d")
        dt_ate = datetime.strptime(ate, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        flash("Datas inválidas.", "error")
        return render_template("admin/relatorio.html", dados=None, de=de, ate=ate)

    rodadas = (
        Rodada.query
        .filter(Rodada.data_abertura >= dt_de, Rodada.data_abertura <= dt_ate)
        .order_by(Rodada.data_abertura.desc())
        .all()
    )
    rod_ids = [r.id for r in rodadas]

    total_pedidos = ItemPedido.query.filter(ItemPedido.rodada_id.in_(rod_ids)).count() if rod_ids else 0
    total_cotacoes = Cotacao.query.filter(Cotacao.rodada_id.in_(rod_ids)).count() if rod_ids else 0
    total_participacoes = ParticipacaoRodada.query.filter(
        ParticipacaoRodada.rodada_id.in_(rod_ids)).count() if rod_ids else 0

    lanchonetes_ativas = (
        db.session.query(func.count(func.distinct(ItemPedido.lanchonete_id)))
        .filter(ItemPedido.rodada_id.in_(rod_ids))
        .scalar()
    ) if rod_ids else 0

    media_avaliacao = 0
    if rod_ids:
        avg = (
            db.session.query(func.avg(ParticipacaoRodada.avaliacao_geral))
            .filter(ParticipacaoRodada.rodada_id.in_(rod_ids),
                    ParticipacaoRodada.avaliacao_geral.isnot(None))
            .scalar()
        )
        media_avaliacao = round(float(avg), 1) if avg else 0

    dados = {
        "rodadas": rodadas,
        "total_rodadas": len(rodadas),
        "finalizadas": sum(1 for r in rodadas if r.status == "finalizada"),
        "canceladas": sum(1 for r in rodadas if r.status == "cancelada"),
        "total_pedidos": total_pedidos,
        "total_cotacoes": total_cotacoes,
        "total_participacoes": total_participacoes,
        "lanchonetes_ativas": lanchonetes_ativas,
        "media_avaliacao": media_avaliacao,
    }

    if exportar:
        return csv_response(
            filename=f"relatorio_{de}_a_{ate}.csv",
            headers=["rodada", "data_abertura", "status", "pedidos", "cotacoes"],
            rows=[
                [r.nome, r.data_abertura.strftime("%Y-%m-%d"), r.status,
                 str(ItemPedido.query.filter_by(rodada_id=r.id).count()),
                 str(Cotacao.query.filter_by(rodada_id=r.id).count())]
                for r in rodadas
            ],
        )

    return render_template("admin/relatorio.html", dados=dados, de=de, ate=ate)

"""Rotas admin do ciclo de vida de Rodadas + exports."""
import logging
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import (
    Produto, Rodada, RodadaProduto, Cotacao,
    ItemPedido, ParticipacaoRodada, EventoRodada,
)
from app.services.csv_export import csv_response
from . import admin_bp, admin_required

logger = logging.getLogger(__name__)


@admin_bp.route("/rodadas/nova", methods=["GET", "POST"])
@login_required
@admin_required
def rodada_nova():
    if request.method == "POST":
        rodada = Rodada(
            nome=request.form["nome"].strip(),
            data_abertura=datetime.strptime(request.form["data_abertura"], "%Y-%m-%d"),
            data_fechamento=datetime.strptime(request.form["data_fechamento"], "%Y-%m-%d"),
            status="preparando",
        )
        db.session.add(rodada)
        db.session.commit()
        logger.info("ADMIN_RODADA_CRIADA admin=%s rodada=%s nome=%s",
                    current_user.id, rodada.id, rodada.nome)
        flash("Rodada criada! Agora monte o catálogo de produtos.", "success")
        return redirect(url_for("admin.rodada_catalogo", rodada_id=rodada.id))

    return render_template("admin/rodada_form.html")


@admin_bp.route("/rodadas/<int:rodada_id>/catalogo", methods=["GET", "POST"])
@login_required
@admin_required
def rodada_catalogo(rodada_id):
    """Tela onde o admin seleciona os produtos que farao parte da rodada."""
    rodada = db.get_or_404(Rodada, rodada_id)
    produtos_ativos = (
        Produto.query.filter_by(ativo=True)
        .order_by(Produto.categoria, Produto.subcategoria, Produto.nome)
        .all()
    )

    if request.method == "POST":
        ids_selecionados = set(request.form.getlist("produto_id", type=int))
        atuais = RodadaProduto.query.filter_by(rodada_id=rodada_id).all()
        atuais_ids = {rp.produto_id for rp in atuais}

        novos = ids_selecionados - atuais_ids
        for pid in novos:
            db.session.add(RodadaProduto(
                rodada_id=rodada_id,
                produto_id=pid,
                adicionado_por_fornecedor_id=None,
                aprovado=None,
            ))

        remover = atuais_ids - ids_selecionados
        for rp in atuais:
            if rp.produto_id in remover and rp.preco_partida is None:
                db.session.delete(rp)

        acao = request.form.get("acao")
        if acao == "enviar":
            rodada.status = "aguardando_cotacao"
            flash(f"Catálogo enviado aos fornecedores! {len(ids_selecionados)} produtos.", "success")
            db.session.commit()
            return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))
        else:
            db.session.commit()
            flash(f"Catálogo salvo. {len(ids_selecionados)} produtos selecionados.", "success")
            return redirect(url_for("admin.rodada_catalogo", rodada_id=rodada_id))

    selecionados = {rp.produto_id for rp in RodadaProduto.query.filter_by(rodada_id=rodada_id).all()}

    by_cat = {}
    for p in produtos_ativos:
        sub = p.subcategoria or "—"
        by_cat.setdefault(p.categoria, {}).setdefault(sub, []).append(p)

    return render_template(
        "admin/rodada_catalogo.html",
        rodada=rodada,
        produtos_por_categoria=by_cat,
        selecionados=selecionados,
        total_selecionados=len(selecionados),
    )


@admin_bp.route("/rodadas/<int:rodada_id>/fechar", methods=["POST"])
@login_required
@admin_required
def rodada_fechar(rodada_id):
    rodada = db.get_or_404(Rodada, rodada_id)
    rodada.status = "fechada"
    db.session.add(EventoRodada(
        rodada_id=rodada_id,
        tipo=EventoRodada.TIPO_RODADA_FECHADA,
        ator_id=current_user.id,
        descricao="Rodada fechada pelo admin para cotação",
    ))
    db.session.commit()
    flash(f"Rodada '{rodada.nome}' fechada. Hora de cotar!", "success")
    return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))


@admin_bp.route("/rodadas/<int:rodada_id>/encerrar-coleta", methods=["POST"])
@login_required
@admin_required
def rodada_encerrar_coleta(rodada_id):
    """Admin encerra coleta de pedidos das lanchonetes -> status em_negociacao."""
    rodada = db.get_or_404(Rodada, rodada_id)
    if rodada.status != "aberta":
        flash("Só é possível encerrar coleta de rodadas abertas.", "warning")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))
    rodada.status = "em_negociacao"
    db.session.add(EventoRodada(
        rodada_id=rodada_id,
        tipo="rodada_em_negociacao",
        ator_id=current_user.id,
        descricao="Admin encerrou a coleta de pedidos e iniciou a negociação",
    ))
    db.session.commit()
    flash("Coleta encerrada! A rodada está agora em negociação.", "success")
    return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))


@admin_bp.route("/rodadas/<int:rodada_id>/finalizar", methods=["POST"])
@login_required
@admin_required
def rodada_finalizar(rodada_id):
    """Admin finaliza a negociação -> rodada 'finalizada' (lanchonetes aceitam)."""
    rodada = db.get_or_404(Rodada, rodada_id)
    if rodada.status != "em_negociacao":
        flash("Só é possível finalizar rodadas em negociação.", "warning")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))

    rps = RodadaProduto.query.filter_by(rodada_id=rodada_id).filter(
        RodadaProduto.preco_partida.isnot(None)
    ).all()
    for rp in rps:
        forn_id = rp.adicionado_por_fornecedor_id
        if forn_id and rp.preco_partida:
            existe = Cotacao.query.filter_by(
                rodada_id=rodada_id, fornecedor_id=forn_id,
                produto_id=rp.produto_id,
            ).first()
            if not existe:
                db.session.add(Cotacao(
                    rodada_id=rodada_id,
                    fornecedor_id=forn_id,
                    produto_id=rp.produto_id,
                    preco_unitario=rp.preco_partida,
                    selecionada=True,
                ))
    rodada.status = "finalizada"
    db.session.add(EventoRodada(
        rodada_id=rodada_id,
        tipo="rodada_finalizada",
        ator_id=current_user.id,
        descricao="Rodada finalizada pelo admin",
    ))
    db.session.commit()
    logger.info("ADMIN_RODADA_FINALIZADA admin=%s rodada=%s",
                current_user.id, rodada_id)
    flash("Rodada finalizada! Lanchonetes podem agora aceitar a proposta.", "success")
    return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))


@admin_bp.route("/rodadas/<int:rodada_id>/cancelar", methods=["POST"])
@login_required
@admin_required
def rodada_cancelar(rodada_id):
    rodada = db.get_or_404(Rodada, rodada_id)
    if rodada.status == "cancelada":
        flash("Esta rodada já foi cancelada.", "warning")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))
    rodada.status = "cancelada"
    db.session.add(EventoRodada(
        rodada_id=rodada_id,
        tipo=EventoRodada.TIPO_RODADA_CANCELADA,
        ator_id=current_user.id,
        descricao="Rodada cancelada pelo admin",
    ))
    db.session.commit()
    logger.warning("ADMIN_RODADA_CANCELADA admin=%s rodada=%s nome=%s",
                   current_user.id, rodada_id, rodada.nome)
    flash(f"Rodada '{rodada.nome}' cancelada.", "success")
    return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))


@admin_bp.route("/rodadas/<int:rodada_id>/liberar", methods=["POST"])
@login_required
@admin_required
def rodada_liberar(rodada_id):
    """Admin libera a rodada para as lanchonetes (muda status -> aberta)."""
    rodada = db.get_or_404(Rodada, rodada_id)
    if rodada.status not in ("aguardando_cotacao", "aguardando_aprovacao"):
        flash("Rodada não está pronta para ser liberada.", "warning")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))

    pendentes = RodadaProduto.query.filter_by(
        rodada_id=rodada_id, aprovado=None,
    ).filter(RodadaProduto.adicionado_por_fornecedor_id.isnot(None)).count()
    if pendentes > 0:
        flash(f"Ainda há {pendentes} produto(s) aguardando aprovação.", "warning")
        return redirect(url_for("admin.rodada_aprovar_produtos", rodada_id=rodada_id))

    rodada.status = "aberta"
    db.session.commit()
    logger.info("ADMIN_RODADA_LIBERADA admin=%s rodada=%s",
                current_user.id, rodada_id)
    flash("Rodada liberada para as lanchonetes!", "success")
    return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))


@admin_bp.route("/rodadas/exportar.csv")
@login_required
@admin_required
def rodadas_exportar():
    lista = Rodada.query.order_by(Rodada.data_abertura.desc()).all()
    return csv_response(
        filename="rodadas.csv",
        headers=["id", "nome", "status", "data_abertura", "data_fechamento", "criado_em"],
        rows=[
            [r.id, r.nome, r.status,
             r.data_abertura.strftime("%Y-%m-%d %H:%M") if r.data_abertura else "",
             r.data_fechamento.strftime("%Y-%m-%d %H:%M") if r.data_fechamento else "",
             r.criado_em.strftime("%Y-%m-%d %H:%M") if r.criado_em else ""]
            for r in lista
        ],
    )


@admin_bp.route("/rodadas/<int:rodada_id>/exportar.csv")
@login_required
@admin_required
def rodada_detalhe_exportar(rodada_id):
    """Exporta demanda agregada + cotações da rodada em CSV pra admin."""
    rodada = db.get_or_404(Rodada, rodada_id)

    # Demanda agregada — pool unificado: somente pedidos aprovados
    demanda = (
        db.session.query(
            Produto.nome,
            Produto.categoria,
            Produto.unidade,
            func.sum(ItemPedido.quantidade).label("total_pedido"),
            func.count(func.distinct(ItemPedido.lanchonete_id)).label("qtd_lanchonetes"),
        )
        .join(ItemPedido, ItemPedido.produto_id == Produto.id)
        .join(ParticipacaoRodada,
              (ParticipacaoRodada.rodada_id == ItemPedido.rodada_id) &
              (ParticipacaoRodada.lanchonete_id == ItemPedido.lanchonete_id))
        .filter(ItemPedido.rodada_id == rodada_id)
        .filter(ParticipacaoRodada.pedido_aprovado_em.isnot(None))
        .group_by(Produto.id)
        .order_by(Produto.categoria, Produto.nome)
        .all()
    )
    cotacoes = (
        Cotacao.query
        .filter_by(rodada_id=rodada_id)
        .order_by(Cotacao.produto_id, Cotacao.preco_unitario)
        .all()
    )

    headers = ["produto", "categoria", "unidade", "total_pedido", "lanchonetes",
               "fornecedor_cotacao", "preco_unitario", "selecionada"]
    rows = []
    for d in demanda:
        cots = [c for c in cotacoes if c.produto.nome == d.nome]
        if cots:
            for c in cots:
                rows.append([
                    d.nome, d.categoria, d.unidade, str(d.total_pedido),
                    str(d.qtd_lanchonetes),
                    c.fornecedor.razao_social if c.fornecedor else "",
                    str(c.preco_unitario),
                    "sim" if c.selecionada else "",
                ])
        else:
            rows.append([d.nome, d.categoria, d.unidade, str(d.total_pedido),
                         str(d.qtd_lanchonetes), "", "", ""])

    nome_arquivo = f"rodada_{rodada_id}_{rodada.nome.replace(' ', '_')}.csv"
    return csv_response(filename=nome_arquivo, headers=headers, rows=rows)

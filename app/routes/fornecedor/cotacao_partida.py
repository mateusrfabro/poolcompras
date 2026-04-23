"""Fase 1 da cotacao: ver demanda + preco de partida + sugestao de produto novo."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import (
    Rodada, ItemPedido, Cotacao, Produto,
    ParticipacaoRodada, RodadaProduto,
)
from . import fornecedor_bp, fornecedor_required


@fornecedor_bp.route("/rodada/<int:rodada_id>")
@login_required
@fornecedor_required
def ver_demanda(rodada_id):
    rodada = db.get_or_404(Rodada, rodada_id)

    # Demanda agregada — SOMENTE pedidos aprovados pelo admin
    agregado = (
        db.session.query(
            Produto.id,
            Produto.nome,
            Produto.categoria,
            Produto.unidade,
            func.sum(ItemPedido.quantidade).label("total_quantidade"),
        )
        .join(ItemPedido, ItemPedido.produto_id == Produto.id)
        .join(ParticipacaoRodada,
              (ParticipacaoRodada.rodada_id == ItemPedido.rodada_id) &
              (ParticipacaoRodada.lanchonete_id == ItemPedido.lanchonete_id))
        .filter(ItemPedido.rodada_id == rodada_id)
        .filter(ParticipacaoRodada.pedido_aprovado_em.isnot(None))
        .group_by(Produto.id, Produto.nome, Produto.categoria, Produto.unidade)
        .order_by(Produto.categoria, Produto.nome)
        .all()
    )

    fornecedor = current_user.fornecedor
    minhas = []
    if fornecedor:
        minhas = Cotacao.query.filter_by(
            rodada_id=rodada_id, fornecedor_id=fornecedor.id
        ).all()

    return render_template(
        "fornecedor/demanda.html",
        rodada=rodada,
        agregado=agregado,
        minhas_cotacoes=minhas,
    )


@fornecedor_bp.route("/rodada/<int:rodada_id>/cotar", methods=["GET", "POST"])
@login_required
@fornecedor_required
def enviar_cotacao(rodada_id):
    """Rota legada: cotacao direta (status fechada/cotando)."""
    rodada = db.get_or_404(Rodada, rodada_id)
    fornecedor = current_user.fornecedor

    if rodada.status not in ("fechada", "cotando"):
        flash("Esta rodada não está aberta para cotações.", "warning")
        return redirect(url_for("fornecedor.dashboard"))

    produtos_ids = (
        db.session.query(func.distinct(ItemPedido.produto_id))
        .filter(ItemPedido.rodada_id == rodada_id)
        .all()
    )
    produtos_ids = [p[0] for p in produtos_ids]
    produtos = Produto.query.filter(Produto.id.in_(produtos_ids)).order_by(Produto.categoria, Produto.nome).all()

    qtds = dict(
        db.session.query(
            ItemPedido.produto_id,
            func.sum(ItemPedido.quantidade),
        )
        .filter(ItemPedido.rodada_id == rodada_id)
        .group_by(ItemPedido.produto_id)
        .all()
    )

    if request.method == "POST":
        count = 0
        for produto in produtos:
            preco = request.form.get(f"preco_{produto.id}", type=float)
            if preco and 0 < preco <= 100000:
                existente = Cotacao.query.filter_by(
                    rodada_id=rodada_id,
                    fornecedor_id=fornecedor.id,
                    produto_id=produto.id,
                ).first()

                if existente:
                    existente.preco_unitario = preco
                else:
                    db.session.add(Cotacao(
                        rodada_id=rodada_id,
                        fornecedor_id=fornecedor.id,
                        produto_id=produto.id,
                        preco_unitario=preco,
                    ))
                count += 1

        if rodada.status == "fechada":
            rodada.status = "cotando"

        db.session.commit()
        flash(f"Cotação enviada! {count} produto(s) cotado(s).", "success")
        return redirect(url_for("fornecedor.ver_demanda", rodada_id=rodada_id))

    return render_template(
        "fornecedor/cotar.html",
        rodada=rodada,
        produtos=produtos,
        qtds=qtds,
    )


@fornecedor_bp.route("/rodada/<int:rodada_id>/cotar-catalogo", methods=["GET", "POST"])
@login_required
@fornecedor_required
def cotar_catalogo(rodada_id):
    """Fornecedor preenche preço de partida nos produtos do catálogo + sugere novos."""
    rodada = db.get_or_404(Rodada, rodada_id)
    if rodada.status != "aguardando_cotacao":
        flash("Esta rodada não está mais aberta para cotação.", "warning")
        return redirect(url_for("fornecedor.dashboard"))

    fornecedor = current_user.fornecedor
    if not fornecedor:
        flash("Complete seu cadastro.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    catalogo = (
        RodadaProduto.query
        .filter_by(rodada_id=rodada_id)
        .filter((RodadaProduto.aprovado.is_(None))
                | (RodadaProduto.aprovado.is_(True)))
        .join(Produto)
        .order_by(Produto.categoria, Produto.subcategoria, Produto.nome)
        .all()
    )

    if request.method == "POST":
        # 1. Atualiza precos de partida
        count_precos = 0
        for rp in catalogo:
            preco_str = request.form.get(f"preco_{rp.id}", "").strip()
            if preco_str:
                try:
                    preco = float(preco_str.replace(",", "."))
                    if 0 < preco <= 100000:
                        rp.preco_partida = preco
                        count_precos += 1
                except ValueError:
                    pass

        # 2. Produto sugerido (opcional)
        nome_novo = request.form.get("novo_nome", "").strip()
        if nome_novo:
            categoria_nova = request.form.get("novo_categoria", "").strip() or "Outro"
            subcategoria_nova = request.form.get("novo_subcategoria", "").strip()
            if not subcategoria_nova:
                flash("Ao sugerir um produto novo, preencha também a subcategoria.", "error")
                return redirect(url_for("fornecedor.cotar_catalogo", rodada_id=rodada_id))
            unidade_nova = request.form.get("novo_unidade", "").strip() or "unidade"
            preco_novo_str = request.form.get("novo_preco", "").strip()

            try:
                preco_novo = float(preco_novo_str.replace(",", ".")) if preco_novo_str else None
            except ValueError:
                preco_novo = None

            produto_novo = Produto(
                nome=nome_novo,
                categoria=categoria_nova,
                subcategoria=subcategoria_nova,
                unidade=unidade_nova,
                ativo=True,
                descricao=f"Sugerido por {fornecedor.razao_social}",
            )
            db.session.add(produto_novo)
            db.session.flush()

            db.session.add(RodadaProduto(
                rodada_id=rodada_id,
                produto_id=produto_novo.id,
                preco_partida=preco_novo,
                adicionado_por_fornecedor_id=fornecedor.id,
                aprovado=None,
            ))
            flash(f"Produto '{nome_novo}' sugerido. Aguardando aprovação do admin.", "success")

        # 3. Auto-libera se nao ha produtos pendentes
        pendentes = RodadaProduto.query.filter_by(
            rodada_id=rodada_id, aprovado=None,
        ).filter(RodadaProduto.adicionado_por_fornecedor_id.isnot(None)).count()

        db.session.commit()

        if pendentes == 0 and not nome_novo:
            sem_preco = RodadaProduto.query.filter_by(
                rodada_id=rodada_id, preco_partida=None,
            ).count()
            if sem_preco == 0:
                rodada.status = "aberta"
                db.session.commit()
                flash(f"Cotação salva! {count_precos} preços atualizados. Rodada liberada para lanchonetes.", "success")
            else:
                flash(f"Cotação salva. {sem_preco} produto(s) ainda sem preço.", "success")
        else:
            flash(f"Cotação salva. {count_precos} preços atualizados.", "success")

        return redirect(url_for("fornecedor.cotar_catalogo", rodada_id=rodada_id))

    by_cat = {}
    for rp in catalogo:
        cat = rp.produto.categoria
        sub = rp.produto.subcategoria or "—"
        by_cat.setdefault(cat, {}).setdefault(sub, []).append(rp)

    rows_sub = (
        db.session.query(Produto.categoria, Produto.subcategoria)
        .filter(Produto.subcategoria.isnot(None))
        .filter(Produto.subcategoria != "")
        .distinct()
        .order_by(Produto.categoria, Produto.subcategoria)
        .all()
    )
    subcategorias_por_cat = {}
    for cat, sub in rows_sub:
        subcategorias_por_cat.setdefault(cat, []).append(sub)

    return render_template(
        "fornecedor/cotar_catalogo.html",
        rodada=rodada,
        catalogo_por_categoria=by_cat,
        fornecedor=fornecedor,
        subcategorias_por_cat=subcategorias_por_cat,
    )

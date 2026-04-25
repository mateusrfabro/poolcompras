"""Rotas admin de Produtos (CRUD + historico de precos + export)."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import select

from app import db
from app.models import Produto, Rodada, RodadaProduto, Cotacao, Fornecedor
from app.services.csv_export import csv_response
from . import admin_bp, admin_required


def _subcategorias_por_categoria():
    """Retorna dict {categoria: [subcategorias_distintas]} para datalist."""
    rows = (
        db.session.query(Produto.categoria, Produto.subcategoria)
        .filter(Produto.subcategoria.isnot(None))
        .filter(Produto.subcategoria != "")
        .distinct()
        .order_by(Produto.categoria, Produto.subcategoria)
        .all()
    )
    out = {}
    for cat, sub in rows:
        out.setdefault(cat, []).append(sub)
    return out


@admin_bp.route("/produtos")
@login_required
@admin_required
def produtos():
    lista = db.session.scalars(
        select(Produto).order_by(Produto.categoria, Produto.nome)
    ).all()
    return render_template("admin/produtos.html", produtos=lista)


@admin_bp.route("/produtos/novo", methods=["GET", "POST"])
@login_required
@admin_required
def produto_novo():
    if request.method == "POST":
        nome = request.form["nome"].strip()
        categoria = request.form["categoria"].strip()
        subcategoria = request.form.get("subcategoria", "").strip()
        unidade = request.form["unidade"].strip()

        if not subcategoria:
            flash("Subcategoria é obrigatória. Ex: Acém, Brioche, Fatiado...", "error")
            return render_template(
                "admin/produto_form.html", produto=None,
                subcategorias_por_cat=_subcategorias_por_categoria(),
                form_data=request.form,
            )

        produto = Produto(
            nome=nome,
            descricao=request.form.get("descricao", "").strip(),
            categoria=categoria,
            subcategoria=subcategoria,
            unidade=unidade,
        )
        db.session.add(produto)
        db.session.commit()
        flash("Produto cadastrado!", "success")
        return redirect(url_for("admin.produtos"))

    return render_template(
        "admin/produto_form.html", produto=None,
        subcategorias_por_cat=_subcategorias_por_categoria(),
    )


@admin_bp.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def produto_editar(produto_id):
    produto = db.get_or_404(Produto, produto_id)

    if request.method == "POST":
        subcategoria = request.form.get("subcategoria", "").strip()
        if not subcategoria:
            flash("Subcategoria é obrigatória. Ex: Acém, Brioche, Fatiado...", "error")
            return render_template(
                "admin/produto_form.html", produto=produto,
                subcategorias_por_cat=_subcategorias_por_categoria(),
            )

        produto.nome = request.form["nome"].strip()
        produto.descricao = request.form.get("descricao", "").strip()
        produto.categoria = request.form["categoria"].strip()
        produto.subcategoria = subcategoria
        produto.unidade = request.form["unidade"].strip()
        produto.ativo = "ativo" in request.form
        db.session.commit()
        flash("Produto atualizado!", "success")
        return redirect(url_for("admin.produtos"))

    return render_template(
        "admin/produto_form.html", produto=produto,
        subcategorias_por_cat=_subcategorias_por_categoria(),
    )


@admin_bp.route("/produtos/exportar.csv")
@login_required
@admin_required
def produtos_exportar():
    lista = db.session.scalars(
        select(Produto).order_by(Produto.categoria, Produto.subcategoria, Produto.nome)
    ).all()
    return csv_response(
        filename="produtos.csv",
        headers=["id", "nome", "categoria", "subcategoria", "unidade", "descricao", "ativo", "criado_em"],
        rows=[
            [p.id, p.nome, p.categoria, p.subcategoria or "", p.unidade, p.descricao or "",
             "sim" if p.ativo else "nao",
             p.criado_em.strftime("%Y-%m-%d %H:%M") if p.criado_em else ""]
            for p in lista
        ],
    )


@admin_bp.route("/produtos/<int:produto_id>/historico-precos")
@login_required
@admin_required
def produto_historico_precos(produto_id):
    """Evolucao do preco de um SKU ao longo das rodadas: preco de partida + cotacoes finais + vencedor."""
    produto = db.get_or_404(Produto, produto_id)

    aparicoes = (
        db.session.query(RodadaProduto, Rodada)
        .join(Rodada, RodadaProduto.rodada_id == Rodada.id)
        .filter(RodadaProduto.produto_id == produto_id)
        .order_by(Rodada.data_abertura.desc())
        .all()
    )

    rodada_ids = [r.id for rp, r in aparicoes]
    cotacoes_por_rodada = {}
    if rodada_ids:
        cots = (
            db.session.query(Cotacao, Fornecedor)
            .join(Fornecedor, Cotacao.fornecedor_id == Fornecedor.id)
            .filter(Cotacao.produto_id == produto_id)
            .filter(Cotacao.rodada_id.in_(rodada_ids))
            .order_by(Cotacao.preco_unitario)
            .all()
        )
        for c, f in cots:
            cotacoes_por_rodada.setdefault(c.rodada_id, []).append((c, f))

    linhas = []
    for rp, r in aparicoes:
        cots = cotacoes_por_rodada.get(r.id, [])
        vencedora = next((c for c, f in cots if c.selecionada), None)
        menor_preco = float(cots[0][0].preco_unitario) if cots else None
        menor_forn = cots[0][1].razao_social if cots else None
        linhas.append({
            "rodada": r,
            "preco_partida": float(rp.preco_partida) if rp.preco_partida else None,
            "menor_preco": menor_preco,
            "menor_fornecedor": menor_forn,
            "qtd_cotacoes": len(cots),
            "vencedora_preco": float(vencedora.preco_unitario) if vencedora else None,
            "vencedora_fornecedor": next(
                (f.razao_social for c, f in cots if c.selecionada), None
            ),
        })

    precos_finais = [l["menor_preco"] for l in linhas if l["menor_preco"]]
    stats = None
    if precos_finais:
        stats = {
            "rodadas": len(linhas),
            "preco_min": min(precos_finais),
            "preco_max": max(precos_finais),
            "preco_medio": sum(precos_finais) / len(precos_finais),
            "variacao_pct": round((precos_finais[0] - precos_finais[-1]) / precos_finais[-1] * 100, 1)
                if len(precos_finais) >= 2 and precos_finais[-1] > 0 else 0,
        }

    return render_template(
        "admin/produto_historico_precos.html",
        produto=produto,
        linhas=linhas,
        stats=stats,
    )

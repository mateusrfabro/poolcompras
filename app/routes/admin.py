import csv
from io import StringIO
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app import db
from app.models import (
    Produto, Rodada, Fornecedor, Lanchonete,
    ParticipacaoRodada, AvaliacaoRodada, ItemPedido, Cotacao, RodadaProduto,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash("Acesso restrito a administradores.", "error")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)

    return decorated


# --- Produtos ---
@admin_bp.route("/produtos")
@login_required
@admin_required
def produtos():
    lista = Produto.query.order_by(Produto.categoria, Produto.nome).all()
    return render_template("admin/produtos.html", produtos=lista)


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
    produto = Produto.query.get_or_404(produto_id)

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


# --- Fornecedores ---
@admin_bp.route("/fornecedores")
@login_required
@admin_required
def fornecedores():
    lista = Fornecedor.query.order_by(Fornecedor.razao_social).all()
    return render_template("admin/fornecedores.html", fornecedores=lista)


@admin_bp.route("/fornecedores/novo", methods=["GET", "POST"])
@login_required
@admin_required
def fornecedor_novo():
    if request.method == "POST":
        fornecedor = Fornecedor(
            razao_social=request.form["razao_social"].strip(),
            nome_contato=request.form.get("nome_contato", "").strip(),
            telefone=request.form.get("telefone", "").strip(),
            email=request.form.get("email", "").strip(),
            cidade=request.form.get("cidade", "").strip(),
            chave_pix=request.form.get("chave_pix", "").strip() or None,
            banco=request.form.get("banco", "").strip() or None,
            agencia=request.form.get("agencia", "").strip() or None,
            conta=request.form.get("conta", "").strip() or None,
        )
        db.session.add(fornecedor)
        db.session.commit()
        flash("Fornecedor cadastrado!", "success")
        return redirect(url_for("admin.fornecedores"))

    return render_template("admin/fornecedor_form.html", fornecedor=None)


@admin_bp.route("/fornecedores/<int:fornecedor_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def fornecedor_editar(fornecedor_id):
    fornecedor = Fornecedor.query.get_or_404(fornecedor_id)
    if request.method == "POST":
        fornecedor.razao_social = request.form["razao_social"].strip()
        fornecedor.nome_contato = request.form.get("nome_contato", "").strip()
        fornecedor.telefone = request.form.get("telefone", "").strip()
        fornecedor.email = request.form.get("email", "").strip()
        fornecedor.cidade = request.form.get("cidade", "").strip()
        fornecedor.chave_pix = request.form.get("chave_pix", "").strip() or None
        fornecedor.banco = request.form.get("banco", "").strip() or None
        fornecedor.agencia = request.form.get("agencia", "").strip() or None
        fornecedor.conta = request.form.get("conta", "").strip() or None
        fornecedor.ativo = "ativo" in request.form
        db.session.commit()
        flash("Fornecedor atualizado!", "success")
        return redirect(url_for("admin.fornecedores"))
    return render_template("admin/fornecedor_form.html", fornecedor=fornecedor)


@admin_bp.route("/fornecedores/exportar.csv")
@login_required
@admin_required
def fornecedores_exportar():
    fornecedores = Fornecedor.query.order_by(Fornecedor.razao_social).all()
    return _csv_response(
        filename="fornecedores.csv",
        headers=["id", "razao_social", "nome_contato", "telefone", "email", "cidade", "ativo", "criado_em"],
        rows=[
            [f.id, f.razao_social, f.nome_contato or "", f.telefone or "",
             f.email or "", f.cidade or "", "sim" if f.ativo else "nao",
             f.criado_em.strftime("%Y-%m-%d %H:%M") if f.criado_em else ""]
            for f in fornecedores
        ],
    )


# --- Rodadas ---
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
        flash("Rodada criada! Agora monte o catálogo de produtos.", "success")
        return redirect(url_for("admin.rodada_catalogo", rodada_id=rodada.id))

    return render_template("admin/rodada_form.html")


@admin_bp.route("/rodadas/<int:rodada_id>/catalogo", methods=["GET", "POST"])
@login_required
@admin_required
def rodada_catalogo(rodada_id):
    """Tela onde o admin seleciona os produtos que farao parte da rodada."""
    rodada = Rodada.query.get_or_404(rodada_id)
    produtos_ativos = (
        Produto.query.filter_by(ativo=True)
        .order_by(Produto.categoria, Produto.subcategoria, Produto.nome)
        .all()
    )

    if request.method == "POST":
        ids_selecionados = set(request.form.getlist("produto_id", type=int))
        # Produtos ja no catalogo desta rodada
        atuais = RodadaProduto.query.filter_by(rodada_id=rodada_id).all()
        atuais_ids = {rp.produto_id for rp in atuais}

        # Adicionar novos
        novos = ids_selecionados - atuais_ids
        for pid in novos:
            db.session.add(RodadaProduto(
                rodada_id=rodada_id,
                produto_id=pid,
                adicionado_por_fornecedor_id=None,  # admin adicionou
                aprovado=None,  # admin nao precisa aprovar o proprio
            ))

        # Remover os desmarcados (se nao tiver preco preenchido ainda)
        remover = atuais_ids - ids_selecionados
        for rp in atuais:
            if rp.produto_id in remover and rp.preco_partida is None:
                db.session.delete(rp)

        # Decide acao
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

    # Carrega selecao atual
    selecionados = {rp.produto_id for rp in RodadaProduto.query.filter_by(rodada_id=rodada_id).all()}

    # Agrupa por categoria -> subcategoria pra UX
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
    rodada = Rodada.query.get_or_404(rodada_id)
    rodada.status = "fechada"
    from app.models import EventoRodada
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
    rodada = Rodada.query.get_or_404(rodada_id)
    if rodada.status != "aberta":
        flash("Só é possível encerrar coleta de rodadas abertas.", "warning")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))
    rodada.status = "em_negociacao"
    from app.models import EventoRodada
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
    rodada = Rodada.query.get_or_404(rodada_id)
    if rodada.status != "em_negociacao":
        flash("Só é possível finalizar rodadas em negociação.", "warning")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))

    # Marca cotacao selecionada = menor preco de partida por produto (simples)
    rps = RodadaProduto.query.filter_by(rodada_id=rodada_id).filter(
        RodadaProduto.preco_partida.isnot(None)
    ).all()
    for rp in rps:
        # Cria Cotacao se nao existir (liga fornecedor ao produto via preco_partida)
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
    from app.models import EventoRodada
    db.session.add(EventoRodada(
        rodada_id=rodada_id,
        tipo="rodada_finalizada",
        ator_id=current_user.id,
        descricao="Rodada finalizada pelo admin",
    ))
    db.session.commit()
    flash("Rodada finalizada! Lanchonetes podem agora aceitar a proposta.", "success")
    return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))


@admin_bp.route("/rodadas/<int:rodada_id>/cancelar", methods=["POST"])
@login_required
@admin_required
def rodada_cancelar(rodada_id):
    rodada = Rodada.query.get_or_404(rodada_id)
    if rodada.status == "cancelada":
        flash("Esta rodada já foi cancelada.", "warning")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))
    rodada.status = "cancelada"
    from app.models import EventoRodada
    db.session.add(EventoRodada(
        rodada_id=rodada_id,
        tipo=EventoRodada.TIPO_RODADA_CANCELADA,
        ator_id=current_user.id,
        descricao="Rodada cancelada pelo admin",
    ))
    db.session.commit()
    flash(f"Rodada '{rodada.nome}' cancelada.", "success")
    return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))


# --- Lanchonetes ---
@admin_bp.route("/lanchonetes")
@login_required
@admin_required
def lanchonetes():
    lista = Lanchonete.query.order_by(Lanchonete.nome_fantasia).all()
    return render_template("admin/lanchonetes.html", lanchonetes=lista)


@admin_bp.route("/lanchonetes/<int:lanchonete_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def lanchonete_editar(lanchonete_id):
    lanchonete = Lanchonete.query.get_or_404(lanchonete_id)
    if request.method == "POST":
        lanchonete.nome_fantasia = request.form["nome_fantasia"].strip()
        lanchonete.cnpj = request.form.get("cnpj", "").strip() or None
        lanchonete.endereco = request.form.get("endereco", "").strip()
        lanchonete.bairro = request.form.get("bairro", "").strip()
        lanchonete.cidade = request.form.get("cidade", "").strip() or "Londrina"
        lanchonete.ativa = "ativa" in request.form
        db.session.commit()
        flash("Lanchonete atualizada!", "success")
        return redirect(url_for("admin.lanchonetes"))
    return render_template("admin/lanchonete_form.html", lanchonete=lanchonete)


@admin_bp.route("/lanchonetes/exportar.csv")
@login_required
@admin_required
def lanchonetes_exportar():
    lista = Lanchonete.query.order_by(Lanchonete.nome_fantasia).all()
    return _csv_response(
        filename="lanchonetes.csv",
        headers=["id", "nome_fantasia", "responsavel", "email_responsavel",
                 "telefone", "cnpj", "endereco", "bairro", "cidade", "ativa", "criado_em"],
        rows=[
            [l.id, l.nome_fantasia,
             l.responsavel.nome_responsavel if l.responsavel else "",
             l.responsavel.email if l.responsavel else "",
             l.responsavel.telefone if l.responsavel else "",
             l.cnpj or "", l.endereco or "", l.bairro or "", l.cidade or "",
             "sim" if l.ativa else "nao",
             l.criado_em.strftime("%Y-%m-%d %H:%M") if l.criado_em else ""]
            for l in lista
        ],
    )


# --- Produtos: exportar ---
@admin_bp.route("/produtos/exportar.csv")
@login_required
@admin_required
def produtos_exportar():
    lista = Produto.query.order_by(Produto.categoria, Produto.subcategoria, Produto.nome).all()
    return _csv_response(
        filename="produtos.csv",
        headers=["id", "nome", "categoria", "subcategoria", "unidade", "descricao", "ativo", "criado_em"],
        rows=[
            [p.id, p.nome, p.categoria, p.subcategoria or "", p.unidade, p.descricao or "",
             "sim" if p.ativo else "nao",
             p.criado_em.strftime("%Y-%m-%d %H:%M") if p.criado_em else ""]
            for p in lista
        ],
    )


# --- Rodadas: exportar ---
@admin_bp.route("/rodadas/exportar.csv")
@login_required
@admin_required
def rodadas_exportar():
    lista = Rodada.query.order_by(Rodada.data_abertura.desc()).all()
    return _csv_response(
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


# --- Analytics ---
@admin_bp.route("/analytics")
@login_required
@admin_required
def analytics():
    """Dashboard de KPIs do PoolCompras para o admin."""
    # Stats gerais
    total_lanchonetes = Lanchonete.query.filter_by(ativa=True).count()
    total_fornecedores = Fornecedor.query.filter_by(ativo=True).count()
    total_produtos = Produto.query.filter_by(ativo=True).count()
    total_rodadas = Rodada.query.count()
    rodadas_finalizadas = Rodada.query.filter_by(status="finalizada").count()

    # Participações
    total_participacoes = ParticipacaoRodada.query.count()
    participacoes_completas = ParticipacaoRodada.query.filter(
        ParticipacaoRodada.avaliacao_geral.isnot(None)
    ).count()

    # Média de avaliação geral
    media_avaliacao = (
        db.session.query(func.avg(ParticipacaoRodada.avaliacao_geral))
        .filter(ParticipacaoRodada.avaliacao_geral.isnot(None))
        .scalar()
    ) or 0

    # Top 5 fornecedores por avaliação média
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

    # Produtos mais pedidos (top 10)
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

    # Lanchonetes mais ativas (top 5 por participações)
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

    # Taxa de conclusao do fluxo (completas / participacoes)
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


# --- Rodada detalhe: exportar ---
@admin_bp.route("/rodadas/<int:rodada_id>/exportar.csv")
@login_required
@admin_required
def rodada_detalhe_exportar(rodada_id):
    """Exporta demanda agregada + cotações da rodada em CSV pra admin."""
    from sqlalchemy import func
    from app.models import ItemPedido

    rodada = Rodada.query.get_or_404(rodada_id)

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

    from app.models import Cotacao
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
    return _csv_response(filename=nome_arquivo, headers=headers, rows=rows)


# --- Helper: gera resposta CSV com BOM UTF-8 para Excel abrir com acentos OK ---
# --- Aprovacao de produtos sugeridos pelo fornecedor ---
@admin_bp.route("/rodadas/<int:rodada_id>/aprovar-produtos", methods=["GET", "POST"])
@login_required
@admin_required
def rodada_aprovar_produtos(rodada_id):
    """Admin aprova ou recusa produtos sugeridos pelos fornecedores."""
    rodada = Rodada.query.get_or_404(rodada_id)
    pendentes = (
        RodadaProduto.query
        .filter_by(rodada_id=rodada_id, aprovado=None)
        .filter(RodadaProduto.adicionado_por_fornecedor_id.isnot(None))
        .all()
    )

    if request.method == "POST":
        rp_id = request.form.get("rp_id", type=int)
        acao = request.form.get("acao")
        rp = RodadaProduto.query.get(rp_id)
        if not rp or rp.rodada_id != rodada_id:
            flash("Produto não encontrado.", "error")
            return redirect(url_for("admin.rodada_aprovar_produtos", rodada_id=rodada_id))

        if acao == "aprovar":
            rp.aprovado = True
            flash(f"Produto '{rp.produto.nome}' aprovado.", "success")
        elif acao == "recusar":
            rp.aprovado = False
            # Desativa o produto (nao aparece pra lanchonete)
            if rp.produto:
                rp.produto.ativo = False
            flash(f"Produto '{rp.produto.nome}' recusado.", "success")

        db.session.commit()
        return redirect(url_for("admin.rodada_aprovar_produtos", rodada_id=rodada_id))

    return render_template(
        "admin/rodada_aprovar_produtos.html",
        rodada=rodada,
        pendentes=pendentes,
    )


@admin_bp.route("/rodadas/<int:rodada_id>/liberar", methods=["POST"])
@login_required
@admin_required
def rodada_liberar(rodada_id):
    """Admin libera a rodada para as lanchonetes (muda status -> aberta)."""
    rodada = Rodada.query.get_or_404(rodada_id)
    if rodada.status not in ("aguardando_cotacao", "aguardando_aprovacao"):
        flash("Rodada não está pronta para ser liberada.", "warning")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))

    # Checa se todos aprovados
    pendentes = RodadaProduto.query.filter_by(
        rodada_id=rodada_id, aprovado=None,
    ).filter(RodadaProduto.adicionado_por_fornecedor_id.isnot(None)).count()
    if pendentes > 0:
        flash(f"Ainda há {pendentes} produto(s) aguardando aprovação.", "warning")
        return redirect(url_for("admin.rodada_aprovar_produtos", rodada_id=rodada_id))

    rodada.status = "aberta"
    db.session.commit()
    flash("Rodada liberada para as lanchonetes!", "success")
    return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))


# --- Historico de precos de um produto ao longo das rodadas ---
@admin_bp.route("/produtos/<int:produto_id>/historico-precos")
@login_required
@admin_required
def produto_historico_precos(produto_id):
    """Evolucao do preco de um SKU ao longo das rodadas: preco de partida + cotacoes finais + vencedor."""
    produto = Produto.query.get_or_404(produto_id)

    # Todas as aparicoes do produto em RodadaProduto (preco de partida)
    aparicoes = (
        db.session.query(RodadaProduto, Rodada)
        .join(Rodada, RodadaProduto.rodada_id == Rodada.id)
        .filter(RodadaProduto.produto_id == produto_id)
        .order_by(Rodada.data_abertura.desc())
        .all()
    )

    # Pra cada rodada, pegar cotacoes finais (Cotacao)
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

    # Monta linhas da tabela
    linhas = []
    for rp, r in aparicoes:
        cots = cotacoes_por_rodada.get(r.id, [])
        vencedora = next((c for c, f in cots if c.selecionada), None)
        # Menor preco e fornecedor
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

    # Estatisticas simples
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


# --- Funil de conversao da rodada ---
@admin_bp.route("/rodadas/<int:rodada_id>/funil")
@login_required
@admin_required
def rodada_funil(rodada_id):
    """Mostra onde os pedidos travam na rodada: convidadas -> iniciaram -> enviaram -> aprovadas -> aceitaram -> pagaram -> receberam."""
    rodada = Rodada.query.get_or_404(rodada_id)

    # Etapa 1: lanchonetes ativas (convidadas)
    convidadas = Lanchonete.query.filter_by(ativa=True).count()

    # Etapa 2: iniciaram pedido (tem ItemPedido na rodada)
    iniciaram_ids = {
        lid for (lid,) in db.session.query(ItemPedido.lanchonete_id)
        .filter_by(rodada_id=rodada_id)
        .distinct().all()
    }
    iniciaram = len(iniciaram_ids)

    # Particpacoes com flags de pedido
    parts = ParticipacaoRodada.query.filter_by(rodada_id=rodada_id).all()

    # Etapa 3: enviaram (pedido_enviado_em preenchido)
    enviaram = sum(1 for p in parts if p.pedido_enviado_em)

    # Etapa 4: aprovadas
    aprovadas = sum(1 for p in parts if p.pedido_aprovado_em)

    # Etapa 5: aceitaram proposta (pos-finalizacao)
    aceitaram = sum(1 for p in parts if p.aceite_proposta is True)

    # Etapa 6: pagaram (comprovante enviado)
    pagaram = sum(1 for p in parts if p.comprovante_em)

    # Etapa 7: receberam (entrega informada)
    receberam = sum(1 for p in parts if p.entrega_informada_em)

    # Etapa 8: avaliaram
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

    # Calcula % vs topo do funil e vs etapa anterior
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


# --- Moderacao de pedidos das lanchonetes ---
@admin_bp.route("/rodadas/<int:rodada_id>/moderar-pedidos", methods=["GET", "POST"])
@login_required
@admin_required
def moderar_pedidos(rodada_id):
    """Admin aprova/devolve/reprova pedidos enviados pelas lanchonetes."""
    rodada = Rodada.query.get_or_404(rodada_id)

    if request.method == "POST":
        participacao_id = request.form.get("participacao_id", type=int)
        acao = request.form.get("acao")
        motivo = request.form.get("motivo", "").strip() or None

        part = ParticipacaoRodada.query.get(participacao_id)
        if not part or part.rodada_id != rodada_id:
            flash("Participacao nao encontrada.", "error")
            return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))

        nome_lanchonete = part.lanchonete.nome_fantasia if part.lanchonete else f"#{part.lanchonete_id}"

        if acao == "aprovar":
            part.pedido_aprovado_em = datetime.utcnow()
            part.pedido_aprovado_por_id = current_user.id
            part.pedido_devolvido_em = None
            part.pedido_reprovado_em = None
            flash(f"Pedido de {nome_lanchonete} aprovado.", "success")
        elif acao == "devolver":
            part.pedido_devolvido_em = datetime.utcnow()
            part.pedido_motivo_devolucao = motivo
            part.pedido_enviado_em = None  # lanchonete precisa reenviar
            part.pedido_aprovado_em = None
            flash(f"Pedido de {nome_lanchonete} devolvido a lanchonete.", "success")
        elif acao == "reprovar":
            part.pedido_reprovado_em = datetime.utcnow()
            part.pedido_aprovado_em = None
            flash(f"Pedido de {nome_lanchonete} reprovado.", "warning")
        elif acao == "reverter":
            # Reverte aprovacao (volta pra estado 'enviado')
            part.pedido_aprovado_em = None
            part.pedido_aprovado_por_id = None
            flash(f"Aprovacao de {nome_lanchonete} revertida. Pedido voltou a aguardar moderacao.", "info")

        db.session.commit()
        return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))

    # Carrega pedidos agrupados por status
    participacoes = (
        ParticipacaoRodada.query
        .options(joinedload(ParticipacaoRodada.lanchonete))
        .filter_by(rodada_id=rodada_id)
        .filter(ParticipacaoRodada.pedido_enviado_em.isnot(None))
        .all()
    )

    enviados = [p for p in participacoes
                if p.pedido_aprovado_em is None and p.pedido_reprovado_em is None]
    aprovados = [p for p in participacoes if p.pedido_aprovado_em is not None]
    reprovados = [p for p in participacoes if p.pedido_reprovado_em is not None]

    # Itens de cada pedido
    itens_por_participacao = {}
    for p in participacoes:
        itens_por_participacao[p.id] = (
            ItemPedido.query
            .options(joinedload(ItemPedido.produto))
            .filter_by(rodada_id=rodada_id, lanchonete_id=p.lanchonete_id)
            .all()
        )

    return render_template(
        "admin/moderar_pedidos.html",
        rodada=rodada,
        enviados=enviados,
        aprovados=aprovados,
        reprovados=reprovados,
        itens_por_participacao=itens_por_participacao,
    )


# --- Historico de produtos sugeridos/aprovados por fornecedores ---
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

    # Exportar CSV
    if request.args.get("exportar") == "csv":
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["Data", "Rodada", "Produto", "Categoria", "Subcategoria",
                    "Unidade", "Preco de partida (R$)", "Fornecedor", "Status"])
        for rp, p, r, f in registros:
            status = "Pendente" if rp.aprovado is None else ("Aprovado" if rp.aprovado else "Recusado")
            w.writerow([
                rp.criado_em.strftime("%d/%m/%Y %H:%M") if rp.criado_em else "",
                r.nome, p.nome, p.categoria, p.subcategoria or "",
                p.unidade,
                f"{float(rp.preco_partida):.2f}".replace(".", ",") if rp.preco_partida else "",
                f.razao_social, status,
            ])
        return Response(
            "\ufeff" + buf.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=historico_aprovacoes.csv"},
        )

    return render_template("admin/historico_aprovacoes.html", registros=registros)


# --- Relatorio consolidado por periodo ---
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

    # Rodadas no periodo
    rodadas = (
        Rodada.query
        .filter(Rodada.data_abertura >= dt_de, Rodada.data_abertura <= dt_ate)
        .order_by(Rodada.data_abertura.desc())
        .all()
    )
    rod_ids = [r.id for r in rodadas]

    # Totais
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
        from app.services.csv_export import csv_response
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


def _csv_response(filename: str, headers: list, rows: list) -> Response:
    buf = StringIO()
    # BOM para Excel reconhecer como UTF-8 (evita acento quebrado no Windows)
    buf.write("\ufeff")
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

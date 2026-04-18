import csv
from io import StringIO
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func
from app import db
from app.models import (
    Produto, Rodada, Fornecedor, Lanchonete,
    ParticipacaoRodada, AvaliacaoRodada, ItemPedido, Cotacao,
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


@admin_bp.route("/produtos/novo", methods=["GET", "POST"])
@login_required
@admin_required
def produto_novo():
    if request.method == "POST":
        produto = Produto(
            nome=request.form["nome"].strip(),
            descricao=request.form.get("descricao", "").strip(),
            categoria=request.form["categoria"].strip(),
            unidade=request.form["unidade"].strip(),
        )
        db.session.add(produto)
        db.session.commit()
        flash("Produto cadastrado!", "success")
        return redirect(url_for("admin.produtos"))

    return render_template("admin/produto_form.html", produto=None)


@admin_bp.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def produto_editar(produto_id):
    produto = Produto.query.get_or_404(produto_id)

    if request.method == "POST":
        produto.nome = request.form["nome"].strip()
        produto.descricao = request.form.get("descricao", "").strip()
        produto.categoria = request.form["categoria"].strip()
        produto.unidade = request.form["unidade"].strip()
        produto.ativo = "ativo" in request.form
        db.session.commit()
        flash("Produto atualizado!", "success")
        return redirect(url_for("admin.produtos"))

    return render_template("admin/produto_form.html", produto=produto)


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
        )
        db.session.add(rodada)
        db.session.commit()
        flash("Rodada criada!", "success")
        return redirect(url_for("rodadas.listar"))

    return render_template("admin/rodada_form.html")


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
    lista = Produto.query.order_by(Produto.categoria, Produto.nome).all()
    return _csv_response(
        filename="produtos.csv",
        headers=["id", "nome", "categoria", "unidade", "descricao", "ativo", "criado_em"],
        rows=[
            [p.id, p.nome, p.categoria, p.unidade, p.descricao or "",
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

    # Demanda agregada
    demanda = (
        db.session.query(
            Produto.nome,
            Produto.categoria,
            Produto.unidade,
            func.sum(ItemPedido.quantidade).label("total_pedido"),
            func.count(func.distinct(ItemPedido.lanchonete_id)).label("qtd_lanchonetes"),
        )
        .join(ItemPedido, ItemPedido.produto_id == Produto.id)
        .filter(ItemPedido.rodada_id == rodada_id)
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

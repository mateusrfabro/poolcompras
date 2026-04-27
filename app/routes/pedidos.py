from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, contains_eager
from app import db
from app.models import Produto, Rodada, ItemPedido, RodadaProduto, ParticipacaoRodada
from app.services.csv_export import csv_response
from app.services.rodada_corrente import rodada_corrente_aberta

pedidos_bp = Blueprint("pedidos", __name__, url_prefix="/pedidos")


@pedidos_bp.route("/")
@login_required
def listar():
    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro primeiro.", "error")
        return redirect(url_for("main.dashboard"))

    rodada_aberta = rodada_corrente_aberta()
    meus_pedidos = []
    if rodada_aberta:
        meus_pedidos = (
            ItemPedido.query
            .filter_by(rodada_id=rodada_aberta.id, lanchonete_id=lanchonete.id)
            .all()
        )

    return render_template(
        "pedidos/listar.html",
        rodada=rodada_aberta,
        pedidos=meus_pedidos,
    )


@pedidos_bp.route("/exportar.csv")
@login_required
def exportar():
    """Exporta os pedidos da lanchonete na rodada aberta."""
    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro primeiro.", "error")
        return redirect(url_for("pedidos.listar"))
    rodada = rodada_corrente_aberta()
    if not rodada:
        flash("Nenhuma rodada aberta.", "warning")
        return redirect(url_for("pedidos.listar"))
    itens = (
        ItemPedido.query
        .options(joinedload(ItemPedido.produto))
        .filter_by(rodada_id=rodada.id, lanchonete_id=lanchonete.id)
        .all()
    )
    return csv_response(
        filename=f"meus_pedidos_{rodada.nome.replace(' ', '_')}.csv",
        headers=["produto", "categoria", "quantidade", "unidade", "observacao"],
        rows=[
            [i.produto.nome, i.produto.categoria, str(i.quantidade),
             i.produto.unidade, i.observacao or ""]
            for i in itens
        ],
    )


@pedidos_bp.route("/catalogo", methods=["GET", "POST"])
@login_required
def catalogo():
    """Tela nova: lista o catalogo da rodada aberta com preco de partida,
    lanchonete marca quantidade de cada item (pode ser 0)."""
    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro.", "error")
        return redirect(url_for("main.dashboard"))

    rodada = rodada_corrente_aberta()
    if not rodada:
        flash("Nenhuma rodada aberta no momento.", "warning")
        return redirect(url_for("pedidos.listar"))

    # Carrega catalogo da rodada (apenas aprovados ou do admin).
    # contains_eager popula rp.produto com o mesmo join — sem N+1 no loop abaixo.
    catalogo = (
        RodadaProduto.query
        .filter_by(rodada_id=rodada.id)
        .filter((RodadaProduto.aprovado.is_(None))
                | (RodadaProduto.aprovado.is_(True)))
        .join(Produto)
        .options(contains_eager(RodadaProduto.produto))
        .order_by(Produto.categoria, Produto.subcategoria, Produto.nome)
        .all()
    )

    # ParticipacaoRodada da lanchonete (pra saber status do pedido)
    participacao = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada.id, lanchonete_id=lanchonete.id,
    ).first()

    # Bloqueia edicao se pedido ja esta aprovado ou reprovado
    pedido_bloqueado = participacao and (
        participacao.pedido_aprovado_em is not None or
        participacao.pedido_reprovado_em is not None
    )

    if request.method == "POST":
        if pedido_bloqueado:
            flash("Pedido ja foi moderado pelo admin e nao pode mais ser editado.", "error")
            return redirect(url_for("pedidos.catalogo"))

        acao = request.form.get("acao", "salvar")
        count_add = 0
        count_upd = 0
        count_del = 0
        # Pre-carrega TODOS itens existentes em 1 query (evita N+1 no loop).
        itens_existentes = {
            i.produto_id: i for i in ItemPedido.query.filter_by(
                rodada_id=rodada.id, lanchonete_id=lanchonete.id,
            ).all()
        }
        for rp in catalogo:
            qtd_str = request.form.get(f"qtd_{rp.produto_id}", "").strip()
            try:
                qtd = float(qtd_str.replace(",", ".")) if qtd_str else 0
            except ValueError:
                qtd = 0

            existente = itens_existentes.get(rp.produto_id)

            if qtd > 0:
                if existente:
                    existente.quantidade = qtd
                    count_upd += 1
                else:
                    db.session.add(ItemPedido(
                        rodada_id=rodada.id,
                        lanchonete_id=lanchonete.id,
                        produto_id=rp.produto_id,
                        quantidade=qtd,
                    ))
                    count_add += 1
            elif existente:
                db.session.delete(existente)
                count_del += 1

        # Garante ParticipacaoRodada (cria no primeiro save)
        if not participacao:
            participacao = ParticipacaoRodada(
                rodada_id=rodada.id,
                lanchonete_id=lanchonete.id,
            )
            db.session.add(participacao)
            db.session.flush()

        if acao == "enviar":
            # Exige pelo menos 1 item no pedido
            total_itens = ItemPedido.query.filter_by(
                rodada_id=rodada.id, lanchonete_id=lanchonete.id,
            ).count() + count_add - count_del
            if total_itens <= 0:
                db.session.rollback()
                flash("Voce precisa escolher ao menos 1 item antes de enviar o pedido.", "error")
                return redirect(url_for("pedidos.catalogo"))

            participacao.pedido_enviado_em = datetime.now(timezone.utc)
            # Se estava devolvido, limpa pra nova avaliacao
            participacao.pedido_devolvido_em = None
            participacao.pedido_motivo_devolucao = None
            db.session.commit()
            flash("Pedido enviado para aprovacao do admin.", "success")
            return redirect(url_for("main.dashboard"))

        # Acao = salvar (rascunho)
        db.session.commit()
        flash(
            f"Pedido salvo (rascunho). {count_add} novos, {count_upd} atualizados, {count_del} removidos. "
            "Clique em 'Enviar pedido' quando quiser submeter para o admin.",
            "success",
        )
        return redirect(url_for("pedidos.catalogo"))

    # Meus pedidos atuais (pra preencher inputs)
    meus_pedidos = {
        ip.produto_id: float(ip.quantidade)
        for ip in ItemPedido.query.filter_by(
            rodada_id=rodada.id, lanchonete_id=lanchonete.id,
        ).all()
    }

    # Agrupa por categoria -> subcategoria
    by_cat = {}
    for rp in catalogo:
        cat = rp.produto.categoria
        sub = rp.produto.subcategoria or "—"
        by_cat.setdefault(cat, {}).setdefault(sub, []).append(rp)

    # Listas pra filtro
    categorias = sorted(by_cat.keys())

    # QuickWin: ultima rodada em que a lanchonete pediu algo (pra "Meu pedido usual")
    # So oferece se nao tem itens salvos ainda na rodada atual (senao vira ruido)
    ultima_rodada_pedido = None
    if not pedido_bloqueado and not meus_pedidos:
        ultima_rodada_pedido = (
            db.session.query(Rodada)
            .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
            .filter(ItemPedido.lanchonete_id == lanchonete.id)
            .filter(ItemPedido.rodada_id != rodada.id)
            .group_by(Rodada.id)
            .order_by(Rodada.data_abertura.desc())
            .first()
        )

    return render_template(
        "pedidos/catalogo.html",
        rodada=rodada,
        catalogo_por_cat=by_cat,
        meus_pedidos=meus_pedidos,
        categorias=categorias,
        total_itens=len(meus_pedidos),
        participacao=participacao,
        pedido_bloqueado=pedido_bloqueado,
        ultima_rodada_pedido=ultima_rodada_pedido,
    )


@pedidos_bp.route("/repetir-ultimo-pedido", methods=["POST"])
@login_required
def repetir_ultimo_pedido():
    """Copia itens da ultima rodada participada pra rodada aberta atual.
    Nao duplica: se produto ja existe na rodada atual, ignora (nao sobrescreve)."""
    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro.", "error")
        return redirect(url_for("main.dashboard"))

    rodada = rodada_corrente_aberta()
    if not rodada:
        flash("Nenhuma rodada aberta.", "warning")
        return redirect(url_for("pedidos.listar"))

    # Verifica bloqueio
    participacao = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada.id, lanchonete_id=lanchonete.id,
    ).first()
    if participacao and (participacao.pedido_aprovado_em or participacao.pedido_reprovado_em):
        flash("Pedido ja foi moderado e nao pode mais ser editado.", "error")
        return redirect(url_for("pedidos.catalogo"))

    # Ultima rodada da lanchonete
    ultima = (
        db.session.query(Rodada)
        .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
        .filter(ItemPedido.lanchonete_id == lanchonete.id)
        .filter(ItemPedido.rodada_id != rodada.id)
        .group_by(Rodada.id)
        .order_by(Rodada.data_abertura.desc())
        .first()
    )
    if not ultima:
        flash("Voce ainda nao tem pedido anterior pra copiar.", "warning")
        return redirect(url_for("pedidos.catalogo"))

    # Produtos disponiveis no catalogo atual
    catalogo_atual_ids = {
        rp.produto_id for rp in RodadaProduto.query
        .filter_by(rodada_id=rodada.id)
        .filter((RodadaProduto.aprovado.is_(None))
                | (RodadaProduto.aprovado.is_(True)))
        .all()
    }

    itens_anteriores = ItemPedido.query.filter_by(
        rodada_id=ultima.id, lanchonete_id=lanchonete.id,
    ).all()

    # Itens ja salvos na rodada atual
    itens_atuais = {
        ip.produto_id: ip for ip in ItemPedido.query.filter_by(
            rodada_id=rodada.id, lanchonete_id=lanchonete.id,
        ).all()
    }

    count_add = 0
    count_skip_fora_catalogo = 0
    count_skip_ja_existe = 0
    for item in itens_anteriores:
        if item.produto_id not in catalogo_atual_ids:
            count_skip_fora_catalogo += 1
            continue
        if item.produto_id in itens_atuais:
            count_skip_ja_existe += 1
            continue
        db.session.add(ItemPedido(
            rodada_id=rodada.id,
            lanchonete_id=lanchonete.id,
            produto_id=item.produto_id,
            quantidade=item.quantidade,
        ))
        count_add += 1

    db.session.commit()
    msg = f"Copiei {count_add} item(ns) da rodada anterior '{ultima.nome}'."
    if count_skip_fora_catalogo:
        msg += f" {count_skip_fora_catalogo} item(ns) fora do catalogo atual foram ignorados."
    if count_skip_ja_existe:
        msg += f" {count_skip_ja_existe} item(ns) ja estavam no pedido atual (nao sobrescrevi)."
    flash(msg, "success")
    return redirect(url_for("pedidos.catalogo"))


@pedidos_bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    """Rota legada — redireciona pra novo catalogo da rodada."""
    return redirect(url_for("pedidos.catalogo"))


@pedidos_bp.route("/remover/<int:item_id>", methods=["POST"])
@login_required
def remover(item_id):
    item = db.session.get(ItemPedido, item_id)
    if item is None:
        flash("Este item não existe mais (pode ter sido removido em outra sessão).", "warning")
        return redirect(url_for("pedidos.listar"))
    lanchonete = current_user.lanchonete

    if item.lanchonete_id != lanchonete.id:
        flash("Você não pode remover este item.", "error")
        return redirect(url_for("pedidos.listar"))

    if item.rodada.status != "aberta":
        flash("Esta rodada já foi fechada.", "error")
        return redirect(url_for("pedidos.listar"))

    db.session.delete(item)
    db.session.commit()
    flash("Item removido do pedido.", "success")
    return redirect(url_for("pedidos.listar"))

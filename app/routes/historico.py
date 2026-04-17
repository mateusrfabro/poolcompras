"""
Historico de rodadas da lanchonete logada.
Lista as rodadas em que a lanchonete participou (com status e contagem
de produtos). Detalhe expandido fica em template separado.
"""
from collections import defaultdict
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app import db
from app.models import (
    Rodada, ItemPedido, Cotacao, Produto, Lanchonete, Fornecedor,
    ParticipacaoRodada, EventoRodada, AvaliacaoRodada,
)
from app.services.csv_export import csv_response

historico_bp = Blueprint("historico", __name__, url_prefix="/minhas-rodadas")


# Status que aparecem na aba Historico (nao queremos mostrar so "aberta" aqui)
STATUS_HISTORICO = ("finalizada", "cancelada", "fechada", "cotando")


@historico_bp.route("/")
@login_required
def listar():
    """Listagem de rodadas em que a lanchonete logada participou."""
    if current_user.is_admin or current_user.is_fornecedor:
        flash("Esta área é apenas para lanchonetes.", "warning")
        return redirect(url_for("main.dashboard"))

    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro primeiro.", "error")
        return redirect(url_for("main.dashboard"))

    # Filtro de status (default: todas)
    filtro_status = request.args.get("status", "todas")

    # Subquery: rodadas em que essa lanchonete teve pedidos
    rodadas_q = (
        db.session.query(
            Rodada,
            func.count(ItemPedido.id).label("qtd_itens"),
            func.count(func.distinct(ItemPedido.produto_id)).label("qtd_produtos"),
        )
        .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
        .filter(ItemPedido.lanchonete_id == lanchonete.id)
        .group_by(Rodada.id)
        .order_by(Rodada.data_abertura.desc())
    )

    # Nota dada pela lanchonete por rodada (map id->estrelas)
    notas_map = dict(
        db.session.query(ParticipacaoRodada.rodada_id,
                         ParticipacaoRodada.avaliacao_geral)
        .filter(ParticipacaoRodada.lanchonete_id == lanchonete.id,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .all()
    )

    if filtro_status == "todas":
        # Mostra todas em que ela participou (inclui aberta tambem)
        pass
    elif filtro_status in STATUS_HISTORICO:
        rodadas_q = rodadas_q.filter(Rodada.status == filtro_status)
    elif filtro_status == "aberta":
        rodadas_q = rodadas_q.filter(Rodada.status == "aberta")

    rodadas = rodadas_q.all()

    # Conta totais p/ filtros (badges) — DISTINCT pra contar RODADAS, nao itens
    contagem = dict(
        db.session.query(Rodada.status, func.count(func.distinct(Rodada.id)))
        .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
        .filter(ItemPedido.lanchonete_id == lanchonete.id)
        .group_by(Rodada.status)
        .all()
    )
    contagem["todas"] = sum(contagem.values())

    return render_template(
        "historico/listar.html",
        rodadas=rodadas,
        filtro_status=filtro_status,
        contagem=contagem,
        lanchonete=lanchonete,
        notas_map=notas_map,
    )


@historico_bp.route("/exportar.csv")
@login_required
def exportar():
    """Exporta histórico de rodadas da lanchonete logada."""
    if current_user.is_admin or current_user.is_fornecedor:
        flash("Esta área é apenas para lanchonetes.", "warning")
        return redirect(url_for("main.dashboard"))
    lanchonete = current_user.lanchonete
    if not lanchonete:
        return redirect(url_for("main.dashboard"))

    rodadas = (
        db.session.query(
            Rodada,
            func.count(ItemPedido.id).label("qtd_itens"),
        )
        .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
        .filter(ItemPedido.lanchonete_id == lanchonete.id)
        .group_by(Rodada.id)
        .order_by(Rodada.data_abertura.desc())
        .all()
    )
    notas = dict(
        db.session.query(ParticipacaoRodada.rodada_id, ParticipacaoRodada.avaliacao_geral)
        .filter(ParticipacaoRodada.lanchonete_id == lanchonete.id,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .all()
    )
    return csv_response(
        filename=f"minhas_rodadas_{lanchonete.nome_fantasia.replace(' ', '_')}.csv",
        headers=["rodada", "data", "status", "itens_pedidos", "avaliacao"],
        rows=[
            [r.nome, r.data_abertura.strftime("%Y-%m-%d"), r.status,
             str(qtd), str(notas.get(r.id, ""))]
            for r, qtd in rodadas
        ],
    )


@historico_bp.route("/<int:rodada_id>")
@login_required
def detalhe(rodada_id):
    """Detalhe expandido de uma rodada da lanchonete logada."""
    if current_user.is_admin or current_user.is_fornecedor:
        flash("Esta área é apenas para lanchonetes.", "warning")
        return redirect(url_for("main.dashboard"))

    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro primeiro.", "error")
        return redirect(url_for("main.dashboard"))

    rodada = Rodada.query.get_or_404(rodada_id)

    # Garante que a lanchonete participou desta rodada
    participou = (
        ItemPedido.query
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete.id)
        .first()
    )
    if not participou:
        flash("Você não participou desta rodada.", "warning")
        return redirect(url_for("historico.listar"))

    # Itens da lanchonete nesta rodada (com produto, joinedload p/ evitar N+1 no loop)
    meus_itens = (
        ItemPedido.query
        .options(joinedload(ItemPedido.produto))
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete.id)
        .join(Produto, ItemPedido.produto_id == Produto.id)
        .order_by(Produto.categoria, Produto.nome)
        .all()
    )

    # Fix N+1: carrega TODAS as cotacoes da rodada em 1 query (com fornecedor) e agrupa
    cotacoes_por_produto = defaultdict(list)
    cotacoes_rodada = (
        Cotacao.query
        .options(joinedload(Cotacao.fornecedor))
        .filter_by(rodada_id=rodada_id)
        .all()
    )
    for c in cotacoes_rodada:
        cotacoes_por_produto[c.produto_id].append(c)

    # Monta detalhe de cada item com lookup O(1)
    itens_detalhe = []
    for item in meus_itens:
        cots = cotacoes_por_produto.get(item.produto_id, [])
        if cots:
            preco_partida = max(c.preco_unitario for c in cots)
            preco_final = min(c.preco_unitario for c in cots)
            forn_vencedor = next((c.fornecedor for c in cots if c.selecionada), None)
        else:
            preco_partida = preco_final = None
            forn_vencedor = None

        itens_detalhe.append({
            "item": item,
            "produto": item.produto,
            "quantidade": item.quantidade,
            "preco_partida": preco_partida,
            "preco_final": preco_final,
            "fornecedor": forn_vencedor,
            "subtotal": (preco_final * item.quantidade) if preco_final else None,
        })

    total_estimado = sum(i["subtotal"] for i in itens_detalhe if i["subtotal"]) or 0
    total_partida = sum(
        (i["preco_partida"] or 0) * i["quantidade"] for i in itens_detalhe
    )
    economia = total_partida - total_estimado if total_partida and total_estimado else 0

    # Break-down por fornecedor vencedor: valor a pagar + dados bancarios
    pagamento_por_fornecedor = {}
    for i in itens_detalhe:
        forn = i.get("fornecedor")
        if forn and i.get("subtotal"):
            if forn.id not in pagamento_por_fornecedor:
                pagamento_por_fornecedor[forn.id] = {
                    "fornecedor": forn,
                    "total": 0,
                    "itens": [],
                }
            pagamento_por_fornecedor[forn.id]["total"] += float(i["subtotal"])
            pagamento_por_fornecedor[forn.id]["itens"].append({
                "nome": i["produto"].nome,
                "quantidade": i["quantidade"],
                "unidade": i["produto"].unidade,
                "subtotal": float(i["subtotal"]),
            })
    pagamento_por_fornecedor = list(pagamento_por_fornecedor.values())

    # Insights pra rodada finalizada
    insights = []
    if economia and total_partida:
        pct = float(economia / total_partida * 100)
        insights.append(f"Economia total de {pct:.1f}% sobre o preço de partida.")

    # Produto com maior economia (absoluta)
    itens_com_eco = [
        i for i in itens_detalhe
        if i["preco_partida"] and i["preco_final"] and i["preco_partida"] > i["preco_final"]
    ]
    if itens_com_eco:
        top = max(itens_com_eco,
                  key=lambda i: (i["preco_partida"] - i["preco_final"]) * i["quantidade"])
        eco_top = (top["preco_partida"] - top["preco_final"]) * top["quantidade"]
        insights.append(
            f"Maior economia nesta rodada: {top['produto'].nome} "
            f"(você economizou R$ {float(eco_top):,.2f} nesse item)."
            .replace(",", "X").replace(".", ",").replace("X", ".")
        )

    # Fornecedor mais presente (venceu mais cotações)
    forn_contagem = defaultdict(int)
    for i in itens_detalhe:
        if i.get("fornecedor"):
            forn_contagem[i["fornecedor"].razao_social] += 1
    if forn_contagem:
        top_forn = max(forn_contagem, key=forn_contagem.get)
        insights.append(f"Fornecedor destaque: {top_forn} (venceu {forn_contagem[top_forn]} produtos).")

    # Fase 2: participacao da lanchonete + eventos da timeline
    participacao = (
        ParticipacaoRodada.query
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete.id)
        .first()
    )

    # Eventos da rodada filtrados para esta lanchonete (inclui eventos globais lanchonete_id=NULL)
    eventos = (
        EventoRodada.query
        .options(joinedload(EventoRodada.ator))
        .filter(EventoRodada.rodada_id == rodada_id)
        .filter(
            (EventoRodada.lanchonete_id == lanchonete.id)
            | (EventoRodada.lanchonete_id.is_(None))
        )
        .order_by(EventoRodada.criado_em.asc())
        .all()
    )

    # Monta as fases da timeline com status derivado da participacao (ordem canonica)
    fases = _montar_fases_timeline(participacao, rodada)

    return render_template(
        "historico/detalhe.html",
        rodada=rodada,
        lanchonete=lanchonete,
        itens=itens_detalhe,
        total_estimado=total_estimado,
        total_partida=total_partida,
        economia=economia,
        participacao=participacao,
        eventos=eventos,
        fases=fases,
        insights=insights,
        media_geral=_media_geral_rodada(rodada_id),
        pagamento_por_fornecedor=pagamento_por_fornecedor,
    )


def _media_geral_rodada(rodada_id):
    """Media de avaliacao de TODAS as lanchonetes nesta rodada."""
    media = (
        db.session.query(func.avg(ParticipacaoRodada.avaliacao_geral))
        .filter(ParticipacaoRodada.rodada_id == rodada_id,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .scalar()
    )
    return round(float(media), 1) if media else None


def _montar_fases_timeline(participacao, rodada):
    """Deriva o estado das 6 fases do fluxo a partir da ParticipacaoRodada.

    Retorna lista de dicts {icone, status, titulo, descricao, data} onde:
      status = 'ok' (verde ✓) | 'problema' (vermelho ✗) | 'pendente' (cinza —)
    """
    if not participacao:
        # Rodada aberta ou cancelada sem participacao registrada: tudo pendente
        return []

    def _fmt(dt):
        return dt.strftime("%d/%m/%Y às %H:%M") if dt else None

    fases = []

    # 1. Aceite da proposta
    if participacao.aceite_proposta is True:
        fases.append({"status": "ok", "titulo": "Proposta aceita",
                      "descricao": "Você aceitou a proposta final consolidada.",
                      "data": _fmt(participacao.aceite_em)})
    elif participacao.aceite_proposta is False:
        fases.append({"status": "problema", "titulo": "Proposta recusada",
                      "descricao": "Você recusou a proposta final.",
                      "data": _fmt(participacao.aceite_em)})
    else:
        fases.append({"status": "pendente", "titulo": "Aguardando aceite",
                      "descricao": "Proposta final ainda não foi aceita.", "data": None})

    # 2. Comprovante
    if participacao.comprovante_key:
        fases.append({"status": "ok", "titulo": "Comprovante enviado",
                      "descricao": "Comprovante de pagamento carregado.",
                      "data": _fmt(participacao.comprovante_em)})
    else:
        fases.append({"status": "pendente", "titulo": "Aguardando comprovante",
                      "descricao": "Envio do comprovante de pagamento.", "data": None})

    # 3. Pagamento confirmado pelo fornecedor
    if participacao.pagamento_confirmado_em:
        fases.append({"status": "ok", "titulo": "Pagamento confirmado",
                      "descricao": "Fornecedor confirmou o recebimento do pagamento.",
                      "data": _fmt(participacao.pagamento_confirmado_em)})
    else:
        fases.append({"status": "pendente", "titulo": "Aguardando confirmação do fornecedor",
                      "descricao": "Fornecedor ainda não confirmou o pagamento.", "data": None})

    # 4. Entrega informada
    if participacao.entrega_informada_em:
        desc = "Entregue em " + participacao.entrega_data.strftime("%d/%m/%Y") if participacao.entrega_data else "Entrega informada."
        fases.append({"status": "ok", "titulo": "Entrega informada",
                      "descricao": desc, "data": _fmt(participacao.entrega_informada_em)})
    else:
        fases.append({"status": "pendente", "titulo": "Aguardando entrega",
                      "descricao": "Fornecedor ainda não informou a entrega.", "data": None})

    # 5. Recebimento confirmado pelo cliente
    if participacao.recebimento_ok is True:
        fases.append({"status": "ok", "titulo": "Recebimento confirmado",
                      "descricao": "Você confirmou o recebimento sem problemas.",
                      "data": _fmt(participacao.recebimento_em)})
    elif participacao.recebimento_ok is False:
        fases.append({"status": "problema", "titulo": "Problema no recebimento",
                      "descricao": participacao.recebimento_observacao or "Problema reportado.",
                      "data": _fmt(participacao.recebimento_em)})
    else:
        fases.append({"status": "pendente", "titulo": "Aguardando confirmação de recebimento",
                      "descricao": "Cliente ainda não confirmou o recebimento.", "data": None})

    # 6. Avaliacao
    if participacao.avaliacao_geral:
        fases.append({"status": "ok", "titulo": f"Rodada avaliada",
                      "descricao": f"Você deu {participacao.avaliacao_geral} estrela(s).",
                      "data": _fmt(participacao.avaliacao_em)})
    else:
        fases.append({"status": "pendente", "titulo": "Aguardando avaliação",
                      "descricao": "Você ainda não avaliou esta rodada.", "data": None})

    return fases


# ---------- Analytics da lanchonete ----------

@historico_bp.route("/analytics")
@login_required
def analytics():
    """Dashboard de KPIs pessoais da lanchonete logada."""
    if current_user.is_admin or current_user.is_fornecedor:
        flash("Esta área é apenas para lanchonetes.", "warning")
        return redirect(url_for("main.dashboard"))

    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro primeiro.", "error")
        return redirect(url_for("main.dashboard"))

    lid = lanchonete.id

    # Contagens basicas
    total_rodadas = (
        db.session.query(func.count(func.distinct(ItemPedido.rodada_id)))
        .filter(ItemPedido.lanchonete_id == lid)
        .scalar()
    ) or 0

    rodadas_avaliadas = (
        ParticipacaoRodada.query
        .filter_by(lanchonete_id=lid)
        .filter(ParticipacaoRodada.avaliacao_geral.isnot(None))
        .count()
    )

    total_itens_pedidos = (
        ItemPedido.query.filter_by(lanchonete_id=lid).count()
    )

    # Média de avaliação que a lanchonete deu
    minha_media = (
        db.session.query(func.avg(ParticipacaoRodada.avaliacao_geral))
        .filter(ParticipacaoRodada.lanchonete_id == lid,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .scalar()
    ) or 0

    # Produtos mais pedidos pela lanchonete (top 5)
    meus_top_produtos = (
        db.session.query(
            Produto.nome, Produto.unidade,
            func.sum(ItemPedido.quantidade).label("total"),
        )
        .join(ItemPedido, ItemPedido.produto_id == Produto.id)
        .filter(ItemPedido.lanchonete_id == lid)
        .group_by(Produto.id)
        .order_by(func.sum(ItemPedido.quantidade).desc())
        .limit(5)
        .all()
    )

    # Ranking de fornecedores que a lanchonete avaliou (media das notas que ELA deu)
    meus_fornecedores = (
        db.session.query(
            Fornecedor.razao_social,
            func.avg(AvaliacaoRodada.estrelas).label("media"),
            func.count(AvaliacaoRodada.id).label("avaliacoes"),
        )
        .join(AvaliacaoRodada, AvaliacaoRodada.fornecedor_id == Fornecedor.id)
        .filter(AvaliacaoRodada.lanchonete_id == lid)
        .group_by(Fornecedor.id)
        .order_by(func.avg(AvaliacaoRodada.estrelas).desc())
        .all()
    )

    # Historico de notas por rodada (pra mini grafico textual)
    historico_notas = (
        db.session.query(
            Rodada.nome,
            ParticipacaoRodada.avaliacao_geral,
        )
        .join(ParticipacaoRodada, ParticipacaoRodada.rodada_id == Rodada.id)
        .filter(ParticipacaoRodada.lanchonete_id == lid,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .order_by(Rodada.data_abertura.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "historico/analytics.html",
        lanchonete=lanchonete,
        total_rodadas=total_rodadas,
        rodadas_avaliadas=rodadas_avaliadas,
        total_itens_pedidos=total_itens_pedidos,
        minha_media=round(float(minha_media), 1),
        meus_top_produtos=meus_top_produtos,
        meus_fornecedores=meus_fornecedores,
        historico_notas=historico_notas,
    )
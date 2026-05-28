"""Detalhe expandido de 1 rodada da lanchonete logada.

Inclui itens, precos (partida x final), economia, timeline de fases (aceite,
comprovante, pagamento, entrega, recebimento, avaliacao), insights automaticos
e break-down de pagamento por fornecedor.
"""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Rodada, ItemPedido, Cotacao, Produto, RodadaProduto,
    ParticipacaoRodada, EventoRodada, SubmissaoCotacao,
)
from . import historico_bp, lanchonete_required


_ZERO = Decimal("0")
_CENT = Decimal("0.01")


def _to_dec(v):
    """Converte qualquer numerico pra Decimal preservando precisao."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _q2(v):
    """Quantize pra centavos (None passa). Mantem Decimal — |brl aceita."""
    if v is None:
        return None
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


@historico_bp.route("/<int:rodada_id>")
@login_required
@lanchonete_required
def detalhe(rodada_id):
    """Detalhe expandido de uma rodada da lanchonete logada."""
    lanchonete = current_user.lanchonete
    rodada = db.get_or_404(Rodada, rodada_id)

    participou = (
        ItemPedido.query
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete.id)
        .first()
    )
    if not participou:
        flash("Você não participou desta rodada.", "warning")
        return redirect(url_for("historico.listar"))

    meus_itens = (
        ItemPedido.query
        .options(joinedload(ItemPedido.produto))
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete.id)
        .join(Produto, ItemPedido.produto_id == Produto.id)
        .order_by(Produto.categoria, Produto.nome)
        .all()
    )

    # Fix N+1: 1 query por categoria de dados.
    # Perf: filtra cotacoes pelos produtos QUE A LANCHONETE PEDIU — sem
    # esse filtro, rodadas grandes (50+ produtos) trazem 80%+ rows que
    # nem entram no loop abaixo.
    meus_produto_ids = [i.produto_id for i in meus_itens]
    cotacoes_por_produto = defaultdict(list)
    if meus_produto_ids:
        cotacoes_rodada = (
            Cotacao.query
            .options(joinedload(Cotacao.fornecedor))
            .filter_by(rodada_id=rodada_id)
            .filter(Cotacao.produto_id.in_(meus_produto_ids))
            .all()
        )
        for c in cotacoes_rodada:
            cotacoes_por_produto[c.produto_id].append(c)

    partidas_por_produto = {
        rp.produto_id: _to_dec(rp.preco_partida) if rp.preco_partida else None
        for rp in RodadaProduto.query.filter_by(rodada_id=rodada_id).all()
    }

    # Monta detalhe de cada item com lookup O(1)
    # preco_partida = RodadaProduto.preco_partida (preco de referencia, fase 1)
    # preco_final = menor cotacao final (vencedora) OU cotacao selecionada se existir
    # Aritmetica monetaria em Decimal — float acumula drift em totais.
    itens_detalhe = []
    for item in meus_itens:
        cots = cotacoes_por_produto.get(item.produto_id, [])
        preco_partida = partidas_por_produto.get(item.produto_id)
        if cots:
            selecionada = next((c for c in cots if c.selecionada), None)
            if selecionada:
                preco_final = _to_dec(selecionada.preco_unitario)
                forn_vencedor = selecionada.fornecedor
            else:
                menor = min(cots, key=lambda c: c.preco_unitario)
                preco_final = _to_dec(menor.preco_unitario)
                forn_vencedor = menor.fornecedor
        else:
            preco_final = None
            forn_vencedor = None

        qtd = _to_dec(item.quantidade) or _ZERO
        itens_detalhe.append({
            "item": item,
            "produto": item.produto,
            "quantidade": qtd,
            "preco_partida": preco_partida,
            "preco_final": preco_final,
            "fornecedor": forn_vencedor,
            "subtotal": _q2(preco_final * qtd) if preco_final else None,
        })

    total_estimado = sum(
        (i["subtotal"] for i in itens_detalhe if i["subtotal"]), _ZERO
    )
    total_partida = sum(
        ((i["preco_partida"] or _ZERO) * i["quantidade"] for i in itens_detalhe),
        _ZERO,
    )
    total_partida = _q2(total_partida)
    economia = (total_partida - total_estimado) if total_partida and total_estimado else _ZERO

    # Break-down por fornecedor vencedor: valor a pagar + dados bancarios
    pagamento_por_fornecedor = {}
    for i in itens_detalhe:
        forn = i.get("fornecedor")
        if forn and i.get("subtotal"):
            if forn.id not in pagamento_por_fornecedor:
                pagamento_por_fornecedor[forn.id] = {
                    "fornecedor": forn,
                    "total": _ZERO,
                    "itens": [],
                }
            pagamento_por_fornecedor[forn.id]["total"] += i["subtotal"]
            pagamento_por_fornecedor[forn.id]["itens"].append({
                "nome": i["produto"].nome,
                "quantidade": i["quantidade"],
                "unidade": i["produto"].unidade,
                "subtotal": i["subtotal"],
            })
    for entry in pagamento_por_fornecedor.values():
        entry["total"] = _q2(entry["total"])
    pagamento_por_fornecedor = list(pagamento_por_fornecedor.values())

    # Insights pra rodada finalizada
    insights = []
    if economia and total_partida:
        pct = float((economia / total_partida * Decimal("100"))
                    .quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        insights.append(f"Economia total de {pct:.1f}% sobre o preço de partida.")

    itens_com_eco = [
        i for i in itens_detalhe
        if i["preco_partida"] and i["preco_final"] and i["preco_partida"] > i["preco_final"]
    ]
    if itens_com_eco:
        top = max(itens_com_eco,
                  key=lambda i: (i["preco_partida"] - i["preco_final"]) * i["quantidade"])
        eco_top = _q2((top["preco_partida"] - top["preco_final"]) * top["quantidade"])
        insights.append(
            f"Maior economia nesta rodada: {top['produto'].nome} "
            f"(você economizou R$ {eco_top:,.2f} nesse item)."
            .replace(",", "X").replace(".", ",").replace("X", ".")
        )

    forn_contagem = defaultdict(int)
    for i in itens_detalhe:
        if i.get("fornecedor"):
            forn_contagem[i["fornecedor"].razao_social] += 1
    if forn_contagem:
        top_forn = max(forn_contagem, key=forn_contagem.get)
        insights.append(f"Fornecedor destaque: {top_forn} (venceu {forn_contagem[top_forn]} produtos).")

    participacao = (
        ParticipacaoRodada.query
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete.id)
        .first()
    )

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

    fases = _montar_fases_timeline(participacao, rodada)

    # Proposta disponivel pra aceite: finalizada OU em_negociacao com submissao aprovada
    proposta_disponivel = rodada.status == Rodada.STATUS_FINALIZADA or (
        rodada.status == Rodada.STATUS_EM_NEGOCIACAO and
        db.session.query(SubmissaoCotacao.id).filter_by(rodada_id=rodada_id)
        .filter(SubmissaoCotacao.aprovada_em.isnot(None)).first() is not None
    )

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
        proposta_disponivel=proposta_disponivel,
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

    Retorna lista de dicts {status, titulo, descricao, data} onde:
      status = 'ok' (verde) | 'problema' (vermelho) | 'pendente' (cinza)
    """
    if not participacao:
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
        fases.append({"status": "ok", "titulo": "Rodada avaliada",
                      "descricao": f"Você deu {participacao.avaliacao_geral} estrela(s).",
                      "data": _fmt(participacao.avaliacao_em)})
    else:
        fases.append({"status": "pendente", "titulo": "Aguardando avaliação",
                      "descricao": "Você ainda não avaliou esta rodada.", "data": None})

    return fases

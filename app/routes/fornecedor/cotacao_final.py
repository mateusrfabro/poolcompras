"""Fase 2 da cotacao: preco final (com volumes reais) + envio pra aprovacao + notas."""
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import contains_eager

from app import db, limiter


def _calcular_linhas_cotacao(rodada_produtos, volumes, cotacoes_existentes):
    """Monta linhas da tabela de cotacao final + totais.

    Retorna (linhas, total_partida, total_final, economia_total_rs, economia_total_pct).
    Cada linha eh dict pronto pro template (produto, volume, partida, final, economia).
    """
    linhas = []
    total_partida = 0.0
    total_final = 0.0
    for rp in rodada_produtos:
        pid = rp.produto_id
        if pid not in volumes:
            continue
        vol = float(volumes[pid])
        partida = float(rp.preco_partida) if rp.preco_partida else None
        cot = cotacoes_existentes.get(pid)
        final = float(cot.preco_unitario) if cot else None
        economia_pct = None
        economia_rs = None
        if partida and final and partida > 0:
            economia_pct = round((partida - final) / partida * 100, 1)
            economia_rs = round((partida - final) * vol, 2)
            total_partida += partida * vol
            total_final += final * vol
        linhas.append({
            "rodada_produto": rp,
            "produto": rp.produto,
            "volume": vol,
            "partida": partida,
            "final": final,
            "economia_pct": economia_pct,
            "economia_rs": economia_rs,
        })

    economia_total_rs = round(total_partida - total_final, 2) if total_partida else 0
    economia_total_pct = (
        round((total_partida - total_final) / total_partida * 100, 1)
        if total_partida else 0
    )
    return linhas, total_partida, total_final, economia_total_rs, economia_total_pct
from app.models import (
    Rodada, ItemPedido, Cotacao, Produto,
    ParticipacaoRodada, RodadaProduto,
    SubmissaoCotacao, NotaNegociacao,
)
from . import fornecedor_bp, fornecedor_required


@fornecedor_bp.route("/rodada/<int:rodada_id>/cotacao-final", methods=["GET", "POST"])
@login_required
@fornecedor_required
def cotar_final(rodada_id):
    """Tela onde o fornecedor fecha o preco FINAL com base nos volumes reais agregados.
    Disponivel quando rodada.status == 'em_negociacao'. Mostra lado a lado:
    preco de partida, preco final (input), e economia calculada.
    """
    rodada = db.get_or_404(Rodada, rodada_id)
    if rodada.status != "em_negociacao":
        flash("Esta rodada nao esta em fase de negociacao.", "warning")
        return redirect(url_for("fornecedor.dashboard"))

    fornecedor = current_user.fornecedor
    if not fornecedor:
        flash("Complete seu cadastro.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    # Volumes agregados (SOMENTE aprovados pelo admin)
    volumes = dict(
        db.session.query(
            ItemPedido.produto_id,
            func.sum(ItemPedido.quantidade),
        )
        .join(ParticipacaoRodada,
              (ParticipacaoRodada.rodada_id == ItemPedido.rodada_id) &
              (ParticipacaoRodada.lanchonete_id == ItemPedido.lanchonete_id))
        .filter(ItemPedido.rodada_id == rodada_id)
        .filter(ParticipacaoRodada.pedido_aprovado_em.isnot(None))
        .group_by(ItemPedido.produto_id)
        .all()
    )

    rodada_produtos = (
        RodadaProduto.query
        .filter_by(rodada_id=rodada_id)
        .filter((RodadaProduto.aprovado.is_(None))
                | (RodadaProduto.aprovado.is_(True)))
        .join(Produto)
        .options(contains_eager(RodadaProduto.produto))
        .order_by(Produto.categoria, Produto.subcategoria, Produto.nome)
        .all()
    )

    cotacoes_existentes = {
        c.produto_id: c for c in Cotacao.query.filter_by(
            rodada_id=rodada_id, fornecedor_id=fornecedor.id,
        ).all()
    }

    submissao = SubmissaoCotacao.query.filter_by(
        rodada_id=rodada_id, fornecedor_id=fornecedor.id,
    ).first()
    bloqueado = bool(submissao and submissao.aprovada_em)

    if request.method == "POST":
        if bloqueado:
            flash("Cotacao ja foi aprovada pelo admin — nao eh mais editavel.", "error")
            return redirect(url_for("fornecedor.cotar_final", rodada_id=rodada_id))

        acao = request.form.get("acao", "salvar")
        count = 0
        for rp in rodada_produtos:
            pid = rp.produto_id
            if pid not in volumes:
                continue
            preco_str = request.form.get(f"preco_final_{pid}", "").strip()
            if not preco_str:
                continue
            try:
                preco_final = float(preco_str.replace(",", "."))
            except ValueError:
                continue
            if preco_final <= 0 or preco_final > 100000:
                # Rejeita zero/negativo e valores absurdos (digito errado, ataque).
                continue

            existente = cotacoes_existentes.get(pid)
            if existente:
                existente.preco_unitario = preco_final
            else:
                db.session.add(Cotacao(
                    rodada_id=rodada_id,
                    fornecedor_id=fornecedor.id,
                    produto_id=pid,
                    preco_unitario=preco_final,
                ))
            count += 1

        if not submissao:
            submissao = SubmissaoCotacao(
                rodada_id=rodada_id, fornecedor_id=fornecedor.id,
            )
            db.session.add(submissao)
            db.session.flush()

        if acao == "enviar":
            total_precos = Cotacao.query.filter_by(
                rodada_id=rodada_id, fornecedor_id=fornecedor.id,
            ).count()
            if total_precos == 0:
                db.session.rollback()
                flash("Voce precisa preencher ao menos 1 preco antes de enviar.", "error")
                return redirect(url_for("fornecedor.cotar_final", rodada_id=rodada_id))

            submissao.enviada_em = datetime.now(timezone.utc)
            submissao.devolvida_em = None
            db.session.commit()
            flash("Cotacao enviada pra aprovacao do admin.", "success")
            return redirect(url_for("fornecedor.dashboard"))

        db.session.commit()
        flash(f"Cotacao salva (rascunho). {count} preco(s). Clique em 'Enviar pra aprovacao' quando finalizar.", "success")
        return redirect(url_for("fornecedor.cotar_final", rodada_id=rodada_id))

    (linhas, total_partida, total_final,
     economia_total_rs, economia_total_pct) = _calcular_linhas_cotacao(
        rodada_produtos, volumes, cotacoes_existentes,
    )

    notas = []
    if submissao:
        notas = NotaNegociacao.query.filter_by(submissao_id=submissao.id)\
            .order_by(NotaNegociacao.criado_em.asc()).all()

    return render_template(
        "fornecedor/cotar_final.html",
        rodada=rodada,
        linhas=linhas,
        submissao=submissao,
        bloqueado=bloqueado,
        economia_total_rs=economia_total_rs,
        economia_total_pct=economia_total_pct,
        total_partida=total_partida,
        total_final=total_final,
        notas=notas,
    )


@fornecedor_bp.route("/rodada/<int:rodada_id>/cotacao-final/nota", methods=["POST"])
@login_required
@fornecedor_required
@limiter.limit("30/hour")
def adicionar_nota_negociacao(rodada_id):
    """Fornecedor adiciona nota na negociacao (permitido so se nao aprovada)."""
    fornecedor = current_user.fornecedor
    if not fornecedor:
        flash("Complete seu cadastro.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    submissao = SubmissaoCotacao.query.filter_by(
        rodada_id=rodada_id, fornecedor_id=fornecedor.id,
    ).first()
    if not submissao:
        flash("Voce ainda nao enviou cotacao pra esta rodada.", "error")
        return redirect(url_for("fornecedor.cotar_final", rodada_id=rodada_id))
    if submissao.aprovada_em:
        flash("Cotacao ja foi aprovada — sem negociacao ativa.", "warning")
        return redirect(url_for("fornecedor.cotar_final", rodada_id=rodada_id))

    texto = request.form.get("texto", "").strip()
    if not texto:
        flash("Escreva uma mensagem antes de enviar.", "warning")
        return redirect(url_for("fornecedor.cotar_final", rodada_id=rodada_id))

    db.session.add(NotaNegociacao(
        submissao_id=submissao.id,
        autor_tipo=NotaNegociacao.AUTOR_FORNECEDOR,
        autor_usuario_id=current_user.id,
        texto=texto[:1000],
    ))
    db.session.commit()
    flash("Mensagem adicionada.", "success")
    return redirect(url_for("fornecedor.cotar_final", rodada_id=rodada_id))

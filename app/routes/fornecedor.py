from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app import db
from app.models import (
    Rodada, ItemPedido, Cotacao, Produto,
    ParticipacaoRodada, Lanchonete, AvaliacaoRodada, RodadaProduto,
)

fornecedor_bp = Blueprint("fornecedor", __name__, url_prefix="/fornecedor")


def fornecedor_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_fornecedor:
            flash("Acesso restrito a fornecedores.", "error")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)

    return decorated


@fornecedor_bp.route("/dashboard")
@login_required
@fornecedor_required
def dashboard():
    fornecedor = current_user.fornecedor

    # Rodadas prontas para cotação (aguardando_cotacao=partida; em_negociacao=cotacao final; legado: fechada/cotando)
    rodadas_para_cotar = Rodada.query.filter(
        Rodada.status.in_(["aguardando_cotacao", "em_negociacao", "fechada", "cotando"])
    ).order_by(Rodada.data_fechamento.desc()).all()

    # Cotações já enviadas por este fornecedor
    minhas_cotacoes = (
        Cotacao.query
        .filter_by(fornecedor_id=fornecedor.id)
        .order_by(Cotacao.criado_em.desc())
        .limit(20)
        .all()
    ) if fornecedor else []

    # Pendencias agrupadas POR RODADA (nao por lanchonete)
    pendencias_por_rodada = []
    if fornecedor:
        rodadas_cotadas_ids = [
            r for (r,) in db.session.query(Cotacao.rodada_id)
                .filter_by(fornecedor_id=fornecedor.id)
                .distinct().all()
        ]
        if rodadas_cotadas_ids:
            participacoes = (
                ParticipacaoRodada.query
                .options(joinedload(ParticipacaoRodada.lanchonete),
                         joinedload(ParticipacaoRodada.rodada))
                .filter(ParticipacaoRodada.rodada_id.in_(rodadas_cotadas_ids))
                .filter(ParticipacaoRodada.aceite_proposta.is_(True))
                .filter(ParticipacaoRodada.comprovante_key.isnot(None))
                .filter(ParticipacaoRodada.entrega_informada_em.is_(None))
                .order_by(ParticipacaoRodada.comprovante_em.asc())
                .all()
            )
            # Agrupa por rodada
            por_rodada = {}
            for p in participacoes:
                rid = p.rodada_id
                if rid not in por_rodada:
                    por_rodada[rid] = {
                        "rodada": p.rodada,
                        "aguardando_pagamento": [],
                        "aguardando_entrega": [],
                    }
                if not p.pagamento_confirmado_em:
                    por_rodada[rid]["aguardando_pagamento"].append(p)
                elif not p.entrega_informada_em:
                    por_rodada[rid]["aguardando_entrega"].append(p)
            pendencias_por_rodada = list(por_rodada.values())

    # Manter backward-compat: template ainda recebe participacoes_pendentes (lista flat)
    participacoes_pendentes = [
        p for bloco in pendencias_por_rodada
        for p in (bloco["aguardando_pagamento"] + bloco["aguardando_entrega"])
    ]

    # KPIs rapidos (mesmos da tela "Meu Desempenho", mas condensados)
    kpis = None
    if fornecedor:
        fid = fornecedor.id
        total_cot = Cotacao.query.filter_by(fornecedor_id=fid).count()
        vencedoras = Cotacao.query.filter_by(fornecedor_id=fid, selecionada=True).count()
        taxa_vitoria = round(vencedoras / total_cot * 100, 1) if total_cot else 0
        media_recebida = (
            db.session.query(func.avg(AvaliacaoRodada.estrelas))
            .filter(AvaliacaoRodada.fornecedor_id == fid)
            .scalar()
        )
        media_recebida = round(float(media_recebida), 1) if media_recebida else 0
        # Rodadas aguardando cotacao que ainda nao cotei
        rodadas_a_cotar_ids = [r.id for r in rodadas_para_cotar if r.status == "aguardando_cotacao"]
        ja_cotei_nestas = set()
        if rodadas_a_cotar_ids:
            ja_cotei_nestas = {
                r for (r,) in db.session.query(Cotacao.rodada_id)
                    .filter(Cotacao.fornecedor_id == fid)
                    .filter(Cotacao.rodada_id.in_(rodadas_a_cotar_ids))
                    .distinct().all()
            }
        cotacoes_pendentes = len([r for r in rodadas_a_cotar_ids if r not in ja_cotei_nestas])

        kpis = {
            "cotacoes_pendentes": cotacoes_pendentes,
            "taxa_vitoria": taxa_vitoria,
            "media_recebida": media_recebida,
            "participacoes_pendentes": len(participacoes_pendentes),
        }

    # Ultimas 3 rodadas que cotei (com preview: total cotado + vitorias)
    ultimas_rodadas = []
    if fornecedor:
        rodadas_cotadas = (
            db.session.query(Rodada)
            .join(Cotacao, Cotacao.rodada_id == Rodada.id)
            .filter(Cotacao.fornecedor_id == fornecedor.id)
            .group_by(Rodada.id)
            .order_by(Rodada.data_abertura.desc())
            .limit(3)
            .all()
        )
        for r in rodadas_cotadas:
            total_cotado = (
                db.session.query(func.count(Cotacao.id))
                .filter(Cotacao.rodada_id == r.id, Cotacao.fornecedor_id == fornecedor.id)
                .scalar()
            ) or 0
            vitorias = (
                db.session.query(func.count(Cotacao.id))
                .filter(Cotacao.rodada_id == r.id,
                        Cotacao.fornecedor_id == fornecedor.id,
                        Cotacao.selecionada.is_(True))
                .scalar()
            ) or 0
            # Nota que recebeu nessa rodada
            nota = (
                db.session.query(func.avg(AvaliacaoRodada.estrelas))
                .filter(AvaliacaoRodada.rodada_id == r.id,
                        AvaliacaoRodada.fornecedor_id == fornecedor.id)
                .scalar()
            )
            ultimas_rodadas.append({
                "rodada": r,
                "cotacoes": total_cotado,
                "vitorias": vitorias,
                "nota": round(float(nota), 1) if nota else None,
            })

    return render_template(
        "fornecedor/dashboard.html",
        fornecedor=fornecedor,
        rodadas_para_cotar=rodadas_para_cotar,
        minhas_cotacoes=minhas_cotacoes,
        participacoes_pendentes=participacoes_pendentes,
        pendencias_por_rodada=pendencias_por_rodada,
        kpis=kpis,
        ultimas_rodadas=ultimas_rodadas,
    )


@fornecedor_bp.route("/rodada/<int:rodada_id>")
@login_required
@fornecedor_required
def ver_demanda(rodada_id):
    rodada = Rodada.query.get_or_404(rodada_id)

    # Demanda agregada — SOMENTE pedidos aprovados pelo admin
    # (pedidos rascunho/enviados/devolvidos/reprovados sao invisiveis pro fornecedor)
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

    # Cotações já enviadas por mim nesta rodada
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


@fornecedor_bp.route("/rodada/<int:rodada_id>/cotacao-final", methods=["GET", "POST"])
@login_required
@fornecedor_required
def cotar_final(rodada_id):
    """Tela onde o fornecedor fecha o preco FINAL com base nos volumes reais agregados.
    Disponivel quando rodada.status == 'em_negociacao'. Mostra lado a lado:
    preco de partida, preco final (input), e economia calculada.
    """
    rodada = Rodada.query.get_or_404(rodada_id)
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

    # Precos de partida deste fornecedor na rodada
    rodada_produtos = (
        RodadaProduto.query
        .filter_by(rodada_id=rodada_id)
        .filter((RodadaProduto.aprovado.is_(None))
                | (RodadaProduto.aprovado.is_(True)))
        .join(Produto)
        .order_by(Produto.categoria, Produto.subcategoria, Produto.nome)
        .all()
    )

    # Cotacoes finais ja enviadas (pra preencher o form)
    cotacoes_existentes = {
        c.produto_id: c for c in Cotacao.query.filter_by(
            rodada_id=rodada_id, fornecedor_id=fornecedor.id,
        ).all()
    }

    if request.method == "POST":
        count = 0
        for rp in rodada_produtos:
            pid = rp.produto_id
            if pid not in volumes:  # so cota o que foi pedido
                continue
            preco_str = request.form.get(f"preco_final_{pid}", "").strip()
            if not preco_str:
                continue
            try:
                preco_final = float(preco_str.replace(",", "."))
            except ValueError:
                continue
            if preco_final <= 0:
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

        db.session.commit()
        flash(f"Cotacao final salva. {count} preco(s) enviado(s).", "success")
        return redirect(url_for("fornecedor.cotar_final", rodada_id=rodada_id))

    # Monta linhas pra tela: so produtos que tiveram demanda
    linhas = []
    for rp in rodada_produtos:
        pid = rp.produto_id
        if pid not in volumes:
            continue
        partida = float(rp.preco_partida) if rp.preco_partida else None
        cot = cotacoes_existentes.get(pid)
        final = float(cot.preco_unitario) if cot else None
        economia_pct = None
        economia_rs = None
        if partida and final and partida > 0:
            economia_pct = round((partida - final) / partida * 100, 1)
            economia_rs = round((partida - final) * float(volumes[pid]), 2)
        linhas.append({
            "rodada_produto": rp,
            "produto": rp.produto,
            "volume": float(volumes[pid]),
            "partida": partida,
            "final": final,
            "economia_pct": economia_pct,
            "economia_rs": economia_rs,
        })

    return render_template(
        "fornecedor/cotar_final.html",
        rodada=rodada,
        linhas=linhas,
    )


@fornecedor_bp.route("/rodada/<int:rodada_id>/cotar", methods=["GET", "POST"])
@login_required
@fornecedor_required
def enviar_cotacao(rodada_id):
    rodada = Rodada.query.get_or_404(rodada_id)
    fornecedor = current_user.fornecedor

    if rodada.status not in ("fechada", "cotando"):
        flash("Esta rodada não está aberta para cotações.", "warning")
        return redirect(url_for("fornecedor.dashboard"))

    # Produtos com demanda nesta rodada
    produtos_ids = (
        db.session.query(func.distinct(ItemPedido.produto_id))
        .filter(ItemPedido.rodada_id == rodada_id)
        .all()
    )
    produtos_ids = [p[0] for p in produtos_ids]
    produtos = Produto.query.filter(Produto.id.in_(produtos_ids)).order_by(Produto.categoria, Produto.nome).all()

    # Quantidades agregadas
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
            if preco and preco > 0:
                # Atualiza se já existe, senão cria
                existente = Cotacao.query.filter_by(
                    rodada_id=rodada_id,
                    fornecedor_id=fornecedor.id,
                    produto_id=produto.id,
                ).first()

                if existente:
                    existente.preco_unitario = preco
                else:
                    cotacao = Cotacao(
                        rodada_id=rodada_id,
                        fornecedor_id=fornecedor.id,
                        produto_id=produto.id,
                        preco_unitario=preco,
                    )
                    db.session.add(cotacao)
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
    rodada = Rodada.query.get_or_404(rodada_id)
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
        # 1. Atualiza precos de partida dos produtos existentes
        count_precos = 0
        for rp in catalogo:
            preco_str = request.form.get(f"preco_{rp.id}", "").strip()
            if preco_str:
                try:
                    preco = float(preco_str.replace(",", "."))
                    if preco > 0:
                        rp.preco_partida = preco
                        count_precos += 1
                except ValueError:
                    pass

        # 2. Produto sugerido (opcional — novo produto que nao esta no catalogo)
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

            # Cria produto marcado como inativo (só ativa se admin aprovar? Simples: cria ativo
            # mas o RodadaProduto tem aprovado=None pra sinalizar pendencia)
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
                aprovado=None,  # aguarda admin
            ))
            flash(f"Produto '{nome_novo}' sugerido. Aguardando aprovação do admin.", "success")

        # 3. Se nao ha produtos pendentes, auto-libera
        pendentes = RodadaProduto.query.filter_by(
            rodada_id=rodada_id, aprovado=None,
        ).filter(RodadaProduto.adicionado_por_fornecedor_id.isnot(None)).count()

        db.session.commit()

        if pendentes == 0 and not nome_novo:
            # Verifica se todos tem preco preenchido
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

    # Agrupa por categoria -> subcategoria para UI
    by_cat = {}
    for rp in catalogo:
        cat = rp.produto.categoria
        sub = rp.produto.subcategoria or "—"
        by_cat.setdefault(cat, {}).setdefault(sub, []).append(rp)

    # Datalist de subcategorias existentes
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


@fornecedor_bp.route("/analytics")
@login_required
@fornecedor_required
def analytics():
    """Dashboard de KPIs do fornecedor logado."""
    fornecedor = current_user.fornecedor
    if not fornecedor:
        flash("Complete seu cadastro.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    fid = fornecedor.id

    # Cotacoes enviadas
    total_cotacoes = Cotacao.query.filter_by(fornecedor_id=fid).count()
    cotacoes_vencedoras = Cotacao.query.filter_by(fornecedor_id=fid, selecionada=True).count()
    taxa_vitoria = round(cotacoes_vencedoras / total_cotacoes * 100, 1) if total_cotacoes else 0

    # Rodadas que participou
    rodadas_participou = (
        db.session.query(func.count(func.distinct(Cotacao.rodada_id)))
        .filter(Cotacao.fornecedor_id == fid)
        .scalar()
    ) or 0

    # Media de avaliacao que recebeu das lanchonetes
    media_recebida = (
        db.session.query(func.avg(AvaliacaoRodada.estrelas))
        .filter(AvaliacaoRodada.fornecedor_id == fid)
        .scalar()
    )
    total_avaliacoes = AvaliacaoRodada.query.filter_by(fornecedor_id=fid).count()
    media_recebida = round(float(media_recebida), 1) if media_recebida else 0

    # Top 5 produtos que mais cotou (volume de cotacoes)
    top_produtos = (
        db.session.query(
            Produto.nome,
            func.count(Cotacao.id).label("vezes_cotado"),
            func.avg(Cotacao.preco_unitario).label("preco_medio"),
        )
        .join(Cotacao, Cotacao.produto_id == Produto.id)
        .filter(Cotacao.fornecedor_id == fid)
        .group_by(Produto.id)
        .order_by(func.count(Cotacao.id).desc())
        .limit(5)
        .all()
    )

    # Historico de avaliacoes recebidas (ultimas 10)
    avaliacoes_recentes = (
        db.session.query(
            Rodada.nome,
            Lanchonete.nome_fantasia,
            AvaliacaoRodada.estrelas,
            AvaliacaoRodada.comentario,
        )
        .join(AvaliacaoRodada, AvaliacaoRodada.rodada_id == Rodada.id)
        .join(Lanchonete, AvaliacaoRodada.lanchonete_id == Lanchonete.id)
        .filter(AvaliacaoRodada.fornecedor_id == fid)
        .order_by(AvaliacaoRodada.criado_em.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "fornecedor/analytics.html",
        fornecedor=fornecedor,
        total_cotacoes=total_cotacoes,
        cotacoes_vencedoras=cotacoes_vencedoras,
        taxa_vitoria=taxa_vitoria,
        rodadas_participou=rodadas_participou,
        media_recebida=media_recebida,
        total_avaliacoes=total_avaliacoes,
        top_produtos=top_produtos,
        avaliacoes_recentes=avaliacoes_recentes,
    )
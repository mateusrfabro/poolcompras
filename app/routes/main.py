from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, text
from app import db
from app.models import (
    Lanchonete, Rodada, ItemPedido, Cotacao, Produto,
    ParticipacaoRodada, AvaliacaoRodada, Fornecedor,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/health")
def health():
    """Healthcheck: retorna 200 se app + DB estao ok. Sem auth."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "db": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "db": str(e)}), 500


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("index.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    # Fornecedor vai para o painel dele
    if current_user.is_fornecedor:
        return redirect(url_for("fornecedor.dashboard"))

    # Admin
    if current_user.is_admin:
        total_lanchonetes = Lanchonete.query.filter_by(ativa=True).count()
        total_produtos = Produto.query.filter_by(ativo=True).count()
        rodada_aberta = Rodada.query.filter_by(status="aberta").first()

        pedidos_rodada = 0
        qtd_lanchonetes_rodada = 0
        if rodada_aberta:
            pedidos_rodada = ItemPedido.query.filter_by(rodada_id=rodada_aberta.id).count()
            qtd_lanchonetes_rodada = (
                db.session.query(func.count(func.distinct(ItemPedido.lanchonete_id)))
                .filter(ItemPedido.rodada_id == rodada_aberta.id)
                .scalar()
            )

        return render_template(
            "dashboard_admin.html",
            total_lanchonetes=total_lanchonetes,
            total_produtos=total_produtos,
            rodada_aberta=rodada_aberta,
            pedidos_rodada=pedidos_rodada,
            qtd_lanchonetes_rodada=qtd_lanchonetes_rodada,
        )

    # Lanchonete
    lanchonete = current_user.lanchonete
    rodada_aberta = Rodada.query.filter_by(status="aberta").first()

    meus_pedidos = []
    if rodada_aberta and lanchonete:
        meus_pedidos = (
            ItemPedido.query
            .filter_by(rodada_id=rodada_aberta.id, lanchonete_id=lanchonete.id)
            .all()
        )

    # KPIs e pendencias da lanchonete
    kpis = {}
    pendencias = []
    ultimas_rodadas = []
    if lanchonete:
        lid = lanchonete.id

        # Pendencias: rodadas finalizadas onde precisa de acao do cliente
        participacoes = (
            ParticipacaoRodada.query
            .filter_by(lanchonete_id=lid)
            .join(Rodada, ParticipacaoRodada.rodada_id == Rodada.id)
            .filter(Rodada.status == "finalizada")
            .all()
        )
        for p in participacoes:
            if p.aceite_proposta is None:
                pendencias.append({"rodada": p.rodada, "acao": "Aceitar proposta", "urgencia": "alta"})
            elif p.aceite_proposta and not p.comprovante_key:
                pendencias.append({"rodada": p.rodada, "acao": "Enviar comprovante", "urgencia": "alta"})
            elif p.entrega_informada_em and p.recebimento_ok is None:
                pendencias.append({"rodada": p.rodada, "acao": "Confirmar recebimento", "urgencia": "media"})
            elif p.recebimento_ok and not p.avaliacao_geral:
                pendencias.append({"rodada": p.rodada, "acao": "Avaliar a rodada", "urgencia": "baixa"})

        # KPIs
        total_rodadas = (
            db.session.query(func.count(func.distinct(ItemPedido.rodada_id)))
            .filter(ItemPedido.lanchonete_id == lid)
            .scalar()
        ) or 0

        rodadas_concluidas = (
            ParticipacaoRodada.query
            .filter_by(lanchonete_id=lid)
            .filter(ParticipacaoRodada.avaliacao_geral.isnot(None))
            .count()
        )

        media_que_deu = (
            db.session.query(func.avg(ParticipacaoRodada.avaliacao_geral))
            .filter(ParticipacaoRodada.lanchonete_id == lid,
                    ParticipacaoRodada.avaliacao_geral.isnot(None))
            .scalar()
        ) or 0

        kpis = {
            "total_rodadas": total_rodadas,
            "rodadas_concluidas": rodadas_concluidas,
            "pendencias": len(pendencias),
            "media_que_deu": round(float(media_que_deu), 1),
        }

        # Ultimas 3 rodadas finalizadas/canceladas + preview (total gasto + nota dada)
        ultimas_rodadas_raw = (
            db.session.query(Rodada)
            .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
            .filter(ItemPedido.lanchonete_id == lid,
                    Rodada.status.in_(["finalizada", "cancelada", "fechada"]))
            .group_by(Rodada.id)
            .order_by(Rodada.data_abertura.desc())
            .limit(3)
            .all()
        )

        ultimas_rodadas = []
        for r in ultimas_rodadas_raw:
            # Total gasto = soma(qtd * preco cotacao selecionada) para pedidos dessa lanchonete
            total = (
                db.session.query(
                    func.coalesce(func.sum(ItemPedido.quantidade * Cotacao.preco_unitario), 0)
                )
                .join(Cotacao,
                      (Cotacao.rodada_id == ItemPedido.rodada_id) &
                      (Cotacao.produto_id == ItemPedido.produto_id) &
                      (Cotacao.selecionada.is_(True)))
                .filter(ItemPedido.rodada_id == r.id,
                        ItemPedido.lanchonete_id == lid)
                .scalar()
            ) or 0
            part = (
                ParticipacaoRodada.query
                .filter_by(rodada_id=r.id, lanchonete_id=lid)
                .first()
            )
            nota = part.avaliacao_geral if part else None
            ultimas_rodadas.append({
                "rodada": r,
                "total": float(total) if total else 0.0,
                "nota": nota,
            })

    return render_template(
        "dashboard.html",
        lanchonete=lanchonete,
        rodada_aberta=rodada_aberta,
        meus_pedidos=meus_pedidos,
        kpis=kpis,
        pendencias=pendencias,
        ultimas_rodadas=ultimas_rodadas,
    )

"""Marketplace publico — vitrine de fornecedores sem login.

Pagina /marketplace lista fornecedores ativos com nota media e numero de
avaliacoes. Sem autenticacao, acessivel por qualquer pessoa (lanchonetes
prospect). Rate-limit pra evitar crawler pesado.
"""
from flask import Blueprint, render_template
from sqlalchemy import func

from app import db, limiter
from app.models import Fornecedor, AvaliacaoRodada, Cotacao

marketplace_bp = Blueprint("marketplace", __name__)


@marketplace_bp.route("/marketplace")
@limiter.limit("30 per minute", error_message="Muitos acessos. Tente novamente em instantes.")
def listar():
    """Lista publica de fornecedores ativos com rating medio."""
    # Query: fornecedores ativos + agregados de avaliacao + contagem de
    # rodadas com cotacao vencedora (indicador de atividade).
    rows = (
        db.session.query(
            Fornecedor.id,
            Fornecedor.razao_social,
            Fornecedor.cidade,
            func.avg(AvaliacaoRodada.estrelas).label("media"),
            func.count(AvaliacaoRodada.id).label("avaliacoes"),
        )
        .outerjoin(AvaliacaoRodada, AvaliacaoRodada.fornecedor_id == Fornecedor.id)
        # Opt-in LGPD: apenas fornecedores que autorizaram explicitamente.
        .filter(Fornecedor.ativo.is_(True))
        .filter(Fornecedor.aparece_no_marketplace.is_(True))
        .group_by(Fornecedor.id)
        .order_by(
            func.avg(AvaliacaoRodada.estrelas).desc().nullslast(),
            func.count(AvaliacaoRodada.id).desc(),
            Fornecedor.razao_social,
        )
        .all()
    )

    # Rodadas com cotacao vencedora por fornecedor (atividade)
    atividade = dict(
        db.session.query(
            Cotacao.fornecedor_id,
            func.count(func.distinct(Cotacao.rodada_id)),
        )
        .filter(Cotacao.selecionada.is_(True))
        .group_by(Cotacao.fornecedor_id)
        .all()
    )

    fornecedores = [
        {
            "id": r.id,
            "razao_social": r.razao_social,
            "cidade": r.cidade or "Londrina",
            "media": round(float(r.media), 1) if r.media else None,
            "avaliacoes": r.avaliacoes or 0,
            "rodadas_vencidas": atividade.get(r.id, 0),
        }
        for r in rows
    ]

    return render_template("marketplace/listar.html", fornecedores=fornecedores)

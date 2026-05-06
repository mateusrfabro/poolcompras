"""Calculo de comissao do fornecedor sobre vendas efetivadas.

Comissao = (venda efetivada total × percentual_comissao do fornecedor) / 100

Vendas efetivadas vem de `vendas_efetivadas.linhas_efetivadas` — mesma
fonte de P&L do fornecedor + CMV da lanchonete (consistencia garantida).

Agregacoes:
- Total a pagar (somatorio sobre todas vendas)
- Por rodada
- Por dia (data da rodada finalizada)

V2: persistir em tabela ComissaoFornecedor com snapshot do percentual no
momento da venda (caso admin mude o % depois). Por agora calcula on-the-fly.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app import db
from app.models import Fornecedor
from app.services.vendas_efetivadas import linhas_efetivadas


def calcular_comissao_fornecedor(fornecedor_id: int) -> dict:
    """Retorna agregacoes de comissao pro fornecedor logado.

    Returns:
        {
            "percentual": Decimal,   # % do fornecedor (snapshot atual)
            "receita_total": float,  # vendas efetivadas em valor
            "comissao_total": float, # receita * %
            "por_rodada": [{rodada_id, nome, data, receita, comissao}],
            "por_dia":    [{data, receita, comissao}],
        }
    """
    fornecedor = db.session.get(Fornecedor, fornecedor_id)
    if fornecedor is None:
        return {
            "percentual": Decimal("0"),
            "receita_total": 0.0, "comissao_total": 0.0,
            "por_rodada": [], "por_dia": [],
        }

    pct = fornecedor.percentual_comissao or Decimal("0")
    pct_float = float(pct) / 100.0

    receita_total = 0.0
    por_rodada = {}
    por_dia = defaultdict(lambda: {"receita": 0.0, "comissao": 0.0})

    for l in linhas_efetivadas(fornecedor_id=fornecedor_id):
        qtd = float(l.quantidade or 0)
        preco = float(l.preco_final or 0)
        receita = qtd * preco
        receita_total += receita

        r = por_rodada.setdefault(l.rodada_id, {
            "rodada_id": l.rodada_id,
            "nome": l.rodada_nome,
            "data": l.data,
            "receita": 0.0,
        })
        r["receita"] += receita

        # Agrupa por data da rodada (mesmo dia para varias rodadas eh raro
        # mas suportado — soma).
        data_key = l.data.date() if l.data else None
        if data_key is not None:
            por_dia[data_key]["receita"] += receita

    # Aplica % uma vez por bucket (precisao igual a aplicar por linha).
    for r in por_rodada.values():
        r["comissao"] = round(r["receita"] * pct_float, 2)
        r["receita"] = round(r["receita"], 2)
    for k in por_dia:
        por_dia[k]["comissao"] = round(por_dia[k]["receita"] * pct_float, 2)
        por_dia[k]["receita"] = round(por_dia[k]["receita"], 2)

    por_rodada_list = sorted(
        por_rodada.values(), key=lambda r: r["data"] or 0, reverse=True,
    )
    por_dia_list = [
        {"data": k, **v} for k, v in sorted(por_dia.items(), reverse=True)
    ]

    return {
        "percentual": pct,
        "receita_total": round(receita_total, 2),
        "comissao_total": round(receita_total * pct_float, 2),
        "por_rodada": por_rodada_list,
        "por_dia": por_dia_list,
    }


def calcular_comissoes_todos_fornecedores() -> list[dict]:
    """Visao admin: 1 linha por fornecedor com totais agregados."""
    fornecedores = (
        Fornecedor.query.filter_by(ativo=True)
        .order_by(Fornecedor.razao_social)
        .all()
    )
    resultado = []
    for f in fornecedores:
        c = calcular_comissao_fornecedor(f.id)
        resultado.append({
            "fornecedor_id": f.id,
            "razao_social": f.razao_social,
            "percentual": c["percentual"],
            "receita_total": c["receita_total"],
            "comissao_total": c["comissao_total"],
        })
    return resultado

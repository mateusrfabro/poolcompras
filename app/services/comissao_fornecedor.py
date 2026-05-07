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
from decimal import Decimal, ROUND_HALF_UP

from app import db
from app.models import Fornecedor
from app.services.vendas_efetivadas import linhas_efetivadas


_CENT = Decimal("0.01")


def _q(d: Decimal) -> Decimal:
    """Quantize pra 2 casas com half-up (padrao financeiro BR)."""
    return d.quantize(_CENT, rounding=ROUND_HALF_UP)


def _to_decimal(x) -> Decimal:
    """Converte qualquer numero pra Decimal sem passar por float
    (preserva precisao monetaria — viola 'Float pra dinheiro' se passar)."""
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def calcular_comissao_fornecedor(fornecedor_id: int) -> dict:
    """Retorna agregacoes de comissao pro fornecedor logado.

    Calculo todo em Decimal — Float pra dinheiro causa drift e viola
    padrao do projeto (CLAUDE.md). Conversao pra float so no fim, se
    o template/JSON precisar (Jinja "%.2f"|format aceita Decimal direto).

    Returns:
        {
            "percentual": Decimal,    # % do fornecedor (snapshot atual)
            "receita_total": Decimal, # vendas efetivadas, 2 casas
            "comissao_total": Decimal,# receita * %, 2 casas
            "por_rodada": [{rodada_id, nome, data, receita, comissao}],
            "por_dia":    [{data, receita, comissao}],
        }
    """
    fornecedor = db.session.get(Fornecedor, fornecedor_id)
    if fornecedor is None:
        return {
            "percentual": Decimal("0"),
            "receita_total": Decimal("0"), "comissao_total": Decimal("0"),
            "por_rodada": [], "por_dia": [],
        }

    pct = fornecedor.percentual_comissao or Decimal("0")
    pct_decimal = pct / Decimal("100")

    receita_total = Decimal("0")
    por_rodada: dict[int, dict] = {}
    por_dia: dict = defaultdict(lambda: {"receita": Decimal("0"),
                                          "comissao": Decimal("0")})

    for l in linhas_efetivadas(fornecedor_id=fornecedor_id):
        qtd = _to_decimal(l.quantidade)
        preco = _to_decimal(l.preco_final)
        receita = qtd * preco
        receita_total += receita

        r = por_rodada.setdefault(l.rodada_id, {
            "rodada_id": l.rodada_id,
            "nome": l.rodada_nome,
            "data": l.data,
            "receita": Decimal("0"),
        })
        r["receita"] += receita

        data_key = l.data.date() if l.data else None
        if data_key is not None:
            por_dia[data_key]["receita"] += receita

    # Aplica % por bucket (matematicamente igual a aplicar por linha).
    for r in por_rodada.values():
        r["comissao"] = _q(r["receita"] * pct_decimal)
        r["receita"] = _q(r["receita"])
    for k in por_dia:
        por_dia[k]["comissao"] = _q(por_dia[k]["receita"] * pct_decimal)
        por_dia[k]["receita"] = _q(por_dia[k]["receita"])

    por_rodada_list = sorted(
        por_rodada.values(), key=lambda r: r["data"] or 0, reverse=True,
    )
    por_dia_list = [
        {"data": k, **v} for k, v in sorted(por_dia.items(), reverse=True)
    ]

    return {
        "percentual": pct,
        "receita_total": _q(receita_total),
        "comissao_total": _q(receita_total * pct_decimal),
        "por_rodada": por_rodada_list,
        "por_dia": por_dia_list,
    }


def calcular_comissoes_todos_fornecedores() -> list[dict]:
    """Visao admin: 1 linha por fornecedor com totais agregados."""
    fornecedores = db.session.scalars(
        db.select(Fornecedor).where(Fornecedor.ativo.is_(True))
        .order_by(Fornecedor.razao_social)
    ).all()
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

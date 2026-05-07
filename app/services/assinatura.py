"""Geracao de Assinatura + Faturas para uma lanchonete recem-cadastrada.

MVP: ao se cadastrar, a lanchonete recebe automaticamente 1 assinatura
ativa de 12 parcelas mensais de R$500. Vencimento replica o dia do
cadastro (ajustado pra max=28 pra nao quebrar em fevereiro). Admin
marca pagamento manualmente em /admin/financeiro depois.

Renovacao no fim do ciclo: process manual no admin (gerar nova
Assinatura). Automacao fica pra v2.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date
from decimal import Decimal

from app import db
from app.models import Assinatura, Fatura, Lanchonete

logger = logging.getLogger(__name__)

VALOR_MENSAL_PADRAO = Decimal("500.00")
PARCELAS_PADRAO = 12
DIA_VENCIMENTO_MAX = 28  # evita drift fevereiro/anos bissextos


def _proximo_mes(d: date) -> date:
    """Primeiro dia do mes seguinte a `d`."""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _ultimo_dia_do_mes(ano: int, mes: int) -> date:
    """Ultimo dia do mes (28-31)."""
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _vencimento_no_mes(ano: int, mes: int, dia_alvo: int) -> date:
    """Aplica dia_alvo no mes; se dia_alvo > ultimo_dia, usa ultimo_dia."""
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(dia_alvo, ultimo))


def criar_assinatura_inicial(
    lanchonete: Lanchonete,
    valor_mensal: Decimal = VALOR_MENSAL_PADRAO,
    parcelas: int = PARCELAS_PADRAO,
    inicio: date | None = None,
) -> Assinatura:
    """Cria 1 Assinatura ativa + N Faturas pendentes pra lanchonete.

    Idempotencia: se a lanchonete ja tem assinatura ativa, devolve a
    existente sem criar duplicada (defensivo — caller pode tropecar em
    chamadas duplas durante reentrada do signup).

    Para callers que precisam saber se criaram agora ou retornaram
    existente (ex: flash diferente em /admin/financeiro/.../gerar), use
    `criar_assinatura_inicial_idempotente()` que retorna tupla.

    Args:
        lanchonete: dona do contrato.
        valor_mensal: valor de cada parcela (R$500 default).
        parcelas: total de parcelas (12 default).
        inicio: data de inicio do contrato (hoje default).

    Returns:
        Assinatura ja persistida e com `parcelas` Faturas associadas.
    """
    assinatura, _ = criar_assinatura_inicial_idempotente(
        lanchonete, valor_mensal=valor_mensal,
        parcelas=parcelas, inicio=inicio,
    )
    return assinatura


def criar_assinatura_inicial_idempotente(
    lanchonete: Lanchonete,
    valor_mensal: Decimal = VALOR_MENSAL_PADRAO,
    parcelas: int = PARCELAS_PADRAO,
    inicio: date | None = None,
) -> tuple[Assinatura, bool]:
    """Mesma logica de criar_assinatura_inicial mas devolve tupla
    `(assinatura, criada_agora)` pro caller distinguir caminho."""
    existente = db.session.execute(
        db.select(Assinatura).where(
            Assinatura.lanchonete_id == lanchonete.id,
            Assinatura.status == Assinatura.STATUS_ATIVA,
        )
    ).scalar_one_or_none()
    if existente:
        return existente, False

    inicio = inicio or date.today()
    dia_vencimento = min(inicio.day, DIA_VENCIMENTO_MAX)

    # vigencia_fim = ultimo dia do mes da parcela final.
    # Ex: cadastro em 06/05/2026 com 12 parcelas -> vigencia_fim = 30/04/2027.
    mes_da_ultima = inicio
    for _ in range(parcelas - 1):
        mes_da_ultima = _proximo_mes(mes_da_ultima)
    vigencia_fim = _ultimo_dia_do_mes(mes_da_ultima.year, mes_da_ultima.month)

    assinatura = Assinatura(
        lanchonete_id=lanchonete.id,
        valor_mensal=valor_mensal,
        parcelas_total=parcelas,
        vigencia_inicio=inicio,
        vigencia_fim=vigencia_fim,
        status=Assinatura.STATUS_ATIVA,
    )
    db.session.add(assinatura)
    db.session.flush()  # pega id pra FK das faturas

    mes_ref = date(inicio.year, inicio.month, 1)
    for n in range(1, parcelas + 1):
        venc = _vencimento_no_mes(mes_ref.year, mes_ref.month, dia_vencimento)
        db.session.add(Fatura(
            assinatura_id=assinatura.id,
            parcela_numero=n,
            mes_referencia=mes_ref,
            valor=valor_mensal,
            vencimento=venc,
            status=Fatura.STATUS_PENDENTE,
        ))
        mes_ref = _proximo_mes(mes_ref)

    db.session.commit()
    logger.info(
        "ASSINATURA_CRIADA lanchonete=%s assinatura=%s parcelas=%s valor=%s",
        lanchonete.id, assinatura.id, parcelas, valor_mensal,
    )
    return assinatura, True

"""Programa de indicacao: codigo unico + registro + verificacao de recompensa.

Regra (MVP):
- Cada lanchonete tem `codigo_indicacao` (8 chars). Espalha link
  `aggron.com.br/registro?ind=ABC123`.
- Visitante cadastra via link -> cria `Indicacao(indicador, indicada)`.
- Apos 3 indicadas com `ativa=True` ha mais de 30 dias e ainda sem
  recompensa aplicada, indicadora ganha 1 mes gratis (aplicado
  manualmente pela equipe — sistema notifica admin via Telegram).

Anti-fraude MVP:
- DB CHECK constraint bloqueia auto-indicacao
- UNIQUE(indicada_lanchonete_id) bloqueia reclassificar dono
- Service valida codigo existe antes de criar
- Codigos sem caracteres confusos (sem 0/O/1/I/L) — copy-paste resistente
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app import db
from app.models import Lanchonete, Indicacao

logger = logging.getLogger(__name__)

# Alfabeto sem caracteres ambiguos pra leitura/ditado por telefone.
_ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODIGO_LEN = 8

# Recompensa: 3 indicadas ativas ha 30+ dias.
RECOMPENSA_INDICADAS_NECESSARIAS = 3
RECOMPENSA_DIAS_ATIVA_MINIMO = 30


def _gerar_codigo_unico() -> str:
    """Gera codigo unico, com retry em caso de colisao (probabilidade
    desprezivel — 32^8 = 1.1T combinacoes). Limite de 20 tentativas pra
    evitar loop infinito em caso de bug."""
    for _ in range(20):
        cod = "".join(secrets.choice(_ALPHA) for _ in range(_CODIGO_LEN))
        existe = db.session.query(Lanchonete.id).filter_by(
            codigo_indicacao=cod,
        ).first()
        if not existe:
            return cod
    raise RuntimeError("Falha ao gerar codigo de indicacao unico apos 20 tentativas")


def garantir_codigo(lanchonete: Lanchonete) -> str:
    """Retorna o codigo da lanchonete, gerando lazy se ainda nao existir.

    Lanchonetes legacy (criadas antes desta feature) tem codigo_indicacao
    NULL. Primeiro acesso ao dashboard de indicacao chama isto e popula.
    """
    if lanchonete.codigo_indicacao:
        return lanchonete.codigo_indicacao
    cod = _gerar_codigo_unico()
    lanchonete.codigo_indicacao = cod
    db.session.commit()
    logger.info("INDICACAO_CODIGO_GERADO lanchonete=%s", lanchonete.id)
    return cod


def buscar_indicador_por_codigo(codigo: str) -> Optional[Lanchonete]:
    """Retorna lanchonete dona do codigo, ou None se nao existir/invalido."""
    if not codigo:
        return None
    codigo = codigo.strip().upper()
    if len(codigo) != _CODIGO_LEN or not all(c in _ALPHA for c in codigo):
        return None
    return Lanchonete.query.filter_by(codigo_indicacao=codigo).first()


def registrar_indicacao(codigo: str, indicada_lanchonete: Lanchonete) -> bool:
    """Tenta registrar uma indicacao. Retorna True se criada, False senao.

    Casos que retornam False (silenciosos pra nao expor enumeration):
    - codigo invalido ou inexistente
    - auto-indicacao (mesma lanchonete)
    - indicada ja tem indicador (UNIQUE constraint)
    """
    indicador = buscar_indicador_por_codigo(codigo)
    if not indicador:
        return False
    if indicador.id == indicada_lanchonete.id:
        logger.info("INDICACAO_AUTO_BLOQUEADA")
        return False
    try:
        db.session.add(Indicacao(
            indicador_lanchonete_id=indicador.id,
            indicada_lanchonete_id=indicada_lanchonete.id,
            codigo_usado=indicador.codigo_indicacao,
        ))
        db.session.commit()
        logger.info(
            "INDICACAO_REGISTRADA indicador=%s indicada=%s",
            indicador.id, indicada_lanchonete.id,
        )
        # Notif "quase la" pro indicador quando ele chegou em N-1 indicacoes
        # totais (independente de elegibilidade — vai virar elegivel em 30d).
        # Best-effort: nao bloqueia o cadastro se Telegram cair.
        try:
            _notificar_quase_la_se_aplicavel(indicador)
        except Exception:  # pylint: disable=broad-except
            logger.warning(
                "INDICACAO_NOTIF_QUASE_LA_FALHOU indicador=%s",
                indicador.id, exc_info=True,
            )
        return True
    except IntegrityError:
        # UNIQUE(indicada_lanchonete_id) violado — race ou tentativa de
        # reclassificar. Silencioso.
        db.session.rollback()
        logger.info("INDICACAO_DUPLICADA_BLOQUEADA")
        return False


def _notificar_quase_la_se_aplicavel(indicador: Lanchonete) -> None:
    """Dispara Telegram pro indicador quando o total de indicacoes pendentes
    (sem recompensa aplicada) bate em N-1. Heuristica: se contagem == N-1
    APOS este cadastro, eh a transicao — primeira vez. Disparado 1x por
    "quase chegada".

    Comportamento de gatilho clasico (efeito da meta proxima): user que
    chega em 2/3 tem maior prob de ir buscar o 3o.
    """
    from app.services.notificacoes import notificar_evento  # local: evita ciclo
    pendentes = (
        Indicacao.query
        .filter_by(indicador_lanchonete_id=indicador.id)
        .filter(Indicacao.recompensa_aplicada_em.is_(None))
        .count()
    )
    if pendentes != RECOMPENSA_INDICADAS_NECESSARIAS - 1:
        return
    if not indicador.responsavel:
        return
    titulo = f"Falta 1 indicação pra você ganhar 1 mês grátis"
    detalhes = (
        f"Você já tem {pendentes} indicações registradas. "
        f"Indique mais 1 e, quando completar 30 dias ativa, libera o "
        f"resgate de R$ 500,00 no seu próximo boleto."
    )
    notificar_evento(indicador.responsavel, titulo, detalhes)
    logger.info("INDICACAO_NOTIF_QUASE_LA_ENVIADA indicador=%s", indicador.id)


def indicacoes_da_lanchonete(lanchonete_id: int) -> list[dict]:
    """Lista indicacoes feitas pela lanchonete, com status pro dashboard.

    Cada item: {
        'indicada': Lanchonete,
        'criado_em': datetime,
        'status': 'aguardando_30d' | 'elegivel' | 'inativa' | 'recompensada',
        'dias_para_elegivel': int (so se aguardando_30d),
    }
    """
    agora = datetime.now(timezone.utc)
    cutoff = agora - timedelta(days=RECOMPENSA_DIAS_ATIVA_MINIMO)
    # joinedload(indicada) evita N+1: cada item do loop acessa
    # ind.indicada.ativa e ind.indicada.nome_fantasia.
    indicacoes = (
        Indicacao.query
        .options(joinedload(Indicacao.indicada))
        .filter_by(indicador_lanchonete_id=lanchonete_id)
        .order_by(Indicacao.criado_em.desc())
        .all()
    )
    resultado = []
    for ind in indicacoes:
        item = {
            "indicada": ind.indicada,
            "criado_em": ind.criado_em,
            "status": None,
            "dias_para_elegivel": None,
        }
        if ind.recompensa_aplicada_em:
            item["status"] = "recompensada"
        elif not ind.indicada or not ind.indicada.ativa:
            item["status"] = "inativa"
        elif ind.criado_em > cutoff:
            item["status"] = "aguardando_30d"
            dias_passados = (agora - ind.criado_em).days
            item["dias_para_elegivel"] = max(0, RECOMPENSA_DIAS_ATIVA_MINIMO - dias_passados)
        else:
            item["status"] = "elegivel"
        resultado.append(item)
    return resultado


def calcular_status_recompensa(lanchonete_id: int) -> dict:
    """Retorna o estado atual do programa pra uma lanchonete.

    Returns:
        {
            'elegiveis': int (indicacoes com >=30d ativas sem recompensa),
            'necessarias': 3,
            'pode_resgatar': bool,
            'aguardando_30d': int (contagem de indicacoes ainda no periodo de carencia),
            'total_recompensas_recebidas': int,
        }
    """
    agora = datetime.now(timezone.utc)
    cutoff = agora - timedelta(days=RECOMPENSA_DIAS_ATIVA_MINIMO)
    base = Indicacao.query.filter_by(indicador_lanchonete_id=lanchonete_id)

    elegiveis = (
        base.filter(Indicacao.recompensa_aplicada_em.is_(None))
        .filter(Indicacao.criado_em <= cutoff)
        .join(Lanchonete, Indicacao.indicada_lanchonete_id == Lanchonete.id)
        .filter(Lanchonete.ativa.is_(True))
        .count()
    )
    aguardando = (
        base.filter(Indicacao.recompensa_aplicada_em.is_(None))
        .filter(Indicacao.criado_em > cutoff)
        .count()
    )
    recompensadas_total = (
        base.filter(Indicacao.recompensa_aplicada_em.isnot(None)).count()
    )
    return {
        "elegiveis": elegiveis,
        "necessarias": RECOMPENSA_INDICADAS_NECESSARIAS,
        "pode_resgatar": elegiveis >= RECOMPENSA_INDICADAS_NECESSARIAS,
        "aguardando_30d": aguardando,
        "total_recompensas_recebidas": recompensadas_total // RECOMPENSA_INDICADAS_NECESSARIAS,
    }

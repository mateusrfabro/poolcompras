"""
Comandos CLI customizados do Flask.

Uso:
    flask cron fechar-vencidas   # fecha rodadas com data_fechamento <= agora
    flask cron status            # status do agendamento (debug)

Deploy: na VM (Ademar), adicionar ao crontab:
    */5 * * * * cd /app && FLASK_APP=run.py flask cron fechar-vencidas >> /var/log/poolcompras-cron.log 2>&1
"""
from datetime import datetime, timezone
import click
from flask import Blueprint
from flask.cli import with_appcontext

from app import db
from app.models import Rodada, EventoRodada, ParticipacaoRodada

cron_bp = Blueprint("cron", __name__, cli_group="cron")


@cron_bp.cli.command("fechar-vencidas")
@with_appcontext
def fechar_vencidas():
    """Fecha rodadas cujo data_fechamento ja passou, gerando EventoRodada."""
    # SQLite retorna datetime naive; comparamos naive com naive
    agora = datetime.now(timezone.utc)

    rodadas = Rodada.query.filter(
        Rodada.status == "aberta",
        Rodada.data_fechamento <= agora,
    ).all()

    if not rodadas:
        click.echo(f"[{agora.isoformat()}] nenhuma rodada vencida.")
        return

    for r in rodadas:
        r.status = "fechada"
        db.session.add(EventoRodada(
            rodada_id=r.id,
            tipo=EventoRodada.TIPO_RODADA_FECHADA,
            descricao=f"Rodada fechada automaticamente (deadline: {r.data_fechamento.isoformat()})",
        ))
        click.echo(f"  -> fechada: {r.nome} (id {r.id})")

    db.session.commit()
    click.echo(f"[{agora.isoformat()}] {len(rodadas)} rodada(s) fechada(s).")


@cron_bp.cli.command("deadline-vencido")
@with_appcontext
def deadline_vencido():
    """Marca participacoes que passaram do deadline de alguma fase (loga no EventoRodada).
    Nao cancela automaticamente — apenas registra pra relatorio.
    """
    agora = datetime.now(timezone.utc)
    contagens = {"pedido": 0, "cotacao": 0, "aceite": 0,
                 "pagamento": 0, "entrega": 0, "confirmacao": 0}

    # Rodadas com algum deadline configurado
    rodadas = Rodada.query.filter(
        (Rodada.deadline_pedido.isnot(None))
        | (Rodada.deadline_cotacao.isnot(None))
        | (Rodada.deadline_aceite.isnot(None))
        | (Rodada.deadline_pagamento.isnot(None))
        | (Rodada.deadline_entrega.isnot(None))
        | (Rodada.deadline_confirmacao.isnot(None))
    ).all()

    for r in rodadas:
        participacoes = ParticipacaoRodada.query.filter_by(rodada_id=r.id).all()
        for p in participacoes:
            # Pra cada deadline vencido, se a fase nao foi concluida, loga
            checks = [
                (r.deadline_aceite, p.aceite_proposta is None, "aceite"),
                (r.deadline_pagamento, not p.comprovante_key, "pagamento"),
                (r.deadline_entrega, not p.entrega_informada_em, "entrega"),
                (r.deadline_confirmacao, p.recebimento_ok is None, "confirmacao"),
            ]
            for deadline, pendente, fase in checks:
                if deadline and pendente and deadline <= agora:
                    # Ja logou antes? Evita spam
                    existe = EventoRodada.query.filter_by(
                        rodada_id=r.id, lanchonete_id=p.lanchonete_id,
                        tipo=EventoRodada.TIPO_DEADLINE_VENCIDO,
                    ).filter(EventoRodada.descricao.like(f"%{fase}%")).first()
                    if existe:
                        continue
                    db.session.add(EventoRodada(
                        rodada_id=r.id,
                        lanchonete_id=p.lanchonete_id,
                        tipo=EventoRodada.TIPO_DEADLINE_VENCIDO,
                        descricao=f"Deadline da fase {fase} vencido sem acao",
                    ))
                    contagens[fase] += 1

    db.session.commit()
    total = sum(contagens.values())
    click.echo(f"[{agora.isoformat()}] {total} deadline(s) registrados: {contagens}")


@cron_bp.cli.command("status")
@with_appcontext
def status():
    """Mostra rodadas abertas e suas datas de fechamento (util pra debug de cron)."""
    agora = datetime.now(timezone.utc)
    rodadas = Rodada.query.filter_by(status="aberta").order_by(Rodada.data_fechamento.asc()).all()
    if not rodadas:
        click.echo("Nenhuma rodada aberta.")
        return
    click.echo(f"Agora: {agora.isoformat()}")
    click.echo(f"{len(rodadas)} rodada(s) abertas:")
    for r in rodadas:
        vencida = "VENCIDA" if r.data_fechamento <= agora else "ativa"
        click.echo(f"  [{vencida}] {r.nome} (id {r.id}) -> fecha em {r.data_fechamento.isoformat()}")
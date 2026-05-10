"""Tela admin de auditoria — lista AuditLog com filtros + export CSV.

Permite ao admin/dono ver:
- Quem logou e quando (login_ok / login_fail / logout)
- Quem criou/editou/converteu lead (CRM rastreabilidade do Gabriel SDR)
- Quem cadastrou produto/lanchonete/fornecedor/vendedor
- Quem criou/cancelou/finalizou rodada

Filtros: usuario_id, acao, periodo (de/ate), recurso_tipo. Paginado.
"""
from datetime import datetime, timezone, timedelta

from flask import render_template, request
from flask_login import login_required
from sqlalchemy import and_, desc

from app import db
from app.models import AuditLog, Usuario
from app.services.csv_export import csv_response
from . import admin_bp, admin_required


_PAGE_SIZE = 50
# Lista de acoes pra dropdown — sincronizado com constantes em AuditLog.
_ACOES_DISPONIVEIS = [
    AuditLog.ACAO_LOGIN_OK, AuditLog.ACAO_LOGIN_FAIL, AuditLog.ACAO_LOGOUT,
    AuditLog.ACAO_LEAD_CRIADO, AuditLog.ACAO_LEAD_STATUS_ALTERADO,
    AuditLog.ACAO_LEAD_CONVERTIDO, AuditLog.ACAO_LEAD_EVENTO,
    AuditLog.ACAO_PRODUTO_CRIADO, AuditLog.ACAO_PRODUTO_EDITADO,
    AuditLog.ACAO_LANCHONETE_CRIADA, AuditLog.ACAO_FORNECEDOR_CRIADO,
    AuditLog.ACAO_VENDEDOR_CRIADO,
    AuditLog.ACAO_RODADA_CRIADA, AuditLog.ACAO_RODADA_CANCELADA,
    AuditLog.ACAO_RODADA_FINALIZADA,
]


def _construir_filtros():
    """Le query string e devolve (lista_de_filtros_sqla, dict_pra_template)."""
    filtros = []
    estado = {
        "usuario_id": request.args.get("usuario_id", "").strip() or None,
        "acao": request.args.get("acao", "").strip() or None,
        "recurso_tipo": request.args.get("recurso_tipo", "").strip() or None,
        "de": request.args.get("de", "").strip() or None,
        "ate": request.args.get("ate", "").strip() or None,
    }
    if estado["usuario_id"]:
        try:
            filtros.append(AuditLog.usuario_id == int(estado["usuario_id"]))
        except ValueError:
            pass
    if estado["acao"]:
        filtros.append(AuditLog.acao == estado["acao"])
    if estado["recurso_tipo"]:
        filtros.append(AuditLog.recurso_tipo == estado["recurso_tipo"])
    if estado["de"]:
        try:
            de_dt = datetime.strptime(estado["de"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            filtros.append(AuditLog.criado_em >= de_dt)
        except ValueError:
            pass
    if estado["ate"]:
        try:
            ate_dt = datetime.strptime(estado["ate"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            # Inclui o dia inteiro
            filtros.append(AuditLog.criado_em < ate_dt + timedelta(days=1))
        except ValueError:
            pass
    return filtros, estado


@admin_bp.route("/auditoria")
@login_required
@admin_required
def auditoria():
    """Lista paginada do AuditLog com filtros."""
    filtros, estado = _construir_filtros()
    pagina = max(1, int(request.args.get("p", "1") or "1"))

    q = (
        db.session.query(AuditLog)
        .filter(and_(*filtros) if filtros else True)
        .order_by(desc(AuditLog.criado_em))
    )
    total = q.count()
    eventos = (
        q.limit(_PAGE_SIZE).offset((pagina - 1) * _PAGE_SIZE).all()
    )
    # Resolve nomes dos usuarios em 1 query (evita N+1).
    user_ids = {e.usuario_id for e in eventos if e.usuario_id}
    users = {u.id: u for u in Usuario.query.filter(Usuario.id.in_(user_ids)).all()} if user_ids else {}

    # Lista de usuarios pro filtro (so admin/vendedor — quem age no sistema)
    usuarios_filtro = (
        Usuario.query
        .filter(Usuario.tipo.in_(["admin", "vendedor"]))
        .order_by(Usuario.nome_responsavel).all()
    )

    return render_template(
        "admin/auditoria.html",
        eventos=eventos,
        users=users,
        total=total,
        pagina=pagina,
        page_size=_PAGE_SIZE,
        tem_proxima=(pagina * _PAGE_SIZE) < total,
        acoes_disponiveis=_ACOES_DISPONIVEIS,
        usuarios_filtro=usuarios_filtro,
        filtros=estado,
    )


@admin_bp.route("/auditoria/exportar.csv")
@login_required
@admin_required
def auditoria_exportar():
    """Exporta auditoria filtrada em CSV pra relatorio."""
    filtros, _ = _construir_filtros()
    eventos = (
        db.session.query(AuditLog)
        .filter(and_(*filtros) if filtros else True)
        .order_by(desc(AuditLog.criado_em))
        .limit(5000)  # cap de seguranca pra nao gerar CSV gigante
        .all()
    )
    user_ids = {e.usuario_id for e in eventos if e.usuario_id}
    users = {u.id: u for u in Usuario.query.filter(Usuario.id.in_(user_ids)).all()} if user_ids else {}

    return csv_response(
        filename=f"aggron_auditoria_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv",
        headers=["data_utc", "usuario_email", "usuario_tipo", "acao",
                 "recurso_tipo", "recurso_id", "detalhes", "ip", "user_agent"],
        rows=[
            [
                e.criado_em.isoformat(),
                users.get(e.usuario_id).email if users.get(e.usuario_id) else "",
                users.get(e.usuario_id).tipo if users.get(e.usuario_id) else "",
                e.acao,
                e.recurso_tipo or "",
                e.recurso_id or "",
                e.detalhes or "",
                e.ip or "",
                (e.user_agent or "")[:120],
            ]
            for e in eventos
        ],
    )

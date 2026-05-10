"""Helper centralizado pra registrar acoes no AuditLog.

Uso:
    from app.services.audit import audit
    from app.models import AuditLog

    audit(AuditLog.ACAO_LOGIN_OK)
    audit(AuditLog.ACAO_LEAD_CRIADO, recurso_tipo='lead', recurso_id=lead.id,
          detalhes=f"estabelecimento={lead.nome_estabelecimento[:80]}")

Filosofia:
- Best-effort: NUNCA derruba o request principal. Se falhar (DB down,
  request fora de contexto, etc), loga warning e segue.
- Auto-captura: usuario_id, ip, user_agent vem do request atual se
  disponivel — caller so passa o que muda (acao + recurso opcional).
- Insert-only commit: faz commit imediato (atomic com a transacao do
  caller seria ideal, mas adicionar audit eh secundario — perda
  ocasional de log eh aceitavel pra nao acoplar).

NUNCA salvar PII em `detalhes` (senha, token, CPF, etc).
"""
import logging

from flask import has_request_context, request
from flask_login import current_user

from app import db
from app.models import AuditLog

logger = logging.getLogger(__name__)


def audit(acao: str, *, recurso_tipo: str | None = None,
          recurso_id: int | None = None, detalhes: str | None = None,
          usuario_id: int | None = None) -> None:
    """Registra uma entrada no AuditLog. Best-effort — falha nao propaga."""
    try:
        # usuario_id explicito > current_user > None (ex: login_fail anonimo)
        uid = usuario_id
        if uid is None and has_request_context() and current_user.is_authenticated:
            uid = current_user.id

        ip = None
        ua = None
        if has_request_context():
            # Respeita ProxyFix — request.remote_addr ja vem do CF-Connecting-IP.
            ip = request.remote_addr
            ua = (request.headers.get("User-Agent") or "")[:255]

        entrada = AuditLog(
            usuario_id=uid,
            acao=acao[:50],
            recurso_tipo=recurso_tipo[:40] if recurso_tipo else None,
            recurso_id=recurso_id,
            detalhes=detalhes[:500] if detalhes else None,
            ip=ip,
            user_agent=ua,
        )
        db.session.add(entrada)
        db.session.commit()
    except Exception:  # pylint: disable=broad-except
        # Nao propaga — auditoria nao pode quebrar fluxo principal.
        try:
            db.session.rollback()
        except Exception:  # pylint: disable=broad-except
            pass
        logger.warning("AUDIT_FAIL acao=%s recurso=%s/%s",
                       acao, recurso_tipo, recurso_id, exc_info=True)

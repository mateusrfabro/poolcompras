"""
Rota de download autenticada para arquivos salvos via storage abstraction.

Regras de acesso:
- Admin: ve qualquer arquivo
- Lanchonete: ve apenas comprovantes da propria participacao
- Fornecedor: ve comprovantes de participacoes da propria rodada (cotou naquela rodada)

Nao servir arquivos via static/: o storage guarda em instance/uploads/
(fora da raiz web) e esta rota valida ownership antes de mandar o arquivo.
"""
from flask import Blueprint, abort, send_file
from flask_login import login_required, current_user
from io import BytesIO
from sqlalchemy import select
from app import db
from app.models import ParticipacaoRodada, Cotacao, Fatura, Assinatura
from app.services.storage import get_storage

uploads_bp = Blueprint("uploads", __name__, url_prefix="/uploads")


@uploads_bp.route("/<path:key>")
@login_required
def servir(key):
    """Serve o arquivo se o usuario tem permissao.

    Roteia por prefixo da key:
    - 'nf/...' -> NF de Fatura (admin OU lanchonete dona do contrato)
    - resto -> comprovante de pagamento (admin/lanchonete dona/fornecedor que cotou)
    """
    storage = get_storage()
    if not storage.exists(key):
        abort(404)

    if key.startswith("nf/"):
        return _servir_nf(key, storage)
    return _servir_comprovante(key, storage)


def _servir_nf(key, storage):
    """NF de Fatura. Acesso: admin ou lanchonete dona da assinatura."""
    fatura = db.session.execute(
        select(Fatura).where(Fatura.nf_pdf_key == key)
    ).scalar_one_or_none()
    if not fatura:
        abort(404)

    if not current_user.is_admin:
        if not current_user.is_lanchonete or not current_user.lanchonete:
            abort(403)
        assinatura = db.session.get(Assinatura, fatura.assinatura_id)
        if not assinatura or assinatura.lanchonete_id != current_user.lanchonete.id:
            abort(403)

    conteudo = storage.read(key)
    return send_file(
        BytesIO(conteudo),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"nf_{fatura.mes_referencia.strftime('%Y_%m')}_parcela_{fatura.parcela_numero}.pdf",
    )


def _servir_comprovante(key, storage):
    """Comprovante de pagamento (fluxo antigo)."""
    participacao = db.session.execute(
        select(ParticipacaoRodada).where(ParticipacaoRodada.comprovante_key == key)
    ).scalar_one_or_none()
    if not participacao:
        abort(404)

    if not _pode_ver(current_user, participacao):
        abort(403)

    conteudo = storage.read(key)
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    mimes = {"pdf": "application/pdf", "png": "image/png",
             "jpg": "image/jpeg", "jpeg": "image/jpeg"}
    mime = mimes.get(ext, "application/octet-stream")

    # Forca download em todos os tipos: PDFs podem conter JS que executa inline,
    # e imagens (png/jpg) servidas inline no mesmo origin abrem vetor de
    # HTML smuggling em browsers antigos. Defesa em profundidade.
    return send_file(
        BytesIO(conteudo),
        mimetype=mime,
        as_attachment=True,
        download_name=f"comprovante_{participacao.rodada_id}_{participacao.lanchonete_id}.{ext}",
    )


def _pode_ver(user, participacao) -> bool:
    """Autorizacao: admin ve tudo; lanchonete ve o proprio; fornecedor ve se cotou na rodada."""
    if user.is_admin:
        return True
    if user.is_lanchonete:
        return bool(user.lanchonete and user.lanchonete.id == participacao.lanchonete_id)
    if user.is_fornecedor:
        if not user.fornecedor:
            return False
        # Fornecedor tem acesso se cotou nessa rodada
        cotou = db.session.execute(
            select(Cotacao).where(
                Cotacao.rodada_id == participacao.rodada_id,
                Cotacao.fornecedor_id == user.fornecedor.id,
            )
        ).first()
        return cotou is not None
    return False

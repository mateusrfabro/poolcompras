"""
Rota de download autenticada para arquivos salvos via storage abstraction.

Regras de acesso:
- Admin: ve qualquer arquivo
- Lanchonete: ve apenas comprovantes da propria participacao
- Fornecedor: ve comprovantes de participacoes da propria rodada (cotou naquela rodada)

Nao servir arquivos via static/: o storage guarda em instance/uploads/
(fora da raiz web) e esta rota valida ownership antes de mandar o arquivo.
"""
from flask import Blueprint, abort, send_file, current_app
from flask_login import login_required, current_user
from io import BytesIO
from app.models import ParticipacaoRodada, Cotacao
from app.services.storage import get_storage

uploads_bp = Blueprint("uploads", __name__, url_prefix="/uploads")


@uploads_bp.route("/<path:key>")
@login_required
def servir(key):
    """Serve o arquivo se o usuario tem permissao."""
    # 1. Localiza a participacao dona deste comprovante
    participacao = ParticipacaoRodada.query.filter_by(comprovante_key=key).first()
    if not participacao:
        # Pode ser arquivo de outro tipo no futuro. Por agora, so comprovantes.
        abort(404)

    # 2. Checa autorizacao
    if not _pode_ver(current_user, participacao):
        abort(403)

    # 3. Le via storage e serve
    storage = get_storage()
    if not storage.exists(key):
        abort(404)

    conteudo = storage.read(key)
    # Descobre content-type pela extensao (storage sanitizou ao salvar)
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    mimes = {"pdf": "application/pdf", "png": "image/png",
             "jpg": "image/jpeg", "jpeg": "image/jpeg"}
    mime = mimes.get(ext, "application/octet-stream")

    return send_file(
        BytesIO(conteudo),
        mimetype=mime,
        as_attachment=False,  # inline (abre no browser)
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
        cotou = Cotacao.query.filter_by(
            rodada_id=participacao.rodada_id,
            fornecedor_id=user.fornecedor.id,
        ).first()
        return cotou is not None
    return False

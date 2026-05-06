"""Area financeira do admin: visao geral de assinaturas + gerenciamento de faturas.

- GET  /admin/financeiro                       lista todas assinaturas
- GET  /admin/financeiro/<assinatura_id>       detalhe + 12 faturas
- POST /admin/financeiro/fatura/<id>/marcar-paga
- POST /admin/financeiro/fatura/<id>/marcar-pendente   (desfazer baixa por engano)
- POST /admin/financeiro/fatura/<id>/nf                upload PDF da NF
- POST /admin/financeiro/lanchonete/<id>/gerar         gera contrato retroativo

NF emitida fora do sistema (NFS-e da Pref. Londrina). Admin sobe o PDF
manualmente — lanchonete baixa pelo dashboard. Integracao automatica
(NFe.io / Notazz) fica pra v2.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import (
    render_template, request, redirect, url_for, flash, abort,
)
from flask_login import login_required, current_user
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from app import db
from app.models import Assinatura, Fatura, Lanchonete
from app.services.assinatura import criar_assinatura_inicial
from app.services.storage import get_storage
from . import admin_bp, admin_required

logger = logging.getLogger(__name__)

# PDF only — NFS-e em PDF eh o padrao Pref. Londrina. Sem imagem
# (precisa do arquivo fiscal autentico, nao foto).
NF_EXTENSAO_PERMITIDA = ".pdf"
NF_MIME_PERMITIDO = {"application/pdf"}
NF_TAMANHO_MAX_BYTES = 5 * 1024 * 1024  # 5MB — NFS-e e leve


@admin_bp.route("/financeiro")
@login_required
@admin_required
def financeiro():
    """Lista assinaturas + visao geral de inadimplencia."""
    # Todas assinaturas com lanchonete + faturas (carregamento em selectin
    # pra evitar N+1 ao iterar no template).
    assinaturas = db.session.scalars(
        select(Assinatura)
        .options(joinedload(Assinatura.lanchonete), joinedload(Assinatura.faturas))
        .order_by(Assinatura.criado_em.desc())
    ).unique().all()

    # KPIs agregados
    total_pendente = db.session.scalar(
        select(func.coalesce(func.sum(Fatura.valor), 0))
        .where(Fatura.status == Fatura.STATUS_PENDENTE)
    )
    total_pago_mes = db.session.scalar(
        select(func.coalesce(func.sum(Fatura.valor), 0))
        .where(Fatura.status == Fatura.STATUS_PAGA)
        .where(func.strftime("%Y-%m", Fatura.pago_em) ==
               datetime.now(timezone.utc).strftime("%Y-%m"))
    ) if db.engine.dialect.name == "sqlite" else db.session.scalar(
        select(func.coalesce(func.sum(Fatura.valor), 0))
        .where(Fatura.status == Fatura.STATUS_PAGA)
        .where(func.to_char(Fatura.pago_em, "YYYY-MM") ==
               datetime.now(timezone.utc).strftime("%Y-%m"))
    )

    # Lanchonetes sem assinatura (legacy ou criadas antes do deploy)
    sem_contrato = db.session.scalars(
        select(Lanchonete)
        .outerjoin(Assinatura, Assinatura.lanchonete_id == Lanchonete.id)
        .where(Assinatura.id.is_(None))
        .where(Lanchonete.ativa.is_(True))
        .order_by(Lanchonete.nome_fantasia)
    ).all()

    return render_template(
        "admin/financeiro.html",
        assinaturas=assinaturas,
        total_pendente=total_pendente or 0,
        total_pago_mes=total_pago_mes or 0,
        sem_contrato=sem_contrato,
    )


@admin_bp.route("/financeiro/<int:assinatura_id>")
@login_required
@admin_required
def financeiro_detalhe(assinatura_id):
    assinatura = db.session.get(Assinatura, assinatura_id)
    if assinatura is None:
        abort(404)
    return render_template(
        "admin/financeiro_detalhe.html",
        assinatura=assinatura,
    )


@admin_bp.route("/financeiro/fatura/<int:fatura_id>/marcar-paga", methods=["POST"])
@login_required
@admin_required
def fatura_marcar_paga(fatura_id):
    fatura = db.session.get(Fatura, fatura_id)
    if fatura is None:
        abort(404)
    # Idempotencia: ja paga = no-op silencioso, evita audit duplicado
    # se admin clicar 2x.
    if fatura.status == Fatura.STATUS_PAGA:
        flash("Fatura ja estava marcada como paga.", "warning")
        return redirect(url_for("admin.financeiro_detalhe", assinatura_id=fatura.assinatura_id))

    fatura.status = Fatura.STATUS_PAGA
    fatura.pago_em = datetime.now(timezone.utc)
    fatura.pago_por_id = current_user.id
    db.session.commit()
    logger.info(
        "ADMIN_FATURA_PAGA admin=%s fatura=%s assinatura=%s valor=%s",
        current_user.id, fatura.id, fatura.assinatura_id, fatura.valor,
    )
    flash(f"Fatura #{fatura.parcela_numero} marcada como paga.", "success")
    return redirect(url_for("admin.financeiro_detalhe", assinatura_id=fatura.assinatura_id))


@admin_bp.route("/financeiro/fatura/<int:fatura_id>/marcar-pendente", methods=["POST"])
@login_required
@admin_required
def fatura_marcar_pendente(fatura_id):
    """Desfaz a baixa (admin clicou errado). Limpa pago_em + pago_por."""
    fatura = db.session.get(Fatura, fatura_id)
    if fatura is None:
        abort(404)
    if fatura.status != Fatura.STATUS_PAGA:
        flash("Fatura nao estava marcada como paga.", "warning")
        return redirect(url_for("admin.financeiro_detalhe", assinatura_id=fatura.assinatura_id))

    fatura.status = Fatura.STATUS_PENDENTE
    fatura.pago_em = None
    fatura.pago_por_id = None
    db.session.commit()
    logger.warning(
        "ADMIN_FATURA_DESFEZ_PAGAMENTO admin=%s fatura=%s",
        current_user.id, fatura.id,
    )
    flash(f"Pagamento da fatura #{fatura.parcela_numero} foi desfeito.", "success")
    return redirect(url_for("admin.financeiro_detalhe", assinatura_id=fatura.assinatura_id))


@admin_bp.route("/financeiro/fatura/<int:fatura_id>/nf", methods=["POST"])
@login_required
@admin_required
def fatura_upload_nf(fatura_id):
    """Admin sobe PDF da NFS-e. Substitui anterior se existir."""
    fatura = db.session.get(Fatura, fatura_id)
    if fatura is None:
        abort(404)
    arquivo = request.files.get("nf")
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo PDF.", "error")
        return redirect(url_for("admin.financeiro_detalhe", assinatura_id=fatura.assinatura_id))

    if not arquivo.filename.lower().endswith(NF_EXTENSAO_PERMITIDA):
        flash("Formato invalido. Envie PDF.", "error")
        return redirect(url_for("admin.financeiro_detalhe", assinatura_id=fatura.assinatura_id))
    if arquivo.mimetype not in NF_MIME_PERMITIDO:
        flash("Tipo MIME invalido. Envie PDF.", "error")
        return redirect(url_for("admin.financeiro_detalhe", assinatura_id=fatura.assinatura_id))

    # Tamanho via seek (file-like) — antes de salvar pra nao gravar inutil.
    arquivo.seek(0, 2)  # SEEK_END
    tamanho = arquivo.tell()
    arquivo.seek(0)
    if tamanho > NF_TAMANHO_MAX_BYTES:
        flash(f"Arquivo muito grande (max {NF_TAMANHO_MAX_BYTES // 1024 // 1024}MB).",
              "error")
        return redirect(url_for("admin.financeiro_detalhe", assinatura_id=fatura.assinatura_id))

    storage = get_storage()
    # Apaga NF anterior antes de subir nova (idempotencia + economia disco).
    if fatura.nf_pdf_key:
        storage.delete(fatura.nf_pdf_key)

    subdir = f"nf/{fatura.mes_referencia.year}/{fatura.mes_referencia.month:02d}"
    key = storage.save(arquivo, subdir=subdir,
                       original_name=f"nf_fatura_{fatura.id}.pdf")
    fatura.nf_pdf_key = key
    fatura.nf_emitida_em = datetime.now(timezone.utc)
    db.session.commit()
    logger.info(
        "ADMIN_FATURA_NF_UPLOAD admin=%s fatura=%s key=%s",
        current_user.id, fatura.id, key,
    )
    flash(f"NF da fatura #{fatura.parcela_numero} enviada.", "success")
    return redirect(url_for("admin.financeiro_detalhe", assinatura_id=fatura.assinatura_id))


@admin_bp.route("/financeiro/lanchonete/<int:lanchonete_id>/gerar", methods=["POST"])
@login_required
@admin_required
def gerar_contrato_retroativo(lanchonete_id):
    """Gera Assinatura + 12 Faturas pra lanchonete sem contrato (legacy)."""
    lanch = db.session.get(Lanchonete, lanchonete_id)
    if lanch is None:
        abort(404)
    a = criar_assinatura_inicial(lanch)
    logger.info(
        "ADMIN_CONTRATO_RETROATIVO admin=%s lanchonete=%s assinatura=%s",
        current_user.id, lanch.id, a.id,
    )
    flash(f"Contrato gerado pra {lanch.nome_fantasia} (12 parcelas R$500).",
          "success")
    return redirect(url_for("admin.financeiro_detalhe", assinatura_id=a.id))

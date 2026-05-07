"""CRUD de Leads — criar, ver detalhe, mover de coluna, converter em cliente."""
import logging
from datetime import datetime, timezone

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app import db, limiter
from app.models import Lead, LeadEvento, Vendedor
from . import crm_bp, vendedor_ou_admin_required

logger = logging.getLogger(__name__)


def _vendedor_pode_ver(lead) -> bool:
    """Authorizacao: admin ve tudo; vendedor so os proprios leads."""
    if current_user.is_admin:
        return True
    if current_user.is_vendedor and current_user.vendedor:
        return lead.vendedor_id == current_user.vendedor.id
    return False


@crm_bp.route("/leads/novo", methods=["GET", "POST"])
@login_required
@vendedor_ou_admin_required
@limiter.limit("60 per hour", methods=["POST"],
               error_message="Muitos leads em sequencia. Aguarde.")
def lead_novo():
    """Vendedor cadastra lead. Admin escolhe vendedor; vendedor eh o proprio."""
    if request.method == "POST":
        nome_estab = request.form.get("nome_estabelecimento", "").strip()
        if not nome_estab:
            flash("Nome do estabelecimento é obrigatório.", "error")
            return render_template("crm/lead_form.html", lead=None,
                                   form_data=request.form,
                                   vendedores=_vendedores_form())

        # Vendedor: admin escolhe; se vendedor logado, eh o proprio.
        if current_user.is_admin:
            try:
                vendedor_id = int(request.form.get("vendedor_id", ""))
            except (ValueError, TypeError):
                flash("Selecione um vendedor.", "error")
                return render_template("crm/lead_form.html", lead=None,
                                       form_data=request.form,
                                       vendedores=_vendedores_form())
            if not db.session.get(Vendedor, vendedor_id):
                flash("Vendedor inválido.", "error")
                return render_template("crm/lead_form.html", lead=None,
                                       form_data=request.form,
                                       vendedores=_vendedores_form())
        else:
            vendedor_id = current_user.vendedor.id

        lead = Lead(
            nome_estabelecimento=nome_estab,
            nome_contato=request.form.get("nome_contato", "").strip() or None,
            telefone=request.form.get("telefone", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            cidade=request.form.get("cidade", "").strip() or None,
            cnpj=request.form.get("cnpj", "").strip() or None,
            observacoes=request.form.get("observacoes", "").strip() or None,
            vendedor_id=vendedor_id,
            status=Lead.STATUS_FRIO,
        )
        db.session.add(lead)
        db.session.flush()

        # Primeiro evento: criacao do lead.
        db.session.add(LeadEvento(
            lead_id=lead.id,
            autor_usuario_id=current_user.id,
            tipo=LeadEvento.TIPO_NOTA,
            descricao=f"Lead criado por {current_user.nome_responsavel or current_user.email}.",
        ))
        db.session.commit()
        logger.info(
            "CRM_LEAD_CRIADO autor=%s lead=%s vendedor=%s",
            current_user.id, lead.id, vendedor_id,
        )
        flash(f"Lead '{nome_estab}' criado.", "success")
        return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))

    return render_template("crm/lead_form.html", lead=None,
                           form_data={}, vendedores=_vendedores_form())


@crm_bp.route("/leads/<int:lead_id>")
@login_required
@vendedor_ou_admin_required
def lead_detalhe(lead_id):
    lead = db.session.get(Lead, lead_id)
    if lead is None:
        abort(404)
    if not _vendedor_pode_ver(lead):
        abort(403)
    return render_template(
        "crm/lead_detalhe.html",
        lead=lead,
        eventos=lead.eventos,
        status_ordem=Lead.STATUS_KANBAN_ORDEM,
        status_labels={
            Lead.STATUS_FRIO: "Frio", Lead.STATUS_MORNO: "Morno",
            Lead.STATUS_QUENTE: "Quente", Lead.STATUS_FECHADO: "Fechado",
            Lead.STATUS_CANCELADO: "Cancelado",
        },
    )


@crm_bp.route("/leads/<int:lead_id>/evento", methods=["POST"])
@login_required
@vendedor_ou_admin_required
@limiter.limit("120 per hour")
def lead_evento_adicionar(lead_id):
    """Adiciona nota livre ao log do lead."""
    lead = db.session.get(Lead, lead_id)
    if lead is None:
        abort(404)
    if not _vendedor_pode_ver(lead):
        abort(403)

    descricao = request.form.get("descricao", "").strip()
    if not descricao:
        flash("Descrição vazia — nada salvo.", "warning")
        return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))

    db.session.add(LeadEvento(
        lead_id=lead.id,
        autor_usuario_id=current_user.id,
        tipo=LeadEvento.TIPO_NOTA,
        descricao=descricao[:1000],
    ))
    db.session.commit()
    flash("Nota adicionada.", "success")
    return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))


@crm_bp.route("/leads/<int:lead_id>/status", methods=["POST"])
@login_required
@vendedor_ou_admin_required
@limiter.limit("120 per hour")
def lead_mudar_status(lead_id):
    """Move lead de coluna no Kanban. Loga mudanca como evento."""
    lead = db.session.get(Lead, lead_id)
    if lead is None:
        abort(404)
    if not _vendedor_pode_ver(lead):
        abort(403)

    novo_status = request.form.get("status", "").strip()
    if novo_status not in Lead.STATUS_VALIDOS:
        flash("Status inválido.", "error")
        return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))

    if novo_status == lead.status:
        # Idempotente — sem evento ruidoso.
        return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))

    anterior = lead.status
    lead.status = novo_status
    lead.atualizado_em = datetime.now(timezone.utc)

    motivo = request.form.get("motivo", "").strip()
    descricao = f"Status: {anterior} → {novo_status}"
    if motivo:
        descricao += f". Motivo: {motivo[:500]}"
    db.session.add(LeadEvento(
        lead_id=lead.id,
        autor_usuario_id=current_user.id,
        tipo=LeadEvento.TIPO_MUDANCA_STATUS,
        descricao=descricao,
    ))
    db.session.commit()
    logger.info(
        "CRM_LEAD_STATUS lead=%s autor=%s %s -> %s",
        lead.id, current_user.id, anterior, novo_status,
    )
    flash(f"Lead movido pra '{novo_status}'.", "success")
    return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))


@crm_bp.route("/leads/<int:lead_id>/minuta")
@login_required
@vendedor_ou_admin_required
@limiter.limit("60 per hour")
def lead_minuta(lead_id):
    """Gera PDF da minuta on-the-fly. Vendedor manda pelo WhatsApp."""
    from io import BytesIO
    from flask import send_file
    from app.services.minuta_pdf import gerar_minuta_pdf

    lead = db.session.get(Lead, lead_id)
    if lead is None:
        abort(404)
    if not _vendedor_pode_ver(lead):
        abort(403)

    pdf_bytes = gerar_minuta_pdf(lead)
    nome_arquivo = (
        f"minuta_aggron_{lead.id}_{lead.nome_estabelecimento[:30]}.pdf"
        .replace(" ", "_").replace("/", "_")
    )
    # Log de auditoria — ajuda investigar quem gerou minuta de quem.
    logger.info(
        "CRM_MINUTA_GERADA lead=%s autor=%s tamanho_bytes=%s",
        lead.id, current_user.id, len(pdf_bytes),
    )
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome_arquivo,
    )


@crm_bp.route("/leads/<int:lead_id>/converter", methods=["POST"])
@login_required
@vendedor_ou_admin_required
@limiter.limit("30 per hour")
def lead_converter(lead_id):
    """Converte lead em Lanchonete + Usuario + Assinatura.

    Requer:
    - lead.email (login do cliente)
    - lead.telefone (canal de notificacao Aggron)
    Gera senha temporaria + retorna no flash pra vendedor passar via WhatsApp.
    """
    from app.models import Lanchonete, Usuario
    from app.services.passwords import hash_senha
    from app.services.assinatura import criar_assinatura_inicial
    from app.routes.admin.vendedores import _gerar_senha_temporaria

    lead = db.session.get(Lead, lead_id)
    if lead is None:
        abort(404)
    if not _vendedor_pode_ver(lead):
        abort(403)
    if lead.lanchonete_id:
        flash("Lead já foi convertido em cliente.", "warning")
        return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))

    email = (lead.email or "").strip().lower()
    if not email:
        flash("Lead precisa ter email pra virar cliente. Edite o lead primeiro.",
              "error")
        return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))
    if Usuario.query.filter_by(email=email).first():
        flash(f"Já existe usuário com email {email}. Use outro.", "error")
        return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))
    if not (lead.telefone and sum(c.isdigit() for c in lead.telefone) >= 8):
        flash("Lead precisa ter WhatsApp pra virar cliente.", "error")
        return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))

    senha = _gerar_senha_temporaria()
    usuario = Usuario(
        email=email,
        senha_hash=hash_senha(senha),
        nome_responsavel=lead.nome_contato or lead.nome_estabelecimento,
        telefone=lead.telefone,
        tipo="lanchonete",
        ativo=True,
        aceite_termos_em=datetime.now(timezone.utc),  # vendedor assume aceite no contrato
    )
    db.session.add(usuario)
    db.session.flush()

    lanchonete = Lanchonete(
        usuario_id=usuario.id,
        nome_fantasia=lead.nome_estabelecimento,
        cnpj=lead.cnpj,
        cidade=lead.cidade or "Londrina",
        ativa=True,
        vendedor_id=lead.vendedor_id,  # mantem vinculo com vendedor que fechou
    )
    db.session.add(lanchonete)
    db.session.flush()

    # Liga o lead a lanchonete pra rastreabilidade.
    lead.lanchonete_id = lanchonete.id
    lead.status = Lead.STATUS_FECHADO
    lead.atualizado_em = datetime.now(timezone.utc)

    db.session.add(LeadEvento(
        lead_id=lead.id,
        autor_usuario_id=current_user.id,
        tipo=LeadEvento.TIPO_CONVERSAO,
        descricao=f"Convertido em cliente. Lanchonete #{lanchonete.id} criada. "
                  f"Login: {email}.",
    ))
    db.session.commit()

    # Gera assinatura + 12 faturas (mesmo helper do signup).
    try:
        criar_assinatura_inicial(lanchonete)
    except Exception:
        logger.exception("CRM_CONVERSAO_FALHA_ASSINATURA lead=%s lanch=%s",
                         lead.id, lanchonete.id)

    logger.info(
        "CRM_LEAD_CONVERTIDO lead=%s autor=%s lanchonete=%s",
        lead.id, current_user.id, lanchonete.id,
    )
    flash(
        f"Cliente '{lead.nome_estabelecimento}' criado. Login: {email} / "
        f"Senha temporária: {senha} — copie e mande pelo WhatsApp pro cliente.",
        "success",
    )
    return redirect(url_for("crm.lead_detalhe", lead_id=lead.id))


def _vendedores_form():
    return db.session.scalars(
        db.select(Vendedor).where(Vendedor.ativo.is_(True))
        .order_by(Vendedor.nome)
    ).all()

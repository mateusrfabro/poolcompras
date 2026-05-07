"""Gera PDF de minuta de contrato a partir de um Lead.

Usa reportlab (puro Python, sem SaaS de assinatura). Vendedor manda
o PDF gerado pro cliente via WhatsApp; cliente assina por fora
(impressao+rabisco / Acrobat / outro). Quando devolver, admin sobe o
PDF assinado em /admin/financeiro como NF-1 ou similar.

Migracao pra Clicksign/D4Sign fica pra v2 quando o volume justificar
(~R$5-10/contrato; vira ROI claro a partir de ~50/mes).

CONTEUDO DO CONTRATO E PLACEHOLDER. Direito comercial deve revisar
antes de mandar pra cliente real. Ajustar TEMPLATE_TERMOS quando
houver versao validada juridicamente.
"""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)


# Defaults Aggron — ajustar se mudar plano ou contato.
VALOR_MENSAL_PADRAO = Decimal("500.00")
PARCELAS_PADRAO = 12
RAZAO_AGGRON = "Aggron Central de Compras"  # CNPJ/razao real preencher quando tiver
EMAIL_AGGRON = "contato@aggron.com.br"
EMAIL_FINANCEIRO = "financeiro@aggron.com.br"


# Texto resumido do contrato. JURIDICO DEVE REVISAR.
TEMPLATE_TERMOS = [
    (
        "1. Objeto",
        "A {AGGRON} provê acesso ao seu serviço de central de compras "
        "cooperativa para hamburguerias, agregando volume entre clientes "
        "para obter melhores preços de fornecedores parceiros."
    ),
    (
        "2. Mensalidade",
        "O CONTRATANTE pagará à AGGRON o valor de R$ {VALOR_FORMAT} "
        "({PARCELAS} parcelas mensais), via PIX ou boleto, com "
        "vencimento todo dia {DIA_VENC} de cada mês. A primeira parcela "
        "vence em {DATA_PRIMEIRA_PARCELA}."
    ),
    (
        "3. Vigência",
        "O contrato tem vigência de 12 meses a partir da assinatura, "
        "renovável automaticamente por igual período salvo manifestação "
        "em contrário com 30 dias de antecedência."
    ),
    (
        "4. Pagamento dos fornecedores",
        "O pagamento dos insumos comprados via Aggron é feito DIRETO "
        "pelo CONTRATANTE ao fornecedor escolhido em cada rodada, "
        "via PIX, sem intermediação financeira da Aggron."
    ),
    (
        "5. Nota Fiscal",
        "A AGGRON emitirá Nota Fiscal de Serviço Eletrônica (NFS-e) "
        "no município de Londrina/PR a cada parcela paga, enviada para "
        "o e-mail cadastrado pelo CONTRATANTE."
    ),
    (
        "6. Confidencialidade",
        "Volumes, preços e dados comerciais trocados na plataforma são "
        "confidenciais entre as partes envolvidas em cada rodada."
    ),
    (
        "7. LGPD",
        "Tratamento de dados pessoais segue a Política de Privacidade "
        "publicada em aggron.com.br/privacidade."
    ),
    (
        "8. Foro",
        "Fica eleito o foro da Comarca de Londrina/PR para dirimir "
        "qualquer questão oriunda deste contrato."
    ),
]


def gerar_minuta_pdf(lead, valor_mensal: Decimal | None = None,
                     parcelas: int = PARCELAS_PADRAO,
                     dia_vencimento: int | None = None) -> bytes:
    """Gera o PDF da minuta como bytes pra Flask servir via send_file.

    Args:
        lead: instancia de Lead com nome_estabelecimento, cnpj, email,
              telefone, nome_contato, cidade.
        valor_mensal: valor da parcela. Default R$500.
        parcelas: total de parcelas. Default 12.
        dia_vencimento: dia do mes do vencimento. Default = hoje.dia (cap 28).

    Returns:
        bytes do PDF (use BytesIO no Flask send_file).
    """
    valor = valor_mensal if valor_mensal is not None else VALOR_MENSAL_PADRAO
    hoje = date.today()
    dia_venc = dia_vencimento or min(hoje.day, 28)

    primeiro_mes = hoje.month + 1 if hoje.month < 12 else 1
    primeiro_ano = hoje.year if hoje.month < 12 else hoje.year + 1
    primeiro_dia = min(dia_venc, 28)
    data_primeira = date(primeiro_ano, primeiro_mes, primeiro_dia)

    contexto = {
        "AGGRON": RAZAO_AGGRON,
        "VALOR_FORMAT": f"{valor:.2f}".replace(".", ","),
        "PARCELAS": parcelas,
        "DIA_VENC": dia_venc,
        "DATA_PRIMEIRA_PARCELA": data_primeira.strftime("%d/%m/%Y"),
    }

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2.0 * cm, rightMargin=2.0 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm,
        title=f"Minuta Aggron - {lead.nome_estabelecimento}",
        author="Aggron",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"],
                        textColor=colors.HexColor("#1D3557"),
                        fontSize=18, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"],
                        textColor=colors.HexColor("#1D3557"),
                        fontSize=12, spaceAfter=4, spaceBefore=10)
    body = ParagraphStyle("body", parent=styles["BodyText"],
                          fontSize=10, leading=14, alignment=4)  # justify
    small = ParagraphStyle("small", parent=styles["BodyText"],
                           fontSize=8, textColor=colors.grey)

    story = []

    # Cabecalho
    story.append(Paragraph(
        "Contrato de Prestação de Serviços — Aggron", h1
    ))
    story.append(Paragraph(
        f"Documento gerado em {hoje.strftime('%d/%m/%Y')} · "
        f"{EMAIL_AGGRON}", small
    ))
    story.append(Spacer(1, 0.6 * cm))

    # Partes
    story.append(Paragraph("Partes", h2))
    partes_data = [
        ["CONTRATADA", RAZAO_AGGRON],
        ["E-mail comercial", EMAIL_AGGRON],
        ["E-mail financeiro", EMAIL_FINANCEIRO],
        ["", ""],
        ["CONTRATANTE", lead.nome_estabelecimento or "—"],
        ["Responsável", lead.nome_contato or "—"],
        ["CNPJ", lead.cnpj or "_______________________"],
        ["E-mail", lead.email or "_______________________"],
        ["WhatsApp", lead.telefone or "_______________________"],
        ["Cidade", lead.cidade or "Londrina/PR"],
    ]
    t = Table(partes_data, colWidths=[4.5 * cm, 12 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 3), (1, 3), 0.3, colors.HexColor("#dddddd")),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.6 * cm))

    # Termos
    story.append(Paragraph("Termos", h2))
    for titulo, texto in TEMPLATE_TERMOS:
        try:
            texto_renderizado = texto.format(**contexto)
        except KeyError:
            texto_renderizado = texto
        story.append(Paragraph(f"<b>{titulo}</b>", body))
        story.append(Paragraph(texto_renderizado, body))
        story.append(Spacer(1, 0.25 * cm))

    # Assinaturas
    story.append(Spacer(1, 1.0 * cm))
    story.append(Paragraph("Assinaturas", h2))
    story.append(Spacer(1, 1.5 * cm))
    sig_data = [
        ["_____________________________________",
         "_____________________________________"],
        ["Aggron", lead.nome_estabelecimento or "Contratante"],
        [hoje.strftime("Londrina/PR, %d/%m/%Y"), ""],
    ]
    sig = Table(sig_data, colWidths=[8 * cm, 8 * cm])
    sig.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(sig)

    doc.build(story)
    return buffer.getvalue()

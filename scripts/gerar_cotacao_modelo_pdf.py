"""Gera PDF modelo de Cotacao Consolidada Aggron.

Demo da aplicacao das skills `pdf` + `aggron-brand-guidelines` num
artefato real. Output em docs/exemplos/cotacao_modelo.pdf.

Identidade visual fiel ao manual oficial:
- Verde Aggron #0F2A1F (fundo capa)
- Verde Claro #166B3D (header da tabela, linhas-guia)
- Ouro #D4AF37 (acentos, totais, tagline)
- Cinza Claro #E6E6E6 (texto sobre dark)
- Grafite #111418 (fundo principal de paginas internas)
- Tagline oficial: "Conectamos quem fornece com quem faz acontecer."

Tipografia: fallback Helvetica (reportlab default). Pra usar Sora/Inter
em prod, registrar TTFs com pdfmetrics.registerFont (deixado como TODO).
"""
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)
from reportlab.lib.utils import ImageReader
from reportlab.lib.enums import TA_LEFT, TA_RIGHT

# === Tokens oficiais da skill aggron-brand-guidelines ===
VERDE_AGGRON  = HexColor("#0F2A1F")
VERDE_CLARO   = HexColor("#166B3D")
OURO          = HexColor("#D4AF37")
GRAFITE       = HexColor("#111418")
GRAFITE_DARK  = HexColor("#0a0c0e")
CINZA_CLARO   = HexColor("#E6E6E6")
CINZA_MUTED   = HexColor("#8b929a")

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "app" / "static" / "images" / "logo-aggron-symbol.png"
OUT_PATH  = ROOT / "docs" / "exemplos" / "cotacao_modelo.pdf"

# === Dados FICTICIOS de demo — nunca usar em prod ===
RODADA = {
    "nome": "Rodada Maio 2026 #14",
    "data_fechamento": "31/05/2026",
    "lanchonetes_participando": 7,
    "total_pedidos": 142,
    "economia_estimada": "R$ 4.832,40",
}

ITENS = [
    # (produto, qtd, unidade, fornecedor, preco_unit, total)
    ("Hamburguer artesanal 150g (caixa 20un)", 38, "cx", "D'Sul Carnes Premium",  "R$ 178,00", "R$ 6.764,00"),
    ("Pao brioche selado 100mm",                 145, "cx", "Panificadora Trigo Dourado", "R$ 26,40",  "R$ 3.828,00"),
    ("Queijo cheddar fatiado (1kg)",              92, "kg", "Latticini Sao Paulo",       "R$ 38,90",  "R$ 3.578,80"),
    ("Bacon defumado em manta (3kg)",             28, "un", "D'Sul Carnes Premium",      "R$ 52,00",  "R$ 1.456,00"),
    ("Batata pre-frita congelada (2,5kg)",        61, "sc", "Frioz Distribuidora",       "R$ 28,50",  "R$ 1.738,50"),
    ("Maionese verde artesanal (3kg)",            18, "pt", "Empório do Molho",          "R$ 41,90",  "R$ 754,20"),
    ("Cebola caramelizada (1kg)",                 14, "un", "Empório do Molho",          "R$ 24,80",  "R$ 347,20"),
    ("Refrigerante lata 350ml (fardo 12un)",      85, "fd", "Distrib Bebidas Norte",     "R$ 36,00",  "R$ 3.060,00"),
    ("Embalagem kraft hamburguer (cx 200)",       12, "cx", "EcoPack Solucoes",          "R$ 89,00",  "R$ 1.068,00"),
]

TOTAL_GERAL = "R$ 22.594,70"


def _draw_page_background(canvas_obj, doc):
    """Pinta o fundo da pagina inteiro de grafite escuro + borda topo."""
    canvas_obj.saveState()
    # Fundo
    canvas_obj.setFillColor(GRAFITE_DARK)
    canvas_obj.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    # Linha verde 2pt no topo (acima da margem)
    canvas_obj.setFillColor(VERDE_CLARO)
    canvas_obj.rect(0, A4[1] - 3, A4[0], 3, fill=1, stroke=0)
    # Header com nome do documento
    canvas_obj.setFillColor(CINZA_MUTED)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawString(20 * mm, A4[1] - 12 * mm,
                          f"AGGRON  /  Cotacao Consolidada  /  {RODADA['nome']}")
    canvas_obj.drawRightString(A4[0] - 20 * mm, A4[1] - 12 * mm,
                               f"Pagina {canvas_obj.getPageNumber()}")
    # Footer
    canvas_obj.setFillColor(CINZA_MUTED)
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.drawCentredString(A4[0] / 2, 12 * mm,
                                 "Aggron Central de Compras Cooperativa  |  Londrina-PR  |  contato@aggron.com.br")
    canvas_obj.setFillColor(OURO)
    canvas_obj.drawCentredString(A4[0] / 2, 7 * mm,
                                 "Conectamos quem fornece com quem faz acontecer.")
    canvas_obj.restoreState()


def _draw_cover_page(canvas_obj, doc):
    """Pinta a capa: fundo verde Aggron + logo dourado + tagline."""
    canvas_obj.saveState()
    # Fundo verde Aggron pleno
    canvas_obj.setFillColor(VERDE_AGGRON)
    canvas_obj.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    # Logo centralizado
    if LOGO_PATH.exists():
        try:
            img = ImageReader(str(LOGO_PATH))
            logo_w = 50 * mm
            logo_h = 50 * mm
            canvas_obj.drawImage(img, (A4[0] - logo_w) / 2, A4[1] / 2 + 20 * mm,
                                 width=logo_w, height=logo_h, mask='auto')
        except OSError as e:
            print(f"Aviso: nao foi possivel embedar logo: {e}")
    # Wordmark
    canvas_obj.setFillColor(CINZA_CLARO)
    canvas_obj.setFont("Helvetica-Bold", 36)
    # letter-spacing emulado: desenha caractere a caractere
    text = "AGGRON"
    char_spacing = 8
    char_widths = [canvas_obj.stringWidth(c, "Helvetica-Bold", 36) for c in text]
    total_w = sum(char_widths) + char_spacing * (len(text) - 1)
    x = (A4[0] - total_w) / 2
    y = A4[1] / 2 + 5 * mm
    for c, w in zip(text, char_widths):
        canvas_obj.drawString(x, y, c)
        x += w + char_spacing

    # Tagline oficial em ouro
    canvas_obj.setFillColor(OURO)
    canvas_obj.setFont("Helvetica", 11)
    canvas_obj.drawCentredString(A4[0] / 2, A4[1] / 2 - 8 * mm,
                                 "CONECTAMOS QUEM FORNECE COM QUEM FAZ ACONTECER")
    # Linha decorativa ouro
    canvas_obj.setStrokeColor(OURO)
    canvas_obj.setLineWidth(0.8)
    canvas_obj.line(A4[0] / 2 - 35 * mm, A4[1] / 2 - 13 * mm,
                    A4[0] / 2 + 35 * mm, A4[1] / 2 - 13 * mm)
    # Titulo do documento
    canvas_obj.setFillColor(CINZA_CLARO)
    canvas_obj.setFont("Helvetica-Bold", 22)
    canvas_obj.drawCentredString(A4[0] / 2, A4[1] / 2 - 35 * mm, "Cotacao Consolidada")
    canvas_obj.setFillColor(CINZA_MUTED)
    canvas_obj.setFont("Helvetica", 12)
    canvas_obj.drawCentredString(A4[0] / 2, A4[1] / 2 - 43 * mm, RODADA["nome"])
    # Bloco de metadados em baixo
    meta_y = 60 * mm
    canvas_obj.setFillColor(CINZA_MUTED)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawString(25 * mm, meta_y, "GERADO EM")
    canvas_obj.drawString(85 * mm, meta_y, "FECHAMENTO")
    canvas_obj.drawString(145 * mm, meta_y, "PARTICIPANTES")
    canvas_obj.setFillColor(CINZA_CLARO)
    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.drawString(25 * mm, meta_y - 6 * mm,
                          datetime.now().strftime("%d/%m/%Y as %H:%M"))
    canvas_obj.drawString(85 * mm, meta_y - 6 * mm, RODADA["data_fechamento"])
    canvas_obj.drawString(145 * mm, meta_y - 6 * mm,
                          f"{RODADA['lanchonetes_participando']} lanchonetes")
    # Rodape capa
    canvas_obj.setFillColor(CINZA_MUTED)
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.drawCentredString(A4[0] / 2, 15 * mm,
                                 "Aggron Central de Compras Cooperativa  |  Londrina-PR")
    canvas_obj.restoreState()


def _format_table():
    """Monta a tabela de itens com estilizacao oficial."""
    header = ["Produto", "Qtd", "Un.", "Fornecedor", "Preco unit.", "Total"]
    data = [header] + [list(row) for row in ITENS]
    # Tabela
    col_widths = [70 * mm, 15 * mm, 12 * mm, 45 * mm, 22 * mm, 25 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        # Header em verde claro
        ('BACKGROUND',   (0, 0), (-1, 0), VERDE_CLARO),
        ('TEXTCOLOR',    (0, 0), (-1, 0), CINZA_CLARO),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0), 9),
        ('ALIGN',        (0, 0), (-1, 0), 'LEFT'),
        ('ALIGN',        (1, 0), (2, 0), 'RIGHT'),
        ('ALIGN',        (4, 0), (5, 0), 'RIGHT'),
        ('TOPPADDING',   (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 9),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        # Corpo
        ('TEXTCOLOR',    (0, 1), (-1, -1), CINZA_CLARO),
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',     (0, 1), (-1, -1), 9),
        ('ALIGN',        (1, 1), (2, -1), 'RIGHT'),
        ('ALIGN',        (4, 1), (5, -1), 'RIGHT'),
        ('TOPPADDING',   (0, 1), (-1, -1), 7),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 7),
        # Total em ouro com texto grafite
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        # Zebra striping sutil
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [GRAFITE, GRAFITE_DARK]),
        # Bordas
        ('LINEBELOW',    (0, 0), (-1, 0), 0.5, OURO),
        ('LINEBELOW',    (0, -1), (-1, -1), 0.3, HexColor("#2a3038")),
    ])
    table.setStyle(style)
    return table


def gerar_pdf():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT_PATH),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=22 * mm, bottomMargin=22 * mm,
        title=f"Cotacao Consolidada — {RODADA['nome']}",
        author="Aggron Central de Compras Cooperativa",
    )

    styles = getSampleStyleSheet()
    style_h1 = ParagraphStyle(
        "h1_aggron", parent=styles["Heading1"],
        fontName="Helvetica-Bold", fontSize=18,
        textColor=CINZA_CLARO, spaceAfter=4, leading=22,
    )
    style_h2 = ParagraphStyle(
        "h2_aggron", parent=styles["Heading2"],
        fontName="Helvetica-Bold", fontSize=13,
        textColor=CINZA_CLARO, spaceBefore=12, spaceAfter=6, leading=16,
    )
    style_eyebrow = ParagraphStyle(
        "eyebrow", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=8,
        textColor=OURO, leading=12, spaceAfter=2,
    )
    style_body = ParagraphStyle(
        "body_aggron", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10,
        textColor=CINZA_CLARO, leading=14, spaceAfter=4,
    )
    style_muted = ParagraphStyle(
        "muted", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8.5,
        textColor=CINZA_MUTED, leading=12,
    )
    style_kpi_label = ParagraphStyle(
        "kpi_label", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=7.5,
        textColor=CINZA_MUTED, leading=10, alignment=TA_LEFT,
    )
    style_kpi_num = ParagraphStyle(
        "kpi_num", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=22,
        textColor=OURO, leading=24, alignment=TA_LEFT,
    )
    style_total_label = ParagraphStyle(
        "total_label", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=10,
        textColor=CINZA_MUTED, leading=14, alignment=TA_RIGHT,
    )
    style_total_num = ParagraphStyle(
        "total_num", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=20,
        textColor=OURO, leading=24, alignment=TA_RIGHT,
    )

    flowables = []

    # === Pagina 1: Capa (renderizada via onPage) ===
    # SimpleDocTemplate exige conteudo; usamos um Spacer + PageBreak.
    flowables.append(Spacer(1, 1))
    flowables.append(PageBreak())

    # === Pagina 2+: Sumario executivo ===
    flowables.append(Paragraph("RODADA EM REVISAO", style_eyebrow))
    flowables.append(Paragraph(RODADA["nome"], style_h1))
    flowables.append(Paragraph(
        "Cotacao consolidada apos coleta de pedidos das lanchonetes participantes "
        "e negociacao final com fornecedores. Este documento e referencia oficial "
        "do fechamento.", style_body))
    flowables.append(Spacer(1, 12))

    # KPIs em 3 colunas (asimetria estilo Stripe)
    kpi_data = [[
        Paragraph("LANCHONETES PARTICIPANDO", style_kpi_label),
        Paragraph("PEDIDOS COLETADOS", style_kpi_label),
        Paragraph("ECONOMIA ESTIMADA", style_kpi_label),
    ], [
        Paragraph(str(RODADA["lanchonetes_participando"]), style_kpi_num),
        Paragraph(str(RODADA["total_pedidos"]), style_kpi_num),
        Paragraph(RODADA["economia_estimada"], style_kpi_num),
    ]]
    kpi_table = Table(kpi_data, colWidths=[55*mm, 55*mm, 55*mm])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GRAFITE),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('LINEBEFORE', (1, 0), (1, -1), 0.5, HexColor("#2a3038")),
        ('LINEBEFORE', (2, 0), (2, -1), 0.5, HexColor("#2a3038")),
    ]))
    flowables.append(kpi_table)
    flowables.append(Spacer(1, 18))

    # Secao: itens
    flowables.append(Paragraph("Itens consolidados", style_h2))
    flowables.append(Paragraph(
        "Quantidades agregadas por SKU apos pedido das lanchonetes. "
        "Precos finais ja contemplam volume da rodada.", style_muted))
    flowables.append(Spacer(1, 8))
    flowables.append(_format_table())
    flowables.append(Spacer(1, 6))

    # Total geral em destaque (faixa ouro)
    total_data = [[
        Paragraph("TOTAL CONSOLIDADO DA RODADA", style_total_label),
        Paragraph(TOTAL_GERAL, style_total_num),
    ]]
    total_table = Table(total_data, colWidths=[124*mm, 65*mm])
    total_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GRAFITE),
        ('TOPPADDING', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('LEFTPADDING', (0, 0), (-1, -1), 18),
        ('RIGHTPADDING', (0, 0), (-1, -1), 18),
        ('LINEABOVE', (0, 0), (-1, 0), 2, OURO),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, OURO),
    ]))
    flowables.append(total_table)
    flowables.append(Spacer(1, 18))

    # Nota final
    flowables.append(Paragraph("Proximos passos", style_h2))
    flowables.append(Paragraph(
        "1. Cada lanchonete recebe individualmente sua parcela com instrucoes de pagamento.", style_body))
    flowables.append(Paragraph(
        "2. O pagamento e direto ao fornecedor (Aggron nao intermedia financeiro).", style_body))
    flowables.append(Paragraph(
        "3. Apos confirmacao do pagamento, fornecedor inicia entrega no prazo combinado.", style_body))
    flowables.append(Paragraph(
        "4. Recebimento confirmado pela lanchonete encerra o ciclo da rodada.", style_body))

    def _on_first_page(canv, doc_):
        _draw_cover_page(canv, doc_)

    def _on_later_pages(canv, doc_):
        _draw_page_background(canv, doc_)

    doc.build(flowables,
              onFirstPage=_on_first_page,
              onLaterPages=_on_later_pages)
    print(f"OK: {OUT_PATH}")
    return OUT_PATH


if __name__ == "__main__":
    gerar_pdf()

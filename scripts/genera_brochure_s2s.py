# -*- coding: utf-8 -*-
"""
Genera la brochure informativa per accesso immobile S2S, partendo dal contenuto
originale di Gi Group e adattandolo:
- Logo: assets/logo-S2S-def.gif al posto di "GI Group"
- Ragione sociale: "Service to Service S.r.l." (S2S) al posto di "Gi Group S.p.A."
- Sede: S.S. Appia 7 Bis Km 800, presso Parco Commerciale "Appia Center",
        81030 Teverola CE
- Pagina 4: norme di emergenza con icone vettoriali al posto delle immagini
  bitmap dell'originale (riprodotte con primitive ReportLab/canvas).
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak,
    KeepTogether, Flowable
)
from pathlib import Path
import copy

ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = ROOT / "assets" / "logo-S2S-def.gif"
OUTPUT = ROOT / "output" / "S2S_Brochure_Accesso_Immobile.pdf"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# ─── Costanti documento ───
COMPANY_NAME = "Service to Service S.r.l."
COMPANY_SHORT = "S2S"
ADDRESS_LINE_1 = 'S.S. Appia 7 Bis Km 800, Parco Commerciale "Appia Center"'
ADDRESS_LINE_2 = "81030 Teverola (CE)"
ADDRESS_FULL = (
    'S.S. Appia 7 Bis Km 800, presso Parco Commerciale "Appia Center", '
    "81030 Teverola CE"
)
EMAIL_PRIVACY = "privacy@s2s.it"
EMAIL_DPO = "dpo@s2s.it"

DOC_REV = "Rev.2_20260509"
DOC_ALLEGATO = "Allegato 01_PEI"

# Colori
BRAND_BLUE = HexColor("#0E3B7A")
BRAND_GREY = HexColor("#666666")
RULE_COLOR = HexColor("#CCCCCC")
TEXT_DARK = HexColor("#222222")
EMERGENCY_RED = HexColor("#C62828")
EMERGENCY_BG = HexColor("#FFEBEE")
SECTION_BG = HexColor("#FFE0B2")
SECTION_FG = HexColor("#BF360C")
WARN_YELLOW = HexColor("#FBC02D")
SAFE_GREEN = HexColor("#2E7D32")
INFO_BLUE = HexColor("#1565C0")


# ─── Header/Footer su ogni pagina ───
def draw_page_header_footer(canvas, doc):
    canvas.saveState()
    page_w, page_h = A4

    # ── Header layout fisso 30mm ──
    header_top = page_h - 6 * mm                  # margin top header
    header_bottom = page_h - 32 * mm              # bottom della banda header
    line_y = header_bottom                         # linea sotto header

    # Logo a sinistra
    logo_x = 18 * mm
    logo_y = header_bottom + 2 * mm
    logo_w = 26 * mm
    logo_h = 18 * mm
    if LOGO_PATH.exists():
        try:
            canvas.drawImage(
                str(LOGO_PATH), logo_x, logo_y,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            canvas.setFont("Helvetica-Bold", 14)
            canvas.setFillColor(BRAND_BLUE)
            canvas.drawString(logo_x, logo_y + 6 * mm, "S2S")

    # Box destro (Allegato / Rev / Pagina) — più stretto e in alto
    box_w = 50 * mm
    box_h = 22 * mm
    box_x = page_w - 18 * mm - box_w   # 18mm margine destro
    box_y = header_bottom + 0 * mm
    canvas.setStrokeColor(black)
    canvas.setLineWidth(0.5)
    canvas.rect(box_x, box_y, box_w, box_h, stroke=1, fill=0)
    # 3 righe interne
    row_h = box_h / 3
    canvas.line(box_x, box_y + 2 * row_h, box_x + box_w, box_y + 2 * row_h)
    canvas.line(box_x, box_y + 1 * row_h, box_x + box_w, box_y + 1 * row_h)
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(TEXT_DARK)
    canvas.drawCentredString(box_x + box_w / 2, box_y + 2 * row_h + row_h / 2 - 3, DOC_ALLEGATO)
    canvas.drawCentredString(box_x + box_w / 2, box_y + 1 * row_h + row_h / 2 - 3, DOC_REV)
    total = getattr(doc, "_totalPages", "5")
    canvas.drawCentredString(
        box_x + box_w / 2, box_y + row_h / 2 - 3,
        f"Pagina {doc.page} di {total}",
    )

    # Centro: titolo + sottotitoli (lo spazio è da logo_x+logo_w+4mm a box_x-4mm)
    text_x = logo_x + logo_w + 6 * mm
    text_max = box_x - text_x - 4 * mm
    canvas.setFont("Helvetica-Bold", 12)
    canvas.setFillColor(TEXT_DARK)
    canvas.drawString(text_x, header_bottom + 16 * mm, COMPANY_NAME)
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(BRAND_GREY)
    canvas.drawString(text_x, header_bottom + 11 * mm,
                      "Brochure informativa per l'accesso alla struttura")
    # Indirizzo su due righe per non sovrapporsi al box
    canvas.drawString(text_x, header_bottom + 7 * mm, ADDRESS_LINE_1)
    canvas.drawString(text_x, header_bottom + 3 * mm, ADDRESS_LINE_2)

    # Linea sotto header
    canvas.setStrokeColor(RULE_COLOR)
    canvas.setLineWidth(0.5)
    canvas.line(15 * mm, line_y - 1 * mm, page_w - 15 * mm, line_y - 1 * mm)

    # ── Footer ──
    canvas.setFont("Helvetica-Oblique", 7)
    canvas.setFillColor(BRAND_GREY)
    footer_y = 12 * mm
    canvas.drawCentredString(page_w / 2, footer_y,
                              f"Questo documento è di proprietà di {COMPANY_NAME}.")
    canvas.drawCentredString(page_w / 2, footer_y - 4 * mm,
                              f"Il suo contenuto, intero o in parte, non può essere copiato, "
                              f"utilizzato o divulgato a terzi senza autorizzazione scritta di "
                              f"{COMPANY_NAME}.")

    canvas.restoreState()


# ─── Stili paragrafi ───
styles = getSampleStyleSheet()
body = ParagraphStyle("Body", parent=styles["BodyText"],
                      fontName="Helvetica", fontSize=10, leading=13,
                      alignment=TA_JUSTIFY, textColor=TEXT_DARK, spaceAfter=4)
section_h = ParagraphStyle("SectionH", parent=styles["Heading2"],
                           fontName="Helvetica-Bold", fontSize=12, leading=16,
                           textColor=BRAND_BLUE, spaceBefore=10, spaceAfter=6,
                           alignment=TA_CENTER)
sub_h = ParagraphStyle("SubH", parent=styles["Heading3"],
                       fontName="Helvetica-Bold", fontSize=11, leading=14,
                       textColor=TEXT_DARK, spaceBefore=8, spaceAfter=2)
center_b = ParagraphStyle("CenterBold", parent=body, fontName="Helvetica-Bold",
                          fontSize=11, alignment=TA_CENTER, textColor=BRAND_BLUE,
                          spaceBefore=10, spaceAfter=6)
emergency_h = ParagraphStyle("EmergencyH", parent=section_h, fontSize=22,
                             textColor=EMERGENCY_RED, spaceBefore=4, spaceAfter=14)


# ─── Icone vettoriali (Flowable custom) ───
class Icon(Flowable):
    """Disegna un'icona vettoriale di emergenza/sicurezza dentro un quadrato.
    `kind` può essere uno di:
      fire-extinguisher, hydrant, alarm-button, electric-panel, you-are-here,
      exit-arrow, emergency-exit, emergency-stairs, meeting-point, first-aid,
      no-smoking, no-trash-fire, fire, no-elevator, evacuate-walk, phone,
      lock, danger
    """
    def __init__(self, kind, size=14 * mm):
        super().__init__()
        self.kind = kind
        self.size = size
        self.width = size
        self.height = size

    def draw(self):
        c = self.canv
        s = self.size
        c.saveState()
        # Sfondo: bianco con bordo grigio sottile
        c.setStrokeColor(HexColor("#BBBBBB"))
        c.setLineWidth(0.4)
        c.rect(0, 0, s, s, stroke=1, fill=0)
        cx, cy = s / 2, s / 2
        k = self.kind

        def red():    c.setFillColor(HexColor("#E53935")); c.setStrokeColor(HexColor("#B71C1C"))
        def green():  c.setFillColor(HexColor("#43A047")); c.setStrokeColor(HexColor("#1B5E20"))
        def yellow(): c.setFillColor(HexColor("#FBC02D")); c.setStrokeColor(HexColor("#F57F17"))
        def blue():   c.setFillColor(HexColor("#1E88E5")); c.setStrokeColor(HexColor("#0D47A1"))
        def black_():  c.setFillColor(black); c.setStrokeColor(black)
        def white_():  c.setFillColor(white); c.setStrokeColor(black)

        if k == "fire-extinguisher":
            # Estintore: corpo rosso + maniglia + base
            red(); c.roundRect(cx - 2.5*mm, cy - 4*mm, 5*mm, 8*mm, 1*mm, fill=1, stroke=1)
            black_(); c.rect(cx - 0.5*mm, cy + 4*mm, 1*mm, 1.2*mm, fill=1, stroke=1)
            c.line(cx + 0.5*mm, cy + 4.6*mm, cx + 2.2*mm, cy + 4.6*mm)
            c.setFillColor(white); c.rect(cx - 1.5*mm, cy - 1*mm, 3*mm, 2*mm, fill=1, stroke=0)

        elif k == "hydrant":
            # Idrante: corpo rosso ad arco + fori
            red(); c.roundRect(cx - 3*mm, cy - 4*mm, 6*mm, 8*mm, 1.5*mm, fill=1, stroke=1)
            white_(); c.circle(cx - 1.2*mm, cy + 1.5*mm, 0.6*mm, fill=1, stroke=0)
            c.circle(cx + 1.2*mm, cy + 1.5*mm, 0.6*mm, fill=1, stroke=0)
            c.circle(cx, cy - 1*mm, 0.6*mm, fill=1, stroke=0)

        elif k == "alarm-button":
            # Pulsante allarme: cerchio rosso con quadrato bianco interno
            red(); c.circle(cx, cy, 4*mm, fill=1, stroke=1)
            white_(); c.rect(cx - 1.5*mm, cy - 1.5*mm, 3*mm, 3*mm, fill=1, stroke=0)

        elif k == "electric-panel":
            # Quadro elettrico: rettangolo giallo con saetta nera
            yellow(); c.roundRect(cx - 3.5*mm, cy - 3.5*mm, 7*mm, 7*mm, 0.8*mm, fill=1, stroke=1)
            # Saetta semplificata
            c.setFillColor(black)
            p = c.beginPath()
            p.moveTo(cx + 0.5*mm, cy + 2.5*mm)
            p.lineTo(cx - 1.5*mm, cy)
            p.lineTo(cx, cy)
            p.lineTo(cx - 0.5*mm, cy - 2.5*mm)
            p.lineTo(cx + 1.5*mm, cy - 0.2*mm)
            p.lineTo(cx, cy - 0.2*mm)
            p.lineTo(cx + 0.5*mm, cy + 2.5*mm)
            p.close()
            c.drawPath(p, fill=1, stroke=0)

        elif k == "you-are-here":
            # Posizione: cerchio blu con punto
            blue(); c.circle(cx, cy, 3.5*mm, fill=1, stroke=1)
            white_(); c.circle(cx, cy, 1.2*mm, fill=1, stroke=0)

        elif k == "exit-arrow":
            # Direzione di esodo: freccia verde verso destra
            green(); c.rect(cx - 4*mm, cy - 1.5*mm, 5*mm, 3*mm, fill=1, stroke=0)
            p = c.beginPath()
            p.moveTo(cx + 1*mm, cy - 3*mm); p.lineTo(cx + 1*mm, cy + 3*mm)
            p.lineTo(cx + 4*mm, cy); p.close()
            c.drawPath(p, fill=1, stroke=0)

        elif k == "emergency-exit":
            # Uscita emergenza: omino verde + porta + freccia
            green(); c.rect(cx - 3.5*mm, cy - 4*mm, 7*mm, 8*mm, fill=1, stroke=0)
            # omino bianco
            c.setFillColor(white)
            c.circle(cx - 1.2*mm, cy + 2*mm, 0.8*mm, fill=1, stroke=0)
            c.rect(cx - 1.5*mm, cy - 2*mm, 0.6*mm, 3*mm, fill=1, stroke=0)
            c.rect(cx - 1.0*mm, cy - 2*mm, 0.6*mm, 3*mm, fill=1, stroke=0)
            # freccia laterale
            p = c.beginPath()
            p.moveTo(cx + 1*mm, cy - 1*mm); p.lineTo(cx + 1*mm, cy + 1*mm)
            p.lineTo(cx + 3*mm, cy); p.close()
            c.drawPath(p, fill=1, stroke=0)

        elif k == "emergency-stairs":
            # Scala emergenza: omino + scaletta
            green(); c.rect(cx - 3.5*mm, cy - 4*mm, 7*mm, 8*mm, fill=1, stroke=0)
            c.setFillColor(white)
            # gradini
            for i in range(3):
                c.rect(cx + 0.0*mm + i*0.7*mm, cy - 3*mm + i*1.0*mm,
                       2*mm - i*0.3*mm, 0.6*mm, fill=1, stroke=0)
            # omino
            c.circle(cx - 1.3*mm, cy + 2*mm, 0.7*mm, fill=1, stroke=0)
            c.rect(cx - 1.6*mm, cy - 1*mm, 0.6*mm, 3*mm, fill=1, stroke=0)

        elif k == "meeting-point":
            # Punto di raduno: 4 frecce convergenti su pallino centrale
            green(); c.rect(cx - 3.5*mm, cy - 3.5*mm, 7*mm, 7*mm, fill=1, stroke=0)
            c.setFillColor(white)
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                p = c.beginPath()
                p.moveTo(cx + dx*1.5*mm - dy*0.6*mm, cy + dy*1.5*mm - dx*0.6*mm)
                p.lineTo(cx + dx*1.5*mm + dy*0.6*mm, cy + dy*1.5*mm + dx*0.6*mm)
                p.lineTo(cx + dx*0.4*mm, cy + dy*0.4*mm)
                p.close()
                c.drawPath(p, fill=1, stroke=0)
            c.circle(cx, cy, 0.6*mm, fill=1, stroke=0)

        elif k == "first-aid":
            # Cassetta primo soccorso: quadrato verde con croce bianca
            green(); c.roundRect(cx - 3.5*mm, cy - 3*mm, 7*mm, 6*mm, 0.5*mm, fill=1, stroke=0)
            white_();
            c.rect(cx - 0.7*mm, cy - 1.6*mm, 1.4*mm, 3.2*mm, fill=1, stroke=0)
            c.rect(cx - 1.6*mm, cy - 0.7*mm, 3.2*mm, 1.4*mm, fill=1, stroke=0)

        elif k == "no-smoking":
            # No fumare: cerchio rosso barrato + sigaretta
            black_(); c.rect(cx - 2.5*mm, cy - 0.4*mm, 5*mm, 0.8*mm, fill=1, stroke=0)  # sigaretta
            c.setFillColor(HexColor("#E0E0E0")); c.rect(cx + 1.7*mm, cy - 0.4*mm, 1*mm, 0.8*mm, fill=1, stroke=0)
            # cerchio rosso barrato
            c.setStrokeColor(HexColor("#E53935")); c.setLineWidth(1.2)
            c.circle(cx, cy, 4*mm, stroke=1, fill=0)
            c.line(cx - 2.8*mm, cy - 2.8*mm, cx + 2.8*mm, cy + 2.8*mm)

        elif k == "no-trash-fire":
            # Vietato gettare materiale infiammabile: cestino + fiamma + cerchio barrato
            black_(); c.rect(cx - 1.8*mm, cy - 2*mm, 3.6*mm, 3*mm, fill=0, stroke=1)
            c.line(cx - 2*mm, cy + 1*mm, cx + 2*mm, cy + 1*mm)
            # fiamma piccola
            c.setFillColor(HexColor("#FB8C00"))
            p = c.beginPath()
            p.moveTo(cx - 1*mm, cy - 1.5*mm); p.lineTo(cx + 1*mm, cy - 1.5*mm)
            p.lineTo(cx, cy + 0.5*mm); p.close()
            c.drawPath(p, fill=1, stroke=0)
            # cerchio barrato
            c.setStrokeColor(HexColor("#E53935")); c.setLineWidth(1.2)
            c.circle(cx, cy, 4*mm, stroke=1, fill=0)
            c.line(cx - 2.8*mm, cy - 2.8*mm, cx + 2.8*mm, cy + 2.8*mm)

        elif k == "fire":
            # Fiamma
            c.setFillColor(HexColor("#FB8C00"))
            p = c.beginPath()
            p.moveTo(cx, cy - 3*mm)
            p.curveTo(cx + 3*mm, cy - 1*mm, cx + 1.5*mm, cy + 2*mm, cx, cy + 3*mm)
            p.curveTo(cx - 1.5*mm, cy + 2*mm, cx - 3*mm, cy - 1*mm, cx, cy - 3*mm)
            c.drawPath(p, fill=1, stroke=0)
            c.setFillColor(HexColor("#FFEB3B"))
            p2 = c.beginPath()
            p2.moveTo(cx, cy - 1*mm)
            p2.curveTo(cx + 1.5*mm, cy + 0*mm, cx + 0.7*mm, cy + 1.5*mm, cx, cy + 2*mm)
            p2.curveTo(cx - 0.7*mm, cy + 1.5*mm, cx - 1.5*mm, cy, cx, cy - 1*mm)
            c.drawPath(p2, fill=1, stroke=0)

        elif k == "no-elevator":
            # Vietato ascensore: rettangolo + cerchio barrato
            black_(); c.rect(cx - 2*mm, cy - 3*mm, 4*mm, 6*mm, fill=0, stroke=1)
            c.line(cx, cy - 3*mm, cx, cy + 3*mm)
            # frecce su/giù
            c.line(cx - 1*mm, cy + 1*mm, cx - 1*mm, cy + 2.5*mm)
            c.line(cx + 1*mm, cy - 1*mm, cx + 1*mm, cy - 2.5*mm)
            # cerchio barrato
            c.setStrokeColor(HexColor("#E53935")); c.setLineWidth(1.2)
            c.circle(cx, cy, 4*mm, stroke=1, fill=0)
            c.line(cx - 2.8*mm, cy - 2.8*mm, cx + 2.8*mm, cy + 2.8*mm)

        elif k == "evacuate-walk":
            # Personale che evacua: omino in movimento (verde, simbolo standard)
            green(); c.rect(cx - 3.5*mm, cy - 3.5*mm, 7*mm, 7*mm, fill=1, stroke=0)
            c.setFillColor(white)
            c.circle(cx - 0.5*mm, cy + 2.2*mm, 0.7*mm, fill=1, stroke=0)
            # corpo (linea inclinata)
            c.setLineWidth(1)
            c.setStrokeColor(white)
            c.line(cx - 0.5*mm, cy + 1.4*mm, cx + 0.5*mm, cy - 1.5*mm)
            # gambe
            c.line(cx + 0.5*mm, cy - 1.5*mm, cx - 1*mm, cy - 3*mm)
            c.line(cx + 0.5*mm, cy - 1.5*mm, cx + 2*mm, cy - 3*mm)
            # braccia
            c.line(cx - 0.5*mm, cy + 1*mm, cx - 2.2*mm, cy + 0.5*mm)
            c.line(cx - 0.5*mm, cy + 0.5*mm, cx + 2.2*mm, cy + 1.5*mm)

        elif k == "phone":
            # Telefono di emergenza
            c.setFillColor(HexColor("#1E88E5"))
            c.roundRect(cx - 3*mm, cy - 4*mm, 6*mm, 8*mm, 1*mm, fill=1, stroke=0)
            c.setFillColor(white)
            c.rect(cx - 2*mm, cy - 1*mm, 4*mm, 4*mm, fill=1, stroke=0)
            c.circle(cx, cy - 2.5*mm, 0.6*mm, fill=1, stroke=0)

        elif k == "lock":
            # Lucchetto
            c.setFillColor(HexColor("#FB8C00"))
            c.roundRect(cx - 2.5*mm, cy - 3*mm, 5*mm, 5*mm, 0.5*mm, fill=1, stroke=0)
            c.setLineWidth(1.4)
            c.setStrokeColor(HexColor("#FB8C00"))
            c.arc(cx - 2*mm, cy + 1*mm, cx + 2*mm, cy + 4*mm, 0, 180)
            white_(); c.circle(cx, cy - 0.5*mm, 0.6*mm, fill=1, stroke=0)

        elif k == "danger":
            # Triangolo di pericolo giallo con !
            yellow()
            p = c.beginPath()
            p.moveTo(cx, cy + 3.5*mm); p.lineTo(cx + 3.5*mm, cy - 2.5*mm)
            p.lineTo(cx - 3.5*mm, cy - 2.5*mm); p.close()
            c.drawPath(p, fill=1, stroke=1)
            black_(); c.rect(cx - 0.3*mm, cy - 1*mm, 0.6*mm, 2.5*mm, fill=1, stroke=0)
            c.circle(cx, cy - 1.8*mm, 0.4*mm, fill=1, stroke=0)

        elif k == "videocamera":
            # Videocamera sorveglianza
            c.setFillColor(HexColor("#37474F"))
            c.rect(cx - 3*mm, cy - 1.5*mm, 5*mm, 3*mm, fill=1, stroke=0)
            p = c.beginPath()
            p.moveTo(cx + 2*mm, cy - 1*mm); p.lineTo(cx + 2*mm, cy + 1*mm)
            p.lineTo(cx + 3.5*mm, cy + 0.6*mm); p.lineTo(cx + 3.5*mm, cy - 0.6*mm)
            p.close()
            c.drawPath(p, fill=1, stroke=0)
            white_(); c.circle(cx - 1*mm, cy + 2.5*mm, 0.5*mm, fill=1, stroke=0)

        elif k == "badge":
            # Badge con clip
            c.setFillColor(HexColor("#1E88E5"))
            c.roundRect(cx - 2.5*mm, cy - 3*mm, 5*mm, 5.5*mm, 0.5*mm, fill=1, stroke=0)
            black_(); c.rect(cx - 0.5*mm, cy + 2.5*mm, 1*mm, 1*mm, fill=1, stroke=0)
            white_();
            c.circle(cx, cy + 0.5*mm, 1*mm, fill=1, stroke=0)
            c.rect(cx - 1.5*mm, cy - 2.2*mm, 3*mm, 0.8*mm, fill=1, stroke=0)

        c.restoreState()


def icon_with_label(kind, label, label_w=70 * mm):
    """Cella tabella: icona + testo accanto."""
    return Table(
        [[Icon(kind), Paragraph(label, body)]],
        colWidths=[16 * mm, label_w],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ])
    )


# ─── Costruzione contenuto ───
story = []

# === Pagina 1 ===
story.append(Spacer(1, 4 * mm))
story.append(Paragraph(
    "Gentile Ospite,<br/>"
    f"Le forniamo nel seguito alcune informazioni in merito all'accesso "
    f"nell'immobile di {ADDRESS_FULL}, sede di {COMPANY_NAME} e delle "
    f"società del gruppo {COMPANY_SHORT}.",
    body,
))
story.append(Spacer(1, 4 * mm))

# Sezione BADGE con icona accanto
story.append(Table(
    [[Icon("badge"), Paragraph("BADGE ACCESSO", section_h)]],
    colWidths=[16 * mm, 150 * mm],
    style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")])
))
story.append(Paragraph(
    "Le verrà fornito un badge per accedere ai piani; il badge è "
    "necessario al fine di monitorare l'accesso e la sua presenza "
    "nell'immobile, consente l'apertura delle porte a vetri al piano "
    "cui deve recarsi.<br/>"
    "L'attribuzione del badge si limita a registrare la presenza degli "
    "ospiti del palazzo senza identificare le singole persone.",
    body,
))

# Sezione VIDEOSORVEGLIANZA con icona
story.append(Table(
    [[Icon("videocamera"), Paragraph("VIDEOSORVEGLIANZA", section_h)]],
    colWidths=[16 * mm, 150 * mm],
    style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")])
))
story.append(Paragraph(
    "Le segnaliamo che le aree di accesso alla struttura (hall di ingresso) "
    "e ai piani (sbarchi ascensori) sono soggette a videosorveglianza come "
    "indicato dalla relativa cartellonistica.",
    body,
))

story.append(Paragraph("ACCESSO ALLA RETE WI-FI", section_h))
story.append(Paragraph(
    f"Per accedere alla rete internet {COMPANY_SHORT} può chiedere "
    "informazioni al personale della Società.",
    body,
))

story.append(Paragraph("INFORMATIVA PRIVACY", section_h))
story.append(Paragraph(
    "Ai sensi e per gli effetti dell'articolo 13 del Regolamento UE 2016/679 "
    f"(GDPR), e nel rispetto del Provvedimento del Garante per la protezione "
    f"dei dati personali in materia di videosorveglianza emesso in data 8 "
    f"aprile 2010, {COMPANY_NAME} (di seguito anche \"{COMPANY_SHORT}\" o la "
    f"\"Società\") fornisce alcune informazioni riguardanti il trattamento "
    f"dei dati personali da Lei forniti in occasione dell'accesso presso la "
    f"nostra sede nonché delle immagini riprese dal sistema di videosorveglianza.",
    body,
))

story.append(Paragraph("A — Finalità del trattamento e basi giuridiche", sub_h))
story.append(Paragraph(
    "Il trattamento dei dati personali raccolti e delle immagini registrate "
    "è effettuato per garantire la sicurezza delle persone e la conservazione "
    "del patrimonio aziendale. In particolare, i dati personali raccolti "
    "all'atto della consegna del badge vengono trattati esclusivamente al "
    "fine di identificare la Sua persona e di indirizzarLa correttamente al "
    "personale con cui ha appuntamento e per poter garantire la tutela "
    "dell'incolumità fisica dei soggetti presenti all'interno dell'immobile "
    "nel caso si verificassero situazioni di pericolo.<br/>"
    "La base giuridica di tale trattamento è rinvenibile nel perseguimento "
    "del legittimo interesse del Titolare (art. 6 par. 1, lett. f del GDPR).",
    body,
))

story.append(PageBreak())

# === Pagina 2 ===
story.append(Paragraph("B — Periodo di conservazione dei dati", sub_h))
story.append(Paragraph(
    "I Suoi dati personali (nome e cognome) vengono raccolti dal personale "
    "della <i>reception</i> e registrati su un supporto cartaceo e conservati "
    "per un periodo pari a 12 mesi.<br/>"
    "Le immagini riprese tramite il sistema di videosorveglianza vengono "
    "registrate e conservate per un periodo massimo di 24 ore, dopodiché "
    "vengono automaticamente cancellate; le immagini registrate non sono "
    "collegate e/o incrociate con altri codici identificativi, carte "
    "elettroniche o dispositivi che rendano identificabile la persona.<br/>"
    "Decorso il termine di conservazione sopra indicati, i dati sono "
    "distrutti o resi anonimi.",
    body,
))

story.append(Paragraph("C — Modalità del trattamento", sub_h))
story.append(Paragraph(
    "Il trattamento dei dati è improntato ai principi di correttezza, "
    "liceità e trasparenza e minimizzazione dei dati (privacy by design); "
    "potrà essere effettuato sia manualmente che attraverso modalità "
    "automatizzate atte a memorizzarli, elaborarli e trasmetterli ed "
    "avverrà mediante misure tecniche e organizzative adeguate, per quanto "
    "di ragione e allo stato della tecnica, a garantire, fra l'altro, la "
    "sicurezza, la riservatezza, l'integrità, la disponibilità e la "
    "resilienza dei sistemi e dei servizi, evitando il rischio di perdita, "
    "distruzione, accesso o divulgazione non autorizzati o, comunque, uso "
    "illecito, nonché mediante misure ragionevoli per cancellare o "
    "rettificare tempestivamente i dati inesatti rispetto alle finalità "
    "per le quali sono trattati.",
    body,
))

story.append(Paragraph("D — Natura del conferimento dei dati e conseguenze del rifiuto", sub_h))
story.append(Paragraph(
    "Il conferimento dei dati è necessario per consentirLe l'accesso presso "
    "la nostra sede; il Suo rifiuto comporta l'impossibilità di accedere ai locali.",
    body,
))

story.append(Paragraph("E — Destinatari dei dati", sub_h))
story.append(Paragraph(
    "I Suoi dati potranno essere trattati esclusivamente dai dipendenti "
    "delle funzioni aziendali autorizzate al trattamento in quanto deputate "
    "al perseguimento delle finalità sopraindicate. Tali dipendenti hanno "
    "ricevuto, al riguardo, adeguate istruzioni operative.<br/>"
    f"I Suoi dati personali possono essere altresì trattati da soggetti "
    f"esterni, espressamente nominati responsabili del trattamento, che "
    f"forniscono a {COMPANY_SHORT}:<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;– Servizi di Vigilanza<br/>"
    "&nbsp;&nbsp;&nbsp;&nbsp;– Servizi di postalizzazione delle comunicazioni.<br/>"
    "L'elenco aggiornato contenente i destinatari è disponibile presso la "
    f"nostra sede sociale oppure inviando una comunicazione e-mail a "
    f"<b>{EMAIL_PRIVACY}</b>.<br/>"
    "I dati personali conferiti dai candidati non saranno oggetto di diffusione.",
    body,
))

story.append(Paragraph("F — Dati di contatto del Titolare", sub_h))
story.append(Paragraph(
    f"Titolare del Trattamento dei dati personali è <b>{COMPANY_NAME}</b>, "
    f"con sede in {ADDRESS_FULL}, in persona del legale rappresentante "
    f"pro tempore.",
    body,
))

story.append(Paragraph("G — Dati di contatto del Data Protection Officer (DPO)", sub_h))
story.append(Paragraph(
    f"Responsabile della protezione dei dati (DPO) è contattabile al "
    f"seguente recapito:<br/>"
    f"{ADDRESS_FULL}, all'attenzione del Data Protection Officer, "
    f"email <b>{EMAIL_DPO}</b>.",
    body,
))

story.append(Paragraph("H — Diritti dell'interessato", sub_h))
story.append(Paragraph(
    "In conformità a quanto previsto dal GDPR, Lei ha diritto di esercitare "
    "i diritti ivi indicati ed in particolare:",
    body,
))

story.append(PageBreak())

# === Pagina 3 ===
diritti = [
    ("Art. 15 diritto di accesso",
     "ottenere conferma che sia o meno in corso un trattamento di dati "
     "personali che La riguardano e, in tal caso, ricevere informazioni "
     "relativamente a, tra le altre, finalità del trattamento, categorie "
     "di dati personali trattati e periodo di conservazione e destinatari "
     "cui questi dati possono essere comunicati;"),
    ("Art. 16 diritto di rettifica",
     "ottenere senza giustificato ritardo, la rettifica dei dati personali "
     "inesatti che La riguardano e l'integrazione dei dati incompleti;"),
    ("Art. 17 diritto alla cancellazione",
     "ottenere, senza ingiustificato ritardo, la cancellazione dei dati "
     "personali che La riguardano, nei casi previsti dal GDPR;"),
    ("Art. 18 diritto di limitazione",
     "ottenere limitazioni di trattamento nei casi espressamente previsti dal GDPR;"),
    ("Art. 20 diritto alla portabilità",
     "ricevere in un formato strutturato, di uso comune e leggibile da un "
     "dispositivo automatico, i dati personali che La riguardano forniti al "
     "Titolare, e di ottenere che gli stessi siano trasmessi ad altro "
     "titolare senza impedimenti, nei casi previsti dal GDPR;"),
    ("Art. 21 diritto di opposizione",
     "opporsi al trattamento dei dati personali che La riguardano, salvo "
     "che sussistano motivi legittimi per il Titolare di continuare il trattamento."),
]
for art, desc in diritti:
    story.append(Paragraph(f"<b>{art}</b>: {desc}", body))

story.append(Paragraph(
    "Tali diritti possono essere esercitati scrivendo a mezzo posta, "
    f"all'indirizzo sotto indicato, oppure tramite posta elettronica al "
    f"seguente indirizzo e-mail: <b>{EMAIL_PRIVACY}</b>. Resta inteso che, "
    f"laddove la richiesta sia presentata mediante mezzi elettronici, le "
    f"informazioni saranno fornite in un formato elettronico di uso comune.<br/>"
    "In ogni caso l'interessato ha sempre diritto di proporre reclamo al "
    "Garante per la Protezione dei Dati Personali, ai sensi dell'art. 77 "
    "del GDPR, qualora ritenga che il trattamento dei propri dati sia "
    "contrario alla normativa in vigore.",
    body,
))

story.append(Spacer(1, 4 * mm))
story.append(Paragraph("SICUREZZA", section_h))
story.append(Paragraph(
    f"La informiamo, infine, che esiste un piano di emergenza interno "
    f"all'azienda. Sono stati identificati gli addetti alla gestione delle "
    "emergenze. Vi invitiamo a prendere visione delle planimetrie di "
    "evacuazione posizionate ad ogni piano.<br/>"
    "<b>In caso di allarme:</b> seguite le indicazioni della persona di "
    "riferimento o dei componenti della squadra di emergenza. Uscite dai "
    "locali chiudendo la porta. Non utilizzate gli ascensori, ma il corpo "
    "scala raggiungibile seguendo le indicazioni della cartellonistica di "
    "evacuazione che vi porterà fino al punto di raduno stabilito nel "
    "piazzale all'esterno dello stabile. Una volta giunti al punto di "
    "raduno ricercate la persona di riferimento e non allontanatevi senza "
    "autorizzazione. Non rientrate per nessun motivo nell'edificio prima "
    "del segnale di cessato allarme.",
    body,
))

story.append(PageBreak())

# === Pagina 4 — Norme di emergenza con icone vettoriali ===
story.append(Spacer(1, 2 * mm))
story.append(Paragraph("NORME DI COMPORTAMENTO IN CASO DI", section_h))
story.append(Paragraph("EMERGENZA", emergency_h))
story.append(Paragraph(
    "<b>1.</b> MANTENERE LA CALMA. NON FARSI PRENDERE DAL PANICO.<br/>"
    "<b>2.</b> SEGUIRE LE ISTRUZIONI QUI RIPORTATE PER UN ESODO RAPIDO E ORDINATO.",
    ParagraphStyle("EmIntro", parent=body, alignment=TA_CENTER, fontSize=11,
                   spaceAfter=10),
))


def section_box(title_text, bg_color, fg_color):
    return Paragraph(
        f"<b>{title_text}</b>",
        ParagraphStyle("EmSec", parent=sub_h, alignment=TA_CENTER,
                       backColor=bg_color, textColor=fg_color, borderPadding=4,
                       spaceBefore=4, spaceAfter=2)
    )


# MISURE PREVENTIVE — icone vietato fumare e vietato gettare materiale infiammabile
story.append(section_box("MISURE PREVENTIVE", SECTION_BG, SECTION_FG))
story.append(Table(
    [[
        icon_with_label("no-smoking",
                        "<b>È VIETATO FUMARE</b> e fare uso di fiamme libere "
                        "nelle zone prescritte.", label_w=70*mm),
        icon_with_label("no-trash-fire",
                        "<b>È VIETATO GETTARE</b> nei cestini mozziconi di sigarette, "
                        "materiali infiammabili, ecc.", label_w=70*mm),
    ]],
    colWidths=[88*mm, 88*mm],
    style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ])
))
story.append(Spacer(1, 4 * mm))

# IN CASO DI EMERGENZA con triangolo pericolo + telefono
story.append(section_box("IN CASO DI EMERGENZA", SECTION_BG, SECTION_FG))
story.append(Table(
    [[
        Icon("danger"),
        Paragraph(
            "Chiunque rilevi fatti anomali che possano far presumere un'imminente "
            "\"situazione di pericolo\", che non possa essere prontamente eliminata "
            "con interventi diretti (es. uso di estintore portatile in caso di "
            "incendio) deve immediatamente chiamare il numero di emergenza interno.",
            body
        ),
        Icon("phone"),
        Paragraph("<b>NUMERO DI<br/>EMERGENZA</b><br/>Reception S2S",
                  ParagraphStyle("Phone", parent=body, alignment=TA_CENTER,
                                 fontSize=9, leading=11)),
    ]],
    colWidths=[16*mm, 110*mm, 16*mm, 32*mm],
    style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (2, 0), (3, 0), 0.6, EMERGENCY_RED),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ])
))
story.append(Spacer(1, 4 * mm))

# IN CASO DI INCENDIO
story.append(section_box("IN CASO DI INCENDIO", SECTION_BG, SECTION_FG))
story.append(Table(
    [[
        Icon("fire"),
        Paragraph(
            "• Dare l'allarme verbalmente o mediante il pulsante di emergenza "
            "più vicino.<br/>"
            "• Utilizzare i mezzi antincendio disponibili per estinguere "
            "l'incendio compatibilmente con le proprie capacità e senza "
            "compromettere la propria incolumità.",
            body
        ),
        Icon("fire-extinguisher"),
    ]],
    colWidths=[16*mm, 142*mm, 16*mm],
    style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")])
))
story.append(Spacer(1, 4 * mm))

# IN CASO DI EVACUAZIONE
story.append(section_box("IN CASO DI EVACUAZIONE", SECTION_BG, SECTION_FG))
story.append(Table(
    [[
        Icon("no-elevator"),
        Paragraph(
            "<b>È VIETATO SERVIRSI DEGLI ASCENSORI.</b> Evitare di correre, "
            "spingersi e urlare.",
            body
        ),
        Icon("evacuate-walk"),
    ]],
    colWidths=[16*mm, 142*mm, 16*mm],
    style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")])
))
story.append(Spacer(1, 2 * mm))
story.append(Paragraph(
    "<b>Personale e visitatori/ospiti:</b><br/>"
    "• Abbandonare regolarmente i locali seguendo i cartelli indicatori "
    "in conformità alle istruzioni impartite dal Responsabile incaricato.<br/>"
    "• Il personale non in grado di muoversi autonomamente attenda con calma "
    "l'arrivo dei soccorritori incaricati.<br/><br/>"
    "<b>In caso di presenza di fumo</b> portarsi un fazzoletto inumidito "
    "sulla via dell'aria e proseguire possibilmente lateralmente lungo il "
    "verso di fuga. Evitare di privarsi della ricerca di persone o di "
    "oggetti personali se non richiesto dagli addetti alla emergenza.",
    body
))

story.append(PageBreak())

# === Pagina 5 — Legenda icone ===
story.append(Spacer(1, 2 * mm))
story.append(Paragraph("LEGENDA SIMBOLI DI SICUREZZA", section_h))
story.append(Paragraph(
    "Riferimento dei simboli presenti sulla cartellonistica aziendale "
    "(planimetrie di evacuazione esposte ad ogni piano):",
    ParagraphStyle("LegIntro", parent=body, alignment=TA_CENTER, spaceAfter=8),
))

# Tabella legenda 2 colonne x 5 righe
legenda_rows = [
    [
        icon_with_label("fire-extinguisher", "<b>ESTINTORI</b><br/>Segnaletica rossa"),
        icon_with_label("exit-arrow", "<b>DIREZIONE DI ESODO</b><br/>Segnaletica verde con freccia"),
    ],
    [
        icon_with_label("hydrant", "<b>IDRANTI UNI 45</b><br/>Segnaletica rossa"),
        icon_with_label("emergency-exit", "<b>USCITA DI EMERGENZA</b><br/>Segnaletica verde"),
    ],
    [
        icon_with_label("alarm-button", "<b>PULSANTE DI EMERGENZA</b><br/>Segnaletica rossa"),
        icon_with_label("emergency-stairs", "<b>SCALA DI EMERGENZA</b><br/>Segnaletica verde"),
    ],
    [
        icon_with_label("electric-panel", "<b>QUADRO ELETTRICO</b><br/>Segnaletica gialla"),
        icon_with_label("meeting-point", "<b>PUNTO DI RADUNO</b><br/>Segnaletica verde"),
    ],
    [
        icon_with_label("you-are-here", "<b>VOSTRA POSIZIONE</b><br/>Segnaletica blu"),
        icon_with_label("first-aid", "<b>CASSETTA DI PRIMO SOCCORSO</b><br/>Segnaletica verde con croce bianca"),
    ],
]
story.append(Table(
    legenda_rows,
    colWidths=[88*mm, 88*mm],
    style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE_COLOR),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE_COLOR),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])
))

story.append(Spacer(1, 8 * mm))
story.append(Paragraph(
    "<i>Per i dettagli grafici e i percorsi specifici di evacuazione fare "
    "riferimento alle planimetrie di sicurezza esposte ad ogni piano della "
    f"sede di Teverola di {COMPANY_NAME}.</i>",
    ParagraphStyle("EmFoot", parent=body, alignment=TA_CENTER, fontSize=9,
                   textColor=BRAND_GREY, spaceBefore=6),
))


# ─── Generazione PDF (due passate per "Pagina N di TOT") ───
def _build(file_path, total=None):
    doc = SimpleDocTemplate(
        str(file_path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=36 * mm, bottomMargin=22 * mm,
        title=f"{COMPANY_SHORT} — Brochure accesso immobile",
        author=COMPANY_NAME,
    )

    def _on_page(canvas, doc_):
        if total is not None:
            doc_._totalPages = total
        draw_page_header_footer(canvas, doc_)

    holder = {"n": 1}
    if total is None:
        def _on_page_count(canvas, doc_):
            holder["n"] = doc_.page
            draw_page_header_footer(canvas, doc_)
        doc.build(copy.deepcopy(story), onFirstPage=_on_page_count, onLaterPages=_on_page_count)
        return holder["n"]
    else:
        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
        return total


tmp = OUTPUT.with_suffix(".__count.pdf")
total = _build(tmp, total=None)
_build(OUTPUT, total=total)
try:
    tmp.unlink(missing_ok=True)
except Exception:
    pass

print(f"OK — generato: {OUTPUT}")
print(f"Pagine: {total}")

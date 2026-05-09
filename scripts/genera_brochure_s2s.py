# -*- coding: utf-8 -*-
"""
Genera la brochure informativa per accesso immobile S2S, partendo dal contenuto
originale di Gi Group e adattandolo:
- Logo: assets/logo-S2S-def.gif al posto di "GI Group"
- Ragione sociale: "Service to Service S.r.l." (S2S) al posto di "Gi Group S.p.A."
- Sede: S.S. Appia 7 Bis Km 800, presso Parco Commerciale "Appia Center",
        81030 Teverola CE
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak,
    KeepTogether
)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = ROOT / "assets" / "logo-S2S-def.gif"
OUTPUT = ROOT / "output" / "S2S_Brochure_Accesso_Immobile.pdf"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# ─── Costanti documento ───
COMPANY_NAME = "Service to Service S.r.l."
COMPANY_SHORT = "S2S"
ADDRESS_LINE = (
    'S.S. Appia 7 Bis Km 800, presso Parco Commerciale "Appia Center", '
    "81030 Teverola CE"
)
EMAIL_PRIVACY = "privacy@s2s.it"
EMAIL_DPO = "dpo@s2s.it"

# Header text (apparirà su ogni pagina via canvas)
HEADER_TITLE = COMPANY_NAME
HEADER_SUB = "Brochure informativa per l'accesso all'immobile"
HEADER_SUB2 = ADDRESS_LINE
DOC_REV = "Rev.1_20260509"
DOC_ALLEGATO = "Allegato 01_PEI"

# Colori brand S2S (blu del logo)
BRAND_BLUE = HexColor("#0E3B7A")
BRAND_GREY = HexColor("#666666")
RULE_COLOR = HexColor("#CCCCCC")
TEXT_DARK = HexColor("#222222")


# ─── Header/Footer su ogni pagina ───
def draw_page_header_footer(canvas, doc):
    canvas.saveState()

    # ── Header banda ──
    page_w, page_h = A4
    header_h = 28 * mm
    canvas.setStrokeColor(RULE_COLOR)
    canvas.setLineWidth(0.5)
    canvas.line(15 * mm, page_h - header_h - 2 * mm,
                page_w - 15 * mm, page_h - header_h - 2 * mm)

    # Logo a sinistra (height 18mm)
    if LOGO_PATH.exists():
        try:
            canvas.drawImage(
                str(LOGO_PATH),
                15 * mm,
                page_h - header_h + 4 * mm,
                width=30 * mm,
                height=20 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            # fallback testo
            canvas.setFont("Helvetica-Bold", 14)
            canvas.setFillColor(BRAND_BLUE)
            canvas.drawString(15 * mm, page_h - 18 * mm, "S2S")

    # Titolo al centro
    canvas.setFont("Helvetica-Bold", 11)
    canvas.setFillColor(TEXT_DARK)
    canvas.drawString(60 * mm, page_h - 14 * mm, HEADER_TITLE)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BRAND_GREY)
    canvas.drawString(60 * mm, page_h - 19 * mm, HEADER_SUB)
    canvas.drawString(60 * mm, page_h - 23 * mm, HEADER_SUB2)

    # Riquadro destro: Allegato + Rev + Pagina
    box_x = page_w - 60 * mm
    box_y = page_h - header_h + 2 * mm
    canvas.setStrokeColor(RULE_COLOR)
    canvas.setLineWidth(0.4)
    canvas.rect(box_x, box_y, 45 * mm, 22 * mm, stroke=1, fill=0)
    canvas.line(box_x, box_y + 14 * mm, box_x + 45 * mm, box_y + 14 * mm)
    canvas.line(box_x, box_y + 7 * mm, box_x + 45 * mm, box_y + 7 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(TEXT_DARK)
    canvas.drawCentredString(box_x + 22.5 * mm, box_y + 18 * mm, DOC_ALLEGATO)
    canvas.drawCentredString(box_x + 22.5 * mm, box_y + 10 * mm, DOC_REV)
    canvas.drawCentredString(
        box_x + 22.5 * mm, box_y + 3 * mm,
        f"Pagina {doc.page} di {doc._totalPages if hasattr(doc, '_totalPages') else '4'}",
    )

    # ── Footer ──
    canvas.setFont("Helvetica-Oblique", 7)
    canvas.setFillColor(BRAND_GREY)
    footer_y = 12 * mm
    canvas.drawCentredString(
        page_w / 2,
        footer_y,
        f"Questo documento è di proprietà di {COMPANY_NAME}.",
    )
    canvas.drawCentredString(
        page_w / 2,
        footer_y - 4 * mm,
        f"Il suo contenuto, intero o in parte, non può essere copiato, utilizzato o "
        f"divulgato a terzi senza autorizzazione scritta di {COMPANY_NAME}.",
    )

    canvas.restoreState()


# ─── Stili paragrafi ───
styles = getSampleStyleSheet()
body = ParagraphStyle(
    "Body",
    parent=styles["BodyText"],
    fontName="Helvetica",
    fontSize=10,
    leading=13,
    alignment=TA_JUSTIFY,
    textColor=TEXT_DARK,
    spaceAfter=4,
)
section_h = ParagraphStyle(
    "SectionH",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=12,
    leading=16,
    textColor=BRAND_BLUE,
    spaceBefore=10,
    spaceAfter=6,
    alignment=TA_CENTER,
)
sub_h = ParagraphStyle(
    "SubH",
    parent=styles["Heading3"],
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=14,
    textColor=TEXT_DARK,
    spaceBefore=8,
    spaceAfter=2,
)
center_b = ParagraphStyle(
    "CenterBold",
    parent=body,
    fontName="Helvetica-Bold",
    fontSize=11,
    alignment=TA_CENTER,
    textColor=BRAND_BLUE,
    spaceBefore=10,
    spaceAfter=6,
)
emergency_h = ParagraphStyle(
    "EmergencyH",
    parent=section_h,
    fontSize=18,
    textColor=HexColor("#C62828"),
    spaceBefore=4,
    spaceAfter=10,
)


# ─── Costruzione contenuto ───
story = []

# === Pagina 1 ===
story.append(Spacer(1, 4 * mm))
story.append(Paragraph(f"{COMPANY_NAME} — Sede di Teverola (CE)", center_b))
story.append(Paragraph(
    "Gentile Ospite,<br/>"
    f"Le forniamo nel seguito alcune informazioni in merito all'accesso "
    f"nell'immobile di {ADDRESS_LINE}, sede di {COMPANY_NAME} e delle "
    f"società del gruppo {COMPANY_SHORT}.",
    body,
))
story.append(Spacer(1, 4 * mm))

story.append(Paragraph("BADGE ACCESSO", section_h))
story.append(Paragraph(
    "Le verrà fornito un badge per accedere ai piani; il badge è "
    "necessario al fine di monitorare l'accesso e la sua presenza "
    "nell'immobile, consente l'apertura delle porte a vetri al piano "
    "cui deve recarsi.<br/>"
    "L'attribuzione del badge si limita a registrare la presenza degli "
    "ospiti del palazzo senza identificare le singole persone.",
    body,
))

story.append(Paragraph("VIDEOSORVEGLIANZA", section_h))
story.append(Paragraph(
    "Le segnaliamo che le aree di accesso all'immobile (hall di ingresso) "
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
    f"con sede in {ADDRESS_LINE}, in persona del legale rappresentante "
    f"pro tempore.",
    body,
))

story.append(Paragraph("G — Dati di contatto del Data Protection Officer (DPO)", sub_h))
story.append(Paragraph(
    f"Responsabile della protezione dei dati (DPO) è contattabile al "
    f"seguente recapito:<br/>"
    f"{ADDRESS_LINE}, all'attenzione del Data Protection Officer, "
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
    f"all'azienda.<br/>"
    "Sono stati identificati gli addetti alla gestione delle emergenze. "
    "Vi invitiamo a prendere visione delle planimetrie di evacuazione "
    "posizionate ad ogni piano.<br/>"
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

# === Pagina 4 — Norme di emergenza (versione testuale, niente icone) ===
story.append(Spacer(1, 4 * mm))
story.append(Paragraph("NORME DI COMPORTAMENTO IN CASO DI", section_h))
story.append(Paragraph("EMERGENZA", emergency_h))
story.append(Paragraph(
    "<b>1.</b> MANTENERE LA CALMA. NON FARSI PRENDERE DAL PANICO.<br/>"
    "<b>2.</b> SEGUIRE LE ISTRUZIONI QUI RIPORTATE PER UN ESODO RAPIDO E ORDINATO.",
    ParagraphStyle("EmIntro", parent=body, alignment=TA_CENTER, fontSize=11,
                   spaceAfter=12),
))

# Tabella tipo "tipologie di emergenza"
def emergency_table(title, items_html):
    return KeepTogether([
        Paragraph(title, ParagraphStyle("EmSec", parent=sub_h, alignment=TA_CENTER,
                                         backColor=HexColor("#FFE0B2"),
                                         textColor=HexColor("#BF360C"),
                                         borderPadding=4)),
        Paragraph(items_html, body),
        Spacer(1, 4 * mm),
    ])

story.append(emergency_table(
    "MISURE PREVENTIVE",
    "• <b>È VIETATO FUMARE</b> e fare uso di fiamme libere nelle zone prescritte.<br/>"
    "• <b>È VIETATO GETTARE</b> nei cestini mozziconi di sigarette, materiali infiammabili, ecc.",
))

story.append(emergency_table(
    "IN CASO DI EMERGENZA",
    "Chiunque rilevi fatti anomali che possano far presumere un'imminente "
    "\"situazione di pericolo\", che non possa essere prontamente eliminata "
    "con interventi diretti (es. uso di estintore portatile in caso di "
    "incendio) deve immediatamente chiamare il numero di emergenza interno: "
    "<b>NUMERO DI EMERGENZA — Reception S2S</b>.<br/>"
    "Durante l'attesa l'addetto disponibile per estinguere l'incendio deve "
    "comunque agire seguendo le procedure previste in azienda, "
    "compatibilmente con le proprie capacità e senza compromettere la "
    "propria incolumità.",
))

story.append(emergency_table(
    "IN CASO DI INCENDIO",
    "• Dare l'allarme verbalmente, il pulsante di emergenza più vicino.<br/>"
    "• Utilizzare i mezzi antincendio disponibili per estinguere l'incendio "
    "compatibilmente con le proprie capacità e senza compromettere la "
    "propria incolumità.",
))

story.append(emergency_table(
    "IN CASO DI EVACUAZIONE",
    "<b>È VIETATO SERVIRSI DEGLI ASCENSORI.</b> Evitare di correre, spingersi "
    "e urlare.<br/><br/>"
    "<b>Personale e visitatori/ospiti:</b><br/>"
    "• Abbandonare regolarmente i locali seguendo i cartelli indicatori in "
    "conformità alle istruzioni impartite dal Responsabile incaricato.<br/>"
    "• Il personale non in grado di muoversi autonomamente attenda con calma "
    "l'arrivo dei soccorritori incaricati.<br/><br/>"
    "<b>Mezzi di spegnimento:</b><br/>"
    "• Idrante ad acqua: non usare su impianti elettrici.<br/>"
    "• Estintori portatili a CO₂ o polvere, anidride carbonica.<br/><br/>"
    "<b>In caso di presenza di fumo:</b> portarsi un fazzoletto inumidito alla "
    "via dell'aria e proseguire possibilmente lateralmente lungo il verso di "
    "fuga.<br/>"
    "Evitare di privarsi della ricerca di persone o di oggetti personali se "
    "non richiesto dagli addetti alla emergenza.",
))

story.append(emergency_table(
    "LEGENDA SIMBOLI (consultare la cartellonistica aziendale)",
    "• <b>ESTINTORI</b> — segnaletica rossa.<br/>"
    "• <b>IDRANTI UNI 45</b> — segnaletica rossa.<br/>"
    "• <b>PULSANTE DI EMERGENZA</b> — segnaletica rossa.<br/>"
    "• <b>QUADRO ELETTRICO</b> — segnaletica gialla.<br/>"
    "• <b>VOSTRA POSIZIONE</b> — segnaletica blu/verde.<br/>"
    "• <b>DIREZIONE DI ESODO</b> — segnaletica verde con freccia.<br/>"
    "• <b>USCITA DI EMERGENZA</b> — segnaletica verde.<br/>"
    "• <b>SCALA DI EMERGENZA</b> — segnaletica verde.<br/>"
    "• <b>PUNTO DI RADUNO</b> — segnaletica verde.<br/>"
    "• <b>CASSETTA DI PRIMO SOCCORSO</b> — segnaletica verde con croce bianca.",
))

story.append(Paragraph(
    "<i>Per i dettagli grafici e i percorsi specifici di evacuazione fare "
    "riferimento alle planimetrie di sicurezza esposte ad ogni piano della "
    "sede di Teverola.</i>",
    ParagraphStyle("EmFoot", parent=body, alignment=TA_CENTER, fontSize=9,
                   textColor=BRAND_GREY, spaceBefore=6),
))


# ─── Generazione PDF con totalPages a posteriori ───
class CountingDoc(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._totalPages = 1

    def afterFlowable(self, flowable):
        pass


# Strategia per pagina N di TOT: due passate
from reportlab.platypus.doctemplate import LayoutError

# Prima passata per contare pagine
first_pass_path = OUTPUT.with_suffix(".__count.pdf")
doc = SimpleDocTemplate(
    str(first_pass_path),
    pagesize=A4,
    leftMargin=18 * mm,
    rightMargin=18 * mm,
    topMargin=34 * mm,    # spazio per header
    bottomMargin=22 * mm, # spazio per footer
    title=f"{COMPANY_SHORT} — Brochure accesso immobile",
    author=COMPANY_NAME,
)
# Hack: usa una funzione che memorizza il numero di pagine totali
total_pages_holder = {"n": 1}

def _on_page(canvas, doc):
    draw_page_header_footer(canvas, doc)

def _count_pages(canvas, doc):
    total_pages_holder["n"] = doc.page

# Build prima passata (silenziosa, conta)
import copy
story_copy = list(story)
doc.build(copy.deepcopy(story_copy), onFirstPage=_count_pages, onLaterPages=_count_pages)

total = total_pages_holder["n"]

# Seconda passata: usa total per il rendering finale
def _render_page(canvas, doc):
    doc._totalPages = total
    draw_page_header_footer(canvas, doc)

doc2 = SimpleDocTemplate(
    str(OUTPUT),
    pagesize=A4,
    leftMargin=18 * mm,
    rightMargin=18 * mm,
    topMargin=34 * mm,
    bottomMargin=22 * mm,
    title=f"{COMPANY_SHORT} — Brochure accesso immobile",
    author=COMPANY_NAME,
)
doc2.build(story, onFirstPage=_render_page, onLaterPages=_render_page)

# Cleanup
try:
    first_pass_path.unlink(missing_ok=True)
except Exception:
    pass

print(f"OK — generato: {OUTPUT}")
print(f"Pagine: {total}")

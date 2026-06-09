import io
import re
import zipfile
from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

APP_VERSION = "AML_KYC_MKS_PRO_2026_06_09_V3"

st.set_page_config(page_title="AWW / AML KYC Analyse - batch 10", layout="wide")


def normalize_be_number(value: str) -> str:
    raw = str(value or "").strip().upper().replace("BE", "")
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 9:
        digits = "0" + digits
    return digits


def format_be_number(digits: str) -> str:
    digits = normalize_be_number(digits)
    if len(digits) != 10:
        return digits
    return f"BE{digits[:4]}.{digits[4:7]}.{digits[7:]}"


def is_valid_be_enterprise_number(digits: str) -> bool:
    digits = normalize_be_number(digits)
    if len(digits) != 10 or not digits.isdigit():
        return False
    base = int(digits[:8])
    check = int(digits[8:])
    return 97 - (base % 97) == check


def kbo_url(digits: str) -> str:
    return f"https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html?nummer={digits}&actionLu=Zoek"


def nbb_url() -> str:
    return "https://consult.cbso.nbb.be/consult-enterprise"


def staatsblad_url() -> str:
    return "https://www.ejustice.just.fgov.be/cgi_tsv/tsv.pl"


def infer_sector_risk(nace_text: str) -> tuple[str, int, list[str]]:
    t = (nace_text or "").lower()
    reasons = []
    score = 3
    label = "Laag tot gemiddeld"
    high_terms = ["bouw", "grondwerk", "beton", "horeca", "nachtwinkel", "transport", "vastgoed", "recycling", "schroot", "crypto", "diamant", "goud", "cash", "autohandel"]
    medium_terms = ["consult", "diensten", "handel", "groothandel", "detailhandel", "management", "holding"]
    if any(x in t for x in high_terms):
        score = 7
        label = "Gemiddeld tot hoog"
        reasons.append("De activiteit behoort tot of raakt aan een sector die in AML-praktijk verhoogde waakzaamheid vereist, onder meer wegens onderaanneming, cashgevoeligheid, btw-risico of complexe facturatiestromen.")
    elif any(x in t for x in medium_terms):
        score = 5
        label = "Gemiddeld"
        reasons.append("De activiteit vereist een normale tot verhoogde beoordeling van economische substantie, contractuele onderbouwing en realiteit van de prestaties.")
    else:
        reasons.append("Op basis van de ingevoerde activiteit werd geen specifiek hoog sectorrisico automatisch herkend. Manuele bevestiging blijft vereist.")
    return label, score, reasons


def infer_financial_risk(row: dict) -> tuple[str, int, list[str]]:
    reasons = []
    score = 3
    ev = row.get("eigen_vermogen")
    res = row.get("resultaat")
    schulden = row.get("schulden")
    activa = row.get("activa")
    try:
        ev = float(ev) if pd.notna(ev) and str(ev).strip() != "" else None
    except Exception:
        ev = None
    try:
        res = float(res) if pd.notna(res) and str(res).strip() != "" else None
    except Exception:
        res = None
    try:
        schulden = float(schulden) if pd.notna(schulden) and str(schulden).strip() != "" else None
    except Exception:
        schulden = None
    try:
        activa = float(activa) if pd.notna(activa) and str(activa).strip() != "" else None
    except Exception:
        activa = None
    if ev is not None and ev < 0:
        score += 4
        reasons.append("Het eigen vermogen is negatief. Dit wijst op continuiteitsrisico en vereist bijkomende aandacht voor financiering, herstelmaatregelen en herkomst van middelen.")
    if res is not None and res < 0:
        score += 2
        reasons.append("Het resultaat is negatief. Bij aanhoudende verliezen stijgt het risico op druk op liquiditeit en mogelijke onregelmatige financieringsstromen.")
    if schulden is not None and activa is not None and activa > 0 and schulden / activa > 0.8:
        score += 2
        reasons.append("De schuldenpositie is hoog ten opzichte van het balanstotaal. Dit verhoogt de nood aan analyse van schuldeisers, rekening-courantposities en aandeelhoudersfinanciering.")
    score = max(1, min(score, 10))
    if score >= 8:
        label = "Hoog"
    elif score >= 5:
        label = "Gemiddeld tot hoog"
    else:
        label = "Laag tot gemiddeld"
    if not reasons:
        reasons.append("Er werden onvoldoende financiele cijfers ingevoerd om een diepgaande financiele analyse automatisch te maken. Raadpleeg de NBB Balanscentrale en vul de kerncijfers aan.")
    return label, score, reasons


def risk_category(total_score: int) -> str:
    if total_score >= 70:
        return "HOOG RISICO"
    if total_score >= 45:
        return "GEMIDDELD TOT VERHOOGD RISICO"
    if total_score >= 25:
        return "GEMIDDELD RISICO"
    return "LAAG TOT GEMIDDELD RISICO"


def bullet_items(items):
    return "".join([f"<li>{escape(str(i))}</li>" for i in items if str(i).strip()])


def build_report_html(row: dict) -> str:
    digits = normalize_be_number(row.get("ondernemingsnummer"))
    valid = is_valid_be_enterprise_number(digits)
    name = str(row.get("naam") or row.get("onderneming") or "Niet ingevuld")
    legal = str(row.get("rechtsvorm") or "Te bevestigen via KBO")
    address = str(row.get("adres") or "Te bevestigen via KBO")
    nace = str(row.get("nace") or row.get("activiteit") or "Niet ingevuld - controle via KBO vereist")
    directors = str(row.get("bestuurders") or "Niet ingevuld - controle via KBO/Staatsblad vereist")
    ubo = str(row.get("ubo") or "Niet publiek volledig beschikbaar - UBO-registercontrole vereist")
    country = str(row.get("land") or "Belgie")
    btw = str(row.get("btw_status") or "Te bevestigen via KBO/VIES")
    founded = str(row.get("oprichtingsdatum") or "Te bevestigen via KBO/Staatsblad")
    sector_label, sector_score, sector_reasons = infer_sector_risk(nace)
    financial_label, financial_score, financial_reasons = infer_financial_risk(row)
    ubo_score = 6 if "niet" in ubo.lower() or "vereist" in ubo.lower() else 4
    geo_score = 2 if country.lower() in ["belgie", "belgium", "be"] else 5
    reputation_score = 4
    structure_score = 5 if "holding" in nace.lower() or "management" in nace.lower() else 4
    client_score = int(round((sector_score + financial_score + ubo_score + geo_score + reputation_score + structure_score) / 6 * 10))
    category = risk_category(client_score)
    today = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = f"""
    <h1>AML-KLANTENAANVAARDINGSANALYSE</h1>
    <h2>{escape(name)}</h2>
    <p><b>Ondernemingsnummer:</b> {escape(format_be_number(digits))}</p>
    <p><b>Rapportdatum:</b> {today}<br/><b>Versie rapportengine:</b> {APP_VERSION}</p>

    <h2>1. IDENTIFICATIE VAN DE CLIENT</h2>
    <table>
      <tr><td>Naam onderneming</td><td>{escape(name)}</td></tr>
      <tr><td>Ondernemingsnummer</td><td>{escape(format_be_number(digits))}</td></tr>
      <tr><td>Validatie ondernemingsnummer</td><td>{'Geldig' if valid else 'Ongeldig of te controleren'}</td></tr>
      <tr><td>Rechtsvorm</td><td>{escape(legal)}</td></tr>
      <tr><td>Oprichtingsdatum</td><td>{escape(founded)}</td></tr>
      <tr><td>Maatschappelijke zetel</td><td>{escape(address)}</td></tr>
      <tr><td>BTW-status</td><td>{escape(btw)}</td></tr>
      <tr><td>Activiteiten / NACE</td><td>{escape(nace)}</td></tr>
    </table>
    <p>De identificatie van de client moet worden bevestigd aan de hand van KBO-gegevens, btw-status, rechtsvorm, zeteladres, vestigingen en activiteiten. Afwijkingen tussen de opgegeven gegevens, KBO, facturatiegegevens of contractdocumenten moeten worden onderzocht vooraleer de client finaal wordt aanvaard.</p>

    <h2>2. IDENTIFICATIE BESTUURDERS EN MANDAATHOUDERS</h2>
    <p><b>Ingevoerde of te controleren bestuurders/mandatarissen:</b> {escape(directors)}</p>
    <p>Voor elk lid van het bestuursorgaan moet worden nagegaan of de persoon correct geidentificeerd is, of het mandaat actueel is, of er recente benoemingen of ontslagen zijn gepubliceerd en of er aanwijzingen bestaan van belangenconflicten, faillissementshistoriek of negatieve reputatie.</p>
    <ul>
      <li>Controleer actieve en historische mandaten via KBO en Belgisch Staatsblad.</li>
      <li>Controleer identiteitsgegevens van bestuurders volgens de kantoorprocedure.</li>
      <li>Voer sanctie-, PEP- en adverse-media screening uit via een geschikte databank.</li>
      <li>Documenteer afwijkingen tussen clientverklaring en publieke bronnen.</li>
    </ul>

    <h2>3. STRUCTUUR EN UBO-ONDERZOEK</h2>
    <p><b>UBO/aandeelhoudersinformatie:</b> {escape(ubo)}</p>
    <p>Publieke bronnen tonen doorgaans geen volledig aandeelhoudersregister. Voor een volledig AWW-dossier is daarom een afzonderlijke UBO-registercontrole noodzakelijk. Indien sprake is van aandeelhoudersfinanciering, bestuurdersleningen, rekening-courantposities of liquiditeitsinjecties, moet de herkomst van de middelen worden beoordeeld en gedocumenteerd.</p>
    <ul>
      <li>Vraag UBO-registeruittreksel op.</li>
      <li>Vraag aandeelhoudersregister of structuurorganigram op indien relevant.</li>
      <li>Controleer de uiteindelijke begunstigden en hun percentage of zeggenschap.</li>
      <li>Controleer of de structuur economisch logisch is.</li>
    </ul>

    <h2>4. ANALYSE VAN DE FINANCIELE TOESTAND</h2>
    <table>
      <tr><td>Activa</td><td>{escape(str(row.get('activa') or 'Niet ingevuld'))}</td></tr>
      <tr><td>Eigen vermogen</td><td>{escape(str(row.get('eigen_vermogen') or 'Niet ingevuld'))}</td></tr>
      <tr><td>Schulden</td><td>{escape(str(row.get('schulden') or 'Niet ingevuld'))}</td></tr>
      <tr><td>Resultaat</td><td>{escape(str(row.get('resultaat') or 'Niet ingevuld'))}</td></tr>
      <tr><td>Brutomarge/omzet</td><td>{escape(str(row.get('omzet') or row.get('brutomarge') or 'Niet ingevuld'))}</td></tr>
    </table>
    <p>Financiele analyse:</p><ul>{bullet_items(financial_reasons)}</ul>
    <p>De NBB-jaarrekening moet worden geraadpleegd om de evolutie over meerdere boekjaren te beoordelen. Belangrijke indicatoren zijn solvabiliteit, liquiditeit, schuldenlast, verlieslatendheid, continuiteitsvermeldingen en transacties met verbonden partijen.</p>

    <h2>5. CONTINUITEITSANALYSE</h2>
    <p>De continuiteitsanalyse beoordeelt of de onderneming structurele financiele moeilijkheden vertoont. Bij negatief eigen vermogen, recurrente verliezen of liquiditeitsproblemen moet worden nagegaan of het bestuursorgaan herstelmaatregelen heeft genomen en of de alarmbelprocedure van toepassing kan zijn.</p>
    <ul>
      <li>Controleer de toelichting bij de jaarrekening.</li>
      <li>Controleer eventuele bijzondere verslagen of vermeldingen over continuiteit.</li>
      <li>Beoordeel of bijkomende financiering economisch verklaarbaar is.</li>
      <li>Vraag bewijsstukken van aandeelhouders- of bestuurdersfinanciering op indien relevant.</li>
    </ul>

    <h2>6. ACTIVITEITSRISICO</h2>
    <p><b>Sectorbeoordeling:</b> {escape(sector_label)}</p>
    <ul>{bullet_items(sector_reasons)}</ul>
    <p>Bij verhoogde sectorrisico's moeten transacties met onderaannemers, cashbetalingen, buitenlandse partijen, complexe facturatieketens en ongebruikelijke marges met verhoogde aandacht worden opgevolgd.</p>

    <h2>7. BESTUURDERSHISTORIEK EN INTEGRITEITSONDERZOEK</h2>
    <p>Op basis van publieke informatie alleen kan geen sluitende integriteitsconclusie worden getrokken. Het kantoor moet de beschikbare bronnen aanvullen met interne clientkennis, identiteitscontrole, UBO-verificatie, sanctiescreening, PEP-screening en waar nodig commerciele databronnen zoals Companyweb, Graydon of Dow Jones Risk & Compliance.</p>
    <ul>
      <li>Geen negatieve vaststelling mag worden afgeleid uit het ontbreken van publieke resultaten alleen.</li>
      <li>Elke match in sanctie-, PEP- of adverse-media databanken moet manueel worden beoordeeld.</li>
      <li>Bij bestuurders met meerdere risicovolle mandaten is verhoogde waakzaamheid aangewezen.</li>
    </ul>

    <h2>8. TRANSACTIERISICO EN MKS-CONTROLE</h2>
    <p>Voor de MKS/monitoring van de zakelijke relatie moeten volgende transactietypes verhoogd worden opgevolgd:</p>
    <ul>
      <li>grote of ongebruikelijke contante betalingen;</li>
      <li>betalingen via derden zonder duidelijke economische reden;</li>
      <li>buitenlandse geldstromen die niet passen bij de activiteit;</li>
      <li>bestuurdersleningen en rekening-courantbewegingen;</li>
      <li>aandeelhoudersfinancieringen en liquiditeitsinjecties;</li>
      <li>facturatiestromen met onderaannemers of verbonden partijen.</li>
    </ul>

    <h2>9. RISICOBEOORDELING VOLGENS ANTIWITWASWET</h2>
    <table>
      <tr><th>Risicofactor</th><th>Beoordeling</th><th>Score</th></tr>
      <tr><td>Geografisch risico</td><td>{'Laag' if geo_score <= 3 else 'Gemiddeld'}</td><td>{geo_score}/10</td></tr>
      <tr><td>Sectorrisico</td><td>{escape(sector_label)}</td><td>{sector_score}/10</td></tr>
      <tr><td>Financieel risico</td><td>{escape(financial_label)}</td><td>{financial_score}/10</td></tr>
      <tr><td>UBO-transparantie</td><td>{'Gemiddeld' if ubo_score >= 5 else 'Laag'}</td><td>{ubo_score}/10</td></tr>
      <tr><td>Reputatierisico</td><td>Te bevestigen via screening</td><td>{reputation_score}/10</td></tr>
      <tr><td>Structuurrisico</td><td>Laag tot gemiddeld</td><td>{structure_score}/10</td></tr>
      <tr><td>Totale AML-score</td><td><b>{category}</b></td><td><b>{client_score}/100</b></td></tr>
    </table>

    <h2>10. BESLUIT CLIENTENAANVAARDING</h2>
    <p>Op basis van de beschikbare en ingevoerde informatie lijkt de onderneming een Belgische juridische entiteit waarvan de identificatie, activiteiten, bestuurders, UBO-structuur en financiele positie verder moeten worden bevestigd aan de hand van officiele bronnen. Er werden in deze automatische analyse geen definitieve aanwijzingen vastgesteld van witwassen of terrorismefinanciering, maar dit rapport vervangt geen menselijke beoordeling.</p>
    <p><b>Eindbeoordeling:</b> {category}</p>
    <p><b>Aanvaardingsadvies:</b> Client aanvaardbaar mits volledige identificatie, UBO-controle, sanctie/PEP-screening en documentatie van de economische activiteit. Bij verhoogde sector-, financiele of UBO-risico's zijn verhoogde waakzaamheidsmaatregelen aangewezen.</p>
    <p><b>Aanbevolen maatregelen:</b></p>
    <ul>
      <li>identificatie en verificatie bestuurders;</li>
      <li>UBO-registercontrole en opname in dossier;</li>
      <li>controle KBO, NBB en Belgisch Staatsblad;</li>
      <li>sanctie-, PEP- en adverse-media screening;</li>
      <li>opvragen bewijs oorsprong middelen bij financiering door aandeelhouders of bestuurders;</li>
      <li>jaarlijkse of versnelde herbeoordeling bij verhoogd risico;</li>
      <li>monitoring van uitzonderlijke transacties volgens kantoorprocedure.</li>
    </ul>

    <h2>11. BRONNEN EN AUDIT TRAIL</h2>
    <ul>
      <li>KBO Public Search: {escape(kbo_url(digits))}</li>
      <li>NBB Balanscentrale: {escape(nbb_url())}</li>
      <li>Belgisch Staatsblad: {escape(staatsblad_url())}</li>
      <li>UBO-register: vereist gemachtigde toegang.</li>
      <li>Sanctie/PEP/adverse media: vereist gespecialiseerde databank.</li>
    </ul>
    <p><b>Disclaimer:</b> Dit rapport is een hulpmiddel voor de voorbereiding van het AWW/KYC/MKS-dossier. Finale clientacceptatie vereist menselijke controle en validatie van de gebruikte bronnen.</p>
    """
    return html


def html_to_pdf_bytes(html: str) -> bytes:
    # Simple HTML parser for the generated restricted HTML subset.
    import re
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.4*cm, leftMargin=1.4*cm, topMargin=1.4*cm, bottomMargin=1.4*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Title"], alignment=TA_CENTER, fontSize=16, leading=20, spaceAfter=12))
    styles.add(ParagraphStyle(name="H2Custom", parent=styles["Heading2"], fontSize=12, leading=15, spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="BodyCustom", parent=styles["BodyText"], fontSize=9, leading=12, spaceAfter=5))
    story = []
    chunks = re.split(r"(<h1>.*?</h1>|<h2>.*?</h2>|<table>.*?</table>|<ul>.*?</ul>|<p>.*?</p>)", html, flags=re.S)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("<h1>"):
            txt = re.sub("<.*?>", "", chunk)
            story.append(Paragraph(escape(txt), styles["TitleCenter"]))
        elif chunk.startswith("<h2>"):
            txt = re.sub("<.*?>", "", chunk)
            story.append(Paragraph(escape(txt), styles["H2Custom"]))
        elif chunk.startswith("<p>"):
            inner = chunk[3:-4]
            inner = inner.replace("<b>", "<b>").replace("</b>", "</b>").replace("<br/>", "<br/>")
            story.append(Paragraph(inner, styles["BodyCustom"]))
        elif chunk.startswith("<ul>"):
            items = re.findall(r"<li>(.*?)</li>", chunk, flags=re.S)
            for item in items:
                story.append(Paragraph("• " + item, styles["BodyCustom"]))
        elif chunk.startswith("<table>"):
            rows = re.findall(r"<tr>(.*?)</tr>", chunk, flags=re.S)
            table_data = []
            for r in rows:
                cells = re.findall(r"<t[dh]>(.*?)</t[dh]>", r, flags=re.S)
                cells = [Paragraph(c, styles["BodyCustom"]) for c in cells]
                if cells:
                    table_data.append(cells)
            if table_data:
                col_count = max(len(r) for r in table_data)
                normalized = [r + [""]*(col_count-len(r)) for r in table_data]
                table = Table(normalized, hAlign="LEFT", colWidths=[5.2*cm] + [10.8*cm/(col_count-1)]*(col_count-1) if col_count > 1 else None)
                table.setStyle(TableStyle([
                    ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
                    ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
                    ("VALIGN", (0,0), (-1,-1), "TOP"),
                    ("LEFTPADDING", (0,0), (-1,-1), 4),
                    ("RIGHTPADDING", (0,0), (-1,-1), 4),
                ]))
                story.append(table)
                story.append(Spacer(1, 6))
    doc.build(story)
    return buffer.getvalue()


def read_input(file) -> pd.DataFrame:
    name = file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    return pd.read_excel(file)


st.title("AWW / AML / KYC / MKS rapportgenerator - professionele batch 10")
st.caption(f"Versie: {APP_VERSION}")
st.warning("Controleer dat deze versie bovenaan zichtbaar is. Zie je deze versieregel niet, dan draait Streamlit nog oude code.")

with st.expander("Benodigde kolommen en optionele verrijking", expanded=False):
    st.write("Verplicht: ondernemingsnummer. Optioneel maar sterk aanbevolen voor uitgebreide rapporten: naam, rechtsvorm, adres, oprichtingsdatum, nace/activiteit, bestuurders, ubo, btw_status, activa, eigen_vermogen, schulden, resultaat, omzet/brutomarge.")
    template = pd.DataFrame([{
        "ondernemingsnummer": "0715946112",
        "naam": "AV Beton-Grondwerken BV",
        "rechtsvorm": "Besloten Vennootschap",
        "adres": "Kattestraat 180/A, 8520 Kuurne",
        "oprichtingsdatum": "18/12/2018",
        "nace": "Bouwrijp maken van terreinen / grondwerken / betonwerken",
        "bestuurders": "Johan Andre Vercruysse; Jessy Lia Renata Vercruysse",
        "ubo": "Te controleren via UBO-register",
        "btw_status": "Actief btw-plichtig",
        "activa": 561860,
        "eigen_vermogen": -292115,
        "schulden": 853975,
        "resultaat": -289147,
        "omzet": -48185,
    }])
    bio = io.BytesIO()
    template.to_excel(bio, index=False)
    st.download_button("Download inputtemplate Excel", bio.getvalue(), "inputtemplate_aww.xlsx")

uploaded = st.file_uploader("Upload Excel of CSV met maximaal 10 ondernemingen", type=["xlsx", "csv"])

if uploaded:
    try:
        df = read_input(uploaded)
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "ondernemingsnummer" not in df.columns:
            st.error("Kolom 'ondernemingsnummer' ontbreekt.")
            st.stop()
        if len(df) > 10:
            st.error("Deze testversie verwerkt maximaal 10 ondernemingen per batch. Beperk het bestand tot 10 lijnen.")
            st.stop()
        st.success(f"{len(df)} ondernemingen geladen.")
        st.dataframe(df)
        if st.button("Genereer uitgebreide AML/KYC/MKS rapporten"):
            zip_buffer = io.BytesIO()
            overview = []
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
                progress = st.progress(0)
                for i, row in df.iterrows():
                    data = row.to_dict()
                    digits = normalize_be_number(data.get("ondernemingsnummer"))
                    html = build_report_html(data)
                    pdf = html_to_pdf_bytes(html)
                    pdf_name = f"AML_KYC_MKS_{digits}.pdf"
                    html_name = f"AML_KYC_MKS_{digits}.html"
                    z.writestr(pdf_name, pdf)
                    z.writestr(html_name, html)
                    sector_label, sector_score, _ = infer_sector_risk(str(data.get("nace") or data.get("activiteit") or ""))
                    financial_label, financial_score, _ = infer_financial_risk(data)
                    score = int(round((sector_score + financial_score + 6 + 2 + 4 + 4) / 6 * 10))
                    overview.append({
                        "ondernemingsnummer": format_be_number(digits),
                        "naam": data.get("naam", ""),
                        "validatie": "geldig" if is_valid_be_enterprise_number(digits) else "te controleren",
                        "sectorrisico": sector_label,
                        "financieel risico": financial_label,
                        "totale score": score,
                        "categorie": risk_category(score),
                    })
                    progress.progress((i + 1) / len(df))
                overview_df = pd.DataFrame(overview)
                out_xlsx = io.BytesIO()
                overview_df.to_excel(out_xlsx, index=False)
                z.writestr("overzicht.xlsx", out_xlsx.getvalue())
            st.success("Rapporten gegenereerd.")
            st.download_button("Download ZIP met rapporten", zip_buffer.getvalue(), "aww_aml_kyc_mks_rapporten.zip", "application/zip")
            st.dataframe(pd.DataFrame(overview))
    except Exception as e:
        st.exception(e)
else:
    st.info("Upload een bestand of download eerst de inputtemplate. Voor diepgaande rapporten moet je zoveel mogelijk velden invullen of later echte databronnen koppelen.")

st.divider()
st.subheader("Waarom rapporten soms beperkt blijven")
st.write("Een rapport kan alleen echt dossierwaardig worden als de app gegevens krijgt. Zonder naam, rechtsvorm, bestuurders, NACE-code, financiele cijfers en UBO-info kan de app alleen generieke AWW-tekst en bronlinks geven. Deze versie maakt wel altijd een uitgebreid dossier, maar markeert ontbrekende gegevens als te controleren.")

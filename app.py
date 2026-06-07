import io
import re
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


st.set_page_config(page_title="AWW België Analyse Tool", layout="wide")

USER_AGENT = "AWW-Belgie-Analyse-Tool/0.1 contact: marc@qualitax.be"


def normalize_enterprise_number(value: Any) -> str:
    s = re.sub(r"\D", "", str(value or ""))
    if len(s) == 9:
        s = "0" + s
    return s


def format_be_number(num: str) -> str:
    num = normalize_enterprise_number(num)
    if len(num) != 10:
        return num
    return f"{num[:4]}.{num[4:7]}.{num[7:]}"


def is_valid_be_enterprise_number(num: str) -> bool:
    num = normalize_enterprise_number(num)
    if len(num) != 10 or not num.isdigit():
        return False
    base = int(num[:8])
    check = int(num[8:])
    return (97 - (base % 97)) == check


def load_numbers(uploaded_file) -> List[str]:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, dtype=str)
    else:
        df = pd.read_excel(uploaded_file, dtype=str)
    possible_cols = [c for c in df.columns if "ondernem" in c.lower() or "nummer" in c.lower() or "enterprise" in c.lower()]
    col = possible_cols[0] if possible_cols else df.columns[0]
    return [normalize_enterprise_number(x) for x in df[col].dropna().tolist()]


def safe_get(url: str, timeout: int = 12) -> Dict[str, Any]:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        return {"ok": r.ok, "status": r.status_code, "text": r.text[:200000], "url": url}
    except Exception as exc:
        return {"ok": False, "status": None, "text": str(exc), "url": url}


def search_web_light(query: str) -> Dict[str, Any]:
    # Gratis, eenvoudige fallback via DuckDuckGo HTML. Niet bedoeld als compliance-databron.
    url = "https://duckduckgo.com/html/"
    try:
        r = requests.post(url, data={"q": query}, headers={"User-Agent": USER_AGENT}, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.select("a.result__a")[:5]:
            results.append({"title": a.get_text(" ", strip=True), "url": a.get("href")})
        return {"ok": True, "results": results}
    except Exception as exc:
        return {"ok": False, "results": [], "error": str(exc)}


def collect_public_sources(num: str, use_online_search: bool) -> Dict[str, Any]:
    formatted = format_be_number(num)
    sources = {
        "kbo_public_search": f"https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html?nummer={num}&actionLu=Zoek",
        "nbb_balanscentrale": "https://consult.cbso.nbb.be/consult-enterprise",
        "belgisch_staatsblad": "https://www.ejustice.just.fgov.be/cgi_tsv/tsv.pl",
    }
    online = []
    if use_online_search:
        queries = [
            f'"{formatted}" onderneming',
            f'"{num}" KBO',
            f'"{formatted}" staatsblad',
        ]
        for q in queries:
            res = search_web_light(q)
            online.extend(res.get("results", []))
    return {"sources": sources, "online_results": online}


def risk_assessment(num: str, data: Dict[str, Any]) -> Dict[str, Any]:
    score = 20
    flags = []
    if not is_valid_be_enterprise_number(num):
        score += 35
        flags.append("Ongeldig of verdacht ondernemingsnummer volgens Belgische controlelogica.")
    if not data.get("online_results"):
        score += 10
        flags.append("Geen online zoekresultaten opgehaald of online zoeken uitgeschakeld.")
    # Conservatieve standaard-AWW-indicatoren voor MVP.
    flags.append("Controleer KBO-status, rechtsvorm, NACE-code, bestuurders en vestigingen manueel via bronlink.")
    flags.append("Controleer jaarrekening en financiële ratio's via NBB Balanscentrale.")
    flags.append("Controleer publicaties en bestuurswijzigingen via Belgisch Staatsblad.")
    flags.append("Controleer UBO, PEP, sancties en adverse media via gemachtigde compliancebronnen.")
    if score < 35:
        level = "Laag"
    elif score < 65:
        level = "Middel"
    else:
        level = "Hoog"
    return {"score": min(score, 100), "level": level, "flags": flags}


def make_pdf(row: Dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 2 * cm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, y, "AWW Analyseverslag")
    y -= 1 * cm
    c.setFont("Helvetica", 10)
    lines = [
        f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Ondernemingsnummer: {row['ondernemingsnummer_geformatteerd']}",
        f"Validatie: {'geldig' if row['geldig'] else 'ongeldig'}",
        f"Risicoscore: {row['risicoscore']}/100",
        f"Risiconiveau: {row['risiconiveau']}",
        "",
        "Belangrijk: dit MVP-rapport is een hulpmiddel. Finale AWW-beoordeling blijft menselijke controle.",
        "",
        "Bronnen:",
        f"- KBO Public Search: {row['kbo_link']}",
        f"- NBB Balanscentrale: {row['nbb_link']}",
        f"- Belgisch Staatsblad: {row['staatsblad_link']}",
        "",
        "Aandachtspunten:",
    ]
    for flag in row["flags"]:
        lines.append(f"- {flag}")
    lines += ["", "Online zoekresultaten:"]
    for item in row.get("online_results", [])[:5]:
        lines.append(f"- {item.get('title','')}: {item.get('url','')}")
    for line in lines:
        if y < 2 * cm:
            c.showPage()
            y = height - 2 * cm
            c.setFont("Helvetica", 10)
        # reportlab latin-1 limitation workaround
        safe_line = str(line).replace("–", "-").replace("’", "'")[:140]
        c.drawString(2 * cm, y, safe_line)
        y -= 0.45 * cm
    c.save()
    return buffer.getvalue()


def analyze_numbers(numbers: List[str], use_online_search: bool):
    rows = []
    pdfs = {}
    progress = st.progress(0)
    status = st.empty()
    for i, num in enumerate(numbers, 1):
        status.write(f"Analyse {i}/{len(numbers)}: {format_be_number(num)}")
        data = collect_public_sources(num, use_online_search)
        risk = risk_assessment(num, data)
        row = {
            "ondernemingsnummer": num,
            "ondernemingsnummer_geformatteerd": format_be_number(num),
            "geldig": is_valid_be_enterprise_number(num),
            "risicoscore": risk["score"],
            "risiconiveau": risk["level"],
            "flags": risk["flags"],
            "kbo_link": data["sources"]["kbo_public_search"],
            "nbb_link": data["sources"]["nbb_balanscentrale"],
            "staatsblad_link": data["sources"]["belgisch_staatsblad"],
            "online_results": data["online_results"],
        }
        rows.append(row)
        pdfs[f"AWW_{num}.pdf"] = make_pdf(row)
        progress.progress(i / len(numbers))
    status.write("Analyse klaar.")
    return rows, pdfs


def dataframe_to_excel(rows: List[Dict[str, Any]]) -> bytes:
    flat = []
    for r in rows:
        flat.append({
            "ondernemingsnummer": r["ondernemingsnummer_geformatteerd"],
            "geldig": r["geldig"],
            "risicoscore": r["risicoscore"],
            "risiconiveau": r["risiconiveau"],
            "kbo_link": r["kbo_link"],
            "nbb_link": r["nbb_link"],
            "staatsblad_link": r["staatsblad_link"],
            "aandachtspunten": " | ".join(r["flags"]),
        })
    out = io.BytesIO()
    pd.DataFrame(flat).to_excel(out, index=False)
    return out.getvalue()


def make_zip(pdfs: Dict[str, bytes], overview_xlsx: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("overzicht.xlsx", overview_xlsx)
        for name, content in pdfs.items():
            z.writestr(f"rapporten/{name}", content)
    return out.getvalue()


def main():
    st.title("AWW België Analyse Tool")
    st.write("Upload een CSV of Excel met ondernemingsnummers. De tool maakt een AWW-overzicht en PDF per onderneming.")

    with st.expander("Inputformaat"):
        st.write("Gebruik een kolom met naam `ondernemingsnummer`, of zet ondernemingsnummers in de eerste kolom.")
        sample = pd.DataFrame({"ondernemingsnummer": ["0403170701", "0434498699"]})
        st.dataframe(sample, use_container_width=True)
        csv = sample.to_csv(index=False).encode("utf-8")
        st.download_button("Download voorbeeld CSV", csv, "input.csv", "text/csv")

    uploaded = st.file_uploader("Upload CSV of Excel", type=["csv", "xlsx"])
    use_online_search = st.checkbox("Online zoekresultaten ophalen", value=False)

    if uploaded:
        numbers = load_numbers(uploaded)
        st.success(f"{len(numbers)} ondernemingsnummers gevonden.")
        st.write([format_be_number(n) for n in numbers[:10]])
        if st.button("Start analyse"):
            rows, pdfs = analyze_numbers(numbers, use_online_search)
            overview = dataframe_to_excel(rows)
            zip_bytes = make_zip(pdfs, overview)
            st.subheader("Overzicht")
            st.dataframe(pd.read_excel(io.BytesIO(overview)), use_container_width=True)
            st.download_button("Download overzicht.xlsx", overview, "overzicht.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("Download alle rapporten ZIP", zip_bytes, "aww_rapporten.zip", "application/zip")

    st.info("Voor productie: koppel officiële KBO/NBB/Staatsblad/UBO/sanctie-API's en voeg gebruikerslogin, logging en bewaarbeleid toe.")


if __name__ == "__main__":
    main()

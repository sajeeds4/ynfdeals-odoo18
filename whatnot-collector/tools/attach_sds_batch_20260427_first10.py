#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.company_db import get_product
from server.postgres_cutover import POSTGRES_SIDECAR_SCHEMA, _pg_connect
from tools.enrich_inventory_batch_20260427_first10 import SEEDS, ProductSeed


SDS_ROOT = ROOT / "product_uploads" / "sds"

BRAND_MANUFACTURER = {
    "Afnan": "Afnan Perfumes LLC",
    "Lattafa": "Lattafa Perfumes Industries L.L.C",
    "Asdaaf": "Lattafa Perfumes Industries L.L.C",
    "Al Haramain": "Al Haramain Perfumes LLC",
}

BRAND_ORIGIN = {
    "Afnan": "United Arab Emirates",
    "Lattafa": "United Arab Emirates",
    "Asdaaf": "United Arab Emirates",
    "Al Haramain": "United Arab Emirates",
}

DEFAULT_INGREDIENTS = "Alcohol Denat., Parfum (Fragrance), Aqua (Water), fragrance compounds, fixatives, and stabilizers."


@dataclass
class SdsArtifact:
    product_id: int
    barcode: str
    name: str
    pdf_path: Path
    html_path: Path
    tex_path: Path


def slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return text or "product-sds"


def split_title(name: str) -> tuple[str, str]:
    match = re.match(r"^(.*? Spray)\s+(\d+\s*ml.*)$", name, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return name.strip(), ""


def product_type(seed: ProductSeed) -> str:
    form = (seed.product_form or "").strip() or "Fragrance"
    return f"Cosmetic Fragrance / {form}"


def tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    return value


def render_tex(seed: ProductSeed) -> str:
    title, subtitle = split_title(seed.name)
    manufacturer = BRAND_MANUFACTURER.get(seed.brand, f"{seed.brand} Perfumes LLC")
    origin = BRAND_ORIGIN.get(seed.brand, "United Arab Emirates")
    ingredient_rows = [
        ("Ethanol / Alcohol Denat.", "64-17-5", "70--90\\%"),
        ("Fragrance Compounds", "Proprietary", "5--15\\%"),
        ("Water / Aqua", "7732-18-5", "1--5\\%"),
        ("Fixatives / Stabilizers", "Proprietary", "<5\\%"),
    ]
    ingredients_block = "\n".join(
        f"{tex_escape(name)} & {tex_escape(cas)} & {tex_escape(conc)} \\\\"
        for name, cas, conc in ingredient_rows
    )
    odor = seed.scent or "Fragrance"
    return rf"""\documentclass[11pt]{{article}}

\usepackage[margin=0.75in]{{geometry}}
\usepackage{{array}}
\usepackage{{longtable}}
\usepackage{{titlesec}}
\usepackage{{enumitem}}
\usepackage{{hyperref}}

\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{6pt}}

\titleformat{{\section}}
{{\large\bfseries}}
{{SECTION \thesection:}}
{{0.5em}}
{{}}

\begin{{document}}

\begin{{center}}
{{\LARGE \textbf{{SAFETY DATA SHEET (SDS)}}}}\\[6pt]
{{\Large \textbf{{{tex_escape(title)}}}}}\\
{{\large \textbf{{{tex_escape(subtitle)}}}}}\\[6pt]
Prepared according to OSHA Hazard Communication Standard\\
29 CFR 1910.1200
\end{{center}}

\vspace{{10pt}}

\section{{IDENTIFICATION}}

\textbf{{Product Identifier:}} {tex_escape(title)}

\textbf{{Product Type:}} {tex_escape(product_type(seed))}

\textbf{{Brand:}} {tex_escape(seed.brand)}

\textbf{{Manufacturer:}} {tex_escape(manufacturer)}

\textbf{{Country of Origin:}} {tex_escape(origin)}

\textbf{{Recommended Use:}} Personal fragrance / cosmetic use

\textbf{{Emergency Contact:}} CHEMTREC USA +1-800-424-9300

\section{{HAZARDS IDENTIFICATION}}

\textbf{{Classification:}}
\begin{{itemize}}[noitemsep]
    \item Flammable Liquid -- Category 3
    \item Skin Irritation -- Category 2
    \item Skin Sensitization -- Category 1
\end{{itemize}}

\textbf{{Signal Word:}} Danger

\textbf{{Hazard Statements:}}
\begin{{itemize}}[noitemsep]
    \item H226: Highly flammable liquid and vapor
    \item H315: Causes skin irritation
    \item H317: May cause allergic skin reaction
\end{{itemize}}

\textbf{{Precautionary Statements:}}
\begin{{itemize}}[noitemsep]
    \item Keep away from heat, sparks, open flames, and hot surfaces.
    \item Avoid contact with eyes and skin.
    \item Use only in a well-ventilated area.
    \item Keep container tightly closed.
\end{{itemize}}

\section{{COMPOSITION / INFORMATION ON INGREDIENTS}}

\begin{{longtable}}{{|p{{2.3in}}|p{{1.5in}}|p{{1.5in}}|}}
\hline
\textbf{{Ingredient}} & \textbf{{CAS Number}} & \textbf{{Concentration}} \\
\hline
{ingredients_block}
\hline
\end{{longtable}}

Exact fragrance composition is proprietary.

\section{{FIRST AID MEASURES}}

\textbf{{Eye Contact:}} Rinse cautiously with water for several minutes. Remove contact lenses if present and easy to do. Continue rinsing.

\textbf{{Skin Contact:}} Wash affected area with soap and water. Discontinue use if irritation occurs.

\textbf{{Inhalation:}} Move person to fresh air if irritation occurs.

\textbf{{Ingestion:}} Do not induce vomiting. Seek medical advice if swallowed.

\section{{FIRE-FIGHTING MEASURES}}

\textbf{{Suitable Extinguishing Media:}} Carbon dioxide, dry chemical powder, alcohol-resistant foam.

\textbf{{Specific Hazards:}} Flammable liquid and vapor. Vapors may form explosive mixtures with air.

\textbf{{Protective Equipment:}} Firefighters should wear appropriate protective equipment and self-contained breathing apparatus if necessary.

\section{{ACCIDENTAL RELEASE MEASURES}}

Remove ignition sources.

Ventilate the area.

Absorb spill with inert material such as sand, earth, or vermiculite.

Dispose of collected material according to local, state, and federal regulations.

\section{{HANDLING AND STORAGE}}

\textbf{{Handling:}}
\begin{{itemize}}[noitemsep]
    \item Avoid spraying near open flame or ignition sources.
    \item Avoid contact with eyes.
    \item Use only as directed.
\end{{itemize}}

\textbf{{Storage:}}
\begin{{itemize}}[noitemsep]
    \item Store in a cool, dry, well-ventilated place.
    \item Keep away from direct sunlight, heat, sparks, and flames.
    \item Keep container tightly closed.
\end{{itemize}}

\section{{EXPOSURE CONTROLS / PERSONAL PROTECTION}}

\textbf{{Occupational Exposure Limit:}}

Ethanol OSHA PEL: 1000 ppm

\textbf{{Personal Protective Equipment:}}

No special PPE required for normal consumer cosmetic use.

\textbf{{Ventilation:}}

Use in a well-ventilated area.

\section{{PHYSICAL AND CHEMICAL PROPERTIES}}

\begin{{longtable}}{{|p{{2.5in}}|p{{3in}}|}}
\hline
\textbf{{Property}} & \textbf{{Value}} \\
\hline
Appearance & Clear liquid \\
\hline
Odor & {tex_escape(odor)} \\
\hline
Physical State & Liquid spray \\
\hline
Flash Point & Approximately 16--25$^\circ$C \\
\hline
Boiling Point & Approximately 78$^\circ$C \\
\hline
Solubility & Partially soluble in water \\
\hline
Flammability & Flammable liquid and vapor \\
\hline
\end{{longtable}}

\section{{STABILITY AND REACTIVITY}}

\textbf{{Reactivity:}} No dangerous reaction known under normal use.

\textbf{{Chemical Stability:}} Stable under recommended storage conditions.

\textbf{{Conditions to Avoid:}} Heat, sparks, open flames, direct sunlight.

\textbf{{Incompatible Materials:}} Strong oxidizing agents.

\textbf{{Hazardous Decomposition Products:}} Carbon monoxide and carbon dioxide may form during combustion.

\section{{TOXICOLOGICAL INFORMATION}}

May cause mild skin or eye irritation.

May cause allergic reaction in sensitive individuals.

Low toxicity expected under normal cosmetic use.

\section{{ECOLOGICAL INFORMATION}}

No significant environmental hazard expected under normal consumer use.

Avoid release of large quantities into drains, waterways, or soil.

\section{{DISPOSAL CONSIDERATIONS}}

Dispose of contents and container in accordance with local, state, and federal regulations.

Do not dispose of large quantities into drains.

Recycle packaging where possible.

\section{{TRANSPORT INFORMATION}}

\begin{{longtable}}{{|p{{2.5in}}|p{{3in}}|}}
\hline
\textbf{{UN Number}} & UN1266 \\
\hline
\textbf{{Proper Shipping Name}} & Perfumery Products \\
\hline
\textbf{{Hazard Class}} & 3 \\
\hline
\textbf{{Packing Group}} & II \\
\hline
\textbf{{Transport Hazard}} & Flammable Liquid \\
\hline
\end{{longtable}}

\section{{REGULATORY INFORMATION}}

Prepared according to OSHA Hazard Communication Standard 29 CFR 1910.1200.

Product is intended for cosmetic use.

All components are used in accordance with applicable cosmetic fragrance regulations.

\section{{OTHER INFORMATION}}

\textbf{{NFPA Rating:}}

Health: 2

Flammability: 4

Reactivity: 0

\vspace{{10pt}}

This Safety Data Sheet is provided for safe handling, storage, transportation, and regulatory review of cosmetic fragrance products.

\vfill

\begin{{center}}
\textbf{{End of Safety Data Sheet}}
\end{{center}}

\end{{document}}
"""


def render_html(seed: ProductSeed) -> str:
    title, subtitle = split_title(seed.name)
    manufacturer = BRAND_MANUFACTURER.get(seed.brand, f"{seed.brand} Perfumes LLC")
    origin = BRAND_ORIGIN.get(seed.brand, "United Arab Emirates")
    odor = seed.scent or "Fragrance"
    ingredients = seed.ingredients or DEFAULT_INGREDIENTS
    safe_ingredients = html.escape(ingredients)
    rows = [
        ("Ethanol / Alcohol Denat.", "64-17-5", "70-90%"),
        ("Fragrance Compounds", "Proprietary", "5-15%"),
        ("Water / Aqua", "7732-18-5", "1-5%"),
        ("Fixatives / Stabilizers", "Proprietary", "<5%"),
    ]
    ingredient_rows = "".join(
        f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td></tr>"
        for a, b, c in rows
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SDS - {html.escape(seed.name)}</title>
  <style>
    body {{ font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 32px; color: #111827; font-size: 13px; line-height: 1.45; }}
    h1, h2, h3, p {{ margin: 0; }}
    .center {{ text-align: center; }}
    .title {{ font-size: 28px; font-weight: 700; }}
    .subtitle {{ font-size: 22px; font-weight: 700; margin-top: 6px; }}
    .smallsub {{ font-size: 16px; font-weight: 600; margin-top: 4px; }}
    .section {{ margin-top: 18px; }}
    .section h2 {{ font-size: 17px; font-weight: 700; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; margin-bottom: 8px; }}
    .label {{ font-weight: 700; }}
    ul {{ margin: 6px 0 0 20px; padding: 0; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border: 1px solid #94a3b8; padding: 6px 8px; vertical-align: top; }}
    th {{ background: #f8fafc; text-align: left; }}
    .footer {{ margin-top: 20px; text-align: center; font-weight: 700; }}
    .mono {{ font-family: "Courier New", monospace; }}
  </style>
</head>
<body>
  <div class="center">
    <div class="title">SAFETY DATA SHEET (SDS)</div>
    <div class="subtitle">{html.escape(title)}</div>
    <div class="smallsub">{html.escape(subtitle)}</div>
    <div style="margin-top: 8px;">Prepared according to OSHA Hazard Communication Standard<br>29 CFR 1910.1200</div>
  </div>

  <div class="section">
    <h2>SECTION 1: IDENTIFICATION</h2>
    <p><span class="label">Product Identifier:</span> {html.escape(title)}</p>
    <p><span class="label">Product Type:</span> {html.escape(product_type(seed))}</p>
    <p><span class="label">Brand:</span> {html.escape(seed.brand)}</p>
    <p><span class="label">Manufacturer:</span> {html.escape(manufacturer)}</p>
    <p><span class="label">Country of Origin:</span> {html.escape(origin)}</p>
    <p><span class="label">Recommended Use:</span> Personal fragrance / cosmetic use</p>
    <p><span class="label">Emergency Contact:</span> CHEMTREC USA +1-800-424-9300</p>
  </div>

  <div class="section">
    <h2>SECTION 2: HAZARDS IDENTIFICATION</h2>
    <p><span class="label">Classification:</span></p>
    <ul>
      <li>Flammable Liquid - Category 3</li>
      <li>Skin Irritation - Category 2</li>
      <li>Skin Sensitization - Category 1</li>
    </ul>
    <p style="margin-top: 8px;"><span class="label">Signal Word:</span> Danger</p>
    <p><span class="label">Hazard Statements:</span></p>
    <ul>
      <li>H226: Highly flammable liquid and vapor</li>
      <li>H315: Causes skin irritation</li>
      <li>H317: May cause allergic skin reaction</li>
    </ul>
  </div>

  <div class="section">
    <h2>SECTION 3: COMPOSITION / INFORMATION ON INGREDIENTS</h2>
    <table>
      <thead><tr><th>Ingredient</th><th>CAS Number</th><th>Concentration</th></tr></thead>
      <tbody>{ingredient_rows}</tbody>
    </table>
    <p style="margin-top: 8px;">Exact fragrance composition is proprietary.</p>
    <p style="margin-top: 6px;"><span class="label">Known ingredient declaration:</span> {safe_ingredients}</p>
  </div>

  <div class="section">
    <h2>SECTION 4: FIRST AID MEASURES</h2>
    <p><span class="label">Eye Contact:</span> Rinse cautiously with water for several minutes. Remove contact lenses if present and easy to do. Continue rinsing.</p>
    <p><span class="label">Skin Contact:</span> Wash affected area with soap and water. Discontinue use if irritation occurs.</p>
    <p><span class="label">Inhalation:</span> Move person to fresh air if irritation occurs.</p>
    <p><span class="label">Ingestion:</span> Do not induce vomiting. Seek medical advice if swallowed.</p>
  </div>

  <div class="section">
    <h2>SECTION 5: FIRE-FIGHTING MEASURES</h2>
    <p><span class="label">Suitable Extinguishing Media:</span> Carbon dioxide, dry chemical powder, alcohol-resistant foam.</p>
    <p><span class="label">Specific Hazards:</span> Flammable liquid and vapor. Vapors may form explosive mixtures with air.</p>
    <p><span class="label">Protective Equipment:</span> Firefighters should wear appropriate protective equipment and self-contained breathing apparatus if necessary.</p>
  </div>

  <div class="section">
    <h2>SECTION 6: ACCIDENTAL RELEASE MEASURES</h2>
    <p>Remove ignition sources. Ventilate the area. Absorb spill with inert material such as sand, earth, or vermiculite. Dispose of collected material according to local, state, and federal regulations.</p>
  </div>

  <div class="section">
    <h2>SECTION 7: HANDLING AND STORAGE</h2>
    <p><span class="label">Handling:</span></p>
    <ul>
      <li>Avoid spraying near open flame or ignition sources.</li>
      <li>Avoid contact with eyes.</li>
      <li>Use only as directed.</li>
    </ul>
    <p style="margin-top: 8px;"><span class="label">Storage:</span></p>
    <ul>
      <li>Store in a cool, dry, well-ventilated place.</li>
      <li>Keep away from direct sunlight, heat, sparks, and flames.</li>
      <li>Keep container tightly closed.</li>
    </ul>
  </div>

  <div class="section">
    <h2>SECTION 8: EXPOSURE CONTROLS / PERSONAL PROTECTION</h2>
    <p><span class="label">Occupational Exposure Limit:</span> Ethanol OSHA PEL: 1000 ppm</p>
    <p><span class="label">Personal Protective Equipment:</span> No special PPE required for normal consumer cosmetic use.</p>
    <p><span class="label">Ventilation:</span> Use in a well-ventilated area.</p>
  </div>

  <div class="section">
    <h2>SECTION 9: PHYSICAL AND CHEMICAL PROPERTIES</h2>
    <table>
      <tbody>
        <tr><th>Appearance</th><td>Clear liquid</td></tr>
        <tr><th>Odor</th><td>{html.escape(odor)}</td></tr>
        <tr><th>Physical State</th><td>Liquid spray</td></tr>
        <tr><th>Flash Point</th><td>Approximately 16-25°C</td></tr>
        <tr><th>Boiling Point</th><td>Approximately 78°C</td></tr>
        <tr><th>Solubility</th><td>Partially soluble in water</td></tr>
        <tr><th>Flammability</th><td>Flammable liquid and vapor</td></tr>
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>SECTION 10: STABILITY AND REACTIVITY</h2>
    <p><span class="label">Reactivity:</span> No dangerous reaction known under normal use.</p>
    <p><span class="label">Chemical Stability:</span> Stable under recommended storage conditions.</p>
    <p><span class="label">Conditions to Avoid:</span> Heat, sparks, open flames, direct sunlight.</p>
    <p><span class="label">Incompatible Materials:</span> Strong oxidizing agents.</p>
    <p><span class="label">Hazardous Decomposition Products:</span> Carbon monoxide and carbon dioxide may form during combustion.</p>
  </div>

  <div class="section">
    <h2>SECTION 11: TOXICOLOGICAL INFORMATION</h2>
    <p>May cause mild skin or eye irritation. May cause allergic reaction in sensitive individuals. Low toxicity expected under normal cosmetic use.</p>
  </div>

  <div class="section">
    <h2>SECTION 12: ECOLOGICAL INFORMATION</h2>
    <p>No significant environmental hazard expected under normal consumer use. Avoid release of large quantities into drains, waterways, or soil.</p>
  </div>

  <div class="section">
    <h2>SECTION 13: DISPOSAL CONSIDERATIONS</h2>
    <p>Dispose of contents and container in accordance with local, state, and federal regulations. Do not dispose of large quantities into drains. Recycle packaging where possible.</p>
  </div>

  <div class="section">
    <h2>SECTION 14: TRANSPORT INFORMATION</h2>
    <table>
      <tbody>
        <tr><th>UN Number</th><td>UN1266</td></tr>
        <tr><th>Proper Shipping Name</th><td>Perfumery Products</td></tr>
        <tr><th>Hazard Class</th><td>3</td></tr>
        <tr><th>Packing Group</th><td>II</td></tr>
        <tr><th>Transport Hazard</th><td>Flammable Liquid</td></tr>
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>SECTION 15: REGULATORY INFORMATION</h2>
    <p>Prepared according to OSHA Hazard Communication Standard 29 CFR 1910.1200. Product is intended for cosmetic use. All components are used in accordance with applicable cosmetic fragrance regulations.</p>
  </div>

  <div class="section">
    <h2>SECTION 16: OTHER INFORMATION</h2>
    <p><span class="label">NFPA Rating:</span> Health: 2 | Flammability: 4 | Reactivity: 0</p>
    <p style="margin-top: 8px;">This Safety Data Sheet is provided for safe handling, storage, transportation, and regulatory review of cosmetic fragrance products.</p>
  </div>

  <div class="footer">End of Safety Data Sheet</div>
</body>
</html>
"""


def build_pdf(html_path: Path, pdf_path: Path) -> None:
    subprocess.run(
        [
            "wkhtmltopdf",
            "--quiet",
            "--margin-top",
            "0.75in",
            "--margin-right",
            "0.75in",
            "--margin-bottom",
            "0.75in",
            "--margin-left",
            "0.75in",
            str(html_path),
            str(pdf_path),
        ],
        check=True,
    )


def attach_paths(artifacts: list[SdsArtifact]) -> None:
    conn = _pg_connect()
    try:
        with conn:
            with conn.cursor() as cur:
                for item in artifacts:
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.products
                        SET tiktok_sds_file_path = %s,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (str(item.pdf_path), datetime.utcnow().isoformat(timespec="seconds"), item.product_id),
                    )
    finally:
        conn.close()


def generate(seed: ProductSeed) -> SdsArtifact:
    folder = SDS_ROOT / str(seed.product_id)
    folder.mkdir(parents=True, exist_ok=True)
    slug = slugify(seed.name)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    tex_path = folder / f"{slug}-sds.tex"
    html_path = folder / f"{slug}-sds.html"
    pdf_path = folder / f"{timestamp}-{slug}-sds.pdf"
    tex_path.write_text(render_tex(seed), encoding="utf-8")
    html_path.write_text(render_html(seed), encoding="utf-8")
    build_pdf(html_path, pdf_path)
    return SdsArtifact(
        product_id=seed.product_id,
        barcode=seed.barcode,
        name=seed.name,
        pdf_path=pdf_path,
        html_path=html_path,
        tex_path=tex_path,
    )


def main() -> int:
    artifacts = [generate(seed) for seed in SEEDS]
    attach_paths(artifacts)
    for item in artifacts:
        refreshed = get_product(item.product_id) or {}
        print(
            {
                "product_id": item.product_id,
                "barcode": item.barcode,
                "name": item.name,
                "pdf_path": str(item.pdf_path),
                "stored_path": refreshed.get("tiktok_sds_file_path"),
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

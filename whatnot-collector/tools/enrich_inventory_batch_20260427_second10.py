#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.company_db import get_product, utc_now
from server.postgres_cutover import POSTGRES_SIDECAR_SCHEMA, _pg_connect


MEDIA_ROOT = ROOT / "data" / "marketplace_images"
EXPORTS = ROOT / "exports"
REPORT_PATH = EXPORTS / "enrichment_batch_2026-04-27_second10_report.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}


@dataclass
class ProductSeed:
    product_id: int
    barcode: str
    brand: str
    name: str
    gender: str
    size_oz: float
    size_ml: int
    volume_oz: float
    volume_ml: int
    product_form: str
    manufacturer: str
    description_intro: str
    top_notes: str
    mid_notes: str
    base_notes: str
    scent: str
    feature: str
    keywords: str
    highlights: list[str]
    similar_to: str | None
    verified_note: str
    source_official_url: str | None
    source_jomashop_url: str | None
    source_fragrantica_url: str | None
    source_parfumo_url: str | None
    image_sources: list[str]
    package_weight_oz: float | None = None
    ingredients: str | None = None
    official_discrepancy_note: str | None = None


SEEDS: list[ProductSeed] = [
    ProductSeed(
        product_id=150,
        barcode="6085010044712",
        brand="Armaf",
        name="Armaf Club De Nuit Intense Man Eau de Toilette Spray 105ml (3.6 oz) Men's Perfume",
        gender="Men",
        size_oz=3.6,
        size_ml=105,
        volume_oz=3.6,
        volume_ml=105,
        product_form="Eau De Toilette",
        manufacturer="Sterling Perfumes Industries LLC",
        description_intro="A bold men's eau de toilette with a citrus-fruity opening, smoky floral heart, and musky amber-vanilla drydown.",
        top_notes="Lemon, Pineapple, Bergamot, Black Currant, Apple",
        mid_notes="Birch, Jasmine, Rose",
        base_notes="Musk, Ambergris, Patchouli, Vanilla",
        scent="Citrus fruity smoky woody",
        feature="eau de toilette spray; men; 105ml / 3.6 oz",
        keywords="Armaf, Club De Nuit Intense Man, Eau De Toilette, Men, 105ml, 3.6 oz, Lemon, Pineapple, Birch, Ambergris",
        highlights=[
            "Eau de toilette spray concentration.",
            "Men's fragrance from Armaf's Club De Nuit line.",
            "105 mL / 3.6 oz bottle size.",
            "Citrus-fruity opening with a smoky musky drydown.",
        ],
        similar_to="Creed Aventus",
        verified_note="Verified from Armaf official, Jomashop, Fragrantica, and Parfumo. Citrus-fruity smoky masculine profile with strong presence and an Aventus-style DNA; best when you want projection, especially evenings and cooler weather, but still versatile enough for everyday wear.",
        source_official_url="https://armaf.com/products/club-de-nuit-intense-man-3",
        source_jomashop_url="https://www.jomashop.com/armaf-mens-club-de-nuit-intense-edt-3-6-oz-fragrances-6085010044712.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Armaf/Club-de-Nuit-Intense-Man-34696.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Armaf/club-de-nuit-intense-man-eau-de-toilette",
        image_sources=[
            "https://armaf.com/cdn/shop/files/Q-106DCLUBDENUITINTENSE_M_FIF_900x_f04752b1-087d-4206-8985-e13e96c5896d.webp",
            "https://cdn2.jomashop.com/media/catalog/product/cache/b3e31d40bbb1abcc90b26106659d5d3f/a/r/armaf-mens-club-de-nuit-intense-edt-spray-36-oz-fragrances-6085010044712.jpg",
            "https://fimgs.net/mdimg/perfume/375x500.34696.jpg",
        ],
    ),
    ProductSeed(
        product_id=206,
        barcode="6294015164176",
        brand="Armaf",
        name="Armaf Club De Nuit Untold Eau de Parfum Spray 105ml (3.6 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.6,
        size_ml=105,
        volume_oz=3.6,
        volume_ml=105,
        product_form="Eau De Parfum",
        manufacturer="Sterling Perfumes Industries LLC",
        description_intro="A radiant unisex eau de parfum with a saffron-jasmine opening, warm amberwood core, and smooth resinous cedar finish.",
        top_notes="Saffron, Jasmine",
        mid_notes="Amberwood, Ambergris",
        base_notes="Fir Resin, Cedar",
        scent="Amber woody warm spicy",
        feature="eau de parfum spray; unisex; 105ml / 3.6 oz",
        keywords="Armaf, Club De Nuit Untold, Eau De Parfum, Unisex, 105ml, 3.6 oz, Saffron, Jasmine, Amberwood, Cedar",
        highlights=[
            "Eau de parfum spray concentration.",
            "Unisex fragrance from Armaf's Club De Nuit line.",
            "105 mL / 3.6 oz bottle size.",
            "Saffron-amber woody profile with strong statement wear energy.",
        ],
        similar_to="Maison Francis Kurkdjian Baccarat Rouge 540 Extrait de Parfum",
        verified_note="Verified from Armaf official, Jomashop, and Fragrantica. Warm amber-woody BR540-extrait style scent with strong projection and longevity; best when you want a loud, sweet-amber statement, especially for evening, cooler weather, or dressed-up wear.",
        source_official_url="https://armaf.com/products/club-de-nuit-untold-3-6-oz",
        source_jomashop_url="https://www.jomashop.com/open-box-armaf-unisex-club-de-nuit-untold-edp-spray-3-6-oz-105-ml-6294015164176.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Armaf/Club-de-Nuit-Untold-78476.html",
        source_parfumo_url=None,
        image_sources=[
            "https://armaf.com/cdn/shop/files/64.png",
            "https://fimgs.net/mdimg/perfume/375x500.78476.jpg",
            "https://m.media-amazon.com/images/I/61IR3JcacpL._SL1500_.jpg",
        ],
    ),
    ProductSeed(
        product_id=149,
        barcode="6085010094151",
        brand="Armaf",
        name="Armaf Club De Nuit Woman Eau de Parfum Spray 105ml (3.6 oz) Women's Perfume",
        gender="Women",
        size_oz=3.6,
        size_ml=105,
        volume_oz=3.6,
        volume_ml=105,
        product_form="Eau De Parfum",
        manufacturer="Sterling Perfumes Industries LLC",
        description_intro="A polished women's eau de parfum with sparkling citrus-fruit brightness, a soft floral heart, and a clean patchouli-musk finish.",
        top_notes="Bergamot, Grapefruit, Peach, Orange",
        mid_notes="Geranium, Jasmine, Litchi, Rose",
        base_notes="Musk, Patchouli, Vanilla, Vetiver",
        scent="Citrus floral patchouli musk",
        feature="eau de parfum spray; women; 105ml / 3.6 oz",
        keywords="Armaf, Club De Nuit Woman, Eau De Parfum, Women, 105ml, 3.6 oz, Bergamot, Rose, Patchouli, Vanilla",
        highlights=[
            "Eau de parfum spray concentration.",
            "Women's fragrance from Armaf's Club De Nuit line.",
            "105 mL / 3.6 oz bottle size.",
            "Bright citrus opening with elegant floral-patchouli depth.",
        ],
        similar_to="Chanel Coco Mademoiselle",
        verified_note="Verified from Armaf official and Fragrantica. Bright citrus-floral feminine profile with clean patchouli-musk sophistication; a common Coco Mademoiselle comparison, and an easy day-to-night choice for office, casual, and dressed-up wear.",
        source_official_url="https://armaf.com/products/club-de-nuit-w",
        source_jomashop_url="https://www.jomashop.com/armaf-ladies-club-de-nuit-edp-spray-3-6-oz-fragrances-6085010094151.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Armaf/Club-de-Nuit-Woman-27655.html",
        source_parfumo_url=None,
        image_sources=[
            "https://armaf.com/cdn/shop/files/CDN1.png",
            "https://fimgs.net/mdimg/perfume/375x500.27655.jpg",
            "https://fimgs.net/mdimg/perfume/375x500.26543.jpg",
        ],
    ),
    ProductSeed(
        product_id=157,
        barcode="6294015188622",
        brand="Armaf",
        name="Armaf Odyssey Candee Special Edition Eau de Parfum Spray 100ml (3.4 oz) Women's Perfume",
        gender="Women",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Sterling Perfumes Industries LLC",
        description_intro="A playful women's eau de parfum with juicy berry-citrus sparkle, a caramel-fruit heart, and a sweet musky patchouli finish.",
        top_notes="Strawberry, Raspberry, Geranium, Peach, Bergamot",
        mid_notes="Caramel, Jasmine, Passionfruit",
        base_notes="Patchouli, Musk, Amber",
        scent="Sweet fruity caramel musk",
        feature="eau de parfum spray; women; 100ml / 3.4 oz",
        keywords="Armaf, Odyssey Candee, Eau De Parfum, Women, 100ml, 3.4 oz, Strawberry, Caramel, Passionfruit, Patchouli",
        highlights=[
            "Eau de parfum spray concentration.",
            "Women's fragrance from Armaf's Odyssey collection.",
            "100 mL / 3.4 oz bottle size.",
            "Sweet berry-caramel profile with musky patchouli depth.",
        ],
        similar_to=None,
        verified_note="Verified from Armaf official, Fragrantica, and Parfumo. Sweet-fruity feminine scent with caramel and patchouli, strongest for playful social wear; source-backed community impression leans spring/summer and casual-to-evening wear rather than formal use.",
        source_official_url="https://armaf.com/products/odyssey-candee-special-edition",
        source_jomashop_url="https://www.jomashop.com/armaf-ladies-odyssey-candee-edp-spray-3-4-oz-fragrances-6294015188622.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Armaf/Odyssey-Candee-96990.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Armaf/odyssey-candee",
        image_sources=[
            "https://armaf.com/cdn/shop/files/armafbeach_11.png",
            "https://fimgs.net/mdimg/perfume/375x500.96990.jpg",
        ],
    ),
    ProductSeed(
        product_id=262,
        barcode="6290360591971",
        brand="Lattafa",
        name="Lattafa Pride Art of Arabia III Eau de Parfum Spray 100ml (3.4 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A deep unisex eau de parfum with aromatic spice up top, a rich tobacco-date heart, and a warm resinous vanilla base.",
        top_notes="Olibanum, Davana, Bergamot",
        mid_notes="Dates, Tobacco, Sandalwood, Tuberose",
        base_notes="Myrrh, Vanilla, Tonka Bean, Labdanum, Patchouli",
        scent="Spicy sweet oriental woody",
        feature="eau de parfum spray; unisex; 100ml / 3.4 oz",
        keywords="Lattafa Pride, Art of Arabia III, Eau De Parfum, Unisex, 100ml, 3.4 oz, Olibanum, Dates, Tobacco, Vanilla",
        highlights=[
            "Eau de parfum spray concentration.",
            "Unisex fragrance from Lattafa Pride.",
            "100 mL / 3.4 oz bottle size.",
            "Spicy-sweet tobacco amber profile with rich resinous depth.",
        ],
        similar_to="Clive Christian Blonde Amber",
        verified_note="Verified from Fragrantica and Parfumo, with Jomashop listing support for the barcode/size. Spicy-sweet amber-tobacco profile with above-average performance; best suited to cooler weather, formal settings, date nights, and richer evening wear.",
        source_official_url=None,
        source_jomashop_url=None,
        source_fragrantica_url="https://www.fragrantica.com/perfume/Lattafa-Perfumes/Art-of-Arabia-III-92425.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/lattafa-pride/art-of-arabia-iii",
        image_sources=[
            "https://fimgs.net/mdimg/perfume/375x500.92425.jpg",
        ],
    ),
    ProductSeed(
        product_id=158,
        barcode="6290362345183",
        brand="Asdaaf",
        name="Asdaaf Fouad Eau de Parfum Spray 100ml (3.4 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A refined unisex eau de parfum with a bright citrus-spice opening, warm saffron-cardamom heart, and smooth amber-woods drydown.",
        top_notes="Citrus, Spicy Notes",
        mid_notes="Cardamom, Saffron",
        base_notes="Precious Woods, Amber",
        scent="Amber woody spicy",
        feature="eau de parfum spray; unisex; 100ml / 3.4 oz",
        keywords="Asdaaf, Fouad, Eau De Parfum, Unisex, 100ml, 3.4 oz, Citrus, Cardamom, Saffron, Amber",
        highlights=[
            "Eau de parfum spray concentration.",
            "Unisex fragrance from Asdaaf.",
            "100 mL / 3.4 oz bottle size.",
            "Citrus-spice opening with saffron, woods, and amber depth.",
        ],
        similar_to=None,
        verified_note="Verified from Jomashop with Parfumo supporting the masculine-leaning positioning. Amber-woody citrus-spice profile with saffron/cardamom warmth; best for dressed-up wear, cooler evenings, and anyone who likes richer Middle Eastern-style compositions without going syrupy.",
        source_official_url=None,
        source_jomashop_url="https://www.jomashop.com/asdaaf-unisex-fouad-edp-spray-3-4-oz-fragrances-6290362345183.html",
        source_fragrantica_url=None,
        source_parfumo_url="https://www.parfumo.com/Perfumes/Asdaaf/fouad",
        image_sources=[
            "https://cdn2.jomashop.com/media/catalog/product/cache/b3e31d40bbb1abcc90b26106659d5d3f/a/s/asdaaf-unisex-fouad-edp-spray-34-oz-fragrances-6290362345183.jpg",
            "https://fimgs.net/mdimg/perfume/375x500.68297.jpg",
        ],
    ),
    ProductSeed(
        product_id=264,
        barcode="6290360598918",
        brand="Lattafa",
        name="Lattafa Atheeri Eau de Parfum Spray 100ml (3.4 oz) Women's Perfume",
        gender="Women",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A luminous women's eau de parfum with a dewy floral opening, soft orchid-jasmine heart, and creamy vanilla-amberwood finish.",
        top_notes="Passionflower, Dewdrop",
        mid_notes="Orchid, Jasmine",
        base_notes="Vanilla, Amberwood",
        scent="Floral gourmand airy vanilla",
        feature="eau de parfum spray; women; 100ml / 3.4 oz",
        keywords="Lattafa, Atheeri, Eau De Parfum, Women, 100ml, 3.4 oz, Passionflower, Orchid, Jasmine, Vanilla",
        highlights=[
            "Eau de parfum spray concentration.",
            "Women's fragrance from Lattafa.",
            "100 mL / 3.4 oz bottle size.",
            "Dewy floral-vanilla profile with a soft airy finish.",
        ],
        similar_to="Gucci Flora Gorgeous Orchid",
        verified_note="Verified from Lattafa official and Fragrantica. Airy floral-gourmand style with dewy freshness and soft vanilla-amberwood; strongest source-backed use case is spring/daytime and work-friendly wear, with a frequent community comparison to Gucci Flora Gorgeous Orchid.",
        source_official_url="https://lattafa.com/product/atheeri/",
        source_jomashop_url="https://www.jomashop.com/lattafa-ladies-atheeri-edp-spray-3-4-oz-fragrances-6290360598918.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Lattafa-Perfumes/Atheeri-105152.html",
        source_parfumo_url=None,
        image_sources=[
            "https://fimgs.net/mdimg/perfume/375x500.105152.jpg",
            "https://cdn2.jomashop.com/media/catalog/product/cache/b3e31d40bbb1abcc90b26106659d5d3f/l/a/lattafa-ladies-atheeri-edp-spray-34-oz-fragrances-6290360598918.jpg",
        ],
        official_discrepancy_note="Official copy says 'for everyone' in the prose while the product header and Fragrantica position it in the women's lane.",
    ),
    ProductSeed(
        product_id=265,
        barcode="6290360593722",
        brand="Lattafa",
        name="Lattafa Atlas Eau de Parfum Spray 55ml (1.85 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=1.85,
        size_ml=55,
        volume_oz=1.85,
        volume_ml=55,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A bold unisex eau de parfum with a salty marine opening, aromatic iris-davana heart, and mossy ambergris-sandalwood base.",
        top_notes="Salt, Sea Notes, Lemon",
        mid_notes="Iris, Davana",
        base_notes="Ambergris, Sandalwood, Oakmoss",
        scent="Marine salty aromatic woody",
        feature="eau de parfum spray; unisex; 55ml / 1.85 oz",
        keywords="Lattafa, Atlas, Eau De Parfum, Unisex, 55ml, 1.85 oz, Sea Notes, Iris, Ambergris, Sandalwood",
        highlights=[
            "Eau de parfum spray concentration.",
            "Unisex fragrance from Lattafa.",
            "55 mL / 1.85 oz bottle size.",
            "Salty marine profile with mossy ambergris depth.",
        ],
        similar_to="Orto Parisi Megamare",
        verified_note="Verified from Lattafa official and Fragrantica, with Jomashop listing support for the barcode/size. Salty marine powerhouse with strong projection and a clear Megamare-style comparison; best for confident wear and people who want bold oceanic presence rather than an easy blind buy.",
        source_official_url="https://lattafa.com/product/atlas/",
        source_jomashop_url=None,
        source_fragrantica_url="https://www.fragrantica.com/perfume/Lattafa-Perfumes/Atlas-89765.html",
        source_parfumo_url=None,
        image_sources=[
            "https://fimgs.net/mdimg/perfume/375x500.89765.jpg",
        ],
        official_discrepancy_note="Official page labels Atlas in the men's lane, while Fragrantica lists it for women and men; saved as unisex to avoid forcing a narrower claim.",
    ),
    ProductSeed(
        product_id=199,
        barcode="6290360593142",
        brand="Lattafa",
        name="Lattafa Bade'e Al Oud Sublime Eau de Parfum Spray 100ml (3.4 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A bright unisex eau de parfum with juicy fruit up top, a soft floral-plum heart, and a smooth mossy vanilla patchouli base.",
        top_notes="Apple, Litchi, Rose",
        mid_notes="Plum, Jasmine",
        base_notes="Moss, Vanilla, Patchouli",
        scent="Fruity floral woody",
        feature="eau de parfum spray; unisex; 100ml / 3.4 oz",
        keywords="Lattafa, Bade'e Al Oud Sublime, Eau De Parfum, Unisex, 100ml, 3.4 oz, Apple, Litchi, Plum, Vanilla",
        highlights=[
            "Eau de parfum spray concentration.",
            "Unisex fragrance from Lattafa's Bade'e Al Oud line.",
            "100 mL / 3.4 oz bottle size.",
            "Juicy fruit opening with soft mossy-vanilla depth.",
        ],
        similar_to="Kayali Eden Sparkling Lychee | 39",
        verified_note="Verified from Lattafa official, Fragrantica, and Jomashop listing support. Fruity-floral woody profile with easy spring/summer daytime appeal; community comparisons consistently point toward Kayali's Eden Sparkling Lychee lane rather than a dark oud style.",
        source_official_url="https://lattafa.com/product/badee-al-oud-sublime/",
        source_jomashop_url="https://www.jomashop.com/lattafa-mens-bade-e-al-oud-oud-for-glory-sublime-edp-3-4-oz-fragrances-6290360593142.html?recrawl=true",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Lattafa-Perfumes/Badee-Al-Oud-Sublime-83309.html",
        source_parfumo_url=None,
        image_sources=[
            "https://www.lattafa-usa.com/cdn/shop/files/Badee-Al-Oud-Sublime-2.png?v=1747421363&width=810",
            "https://fimgs.net/mdimg/perfume/375x500.83309.jpg",
        ],
        official_discrepancy_note="Official page contains two conflicting note sets on the same page; saved data follows the cleaner Fragrantica pyramid that matches the broader community consensus.",
    ),
    ProductSeed(
        product_id=171,
        barcode="6291108326428",
        brand="Fragrance World",
        name="Fragrance World Barakkat Rouge 540 Extrait de Parfum Spray 100ml (3.4 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Extrait De Parfum",
        manufacturer="Fragrance World",
        description_intro="A rich unisex extrait de parfum with bitter almond and saffron up top, a jasmine-cedar core, and a warm woody musky ambergris finish.",
        top_notes="Bitter Almond, Saffron",
        mid_notes="Cedar, Jasmine",
        base_notes="Woody Notes, Ambergris, Musk",
        scent="Oriental woody amber musky",
        feature="extrait de parfum spray; unisex; 100ml / 3.4 oz",
        keywords="Fragrance World, Barakkat Rouge 540, Extrait De Parfum, Unisex, 100ml, 3.4 oz, Saffron, Bitter Almond, Jasmine, Ambergris",
        highlights=[
            "Extrait de parfum spray concentration.",
            "Unisex fragrance from Fragrance World.",
            "100 mL / 3.4 oz bottle size.",
            "Warm almond-saffron amber profile with strong statement wear character.",
        ],
        similar_to="Maison Francis Kurkdjian Baccarat Rouge 540 Extrait de Parfum",
        verified_note="Verified from Fragrantica and multiple retail listings tied to the barcode/size. BR540-extrait style oriental woody profile with bitter almond, saffron, jasmine, and musky woods; best for statement wear, evening use, and anyone specifically shopping this DNA.",
        source_official_url=None,
        source_jomashop_url=None,
        source_fragrantica_url="https://www.fragrantica.com/perfume/Fragrance-World/Barakkat-Rouge-540-Extrait-de-Parfum-107710.html",
        source_parfumo_url=None,
        image_sources=[
            "https://fimgs.net/mdimg/perfume/375x500.107710.jpg",
        ],
        official_discrepancy_note="Retailers split between women's and unisex positioning; Fragrantica lists it for women and men, so the saved record uses unisex.",
    ),
]


def category_name_for_gender(gender: str) -> str:
    value = (gender or "").strip().lower()
    if value in {"men", "male"}:
        return "Beauty & Personal Care - Fragrance - Men's Fragrance"
    if value in {"women", "female"}:
        return "Beauty & Personal Care - Fragrance - Women's Fragrance"
    return "Beauty & Personal Care - Fragrance - Unisex Fragrance"


def volume_text(seed: ProductSeed) -> str:
    return f"{seed.volume_ml} mL / {seed.volume_oz} oz"


def description_text(seed: ProductSeed) -> str:
    return (
        f"{seed.description_intro}\n\n"
        f"Top Notes: {seed.top_notes}\n"
        f"Middle Notes: {seed.mid_notes}\n"
        f"Base Notes: {seed.base_notes}\n\n"
        f"Size: {seed.size_oz} oz / {seed.size_ml} mL\n"
        f"Gender: {seed.gender}"
    )


def description_html(seed: ProductSeed) -> str:
    return (
        f"<p>{seed.description_intro}</p>"
        f"<p>Top Notes: {seed.top_notes}<br>"
        f"Middle Notes: {seed.mid_notes}<br>"
        f"Base Notes: {seed.base_notes}<br><br>"
        f"Size: {seed.size_oz} oz / {seed.size_ml} mL<br>"
        f"Gender: {seed.gender}</p>"
    )


def sanitize_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def download_image(product_id: int, index: int, source: str) -> str | None:
    if not source:
        return None
    try:
        response = requests.get(source, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except Exception:
        return None
    content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    suffix = ".jpg"
    if "png" in content_type or source.lower().endswith(".png"):
        suffix = ".png"
    elif "webp" in content_type or source.lower().endswith(".webp"):
        suffix = ".webp"
    elif "avif" in content_type or source.lower().endswith(".avif"):
        suffix = ".avif"
    folder = MEDIA_ROOT / str(product_id)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{index:02d}-{sanitize_slug(Path(source).stem)[:48]}{suffix}"
    target = folder / filename
    target.write_bytes(response.content)
    return f"/marketplace-media/{product_id}/{filename}"


def build_gallery(seed: ProductSeed, current: dict[str, Any]) -> tuple[str | None, str | None]:
    gallery: list[str] = []
    seen: set[str] = set()
    sources = list(seed.image_sources)
    current_media = str(current.get("media_url") or "").strip()
    if current_media:
        sources.append(current_media)
    for source in sources:
        normalized = source.strip()
        if not normalized or normalized in seen:
            continue
        local = download_image(seed.product_id, len(gallery) + 1, normalized)
        if local and local not in seen:
            seen.add(local)
            gallery.append(local)
    primary = gallery[0] if gallery else (current_media or None)
    gallery_json = json.dumps(gallery, ensure_ascii=True) if gallery else None
    return primary, gallery_json


def update_product(seed: ProductSeed) -> dict[str, Any]:
    current = get_product(seed.product_id) or {}
    primary_image, gallery_json = build_gallery(seed, current)
    now = utc_now()
    updates = {
        "name": seed.name,
        "brand": seed.brand,
        "gender": seed.gender,
        "description": description_text(seed),
        "notes": seed.verified_note,
        "note_top": seed.top_notes,
        "note_mid": seed.mid_notes,
        "note_base": seed.base_notes,
        "size_oz": seed.size_oz,
        "size_ml": seed.size_ml,
        "volume_oz": seed.volume_oz,
        "volume_ml": seed.volume_ml,
        "media_url": primary_image,
        "image_gallery_urls": gallery_json,
        "notes_verified": 1,
        "notes_verified_at": now,
        "similar_to": seed.similar_to,
        "dupe_inspiration": seed.similar_to,
        "ingredients": seed.ingredients,
        "source_official_url": seed.source_official_url,
        "source_jomashop_url": seed.source_jomashop_url,
        "source_fragrantica_url": seed.source_fragrantica_url,
        "source_parfumo_url": seed.source_parfumo_url,
        "tiktok_title": seed.name,
        "tiktok_item_name": seed.name,
        "tiktok_category_name": category_name_for_gender(seed.gender),
        "tiktok_brand": seed.brand,
        "tiktok_manufacturer": seed.manufacturer,
        "tiktok_feature": seed.feature,
        "tiktok_search_keywords": seed.keywords,
        "tiktok_scent": seed.scent,
        "tiktok_product_form": seed.product_form,
        "tiktok_fragrance_concentration": seed.product_form,
        "tiktok_volume": volume_text(seed),
        "tiktok_description": description_html(seed),
        "tiktok_highlights": "\n".join(seed.highlights),
        "tiktok_pack_type": "Single item",
        "tiktok_container_type": "Spray",
        "tiktok_age_group": "Adult",
        "tiktok_region_of_origin": "United Arab Emirates",
        "tiktok_ingredients": seed.ingredients,
        "updated_at": now,
    }
    if seed.package_weight_oz is not None:
        updates["tiktok_package_weight_oz"] = seed.package_weight_oz
    assignments = ", ".join(f"{column} = %s" for column in updates)
    params = list(updates.values()) + [seed.product_id]
    conn = _pg_connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.products (
                        id, name, sku, barcode, category_id, product_type, image_path,
                        cost_price, retail_price, on_hand_qty, low_stock_threshold, active,
                        created_at, updated_at, brand, supplier_name, storage_bin,
                        notes, note_top, note_mid, note_base, media_url, description,
                        ingredients, script, dupe_inspiration, dupe_confidence,
                        dupe_classification, dupe_notes, gender, notes_verified,
                        notes_verified_at, raw_cost, cost_plus_12, cost_plus_20
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        seed.product_id,
                        current.get("name") or seed.name,
                        current.get("sku"),
                        seed.barcode,
                        current.get("category_id"),
                        current.get("product_type"),
                        current.get("image_path"),
                        current.get("cost_price"),
                        current.get("retail_price"),
                        current.get("on_hand_qty"),
                        current.get("low_stock_threshold"),
                        current.get("active"),
                        current.get("created_at") or now,
                        current.get("updated_at") or now,
                        current.get("brand") or seed.brand,
                        current.get("supplier_name"),
                        current.get("storage_bin"),
                        current.get("notes"),
                        current.get("note_top"),
                        current.get("note_mid"),
                        current.get("note_base"),
                        current.get("media_url"),
                        current.get("description"),
                        current.get("ingredients"),
                        current.get("script"),
                        current.get("dupe_inspiration"),
                        current.get("dupe_confidence"),
                        current.get("dupe_classification"),
                        current.get("dupe_notes"),
                        current.get("gender") or seed.gender,
                        current.get("notes_verified"),
                        current.get("notes_verified_at"),
                        current.get("raw_cost") or 0,
                        current.get("cost_plus_12") or 0,
                        current.get("cost_plus_20") or 0,
                    ),
                )
                cur.execute(
                    f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.products SET {assignments} WHERE id = %s",
                    params,
                )
    finally:
        conn.close()
    return {
        "product_id": seed.product_id,
        "barcode": seed.barcode,
        "name": seed.name,
        "gallery_count": 0 if not gallery_json else len(json.loads(gallery_json)),
        "primary_image": primary_image,
        "source_official_url": seed.source_official_url,
        "source_jomashop_url": seed.source_jomashop_url,
        "source_fragrantica_url": seed.source_fragrantica_url,
        "source_parfumo_url": seed.source_parfumo_url,
        "discrepancy_note": seed.official_discrepancy_note,
    }


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    results = [update_product(seed) for seed in SEEDS]
    REPORT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps({"updated": len(results), "report": str(REPORT_PATH), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

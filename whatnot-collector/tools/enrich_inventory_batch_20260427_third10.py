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
REPORT_PATH = EXPORTS / "enrichment_batch_2026-04-27_third10_report.json"
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
        product_id=221,
        barcode="3760060761897",
        brand="Dumont",
        name="Dumont Nitro Blue Eau de Parfum Spray 100ml (3.4 oz) Men's Perfume",
        gender="Men",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Dumont Perfumes Factory L.L.C.",
        description_intro="A warm men's eau de parfum with aromatic citrus spice up top, a praline-woody core, and a sweet amber-rosewood finish.",
        top_notes="Orange Blossom, Cinnamon, Sage, Lemon, Basil",
        mid_notes="Praline, Tolu Balsam, Woody Notes, Black Cardamom",
        base_notes="Sweet Notes, Patchouli, Black Amber, Brazilian Rosewood",
        scent="Warm spicy sweet woody",
        feature="eau de parfum spray; men; 100ml / 3.4 oz",
        keywords="Dumont, Nitro Blue, Eau De Parfum, Men, 100ml, 3.4 oz, Orange Blossom, Praline, Black Amber, Rosewood",
        highlights=[
            "Eau de parfum spray concentration.",
            "Men's fragrance from Dumont's Nitro line.",
            "100 mL / 3.4 oz bottle size.",
            "Warm spicy-sweet profile with praline and woody amber depth.",
        ],
        similar_to=None,
        verified_note="Verified from Dumont official, Fragrantica, and Parfumo. Warm spicy-sweet masculine scent with above-average performance; source-backed guidance leans cooler weather, evening wear, and social settings rather than a fresh daytime 'blue' scent despite the name.",
        source_official_url="https://dumontparfums.com/products/nitro-blue",
        source_jomashop_url="https://www.jomashop.com/dumont-mens-nitro-blue-edp-spray-3-4-oz-fragrances-3760060761897.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Dumont/Nitro-Blue-73021.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Dumont/Nitro_Blue",
        image_sources=[
            "https://dumontparfums.com/cdn/shop/products/NitroBlue1_large.jpg?v=1751280785",
            "https://dumontparfums.com/cdn/shop/products/NitroBlue2_large.jpg?v=1751280785",
            "https://fimgs.net/mdimg/perfume/375x500.73021.jpg",
        ],
    ),
    ProductSeed(
        product_id=220,
        barcode="3760060761279",
        brand="Dumont",
        name="Dumont Nitro Green Eau de Parfum Spray 100ml (3.4 oz) Men's Perfume",
        gender="Men",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Dumont Perfumes Factory L.L.C.",
        description_intro="A modern men's eau de parfum with sweet saffron-vanilla brightness, aromatic lavender depth, and an earthy woody finish.",
        top_notes="Vanilla, Saffron, Jasmine",
        mid_notes="Lavender, Amberwood, Light Amber, Green Leaves, Cedar, Ambergris",
        base_notes="Earthy Notes, Violet, Fir Resin, Cedar",
        scent="Sweet aromatic fougere woody",
        feature="eau de parfum spray; men; 100ml / 3.4 oz",
        keywords="Dumont, Nitro Green, Eau De Parfum, Men, 100ml, 3.4 oz, Vanilla, Saffron, Lavender, Amberwood",
        highlights=[
            "Eau de parfum spray concentration.",
            "Men's fragrance from Dumont's Nitro line.",
            "100 mL / 3.4 oz bottle size.",
            "Sweet aromatic profile with vanilla, lavender, and woody depth.",
        ],
        similar_to="Jean Paul Gaultier Ultra Male / Afnan 9PM",
        verified_note="Verified from Dumont official, Fragrantica, and Parfumo. Sweet aromatic masculine scent with a familiar Ultra Male / 9PM-style lane; best for cooler weather, social wear, and mass-appeal evenings. Parfumo lists a different pyramid, so the saved notes follow the official and Fragrantica alignment.",
        source_official_url="https://dumontparfums.com/products/nitro-green",
        source_jomashop_url="https://www.jomashop.com/dumont-mens-nitro-green-edp-spray-3-4-oz-fragrances-3760060761279.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Dumont/Nitro-Green-73024.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Dumont/Nitro_Green",
        image_sources=[
            "https://cdn.shopify.com/s/files/1/0742/3105/4646/products/NitroGreen1_large.jpg?v=1751280778",
            "https://cdn.shopify.com/s/files/1/0742/3105/4646/products/NitroGreen2_large.jpg?v=1751280778",
        ],
        official_discrepancy_note="Parfumo shows a fresher citrus-herbal pyramid, while Dumont official and Fragrantica agree on the sweeter vanilla-saffron-lavender structure.",
    ),
    ProductSeed(
        product_id=250,
        barcode="3760060762870",
        brand="Dumont",
        name="Dumont Nitro Platinum Eau de Parfum Spray 100ml (3.4 oz) Men's Perfume",
        gender="Men",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Dumont Perfumes Factory L.L.C.",
        description_intro="A vibrant men's eau de parfum with fruity citrus spice up top, a sweet amber-vanilla heart, and a woody musky finish.",
        top_notes="Bergamot, Apple, Blackcurrant, Orange, Pink Pepper, Cardamom",
        mid_notes="Amber, Candy Sugar, Lily of the Valley, Saffron, Dry Wood, Vanilla",
        base_notes="Cedarwood, Vanilla, Moss, Musk, Amber, Guaiac Wood",
        scent="Fruity woody sweet amber",
        feature="eau de parfum spray; men; 100ml / 3.4 oz",
        keywords="Dumont, Nitro Platinum, Eau De Parfum, Men, 100ml, 3.4 oz, Blackcurrant, Cardamom, Vanilla, Guaiac Wood",
        highlights=[
            "Eau de parfum spray concentration.",
            "Men's fragrance from Dumont's Nitro line.",
            "100 mL / 3.4 oz bottle size.",
            "Fruity-sweet woody profile with vanilla and amber depth.",
        ],
        similar_to=None,
        verified_note="Verified from Dumont official, Fragrantica, and Parfumo. Fruity-sweet woody masculine scent with above-average longevity; source-backed wear guidance points to a versatile profile that still feels best when sweeter pineapple-amber styles are welcome.",
        source_official_url="https://dumontparfums.com/products/nitro-platinum",
        source_jomashop_url="https://www.jomashop.com/dumont-mens-nitro-platinum-edp-3-4-oz-fragrances-3760060762870.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Dumont/Nitro-Platinum-101991.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Dumont/nitro-platinum",
        image_sources=[
            "https://dumontparfums.com/cdn/shop/products/NitroPlatinum2_large.jpg?v=1751280771",
            "https://fimgs.net/mdimg/perfume/375x500.101991.jpg",
        ],
    ),
    ProductSeed(
        product_id=223,
        barcode="3770004268191",
        brand="Dumont",
        name="Dumont Nitro Pour Homme Eau de Parfum Spray 100ml (3.4 oz) Men's Perfume",
        gender="Men",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Dumont Perfumes Factory L.L.C.",
        description_intro="A crisp men's eau de parfum with sparkling citrus-spice up top, floral woods through the heart, and a smooth musky tonka base.",
        top_notes="Lemon, Bergamot, Grapefruit, Mandarin, Nutmeg, Cardamom",
        mid_notes="Rose, Jasmine, Orange Blossom",
        base_notes="Sandalwood, Cedar Wood, Guaiac Wood, Tonka Bean, Musk",
        scent="Citrus woody aromatic",
        feature="eau de parfum spray; men; 100ml / 3.4 oz",
        keywords="Dumont, Nitro Pour Homme, Eau De Parfum, Men, 100ml, 3.4 oz, Lemon, Grapefruit, Orange Blossom, Tonka Bean",
        highlights=[
            "Eau de parfum spray concentration.",
            "Men's fragrance from Dumont's Nitro line.",
            "100 mL / 3.4 oz bottle size.",
            "Fresh citrus opening with floral woods and musky tonka depth.",
        ],
        similar_to=None,
        verified_note="Verified from Dumont official and Fragrantica, with Jomashop retailer support. Crisp citrus-woody masculine profile that reads more versatile and easier to wear than the sweeter Nitro flankers; good for everyday, office, and general-purpose masculine wear.",
        source_official_url="https://dumontparfums.com/products/nitro-pour-homme",
        source_jomashop_url="https://www.jomashop.com/dumont-mens-nitro-pour-homme-edp-spray-3-4-oz-fragrances-3770004268191.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Dumont/Nitro-Pour-Homme-73020.html",
        source_parfumo_url=None,
        image_sources=[
            "https://dumontparfums.com/cdn/shop/products/NitroPourHomme2_large.jpg?v=1751280808",
            "https://fimgs.net/mdimg/perfume/375x500.73020.jpg",
        ],
    ),
    ProductSeed(
        product_id=153,
        barcode="3760060761880",
        brand="Dumont",
        name="Dumont Nitro Red Eau de Parfum Spray 100ml (3.4 oz) Men's Perfume",
        gender="Men",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Dumont Perfumes Factory L.L.C.",
        description_intro="A bold men's eau de parfum with fruity aromatic energy, juicy watermelon through the heart, and warm woods in the drydown.",
        top_notes="Bergamot, Lavender, Apple",
        mid_notes="Watermelon, Cedarwood, Calamus",
        base_notes="Sandalwood, Patchouli, Amber",
        scent="Fruity fresh aquatic woody",
        feature="eau de parfum spray; men; 100ml / 3.4 oz",
        keywords="Dumont, Nitro Red, Eau De Parfum, Men, 100ml, 3.4 oz, Bergamot, Watermelon, Cedarwood, Amber",
        highlights=[
            "Eau de parfum spray concentration.",
            "Men's fragrance from Dumont's Nitro line.",
            "100 mL / 3.4 oz bottle size.",
            "Juicy fruity-aquatic style with warm amber-wood depth.",
        ],
        similar_to="Rabanne Invictus / Rasasi Hawas",
        verified_note="Verified from Dumont official, Jomashop, Fragrantica, and Parfumo. Youthful fruity-fresh masculine scent with strong projection and longevity; source-backed guidance clearly points to casual wear, parties, and nightlife rather than formal settings.",
        source_official_url="https://dumontparfums.com/products/nitro-red",
        source_jomashop_url="https://www.jomashop.com/dumont-mens-nitro-red-edp-spray-3-4-oz-fragrances-3760060761880.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Dumont/Nitro-Red-73023.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Dumont/Nitro_Red",
        image_sources=[
            "https://fimgs.net/mdimg/perfume/375x500.73023.jpg",
            "https://m.media-amazon.com/images/I/41E3eygC4FL._SY300_SX300_QL70_FMwebp_.jpg",
        ],
        official_discrepancy_note="Jomashop's long description uses a different note set, but the official Dumont page matches Fragrantica and Parfumo, so the saved notes follow that aligned version.",
    ),
    ProductSeed(
        product_id=222,
        barcode="3760060764171",
        brand="Dumont",
        name="Dumont Nitro White Eau de Parfum Spray 100ml (3.4 oz) Men's Perfume",
        gender="Men",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Dumont Perfumes Factory L.L.C.",
        description_intro="A creamy men's eau de parfum with aromatic freshness up top, resinous woods through the heart, and honeyed vanilla warmth in the base.",
        top_notes="Cypress, Iris, Juniper Berries",
        mid_notes="Patchouli, Myrrh",
        base_notes="Musk, Amber, Honey, Vanilla, Leather",
        scent="Sweet gourmand creamy woody",
        feature="eau de parfum spray; men; 100ml / 3.4 oz",
        keywords="Dumont, Nitro White, Eau De Parfum, Men, 100ml, 3.4 oz, Iris, Myrrh, Honey, Vanilla",
        highlights=[
            "Eau de parfum spray concentration.",
            "Men's fragrance from Dumont's Nitro line.",
            "100 mL / 3.4 oz bottle size.",
            "Creamy honey-vanilla profile with woody resinous depth.",
        ],
        similar_to=None,
        verified_note="Verified from Dumont official, Fragrantica, and Parfumo. Sweet gourmand-leaning masculine scent with above-average performance; best where honeyed vanilla warmth works well, especially cooler weather and social use, while still leaning more polished than loud candy sweetness.",
        source_official_url="https://dumontparfums.com/products/nitro-white",
        source_jomashop_url="https://www.jomashop.com/dumont-mens-nitro-white-edp-spray-3-4-oz-fragrances-3760060764171.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Dumont/Nitro-White-95995.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Dumont/Nitro_White",
        image_sources=[
            "https://dumontparfums.com/cdn/shop/products/NitroWhite1_large.jpg?v=1751280763",
            "https://dumontparfums.com/cdn/shop/products/NitroWhite2_large.jpg?v=1751280763",
        ],
    ),
    ProductSeed(
        product_id=195,
        barcode="6290360598901",
        brand="Lattafa",
        name="Lattafa Fire On Ice Eau de Parfum Spray 110ml (3.71 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.71,
        size_ml=110,
        volume_oz=3.71,
        volume_ml=110,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A cozy unisex eau de parfum with boozy berry spice up top, a caramel-rose heart, and a smoky woody ambroxan finish.",
        top_notes="Black Raspberry, Cinnamon, Cognac (Liquor)",
        mid_notes="Frozen Rose Petals, Caramel, Moss",
        base_notes="Oakwood, Myrrh, Cedarwood, Ambroxan",
        scent="Sweet fruity boozy woody",
        feature="eau de parfum spray; unisex; 110ml / 3.71 oz",
        keywords="Lattafa, Fire On Ice, Eau De Parfum, Unisex, 110ml, 3.71 oz, Black Raspberry, Cognac, Caramel, Ambroxan",
        highlights=[
            "Eau de parfum spray concentration.",
            "Unisex fragrance from Lattafa.",
            "110 mL / 3.71 oz bottle size.",
            "Boozy berry-caramel profile with smoky woody depth.",
        ],
        similar_to="Kilian Angels' Share Paradis",
        verified_note="Verified from Lattafa official, Fragrantica, and Parfumo. Sweet-fruity boozy unisex profile with a strong cooler-weather and evening lean; community comparison most consistently points toward the Angels' Share / Angels' Share Paradis direction, especially for social or intimate wear.",
        source_official_url="https://lattafa.com/product/fire-on-ice/",
        source_jomashop_url="https://www.jomashop.com/lattafa-unisex-fire-on-ice-edp-spray-3.71-oz-fragrances-6290360598901.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Lattafa-Perfumes/Fire-On-Ice-111414.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Lattafa/fire-on-ice",
        image_sources=[
            "https://www.lattafa-usa.com/cdn/shop/files/1_cf2474fb-b1d3-4caf-9adc-86efcccaeb9d.png?v=1756361729&width=810",
            "https://fimgs.net/mdimg/perfume/375x500.111414.jpg",
        ],
    ),
    ProductSeed(
        product_id=217,
        barcode="6290362348061",
        brand="Lattafa",
        name="Lattafa Pride Mini Gift Set 100ml Total (Vintage Radio Edition) Unisex Fragrance Set",
        gender="Unisex",
        size_oz=3.38,
        size_ml=100,
        volume_oz=3.38,
        volume_ml=100,
        product_form="Gift Set",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A curated unisex mini fragrance set featuring five 20ml Lattafa Pride scents for travel, sampling, and gifting.",
        top_notes="Varies by included fragrance in the set",
        mid_notes="Varies by included fragrance in the set",
        base_notes="Varies by included fragrance in the set",
        scent="Mixed discovery set",
        feature="5 x 20ml eau de parfum sprays; unisex fragrance gift set; total 100ml",
        keywords="Lattafa Pride, Mini Gift Set, Vintage Radio, Shaheen Silver, African Drummer, Shuyukh Silver, Bike 1910, 5x20ml",
        highlights=[
            "Gift set with five 20 mL mini fragrance sprays.",
            "Unisex Lattafa Pride discovery-style set.",
            "Total fill volume 100 mL / 3.38 oz.",
            "Includes Bike 1910, Shaheen Silver, African Drummer, Shuyukh Silver, and Vintage Radio.",
        ],
        similar_to=None,
        verified_note="Verified from Lattafa UK and retailer mirrors tied to the barcode. This is a mixed mini set rather than one fragrance pyramid; best used as a discovery, travel, or gifting set with Bike 1910, Shaheen Silver, African Drummer, Shuyukh Silver, and Vintage Radio.",
        source_official_url="https://www.lattafasuk.com/p/lattafa-pride-5x20ml-giftset/",
        source_jomashop_url="https://www.jomashop.com/lattafa-mini-set-gift-set-fragrances-6290362348061.html",
        source_fragrantica_url=None,
        source_parfumo_url=None,
        image_sources=[
            "https://cdn2.jomashop.com/media/catalog/product/cache/0ee3019724ce73007b606b54ba535a23/l/a/lattafa-mini-set-gift-set-fragrances-6290362348061.jpg?width=546&height=546",
        ],
    ),
    ProductSeed(
        product_id=225,
        barcode="6290362348092",
        brand="Lattafa",
        name="Lattafa Pride Mini Gift Set 100ml Total (Nebras Edition) Unisex Fragrance Set",
        gender="Unisex",
        size_oz=3.38,
        size_ml=100,
        volume_oz=3.38,
        volume_ml=100,
        product_form="Gift Set",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A curated unisex mini fragrance set featuring five 20ml Lattafa Pride scents for sampling, travel, and gifting.",
        top_notes="Varies by included fragrance in the set",
        mid_notes="Varies by included fragrance in the set",
        base_notes="Varies by included fragrance in the set",
        scent="Mixed discovery set",
        feature="5 x 20ml eau de parfum sprays; unisex fragrance gift set; total 100ml",
        keywords="Lattafa Pride, Mini Gift Set, Nebras, Art of Wood, Art of Universe, Ansaam Gold, Kashan, 5x20ml",
        highlights=[
            "Gift set with five 20 mL mini fragrance sprays.",
            "Unisex Lattafa Pride discovery-style set.",
            "Total fill volume 100 mL / 3.38 oz.",
            "Includes Nebras, Art of Wood, Art of Universe, Ansaam Gold, and Kashan.",
        ],
        similar_to=None,
        verified_note="Verified from multiple retailer mirrors tied to the barcode. This is a mixed mini set rather than one fragrance pyramid; best used as a discovery, travel, or gifting set with Nebras, Art of Wood, Art of Universe, Ansaam Gold, and Kashan.",
        source_official_url=None,
        source_jomashop_url="https://www.jomashop.com/lattafa-mini-set-gift-set-fragrances-6290362348092.html",
        source_fragrantica_url=None,
        source_parfumo_url=None,
        image_sources=[
            "https://cdn2.jomashop.com/media/catalog/product/cache/0ee3019724ce73007b606b54ba535a23/l/a/lattafa-mini-set-gift-set-fragrances-6290362348092.jpg?width=546&height=546",
        ],
        official_discrepancy_note="Set contents were verified from retailer sources rather than an exact official product page tied to this barcode.",
    ),
    ProductSeed(
        product_id=205,
        barcode="6291108733226",
        brand="Lattafa",
        name="Lattafa Ana Abiyedh Poudree Eau de Parfum Spray 60ml (2.0 oz) Women's Perfume",
        gender="Women",
        size_oz=2.0,
        size_ml=60,
        volume_oz=2.0,
        volume_ml=60,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A soft women's eau de parfum with a floral opening, creamy musky heart, and powdery vanilla-woody base.",
        top_notes="Orange Blossom, Rose, Jasmine",
        mid_notes="Musk",
        base_notes="Vanilla, Tonka Bean, Cedar, Vetiver, Patchouli",
        scent="Powdery vanilla musk floral",
        feature="eau de parfum spray; women; 60ml / 2.0 oz",
        keywords="Lattafa, Ana Abiyedh Poudree, Eau De Parfum, Women, 60ml, 2.0 oz, Orange Blossom, Musk, Vanilla, Tonka Bean",
        highlights=[
            "Eau de parfum spray concentration.",
            "Women's fragrance from Lattafa.",
            "60 mL / 2.0 oz bottle size.",
            "Powdery musky vanilla profile with soft floral warmth.",
        ],
        similar_to=None,
        verified_note="Verified from Fragrantica, Parfumo, and Jomashop. Powdery-sweet feminine scent with a soft cozy style; strongest source-backed use case points to easy everyday wear, office wear, and comfort-scent use rather than loud statement wear.",
        source_official_url=None,
        source_jomashop_url="https://www.jomashop.com/lattafa-ana-abiyedh-poudree-edp-spray-2-0-oz-fragrances-6291108733226.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Lattafa-Perfumes/Ana-Abiyedh-Poudree-84590.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Lattafa/ana-abiyedh-poudree",
        image_sources=[
            "https://fimgs.net/mdimg/perfume/375x500.84590.jpg",
            "https://m.media-amazon.com/images/I/713dFPPTuOL._SL1500_.jpg",
        ],
        official_discrepancy_note="Lattafa's official public page exists for Ana Abiyedh, not the Poudree flanker, so the saved record relies on Fragrantica, Parfumo, and retailer data for this exact barcode.",
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
        sources.extend([s.strip() for s in current_media.splitlines() if s.strip()])
    for source in sources:
        normalized = source.strip()
        if not normalized or normalized in seen:
            continue
        local = download_image(seed.product_id, len(gallery) + 1, normalized)
        if local and local not in seen:
            seen.add(local)
            gallery.append(local)
    primary = gallery[0] if gallery else ((current_media.splitlines()[0].strip() if current_media else None))
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
        "tiktok_pack_type": "Single item" if seed.product_form != "Gift Set" else "Gift set",
        "tiktok_container_type": "Spray" if seed.product_form != "Gift Set" else "Multi-item set",
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

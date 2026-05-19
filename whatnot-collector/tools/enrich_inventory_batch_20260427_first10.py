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
REPORT_PATH = EXPORTS / "enrichment_batch_2026-04-27_first10_report.json"
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
        product_id=203,
        barcode="6290171073840",
        brand="Afnan",
        name="Afnan Mystique Bouquet Eau de Parfum Spray 80ml (2.7 oz) Women's Perfume",
        gender="Women",
        size_oz=2.7,
        size_ml=80,
        volume_oz=2.7,
        volume_ml=80,
        product_form="Eau De Parfum",
        manufacturer="Afnan Perfumes",
        description_intro="A luminous women's eau de parfum with juicy peach-citrus brightness, airy florals through the heart, and a clean musky-ambroxan finish.",
        top_notes="White Peach, Mandarin Orange, Bergamot, Litchi",
        mid_notes="Orange Blossom, Vetiver, Mahonia, Peony",
        base_notes="Ambroxan, Musk, Vanilla, Oak Moss",
        scent="Fruity floral musk",
        feature="eau de parfum spray; women; 80ml / 2.7 oz",
        keywords="Afnan, Mystique Bouquet, Eau De Parfum, Women, 80ml, 2.7 oz, White Peach, Orange Blossom, Ambroxan, Musk",
        highlights=[
            "Eau De Parfum spray concentration.",
            "Women fragrance from Afnan's Mystique Bouquet collection.",
            "80 mL / 2.7 oz bottle size.",
            "Peach-citrus opening with a soft musky floral drydown.",
        ],
        similar_to="Valaya Eau de Parfum by Parfums de Marly",
        source_official_url="https://us.afnan.com/products/mystique-bouquet",
        source_jomashop_url="https://www.jomashop.com/afnan-unisex-mystique-bouquet-edp-spray-2-7-oz-fragrances-6290171073840.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Afnan/Mystique-Bouquet-92434.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Afnan_Perfumes/mystique-bouquet",
        image_sources=[
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/MystiqueBouquetfront.png?v=1775219353",
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/MystiqueBouquetside.png?v=1775219353",
            "https://fimgs.net/mdimg/perfume-thumbs/dark-375x500.92434.avif",
        ],
        package_weight_oz=20.21,
    ),
    ProductSeed(
        product_id=38,
        barcode="6290171075073",
        brand="Afnan",
        name="Afnan Supremacy Collector's Edition Eau de Parfum Spray 100ml (3.4 oz) Men's Perfume",
        gender="Men",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Afnan Perfumes",
        description_intro="A bold men's eau de parfum with a pineapple-bright fruity opening, an amber-wood heart, and a refined mossy musky finish.",
        top_notes="Pineapple, Bergamot, Apple, White Floral",
        mid_notes="Orange Blossom, Birch, Amber",
        base_notes="Oak Moss, Musk, Ambergris",
        scent="Fruity chypre, amber, woody",
        feature="eau de parfum spray; men; 100ml / 3.4 oz",
        keywords="Afnan, Supremacy Collector's Edition, Eau De Parfum, Men, 100ml, 3.4 oz, Pineapple, Birch, Oak Moss, Ambergris",
        highlights=[
            "Eau De Parfum spray concentration.",
            "Men fragrance from Afnan's Supremacy collection.",
            "100 mL / 3.4 oz bottle size.",
            "Bright pineapple opening with smoky amber-moss depth.",
        ],
        similar_to="Absolu Aventus by Creed",
        source_official_url="https://us.afnan.com/products/supremacy-collectors-edition",
        source_jomashop_url=None,
        source_fragrantica_url="https://www.fragrantica.com/perfume/Afnan/Supremacy-Collector-s-Edition-Pour-Homme-98689.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Afnan_Perfumes/supremacy-collector-s-edition",
        image_sources=[
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/SupremacyCollectionsEditionFront_Gray.png?v=1775219166",
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/SupremacyCollectionsEditionSide_Gray_0708991b-9d74-4e52-8f94-ac83588e621a.png?v=1775219167",
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/Untitled_design_66.png?v=1775219167",
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/STILL_Afnan_Collectors_04_SQUARE_01.png?v=1775219167",
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/STILL_Afnan_Collectors_04_SQUARE_02.png?v=1775219167",
        ],
        package_weight_oz=19.47,
    ),
    ProductSeed(
        product_id=167,
        barcode="6290171076001",
        brand="Afnan",
        name="Afnan Turathi Electric Eau de Parfum Spray 90ml (3.0 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.0,
        size_ml=90,
        volume_oz=3.0,
        volume_ml=90,
        product_form="Eau De Parfum",
        manufacturer="Afnan Perfumes",
        description_intro="A bright unisex eau de parfum with sparkling citrus-fruit energy, a soft floral-woody heart, and a smooth musky amber-vanilla base.",
        top_notes="Pear, Pink Grapefruit, Mandarin Orange, Bergamot",
        mid_notes="Orange Blossom, Apple, Cedarwood",
        base_notes="Musk, Amber, Ambrofix, Vanilla",
        scent="Citrus fruity musky",
        feature="eau de parfum spray; unisex; 90ml / 3.0 oz",
        keywords="Afnan, Turathi Electric, Eau De Parfum, Unisex, 90ml, 3.0 oz, Pear, Pink Grapefruit, Cedarwood, Vanilla",
        highlights=[
            "Eau De Parfum spray concentration.",
            "Unisex fragrance from Afnan's Turathi collection.",
            "90 mL / 3.0 oz bottle size.",
            "Sparkling grapefruit and pear with a smooth musky vanilla finish.",
        ],
        similar_to=None,
        source_official_url="https://us.afnan.com/products/turathi-electric",
        source_jomashop_url="https://www.jomashop.com/afnan-unisex-turathi-electric-edp-spray-3-0-oz-fragrances-6290171076001.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Afnan/Turathi-Electric-108244.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Afnan_Perfumes/turathi-electric",
        image_sources=[
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/TurathiElectric.png?v=1775219049",
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/Turathi_Electric-1.png?v=1775219049",
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/Turathi_Electric-2.png?v=1775219049",
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/Turathi_Electric_2048x2048_1.png?v=1775219050",
            "https://cdn.shopify.com/s/files/1/0714/3129/1097/files/Turathi_Electric_2048x2048_2.png?v=1775219050",
        ],
        package_weight_oz=21.8,
    ),
    ProductSeed(
        product_id=218,
        barcode="6291108732489",
        brand="Lattafa",
        name="Lattafa Ajwad Eau de Parfum Spray 60ml (2.03 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=2.03,
        size_ml=60,
        volume_oz=2.03,
        volume_ml=60,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes",
        description_intro="A sweet fruity oriental eau de parfum with a soft floral heart and a creamy amber-vanilla cedar drydown.",
        top_notes="Fruity Notes",
        mid_notes="Jasmine, Rose",
        base_notes="Amber, Vanilla, Musk, Cedarwood",
        scent="Sweet fruity amber",
        feature="eau de parfum spray; unisex; 60ml / 2.03 oz",
        keywords="Lattafa, Ajwad, Eau De Parfum, Unisex, 60ml, 2.03 oz, Fruity Notes, Jasmine, Amber, Vanilla",
        highlights=[
            "Eau De Parfum spray concentration.",
            "Unisex fragrance from Lattafa's Ajwad line.",
            "60 mL / 2.03 oz bottle size.",
            "Fruity floral opening with creamy amber-vanilla depth.",
        ],
        similar_to=None,
        source_official_url="https://lattafa.com/product/ajwad/",
        source_jomashop_url="https://www.jomashop.com/lattafa-unisex-ajwad-edp-spray-2-03-oz-fragrances-6291108732489.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Lattafa-Perfumes/Ajwad-75099.html",
        source_parfumo_url="https://www.parfumo.com/Parfums/Lattafa/ajwad",
        image_sources=[
            "https://lattafa.com/wp-content/uploads/2024/05/1-47.jpg",
            "https://lattafa.com/wp-content/uploads/2024/05/2-47.jpg",
            "https://lattafa.com/wp-content/uploads/2024/05/3-47.jpg",
        ],
        ingredients="Parfum (Fragrance), Aqua (Water), Limonene, Ethylhexyl Methoxycinnamate, Diethylamino, Hydroxybenzoyl Hexylbenzoate, Citral, Cinnamal, Linlool, Bht",
        official_discrepancy_note="Parfumo classifies Ajwad as women while official and Fragrantica support a broader unisex/everyone positioning.",
    ),
    ProductSeed(
        product_id=207,
        barcode="6290360597133",
        brand="Lattafa",
        name="Lattafa Ajwad Pink To Pink Eau de Parfum Spray 60ml (2.0 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=2.0,
        size_ml=60,
        volume_oz=2.0,
        volume_ml=60,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes",
        description_intro="A vibrant unisex eau de parfum with a juicy tropical-citrus opening, a soft floral heart, and a warm leathery musky base.",
        top_notes="Pink Grapefruit, Pink Pepper, Raspberry, Guava",
        mid_notes="Rose, Peony, Magnolia",
        base_notes="Musk, Leather, Vanilla, Ambergris, Moss",
        scent="Fruity floral leather",
        feature="eau de parfum spray; unisex; 60ml / 2.0 oz",
        keywords="Lattafa, Ajwad Pink To Pink, Eau De Parfum, Unisex, 60ml, 2.0 oz, Pink Grapefruit, Guava, Magnolia, Leather",
        highlights=[
            "Eau De Parfum spray concentration.",
            "Unisex fragrance from Lattafa's Ajwad line.",
            "60 mL / 2.0 oz bottle size.",
            "Tropical guava-citrus opening with a smooth leathery drydown.",
        ],
        similar_to=None,
        source_official_url="https://lattafa.com/product/ajwad-pink-to-pink/",
        source_jomashop_url=None,
        source_fragrantica_url="https://www.fragrantica.com/perfume/Lattafa-Perfumes/Ajwad-Pink-to-Pink-89766.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Lattafa/ajwad-pink-to-pink",
        image_sources=[
            "https://www.lattafa-usa.com/cdn/shop/files/Ajwad-Pink-to-Pink-1_f07e8195-9952-48c7-8445-1779e409295b.png?v=1747415196",
            "https://www.lattafa-usa.com/cdn/shop/files/Ajwad-Pink-to-Pink-2_49bf14b4-e60d-48ae-99ba-451736dab7de.png?v=1747415196",
        ],
        official_discrepancy_note="Official product copy mentions lychee in prose, but the official note pyramid uses raspberry instead.",
    ),
    ProductSeed(
        product_id=253,
        barcode="6291106813029",
        brand="Al Haramain",
        name="Al Haramain Amber Oud Ruby Edition Eau de Parfum Spray 60ml (2.0 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=2.0,
        size_ml=60,
        volume_oz=2.0,
        volume_ml=60,
        product_form="Eau De Parfum",
        manufacturer="Al Haramain Perfumes",
        description_intro="A rich unisex eau de parfum with a saffron-almond opening, a woody jasmine heart, and a warm musky amber drydown.",
        top_notes="Saffron, Bitter Almond",
        mid_notes="Cedarwood, Egyptian Jasmine",
        base_notes="Musk, Amber, Woody Notes",
        scent="Sweet woody amber",
        feature="eau de parfum spray; unisex; 60ml / 2.0 oz",
        keywords="Al Haramain, Amber Oud Ruby Edition, Eau De Parfum, Unisex, 60ml, 2.0 oz, Saffron, Bitter Almond, Cedarwood, Jasmine",
        highlights=[
            "Eau De Parfum spray concentration.",
            "Unisex fragrance from Al Haramain's Amber Oud line.",
            "60 mL / 2.0 oz bottle size.",
            "Saffron and almond opening with a warm woody musky base.",
        ],
        similar_to="Baccarat Rouge 540 Extrait de Parfum by Maison Francis Kurkdjian",
        source_official_url="https://shop.alharamainperfumes.com/oman/haramain-amber-oud-ruby-edition-60ml.html",
        source_jomashop_url=None,
        source_fragrantica_url="https://www.fragrantica.com/perfume/Al-Haramain-Perfumes/Amber-Oud-Ruby-Edition-73208.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Al_Haramain/amber-oud-ruby-edition",
        image_sources=[
            "https://shop.alharamainperfumes.com/media/catalog/product/cache/490c4e3bbae272be3ce2b30a9945698e/1/1/1148pn.jpg",
            "https://shop.alharamainperfumes.com/media/catalog/product/cache/490c4e3bbae272be3ce2b30a9945698e/1/1/1148bn.jpg",
            "https://shop.alharamainperfumes.com/media/catalog/product/cache/490c4e3bbae272be3ce2b30a9945698e/a/m/amber_oud_ruby.jpg",
        ],
        official_discrepancy_note="Fragrantica and Parfumo agree on the top and heart but differ slightly on the base; the saved base keeps only the overlapping amber-woody-musky lane.",
    ),
    ProductSeed(
        product_id=254,
        barcode="6291106814873",
        brand="Al Haramain",
        name="Al Haramain Amber Oud Aqua Dubai Extrait de Parfum Spray 100ml (3.38 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.38,
        size_ml=100,
        volume_oz=3.38,
        volume_ml=100,
        product_form="Extrait De Parfum",
        manufacturer="Al Haramain Perfumes",
        description_intro="A fresh unisex extrait de parfum with crisp citrus-green brightness, a fruity aquatic heart, and a clean musky vanilla base.",
        top_notes="Green Notes, Bergamot, Mandarin Orange",
        mid_notes="Blackcurrant, Amber, Melon, Pineapple",
        base_notes="Musk, Petitgrain, Galbanum, Vanilla",
        scent="Citrus aquatic fresh",
        feature="extrait de parfum spray; unisex; 100ml / 3.38 oz",
        keywords="Al Haramain, Amber Oud Aqua Dubai, Extrait De Parfum, Unisex, 100ml, 3.38 oz, Bergamot, Mandarin Orange, Melon, Vanilla",
        highlights=[
            "Extrait De Parfum spray concentration.",
            "Unisex fragrance from Al Haramain's Amber Oud line.",
            "100 mL / 3.38 oz bottle size.",
            "Bright citrus-green opening with a clean musky vanilla base.",
        ],
        similar_to="Imagination by Louis Vuitton",
        source_official_url="https://shop.alharamainperfumes.com/default/haramain-amber-oud-aqua-dubai-extrait-de-parfum.html",
        source_jomashop_url=None,
        source_fragrantica_url="https://www.fragrantica.com/perfume/Al-Haramain-Perfumes/Amber-Oud-Aqua-Dubai-96482.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Al_Haramain/haramain-amber-oud-aqua-dubai",
        image_sources=[
            "https://shop.alharamainperfumes.com/media/catalog/product/cache/490c4e3bbae272be3ce2b30a9945698e/a/h/ahp1483_solo.jpg",
            "https://shop.alharamainperfumes.com/media/catalog/product/cache/490c4e3bbae272be3ce2b30a9945698e/a/h/ahp1483_notes_1.jpg",
            "https://shop.alharamainperfumes.com/media/catalog/product/cache/490c4e3bbae272be3ce2b30a9945698e/a/q/aqua_dubai-02.jpg",
            "https://shop.alharamainperfumes.com/media/catalog/product/cache/490c4e3bbae272be3ce2b30a9945698e/a/q/aqua_dubai-01.jpg",
            "https://shop.alharamainperfumes.com/media/catalog/product/cache/490c4e3bbae272be3ce2b30a9945698e/1/4/1483_combo.jpg",
        ],
    ),
    ProductSeed(
        product_id=168,
        barcode="6291100131716",
        brand="Al Haramain",
        name="Al Haramain Amber Oud Gold Edition Eau de Parfum Spray 60ml (2.0 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=2.0,
        size_ml=60,
        volume_oz=2.0,
        volume_ml=60,
        product_form="Eau De Parfum",
        manufacturer="Al Haramain Perfumes",
        description_intro="A radiant unisex eau de parfum with bergamot-green lift, a juicy fruity amber heart, and a smooth musky vanilla-wood finish.",
        top_notes="Bergamot, Green Notes",
        mid_notes="Melon, Gourmand Notes, Amber, Pineapple",
        base_notes="Musk, Vanilla, Woody Notes",
        scent="Fruity sweet woody",
        feature="eau de parfum spray; unisex; 60ml / 2.0 oz",
        keywords="Al Haramain, Amber Oud Gold Edition, Eau De Parfum, Unisex, 60ml, 2.0 oz, Bergamot, Melon, Pineapple, Vanilla",
        highlights=[
            "Eau De Parfum spray concentration.",
            "Unisex fragrance from Al Haramain's Amber Oud line.",
            "60 mL / 2.0 oz bottle size.",
            "Juicy fruity heart with a smooth musky vanilla finish.",
        ],
        similar_to="Erba Pura by Xerjoff",
        source_official_url=None,
        source_jomashop_url="https://www.jomashop.com/al-haramain-unisex-amber-oud-gold-editon-edp-spray-2-oz-fragrances-6291100131716.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Al-Haramain-Perfumes/Amber-Oud-Gold-Edition-51816.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Al_Haramain/haramain-amber-oud-gold-edition",
        image_sources=[
            "https://cdn2.jomashop.com/media/catalog/product/cache/b3e31d40bbb1abcc90b26106659d5d3f/a/l/al-haramain-unisex-amber-oud-gold-edition-edp-spray-20-oz-fragrances-6291100131716.jpg",
            "https://fimgs.net/mdimg/perfume/375x500.51816.jpg",
        ],
        official_discrepancy_note="The working Al Haramain official page found during research was for 100ml, so the 60ml barcode uses Jomashop plus Fragrantica and Parfumo as the cleanest matching sources.",
    ),
    ProductSeed(
        product_id=263,
        barcode="6291107458571",
        brand="Lattafa",
        name="Lattafa Ameer Al Oudh Intense Oud Eau de Parfum Spray 100ml (3.4 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes",
        description_intro="A smoky-sweet unisex eau de parfum with a saffron-spice opening, a resinous woody heart, and a rich oud-vanilla leather base.",
        top_notes="Saffron, Nutmeg",
        mid_notes="Geranium, Woody Notes, Labdanum",
        base_notes="Oud, Vanilla, Leather",
        scent="Smoky sweet woody",
        feature="eau de parfum spray; unisex; 100ml / 3.4 oz",
        keywords="Lattafa, Ameer Al Oudh Intense Oud, Eau De Parfum, Unisex, 100ml, 3.4 oz, Saffron, Nutmeg, Oud, Vanilla",
        highlights=[
            "Eau De Parfum spray concentration.",
            "Unisex fragrance from Lattafa's Ameer Al Oudh line.",
            "100 mL / 3.4 oz bottle size.",
            "Spicy opening with smoky woods and a warm vanilla-oud finish.",
        ],
        similar_to="By the Fireplace by Maison Martin Margiela",
        source_official_url="https://lattafa.com/product/ameer-al-oudh-intense/",
        source_jomashop_url="https://www.jomashop.com/lattafa-unisex-ameer-al-oudh-intense-oud-edp-spray-3-4-oz-fragrances-6291107458571.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Lattafa-Perfumes/Ameer-Al-Oudh-Intense-Oud-64947.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Lattafa/ameer-al-oudh-intense-oud",
        image_sources=[
            "https://www.lattafa-usa.com/cdn/shop/files/1_f19ccc77-b348-4897-95f8-1a196f56d148.png?v=1747245230",
            "https://cdn2.jomashop.com/media/catalog/product/cache/b3e31d40bbb1abcc90b26106659d5d3f/l/a/lattafa-unisex-ameer-al-oudh-intense-oud-edp-spray-34-oz-fragrances-6291107458571.jpg",
        ],
        official_discrepancy_note="Official old Lattafa product copy and Fragrantica differ; the saved note pyramid follows the matching official note list reposted consistently in Fragrantica and community references.",
    ),
    ProductSeed(
        product_id=181,
        barcode="6291107456355",
        brand="Asdaaf",
        name="Asdaaf Ameerat Al Arab Eau de Parfum Spray 100ml (3.4 oz) Women's Perfume",
        gender="Women",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Asdaaf",
        description_intro="An elegant women's eau de parfum with a fresh aromatic opening, a soft floral heart, and a warm jasmine-saffron finish.",
        top_notes="Basil, Cardamom, Mint",
        mid_notes="Honeysuckle, Lavender",
        base_notes="Jasmine, Pepper, Saffron, Oud",
        scent="Floral fruity oriental",
        feature="eau de parfum spray; women; 100ml / 3.4 oz",
        keywords="Asdaaf, Ameerat Al Arab, Eau De Parfum, Women, 100ml, 3.4 oz, Basil, Cardamom, Honeysuckle, Jasmine",
        highlights=[
            "Eau De Parfum spray concentration.",
            "Women fragrance from Asdaaf's Ameerat Al Arab line.",
            "100 mL / 3.4 oz bottle size.",
            "Fresh aromatic opening with a warm floral oriental base.",
        ],
        similar_to="My Way Eau de Parfum by Giorgio Armani",
        source_official_url="https://lattafa.com/product/ameerat-al-arab/",
        source_jomashop_url=None,
        source_fragrantica_url="https://www.fragrantica.com/perfume/Asdaaf/Ameerat-Al-Arab-81376.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Asdaaf/ameerat-al-arab",
        image_sources=[
            "https://lattafa.com/wp-content/uploads/2024/05/1-40.jpg",
            "https://lattafa.com/wp-content/uploads/2024/05/2-40.jpg",
            "https://lattafa.com/wp-content/uploads/2024/05/3-40.jpg",
            "https://fimgs.net/mdimg/perfume-thumbs/dark-375x500.81376.avif",
        ],
        ingredients="Alcohol Denat., 80% Vol., Parfum (Fragrance), Aqua (Water), Ethylhexyl Methoxycinnamate, Butyl Methoxydibenzoylmethane, Ethylhexyl Salicylate, CI 15985, CI 60730, and CI 17200",
        official_discrepancy_note="Official Lattafa and Fragrantica agree on the fresher citrus/musk profile, while Parfumo shows a spicier pyramid. Saved data leans on the official/Fragrantica lane and preserves the warmer base character from Parfumo.",
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

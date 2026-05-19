# Inventory to TikTok Mapping

This file defines the canonical source-of-truth mapping for TikTok Shop product
uploads. Inventory fields are the only source of truth. TikTok-specific
normalization happens at send time only.

## Core rules

- Inventory is the only product source of truth.
- Do not use legacy marketplace rows as an intermediate catalog.
- `Seller SKU` = inventory `barcode`
- `EAN` = inventory `barcode`
- `Package weight` = inventory `tiktok_package_weight_oz`, fallback `size_oz`
- `SDS` = inventory `tiktok_sds_file_path`
- TikTok category comes from inventory gender mapping:
  - `Men` -> `855696` -> `Beauty & Personal Care - Fragrance - Men's Fragrance`
  - `Women` -> `855952` -> `Beauty & Personal Care - Fragrance - Women's Fragrance`
  - everything else -> `855824` -> `Beauty & Personal Care - Fragrance - Unisex Fragrance`

## Product fields

| TikTok field | Inventory field | Fallback |
| --- | --- | --- |
| Product name | `tiktok_title` | `name` |
| Description | `tiktok_description` | `description` |
| Product highlights | `tiktok_highlights` | `product_highlights` |
| Search keywords | `tiktok_search_keywords` | `search_keywords` |
| Brand | `tiktok_brand` | `brand` |
| Seller SKU | `barcode` | `sku` |
| EAN | `barcode` | `tiktok_ean` if manually overridden |
| Retail price | `tiktok_retail_price` | `retail_price` |
| Quantity | `tiktok_quantity` | `on_hand_qty` |
| Package weight | `tiktok_package_weight_oz` | `size_oz` |
| SDS PDF | `tiktok_sds_file_path` | none |

## Images

Use inventory image fields only:

1. `image_gallery_urls`
2. `tiktok_image_urls`
3. `media_url`
4. `image_url`

Rules:

- Upload up to 9 images.
- Keep existing live TikTok `uri` values when editing drafts/live products.
- Do not reduce to a single image when inventory has a gallery.

## Key attributes

| TikTok field | Inventory field |
| --- | --- |
| Pack Type | `tiktok_pack_type` |
| Scent | `tiktok_scent` |
| Region Of Origin | `tiktok_region_of_origin` |

## Optional attributes

| TikTok field | Inventory field |
| --- | --- |
| Product Form | `tiktok_product_form` |
| Edition | `tiktok_edition` |
| Contains Alcohol Or Aerosol | `tiktok_contains_alcohol_or_aerosol` |
| Manufacturer | `tiktok_manufacturer` |
| Shelf Life | `tiktok_shelf_life` |
| (Inactive) Ingredients | `tiktok_inactive_ingredients` |
| Age Group | `tiktok_age_group` |
| Item Name | `tiktok_item_name` |
| Feature | `tiktok_feature` |
| Fragrance Concentration | `tiktok_fragrance_concentration` |
| Material Type Free | `tiktok_material_type_free` |
| Ingredients | `tiktok_ingredients` |
| Container Type | `tiktok_container_type` |
| Allergen Information | `tiktok_allergen_information` |
| Ingredient Feature | `tiktok_ingredient_feature` |
| Volume | `tiktok_volume` |

## Compliance

| TikTok field | Inventory field |
| --- | --- |
| CA Prop 65: Repro. Chems | `tiktok_ca_prop_65_repro_chems` |
| CA Prop 65: Carcinogens | `tiktok_ca_prop_65_carcinogens` |
| Flammable Liquid | `tiktok_flammable_liquid` |
| Aerosols | `tiktok_aerosols` |
| Dangerous Goods Or Hazardous Materials | `tiktok_dangerous_goods_or_hazardous_materials` |
| Environmental Feature | `tiktok_environmental_feature` |

## Send-time normalization only

- Trim `search keywords` to TikTok's 250-character limit.
- Resolve category attributes against the live TikTok category attribute schema.
- Resolve `brand_id` from the TikTok brand search endpoint only when TikTok
  returns a valid brand for the category/shop.
- Convert package weight from ounces to the unit TikTok expects in payload.
- Include exact SDS certification payload only when the TikTok API format is
  verified and the inventory SDS path exists.

## Things to avoid

- Do not mix `GTIN` and `EAN` rules across different upload scripts.
- Do not append highlights/attributes/keywords into the description body.
- Do not invent package dimensions.
- Do not publish/rebuild from stale draft data when inventory has cleaner data.
- Do not assume TikTok lifecycle API behaves like Seller Center admin actions.

# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    """Re-declares the fragrance merchandising fields that the previous
    `ynf_storefront` uninstall dropped from product_template.

    The post-init hook (see hooks.py) refills these from the CSV snapshot
    saved right before the uninstall.
    """
    _inherit = "product.template"

    x_ynf_inspired_by = fields.Char(
        string="Inspired by",
        help="Community dupe reference shown as a chip, e.g. 'Creed Aventus'.",
    )
    x_ynf_family = fields.Char(
        string="Scent family",
        help="e.g. 'Amber Gourmand', 'Aquatic Aromatic' — used for mood/family filtering.",
    )
    x_ynf_image_url = fields.Char(
        string="Image URL",
        help="External product photo URL, used as a fallback when no DB image is set.",
    )

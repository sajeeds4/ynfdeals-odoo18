# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    """Fragrance-specific merchandising fields used by the YNF theme.

    These match the prefixed convention already used in the YNF database
    (x_ynf_*). If the fields already exist (created via Studio or a prior
    migration) Odoo reuses them — declaring them here just guarantees they
    exist for a clean install and makes them available in QWeb (`product.x_ynf_*`).
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
    x_ynf_note_top = fields.Char(string="Top notes")
    x_ynf_note_mid = fields.Char(string="Heart notes")
    x_ynf_note_base = fields.Char(string="Base notes")

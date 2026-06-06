import logging
from collections import defaultdict

from odoo import http
from odoo.http import request
from odoo.addons.sale.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager

_logger = logging.getLogger(__name__)


class YNFCustomerPortal(CustomerPortal):
    """Broaden the portal's "My Orders" so a logged-in customer also sees
    TikTok Live / TikTok Shop orders that were attached to a shipping
    recipient partner (e.g. "Abdullah Abbas") instead of their own portal
    user partner. Match additional orders by TikTok buyer username.
    """

    def _ynf_handle_variants(self, partner):
        handles = set()
        for raw in (partner.x_ynf_tiktok_live_username, partner.name, partner.email):
            if not raw:
                continue
            h = raw.strip()
            if "@" in h and raw == partner.email:
                h = h.split("@", 1)[0]
            if not h:
                continue
            handles.update({h, h.lower(), h.title(), h.capitalize(), h.upper()})
        return list(handles)

    def _prepare_orders_domain(self, partner):
        base = super()._prepare_orders_domain(partner)
        handles = self._ynf_handle_variants(partner)
        if not handles:
            return base
        return [
            "|",
                "&", *base,
                "&", ("x_ynf_tiktok_buyer_username", "in", handles),
                     ("state", "in", ["sale", "done"]),
        ]

    def _prepare_sale_portal_rendering_values(
        self, page=1, date_begin=None, date_end=None, sortby=None,
        quotation_page=False, **kwargs
    ):
        """Same logic as parent, but sudo the sale.order search so portal
        users see orders matching our broader domain even when those orders
        are attached to a different partner (TikTok shipping recipient)."""
        if quotation_page:
            return super()._prepare_sale_portal_rendering_values(
                page=page, date_begin=date_begin, date_end=date_end,
                sortby=sortby, quotation_page=quotation_page, **kwargs,
            )

        SaleOrder = request.env['sale.order'].sudo()
        partner = request.env.user.partner_id

        if not sortby:
            sortby = 'date'
        values = self._prepare_portal_layout_values()

        domain = self._prepare_orders_domain(partner)
        searchbar_sortings = self._get_sale_searchbar_sortings()
        sort_order = searchbar_sortings[sortby]['order']

        if date_begin and date_end:
            domain += [('create_date', '>', date_begin),
                       ('create_date', '<=', date_end)]

        url_args = {'date_begin': date_begin, 'date_end': date_end}
        if len(searchbar_sortings) > 1:
            url_args['sortby'] = sortby

        step = 30
        pager_values = portal_pager(
            url="/my/orders",
            total=SaleOrder.search_count(domain),
            page=page,
            step=step,
            url_args=url_args,
        )
        orders = SaleOrder.search(
            domain, order=sort_order,
            limit=step,
            offset=pager_values['offset'],
        )

        values.update({
            'date': date_begin,
            'quotations': SaleOrder.browse(),
            'orders': orders,
            'page_name': 'order',
            'pager': pager_values,
            'default_url': "/my/orders",
        })
        if len(searchbar_sortings) > 1:
            values.update({
                'sortby': sortby,
                'searchbar_sortings': searchbar_sortings,
            })
        _logger.info("[YNF] portal /my/orders for %s: %d orders (page %d)",
                     partner.name, len(orders), page)
        return values


class YNFDisputeController(http.Controller):
    """Customer Help / Dispute flow:
       /my/help           — pick a Go Live Session
       /my/help/<n>       — pick a product in that session
       POST /my/help/submit — record the dispute on the order chatter,
                              auto-notifies internal support.
    """

    def _user_orders_for_partner(self):
        partner = request.env.user.partner_id
        if not partner:
            return request.env["sale.order"]
        handles = set()
        for raw in (partner.x_ynf_tiktok_live_username, partner.name, partner.email):
            if not raw:
                continue
            h = (raw or "").strip()
            if "@" in h and raw == partner.email:
                h = h.split("@", 1)[0]
            for v in (h, h.lower(), h.title(), h.capitalize(), h.upper()):
                if v:
                    handles.add(v)
        domain = [
            "|",
            ("partner_id", "child_of", [partner.commercial_partner_id.id]),
            "&", ("x_ynf_tiktok_buyer_username", "in", list(handles)),
                 ("state", "in", ["sale", "done"]),
        ]
        return request.env["sale.order"].sudo().search(
            domain, order="x_ynf_gls_session_no desc, date_order desc")

    @http.route(["/my/help", "/my/help/session"], type="http",
                auth="user", website=True)
    def help_pick_session(self, **kw):
        orders = self._user_orders_for_partner()
        sessions = defaultdict(lambda: {"orders": 0, "lots": 0})
        for o in orders:
            sn = o.x_ynf_gls_session_no or 0
            sessions[sn]["orders"] += 1
            sessions[sn]["lots"] += (o.x_ynf_tiktok_product_count or 1)
            sessions[sn]["date"] = o.date_order
        rows = [
            {"session_no": sn, "orders": v["orders"], "lots": v["lots"],
             "date": v.get("date")}
            for sn, v in sorted(sessions.items(), key=lambda kv: kv[0], reverse=True)
            if sn
        ]
        return request.render("ynf_storefront.portal_help_pick_session",
                              {"sessions": rows, "page_name": "help"})

    @http.route("/my/help/session/<int:session_no>", type="http",
                auth="user", website=True)
    def help_pick_product(self, session_no, **kw):
        orders = self._user_orders_for_partner().filtered(
            lambda o: o.x_ynf_gls_session_no == session_no)
        items = []
        for o in orders:
            for line in o.order_line:
                if not line.product_id:
                    continue
                items.append({
                    "order_id": o.id,
                    "order_name": o.name,
                    "tracking": o.x_ynf_tiktok_tracking_number or "",
                    "lot": o.x_ynf_tiktok_lot_number or o.x_ynf_gls_lot_numbers or "",
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "qty": int(line.product_uom_qty),
                    "line_id": line.id,
                })
        return request.render("ynf_storefront.portal_help_pick_product",
                              {"items": items, "session_no": session_no,
                               "page_name": "help"})

    @http.route("/my/help/submit", type="http", auth="user", website=True,
                methods=["POST"], csrf=True)
    def help_submit(self, order_id=None, line_id=None, session_no=None,
                    issue_type=None, description=None, **kw):
        if not order_id or not description or not issue_type:
            return request.redirect("/my/help?error=missing")
        SO = request.env["sale.order"].sudo()
        order = SO.browse(int(order_id))
        if not order.exists():
            return request.redirect("/my/help?error=not_found")
        line = (request.env["sale.order.line"].sudo().browse(int(line_id))
                if line_id else None)
        partner = request.env.user.partner_id
        product_label = (line.product_id.display_name
                         if line and line.product_id else "—")
        body = (
            f"<div class='ynf-dispute-card'>"
            f"<h4 style='color:#dc2626;margin:0 0 8px 0;'>🚩 Customer dispute</h4>"
            f"<p><b>From:</b> {partner.name}"
            f" ({partner.email or 'no email'})</p>"
            f"<p><b>Session:</b> #{session_no or order.x_ynf_gls_session_no or '—'}"
            f"<br/><b>Order:</b> {order.name}"
            f"<br/><b>Product:</b> {product_label}"
            f"<br/><b>Type:</b> {issue_type}</p>"
            f"<div style='border-left:3px solid #dc2626;padding:6px 12px;"
            f"background:#fee2e2;'>"
            f"<b>Message:</b><br/>"
            f"{description.replace(chr(10), '<br/>')}</div></div>"
        )
        order.message_post(
            body=body,
            subject=f"[DISPUTE] {issue_type} — {product_label}",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            author_id=partner.id,
        )
        return request.render(
            "ynf_storefront.portal_help_thanks",
            {"order": order, "page_name": "help"})

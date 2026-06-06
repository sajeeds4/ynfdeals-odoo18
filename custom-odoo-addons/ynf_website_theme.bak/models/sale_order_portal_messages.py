"""Auto-route portal customer messages on sale.order to internal Discuss.

When a portal/public user posts a message on a sale.order chatter:
  * Subscribe the order's salesperson (if any) and all members of the
    configured "Customer Service" group to the record.
  * Followers automatically receive an Inbox notification in Discuss with a
    link that opens the order form (so internal users see the message AND
    the full order context on the right side).

The "Customer Service" group is read from a system parameter:
    ynf.customer_service_group_xmlid   default: sales_team.group_sale_salesman
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class SaleOrderYNFPortalMessages(models.Model):
    _inherit = "sale.order"

    def _ynf_internal_recipients(self):
        Param = self.env["ir.config_parameter"].sudo()
        group_xmlid = Param.get_param(
            "ynf.customer_service_group_xmlid",
            "sales_team.group_sale_salesman",
        )
        partners = self.env["res.partner"]
        # Salesperson
        if self.user_id and self.user_id.partner_id:
            partners |= self.user_id.partner_id
        # Sales team members
        if self.team_id:
            for u in self.team_id.member_ids:
                if u.partner_id:
                    partners |= u.partner_id
        # Configured group members
        try:
            group = self.env.ref(group_xmlid, raise_if_not_found=False)
        except Exception:
            group = None
        if group:
            for u in group.users:
                if u.partner_id and u.share is False:
                    partners |= u.partner_id
        return partners

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        try:
            author = message.author_id
            # Only act when a portal/public partner is the author and the
            # message is a regular comment (not an internal note).
            is_internal_author = bool(
                author
                and author.user_ids
                and any(not u.share for u in author.user_ids)
            )
            mt_comment = self.env.ref("mail.mt_comment", raise_if_not_found=False)
            if (not is_internal_author
                    and message.subtype_id == mt_comment
                    and message.message_type == "comment"):
                recipients = self._ynf_internal_recipients()
                if recipients:
                    self.message_subscribe(partner_ids=recipients.ids)
                    # Ensure every recipient gets an Inbox notification
                    Notification = self.env["mail.notification"].sudo()
                    existing = set(message.notification_ids.mapped("res_partner_id").ids)
                    to_notify = [p for p in recipients if p.id not in existing]
                    if to_notify:
                        Notification.create([
                            {
                                "mail_message_id": message.id,
                                "res_partner_id": p.id,
                                "notification_type": "inbox",
                                "notification_status": "sent",
                                "is_read": False,
                            }
                            for p in to_notify
                        ])
                        # Push to bus so Discuss inbox updates live
                        for p in to_notify:
                            self.env["bus.bus"]._sendone(
                                p, "mail.message/inbox",
                                {"id": message.id, "thread_model": self._name,
                                 "thread_id": self.id},
                            )
        except Exception:
            _logger.exception("YNF portal-message routing failed for SO %s", self.ids)
        return message

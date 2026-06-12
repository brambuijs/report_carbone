import logging

from odoo import _, api, exceptions, fields, models

from ..base.ir_actions_report import _tz_get

_logger = logging.getLogger(__name__)


class CarbonReportPrintByAction(models.TransientModel):
    _name = "carbone.print_by_action"
    _description = "Print by action"

    @api.model
    def _get_model(self):
        rep_obj = self.env["ir.actions.report"]
        report = rep_obj.browse(self.env.context["active_ids"])
        return report[0].model

    @api.model
    def _get_id_record(self):
        id = self.env.context.get("record_id")
        return id

    @api.model
    def _get_currency_id(self):
        id = self.env.context.get("currency_id")
        return id

    name = fields.Text(string="Object Model", default=_get_model, readonly=True)
    id_object = fields.Integer(string="Object ID", default=_get_id_record)
    lang_id = fields.Many2one(
        "res.lang",
        string="Language",
        default=lambda self: self.env["res.lang"].search([("code", "=", self.env.user.lang)], limit=1),
        help="If this option is enabled, the language in which the report is printed",
    )
    currency_id = fields.Many2one("res.currency", string="Currency", default=_get_currency_id)
    tz = fields.Selection(_tz_get, string="Timezone", default=lambda self: self.env.user.tz or "UTC")

    def to_print(self):
        rep_obj = self.env["ir.actions.report"]
        report = rep_obj.browse(self.env.context["active_id"])[0]
        ctx = dict(self.env.context)
        print_ids = self.env[self.name].browse(self.id_object)
        if not print_ids:
            raise exceptions.UserError(_("No record is retrieve with this id."))
        # report_pdf_no_attachment context key
        # forces the system not to retrieve an attachment saved in the database.
        ctx.update(
            {
                "active_id": print_ids[0],
                "active_ids": print_ids.ids,
                "active_model": report.model,
                "lang": self.lang_id.code,
                "tz": self.tz,
                "currency_id": self.currency_id.id,
                "from_print_by_action": True,
                "report_pdf_no_attachment": True,
            }
        )
        data = {
            "model": report.model,
            "id": print_ids[0],
            "ids": print_ids,
            "report_type": "carbone",
        }
        res = {
            "type": "ir.actions.report",
            "report_name": report.report_name,
            "report_type": report.report_type,
            "datas": data,
            "context": ctx,
            "target": "current",
        }
        return res

from odoo import api, models


class IrModelCarbone(models.Model):
    _inherit = "ir.model"

    @api.depends("name", "model")
    def _compute_display_name(self):
        if not self.env.context.get("carbone_report_display_name"):
            return super()._compute_display_name()
        for rec in self:
            rec.display_name = f"{rec.name} - {rec.model}"

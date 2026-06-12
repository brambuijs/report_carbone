from odoo import _, api, exceptions, fields, models


class CarbonCreateReportWizard(models.TransientModel):
    _name = "carbone.create.report.wizard"
    _description = "Create Carbone report wizard helper"

    report_type_extension = fields.Selection(
        string="Report extension",
        selection=[("docx", ".docx"), ("pptx", ".pptx"), ("xlsx", ".xlsx")],
        help="Leave empty if you already have a existing Carbone template for this report, then set the template ID",
    )

    template_id = fields.Char(
        string="Carbone Template ID", help="Leave empty if you don't have any existing template for this report"
    )

    input_user_model_id = fields.Many2one(
        "ir.model", string="Odoo model name", domain=[("transient", "=", False)], required=True
    )

    action_name = fields.Char(string="Action name", required=True)

    @api.constrains("template_id", "report_type_extension")
    def _check_template_xor_extension(self):
        """Users are not allowed to enter both the extension of their report and a Carbone Template ID.
        This is because if the user enters an extension, it is to create a report from scratch, and we mock a call
        to Carbone to properly set up the studio.
        If the user enters a Carbone Template ID, we will rely exclusively on that, without making a mock call
        to Carbone.
        If the user enters a Carbone Template ID, we will rely exclusively on that, without making
        a mock call."""
        for record in self:
            has_template = bool(record.template_id)
            has_extension = bool(record.report_type_extension)

            if has_template == has_extension:
                raise exceptions.ValidationError(_("You must specify either a template or an extension, but not both."))

    def action_create_carbone_report(self):
        export_suffixe_name = self.input_user_model_id.display_name
        new_carbone_report = self.env["ir.actions.report"].create(
            {
                "name": self.action_name,
                "input_user_model_id": self.input_user_model_id.id,
                "model": self.input_user_model_id.model,
                "template_id": self.template_id,
                "report_type": "carbone",
                "file_extension": self.report_type_extension,
                "m2o_reference_id": self.env[self.input_user_model_id.model].search([], limit=1).id,
            }
        )
        export_model = new_carbone_report.retrieve_global_export_model(
            self.input_user_model_id.model, export_suffixe_name
        )
        new_carbone_report.export_model = export_model
        view_id = self.env.ref("report_carbone.act_report_carbone_view").id
        return {
            "type": "ir.actions.act_window",
            "res_model": "ir.actions.report",
            "view_mode": "form",
            "view_id": view_id,
            "views": [(view_id, "form")],
            "res_id": new_carbone_report.id,
            "target": "current",
            "context": {
                "active_model": "ir.actions.report",
                "active_id": new_carbone_report.id,
                "active_ids": [new_carbone_report.id],
                "default_report_type": "carbone",
            },
        }

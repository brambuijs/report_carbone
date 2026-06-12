from odoo import fields, models


class CarboneResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    carbone_studio_url = fields.Char("Carbone Studio URL", config_parameter="report-engine.carbone_studio_url")
    carbone_js_file_url = fields.Char("Carbone JS file URL", config_parameter="report-engine.carbone_js_file_url")
    is_stage_mode = fields.Boolean(string="Test mode", config_parameter="report-engine.is_stage_mode")
    prod_api_key = fields.Char(string="Prod API Key", config_parameter="report-engine.prod_api_key")
    stage_api_key = fields.Char(string="Test API Key", config_parameter="report-engine.stage_api_key")

    def open_ir_actions_reports(self):
        return self.env["ir.actions.actions"]._for_xml_id("report_carbone.action_carbone_report_template_tree_all")

    def retrieve_carbone_api_key(self, test_mode_key=False):
        """Depending on the ‘test mode’ checkbox or 'test_mode_key' parameter, either the production key or
        the staging key is returned."""
        stage_mode = self.env["ir.config_parameter"].sudo().get_param("report-engine.is_stage_mode")
        if stage_mode or test_mode_key:
            return self.env["ir.config_parameter"].sudo().get_param("report-engine.stage_api_key")
        return self.env["ir.config_parameter"].sudo().get_param("report-engine.prod_api_key")

    def action_download_carbone_documentation(self):
        ir_action_report = self.env["ir.actions.report"]
        return ir_action_report.action_download_carbone_documentation()

    def action_download_carbone_file_sample(self):
        ir_action_report = self.env["ir.actions.report"]
        return ir_action_report.action_download_carbone_file_sample()

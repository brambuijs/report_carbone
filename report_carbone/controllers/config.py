from odoo import http
from odoo.http import request


class CarboneConfigParamController(http.Controller):
    @http.route("/carbone_config/carbone_studio_params", type="json", auth="user")
    def get_carbone_studio_params(self):
        carbone_url = request.env["ir.config_parameter"].sudo().get_param("report-engine.carbone_studio_url")
        carbone_js_url = request.env["ir.config_parameter"].sudo().get_param("report-engine.carbone_js_file_url")
        return {"studio_url": carbone_url, "js_url": carbone_js_url}

    @http.route("/carbone_config/carbone_api_key", type="json", auth="user")
    def get_carbone_api_key(self):
        value = request.env["res.config.settings"].sudo().retrieve_carbone_api_key(test_mode_key=True)
        return {"token": value}

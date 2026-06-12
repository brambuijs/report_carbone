import json
import logging
import mimetypes

import requests
import werkzeug.exceptions
from werkzeug.urls import url_decode

from odoo import _, api, exceptions, http
from odoo.http import content_disposition, request
from odoo.tools import html_escape

from odoo.addons.web.controllers.report import ReportController

_logger = logging.getLogger(__name__)


def _get_headers(extension, content, filename):
    if extension == "zip":
        mime_type = "application/zip"
    else:
        mime_type, _ = mimetypes.guess_type(f"file.{extension}")
        if not mime_type:
            mime_type = "application/octet-stream"  # generic fallback
    header = [
        ("Content-Type", mime_type),
        ("Content-Length", len(content)),
        ("X-Content-Type-Options", "nosniff"),
    ]
    if filename:
        header.append(("Content-Disposition", content_disposition(filename)))
    return header


class CarboneReportController(ReportController):
    @classmethod
    def handle_response(cls, response: requests.Response, raise_exception=True) -> str | dict:
        try:
            response_json = response.json()
        except ValueError:
            response_json = {}
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            response_error_message = response_json.get("message", response.text) if response_json else response.text
            error_message = f"Carbone API Error: {response.status_code}: {response_error_message}"
            _logger.error("Carbone API Error %s: ", response.status_code, exc_info=e)
            if raise_exception:
                raise exceptions.UserError(error_message) from e
            return error_message
        return response_json

    @api.model
    def check_carbone_report(self, carbone_report: "odoo.model.ir_actions_report"):
        if not carbone_report:
            raise exceptions.UserError(_("No report with this name and Carbone type was found."))
        if not carbone_report.name:
            raise exceptions.UserError(_("Please add a name to the report in order to export it."))

    @api.model
    def handle_exception_error(self, e, reportname: str):
        _logger.exception("Error while generating report %s", reportname)
        se = http.serialize_exception(e)
        error = {"code": 200, "message": "Odoo Server Error", "data": se}
        res = request.make_response(html_escape(json.dumps(error)))
        raise werkzeug.exceptions.InternalServerError(response=res) from e

    @http.route(
        [
            "/report/<converter>/<reportname>",
            "/report/<converter>/<reportname>/<docids>",
        ],
        type="http",
        auth="user",
        website=True,
        readonly=True,
    )
    def report_routes(self, reportname: str, docids: str | None = None, converter=None, **data):
        if converter != "carbone":
            return super().report_routes(reportname, docids, converter, **data)
        context = dict(request.env.context)
        context.update({"from_ir_report_controller": True})
        if data.get("options"):
            data.update(json.loads(data.pop("options")))
        if data.get("context"):
            context.update(json.loads(data["context"]))
        request.update_context(**context)

        # Retrieval of ir.actions.report
        carbone_report = request.env["ir.actions.report"]._get_report_from_name(reportname)
        self.check_carbone_report(carbone_report)

        report_content, filename, extension = request.env["ir.actions.report"]._render_carbone(carbone_report, docids)
        if not filename:
            filename = f"{carbone_report.report_name}.{extension}"
        headers = _get_headers(extension, report_content, filename)
        return request.make_response(report_content, headers)

    def _call_carbone_converter(self, docids: str, reportname: str, context: str, url: "str"):
        if docids:
            # Generic report:
            response = self.report_routes(reportname, docids=docids, converter="carbone", context=context)
        else:
            # Particular report:
            data = dict(url_decode(url.split("?")[1]).items())  # decoding the args represented in JSON
            if "context" in data:
                context, data_context = json.loads(context or "{}"), json.loads(data.pop("context"))
                context = json.dumps({**context, **data_context})
            response = self.report_routes(reportname, converter="carbone", context=context, **data)
        return response

    @http.route(["/report/download"], type="http", auth="user")
    def report_download(self, data, context=None):
        """
        Overload of the function to handle ir.actions.reports of "Carbone" type
        :param data: data: a javascript array JSON.stringified contain report internal url ([0]) and
        type [1]
        :param context:
        :return: Response with an attachment header
        """
        requestcontent = json.loads(data)
        url, report_type = requestcontent[0], requestcontent[1]
        if report_type != "carbone":
            return super().report_download(data, context)
        reportname = url
        try:
            reportname = url.split("/report/carbone/")[1].split("?")[0]
            docids = None
            if "/" in reportname:
                reportname, docids = reportname.split("/")

            response = self._call_carbone_converter(docids, reportname, context, url)
            return response
        except Exception as e:
            self.handle_exception_error(e, reportname)

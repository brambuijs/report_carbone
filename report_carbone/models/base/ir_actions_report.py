import base64
import io
import json
import logging
import mimetypes
import os
import re
import zipfile
from collections import OrderedDict
from typing import Any
from urllib.parse import urljoin

import carbone_sdk
import pytz
import requests
from PIL import Image
from werkzeug import urls

from odoo import _, api, exceptions, fields, models, release
from odoo.modules import get_module_path
from odoo.tools.safe_eval import safe_eval, time

from odoo.addons.export_json.controller.main import JsonExportFormat

from ...const import ALLOWED_EXTENSIONS
from ...controllers.main import CarboneReportController
from .exceptions import MissingApiKeyError

_logger = logging.getLogger(__name__)


# put POSIX 'Etc/*' entries at the end to avoid confusing users - see bug 1086728
_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith("Etc/") else "_")]

MODULE_NAME = "report_carbone"
RELATIVE_PATH_PDF = "docs/carbone_userguide_v18.pdf"
RELATIVE_PATH_ODT = "data/demo_template_purchase.odt"
RELATIVE_PLACEHOLDERS_PATH = "data/placeholders"

# In Carbone API documentation, Values ≥ 42000000000 (year 3300) are treated as 'now'.
TIMESTAMP_NOW = 42000000000


def _tz_get(self):
    return _tzs


def _build_zip_from_data(stream_to_ids: dict[Any, list]) -> bytes:
    """
    :param stream_to_ids: dict { io.bytesIo object : [
        int, str]}
    :return: zip bytes
    """
    buffer = io.BytesIO()
    i = 1
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipfile_obj:
        for doc_data in stream_to_ids:
            content = doc_data.getvalue()
            file_name = stream_to_ids[doc_data][1]
            zipfile_obj.writestr(f"{i}-{file_name}", content)
            i += 1
    return buffer.getvalue()


class IrActionsReportCarbone(models.Model):
    _inherit = "ir.actions.report"

    report_type = fields.Selection(selection_add=[("carbone", "Carbone Report")], ondelete={"carbone": "set default"})
    lang_ids = fields.Many2many(
        "res.lang",
        string="Languages",
        help="Language(s) into which the report must be "
        "translated. Leave blank if no specific translation "
        "is required.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        help="Leave blank to let Odoo manage the currency to use "
        "(by default the currency of the associated template, "
        "if there is a currency, otherwise the company currency).",
    )
    tz = fields.Selection(selection=_tzs, string="Timezone")
    template_id = fields.Char(string="Carbone Template ID", default=None)
    export_model = fields.Many2one(
        "ir.exports",
        string="Export Model",
        help="Odoo export template used to retrieve information from a record when "
        "printing the report. These are the same exports as on the Odoo “Export Data” pop-up.",
    )

    hide_create_update_button = fields.Boolean(
        "Hide the 'Create/update export template' button", compute="_compute_hide_create_update_button"
    )
    jsonify_export = fields.Json(string="Export JSON", compute="_compute_all_jsonify_export")
    jsonify_translate_export = fields.Json(string="Export translate JSON", compute="_compute_all_jsonify_export")

    m2o_reference_id = fields.Many2oneReference(
        string="Record for preview",
        model_field="m2o_reference_model",
        help="The data from the field record will be "
        "used for document preview in Studio. The record ID will be used by default for the 'test generation' pop-up.",
    )
    m2o_reference_model = fields.Char(
        string="Reference to the model for m2o_reference", compute="_compute_m2o_reference_model"
    )
    input_user_model_id = fields.Many2one("ir.model", string="Odoo model name", domain=[("transient", "=", False)])
    carbone_translate_ids = fields.One2many(
        "carbone.translate", "ir_actions_report_id", string="Translations available"
    )
    file_extension = fields.Char(string="File extension linked to Carbone Template ID", default="docx")
    is_valid_template_id = fields.Boolean(
        string="Is valid templateId",
        help="True if template id is a templateId,false if it is a versionId",
        compute="_compute_is_valid_template_id",
        store=True,
    )
    partner_lang_path = fields.Char(
        string="Path of the language field",
        help="If specified, the report will be printed according to the language defined in the path. "
        "For example, to print the report in the customer's language for a purchase order, specify partner_id.lang_id. "
        "Leave blank to print the report in the first language specified in the 'Language' field.",
    )
    is_available_in_print_action = fields.Boolean(string="Enable", compute="_compute_is_available_in_print_action")
    report_output_file_extension = fields.Char(
        string="File extension of the generated document",
        help="To be specified in order to generate a document in a format other than PDF "
        "The output format must be included in the list of formats "
        "supported by Carbone. You must provide a production API key and must not "
        "be in test mode.",
    )
    use_complement = fields.Boolean(string="Use complement datas")

    @api.model
    def _setup_template_id_and_extension(self, vals):
        """If a template_id is specified during creation, only the extension is retrieved via the Carbone API
        and the studio is allowed to retrieve the report automatically.
        If there is no template_id, a placeholder report is added to ir.actions.report so that the studio
        can be set up without the user having to specify a template_id.
        """
        if vals.get("template_id"):
            new_file_extension = self.get_extension_file_from_api(vals.get("template_id"), raise_error=False)
            vals.update({"file_extension": new_file_extension})
        else:
            try:
                file_extension = vals.get("file_extension", "docx")
                template_name = vals.get("name") or f"PlaceholderTemplate ({file_extension})"
                new_vals = self.post_template_from_api(template_name, file_extension)
                vals.update(new_vals)
            except Exception as e:
                raise exceptions.UserError(
                    _("An error occurred when uploading placeholder report Carbone : %s") % e
                ) from e

    def check_report_output_file_extension(self, vals):
        report_output_file_extension = vals.get("report_output_file_extension")
        if not report_output_file_extension:
            return
        report_output_file_extension = report_output_file_extension.lower().lstrip(".")

        if report_output_file_extension not in ALLOWED_EXTENSIONS:
            raise exceptions.UserError(
                _("Extension you entered is not included in the list of extensions supported by Carbone.")
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("report_type") == "carbone":
                if not vals.get("report_name"):
                    name = vals.get("name")
                    vals.update({"report_name": name})
                self._setup_template_id_and_extension(vals)

        return super().create(vals_list)

    def write(self, vals):
        if "template_id" in vals.keys():
            new_template_id = vals.get("template_id")
            new_file_extension = self.get_extension_file_from_api(new_template_id, raise_error=False)
            vals.update({"file_extension": new_file_extension})
        if "report_output_file_extension" in vals.keys():
            self.check_report_output_file_extension(vals)
        return super().write(vals)

    def _compute_all_jsonify_export(self):
        """This compute allows you to create data for the jsonify_export and jsonify_translate_export fields.
         - A first step to retrieve a complete JSON of the data, based on the configured export.
        This JSON also contains all available translations, based on the languages active in the tool.
         - The previously retrieved JSON will be used to enhance the translation JSON, which is first built with all the
         carbone.translate related to the report.
         - Once the translation JSON has been modified, we define the jsonify_translate_export field.
         - We can then extract the keys and values containing translations from the complete JSON.
        """
        for rec in self:
            dict_full_data = rec._get_jsonify_export()
            dict_langs = rec._get_jsonify_translate_export()

            # Based on the data from dict_full_data, we add the translations.
            # dict_langs et dict_full_data are modified by reference.
            rec.extract_translations(dict_full_data, dict_langs)

            # The translations are now correctly configured.
            rec.jsonify_translate_export = json.dumps(dict_langs, indent=4)

            # The data no longer has the keys with all the translations for each language.
            rec.jsonify_export = json.dumps(dict_full_data, indent=4)

    def extract_translations(self, data, translations, path: str = ""):
        sub_pattern = ""

        lang = list(translations.keys())
        lang_map = {}
        for code in lang:
            key = code.split("-")[1].upper()
            lang_map.update({key: code})
            sub_pattern += f"{key}|"
        sub_pattern.strip("|")
        translation_pattern = re.compile(r"^(.+)_(" + sub_pattern + ")$")

        keys_to_remove = []

        for key, value in data.items():
            current_path = f"{path}/{key}" if path else key

            match = translation_pattern.match(key)
            if match:
                base_key = match.group(1)
                lang_code = match.group(2)
                locale = lang_map.get(lang_code)

                if locale and locale in translations:
                    if base_key in data:
                        reference_key = data[base_key]
                        if isinstance(reference_key, str):
                            translations[locale][reference_key] = value
                keys_to_remove.append(key)

            elif isinstance(value, dict):
                self.extract_translations(value, translations, current_path)

            elif isinstance(value, list):
                for _i, item in enumerate(value):
                    if isinstance(item, dict):
                        self.extract_translations(item, translations, current_path)

        for key in keys_to_remove:
            del data[key]

    def _get_jsonify_export(self):
        self.ensure_one()
        if not self.export_model or not self.model or self.model not in self.env.registry or not self.m2o_reference_id:
            return {}
        else:
            test_record = self.env[self.model].browse(self.m2o_reference_id)
            export_json_instance = JsonExportFormat()
            export_lines = self.export_model.export_fields
            field_names = self._prepare_fields_name(export_lines)
            lang_codes = self.lang_ids.mapped("code")
            specific_lang = self.get_lang_to_use(test_record, parse_for_carbone=False)
            if specific_lang not in lang_codes:
                lang_codes.append(specific_lang)

            json_data = export_json_instance.perform_json_export(
                [], field_names, test_record.ids, self.env[self.model], lang_codes
            )
            # json_data is an str with a list of dict, we don't want to give user a list, just a dict.
            json_list = json.loads(json_data)
            dict_json = json_list and json_list[0] or json_list[:1]
            return dict_json

    def _get_jsonify_translate_export(self):
        for rec in self:
            all_langs = {}
            available_langs = self.env["res.lang"].search([])
            for lang in available_langs:
                lang_code = lang.code.lower().replace("_", "-")
                all_langs.update({lang_code: {}})

            for carbone_translate in rec.carbone_translate_ids:
                lang_code = carbone_translate.lang_id.code.lower().replace("_", "-")
                lines = {}
                for line in carbone_translate.carbone_translate_line_ids:
                    lines.update({line.source: line.value})
                all_langs.update({lang_code: lines})

            return all_langs

    def _compute_hide_create_update_button(self):
        for rec in self:
            rec.hide_create_update_button = rec.get_hide_create_update_button_value()

    def _compute_is_available_in_print_action(self):
        for rec in self:
            rec.is_available_in_print_action = rec.binding_model_id

    @api.depends("model")
    def _compute_m2o_reference_model(self):
        for rec in self:
            if rec.model not in self.env.registry:
                rec.m2o_reference_model = "res.partner"
            else:
                rec.m2o_reference_model = rec.model

    @api.depends("template_id")
    def _compute_is_valid_template_id(self):
        for rec in self:
            if re.match(r"^[a-f0-9]{64}$", rec.template_id or ""):
                rec.is_valid_template_id = False
            else:
                rec.is_valid_template_id = True

    @api.onchange("model", "export_model", "report_type")
    def onchange_hide_create_update_button(self):
        self.hide_create_update_button = self.get_hide_create_update_button_value()

    @api.onchange("input_user_model_id")
    def onchange_user_model_id(self):
        if self.report_type == "carbone" and self.input_user_model_id:
            self.model = self.input_user_model_id.model
            # We have to set a new record in the m2o_reference_id, because Odoo will try to display a record with
            # current id (4 for example), from a existing model X, in a non-existing record with id 4 in model Y.
            self.m2o_reference_id = self.env[self.model].search([], limit=1)
            export_suffixe_name = self.input_user_model_id.display_name
            if not self.export_model:
                self.export_model = self.retrieve_global_export_model(self.model, export_suffixe_name)

    @api.onchange("name")
    def onchange_name(self):
        """For Carbon reports, the ‘report_type’ field is not displayed.
        It is not used when printing Carbon reports; it is filled in automatically."""
        if self.report_type == "carbone":
            self.report_name = self.name

    def action_setup_carbone_studio_options(self):
        """Use to set-up JSON dicts (data, translations) for Carbone Studio, and retrieve lang in which
        report will be rendered."""
        self.ensure_one()
        test_record = self.env[self.model].browse(self.m2o_reference_id)
        lang_code = self.get_lang_to_use(test_record)
        currency = self.get_currency_to_use(test_record)
        timezone = self.env.context.get("tz") or self.env.user.tz
        template = self.template_id
        extension = self.file_extension
        if not extension:
            extension = self.get_extension_file_from_api(template, raise_error=False)
            self.file_extension = extension

        return {
            "type": "ir.actions.client",
            "tag": "copy_options_to_carbone",
            "context": {
                "record_id": self.id,
                "json_data": self.jsonify_export,
                "json_translate_data": self.jsonify_translate_export,
                "lang": lang_code,
                "timezone": timezone,
                "currency": currency.name,
                "template": template,
                "extension": extension,
            },
        }

    def action_refresh_carbone_studio(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "action_refresh_carbone_studio",
        }

    def get_hide_create_update_button_value(self):
        self.ensure_one()
        res = False
        group_viewer = "report_carbone.group_report_carbone_viewer"
        if (
            self.report_type != "carbone"
            or (self.export_model and not self.export_model.is_global_export)
            or (self.model not in self.env.registry)
            or (self.env.user.has_groups(group_viewer))
        ):
            res = True
        return res

    def get_currency_to_use(self, record=False) -> "odoo.model.res_currency":
        self.ensure_one()
        currency = record and record.carbone_default_currency_id or self.env.user.company_id.currency_id
        if self.currency_id and self.currency_id != currency:
            currency = self.currency_id
        return currency

    def _get_nested_field(self, record, field_path):
        """
        Find the information in the field, based on the path entered, only if the path is valid.
        """
        if not field_path:
            return False

        fields = field_path.split(".")
        current = record

        for field_name in fields:
            if not current or field_name not in current._fields:
                return False
            current = current[field_name]

            if hasattr(current, "_name") and not current:
                return False

        return current

    def get_lang_to_use(self, record, parse_for_carbone=True) -> str:
        """
        For language, the rules are as follows:

        If the function call comes from the test report pop-up, we keep the language specified in the context.
        Otherwise, if a language is specified in ‘partner_lang_path’, we retrieve the associated language.
        Otherwise, we retrieve the first language specified in the ‘lang_ids’ field.
        If the language is still not specified, the language set in the context is retrieved, or else the user's
        language.

        :param record: "odoo.model.any"
        :param parse_for_carbone: bool
        :return: lang code (ex : fr_FR for French)
        """
        self.ensure_one()
        lang = ""
        if self.env.context.get("from_print_by_action"):
            lang = self.env.context.get("lang")
        elif self.partner_lang_path:
            lang = self._get_nested_field(record, self.partner_lang_path)

        if not lang:
            lang = self.lang_ids and self.lang_ids[0].code or self.env.context.get("lang") or self.env.user.lang

        if parse_for_carbone:
            return lang.lower().replace("_", "-")
        return lang

    def _prepare_fields_name(self, export_lines: "odoo.model.ir_exports_line") -> tuple[str]:
        field_names = []
        if "id" not in export_lines.mapped("name"):
            field_names = ["id"]
        for line in export_lines:
            field_names.append(line.name)
        return field_names

    def check_required_fields(self):
        """Raise user error if template_id or export_model fields are missing."""
        missing_field = []
        if not self.template_id:
            missing_field.append("Carbone Template ID")
        if not self.export_model:
            missing_field.append("export model")
        if missing_field:
            raise exceptions.UserError(f"Missing {', '.join(missing_field)} to generate this report")

    def _get_parameters_for_render(self, context, record, parse_for_carbone=True) -> tuple:
        """Used to retrieve lang to translate report, timezone and currency, to render a
        Carbone report."""
        self.ensure_one()

        lang = self.with_context(context).get_lang_to_use(record, parse_for_carbone)

        currency_id = context.get("currency_id")
        currency = self.env["res.currency"].browse(currency_id)
        if not currency:
            currency = self.get_currency_to_use(record)

        tz = context.get("tz") or self.env.user.tz

        return lang, tz, currency

    def _check_no_test_mode_and_prod_api_key(self, extension: str):
        """A user error is raised if the user attempts to print a report in a format other than PDF,
        and the system is in test mode and/or there is no production API key"""
        self.ensure_one()
        is_stage_mode = self.env["ir.config_parameter"].sudo().get_param("report-engine.is_stage_mode")
        prod_api_key = self.env["ir.config_parameter"].sudo().get_param("report-engine.prod_api_key")
        if extension != "pdf" and (is_stage_mode or not prod_api_key):
            raise exceptions.UserError(
                _(
                    "You cannot generate a document in any format other than "
                    "PDF in test mode and/or without a prod API key"
                )
            )

    def get_report_output_file_extension(self) -> str:
        self.ensure_one()
        if self.report_output_file_extension:
            self._check_no_test_mode_and_prod_api_key(self.report_output_file_extension)
            return self.report_output_file_extension
        return "pdf"

    def get_default_user_agent(self) -> str:
        default_user_agent = requests.utils.default_user_agent()
        return f"{default_user_agent} Mangono Odoo v{release.version}"

    def _retrieve_attachement(self, collected_streams, res_ids, has_duplicated_ids):
        """Copy of odoo/addons/base/models/ir_actions_report.py "_render_qweb_pdf_prepare_streams" function.
        The only change was to retrieve the name of the associated
        attachment when printing several reports at the same time
        (we create one zip file with X files, rather than one file containing the information from X files).
        """
        if res_ids:
            records = self.env[self.model].browse(res_ids)
            for record in records:
                res_id = record.id
                if res_id in collected_streams:
                    continue

                stream = None
                attachment = None
                if not has_duplicated_ids and self.attachment and not self._context.get("report_pdf_no_attachment"):
                    attachment = self.retrieve_attachment(record)

                    # Extract the stream from the attachment.
                    if attachment and self.attachment_use:
                        stream = io.BytesIO(attachment.raw)

                        # Ensure the stream can be saved in Image.
                        if attachment.mimetype.startswith("image"):
                            img = Image.open(stream)
                            new_stream = io.BytesIO()
                            img.convert("RGB").save(new_stream, format="pdf")
                            stream.close()
                            stream = new_stream
                filename = attachment and attachment.name or False
                collected_streams[res_id] = {
                    "stream": stream,
                    "attachment": attachment,
                    "filename": filename,
                }
        return collected_streams

    @api.model
    def get_carbone_sdk(self) -> carbone_sdk.CarboneSDK:
        access_token = self.env["res.config.settings"].retrieve_carbone_api_key()
        if not access_token:
            raise MissingApiKeyError(
                _("No API Carbone key has been entered. Please enter it or contact your administrator.")
            )

        csdk = carbone_sdk.CarboneSDK(access_token)
        csdk._api_headers.update({"User-Agent": self.get_default_user_agent()})
        # BB Open patch: render tegen on-premise Carbone-server i.p.v. SDK-default
        # api.carbone.io (cloud). carbone_studio_url wordt anders alleen voor de
        # browser-Studio gebruikt → render lekt naar cloud → "Invalid JWT audience".
        api_url = self.env["ir.config_parameter"].sudo().get_param("report-engine.carbone_studio_url")
        if api_url:
            csdk.set_api_url(api_url.rstrip("/"))
        return csdk

    def _call_carbone_to_get_streams(self, all_res_ids_wo_stream: list, collected_streams: OrderedDict):
        # Creation of Carbone and JsonExportFormat instances
        csdk = self.get_carbone_sdk()

        export_json_instance = JsonExportFormat()

        # Recovery of the report model.
        model = self.model

        # Retrieving field_names from the report.
        field_names = ["id"]
        export_lines = self.export_model.export_fields
        field_names.extend(line.name for line in export_lines)

        context = dict(self.env.context)

        records = self.env[model].browse(all_res_ids_wo_stream) or self.env[model]
        if not records.exists():
            raise exceptions.MissingError(_("No %s selected for printing." % records._description))  # noqa: UP031

        for record in records:
            try:
                # We retrieve the translation language, time zone and currency.
                lang, tz, currency = self._get_parameters_for_render(context, record, parse_for_carbone=False)

                # We collect all the languages into which the report can be translated. And, if necessary,
                # the target language is added to the list of possible translations for the report.
                lang_codes = self.lang_ids.mapped("code")
                if lang not in lang_codes:
                    lang_codes.append(lang)
                # After that, we can transform lang code to match the Carbone language format.
                lang = lang.lower().replace("_", "-")

                # Creating the JSON file (data and translate).
                json_data = export_json_instance.perform_json_export(
                    [], field_names, record.ids, self.env[model], lang_codes
                )
                dict_full_data = json.loads(json_data)[0]
                dict_langs = self._get_jsonify_translate_export()
                # Modification by reference of dicts.
                self.extract_translations(dict_full_data, dict_langs)

                output_file_extension = self.get_report_output_file_extension()
                tuple_pdf = csdk.render(
                    self.template_id,
                    {
                        "complement": self.use_complement and dict_full_data or "",
                        "data": self.use_complement and "" or dict_full_data,
                        "convertTo": output_file_extension,
                        "translations": dict_langs,
                        "lang": lang,
                        "timezone": tz,
                        "currencySource": currency.name,
                        "currencyTarget": currency.name,
                    },
                )
                pdf_content_stream = io.BytesIO(tuple_pdf[0])

                filename = self._retrieve_carbone_filename(record, output_file_extension)
                collected_streams[record.id]["stream"] = pdf_content_stream
                collected_streams[record.id]["filename"] = filename
                collected_streams[record.id]["out_file_extension"] = output_file_extension
            except Exception as e:
                raise exceptions.UserError(
                    _("An error occurred when generating the report via Carbone : %s") % e
                ) from e
        return collected_streams

    def _render_carbone_prepare_streams(self, res_ids=None):
        has_duplicated_ids = res_ids and len(res_ids) != len(set(res_ids))

        collected_streams = OrderedDict()
        if res_ids:
            collected_streams = self._retrieve_attachement(collected_streams, res_ids, has_duplicated_ids)

        res_ids_wo_stream = [res_id for res_id, stream_data in collected_streams.items() if not stream_data["stream"]]
        all_res_ids_wo_stream = res_ids if has_duplicated_ids else res_ids_wo_stream
        is_carbone_needed = not res_ids or res_ids_wo_stream

        if is_carbone_needed:
            collected_streams = self._call_carbone_to_get_streams(all_res_ids_wo_stream, collected_streams)
        return collected_streams

    def _render_carbone_handler_create_attachment(self, has_duplicated_ids, collected_streams):
        """Copy of odoo/addons/base/models/ir_actions_report.py _render_qweb_pdf() ir.attachment handler"""
        # Generate the ir.attachment if needed.
        if not has_duplicated_ids and self.attachment and not self._context.get("report_pdf_no_attachment"):
            attachment_vals_list = self._prepare_pdf_report_attachment_vals_list(self, collected_streams)
            if attachment_vals_list:
                attachment_names = ", ".join(x["name"] for x in attachment_vals_list)
                try:
                    self.env["ir.attachment"].create(attachment_vals_list)
                except exceptions.AccessError:
                    _logger.info(
                        "Cannot save PDF report %r attachments for user %r",
                        attachment_names,
                        self.env.user.display_name,
                    )
                else:
                    _logger.info("The PDF documents %r are now saved in the database", attachment_names)

    def _render_carbone(self, report_ref, docids: str | list, data=None) -> tuple[bytes, str]:
        context = dict(self.env.context)

        report_sudo = self._get_report(report_ref)
        report_sudo = report_sudo.with_env(self.env(context=context))

        # docids can be either a string, if the function call comes from
        # a "Print" button, on a list the call does not come from the button.
        res_ids = self.get_ids(docids)
        has_duplicated_ids = res_ids and len(res_ids) != len(set(res_ids))

        report_sudo.check_required_fields()

        collected_streams = report_sudo._render_carbone_prepare_streams(res_ids)

        report_sudo._render_carbone_handler_create_attachment(has_duplicated_ids, collected_streams)

        stream_to_ids = {
            v["stream"]: [k, v.get("filename", False), v.get("out_file_extension", False)]
            for k, v in collected_streams.items()
            if v["stream"]
        }
        streams_to_dl = list(stream_to_ids.keys())

        if not context.get("from_ir_report_controller") or len(streams_to_dl) == 1:
            pdf_content = streams_to_dl[0].getvalue()
            # stream_to_ids[streams_to_dl[0]] contains [record_id, filename, extension]
            filename = stream_to_ids[streams_to_dl[0]][1]
            extension = stream_to_ids[streams_to_dl[0]][2]
            return pdf_content, filename, extension

        zip_content = _build_zip_from_data(stream_to_ids)
        return zip_content, False, "zip"

    def _retrieve_carbone_filename(self, records, output_file_extension: str) -> str:
        self.ensure_one()
        filename = f"{self.name}.{output_file_extension}"
        if records:
            if self.print_report_name and not len(records) > 1:  # print_report_name is not mandatory
                report_name = self._sanitize(safe_eval(self.print_report_name, {"object": records, "time": time}))
                filename = f"{report_name}.{output_file_extension}"
        return filename

    @api.model
    def _sanitize(self, name: str) -> str:
        """Avoid slash in filename, otherwise zip will  create subdirectory."""
        return name.replace("/", "_").replace(":", "_").replace("\\", "_").replace(" ", "_")

    @api.model
    def _get_report_from_name(self, report_name: str) -> "odoo.model.ir_actions_report":
        """Override to first search for an ir.actions.report by the "Carbone" report type and name,
        before just searching by the report name. Allows you to have reports of different types,
        "Carbone" and others."""

        report_obj = self.env["ir.actions.report"]
        domain = [
            ("report_type", "=", "carbone"),
            ("report_name", "=", report_name),
        ]
        context = self.env["res.users"].context_get()
        res = report_obj.with_context(context).sudo().search(domain, limit=1)
        if not res:
            return super()._get_report_from_name(report_name)
        return res

    @api.model
    def get_ids(self, docids: str | list) -> list[int]:
        if isinstance(docids, list):
            return docids
        return [int(x) for x in docids.split(",")]

    @api.model
    def check_model_in_registry(self, model_name: str):
        if model_name not in self.env.registry:
            raise exceptions.UserError(_("Error : Model not found in registry"))

    def action_carbon_print_by_action_window(self):
        self.ensure_one()
        self.check_model_in_registry(self.model)
        record = self.env[self.model].browse(self.m2o_reference_id)
        context = self.env.context.copy()
        if record:
            context.update({"record_id": record.id, "currency_id": self.get_currency_to_use(record).id})
        return {
            "name": _("Test generation"),
            "view_mode": "form",
            "res_model": "carbone.print_by_action",
            "type": "ir.actions.act_window",
            "context": dict(context),
            "target": "new",
        }

    def create_global_export(self, model_name: str, export_suffixe_name: str) -> "odoo.model.ir_exports":
        fields = self.env["carbone.field.extractor"].get_fields_from_multiple_views(self.model)

        to_create_ir_export_line = [(0, 0, {"name": field}) for field in fields]

        to_create_ir_export_line.insert(0, (5, 0, 0))
        return self.env["ir.exports"].create(
            {
                "name": f"Global Export For Carbone - {export_suffixe_name}",
                "resource": model_name,
                "export_fields": to_create_ir_export_line,
                "is_global_export": True,
            }
        )

    def action_download_carbone_documentation(self):
        ir_attachment_name = "Carbone_report_guide.pdf"
        attachment_xml_id = "report_carbone.report_carbone_userguide_attachment"
        return self.download_carbone_file(ir_attachment_name, attachment_xml_id, MODULE_NAME, RELATIVE_PATH_PDF)

    def action_download_carbone_file_sample(self):
        ir_attachment_name = "Demo_template_purchase_order.odt"
        attachment_xml_id = "report_carbone.report_carbone_demo_purchase_order"
        return self.download_carbone_file(ir_attachment_name, attachment_xml_id, MODULE_NAME, RELATIVE_PATH_ODT)

    def download_carbone_file(
        self, ir_attachment_name: str, attachment_xml_id: str, module_name: str, relative_path: str
    ) -> dict:
        attachment = self.env.ref(attachment_xml_id, raise_if_not_found=False)
        if not attachment:
            attachment = self.env["ir.attachment"].search([("name", "=", ir_attachment_name)], limit=1)
            if not attachment:
                try:
                    module_path = get_module_path(module_name)
                    pdf_path = os.path.join(module_path, relative_path)
                    with open(pdf_path, "rb") as pdf_file:
                        pdf_content = pdf_file.read()
                except Exception as e:
                    raise exceptions.UserError(_("Unable to read file: %s") % str(e)) from e
                datas = base64.b64encode(pdf_content)
                attachment = self.env["ir.attachment"].create(
                    {
                        "name": ir_attachment_name,
                        "datas": datas,
                        "public": True,
                    }
                )
        return {
            "type": "ir.actions.act_url",
            "target": "new",
            "url": f"/web/content/{attachment.id}",
        }

    def retrieve_global_export_model(self, model_name: str, export_suffixe_name: str) -> "odoo.model.ir_exports":
        """Retrieve or create a global export model, when user change Odoo model from ir.actions.report."""
        global_export = self.env["ir.exports"].search(
            [("resource", "=", model_name), ("is_global_export", "=", True)], limit=1
        )
        if not global_export:
            return self.create_global_export(model_name, export_suffixe_name)
        return global_export

    def button_create_update_ir_export(self):
        if self.model not in self.env.registry or not self.input_user_model_id:
            return

        global_export = self.env["ir.exports"].search(
            [("resource", "=", self.model), ("is_global_export", "=", True)], limit=1
        )
        if not global_export:
            export_suffixe = self.input_user_model_id.display_name
            self.export_model = self.create_global_export(self.model, export_suffixe)
        else:
            carbone_extractor = self.env["carbone.field.extractor"]
            last_update_fields = carbone_extractor.get_fields_from_multiple_views(self.model)
            old_fields = global_export.export_fields.mapped("name")
            if last_update_fields == old_fields:
                return
            carbone_extractor.update_current_global_export(global_export, last_update_fields, old_fields)

    @api.model
    def post_template_from_api(self, template_name: str, file_extension: str) -> dict:
        module_path = get_module_path(MODULE_NAME)
        relative_file_path = f"{RELATIVE_PLACEHOLDERS_PATH}/template.{file_extension}"
        file_path = os.path.join(module_path, relative_file_path)
        with open(file_path, "rb") as f:
            file_content = f.read()
        files = {
            "template": (
                os.path.basename(file_path),
                file_content,
                mimetypes.guess_type(file_path)[0] or "application/octet-stream",
            )
        }
        data = {
            "name": template_name,
            "versioning": "true",
            "deployedAt": TIMESTAMP_NOW,
        }
        response = self.call_carbone_endpoint("template", method="POST", files=files, data=data)
        return {"template_id": response["data"]["id"], "file_extension": file_extension}

    def get_extension_file_from_api(self, template_id: str, raise_error=True) -> str | bool:
        # If we are in install mode, for unit test for example, and we have to init a ir.actions.report from an XML
        # file, we don't wan't to call Carbone's API to retrieve extension.
        if self.env.context.get("install_mode"):
            return ".docx"

        endpoint = "templates"
        params = {
            "search": template_id,
            "limit": 1,
            "includeVersions": "true",
        }
        res = self.call_carbone_endpoint(endpoint, params, raise_error)

        # BB Open patch: on-premise carbone-ee draait stateless (geen DB) → het
        # /templates-endpoint bestaat niet (error-string, code w130) i.p.v. een
        # JSON-dict. Default dan naar .docx (WAF-templates zijn .docx).
        if not isinstance(res, dict):
            return ".docx"

        data_list = res.get("data")
        if not data_list:
            return ".docx"

        return data_list[0].get("type")

    def call_carbone_endpoint(self, endpoint: str, params=None, raise_exception=True, method="GET", **kwargs):
        api_token = self.env["res.config.settings"].retrieve_carbone_api_key()
        if not api_token:
            if raise_exception:
                raise MissingApiKeyError(
                    _("No API Carbone key has been entered. Please enter it or contact your administrator.")
                )
            else:
                return False
        api_endpoint = self.env["ir.config_parameter"].sudo().get_param("report-engine.carbone_studio_url")
        response = requests.Response
        # We have to specified carbone-version 5
        headers = {"Authorization": "Bearer " + api_token, "carbone-version": "5"}

        url = f"{api_endpoint}/{endpoint}"
        if params:
            url = urljoin(url, "?" + urls.url_encode(params))
        if method == "GET":
            response = requests.get(url, headers=headers, **kwargs)
        elif method == "POST":
            response = requests.post(url, headers=headers, **kwargs)

        handled_response = CarboneReportController.handle_response(response, raise_exception=raise_exception)
        return handled_response

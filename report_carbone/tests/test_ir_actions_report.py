import json
from unittest.mock import MagicMock, Mock, patch

from requests import Response

from odoo import exceptions
from odoo.tests import common, tagged

from odoo.addons.export_json.controller import main as controller_module

from ..models.base.exceptions import MissingApiKeyError
from ..models.base.ir_actions_report import IrActionsReportCarbone


@tagged("carbone")
class TestIrActionsReport(common.TransactionCase):
    @classmethod
    def create_demo_report(cls):
        cls.report = cls.env["ir.actions.report"].create(
            {
                "name": "Partner Carbone Export",
                "model": "res.partner",
                "report_type": "carbone",
                "report_name": "report_carbone.partner_carbone",
                "report_file": "report_carbone.partner_carbone",
                "binding_model_id": cls.env.ref("base.model_res_partner").id,
                "binding_type": "report",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("base.group_system").id,
                            cls.env.ref("base.group_erp_manager").id,
                        ],
                    )
                ],
                "template_id": "mock_carbone_template_id",
                "export_model": cls.env.ref("jsonifier.ir_exp_partner").id,
            }
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with patch.object(
            IrActionsReportCarbone,
            "call_carbone_endpoint",
            return_value={},
        ):
            cls.report = cls.create_demo_report()

    def setUp(self):
        self.mock_request = MagicMock()
        self.mock_request.env = self.env
        self._setup_patcher(controller_module, "request", self.mock_request)

        self.report_object = self.env["ir.actions.report"]
        self.report_name = "report_carbone.partner_carbone"
        self.report = self.report_object.search([("report_name", "=", self.report_name)])
        self.partner_demo = self.env.ref("base.partner_demo")
        self.partner_admin = self.env.ref("base.partner_admin")

        self.docids = f"{self.partner_demo.id},{self.partner_admin.id}"
        self.env["ir.config_parameter"].set_param("report-engine.stage_api_key", "mock_key")
        self._setup_patcher(IrActionsReportCarbone, "call_carbone_endpoint", Mock(return_value={}))

    def test_generate_report_carbone_without_api_keys(self):
        """MissingApiKeyError has to be raised when we try to generate a carbone report without an API key."""
        self.env["ir.config_parameter"].set_param("report-engine.stage_api_key", False)
        with self.assertRaises(MissingApiKeyError):
            ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)
            ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)

    def test_generate_report_carbone_without_docids(self):
        """MissingError has to be raised, when no record are retrieved from docids given."""
        with self.assertRaises(exceptions.MissingError):
            ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)
            docids = str(self.get_not_use_id(ir_actions_report_carbone.model))
            ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, docids)

    def test_generate_report_carbone(self):
        # ruff: noqa: E501
        bytes_tuple = (
            b"%PDF-1.6\n%\xc3\xa4\xc3\xbc\xc3\xb6\xc3\x9f\n2 0 obj\n<</Length 3 0 R/Filter/FlateDecode>>\nstream\nendstream\nendobj\n\n33 0 obj\n<</Type/Font/Subtype/TrueType/BaseFont/EAAAAA+ArialMT\n/FirstChar 0\n/LastChar 7\n/Widths[0 722 556 333 556 556 556 556 ]\n/FontDescriptor 31 0 R\n/ToUnicode 32 0 R\n>>\nendobj\n\n34 0 obj\n<</F1 18 0 R/F2 28 0 R/F3 23 0 R/F4 33 0 R\n>>\nendobj\n\n12 0 obj\n<</Font 34 0 R\n/XObject<</Im4 4 0 R/Im5 5 0 R/Tr6 6 0 R>>\n/ExtGState<</EGS7 7 0 R>>\n/ProcSet[/PDF/Text/ImageC/ImageI/ImageB]\n>>\nendobj\n\n1 0 obj\n<</Type/Page/Parent 13 0 R/Resources 12 0 R/MediaBox[0 0 595.303937007874 841.889763779528]/Contents 2 0 R>>\nendobj\n\n13 0 obj\n<</Type/Pages\n/Resources 12 0 R\n/MediaBox[ 0 0 595.303937007874 841.889763779528 ]\n/Kids[ 1 0 R ]\n/Count 1>>\nendobj\n\n35 0 obj\n<</Type/Catalog/Pages 13 0 R\n/OpenAction[1 0 R /XYZ null null 0]\n/Lang(fr-FR)\n>>\nendobj\n\n36 0 obj\n<</Creator<FEFF005700720069007400650072>\n/Producer<FEFF004C0069006200720065004F0066006600690063006500200037002E0035>\n/CreationDate(D:20240516115831+02'00')>>\nendobj\n\nxref\n0 37\n0000000000 65535 f \n0000090176 00000 n \n0000000019 00000 n \n0000001987 00000 n \n0000035046 00000 n \n0000002008 00000 n \n0000037841 00000 n \n0000038144 00000 n \n0000035024 00000 n \n0000035443 00000 n \n0000035463 00000 n \n0000037819 00000 n \n0000090031 00000 n \n0000090301 00000 n \n0000038184 00000 n \n0000060763 00000 n \n0000060786 00000 n \n0000060977 00000 n \n0000061557 00000 n \n0000061966 00000 n \n0000063555 00000 n \n0000063577 00000 n \n0000063780 00000 n \n0000064073 00000 n \n0000064247 00000 n \n0000078836 00000 n \n0000078859 00000 n \n0000079055 00000 n \n0000079529 00000 n \n0000079847 00000 n \n0000089251 00000 n \n0000089273 00000 n \n0000089464 00000 n \n0000089788 00000 n \n0000089968 00000 n \n0000090427 00000 n \n0000090525 00000 n \ntrailer\n<</Size 37/Root 35 0 R\n/Info 36 0 R\n/ID [ <DE2B8E34DC80E09A45CB0B58E0A5B779>\n<DE2B8E34DC80E09A45CB0B58E0A5B779> ]\n/DocChecksum /7FB032CF1C87DF68AA5900715229F0B7\n>>\nstartxref\n90700\n%%EOF\n",
            "report_name.pdf",
        )
        with patch("carbone_sdk.CarboneSDK.render", return_value=bytes_tuple):
            self.assertEqual(self.report.report_type, "carbone")
            ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)
            ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)

    def test_get_report_from_name(self):
        # ir_actions_report found with name and report_type == "carbone':
        res = self.report_object._get_report_from_name(self.report_name)
        self.assertTrue(res, "Record have to be found")
        self.assertEqual(res, self.report, "Record found have to be equal of ir_actions_report's Carbone")

        # ir_actions_report found only name:
        homonym_report = self.report.copy()
        homonym_report.report_type = "qweb-pdf"

        res = self.report_object._get_report_from_name(homonym_report.report_name)
        self.assertTrue(res, "Record have to be found")
        self.assertEqual(res, self.report, "Record found have to be equal of copy of Carbone's report")

    def test_failed_generate_report_carbone(self):
        ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)
        mock_render_report = {"success": False, "data": {"renderId": "mock_renderID"}, "error": "ENOENT:File not found"}
        mock_get_report = "empty_pdf"

        # Error
        with (
            patch("carbone_sdk.CarboneSDK.render_report", return_value=mock_render_report),
            patch("carbone_sdk.CarboneSDK.get_report", return_value=mock_get_report),
        ):
            with self.assertRaises(exceptions.UserError) as error:
                ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)

        self.assertEqual(
            str(error.exception),
            "An error occurred when generating the report via Carbone : "
            "Carbone SDK render error: ENOENT:File not found",
        )

    def test_failed_generate_report_carbone_status_code_400(self):
        ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)

        def post(url, **kwargs):
            response = Response()
            if url.startswith("https://api.carbone.io/render/mock_carbone_template_id"):
                response.status_code = 400  # NotFileError
                response._content = json.dumps(
                    {
                        "success": False,
                        "error": "NotFileError",
                    }
                ).encode("utf-8")
            return response

        with patch("requests.post", post):
            with self.assertRaises(exceptions.UserError) as error:
                ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)
        self.assertEqual(
            str(error.exception),
            "An error occurred when generating the report via Carbone : Carbone SDK render error: NotFileError",
        )

    def test_failed_generate_report_carbone_status_code_500(self):
        ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)

        def post(url, **kwargs):
            response = Response()
            if url.startswith("https://api.carbone.io/render/mock_carbone_template_id"):
                response.status_code = 500  # GenerateReportError
                response._content = json.dumps(
                    {
                        "success": False,
                        "error": "GenerateReportError",
                    }
                ).encode("utf-8")
            return response

        with patch("requests.post", post):
            with self.assertRaises(exceptions.UserError) as error:
                ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)
        self.assertEqual(
            str(error.exception),
            "An error occurred when generating the report via Carbone : Carbone SDK render error: GenerateReportError",
        )

    def test_failed_generate_report_render_error(self):
        # Error Carbone SDK render error:
        ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)

        mock_result = {"success": False, "error": "mock_error_message"}
        with (
            patch("os.path.exists", return_value=True),
            patch("carbone_sdk.CarboneSDK.generate_template_id", return_value="no_template_carbone_id"),
            patch("carbone_sdk.CarboneSDK.add_template", return_value=mock_result),
            patch("carbone_sdk.CarboneSDK.render_report", return_value=mock_result),
        ):
            with self.assertRaises(exceptions.UserError) as error:
                ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)
        self.assertEqual(
            str(error.exception),
            "An error occurred when generating the report via Carbone : Carbone SDK render error:mock_error_message",
        )

    def test_failed_generate_report_failed_template_id(self):
        # Error Carbone SDK render error: failled to generate the template id
        ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)

        with patch("os.path.exists", return_value=True):
            with self.assertRaises(exceptions.UserError) as error:
                ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)
        self.assertEqual(
            str(error.exception),
            "An error occurred when generating the report via Carbone :"
            " Carbone SDK render error: failled to generate the template id",
        )

    def test_failed_generate_report_no_export(self):
        # Error export_model
        ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)
        with self.assertRaises(exceptions.UserError) as error:
            ir_actions_report_carbone.export_model = False
            ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)
        self.assertEqual(str(error.exception), "Missing export model to generate this report")

    def test_failed_generate_report_no_template_id(self):
        # Error with no template_id (custom error that squash template_ir error from carbone sdk).
        ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)
        with self.assertRaises(exceptions.UserError) as error:
            ir_actions_report_carbone.template_id = None
            ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)
        self.assertEqual(str(error.exception), "Missing Carbone Template ID to generate this report")

    def test_failed_generate_report_no_render_id(self):
        # Error no render_id send by Carbone
        ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)

        mock_result = {"success": True, "data": {"renderId": []}}
        with (
            patch("carbone_sdk.CarboneSDK.generate_template_id", return_value="no_template_carbone_id"),
            patch("carbone_sdk.CarboneSDK.render_report", return_value=mock_result),
        ):
            with self.assertRaises(exceptions.UserError) as error:
                ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)
        self.assertEqual(
            str(error.exception),
            "An error occurred when generating the report via Carbone : Carbone SDK render error: render_id empty",
        )

    def test_failed_generate_report_default_error(self):
        # Default SDK's error
        ir_actions_report_carbone = self.report_object._get_report_from_name(self.report_name)
        mock_result = None
        with patch("carbone_sdk.CarboneSDK.render_report", return_value=mock_result):
            with self.assertRaises(exceptions.UserError) as error:
                ir_actions_report_carbone._render_carbone(ir_actions_report_carbone, self.docids)
        self.assertEqual(
            str(error.exception),
            "An error occurred when generating the report via Carbone : Carbone SDK render error: something went wrong",
        )

    # region utils

    def get_not_use_id(self, model_name: "str") -> int:
        records = self.env[model_name].search([])
        return max(records.mapped("id")) + 1

    def _setup_patcher(self, target, attribute, new_value):
        patcher = patch.object(target, attribute, new_value)
        patcher.start()
        self.addCleanup(patcher.stop)
        return patcher

    # endregion utils

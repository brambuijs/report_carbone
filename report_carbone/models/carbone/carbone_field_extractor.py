import xml.etree.ElementTree as ET  # type: ignore  # noqa: F401

from odoo import api, models

FIELDS_RECURSION_LIMIT = 0
EXCLUDED_FIELDS = [
    "id",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
    "display_name",
    "message_ids",
    "activity_ids",
    "activity_user_id",
    "message_partner_ids",
    "activity_type_id",
    "default_user_id",
]


class CarboneFieldExtractor(models.Model):
    _name = "carbone.field.extractor"
    _description = "Field extractor for exports based on views"

    @api.model
    def get_exportable_fields_from_view(self, model_name, view_type):
        """
        Retrieves exportable fields from a view (priority to form/list)

        :param model_name: Model name
        :param view_type: Type of view ('list', 'form', 'search')
        :return: List of exportable fields with their info
        """
        target_model = self.env[model_name]

        view_info = target_model.get_view(view_type=view_type)

        root = ET.fromstring(view_info["arch"])

        exportable_fields = []
        processed_fields = set()

        for field_elem in root.iter("field"):
            field_name = field_elem.get("name")

            if field_name and field_name not in processed_fields and field_name in target_model._fields:
                field_obj = target_model._fields[field_name]

                if self._is_field_exportable(field_obj):
                    fields_info = self._get_field_export_info(field_name, field_obj, field_elem)
                    exportable_fields.extend(fields_info)
                    processed_fields.add(field_name)

        return exportable_fields

    @api.model
    def _is_field_exportable(self, field_obj):
        if field_obj.name in EXCLUDED_FIELDS:
            return False

        return getattr(field_obj, "exportable", True)

    @api.model
    def _get_field_export_info(self, field_name, field_obj, field_elem):
        """
        Retrieves export information for a field
        """
        field_info = field_name
        sub_fields = []
        if field_obj.type in ["one2many", "many2many"]:
            sub_fields = self._extract_o2m_m2m_fields(field_elem, field_obj.comodel_name, field_name)
        sub_fields.extend([field_info])
        return sub_fields

    @api.model
    def _get_sub_field_info(self, field_name, comodel_name):
        """
        Retrieves the name of a subfield
        """
        target_model = self.env[comodel_name]
        if field_name not in target_model._fields:
            return None

        field_obj = target_model._fields[field_name]
        if not self._is_field_exportable(field_obj):
            return None

        return field_name

    @api.model
    def _get_inline_view_fields(self, field_elem, comodel_name):
        """
        Recovers fields from inline views (list/form in the field XML)
        """
        inline_fields = []

        for child_elem in field_elem:
            if child_elem.tag in ("list", "form"):
                for sub_field_elem in child_elem.iter("field"):
                    sub_field_name = sub_field_elem.get("name")
                    if sub_field_name:
                        field_info = self._get_sub_field_info(sub_field_name, comodel_name)
                        if field_info:
                            inline_fields.append(field_info)
                break  # Prendre la première vue trouvée

        return inline_fields

    @api.model
    def _extract_o2m_m2m_fields(self, field_elem, comodel_name, parent_field_name):
        """
        Extracts the O2M/M2M relationship fields from inline views

        :param field_elem: XML element of the O2M/M2M field
        :param comodel_name: Target model name
        :param parent_field_name: Parent field name
        :return: List of subfields with their information
        """
        sub_fields = []

        inline_fields = self._get_inline_view_fields(field_elem, comodel_name)
        if not inline_fields:
            return sub_fields

        sub_fields = [f"{parent_field_name}/{sub_field_info}" for sub_field_info in inline_fields]

        return sub_fields

    def clean_fields(self, fields):
        """Allows you to remove occurrences from fields that are displayed with subfields
        (order_line/name, order_line/product_id, and order_line)..
        If 'order_line' is not removed, it is the only thing Odoo will display."""
        prefixes = {f.split("/")[0] for f in fields if "/" in f}
        result = [f for f in fields if not (f in prefixes and any(ff.startswith(f + "/") for ff in fields))]
        return result

    @api.model
    def get_fields_from_multiple_views(self, model_name, view_types=None):
        if view_types is None:
            view_types = ["list", "form"]

        all_fields = []

        for view_type in view_types:
            fields = self.get_exportable_fields_from_view(model_name, view_type)
            for field_info in fields:
                if field_info not in all_fields:
                    all_fields.append(field_info)

        clean_fields = self.clean_fields(all_fields)

        if not clean_fields:
            return self.fallback_get_fields(model_name)
        return clean_fields

    def update_current_global_export(
        self, export: "odoo.model.ir_exports", old_fields: list[str], newer_fields: list[str]
    ):
        added = [field for field in old_fields if field not in newer_fields]
        removed = [field for field in newer_fields if field not in old_fields]

        if removed:
            to_unlink = self.env["ir.exports.line"].search([("export_id", "=", export.id), ("name", "in", removed)])
            to_unlink.unlink()
        if added:
            vals_list = [{"name": name, "export_id": export.id} for name in added]
            self.env["ir.exports.line"].create(vals_list)

    def fallback_get_fields(self, model_name: str, depth: int = FIELDS_RECURSION_LIMIT, prefix: str = "") -> list[str]:
        """
        Used to retrieve all fields that can be exported from a model
        :param model_name: Model to export field
        :param depth: Maximum recursion number
        ⚠ Be careful to not call it with an excessif number, field number grows exponentially
        (tested with purchase.order model with default depth, it gives 76 fields, in depth=1, it increases
        to 1800 fields.
        :param prefix: Must be left empty. Use for recursion call, to have a complete field's parent name.
        :return: Fields name to export
        """
        object_model = self.env[model_name]
        result = []

        fields = object_model.fields_get(
            attributes=["type", "required", "relation", "exportable"],
        )
        for field_name, field in fields.items():
            if field.get("exportable") and field_name not in EXCLUDED_FIELDS:
                full_name = f"{prefix}{field_name}" if not prefix else f"{prefix}/{field_name}"
                result.append(full_name)

                if depth > 0 and field.get("type") in ("many2one", "many2many"):
                    related_model = field.get("relation")
                    nested_fields = self.fallback_get_fields(related_model, depth=depth - 1, prefix=full_name)
                    result.extend(nested_fields)
        return result

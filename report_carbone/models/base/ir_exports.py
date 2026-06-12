from odoo import fields, models


class IrExportsCarbone(models.Model):
    _inherit = "ir.exports"

    is_global_export = fields.Boolean(string="Global Export")


class IrExportsLineCarbone(models.Model):
    _inherit = "ir.exports.line"

    field_label = fields.Char(string="Field label", help="Name render in model view", compute="_compute_field_label")

    def _get_fields_model_data(self, model_name: str):
        model = self.env[model_name]
        return model.fields_get(attributes=["string", "relation"])

    def _get_fields_model_data(self, model_name: str):
        model = self.env[model_name]
        return model.fields_get(attributes=["string", "relation"])

    def _get_field_label_recursive(self, field_path, current_model):
        """
        Recursively retrieves the label of a field for relations
        :param field_path: Field path (ex: 'company_id/name' ou 'partner_id/country_id/name')
        :param current_model: Current model name
        :return: Field label
        """
        path_parts = field_path.split("/")
        fields = self._get_fields_model_data(current_model)
        current_field = path_parts[0]

        field_info = fields.get(current_field)
        if not field_info:
            return field_path

        if len(path_parts) == 1:
            return field_info.get("string", current_field)

        relation_model = field_info.get("relation")
        if not relation_model:
            return field_path

        remaining_path = "/".join(path_parts[1:])
        return self._get_field_label_recursive(remaining_path, relation_model)

    def _compute_field_label(self):
        for rec in self:
            field_label = ""
            current_model = self.export_id.resource
            fields = self._get_fields_model_data(current_model)
            if rec.name and "/" in rec.name:
                field_label = self._get_field_label_recursive(rec.name, current_model)
            else:
                field_get_information_field = fields.get(rec.name)
                if field_get_information_field:
                    field_label = field_get_information_field.get("string")
            rec.field_label = field_label

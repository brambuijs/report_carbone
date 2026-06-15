from odoo import fields, models


class CarboneTranslateLine(models.Model):
    _name = "carbone.translate.line"
    _description = "Carbone Translate Line"
    _rec_name = "source"

    carbone_translate_id = fields.Many2one(
        "carbone.translate", string="Carbone Translate", required=True, ondelete="cascade"
    )
    source = fields.Text(string="Source term")
    value = fields.Text(string="Translation Value", default="")
    _sql_constraints = [
        (
            "source_value_uniq",
            "UNIQUE(source, value, carbone_translate_id)",
            "A report cannot have two translations for the same value.",
        )
    ]

    def write(self, vals):
        # We replace occurrences of the value 'False'
        # with a null string. Carbone does not interpret 'false' in translations.
        if "value" in vals and not vals.get("value"):
            vals["value"] = ""
        return super().write(vals)

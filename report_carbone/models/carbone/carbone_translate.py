from odoo import fields, models


class CarboneTranslate(models.Model):
    _name = "carbone.translate"
    _description = "Carbone Translate"
    _rec_name = "ir_actions_report_id"

    ir_actions_report_id = fields.Many2one(
        "ir.actions.report", string="Carbone Report", required=True, ondelete="cascade"
    )
    lang_id = fields.Many2one(
        "res.lang",
        string="Language",
        required=True,
    )
    carbone_translate_line_ids = fields.One2many(
        "carbone.translate.line", "carbone_translate_id", string="Translation lines"
    )
    _lang_report_uniq = models.Constraint(
        "UNIQUE(ir_actions_report_id, lang_id)",
        "A report cannot have two translations for the same language.",
    )

    def _create_translation_lines(
        self,
        carbone_translate_to_maj: "odoo.model.carbone_translate",
        translation_lines: "odoo.model.carbone_translate_line",
    ):
        existing_sources = carbone_translate_to_maj.mapped("carbone_translate_line_ids.source")
        lines = [
            {
                "source": current_translate_line.source,
                "value": "",
                "carbone_translate_id": carbone_translate_to_maj.id,
            }
            for current_translate_line in translation_lines
            if current_translate_line.source not in existing_sources
        ]
        self.env["carbone.translate.line"].create(lines)

    def button_create_update_copy_of_translate(self):
        self.ensure_one()
        create_vals = []

        report_translate_langs = self.ir_actions_report_id.carbone_translate_ids.mapped("lang_id")
        available_languages = self.ir_actions_report_id.lang_ids
        # If there is no language at all, we will create one, with the right keys.
        for lang in available_languages:
            if lang not in report_translate_langs:
                vals = {"lang_id": lang.id, "ir_actions_report_id": self.ir_actions_report_id.id}
                lines = [
                    (0, 0, {"source": translate_line.source, "value": ""})
                    for translate_line in self.carbone_translate_line_ids
                ]
                vals.update({"carbone_translate_line_ids": lines})
                create_vals.append(vals)
            else:
                carbone_translate_to_maj = self.ir_actions_report_id.carbone_translate_ids.filtered_domain(
                    [("lang_id", "=", lang.id)]
                )
                self._create_translation_lines(carbone_translate_to_maj, self.carbone_translate_line_ids)
        if create_vals:
            self.env["carbone.translate"].create(create_vals)

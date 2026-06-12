import pytz

from odoo import api, fields, models


class Base(models.AbstractModel):
    """The base model, which is implicitly inherited by all models."""

    _inherit = "base"

    carbone_default_currency_id = fields.Many2one(
        "res.currency", string="Default currency used in Carbone Report", compute="_compute_carbone_default_currency_id"
    )

    def _compute_carbone_default_currency_id(self):
        for rec in self:
            currency = self.env.user.company_id.currency_id
            if "currency_id" in rec._fields.keys():
                currency = rec.currency_id
            rec.carbone_default_currency_id = currency

    @api.model
    def _jsonify_value(self, field, value):
        """Overloading the OCA jsonifier library function :
        - Datetime fields are displayed directly with the time zone set in context.
        -The value of a Selection field's label is displayed, rather than the key stored in the database."""
        if value is False and field.type != "boolean":
            value = None
        elif field.type == "date":
            value = fields.Date.to_date(value).isoformat()
        elif field.type == "datetime":
            # Ensures value is a datetime
            value = fields.Datetime.to_datetime(value)
            expected_tz = self.env.context.get("tz") or self.env.user.tz
            tz_pytz = pytz.timezone(expected_tz) if expected_tz else pytz.utc
            value = pytz.utc.localize(value).astimezone(tz_pytz)
            value = value.isoformat()
        elif field.type in ("many2one", "reference"):
            value = value.display_name if value else None
        elif field.type in ("one2many", "many2many"):
            value = [v.display_name for v in value]
        elif field.type == "selection":
            selection_list = field._description_selection(self.env)
            value = dict(selection_list).get(value)
        return value

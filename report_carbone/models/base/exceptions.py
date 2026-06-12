from odoo.exceptions import UserError


class MissingApiKeyError(UserError):
    """Missing Carbone API Keys error.

    When you try to use Carbone API without correct key.
    """

    def __init__(self, message):
        super().__init__(message)

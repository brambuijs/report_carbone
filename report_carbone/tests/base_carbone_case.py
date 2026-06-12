class BaseCarboneCase:
    def _set_up_class(self):
        self.env["ir.config_parameter"].set_param("report-engine.api_endpoint", "https://account.carbone.io/api")

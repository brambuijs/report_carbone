# BB Open: report_carbone draait WAF-only tegen de self-hosted carbone-ee.
# Studio-JS blijft van de publieke CDN (self-contained, geen auth/CORP-issues);
# alleen origin/render wijzen naar onze on-prem carbone (browser-bereikbaar +
# server-side hairpin). Cloud-default (api.carbone.io) zou render naar de cloud
# lekken → "Invalid JWT audience" + lege studio. NIET terugzetten naar cloud.
STUDIO_JS_URL = "https://bin.carbone.io/studio/5.1.1/carbone-studio.min.js"
API_REPORT_URL = "https://carbone-wearefrank.bb-open.com"


def set_res_config_settings(env):
    env["ir.config_parameter"].set_param("report-engine.carbone_studio_url", API_REPORT_URL)
    env["ir.config_parameter"].set_param("report-engine.carbone_js_file_url", STUDIO_JS_URL)
    env["ir.config_parameter"].set_param("report-engine.is_stage_mode", True)

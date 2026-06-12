/** @odoo-module **/

import {registry} from "@web/core/registry";
import {loadJS} from "@web/core/assets";
import {rpc} from "@web/core/network/rpc";
import {user} from "@web/core/user";
import {formatJsonData} from "@report_carbone/js/report/copy_export_json";
import {FormController} from "@web/views/form/form_controller";
import {patch} from "@web/core/utils/patch";

// Bon, voici mon analyse complète et la correction. Le problème est clair :
//
//   1. openTemplateId → Tf.openTemplate({id}, true) sans retourner la promise
//   2. openTemplate est async : fetch versions → getSample → restoreSampleDataFromTemplate → setState → render → updatePreview
//   3. restoreSampleDataFromTemplate fait kf.setState({data: oldData, ...}) — écrase nos données
//   4. kf.setState déclenche le re-render de tous les subscribers → updatePreview → AbortError si un preview était déjà en cours
//   5. Aucun événement externe n'est émis quand openTemplate termine (options:updated n'est émis que par les interactions UI)
//
//   Le listener options:updated ne se déclenche jamais dans ce cas. Il faut une autre stratégie :

// ========== CONSTANTS ==========
//  /!\ You must leave a minimum of 450ms, because when creating a new report, you must allow
// Carbone time to deploy the new template, otherwise it cannot be displayed directly.
// Between two recording changes, a minimum of 250 ms is required.
const DEBOUNCE_DELAY = 450;
const DEFAULT_OPTIONS = ["{}", "{}", "en", "UTC", "USD", "", ""];
const CARBONE_STUDIO_SELECTOR = "carbone-studio";

// ========== DOM UTILITY==========
const LOADER_CLASS = "carbone-studio-loader";

class DOMUtils {
    static setDisplayNone(element) {
        if (!element) return;
        Object.assign(element.style, {
            display: "none",
            width: "0%",
            height: "0%",
        });
    }

    static showLoader(studio) {
        DOMUtils.removeLoader(studio);
        const parent = studio.parentElement;
        if (!parent) return null;
        if (!parent.style.position || parent.style.position === "static") {
            parent.style.position = "relative";
        }
        const overlay = document.createElement("div");
        overlay.className = LOADER_CLASS;
        Object.assign(overlay.style, {
            position: "absolute",
            inset: "0",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(255, 255, 255, 0.75)",
            zIndex: "1000",
        });
        overlay.innerHTML = `
            <div style="text-align:center">
                <div class="o_loading_indicator">
                    <img src="/web/static/img/spin.svg" alt="" style="width:48px;height:48px" />
                </div>
                <div style="margin-top:8px;font-size:14px;color:#666">
                    Loading Odoo data...
                </div>
            </div>`;
        parent.appendChild(overlay);
        return overlay;
    }

    static removeLoader(studio) {
        const parent = studio?.parentElement;
        if (!parent) return;
        parent.querySelectorAll(`.${LOADER_CLASS}`).forEach((el) => el.remove());
    }

    static waitForElement(selector, callback) {
        const element = document.querySelector(selector);
        if (element) {
            callback(element);
            return null;
        }

        const observer = new MutationObserver(() => {
            const found = document.querySelector(selector);
            if (found) {
                observer.disconnect();
                callback(found);
            }
        });

        observer.observe(document.body, {childList: true, subtree: true});
        return observer;
    }

    static improveOdooRecordView() {
        const node = document.querySelector("div.o_group.row.align-items-start");
        if (!node) return;

        node.childNodes.forEach((childNode) => {
            if (childNode.nodeName === "DIV") {
                childNode.classList.add("col-lg-12");
            }
        });
    }
}

// ========== CARBONE HANDLER==========
class CarboneStudioManager {
    constructor() {
        this.observer = null;
        this.studioURL = null;
        this.carboneToken = null;
        this.startIrReportId = null;
        this.isInitialized = false;
        this.debounceTimer = null;
        this.optionsList = [...DEFAULT_OPTIONS];
        this.currentStudio = null;
        this.isTemplateLoading = false;
    }

    async initialize() {
        if (!this.isInitialized) {
            this.studioURL = await CarboneAPI.importCarboneJs();
            this.carboneToken = await CarboneAPI.getCarboneApiKey();
            this.isInitialized = true;
        }
        return {
            studioURL: this.studioURL,
            carboneToken: this.carboneToken,
        };
    }

    /**
     * Safely close the current template, suppressing AbortError rejections
     * that the Carbone web component fires internally (from aborted fetch
     * calls in updatePreview) but does not handle itself.
     */
    safeCloseTemplate() {
        if (!this.currentStudio) return;
        const suppressAbort = (event) => {
            if (event.reason?.name === "AbortError") {
                event.preventDefault();
            }
        };
        window.addEventListener("unhandledrejection", suppressAbort);
        try {
            // BB Open patch: Carbone Studio v5.1.1 heeft GEEN closeTemplate (wel
            // close/destroy) → originele call faalde elke re-render → studio brak af.
            // Roep de method aan die de geladen studio-versie wel heeft.
            const s = this.currentStudio;
            if (typeof s.closeTemplate === "function") {
                s.closeTemplate();
            } else if (typeof s.close === "function") {
                s.close();
            } else if (typeof s.destroy === "function") {
                s.destroy();
            }
        } catch (e) {
            if (e.name !== "AbortError") {
                console.error("Error closing template:", e);
            }
        }
        // Keep the listener long enough for the async rejection to fire
        setTimeout(() => window.removeEventListener("unhandledrejection", suppressAbort), 500);
    }

    cleanup() {
        if (this.observer) {
            this.observer.disconnect();
            this.observer = null;
        }

        if (this.isTemplateLoading && this.currentStudio) {
            this.safeCloseTemplate();
            this.isTemplateLoading = false;
        }
    }

    resetOptions() {
        this.optionsList = [...DEFAULT_OPTIONS];
    }

    async refreshStudio(irReportId = null, services) {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        return new Promise((resolve) => {
            this.debounceTimer = setTimeout(async () => {
                try {
                    // Skip re-entrant refresh while a template load is mid-flight
                    // (the ~2s openTemplate window in safeOpenTemplate). A transient
                    // re-render here re-evaluates getIsCarboneReport()=false and hides
                    // the just-mounted studio ("appears then disappears" flicker).
                    if (this.isTemplateLoading && this.currentStudio) {
                        resolve();
                        return;
                    }

                    this.cleanup();
                    this.resetOptions();

                    const config = await this.initialize();
                    const isCarboneManager = await CarboneAPI.isCarboneManagerUser();
                    const isCarboneReport = this.getIsCarboneReport(services);

                    if (!isCarboneReport || !isCarboneManager) {
                        this.handleHideStudio(config);
                        resolve();
                        return;
                    }

                    if (irReportId) {
                        this.startIrReportId = irReportId;
                        const options = await CarboneAPI.getDefaultOptionParameter(irReportId);
                        if (options) {
                            this.optionsList = options;
                        }
                    }

                    this.observer = DOMUtils.waitForElement(CARBONE_STUDIO_SELECTOR, (studio) => {
                        this.setupStudio(studio, config);
                    });

                    resolve();
                } catch (error) {
                    console.error("Error refreshing Carbone Studio:", error);
                    this.isTemplateLoading = false;
                    resolve();
                }
            }, DEBOUNCE_DELAY);
        });
    }

    setupStudio(studio, config) {
        if (this.currentStudio && this.isTemplateLoading) {
            this.safeCloseTemplate();
        }

        this.currentStudio = studio;
        Object.assign(studio.style, {
            display: "",
            width: "100%",
            height: "100%",
        });
        DOMUtils.improveOdooRecordView();
        this.isTemplateLoading = true;
        this.launchCarbone(studio, config.studioURL, config.carboneToken);
        this.addStudioListeners(studio);
    }

    handleHideStudio(config) {
        DOMUtils.waitForElement(CARBONE_STUDIO_SELECTOR, (studio) => {
            if (!config.studioURL || !config.carboneToken) {
                DOMUtils.setDisplayNone(studio);
            }
        });
    }
    getIsCarboneReport(services) {
        try {
            const actionService = services.action;
            if (!actionService?.currentController?.action) {
                return false;
            }

            const currentController = actionService.currentController;
            this.startIrReportId = currentController.currentState?.resId;
            return currentController.action.context?.default_report_type === "carbone";
        } catch (error) {
            console.error("Error getting current ir.actions.report:", error);
            return false;
        }
    }

    async launchCarbone(studio, studioURL, carboneToken) {
        if (!studio || !studioURL || !carboneToken) {
            DOMUtils.setDisplayNone(studio);
            this.isTemplateLoading = false;   // niet vasthouden → refresh-guard deadlockt anders
            return false;
        }

        studio.setConfig({origin: studioURL, token: carboneToken, mode: "embedded-versioning"});

        const options = this.buildStudioOptions();
        const template = this.buildTemplateConfig();

        await this.safeOpenTemplate(studio, template, options);
        this.isTemplateLoading = false;

        return true;
    }

    buildStudioOptions() {
        if (!this.optionsList || this.optionsList.length < 5) {
            this.optionsList = [...DEFAULT_OPTIONS];
        }

        return {
            complement: JSON.parse(this.optionsList[0]),
            data: JSON.parse(this.optionsList[0]),
            translations: JSON.parse(this.optionsList[1]),
            lang: this.optionsList[2],
            timezone: this.optionsList[3],
            currencySource: this.optionsList[4],
            currencyTarget: this.optionsList[4],
        };
    }

    buildTemplateConfig() {
        const template = {templateId: this.optionsList[5]};
        const extensionName = this.optionsList[6];

        if (extensionName !== false) {
            template.extension = extensionName;
        }

        return template;
    }

    safeOpenTemplate(studio, template, options) {
        // openTemplateId() internally calls Tf.openTemplate() which is async,
        // but openTemplateId does NOT return the promise (fire-and-forget).
        // openTemplate fetches the saved "sample" from the Carbone backend
        // and calls restoreSampleDataFromTemplate(), which overwrites
        // kf.state.data with OLD saved data via kf.setState().
        //
        // No external event is emitted when openTemplate finishes
        // (options:updated is only emitted by UI interactions).
        //
        // Strategy: suppress the AbortError caused by the competing
        // updatePreview calls, show a loader, then re-apply our Odoo data
        // after a delay long enough for openTemplate to finish loading.
        const suppressAbort = (event) => {
            if (event.reason?.name === "AbortError") {
                event.preventDefault();
            }
        };
        window.addEventListener("unhandledrejection", suppressAbort);
        DOMUtils.showLoader(studio);

        try {
            studio.openTemplateId(template["templateId"]);
        } catch (e) {
            console.error("Error opening template:", e);
            DOMUtils.removeLoader(studio);
            window.removeEventListener("unhandledrejection", suppressAbort);
            return Promise.resolve();
        }

        // Wait for openTemplate's async work (getVersions + getSample +
        // restoreSampleDataFromTemplate + setState/render) to complete,
        // then overwrite with the correct Odoo record data.
        return new Promise((resolve) => {
            setTimeout(() => {
                studio.setRenderOptions(options);
                DOMUtils.removeLoader(studio);
                setTimeout(() => window.removeEventListener("unhandledrejection", suppressAbort), 2000);
                resolve();
            }, 2050);
        });
    }

    addStudioListeners(studio) {
        const events = {
            connected: "studio connected.",
            disconnected: "studio disconnected.",
            "options:updated": null,
        };

        Object.entries(events).forEach(([event, message]) => {
            studio.addEventListener(event, (e) => {
                if (message) {
                    console.log(message, e);
                } else {
                    console.log(e.detail);
                }
            });
        });
    }
}

// ========== API CARBONE ==========
class CarboneAPI {
    static async isCarboneManagerUser() {
        if (!user) return false;
        return await user.hasGroup("report_carbone.group_report_carbone_manager");
    }

    static async importCarboneJs() {
        try {
            const res = await rpc("/carbone_config/carbone_studio_params");
            await loadJS(res.js_url);
            return res.studio_url;
        } catch (e) {
            console.error(`Failed to launch Carbone Studio: ${e.message}`);
            return null;
        }
    }

    static async getCarboneApiKey() {
        try {
            const res = await rpc("/carbone_config/carbone_api_key", {});
            return res.token;
        } catch (e) {
            console.error("Failed to retrieve API key:", e);
            return null;
        }
    }

    static async getDefaultOptionParameter(irReportId) {
        try {
            const res = await rpc("/web/dataset/call_kw", {
                model: "ir.actions.report",
                method: "action_setup_carbone_studio_options",
                args: [[irReportId]],
                kwargs: {},
            });

            return [
                formatJsonData(res.context.json_data),
                formatJsonData(res.context.json_translate_data),
                res.context.lang,
                res.context.timezone,
                res.context.currency,
                res.context.template,
                res.context.extension,
            ];
        } catch (e) {
            console.error("Failed to retrieve options from backend:", e);
            return null;
        }
    }
}

// ========== PATCH FORM CONTROLLER ==========
patch(FormController.prototype, {
    // Allows you to systematically refresh the studio, either by scrolling through records using the arrows or
    // by switching back and forth between the list view.
    onWillLoadRoot(nextConfiguration) {
        super.onWillLoadRoot(...arguments);
        // Skip refresh during save — onRecordSaved will handle it after save completes
        if (!this._carboneIsSaving) {
            this.handleCarboneStudio(nextConfiguration.resId);
        }
    },

    async onPagerUpdate(params) {
        await super.onPagerUpdate(...arguments);
        this.handleCarboneStudio(this.model.root.resId);
    },

    async save(params) {
        this._carboneIsSaving = true;
        const result = await super.save(...arguments);
        this._carboneIsSaving = false;
        return result;
    },

    async onRecordSaved(record, changes) {
        await super.onRecordSaved(...arguments);
        this.handleCarboneStudio(this.model.root.resId);
    },

    handleCarboneStudio(resId) {
        const dynamicService = this.env.services.dynamic_element_service;
        const isCarbone = this.props.context.default_report_type === "carbone";

        if (!isCarbone) {
            this.waitForStudioThenRemove();
            return;
        }

        dynamicService?.refreshCarboneStudio(resId);
    },

    waitForStudioThenRemove() {
        DOMUtils.waitForElement(CARBONE_STUDIO_SELECTOR, (studio) => {
            DOMUtils.setDisplayNone(studio);
        });
    },
});

// ========== SERVICE DYNAMIC ELEMENT ==========
export const dynamicElementService = {
    dependencies: ["action"],
    start(env, services) {
        const manager = new CarboneStudioManager();

        async function refreshCarboneStudio(irReportId = null) {
            return await manager.refreshStudio(irReportId, services);
        }

        async function actionRefreshCarboneStudio() {
            await refreshCarboneStudio(manager.startIrReportId);
        }

        registry.category("actions").add("action_refresh_carbone_studio", actionRefreshCarboneStudio);

        return {refreshCarboneStudio};
    },
};

registry.category("services").add("dynamic_element_service", dynamicElementService);

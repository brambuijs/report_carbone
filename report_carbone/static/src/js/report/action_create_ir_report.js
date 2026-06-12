/** @odoo-module */
import {ListController} from "@web/views/list/list_controller";
import {registry} from "@web/core/registry";
import {listView} from "@web/views/list/list_view";
import {_t} from "@web/core/l10n/translation";
export class CarboneIrActionsReportController extends ListController {
    setup() {
        super.setup();
    }
    OnClickCreateReport() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "carbone.create.report.wizard",
            name: _t("Create new Carbone report"),
            view_mode: "form",
            view_type: "form",
            views: [[false, "form"]],
            target: "new",
            res_id: false,
        });
    }
}
CarboneIrActionsReportController.template = "carbone_report_button_on_tree_view.ListView.Buttons";
export const CustomCarboneIrActionsReportController = {
    ...listView,
    Controller: CarboneIrActionsReportController,
};
registry.category("views").add("carbone_report_button_in_tree", CustomCarboneIrActionsReportController);

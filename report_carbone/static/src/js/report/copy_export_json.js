/** @odoo-module **/

import {registry} from "@web/core/registry";

function copyJsonAction(env, action, notifyUser = true) {
    const notification = env.services.notification;

    const jsonData = action.context.json_data;

    if (!jsonData && notifyUser) {
        notification.add("No JSON given in context", {type: "warning"});
        return {type: "ir.actions.act_window_close"};
    }

    const formattedJson = formatJsonData(jsonData);

    copyJsonToTarget(formattedJson, notification, notifyUser);

    return {type: "ir.actions.act_window_close"};
}

registry.category("actions").add("copy_options_to_carbone", copyJsonAction);

export function formatJsonData(jsonData) {
    if (typeof jsonData === "string") {
        try {
            const parsed = JSON.parse(jsonData);
            return JSON.stringify(parsed, null, 4);
        } catch (e) {
            return jsonData;
        }
    } else if (typeof jsonData === "object") {
        return JSON.stringify(jsonData, null, 4);
    }
    return String(jsonData || "");
}

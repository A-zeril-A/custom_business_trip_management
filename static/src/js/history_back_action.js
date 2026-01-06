/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * History Back Action
 * Custom client action to navigate back in browser history.
 * This is used after "Save & Done" to prevent breadcrumb duplication.
 */
async function historyBackAction(env, action) {
    window.history.back();
    return true;
}

// Register the client action
registry.category("actions").add("history_back_action", historyBackAction);

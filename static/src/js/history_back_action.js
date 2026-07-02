/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * History Back Action
 *
 * Client action returned by `action_save_and_complete_form` after "Save & Done"
 * so the user is taken back to the previous breadcrumb instead of pushing a
 * duplicate record view onto the action stack.
 *
 * A function-based client action receives the global `env`, which (unlike a
 * component sub-env) does not expose `config`. The `historyBack` helper is
 * provided by the action service on the current controller's config, so we
 * reach it through `env.services.action` and fall back to `restore()` to remain
 * robust if no current controller config is available.
 */
async function historyBackAction(env) {
    const actionService = env.services.action;
    const controller = actionService.currentController;

    if (controller?.config?.historyBack) {
        controller.config.historyBack();
        return;
    }

    await actionService.restore();
}

// Register the client action
registry.category("actions").add("history_back_action", historyBackAction);

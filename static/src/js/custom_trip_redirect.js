/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Dialog component for Business Trip Form Selection
 */
export class BusinessTripFormSelectionDialog extends Component {
    static template = "custom_business_trip_management.BusinessTripFormSelectionDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        saleOrder: Object,
        onConfirm: Function,
    };

    onConfirm() {
        this.props.onConfirm();
        this.props.close();
    }

    onCancel() {
        this.props.close();
    }
}

/**
 * Custom List Controller for Business Trip Redirect
 * Handles row click events to show a dialog and redirect to create new trip form
 */
export class CustomTripListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dialogService = useService("dialog");
        this.actionService = useService("action");
    }

    /**
     * Handle row click event
     * @param {Object} record - The clicked record
     */
    async onRecordClick(record) {
        const recordId = record.resId;
        if (!recordId) {
            return;
        }

        // Fetch sale order data
        const saleResult = await this.orm.read("sale.order", [recordId], [
            "name",
            "partner_id",
            "amount_total",
        ]);

        if (saleResult && saleResult.length > 0) {
            const saleOrder = {
                name: saleResult[0].name || "",
                partner_id: saleResult[0].partner_id || [0, ""],
                amount_total: saleResult[0].amount_total || 0.0,
            };

            // Show dialog
            this.dialogService.add(BusinessTripFormSelectionDialog, {
                saleOrder: saleOrder,
                onConfirm: () => {
                    // Redirect to create a new form
                    window.location.href = "/business_trip/new/" + recordId;
                },
            });
        }
    }

    /**
     * Override openRecord to intercept row clicks
     * @param {Object} record - The record being opened
     */
    async openRecord(record) {
        await this.onRecordClick(record);
    }
}

// Register the custom list view
export const customTripRedirectView = {
    ...listView,
    Controller: CustomTripListController,
};

registry.category("views").add("custom_trip_redirect", customTripRedirectView);

/**
 * Business Trip Redirect Action
 * Redirects users to different views based on their role
 */
async function businessTripRedirectAction(env, action) {
    const orm = env.services.orm;
    const actionService = env.services.action;

    try {
        // Check if user is HR manager
        const isManager = await orm.call("res.users", "has_group", [
            "hr.group_hr_manager",
        ]);

        if (isManager) {
            // Redirect managers to admin dashboard
            await actionService.doAction(
                "custom_business_trip_management.action_business_trip_dashboard"
            );
        } else {
            // Redirect employees to business trip form request
            await actionService.doAction(
                "custom_business_trip_management.action_business_trip_form_request"
            );
        }
    } catch (error) {
        console.error("Error in business trip redirect:", error);
        // Fallback to form request action
        await actionService.doAction(
            "custom_business_trip_management.action_business_trip_form_request"
        );
    }

    return true;
}

// Register the client action
registry
    .category("actions")
    .add("business_trip_redirect", businessTripRedirectAction);

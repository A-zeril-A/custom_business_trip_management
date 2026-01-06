/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

/**
 * Custom List Controller for Trip Redirect
 * Redirects row clicks to the business trip start page
 */
export class CustomTripController extends ListController {
    /**
     * Override openRecord to redirect to business trip start page
     * @param {Object} record - The record being opened
     */
    async openRecord(record) {
        const recordId = record.resId;
        if (recordId) {
            window.location.href = "/business_trip/start/" + recordId;
        }
    }
}

// Register the custom list view
export const customTripRedirectListView = {
    ...listView,
    Controller: CustomTripController,
};

// Note: This view uses the same key as custom_trip_redirect.js
// If you need both, rename one of them
registry.category("views").add("custom_trip_redirect_list", customTripRedirectListView);

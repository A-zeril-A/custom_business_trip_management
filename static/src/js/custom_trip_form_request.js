/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Dialog component for Business Trip Request Type Selection
 */
export class BusinessTripRequestTypeDialog extends Component {
    static template = "custom_business_trip_management.BusinessTripRequestTypeDialog";
    static components = { Dialog };
    static props = {
        close: Function,
    };

    onWithQuotation() {
        this.props.close();
        window.location.href = "/business_trip/quotation_list";
    }

    onStandalone() {
        this.props.close();
        window.location.href = "/business_trip/create_standalone";
    }

    onCancel() {
        this.props.close();
    }
}

/**
 * Custom List Controller for My Business Trip Forms
 * Adds a "Create New Request" button that opens a dialog to choose request type
 */
export class MyBusinessTripFormsController extends ListController {
    setup() {
        super.setup();
        this.dialogService = useService("dialog");
    }

    /**
     * Show dialog to select request type (with quotation or standalone)
     */
    showRequestTypeDialog() {
        this.dialogService.add(BusinessTripRequestTypeDialog, {});
    }
}

// Patch the controller to add the button action
MyBusinessTripFormsController.template = "custom_business_trip_management.MyBusinessTripFormsListView";

// Register the custom list view
export const myBusinessTripFormsView = {
    ...listView,
    Controller: MyBusinessTripFormsController,
    buttonTemplate: "custom_business_trip_management.MyBusinessTripFormsButtons",
};

registry.category("views").add("my_business_trip_forms_view", myBusinessTripFormsView);

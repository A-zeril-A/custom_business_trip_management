/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { Many2ManyBinaryField } from "@web/views/fields/many2many_binary/many2many_binary_field";
import { _t } from "@web/core/l10n/translation";

/**
 * Patch FormController to track upload status for expense submission wizard.
 * This enhances the form controller to manage upload state and button states
 * specifically for the business trip expense submission wizard.
 */
patch(FormController.prototype, {
    setup() {
        super.setup();
        this._isExpenseWizard = false;
        this._uploadCounter = 0;
    },

    /**
     * Check if current form is the expense wizard
     * @returns {boolean}
     */
    _checkIsExpenseWizard() {
        return this.props.resModel === "business.trip.expense.submission.wizard";
    },

    /**
     * Update upload status in the wizard
     * @param {boolean} isUploading - Whether upload is in progress
     */
    async _updateUploadStatus(isUploading) {
        if (!this._checkIsExpenseWizard()) return;
        
        const record = this.model.root;
        if (record) {
            try {
                await record.update({ is_uploading: isUploading });
            } catch (e) {
                console.warn("Could not update upload status:", e);
            }
        }
    },

    /**
     * Handle file upload start
     */
    _onUploadStart() {
        if (this._checkIsExpenseWizard()) {
            this._uploadCounter++;
            this._updateUploadStatus(true);
            console.log("Upload started, counter:", this._uploadCounter);
        }
    },

    /**
     * Handle file upload complete
     */
    _onUploadComplete() {
        if (this._checkIsExpenseWizard()) {
            this._uploadCounter = Math.max(0, this._uploadCounter - 1);
            if (this._uploadCounter === 0) {
                this._updateUploadStatus(false);
                console.log("All uploads completed");
            }
        }
    },
});

/**
 * Patch Many2ManyBinaryField to track uploads for expense wizard.
 * This adds upload tracking callbacks to the file upload field
 * used in the expense submission process.
 */
patch(Many2ManyBinaryField.prototype, {
    /**
     * Check if this field is in the expense wizard
     * @returns {boolean}
     */
    _isExpenseWizardField() {
        return this.props.record?.resModel === "business.trip.expense.submission.wizard";
    },

    /**
     * Notify controller of upload start
     */
    _notifyUploadStart() {
        // In OWL, we need to find the controller differently
        // For now, we use a simple approach
        if (this._isExpenseWizardField()) {
            const controller = this.env?.config?.Controller;
            if (controller && controller._onUploadStart) {
                controller._onUploadStart();
            }
        }
    },

    /**
     * Notify controller of upload complete
     */
    _notifyUploadComplete() {
        if (this._isExpenseWizardField()) {
            const controller = this.env?.config?.Controller;
            if (controller && controller._onUploadComplete) {
                controller._onUploadComplete();
            }
        }
    },

    /**
     * Override onFileUploaded to add tracking
     * @param {Object} info - Upload info
     */
    async onFileUploaded(info) {
        if (this._isExpenseWizardField()) {
            this._notifyUploadStart();
        }
        
        try {
            const result = await super.onFileUploaded(info);
            if (this._isExpenseWizardField()) {
                this._notifyUploadComplete();
            }
            return result;
        } catch (error) {
            if (this._isExpenseWizardField()) {
                this._notifyUploadComplete();
            }
            throw error;
        }
    },
});

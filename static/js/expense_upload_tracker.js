odoo.define('custom_business_trip_management.expense_upload_tracker', function (require) {
'use strict';

var FormController = require('web.FormController');
var BasicFields = require('web.basic_fields');
var core = require('web.core');
var _t = core._t;

/**
 * Enhanced FormController for expense submission wizard
 */
FormController.include({
    init: function () {
        this._super.apply(this, arguments);
        this._isExpenseWizard = this.modelName === 'business.trip.expense.submission.wizard';
        this._uploadCounter = 0;
    },

    /**
     * Update upload status in the wizard
     */
    _updateUploadStatus: function (isUploading) {
        if (this._isExpenseWizard && this.model && this.model.localData) {
            var record = this.model.localData[this.handle];
            if (record) {
                // Update the is_uploading field
                this.model.notifyChanges(this.handle, {
                    is_uploading: isUploading
                }).then(() => {
                    // Trigger onchange to recompute can_submit
                    this.model.notifyChanges(this.handle, {}, {
                        viewType: 'form'
                    });
                });
            }
        }
    },

    /**
     * Handle file upload start
     */
    _onUploadStart: function () {
        if (this._isExpenseWizard) {
            this._uploadCounter++;
            this._updateUploadStatus(true);
            console.log('Upload started, counter:', this._uploadCounter);
        }
    },

    /**
     * Handle file upload complete
     */
    _onUploadComplete: function () {
        if (this._isExpenseWizard) {
            this._uploadCounter = Math.max(0, this._uploadCounter - 1);
            if (this._uploadCounter === 0) {
                this._updateUploadStatus(false);
                console.log('All uploads completed');
            }
        }
    },

    /**
     * Override renderButtons to disable submit during upload
     */
    renderButtons: function ($node) {
        var result = this._super.apply(this, arguments);
        if (this._isExpenseWizard) {
            this._updateButtonStates();
        }
        return result;
    },

    /**
     * Update button states - removed manual disabled control to let Odoo attrs handle it
     */
    _updateButtonStates: function () {
        if (this.$buttons && this._isExpenseWizard) {
            var $submitBtn = this.$buttons.find('.btn-primary');
            var record = this.model.localData[this.handle];
            
            if (record && record.data) {
                var isUploading = record.data.is_uploading;
                
                // Only update text, let Odoo attrs handle disabled state
                if (isUploading) {
                    $submitBtn.text(_t('Uploading...'));
                } else {
                    $submitBtn.text(_t('Submit Expenses'));
                }
            }
        }
    },

    /**
     * Override update to refresh button states
     */
    update: function () {
        var result = this._super.apply(this, arguments);
        if (this._isExpenseWizard) {
            this._updateButtonStates();
        }
        return result;
    }
});

/**
 * Enhanced Many2ManyBinaryUpload field with upload tracking
 */
var FieldMany2ManyBinaryUploadTracked = BasicFields.FieldMany2ManyBinaryUpload.extend({
    
    init: function () {
        this._super.apply(this, arguments);
        this._isExpenseWizard = this.model === 'business.trip.expense.submission.wizard';
    },

    /**
     * Override _uploadFiles to add tracking
     */
    _uploadFiles: function (files) {
        if (this._isExpenseWizard) {
            // Notify upload start for each file
            for (var i = 0; i < files.length; i++) {
                this._notifyUploadStart();
            }
        }
        
        var result = this._super.apply(this, arguments);
        
        // Handle upload completion
        if (this._isExpenseWizard && result && result.then) {
            result.then((res) => {
                // Notify upload complete for each file
                for (var i = 0; i < files.length; i++) {
                    this._notifyUploadComplete();
                }
                return res;
            }).catch((err) => {
                // Notify upload complete even on error
                for (var i = 0; i < files.length; i++) {
                    this._notifyUploadComplete();
                }
                throw err;
            });
        }
        
        return result;
    },

    /**
     * Notify parent controller of upload start
     */
    _notifyUploadStart: function () {
        var controller = this.getParent();
        while (controller && !controller._onUploadStart) {
            controller = controller.getParent();
        }
        if (controller && controller._onUploadStart) {
            controller._onUploadStart();
        }
    },

    /**
     * Notify parent controller of upload complete
     */
    _notifyUploadComplete: function () {
        var controller = this.getParent();
        while (controller && !controller._onUploadComplete) {
            controller = controller.getParent();
        }
        if (controller && controller._onUploadComplete) {
            controller._onUploadComplete();
        }
    },

    /**
     * Override file deletion to trigger recomputation
     */
    _onDeleteAttachment: function (ev) {
        var result = this._super.apply(this, arguments);
        
        if (this._isExpenseWizard) {
            // Trigger field change to recompute can_submit
            this._setValue(this.value);
        }
        
        return result;
    }
});

// Register the enhanced field
BasicFields.FieldMany2ManyBinaryUpload = FieldMany2ManyBinaryUploadTracked;

return {
    FormController: FormController,
    FieldMany2ManyBinaryUploadTracked: FieldMany2ManyBinaryUploadTracked
};

}); 
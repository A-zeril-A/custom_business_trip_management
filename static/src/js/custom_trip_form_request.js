odoo.define('custom_business_trip_management.form_request', function (require) {
    "use strict";

    const ListController = require('web.ListController');
    const ListView = require('web.ListView');
    const viewRegistry = require('web.view_registry');
    const core = require('web.core');
    const session = require('web.session');

    const MyBusinessTripFormsController = ListController.extend({
        buttons_template: 'FormioMyFormsList.buttons',
        
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            if (!this.$buttons) { return; }
            
            const self = this;
            this.$buttons.on('click', '.o_list_button_create_request', function () {
                // Show the type selection popup
                self._showRequestTypeDialog();
            });
        },
        
        _showRequestTypeDialog: function() {
            const self = this;
            const $dialog = $(core.qweb.render('BusinessTripRequestTypeDialog', {}));
            
            $dialog.appendTo('body').modal();
            
            // Set event handlers
            $dialog.find('.btn-with-quotation').click(function() {
                $dialog.modal('hide');
                
                // استفاده از دو روش برای هدایت به لیست کوتیشن‌ها
                // روش اول: استفاده از مسیر کنترلر (ساده‌تر و مطمئن‌تر)
                window.location.href = '/business_trip/quotation_list';
            });
            
            $dialog.find('.btn-standalone').click(function() {
                $dialog.modal('hide');
                // Redirect to create standalone form
                window.location.href = '/business_trip/create_standalone';
            });
        }
    });

    const MyBusinessTripFormsView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: MyBusinessTripFormsController,
        }),
    });

    viewRegistry.add('my_business_trip_forms_view', MyBusinessTripFormsView);
}); 
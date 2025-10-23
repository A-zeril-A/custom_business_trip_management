odoo.define('custom_business_trip_management.custom_trip_redirect', function (require) {
    "use strict";

    const ListController = require('web.ListController');
    const ListView = require('web.ListView');
    const viewRegistry = require('web.view_registry');
    const core = require('web.core');
    const session = require('web.session');
    const ajax = require('web.ajax');
    const rpc = require('web.rpc');
    const Dialog = require('web.Dialog');
    const AbstractAction = require('web.AbstractAction');

    const CustomTripListController = ListController.extend({
        events: _.extend({}, ListController.prototype.events, {
            'click .o_list_view tbody tr': '_onRowClicked',
        }),

        _onRowClicked: function (event) {
            event.preventDefault();
            event.stopPropagation();

            const record = this.model.get(event.currentTarget.dataset.id);
            if (!record || !record.data || !record.data.id) {
                return;
            }

            const self = this;
            this._rpc({
                model: 'sale.order',
                method: 'read',
                args: [[record.data.id], ['name', 'partner_id', 'amount_total']],
            }).then(function (saleResult) {
                if (saleResult && saleResult.length > 0) {
                    // RPC call to fetch existing forms is removed.
                    // Show selection popup (now more of a confirmation popup)
                    var $dialog = $(core.qweb.render('BusinessTripFormSelectionDialog', {
                        sale_order: {
                            name: saleResult[0].name || '',
                            partner_id: saleResult[0].partner_id || [0, ''],
                            amount_total: saleResult[0].amount_total || 0.0
                        },
                        // 'forms' array is no longer passed
                    }));

                    $dialog.appendTo('body').modal();

                    // Set popup events
                    $dialog.find('.o_confirm').click(function () {
                        $dialog.modal('hide');
                        // Always redirect to create a new form
                        window.location.href = '/business_trip/new/' + record.data.id;
                    });

                    $dialog.find('.o_cancel').click(function () {
                        $dialog.modal('hide');
                    });
                }
            });
        },
    });

    const CustomTripListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: CustomTripListController,
        }),
    });

    viewRegistry.add('custom_trip_redirect', CustomTripListView);

    var BusinessTripRedirect = AbstractAction.extend({
        template: 'BusinessTripRedirect',
        
        init: function (parent, action) {
            this._super.apply(this, arguments);
            this.action = action;
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._redirectBasedOnRole();
            });
        },

        _redirectBasedOnRole: function () {
            var self = this;
            
            // Check user role and redirect accordingly
            rpc.query({
                model: 'res.users',
                method: 'has_group',
                args: ['hr.group_hr_manager']
            }).then(function (is_manager) {
                if (is_manager) {
                    // Redirect managers to admin dashboard
                    self.do_action('custom_business_trip_management.action_business_trip_dashboard');
                } else {
                    // Redirect employees to business trip form
                    self._redirectToBusinessTripForm();
                }
            });
        },

        _redirectToBusinessTripForm: function () {
            var self = this;
            // For employees, redirect to the form view
            this.do_action('custom_business_trip_management.action_business_trip_form_request');
        }
    });

    core.action_registry.add('business_trip_redirect', BusinessTripRedirect);

    return BusinessTripRedirect;
});

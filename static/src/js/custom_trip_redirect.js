odoo.define('custom_business_trip_management.custom_trip_redirect', function (require) {
    "use strict";

    const ListController = require('web.ListController');
    const ListView = require('web.ListView');
    const viewRegistry = require('web.view_registry');
    const core = require('web.core');
    const session = require('web.session');

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
                    // Get forms related to this quotation
                    self._rpc({
                        model: 'formio.form',
                        method: 'search_read',
                        args: [[['sale_order_id', '=', record.data.id]], ['id', 'name', 'create_date', 'state']],
                    }).then(function (formResult) {
                        // Show selection popup
                        var $dialog = $(core.qweb.render('BusinessTripFormSelectionDialog', {
                            sale_order: {
                                name: saleResult[0].name || '',
                                partner_id: saleResult[0].partner_id || [0, ''],
                                amount_total: saleResult[0].amount_total || 0.0
                            },
                            forms: formResult || []
                        }));

                        $dialog.appendTo('body').modal();

                        // Set popup events
                        $dialog.find('.o_confirm').click(function () {
                            var selectedFormId = $dialog.find('select[name="form_selection"]').val();
                            
                            if (selectedFormId === 'new') {
                                $dialog.modal('hide');
                                // استفاده از مسیر جدید که همیشه یک فرم جدید می‌سازد
                                window.location.href = '/business_trip/new/' + record.data.id;
                            } else {
                                // Open selected form
                                $dialog.modal('hide');
                                self.do_action({
                                    type: 'ir.actions.act_window',
                                    name: 'Business Trip Form',
                                    res_model: 'formio.form',
                                    view_mode: 'form',
                                    views: [[false, 'formio_form']],
                                    res_id: parseInt(selectedFormId),
                                });
                            }
                        });

                        $dialog.find('.o_cancel').click(function () {
                            $dialog.modal('hide');
                        });
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
});

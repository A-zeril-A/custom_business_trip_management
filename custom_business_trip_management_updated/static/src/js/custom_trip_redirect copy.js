odoo.define('custom_business_trip_management.custom_trip_redirect', function (require) {
    "use strict";

    var ListController = require('web.ListController');
    var ListView = require('web.ListView');
    var viewRegistry = require('web.view_registry');
    var core = require('web.core');
    var QWeb = core.qweb;

    var CustomTripListController = ListController.extend({
        events: _.extend({}, ListController.prototype.events, {
            'click .o_list_view tbody tr': '_onRowClicked',
        }),

        _onRowClicked: function (event) {
            var self = this;
            var record = this.model.get(event.currentTarget.dataset.id);
            
            // دریافت اطلاعات کوتیشن و فرم‌های مرتبط
            this._rpc({
                model: 'sale.order',
                method: 'read',
                args: [[record.data.id], ['name', 'partner_id']],
            }).then(function (saleResult) {
                if (saleResult && saleResult.length > 0) {
                    // دریافت فرم‌های مرتبط با این کوتیشن
                    self._rpc({
                        model: 'formio.form',
                        method: 'search_read',
                        args: [[['sale_order_id', '=', record.data.id]], ['id', 'name', 'create_date']],
                    }).then(function (formResult) {
                        // نمایش پاپ‌آپ انتخاب
                        var $dialog = $(QWeb.render('BusinessTripFormSelectionDialog', {
                            sale_order: saleResult[0],
                            forms: formResult,
                        }));

                        $dialog.appendTo('body').modal();

                        // تنظیم رویدادهای پاپ‌آپ
                        $dialog.find('.o_confirm').click(function () {
                            var selectedFormId = $dialog.find('select[name="form_selection"]').val();
                            
                            if (selectedFormId === 'new') {
                                // ساخت فرم جدید
                                window.location.href = '/business_trip/start/' + record.data.id;
                            } else {
                                // باز کردن فرم انتخاب شده
                                self.do_action({
                                    type: 'ir.actions.act_window',
                                    name: 'Business Trip Form',
                                    res_model: 'formio.form',
                                    view_mode: 'form',
                                    views: [[false, 'formio_form']],
                                    res_id: parseInt(selectedFormId),
                                });
                            }
                            $dialog.modal('hide');
                        });

                        $dialog.find('.o_cancel').click(function () {
                            $dialog.modal('hide');
                        });
                    });
                }
            });
        }
    });

    var CustomTripListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: CustomTripListController,
        }),
    });

    viewRegistry.add('custom_trip_redirect', CustomTripListView);
});

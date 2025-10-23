odoo.define('custom_business_trip_management.trip_redirect', function (require) {
    'use strict';

    const ListController = require('web.ListController');
    const ListView = require('web.ListView');
    const viewRegistry = require('web.view_registry');

    const CustomTripController = ListController.extend({
        _onRowClicked: function (event) {
            event.preventDefault();
            event.stopPropagation();

            const record = this._getRecord(event);
            if (record && record.data && record.data.id) {
                window.location.href = '/business_trip/start/' + record.data.id;
            }
        }
    });

    const CustomTripListView = ListView.extend({
        config: Object.assign({}, ListView.prototype.config, {
            Controller: CustomTripController,
        }),
    });

    viewRegistry.add('custom_trip_redirect', CustomTripListView);
});

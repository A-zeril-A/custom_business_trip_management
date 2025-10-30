odoo.define('custom_business_trip_management.HistoryBackAction', function (require) {
    "use strict";

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    /**
     * Custom client action to navigate back in browser history
     * This is used after "Save & Done" to prevent breadcrumb duplication
     */
    var HistoryBackAction = AbstractAction.extend({
        start: function () {
            // Navigate back in browser history
            window.history.back();
            return this._super.apply(this, arguments);
        },
    });

    core.action_registry.add('history_back_action', HistoryBackAction);

    return HistoryBackAction;
});


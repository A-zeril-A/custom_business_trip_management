# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, date, timedelta
from odoo.exceptions import ValidationError, UserError
from dateutil.relativedelta import relativedelta
import logging
import json
import ast
import werkzeug
from odoo.exceptions import AccessError
from odoo.tools import html_sanitize
import base64
import io
import pytz
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)
# Set logging level to INFO for this module to ensure all our custom logs are visible
logging.getLogger('odoo.addons.custom_business_trip_management.models.formio_form_inherit').setLevel(logging.INFO)

# Define for compatibility with other modules
STATE_PENDING = 'DRAFT'  # Remap PENDING to DRAFT since we removed PENDING

class FormioForm(models.Model):
    _inherit = 'formio.form'
    # _name = 'formio.form'
    # _inherit = ['formio.form', 'mail.template.mixin']

    # --- LINK TO NEW BUSINESS TRIP MODEL ---
    business_trip_id = fields.Many2one('business.trip', string='Business Trip', ondelete='set null', readonly=True)

    def _filter_new_records(self):
        return self.filtered(lambda r: r.id and isinstance(r.id, int))

    # Personal information fields are now stored in business.trip.data model
    # We keep only UI-specific and business logic fields in this model
    # --- The following fields are being moved to business.trip model ---
    # trip_status, user_id, manager_id, manager_comments, etc.

    display_state = fields.Char(string='Display State', compute='_compute_display_fields')

    # Approvers and dates
    user_id = fields.Many2one('res.users', string='Employee', default=lambda self: self.env.user.id, tracking=True, readonly=True)
    # manager_id is moved
    # MOVED to business.trip or DEPRECATED
    # manager_approval_date = fields.Datetime(string='Manager Initial Approval Date', tracking=False, copy=False)
    # manager_comments is moved

    # Fields related to organizer approval of expenses
    # MOVED to business.trip or DEPRECATED
    # organizer_approval_date = fields.Datetime(string='Organizer Approval Date', tracking=True, copy=False)
    # organizer_expense_comments = fields.Text(string='Organizer Comments on Expenses', tracking=True)

    # Organizer related fields - MOVED to business.trip
    # organizer_id = fields.Many2one(...)
    # manager_max_budget = fields.Monetary(...)
    # temp_manager_max_budget = fields.Monetary(...)
    # organizer_planned_cost = fields.Monetary(...)
    # organizer_trip_plan_details = fields.Text(...)
    # structured_plan_items_json = fields.Text(...)
    # organizer_attachments_ids = fields.Many2many(...)
    # organizer_submission_date = fields.Datetime(...)
    # organizer_confirmed_by = fields.Many2one(...)
    # organizer_confirmation_date = fields.Datetime(...)
    # organizer_comments_to_manager = fields.Text(...)
    # manager_plan_review_comments_to_organizer = fields.Text(...)
    # plan_approval_date = fields.Datetime(...)
    # internal_manager_organizer_notes = fields.Text(...)

    # Link to project and task - MOVED to business.trip
    # business_trip_project_id = fields.Many2one(...)
    # business_trip_task_id = fields.Many2one(...)

    # MOVED to business.trip or DEPRECATED
    # Estimation fields (Legacy or for initial quick estimate by manager if needed)
    # estimated_by = fields.Many2one('res.users', string='Cost Estimated By (Old)', tracking=True, copy=False)
    # estimation_date = fields.Datetime(string='Estimation Date (Old)', tracking=True, copy=False)
    # estimation_comments = fields.Text(string='Estimation Notes (Old)', tracking=True)

    # Return comments (We now have specific comment fields, this might be deprecated or repurposed)
    # return_comments = fields.Text(string='Return Comments (Legacy/General)', tracking=True, help="General return comments, consider using specific fields like manager_comments or manager_plan_review_comments_to_organizer")
    # expense_return_comments = fields.Text(string='Expense Return Comments to Employee', tracking=True, help="Comments from manager/finance to employee for returning expense report.")

    # Travel tracking - MOVED to business.trip model
    # actual_start_date = fields.Datetime(string='Actual Start Date', tracking=True, copy=False)
    # actual_end_date = fields.Datetime(string='Actual End Date', tracking=True, copy=False)
    travel_duration = fields.Float(string='Trip Duration', compute='_compute_travel_dates', store=False, help="Total trip duration. For day trips, shows number of days. For hourly trips, shows hours.")

    # New fields for display in views
    travel_duration_days = fields.Integer(string='Trip Duration (Days)', compute='_compute_travel_duration_parts', store=False, help="Trip duration in days (for multi-day trips)")
    travel_duration_hours = fields.Float(string='Trip Duration (Hours)', compute='_compute_travel_duration_parts', store=False, help="Trip duration in hours (for hourly trips)")
    travel_dates_display = fields.Char(string='Planned Travel Dates', compute='_compute_planned_travel_dates_display', store=False, help="Shows formatted travel dates")

    # ADDED: New field for actual trip duration in days
    actual_travel_duration_days = fields.Integer(string='Actual Trip Duration (Days)', compute='_compute_actual_travel_duration_days', store=False, help="Actual trip duration in days.")

    # ADDED: New fields for improved display of actual dates and duration
    actual_duration_display = fields.Char(string="Actual Duration", compute='_compute_actual_duration_and_dates_display', store=False)
    actual_start_date_display = fields.Char(string="Actual Start Date (Display)", compute='_compute_actual_duration_and_dates_display', store=False)
    actual_end_date_display = fields.Char(string="Actual End Date (Display)", compute='_compute_actual_duration_and_dates_display', store=False)

    # Transportation fields
    use_rental_car = fields.Boolean(string='Use Rental Car', related='business_trip_id.business_trip_data_id.use_rental_car', readonly=True, store=False)
    use_company_car = fields.Boolean(string='Use Company Car', related='business_trip_id.business_trip_data_id.use_company_car', readonly=True, store=False)
    use_personal_car = fields.Boolean(string='Use Personal Car', related='business_trip_id.business_trip_data_id.use_personal_car', readonly=True, store=False)
    use_train = fields.Boolean(string='Use Train', related='business_trip_id.business_trip_data_id.use_train', readonly=True, store=False)
    use_airplane = fields.Boolean(string='Use Airplane', related='business_trip_id.business_trip_data_id.use_airplane', readonly=True, store=False)
    use_bus = fields.Boolean(string='Use Bus', related='business_trip_id.business_trip_data_id.use_bus', readonly=True, store=False)

    # Return transportation fields
    use_return_rental_car = fields.Boolean(string='Use Return Rental Car', related='business_trip_id.business_trip_data_id.use_return_rental_car', readonly=True, store=False)
    use_return_company_car = fields.Boolean(string='Use Return Company Car', related='business_trip_id.business_trip_data_id.use_return_company_car', readonly=True, store=False)
    use_return_personal_car = fields.Boolean(string='Use Return Personal Car', related='business_trip_id.business_trip_data_id.use_return_personal_car', readonly=True, store=False)
    use_return_train = fields.Boolean(string='Use Return Train', related='business_trip_id.business_trip_data_id.use_return_train', readonly=True, store=False)
    use_return_airplane = fields.Boolean(string='Use Return Airplane', related='business_trip_id.business_trip_data_id.use_return_airplane', readonly=True, store=False)
    use_return_bus = fields.Boolean(string='Use Return Bus', related='business_trip_id.business_trip_data_id.use_return_bus', readonly=True, store=False)


    # Related fields to business.trip.data - for display purposes
    destination = fields.Char(string='Destination', related='business_trip_id.business_trip_data_id.destination', readonly=True, store=False)
    purpose = fields.Char(string='Purpose', related='business_trip_id.business_trip_data_id.purpose', store=False, readonly=True)
    travel_start_date = fields.Date(string='Start Date', related='business_trip_id.business_trip_data_id.travel_start_date', readonly=True, store=False)
    travel_end_date = fields.Date(string='End Date', related='business_trip_id.business_trip_data_id.travel_end_date', readonly=True, store=False)
    trip_type = fields.Selection([
        ('one_way', 'One-way Trip'),
        ('two_way', 'Round Trip')
    ], string='Trip Type', compute='_compute_trip_related_fields', store=False)

    @api.depends('business_trip_data_id.trip_type')
    def _compute_trip_related_fields(self):
        """Compute trip_type from business.trip.data model"""
        for record in self._filter_new_records():
            # Find linked business.trip.data record
            trip_data = self.env['business.trip.data'].search([('form_id', '=', record.id)], limit=1)

            if trip_data:
                # Map trip_type from business.trip.data to formio.form
                btd_trip_type_from_form = trip_data.trip_type # This is the selection from the form ('oneWay', 'twoWay')

                # Direct mapping if the values are compatible
                if btd_trip_type_from_form == 'oneWay':
                    record.trip_type = 'one_way'
                elif btd_trip_type_from_form == 'twoWay':
                    record.trip_type = 'two_way'
                else:
                    # Handle cases where trip_data.trip_type might be from the other selection
                    # or if it's not set, default to False or a specific value.
                    # This part might need adjustment based on how trip_data.trip_type is truly populated.
                    # For now, if it's not 'oneWay' or 'twoWay' from BTD, set to False.
                    record.trip_type = False
                _logger.info(f"Mapped BTD trip_type '{btd_trip_type_from_form}' to formio.form trip_type '{record.trip_type}' for form {record.id}")
            else:
                record.trip_type = False
        # For new records that don't have an ID yet
        for record in self.filtered(lambda r: not (r.id and isinstance(r.id, int))):
            record.trip_type = False

    # Submission tracking - MOVED to business.trip
    # submission_date = fields.Datetime(string='Employee Initial Submission Date', tracking=True, copy=False)

    # Cancellation tracking
    # MOVED to business.trip or DEPRECATED
    # cancellation_date = fields.Datetime(string='Cancellation Date', tracking=True, copy=False)
    # cancelled_by = fields.Many2one('res.users', string='Cancelled By', tracking=True, copy=False)
    # actual_expense_submission_date = fields.Datetime(string='Actual Expense Submission Date', tracking=True, readonly=True, copy=False)

    # Re-introducing non-stored computed fields for UI logic (e.g., attrs in views)
    # Their logic is now delegated to the business_trip record.
    is_manager = fields.Boolean(string='Is Manager', compute='_compute_user_roles', store=False)
    is_finance = fields.Boolean(string='Is Finance', compute='_compute_user_roles', store=False)
    is_organizer = fields.Boolean(string='Is Organizer', compute='_compute_user_roles', store=False)
    can_see_costs = fields.Boolean(string='Can See Costs', compute='_compute_user_roles', store=False)
    is_current_user_owner = fields.Boolean(string="Is Current User Owner", compute='_compute_is_current_user_owner', store=False)
    can_cancel_trip = fields.Boolean(string="Can Cancel Trip", compute='_compute_can_cancel_trip', store=False)
    can_undo_expense_approval_action = fields.Boolean(string="Can Undo Expense Approval Action",
                                                  compute='_compute_can_undo_expense_approval_action',
                                                  store=False)

    # New computed field for displaying quotation link or Standalone
    display_quotation_ref = fields.Char(
        string="Linked Quotation Display",
        compute='_compute_display_quotation_ref',
        store=False
    )

    # --- Phase-based statusbar fields for showing multiple headers ---
    trip_status_phase1 = fields.Selection([
        ('draft', 'Awaiting Submission'),
        ('submitted', 'To Manager'),
        ('returned', 'Returned to Employee'),
        ('pending_organization', 'To Organizer'),
        ('organization_done', 'Organization Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='Trip Status (Phase 1)', compute='_compute_trip_status_phases', store=False)

    # Exception statuses for phase one
    is_returned = fields.Boolean(string='Is Returned', compute='_compute_exceptional_statuses', store=False)
    is_rejected = fields.Boolean(string='Is Rejected', compute='_compute_exceptional_statuses', store=False)

    trip_status_phase2 = fields.Selection([
        ('awaiting_trip_start', 'Awaiting Trip Start'),
        ('in_progress', 'Travel in Progress'),
        ('completed_waiting_expense', 'Awaiting Travel Expenses'),
        ('expense_submitted', 'Expenses Under Review'),
        ('expense_returned', 'Expenses Returned for Revision'),
        ('completed', 'TRAVEL PROCESS COMPLETED'),
    ], string='Trip Status (Phase 2)', compute='_compute_trip_status_phases', store=False)

    # Exception status for phase two
    is_expense_returned = fields.Boolean(string='Is Expense Returned', compute='_compute_exceptional_statuses', store=False)

    # New computed field for role display
    my_role = fields.Char(
        string="My Role",
        compute='_compute_my_role',
        store=False,
        help="Indicates the current user's role for this form"
    )

    # Override the state field to provide better labels
    state = fields.Selection(
        selection_add=[
            ('DRAFT', 'Awaiting Completion'),
            ('COMPLETE', 'Form Completed'),
            ('CANCEL', 'Cancelled')
        ],
    )

    # New field to check if all trip details are filled - MOVED to business.trip
    # has_trip_details = fields.Boolean(string='Has Trip Details', compute='_compute_has_trip_details', help="Technical field to check if all required trip details are filled.")

    # Flag to track forms being edited in returned state
    edit_in_returned_state = fields.Boolean(string='Edit in Returned State', default=False,
        help="Technical field to track forms being edited while in returned state")

    # Helper fields
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    notes = fields.Text(string='Notes')

    # For storing employee tickets and travel documents
    employee_documents_ids = fields.Many2many('ir.attachment',
                                           'formio_form_employee_docs_rel',
                                           'form_id', 'attachment_id',
                                           string='Employee Travel Documents',
                                           help="Documents for the employee such as tickets, reservations, etc.")

    # Fields for business calculations and display that depend on business.trip.data
    currency_id = fields.Many2one('res.currency', string='Currency',
                                 default=lambda self: self.env.company.currency_id.id, tracking=True)

    # New field to hold the M2O to sale.order
    sale_order_id = fields.Many2one('sale.order', string='Linked Sales Order', tracking=True, copy=False, help="Sales order linked to this trip request.")

    # Link to project and task - MOVED to business.trip
    # business_trip_project_id = fields.Many2one(...)
    # business_trip_task_id = fields.Many2one(...)

    organizer_plan_html = fields.Html(string="Organizer Plan Details", compute='_compute_organizer_plan_html', store=False)

    # START: New fields for structured organizer plan display
    organizer_plan_has_flight = fields.Boolean(string="Has Flight Plan", compute='_compute_organizer_plan_display_fields', store=False)
    organizer_plan_flight_html = fields.Html(string="Flight Plan Details", compute='_compute_organizer_plan_display_fields', store=False)
    organizer_plan_has_hotel = fields.Boolean(string="Has Hotel Plan", compute='_compute_organizer_plan_display_fields', store=False)
    organizer_plan_hotel_html = fields.Html(string="Hotel Plan Details", compute='_compute_organizer_plan_display_fields', store=False)
    organizer_plan_has_train = fields.Boolean(string="Has Train Plan", compute='_compute_organizer_plan_display_fields', store=False)
    organizer_plan_train_html = fields.Html(string="Train Plan Details", compute='_compute_organizer_plan_display_fields', store=False)
    organizer_plan_has_car_rental = fields.Boolean(string="Has Car Rental Plan", compute='_compute_organizer_plan_display_fields', store=False)
    organizer_plan_car_rental_html = fields.Html(string="Car Rental Plan Details", compute='_compute_organizer_plan_display_fields', store=False)
    organizer_plan_has_other = fields.Boolean(string="Has Other Plan Items", compute='_compute_organizer_plan_display_fields', store=False)
    organizer_plan_other_html = fields.Html(string="Other Plan Details", compute='_compute_organizer_plan_display_fields', store=False)
    # END: New fields for structured organizer plan display

    # MOVED to business.trip
    # final_total_cost = fields.Float(string='Final Total Cost', tracking=False, store=False,
    #                                help="The total cost to company: planned cost plus any additional expenses that exceed the planned budget.")

    # # Budget calculation fields
    # budget_difference = fields.Float(string='Budget Deviation', compute='_compute_budget_difference', store=False, tracking=False,
    #                                  help="The difference between the organizer planned cost and the actual expenses.")
    # budget_status = fields.Selection([
    #     ('under_budget', 'Under Budget'),
    #     ('on_budget', 'On Budget'),
    #     ('over_budget', 'Over Budget'),
    # ], string='Budget Status', compute='_compute_budget_difference', store=False, tracking=False)
    # payback_amount = fields.Float(string='Payback Amount', compute='_compute_budget_difference', store=False, tracking=False,
    #                              help="Amount to be paid back to employee (for expenses exceeding the planned budget)")

    # New fields for better transportation display
    transportation_display_data = fields.Text(string="Transportation Display Data", compute="_compute_transportation_display_data", store=False)
    return_transportation_display_data = fields.Text(string="Return Transportation Display Data", compute="_compute_transportation_display_data", store=False)
    has_any_transportation = fields.Boolean(string="Has Any Transportation", compute="_compute_transportation_display_data", store=False)
    has_any_return_transportation = fields.Boolean(string="Has Any Return Transportation", compute="_compute_transportation_display_data", store=False)

    @api.depends('state')
    def _compute_display_fields(self):
        """Override to customize display state labels for better clarity"""
        super(FormioForm, self)._compute_display_fields()
        for record in self:
            # Customize display text for form states
            if record.state == 'DRAFT':
                record.display_state = 'Awaiting Completion'
            elif record.state == 'COMPLETE':
                record.display_state = 'Form Completed'
            elif record.state == 'CANCEL':
                record.display_state = 'Cancelled'

    @api.depends(lambda self: ['sale_order_id', 'sale_order_id.name'] if 'sale_order_id' in self._fields else [])
    def _compute_display_quotation_ref(self):
        for record in self:
            if hasattr(record, 'sale_order_id') and record.sale_order_id:
                record.display_quotation_ref = record.sale_order_id.name # type: ignore
            else:
                record.display_quotation_ref = "Standalone"

    @api.model
    def create(self, vals_list):
        # The logic for creating business.trip.data has been moved to business.trip model's create method.
        # This method is now simplified.
        if not isinstance(vals_list, list):
            vals_list = [vals_list]

        for vals in vals_list:
            # Make sure state is DRAFT not PENDING (which we removed)
            if vals.get('state') == 'PENDING':
                vals['state'] = 'DRAFT'

        records = super(FormioForm, self).create(vals_list)

        for i, record in enumerate(records):
            vals = vals_list[i]
            if vals.get('state') == 'DRAFT' and not record.trip_status:
                record.trip_status = 'draft'
            elif vals.get('state') == 'COMPLETE' and not record.trip_status:
                record.trip_status = 'submitted' # Default to submitted if form is directly completed
            
            # Link attachments to the record
            attachments = record.expense_attachment_ids + record.organizer_attachments_ids + record.employee_documents_ids
            for attachment in attachments:
                if not attachment.res_id:
                    attachment.write({'res_model': self._name, 'res_id': record.id})

        return records

    def _process_transport_means_json(self):
        """
        Process the transport_means_json and return_transport_means_json fields
        to ensure the Boolean fields are correctly set.
        Note: This method should only be called after submission_data has been processed
        and transport_means_json is available in business.trip.data.
        """
        for record in self._filter_new_records():
            # Find linked business.trip.data record
            trip_data = self.env['business.trip.data'].search([('form_id', '=', record.id)], limit=1) # type: ignore
            if not trip_data:
                _logger.warning(f"No business.trip.data record found for form {record.id}, cannot process transport data") # type: ignore
                continue

            # Process outbound transportation
            if trip_data.transport_means_json:
                try:
                    transport_data = json.loads(trip_data.transport_means_json)
                    _logger.info(f"Processing transport_means_json for form {record.id}: {transport_data}")

                    # Update boolean fields on trip_data based on JSON content
                    trip_data.use_rental_car = bool(transport_data.get('rental_car'))
                    trip_data.use_company_car = bool(transport_data.get('company_car'))
                    trip_data.use_personal_car = bool(transport_data.get('personal_car'))
                    trip_data.use_train = bool(transport_data.get('train'))
                    trip_data.use_airplane = bool(transport_data.get('airplane'))
                    trip_data.use_bus = bool(transport_data.get('bus'))

                    _logger.info(f"Updated transport fields: rental_car={trip_data.use_rental_car}, train={trip_data.use_train}, airplane={trip_data.use_airplane}, bus={trip_data.use_bus}")
                except Exception as e:
                    _logger.error(f"Error processing transport_means_json: {e}", exc_info=True)
                    # Try alternative parsing method if JSON loading fails
                    try:
                        transport_data = ast.literal_eval(trip_data.transport_means_json)
                        _logger.info(f"Processed transport_means_json with ast.literal_eval: {transport_data}")

                        # Update boolean fields on trip_data based on parsed content
                        trip_data.use_rental_car = bool(transport_data.get('rental_car'))
                        trip_data.use_company_car = bool(transport_data.get('company_car'))
                        trip_data.use_personal_car = bool(transport_data.get('personal_car'))
                        trip_data.use_train = bool(transport_data.get('train'))
                        trip_data.use_airplane = bool(transport_data.get('airplane'))
                        trip_data.use_bus = bool(transport_data.get('bus'))
                    except Exception as e2:
                        _logger.error(f"Error in alternative parsing of transport_means_json: {e2}", exc_info=True)

            # Process return transportation
            if trip_data.return_transport_means_json:
                try:
                    return_transport_data = json.loads(trip_data.return_transport_means_json)
                    _logger.info(f"Processing return_transport_means_json for form {record.id}: {return_transport_data}")

                    # Update boolean fields on trip_data based on JSON content
                    trip_data.use_return_rental_car = bool(return_transport_data.get('rental_car'))
                    trip_data.use_return_company_car = bool(return_transport_data.get('company_car'))
                    trip_data.use_return_personal_car = bool(return_transport_data.get('personal_car'))
                    trip_data.use_return_train = bool(return_transport_data.get('train'))
                    trip_data.use_return_airplane = bool(return_transport_data.get('airplane'))
                    trip_data.use_return_bus = bool(return_transport_data.get('bus'))

                    _logger.info(f"Updated return transport fields: rental_car={trip_data.use_return_rental_car}, train={trip_data.use_return_train}, airplane={trip_data.use_return_airplane}, bus={trip_data.use_return_bus}")
                except Exception as e:
                    _logger.error(f"Error processing return_transport_means_json: {e}", exc_info=True)
                    # Try alternative parsing method if JSON loading fails
                    try:
                        return_transport_data = ast.literal_eval(trip_data.return_transport_means_json)
                        _logger.info(f"Processed return_transport_means_json with ast.literal_eval: {return_transport_data}")

                        # Update boolean fields on trip_data based on parsed content
                        trip_data.use_return_rental_car = bool(return_transport_data.get('rental_car'))
                        trip_data.use_return_company_car = bool(return_transport_data.get('company_car'))
                        trip_data.use_return_personal_car = bool(return_transport_data.get('personal_car'))
                        trip_data.use_return_train = bool(return_transport_data.get('train'))
                        trip_data.use_return_airplane = bool(return_transport_data.get('airplane'))
                        trip_data.use_return_bus = bool(return_transport_data.get('bus'))
                    except Exception as e2:
                        _logger.error(f"Error in alternative parsing of return_transport_means_json: {e2}", exc_info=True)

    def after_submit(self):
        """
        Called when form is submitted through form.io interface.
        This method now delegates the processing to the linked business.trip record.
        """
        _logger.info(f"--- [formio.form after_submit] START for form {self.id} ---")
        
        # First, run the original inherited logic from formio module
        res = super(FormioForm, self).after_submit()

        # Then, if this form is linked to a business trip, trigger our custom logic
        if self.business_trip_id:
            _logger.info(f"Form {self.id} is linked to Business Trip {self.business_trip_id.id}. Delegating processing...")
            self.business_trip_id.process_form_submission(self.submission_data)
        else:
            _logger.warning(f"Form {self.id} is not linked to any Business Trip. Skipping custom processing.")

        _logger.info(f"--- [formio.form after_submit] END for form {self.id} ---")
        return res

    @api.depends('submission_data')
    def _compute_form_data_json(self):
        for record in self:
            raw_submission_dict = {}
            if record.submission_data:
                try:
                    raw_submission_dict = json.loads(record.submission_data)
                except Exception:
                    _logger.error(f"Error parsing submission_data for form_data_json on form {record.id}", exc_info=True)

            try:
                record.form_data_json = json.dumps(raw_submission_dict, indent=2, sort_keys=True)
            except Exception:
                _logger.error(f"Error pretty-printing submission_data for form {record.id}", exc_info=True)
                record.form_data_json = str(raw_submission_dict) # Fallback to simple string representation

    @api.depends('business_trip_data_id.trip_duration_type')
    def _compute_form_data_trip_duration_type_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.trip_duration_type:
                record.form_data_trip_duration_type_display = dict(record.business_trip_data_id._fields['trip_duration_type'].selection).get(record.business_trip_data_id.trip_duration_type)
            else:
                record.form_data_trip_duration_type_display = ''

    @api.depends('business_trip_data_id.trip_type')
    def _compute_form_data_trip_type_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.trip_type:
                record.form_data_trip_type_display = dict(record.business_trip_data_id._fields['trip_type'].selection).get(record.business_trip_data_id.trip_type)
            else:
                record.form_data_trip_type_display = ''

    @api.depends('business_trip_data_id.accommodation_needed')
    def _compute_form_data_accommodation_needed_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.accommodation_needed:
                record.form_data_accommodation_needed_display = dict(record.business_trip_data_id._fields['accommodation_needed'].selection).get(record.business_trip_data_id.accommodation_needed)
            else:
                record.form_data_accommodation_needed_display = ''

    @api.depends('business_trip_data_id.accommodation_need_24h_reception')
    def _compute_form_data_accommodation_need_24h_reception_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.accommodation_need_24h_reception:
                record.form_data_accommodation_need_24h_reception_display = dict(record.business_trip_data_id._fields['accommodation_need_24h_reception'].selection).get(record.business_trip_data_id.accommodation_need_24h_reception)
            else:
                record.form_data_accommodation_need_24h_reception_display = ''

    @api.depends('business_trip_data_id.accompanying_person_ids', 'business_trip_data_id.accompanying_person_ids.full_name', 'business_trip_data_id.accompanying_person_ids.identity_document', 'business_trip_data_id.accompanying_person_ids.identity_document_filename')
    def _compute_accompanying_persons_summary(self):
        for record in self:
            trip_data = record.business_trip_data_id
            if trip_data and trip_data.accompanying_person_ids:
                person_count = len(trip_data.accompanying_person_ids)
                person_names = []
                document_links = []
                
                for person in trip_data.accompanying_person_ids:
                    person_names.append(person.full_name)
                    if person.identity_document and person.identity_document_filename:
                        download_url = f"/web/content/accompanying.person/{person.id}/identity_document/{person.identity_document_filename}?download=true"
                        document_links.append(f"<a href='{download_url}' target='_blank'>{person.identity_document_filename}</a>")
                    elif person.identity_document:
                        download_url = f"/web/content/accompanying.person/{person.id}/identity_document/document.pdf?download=true"
                        document_links.append(f"<a href='{download_url}' target='_blank'>Document</a>")
                    else:
                        document_links.append("No document")
                
                count_text = f"Number of accompanying persons: {person_count}"
                names_text = f"Names: {', '.join(person_names)}"
                links_text = f"Documents: {', '.join(document_links)}"
                
                record.form_data_accompanying_persons_summary_display = f"{count_text}<br/>{names_text}<br/>{links_text}"
            else:
                record.form_data_accompanying_persons_summary_display = "No accompanying persons."

    @api.depends('business_trip_data_id.airplane_baggage_type')
    def _compute_form_data_airplane_baggage_type_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.airplane_baggage_type:
                record.form_data_airplane_baggage_type_display = dict(record.business_trip_data_id._fields['airplane_baggage_type'].selection).get(record.business_trip_data_id.airplane_baggage_type)
            else:
                record.form_data_airplane_baggage_type_display = ''

    @api.depends('business_trip_data_id.return_airplane_baggage_type')
    def _compute_form_data_return_airplane_baggage_type_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.return_airplane_baggage_type:
                record.form_data_return_airplane_baggage_type_display = dict(record.business_trip_data_id._fields['return_airplane_baggage_type'].selection).get(record.business_trip_data_id.return_airplane_baggage_type)
            else:
                record.form_data_return_airplane_baggage_type_display = ''

    @api.depends('business_trip_data_id.rental_car_credit_card')
    def _compute_form_data_rental_car_credit_card_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.rental_car_credit_card:
                record.form_data_rental_car_credit_card_display = dict(record.business_trip_data_id._fields['rental_car_credit_card'].selection).get(record.business_trip_data_id.rental_car_credit_card)
            else:
                record.form_data_rental_car_credit_card_display = ''

    @api.depends('business_trip_data_id.rental_car_type')
    def _compute_form_data_rental_car_type_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.rental_car_type:
                record.form_data_rental_car_type_display = dict(record.business_trip_data_id._fields['rental_car_type'].selection).get(record.business_trip_data_id.rental_car_type)
            else:
                record.form_data_rental_car_type_display = ''

    @api.depends('business_trip_data_id.return_rental_car_credit_card')
    def _compute_form_data_return_rental_car_credit_card_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.return_rental_car_credit_card:
                record.form_data_return_rental_car_credit_card_display = dict(record.business_trip_data_id._fields['return_rental_car_credit_card'].selection).get(record.business_trip_data_id.return_rental_car_credit_card)
            else:
                record.form_data_return_rental_car_credit_card_display = ''

    @api.depends('business_trip_data_id.return_rental_car_type')
    def _compute_form_data_return_rental_car_type_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.return_rental_car_type:
                record.form_data_return_rental_car_type_display = dict(record.business_trip_data_id._fields['return_rental_car_type'].selection).get(record.business_trip_data_id.return_rental_car_type)
            else:
                record.form_data_return_rental_car_type_display = ''

    @api.depends('business_trip_data_id.use_rental_car', 'business_trip_data_id.use_company_car',
                 'business_trip_data_id.use_personal_car', 'business_trip_data_id.use_train',
                 'business_trip_data_id.use_airplane', 'business_trip_data_id.use_bus',
                 'business_trip_data_id.use_return_rental_car', 'business_trip_data_id.use_return_company_car',
                 'business_trip_data_id.use_return_personal_car', 'business_trip_data_id.use_return_train',
                 'business_trip_data_id.use_return_airplane', 'business_trip_data_id.use_return_bus')


    @api.onchange('state')
    def _onchange_state(self):
        """Update trip_status when form state changes"""
        if self.state == 'DRAFT' and self.trip_status not in ['draft']:
            # If form is reset to draft, trip status should also be draft
            if not self.trip_status or self.trip_status in ['submitted']:
                self.trip_status = 'draft'
            # Other states should not automatically revert to draft by formio state change alone

        elif self.state == 'COMPLETE':
            if self.trip_status == 'draft':
                self.trip_status = 'submitted' # Employee completes the draft
            elif not self.trip_status: # If somehow status is blank when form is completed
                self.trip_status = 'submitted'

        elif self.state == 'CANCEL':
            if self.trip_status not in ['cancelled', 'rejected']:
                # If formio form is cancelled, and trip not already terminal, set to cancelled
                # Consider if a trip should only be cancellable via its own action_cancel_trip method
                self.trip_status = 'cancelled'
                if not self.business_trip_id.cancelled_by:
                    self.business_trip_id.cancelled_by = self.env.user
                if not self.business_trip_id.cancellation_date:
                    self.business_trip_id.cancellation_date = fields.Datetime.now()

    @api.onchange('business_trip_id.trip_status')
    def _onchange_trip_status(self):
        trip_status = self.business_trip_id.trip_status if self.business_trip_id else False
        _logger.info(f"Trip status changed to {trip_status} for form {self.id}, current state: {self.state}")
        if trip_status == 'draft' and self.state != 'DRAFT':
            self.state = 'DRAFT'
        elif trip_status and trip_status not in ['draft', 'cancelled', 'rejected'] and self.state != 'COMPLETE':
             # Most active trip statuses mean the underlying formio form should be in COMPLETE state.
            self.state = 'COMPLETE'
        elif trip_status and trip_status in ['cancelled', 'rejected'] and self.state != 'CANCEL':
            # Terminal trip statuses might map to CANCEL state in formio.
            self.state = 'CANCEL'

    # Methods for workflow transitions - MOVED to business.trip model
    # def action_submit_to_manager(self): ...

    # Manager actions - MOVED to business.trip
    # def action_manager_assign_organizer_and_budget(self): ...
    # def confirm_assignment_and_budget(self, ...): ...
    # def _create_business_trip_task(self, ...): ...
    # def _add_stakeholders_as_followers(self, ...): ...

    # action_manager_approve_plan is removed / integrated into organizer's action
    # action_manager_return_plan_to_organizer is removed, handled by chatter/internal notes

    # MOVED to business.trip model: action_organizer_confirm_planning

    # action_organizer_submit_plan is replaced by action_organizer_confirm_planning

    @api.depends('business_trip_id', 'business_trip_id.user_id', 'business_trip_id.manager_id', 'business_trip_id.organizer_id')
    @api.depends_context('uid')
    def _compute_user_roles(self):
        for record in self:
            if record.business_trip_id:
                # Delegate to the business_trip model's compute method logic
                user = self.env.user
                bt = record.business_trip_id
                is_system_admin = user.has_group('base.group_system')

                if is_system_admin:
                    record.is_manager = True
                    record.is_finance = True
                    record.is_organizer = True
                    record.can_see_costs = True
                    continue

                record.is_manager = (bt.manager_id and user.id == bt.manager_id.id)
                record.is_organizer = (bt.organizer_id and user.id == bt.organizer_id.id)
                is_finance_user = user.has_group('account.group_account_manager')
                record.is_finance = record.is_organizer or is_finance_user
                is_in_organizer_group = user.has_group('custom_business_trip_management.group_business_trip_organizer')
                record.can_see_costs = record.is_manager or record.is_organizer or is_in_organizer_group
            else:
                record.is_manager = False
                record.is_finance = False
                record.is_organizer = False
                record.can_see_costs = self.env.user.has_group('base.group_system') or self.env.user.has_group('custom_business_trip_management.group_business_trip_organizer')

    @api.depends('business_trip_data_id.manual_travel_duration',
                 'business_trip_data_id.travel_start_date',
                 'business_trip_data_id.travel_end_date',
                 'business_trip_data_id') # Ensure compute is triggered if BTD link changes
    def _compute_travel_dates(self):
        _logger.info("FORMIO_FORM_INHERIT: Starting _compute_travel_dates (PLANNED) calculation...")
        for record in self:
            record.travel_duration = 0.0  # Initialize with a default

            btd = None
            if record.id: # If the record has an ID, it might exist in the database
                btd = self.env['business.trip.data'].search([('form_id', '=', record.id)], limit=1)

            if not btd and record.business_trip_data_id: # Fallback to the M2O field if search yields nothing but M2O is set
                btd = record.business_trip_data_id

            _logger.info(f"FORMIO_FORM_INHERIT: Record ID {record.id if record.id else 'NewID'}, Searched/Used BusinessTripData ID: {btd.id if btd else 'None'}")
            if btd:
                _logger.info(f"FORMIO_FORM_INHERIT: BTD Details for record {record.id or 'NewID'} - Manual Duration: {btd.manual_travel_duration}, Start Date: {btd.travel_start_date}, End Date: {btd.travel_end_date}")

            if btd and btd.manual_travel_duration and btd.manual_travel_duration > 0:
                _logger.info(f"FORMIO_FORM_INHERIT: Using manual travel duration: {btd.manual_travel_duration} for record {record.id or 'NewID'}")
                record.travel_duration = btd.manual_travel_duration

            elif btd and btd.travel_start_date and btd.travel_end_date:
                _logger.info(f"FORMIO_FORM_INHERIT: Using planned dates for record {record.id or 'NewID'}. Start: {btd.travel_start_date}, End: {btd.travel_end_date}")
                if btd.travel_end_date >= btd.travel_start_date:
                    delta_days = (btd.travel_end_date - btd.travel_start_date).days
                    record.travel_duration = float(delta_days + 1)
                    _logger.info(f"FORMIO_FORM_INHERIT: Calculated delta_days + 1 = {delta_days + 1}, travel_duration (planned dates): {record.travel_duration} for record {record.id or 'NewID'}")
                else:
                    _logger.warning(f"FORMIO_FORM_INHERIT: Planned end date is before planned start date for record {record.id or 'NewID'}. Start: {btd.travel_start_date}, End: {btd.travel_end_date}")
                    record.travel_duration = 0.0
            else:
                # Changed from WARNING to INFO to reduce log noise for expected cases (e.g., old data)
                _logger.info(f"FORMIO_FORM_INHERIT: Could not calculate travel_duration for record {record.id or 'NewID'}. Conditions not met. btd exists: {bool(btd)}")
                if btd:
                    _logger.info(f"FORMIO_FORM_INHERIT: Further details for {record.id or 'NewID'} - btd.manual_travel_duration: {btd.manual_travel_duration}, btd.travel_start_date: {btd.travel_start_date}, btd.travel_end_date: {btd.travel_end_date}")
                record.travel_duration = 0.0

            _logger.info(f"FORMIO_FORM_INHERIT: Final travel_duration for record {record.id or 'NewID'}: {record.travel_duration}")

    @api.depends('travel_duration', 'business_trip_data_id.trip_duration_type')
    def _compute_travel_duration_parts(self):
        for record in self:
            # MODIFIED: Logic now checks if trip_duration_type is 'days' or another value
            # Assuming 'days' is for daily trips and other values might imply hourly,
            # or we can be more explicit if there are more types.
            # For now, we assume if not 'days' it's not a multi-day calculation.
            # This logic needs to be robust based on ALL possible values of trip_duration_type.
            # Based on business_trip_data.py, values are: 'days', 'weeks', 'short', 'long'.
            # None of these directly imply 'hourly'. Let's assume for now any trip can have hours,
            # and the distinction is not based on a selection but on how data is entered.
            # The original logic used a boolean is_hourly_trip. The closest seems to be manual_travel_duration.
            # Let's revisit if needed. A simple fix is to check if duration has a fraction.

            is_hourly = False # Default to not hourly
            if record.business_trip_data_id:
                # A more direct check for hourly trips would be better.
                # If manual_travel_duration contains a fraction, it's likely hourly.
                if record.business_trip_data_id.manual_travel_duration and record.business_trip_data_id.manual_travel_duration % 1 != 0:
                    is_hourly = True

            if is_hourly:
                record.travel_duration_days = 0
                record.travel_duration_hours = record.travel_duration
            else:
                record.travel_duration_days = int(record.travel_duration)
                record.travel_duration_hours = 0.0

    @api.depends('business_trip_id.actual_start_date', 'business_trip_id.actual_end_date')
    def _compute_actual_travel_duration_days(self):
        for record in self:
            if record.business_trip_id and record.business_trip_id.actual_start_date and record.business_trip_id.actual_end_date:
                if record.business_trip_id.actual_end_date >= record.business_trip_id.actual_start_date:
                    delta = record.business_trip_id.actual_end_date - record.business_trip_id.actual_start_date
                    # Simple day calculation, rounding up.
                    days = delta.days
                    if delta.seconds > 0:
                        days += 1
                    record.actual_travel_duration_days = days if days > 0 else 1
                else:
                    record.actual_travel_duration_days = 0
            else:
                record.actual_travel_duration_days = 0

    @api.depends('travel_start_date', 'travel_end_date')
    def _compute_planned_travel_dates_display(self):
        for record in self:
            if record.travel_start_date and record.travel_end_date:
                record.travel_dates_display = f"{record.travel_start_date.strftime('%d/%m/%Y')} - {record.travel_end_date.strftime('%d/%m/%Y')}"
            elif record.travel_start_date:
                record.travel_dates_display = record.travel_start_date.strftime('%d/%m/%Y')
            else:
                record.travel_dates_display = "Not Set"

    def action_edit_trip_details(self):
        """Open wizard for editing trip details"""
        self.ensure_one()

        allowed_statuses_for_owner_edit = ['draft', 'returned']
        is_owner = self.user_id.id == self.env.user.id
        # Manager/Admin can edit when it's submitted to them, before assigning to organizer
        can_manager_edit = (self.env.user.has_group('base.group_system') or
                            (self.manager_id and self.env.user.id == self.manager_id.id)) and \
                           self.trip_status == 'submitted'

        if not (
            (is_owner and self.trip_status in allowed_statuses_for_owner_edit) or
            can_manager_edit
        ):
            raise ValidationError(f"You cannot edit this trip at its current stage ('{self.trip_status}') or you lack permissions.")

        return {
            'name': 'Edit Trip Details',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.details.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id, 'from_wizard': True}
        }

    def action_edit_cost_estimate(self):
        """Open wizard for editing cost estimate. THIS IS LIKELY DEPRECATED due to new workflow."""
        self.ensure_one()
        _logger.warning("DEPRECATED: action_edit_cost_estimate called. Manager now sets budget directly in Assign Organizer wizard.")

        # Only system admins (who act as managers here for this specific old action)
        if not self.env.user.has_group('base.group_system'):
            raise ValidationError("This deprecated action is restricted to System Administrators.")

        # Check if the trip is in the right status (still 'submitted' as per original logic for this old wizard)
        if self.trip_status != 'submitted':
            raise ValidationError("Cost estimation (deprecated flow) can only be done for submitted trips.")

        return {
            'name': 'Cost Estimation (Legacy)',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.cost.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id}
        }

    def action_back_to_draft(self):
        """Return a submitted form back to draft status"""
        self.ensure_one()

        # Only the owner can return to draft and only if it's in submitted or returned status
        if self.user_id.id != self.env.user.id:
            raise ValidationError("Only the owner of this trip request can return it to draft status.")

        # Allow return to draft for submitted forms (and those already in draft or returned status)
        if self.trip_status not in ['submitted', 'returned', 'draft']:
            raise ValidationError("Only submitted forms, returned forms, or completed forms still in draft status can be returned to draft editing state.")

        # Check if the request has already been processed by a manager if trip_status is 'submitted'
        if self.trip_status == 'submitted' and \
           (self.business_trip_id.estimated_by or self.business_trip_id.manager_approval_date or self.business_trip_id.organizer_approval_date or self.business_trip_id.organizer_id or \
            self.trip_status in ['rejected']): # Added rejected here for completeness
            raise ValidationError("This request has already been processed or actioned by management and cannot be returned to draft by the user.")

        self.write({
            'state': 'DRAFT',  # formio.form state
            'trip_status': 'draft', # our custom status
        })
        # Clear related approval/estimation/return fields to make it a clean draft on the business.trip model
        self.business_trip_id.write({
            'submission_date': False,
            'manager_id': False,
            'manager_approval_date': False,
            'manager_comments': False,
            'organizer_approval_date': False,
            'organizer_expense_comments': False,
            'estimated_by': False,
            'estimation_date': False,
            'estimation_comments': False,
            'return_comments': False, # Clear previous return comments
            'rejection_reason': False, # Clear previous rejection details
            'rejection_comment': False,
            'rejected_by': False,
            'rejection_date': False,
        })

        # Post a message to the chatter
        self.message_post(body="Request returned to draft by the user.")

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_cancel_trip(self):
        """Cancel a business trip request and mark it as cancelled.
        This is only allowed for the owner of the trip and only if it's in draft or submitted state
        before any manager action."""
        self.ensure_one()

        # Check if the current user is the owner of the trip
        if self.user_id.id != self.env.user.id:
            raise ValidationError("Only the owner of this trip request can cancel it.")

        # Check if the trip is in a cancellable state
        # Only allow cancellation in draft or in submitted state before any manager action
        if self.trip_status not in ['draft', 'submitted']:
            raise ValidationError("You can only cancel requests that are in 'Draft' or 'Submitted' state.")

        # For submitted state, check if it's already been actioned by management
        if self.trip_status == 'submitted' and \
           (self.business_trip_id.estimated_by or self.business_trip_id.manager_approval_date or self.business_trip_id.organizer_approval_date or \
            self.trip_status in ['rejected']):
            raise ValidationError("This request has already been processed by management and cannot be cancelled.")

        # Update trip status to cancelled
        self.business_trip_id.write({
            'trip_status': 'cancelled',
            'cancellation_date': fields.Datetime.now(),
            'cancelled_by': self.env.user.id,
        })
        self.state = 'CANCEL'  # Update formio form state

        # Post a message to the chatter
        self.message_post(body=f"Request cancelled by {self.env.user.name}.")

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.depends('business_trip_id.user_id', 'user_id')
    @api.depends_context('uid')
    def _compute_is_current_user_owner(self):
        for record in self:
            if record.business_trip_id:
                record.is_current_user_owner = (record.business_trip_id.user_id.id == self.env.user.id)
            else:
                # Fallback for forms without a business trip yet
                record.is_current_user_owner = (record.user_id.id == self.env.user.id)

    @api.depends('business_trip_id.trip_status', 'business_trip_id.user_id', 'business_trip_id.manager_approval_date', 'business_trip_id.organizer_submission_date')
    @api.depends_context('uid')
    def _compute_can_cancel_trip(self):
        for record in self:
            can_cancel = False
            if record.business_trip_id:
                bt = record.business_trip_id
                is_owner = (bt.user_id.id == self.env.user.id)

                if is_owner and bt.trip_status in ['draft', 'submitted']:
                     if bt.trip_status == 'submitted':
                        if not (bt.manager_approval_date or bt.organizer_submission_date or bt.trip_status in ['rejected', 'pending_organization']):
                            can_cancel = True
                     else: # draft
                        can_cancel = True
            else:
                # Simplified logic for a form not yet linked to a business trip
                is_owner = (record.user_id.id == self.env.user.id)
                if is_owner and record.state == 'DRAFT' and not record.trip_status:
                    can_cancel = True
            
            record.can_cancel_trip = can_cancel

    @api.depends('business_trip_id.trip_status', 'business_trip_id.expense_approval_date')
    def _compute_can_undo_expense_approval_action(self):
        # Get the setting from the environment's company once
        undo_limit_days = self.env.company.undo_expense_approval_days_limit

        for record in self:
            can_undo = False
            # User must be a system admin (or a specific manager/finance group if defined differently and more granularly)
            is_approver = self.env.user.has_group('base.group_system')

            if record.business_trip_id and record.business_trip_id.trip_status == 'completed' and is_approver:
                if record.business_trip_id.expense_approval_date:
                    if undo_limit_days > 0:
                        approval_date_limit = record.business_trip_id.expense_approval_date + relativedelta(days=undo_limit_days)
                        if fields.Datetime.now() <= approval_date_limit:
                            can_undo = True
                    else: # If limit is 0 or negative, undo is always allowed (if other conditions met)
                        can_undo = True
            record.can_undo_expense_approval_action = can_undo

    def action_open_return_comment_wizard(self):
        """Open wizard for returning the trip request with comments."""
        self.ensure_one()

        if self.trip_status not in ['submitted']:
            raise ValidationError("You can only return requests that are in 'Submitted to Manager' state using this wizard.")

        if not self.env.user.has_group('base.group_system') and not (self.manager_id and self.env.user.id == self.manager_id.id):
            raise ValidationError("Only the assigned manager or system administrators can return the request with comments.")

        return {
            'name': 'Return with Comments',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.return.comment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_form_id': self.id,
            }
        }

    def action_open_expense_return_comment_wizard(self):
        """Open wizard for returning submitted expenses with comments."""
        self.ensure_one()

        if self.trip_status != 'expense_submitted':
            raise ValidationError("You can only return expenses that have been submitted for review.")

        # Check if user has permission (finance/system/organizer)
        if not (self.env.user.has_group('account.group_account_manager') or
                self.env.user.has_group('base.group_system') or
                self.is_organizer):
            raise ValidationError("Only the trip organizer, finance personnel, or system administrators can return expenses.")

        return {
            'name': 'Return Travel Expenses with Comments',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.expense.return.comment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_form_id': self.id,
            }
        }

    def action_undo_cost_estimation(self):
        """Allow manager/finance to revert from cost_estimated to submitted. LIKELY DEPRECATED."""
        self.ensure_one()
        _logger.warning("action_undo_cost_estimation is likely deprecated due to new workflow.")

        if self.trip_status != 'submitted': # Should have been a different status if it was estimated.
                                          # This action becomes less relevant with the new flow.
            raise ValidationError("This action is only available for requests with 'Cost Estimated (Old Flow)' status.")

        if not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only system administrators can perform this action for now.")

        self.write({
            'trip_status': 'submitted',
            'expected_cost': 0.0,
            'estimated_by': False,
            'estimation_date': False,
            'estimation_comments': False,
        })
        self.message_post(body="The cost estimation (old flow) has been undone.")
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_undo_approval(self):
        """Allow manager to revert an approved trip request. LIKELY DEPRECATED / CHANGED."""
        self.ensure_one()
        _logger.warning("action_undo_approval is likely deprecated/changed due to new workflow.")

        # This action needs re-evaluation. With 'organization_done', there isn't a direct 'approved' state by manager before it.
        # If we want to undo 'organization_done', it should go back to 'pending_organization'.
        if self.trip_status != 'organization_done': # Example: Reverting from the new "finalized" state by organizer
            raise ValidationError("This action needs re-evaluation for the new workflow. Currently configured for 'organization_done'.")

        if not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only system administrators can perform this action for now.")

        self.write({
            'trip_status': 'pending_organization', # Revert to organizer planning stage
            'plan_approval_date': False,
            'organizer_submission_date': False,
        })

        self.message_post(body="The trip organization has been reset to 'Pending Organization' by an administrator.")
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_user_undo_expense_submission(self):
        """Allow the user (owner) to recall their expense submission
        if it has not yet been processed (approved, returned, or completed)."""
        self.ensure_one()

        if self.trip_status != 'expense_submitted':
            raise ValidationError("This action is only available for requests with 'Expenses Under Review' status.")

        # Check if the current user is the owner of the request
        if self.user_id.id != self.env.user.id:
            raise ValidationError("Only the owner of this request can recall the expense submission.")

        # Check if expenses have already been actioned by management
        if self.business_trip_id.expense_approval_date or self.business_trip_id.expense_approved_by or self.business_trip_id.trip_status in ['expense_returned', 'completed']:
            raise ValidationError("Expenses have already been processed by management and cannot be recalled.")

        # Store expense value before status change
        current_expense = self.business_trip_id.expense_total
        currency_symbol = self.currency_id.symbol if self.currency_id else ''

        # Change status to waiting for expense submission
        self.business_trip_id.write({
            'trip_status': 'completed_waiting_expense',
        })

        # Create a styled message for expense recall
        styled_message = f"""
<div style="background-color: #e8f4f8; border: 1px solid #17a2b8; border-radius: 5px; padding: 15px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #17a2b8; font-size: 20px; margin-right: 10px;">↩️</span>
        <span style="font-weight: bold; color: #17a2b8; font-size: 16px;">Travel Expenses Recalled</span>
    </div>
    <p style="margin: 5px 0 10px 0;">Travel expense submission (amount: {current_expense} {currency_symbol}) has been recalled by {self.user_id.name} for further editing.</p>
    <div style="background-color: #f8f9fa; border-left: 4px solid #17a2b8; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;">The expense submission has been moved back to 'Awaiting Travel Expenses' status. You can now edit and resubmit your expenses.</p>
    </div>
</div>
"""

        # Send message showing expense amount with improved styling
        self.message_post(
            body=styled_message,
            subtype_xmlid='mail.mt_note'
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_return_with_comment(self):
        """
        Return trip request to employee for revision and correction
        """
        self.ensure_one()

        # Check request status
        if self.trip_status != 'submitted':
            raise ValidationError("You can only return requests that are in 'Submitted to Manager' state.")

        # Check user permissions
        if not self.env.user.has_group('base.group_system') and not (self.manager_id and self.env.user.id == self.manager_id.id):
            raise ValidationError("Only the assigned manager or system administrators can return the request with comments.")

        # Change status to 'returned'
        self.write({
            'trip_status': 'returned',
        })

        # Notify the employee with enhanced styling
        if self.user_id.partner_id:
            # Create a styled message with warning appearance
            styled_message = f"""
<div style="background-color: #ffeeba; border: 1px solid #ffc107; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #856404; font-size: 20px; margin-right: 10px;">⚠️</span>
        <span style="font-weight: bold; color: #856404; font-size: 16px;">Trip Request Returned</span>
    </div>
    <p style="margin: 5px 0 10px 0;">Your business trip request '<strong>{self.title}</strong>' has been returned for revision.</p>
    <div style="background-color: #fff; border-left: 4px solid #ffc107; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Next steps:</strong> Please check the comments below, make necessary corrections, and resubmit your request.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">Returned by: {self.env.user.name}</span>
    </div>
</div>
"""

            # If manager comments exist, include them in the message
            if self.business_trip_id.manager_comments:
                styled_message += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px;">
    <p style="margin: 0 0 5px 0; font-weight: bold;">Comments:</p>
    <p style="margin: 0; color: #333;">{self.business_trip_id.manager_comments}</p>
</div>
"""

            self.message_post(
                body=styled_message,
                partner_ids=[self.user_id.partner_id.id]
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_reject(self):
        """
        Reject trip request by manager
        """
        self.ensure_one()

        # Check request status
        if self.trip_status != 'submitted':
            raise ValidationError("You can only reject requests that are in 'Submitted to Manager' state.")

        # Check user permissions
        if not self.env.user.has_group('base.group_system') and not (self.manager_id and self.env.user.id == self.manager_id.id):
            raise ValidationError("Only the assigned manager or system administrators can reject the request.")

        # Change status to 'rejected' and record rejection information
        self.write({
            'trip_status': 'rejected',
            'rejected_by': self.env.user.id,
            'rejection_date': fields.Datetime.now()
        })

        # Notify the employee
        if self.user_id.partner_id:
            rejection_reason_display = dict(self.business_trip_id._fields['rejection_reason'].selection).get(self.business_trip_id.rejection_reason, self.business_trip_id.rejection_reason)
            message = f"Your business trip request '{self.title}' has been rejected."
            if rejection_reason_display:
                message += f" Reason: {rejection_reason_display}"
            if self.business_trip_id.rejection_comment:
                message += f" Details: {self.business_trip_id.rejection_comment}"

            self.message_post(
                body=message,
                partner_ids=[self.user_id.partner_id.id]
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_manager_undo_expense_approval(self):
        """Allow authorized manager/finance to revert a completed expense approval
        back to 'expense_submitted' for re-evaluation or correction."""
        self.ensure_one()

        if self.trip_status != 'completed':
            raise ValidationError("This action is only available for requests with 'TRAVEL PROCESS COMPLETED' status (expenses approved)." )

        # Check user permissions (e.g., finance, HR manager, or system admin who can approve expenses)
        # Adjust groups as per who is allowed to approve expenses in the first place.
        can_undo_expense_approval = self.env.user.has_group('account.group_account_manager') or \
                                  self.env.user.has_group('hr.group_hr_manager') or \
                                  self.env.user.has_group('base.group_system')

        if not can_undo_expense_approval:
            raise ValidationError("Only authorized personnel (Finance, HR Manager, or System Admin) can undo expense approval.")

        self.business_trip_id.write({
            'trip_status': 'expense_submitted',
            'organizer_approval_date': False,
            'expense_approved_by': False,
            'final_total_cost': 0.0, # Reset final_total_cost as it's set upon approval
        })

        self.message_post(body="Expense approval has been undone. The expenses are now back in 'Expenses Under Review' state for review.")

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
  

    @api.depends('business_trip_id.trip_status')
    def _compute_trip_status_phases(self):
        """
        Calculate phase-based statuses based on trip_status
        This method must ensure that all statuses, including exception statuses,
        are properly displayed in their respective phases.
        """
        _logger.info("Computing trip status phases")
        for rec in self:
            # Log information
            trip_status = rec.business_trip_id.trip_status if rec.business_trip_id else False
            _logger.info(f"Form ID: {rec.id}, Current trip_status: {trip_status}")

            # Phase one - normal and exception stages
            if trip_status in ['draft', 'submitted', 'pending_organization', 'organization_done', 'rejected', 'cancelled']:
                # Standard behavior for normal states
                rec.trip_status_phase1 = trip_status
                _logger.info(f"Setting trip_status_phase1 to {trip_status}")
            elif trip_status == 'returned':
                # Special case for 'returned' status - show it explicitly when active
                rec.trip_status_phase1 = 'returned'
                _logger.info(f"Setting trip_status_phase1 to returned for returned status")
            else:
                # When in phase two, keep showing 'organization_done' in phase one
                if trip_status in ['awaiting_trip_start', 'in_progress', 'completed_waiting_expense', 'expense_submitted', 'expense_returned', 'completed']:
                    rec.trip_status_phase1 = 'organization_done'
                    _logger.info(f"Setting trip_status_phase1 to organization_done while in phase two status: {trip_status}")
                else:
                    rec.trip_status_phase1 = False
                    _logger.info(f"Setting trip_status_phase1 to False for status: {trip_status}")

            # Phase two - normal stages
            if trip_status in ['awaiting_trip_start', 'completed_waiting_expense', 'expense_submitted', 'completed']:
                rec.trip_status_phase2 = trip_status
                _logger.info(f"Setting trip_status_phase2 to {trip_status}")
            elif trip_status == 'in_progress':
                # When in progress, show only in_progress (hide awaiting_trip_start)
                rec.trip_status_phase2 = 'in_progress'
                _logger.info(f"Setting trip_status_phase2 to in_progress for in_progress status")
            elif trip_status == 'expense_returned':
                # Only show expense_returned when it's the actual current status
                rec.trip_status_phase2 = 'expense_returned'
                _logger.info(f"Setting trip_status_phase2 to expense_returned for expense_returned status")
            elif trip_status == 'organization_done':
                # When organization is complete, show phase 2 with awaiting_trip_start as the initial status
                rec.trip_status_phase2 = 'awaiting_trip_start'
                _logger.info(f"Setting trip_status_phase2 to awaiting_trip_start for organization_done status")
            else:
                rec.trip_status_phase2 = False
                _logger.info(f"Setting trip_status_phase2 to False for status: {trip_status}")

            # Additional debug information
            _logger.info(f"Final phase status - Phase1: {rec.trip_status_phase1}, Phase2: {rec.trip_status_phase2}")

    def action_open_organizer_plan_wizard(self):
        """Open wizard for organizer to edit trip plan details"""
        self.ensure_one()

        if self.trip_status != 'pending_organization':
            raise ValidationError("Trip plan can only be edited when in 'Pending Organization' state.")

        # Check if user is the assigned organizer only
        if self.organizer_id.id != self.env.user.id:
            raise ValidationError("Only the assigned organizer can edit the trip plan.")

        return {
            'name': 'Edit Trip Plan',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.organizer.plan.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id}
        }

    def action_submit_expenses(self):
        """
        Submit trip expenses by employee
        """
        self.ensure_one()
        if self.trip_status not in ['completed_waiting_expense', 'expense_returned']:
            raise ValidationError("You can only submit expenses when the trip is in 'Awaiting Travel Expenses' or 'Expense Returned' state.")
        if self.user_id.id != self.env.user.id:
            raise ValidationError("Only the employee of this request can submit expenses.")

        # Store previous status to determine if this is an initial submission or a revision
        previous_status = self.trip_status

        # Change status to 'expense_submitted'
        self.with_context(mail_notrack=True, system_edit=True).write({
            'trip_status': 'expense_submitted',
            'actual_expense_submission_date': fields.Datetime.now(),
        })

        # Check if this is a submission with no expenses
        is_no_expenses = self.env.context.get('no_expenses_submission', False)

        # Create appropriate message based on previous status and expense status
        if is_no_expenses:
            if previous_status == 'completed_waiting_expense':
                # Initial no-expense submission
                message_body = f"Employee {self.user_id.name} has confirmed that there are no additional expenses for trip '{self.title}'."
            else:
                # No-expense revision after return
                message_body = f"Employee {self.user_id.name} has confirmed again that there are no additional expenses for trip '{self.title}'."
        else:
            if previous_status == 'completed_waiting_expense':
                # Initial expense submission
                message_body = f"Employee {self.user_id.name} has submitted travel expenses for trip '{self.title}'."
            else:
                # Expense revision after return
                message_body = f"Employee {self.user_id.name} has resubmitted revised travel expenses for trip '{self.title}'."

            # Add expense amount to the message if expenses were submitted
            message_body += f"<br/>Expense amount: {self.business_trip_id.expense_total:.2f} {self.currency_id.symbol if self.currency_id else ''}"

        # Prepare partners to notify
        partners_to_notify = []
        if self.manager_id and self.manager_id.partner_id:
            partners_to_notify.append(self.manager_id.partner_id.id)
        # Organizer might need this notification
        if self.organizer_id and self.organizer_id.partner_id:
            partners_to_notify.append(self.organizer_id.partner_id.id)

        if partners_to_notify:
            # Create styled message based on whether expenses were submitted or not
            if is_no_expenses:
                # Styled message for no-expense submission
                styled_message = f"""
<div style="background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #155724; font-size: 20px; margin-right: 10px;">✓</span>
        <span style="font-weight: bold; color: #155724; font-size: 16px;">No Expenses Confirmation</span>
    </div>
    <p style="margin: 5px 0 10px 0;">{message_body}</p>
    <div style="background-color: #fff; border-left: 4px solid #28a745; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Note:</strong> The employee has confirmed there are no additional expenses beyond what was already covered by the planned budget.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">Submitted by: {self.user_id.name}</span>
    </div>
</div>
"""
                if self.business_trip_id.expense_comments:
                    styled_message += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px;">
    <p style="margin: 0 0 5px 0; font-weight: bold;">Comments:</p>
    <p style="margin: 0; color: #333;">{self.business_trip_id.expense_comments}</p>
</div>
"""
            else:
                # Styled message for expense submission
                styled_message = f"""
<div style="background-color: #cce5ff; border: 1px solid #b8daff; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #004085; font-size: 20px; margin-right: 10px;">💰</span>
        <span style="font-weight: bold; color: #004085; font-size: 16px;">Travel Expense Submission</span>
    </div>
    <p style="margin: 5px 0 10px 0;">{message_body}</p>
    <div style="background-color: #fff; border-left: 4px solid #007bff; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Next steps:</strong> Please review the expense submission and approve or return for revision as needed.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">Submitted by: {self.user_id.name}</span>
    </div>
</div>
"""
                if self.business_trip_id.expense_comments:
                    styled_message += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px;">
    <p style="margin: 0 0 5px 0; font-weight: bold;">Comments:</p>
    <p style="margin: 0; color: #333;">{self.business_trip_id.expense_comments}</p>
</div>
"""

            # Post the appropriate styled message
            self.message_post(
                body=styled_message,
                partner_ids=partners_to_notify
            )

        return True

    @api.depends('business_trip_id.trip_status')
    def _compute_exceptional_statuses(self):
        """Calculate exception statuses for display in the status bar"""
        for rec in self:
            trip_status = rec.business_trip_id.trip_status if rec.business_trip_id else False
            # Phase one
            rec.is_returned = (trip_status == 'returned')
            rec.is_rejected = (trip_status == 'rejected')

            # Phase two
            rec.is_expense_returned = (trip_status == 'expense_returned')

            # Add log for debugging
            if trip_status == 'expense_returned':
                _logger.info(f"Computing exceptional statuses for form {rec.id}: trip_status = {trip_status}, is_expense_returned set to True")

    def post_confidential_message(self, message, recipient_ids=None, attachment_ids=None):
        """Send confidential message in chatter that is only visible to specific recipients"""
        self.ensure_one()

        if not (self.is_manager or self.is_organizer or self.env.user.has_group('base.group_system')):
            raise ValidationError("You don't have permission to send confidential messages.")

        if not recipient_ids:
            # Default: send to manager and organizer
            recipient_ids = []
            if self.manager_id and self.manager_id.id != self.env.user.id:
                recipient_ids.append(self.manager_id.id)
            if self.organizer_id and self.organizer_id.id != self.env.user.id:
                recipient_ids.append(self.organizer_id.id)

        # Add current user to recipients list if not already included
        if self.env.user.id not in recipient_ids:
            recipient_ids.append(self.env.user.id)

        # Convert user IDs to partner IDs
        partner_ids = self.env['res.users'].browse(recipient_ids).mapped('partner_id').ids

        # Make sure current user's partner is in recipients list
        if self.env.user.partner_id.id not in partner_ids:
            partner_ids.append(self.env.user.partner_id.id)

        # Check for duplicate messages in the last 5 minutes
        recent_messages = self.env['mail.message'].search([
            ('model', '=', 'formio.form'),
            ('res_id', '=', self.id),
            ('confidential', '=', True),
            ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=5))
        ], limit=10, order='id desc')

        # Create a simplified version of the message for comparison
        # Remove HTML tags and normalize whitespace
        def simplify_for_comparison(text):
            # Simple removal of HTML tags for comparison
            import re
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        simplified_message = simplify_for_comparison(message)

        # Check if a similar message was recently sent
        for msg in recent_messages:
            simplified_existing = simplify_for_comparison(msg.body)
            if simplified_message == simplified_existing:
                _logger.info(f"Skipping duplicate confidential message for form {self.id}")
                return True

        # Add confidential label to message
        formatted_message = f'<div class="confidential-message">' \
                            f'<span style="background-color: #dc3545; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px;">' \
                            f'<i class="fa fa-lock"></i> Confidential</span>' \
                            f'<div style="margin-top: 10px;">{message}</div>' \
                            f'</div>'

        # Use internal note type (mail.mt_note) which is more restricted
        subtype_id = self.env.ref('mail.mt_note').id

        # Create a private message with explicit partner_ids
        # This message will only be visible to specified partners
        msg = self.with_context(
            mail_create_nosubscribe=True,
            mail_post_autofollow=False
        ).message_post(
            body=formatted_message,
            message_type='comment',
            subtype_id=subtype_id,
            partner_ids=partner_ids,
            attachment_ids=attachment_ids or [],
        )

        # Set message as confidential
        if msg:
            self.env['mail.message'].browse(msg.id).write({
                'confidential': True,
                'confidential_recipients': [(6, 0, partner_ids)],
                # Set model_name and res_id to restrict visibility
                'model': self._name,
                'res_id': self.id
            })

            # Add log for debugging
            _logger.info(f"Created confidential message ID: {msg.id} with recipients: {partner_ids}")

            # Force clear caches to ensure proper filtering
            self.env['mail.message'].invalidate_cache()
            self.env['mail.notification'].invalidate_cache()

        return True

    @api.depends_context('uid')
    def _compute_my_role(self):
        """Compute the current user's role for this business trip form"""
        current_user_id = self.env.user.id

        for record in self:
            roles = []

            # Check each possible role
            if record.user_id and record.user_id.id == current_user_id:
                roles.append('Employee')

            if record.manager_id and record.manager_id.id == current_user_id:
                roles.append('Manager')

            if record.organizer_id and record.organizer_id.id == current_user_id:
                roles.append('Organizer')

            if not roles and self.env.user.has_group('base.group_system'):
                roles.append('Admin')

            # Join multiple roles with a slash
            record.my_role = ' / '.join(roles) if roles else '-'

    @api.depends('business_trip_id.manager_max_budget', 'business_trip_id.organizer_planned_cost', 'business_trip_id.expense_total', 'business_trip_id.trip_status')
    def _compute_budget_difference(self):
        for record in self:
            if not record.business_trip_id:
                record.final_total_cost = 0.0
                record.budget_difference = 0.0
                record.budget_status = 'on_budget'
                continue
                
            # Calculate final total cost to the company
            # This is the sum of what the organizer planned/spent and what the employee spent out-of-pocket.
            final_total_cost = record.business_trip_id.organizer_planned_cost + record.business_trip_id.expense_total
            record.final_total_cost = final_total_cost

            # Calculate budget_difference: manager_max_budget vs final_total_cost
            # Positive: final_total_cost is under manager_max_budget
            # Negative: final_total_cost is over manager_max_budget
            budget_difference = record.business_trip_id.manager_max_budget - final_total_cost
            record.budget_difference = budget_difference

            # Calculate budget_status based on the new budget_difference
            if abs(budget_difference) < 0.01:  # Almost equal to zero (on budget relative to manager_max_budget)
                record.budget_status = 'on_budget'
            elif budget_difference > 0:  # final_total_cost < manager_max_budget (under manager's overall budget)
                record.budget_status = 'under_budget'
            else:  # budget_difference < 0 means final_total_cost > manager_max_budget (over manager's overall budget)
                record.budget_status = 'over_budget'


    @api.depends('business_trip_data_id.destination',
                 'business_trip_data_id.purpose',
                 'business_trip_data_id.travel_start_date',
                 'business_trip_data_id.travel_end_date')
    def _compute_has_trip_details(self):
        _logger.info(f"FORMIO_FORM_INHERIT: Starting _compute_has_trip_details for {len(self)} records.")
        for record in self:
            record.has_trip_details = False # Default to False
            btd = None
            if record.id:
                btd = self.env['business.trip.data'].search([('form_id', '=', record.id)], limit=1)

            if not btd and record.business_trip_data_id: # Fallback to the M2O field if search yields nothing but M2O is set
                btd = record.business_trip_data_id

            _logger.info(f"FORMIO_FORM_INHERIT: _compute_has_trip_details for record {record.id or 'NewID'}. BTD found: {btd.id if btd else 'None'}")

            if btd:
                has_required_fields = bool(
                    btd.destination and btd.destination.strip() and
                    btd.purpose and btd.purpose.strip() and
                    btd.travel_start_date and
                    btd.travel_end_date
                )
                record.has_trip_details = has_required_fields
                _logger.info(f"FORMIO_FORM_INHERIT: BTD Details - Dest: '{btd.destination}', Purp: '{btd.purpose}', Start: {btd.travel_start_date}, End: {btd.travel_end_date}. Resulting has_trip_details: {record.has_trip_details}")
            else:
                _logger.info(f"FORMIO_FORM_INHERIT: No BTD found for record {record.id or 'NewID'}, has_trip_details remains False.")

    def action_show_missing_details_warning(self):
        self.ensure_one()
        missing_fields = []

        trip_data = None
        if self.id: # Check if record exists (has an ID)
            trip_data = self.env['business.trip.data'].search([('form_id', '=', self.id)], limit=1)
        if not trip_data and self.business_trip_data_id: # Fallback to M2O field
             trip_data = self.business_trip_data_id

        if not trip_data:
            missing_fields.append("Trip Data Record (system error, data not linked)")
        else:
            if not trip_data.destination or not trip_data.destination.strip():
                missing_fields.append('Destination')
            if not trip_data.purpose or not trip_data.purpose.strip():
                missing_fields.append('Purpose')
            if not trip_data.travel_start_date:
                missing_fields.append('Start Date')
            if not trip_data.travel_end_date: # End date is now always required
                missing_fields.append('End Date')

        missing_fields_str = ', '.join(missing_fields)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Missing Trip Details',
                'message': f'Please ensure all required trip details are provided in the form: {missing_fields_str}. If the form was submitted, this data should populate automatically. You might need to re-submit the form if data is still missing after checking the submission.',
                'sticky': True,
                'type': 'warning',
            }
        }

    @api.depends('travel_duration')
    def _compute_travel_display(self):
        _logger.info("FORMIO_FORM_INHERIT: Starting _compute_travel_display...")
        for record in self:
            # Initialize to 0
            record.travel_duration_days = 0
            record.travel_duration_hours = 0 # Always 0 as hourly trips are removed

            # Ensure travel_duration is a number, default to 0.0 if None or invalid
            current_travel_duration = record.travel_duration
            if not isinstance(current_travel_duration, (int, float)):
                _logger.warning(f"FORMIO_FORM_INHERIT: travel_duration is not a number ({current_travel_duration}) for record {record.id or 'NewID'}. Defaulting to 0.")
                current_travel_duration = 0.0

            record.travel_duration_days = int(current_travel_duration)
            _logger.info(f"FORMIO_FORM_INHERIT: _compute_travel_display for record {record.id or 'NewID'} - travel_duration: {current_travel_duration}, calculated travel_duration_days: {record.travel_duration_days}")

    def action_edit_returned_form(self):
        """Open the formio form for editing when it's in returned status by temporarily changing state to DRAFT"""
        self.ensure_one()

        # Check if the user is the owner of the form
        if self.user_id.id != self.env.user.id:
            raise ValidationError("Only the owner of this form can edit it.")

        # Check that the form is in returned status
        if self.trip_status != 'returned':
            raise ValidationError("This action is only available for forms in 'Returned to Employee' status.")

        # Temporarily change the state to DRAFT to allow editing
        self.with_context(system_edit=True).write({
            'state': 'DRAFT',
            'edit_in_returned_state': True  # Mark this form as being edited in returned state
        })

        # Return the action to open the form in edit mode
        action = self.action_view_formio()
        action['context'] = dict(self.env.context)
        action['context'].update({
            'returned_form_edit': True  # Flag to know this is a special edit session
        })

        return action


    @api.depends('first_name', 'last_name')
    def _compute_full_name(self):
        for record in self:
            names = []
            if record.first_name:
                names.append(record.first_name)
            if record.last_name:
                names.append(record.last_name)
            record.full_name = ' '.join(names) if names else False

    @api.model
    def update_existing_transport_data(self):
        """
        Update existing forms with processed transport data.
        This can be called from a server action to fix existing records.
        """
        forms = self.search([('transport_means_json', '!=', False)])
        _logger.info(f"Updating transport data for {len(forms)} existing forms")

        for form in forms:
            try:
                form._process_transport_means_json()
                _logger.info(f"Successfully updated transport data for form {form.id}")
            except Exception as e:
                _logger.error(f"Error updating transport data for form {form.id}: {e}")

        return True

    @api.model
    def fix_submission_data_for_all_forms(self):
        """
        Fix and update submission data extraction for all forms.
        This can be called from a server action to re-process all form data.
        """
        forms = self.search([('submission_data', '!=', False), ('state', '=', 'COMPLETE')])
        total_forms = len(forms)
        _logger.info(f"Re-processing submission data for {total_forms} existing forms")

        processed = 0
        errors = 0

        for form in forms:
            try:
                _logger.info(f"Processing form {form.id} with title: {form.title}")

                # Find or create business.trip.data record for this form
                trip_data = self.env['business.trip.data'].search([('form_id', '=', form.id)], limit=1)
                if not trip_data:
                    _logger.info(f"Creating new business.trip.data record for form {form.id}")
                    trip_data = self.env['business.trip.data'].create({
                        'form_id': form.id,
                    })

                # Process submission data to extract values
                if form.submission_data:
                    submission_data = json.loads(form.submission_data)
                    result = trip_data.process_submission_data(submission_data)

                    if result:
                        _logger.info(f"Successfully extracted data to business.trip.data record {trip_data.id} for form {form.id}")
                    else:
                        _logger.warning(f"Failed to extract data to business.trip.data record {trip_data.id} for form {form.id}")

                # Note: form_data_display fields are now computed automatically via related fields

                processed += 1
                _logger.info(f"Successfully re-processed form {form.id} ({processed}/{total_forms})")
            except Exception as e:
                errors += 1
                _logger.error(f"Error re-processing form {form.id}: {e}", exc_info=True)

        _logger.info(f"Re-processing complete. Processed: {processed}, Errors: {errors}")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Re-processing complete'),
                'message': _('%s forms processed, %s errors') % (processed, errors),
                'sticky': False,
            }
        }

    @api.depends(
        'business_trip_data_id', # Add direct dependency on the M2O field itself
        'business_trip_data_id.transport_means_json',
        'business_trip_data_id.return_transport_means_json',
        'business_trip_data_id.use_rental_car',
        'business_trip_data_id.use_company_car',
        'business_trip_data_id.use_personal_car',
        'business_trip_data_id.use_train',
        'business_trip_data_id.use_airplane',
        'business_trip_data_id.use_bus',
        'business_trip_data_id.use_return_rental_car',
        'business_trip_data_id.use_return_company_car',
        'business_trip_data_id.use_return_personal_car',
        'business_trip_data_id.use_return_train',
        'business_trip_data_id.use_return_airplane',
        'business_trip_data_id.use_return_bus',
        # Rental Car (Outbound)
        'business_trip_data_id.rental_car_pickup_point',
        'business_trip_data_id.rental_car_pickup_date',
        'business_trip_data_id.rental_car_pickup_flexible',
        'business_trip_data_id.rental_car_dropoff_point',
        'business_trip_data_id.rental_car_dropoff_date',
        'business_trip_data_id.rental_car_dropoff_flexible',
        'business_trip_data_id.rental_car_type',
        'business_trip_data_id.rental_car_credit_card',
        'business_trip_data_id.rental_car_kilometer_limit',
        'business_trip_data_id.rental_car_unlimited_km',
        'business_trip_data_id.rental_car_preferences',
        # Rental Car (Return)
        'business_trip_data_id.return_rental_car_pickup_point',
        'business_trip_data_id.return_rental_car_pickup_date',
        'business_trip_data_id.return_rental_car_pickup_flexible',
        'business_trip_data_id.return_rental_car_dropoff_point',
        'business_trip_data_id.return_rental_car_dropoff_date',
        'business_trip_data_id.return_rental_car_dropoff_flexible',
        'business_trip_data_id.return_rental_car_type',
        'business_trip_data_id.return_rental_car_credit_card',
        'business_trip_data_id.return_rental_car_kilometer_limit',
        'business_trip_data_id.return_rental_car_unlimited_km',
        'business_trip_data_id.return_rental_car_preferences',
        # Train (Outbound)
        'business_trip_data_id.train_departure_city',
        'business_trip_data_id.train_departure_station',
        'business_trip_data_id.train_arrival_station',
        'business_trip_data_id.train_departure_date',
        'business_trip_data_id.train_arrival_date',
        'business_trip_data_id.train_departure_flexible',
        'business_trip_data_id.train_arrival_flexible',
        # Train (Return)
        'business_trip_data_id.return_train_departure_city',
        'business_trip_data_id.return_train_departure_station',
        'business_trip_data_id.return_train_arrival_station',
        'business_trip_data_id.return_train_departure_date',
        'business_trip_data_id.return_train_arrival_date',
        'business_trip_data_id.return_train_departure_flexible',
        'business_trip_data_id.return_train_arrival_flexible',
        # Airplane (Outbound)
        'business_trip_data_id.airplane_departure_airport',
        'business_trip_data_id.airplane_arrival_airport',
        'business_trip_data_id.airplane_departure_date',
        'business_trip_data_id.airplane_departure_flexible',
        'business_trip_data_id.airplane_arrival_flexible',
        'business_trip_data_id.airplane_baggage_type',
        'business_trip_data_id.airplane_preferences',
        # Airplane (Return)
        'business_trip_data_id.return_airplane_departure_airport',
        'business_trip_data_id.return_airplane_destination_airport',
        'business_trip_data_id.return_airplane_departure_date',
        'business_trip_data_id.return_airplane_departure_flexible',
        'business_trip_data_id.return_airplane_destination_flexible',
        'business_trip_data_id.return_airplane_baggage_type',
        'business_trip_data_id.return_airplane_preferences',
        # Bus (Outbound)
        'business_trip_data_id.bus_departure_city',
        'business_trip_data_id.bus_departure_terminal',
        'business_trip_data_id.bus_arrival_terminal',
        'business_trip_data_id.bus_departure_date',
        'business_trip_data_id.bus_arrival_date',
        'business_trip_data_id.bus_departure_flexible',
        'business_trip_data_id.bus_arrival_flexible',
        # Bus (Return)
        'business_trip_data_id.return_bus_departure_city',
        'business_trip_data_id.return_bus_departure_station',
        'business_trip_data_id.return_bus_arrival_station',
        'business_trip_data_id.return_bus_departure_date',
        'business_trip_data_id.return_bus_departure_flexible',
        'business_trip_data_id.return_bus_arrival_date',
        'business_trip_data_id.return_bus_arrival_flexible'
    )
    def _compute_transportation_display_data(self):
        _logger.info("COMPUTE_TRANSPORT_DISPLAY: Starting computation for transportation display data.")
        for record in self:
            current_has_any_transportation = False
            current_has_any_return_transportation = False

            trip_data = record.business_trip_data_id # Prioritize direct link
            if not trip_data and record.id: # Fallback to search if direct link is empty
                _logger.info(f"COMPUTE_TRANSPORT_DISPLAY: BTD not directly linked for form {record.id}. Searching...")
                trip_data = self.env['business.trip.data'].search([('form_id', '=', record.id)], limit=1)
                if trip_data:
                    _logger.info(f"COMPUTE_TRANSPORT_DISPLAY: Found BTD {trip_data.id} for form {record.id} via search.")
                else:
                    _logger.info(f"COMPUTE_TRANSPORT_DISPLAY: No BTD found for form {record.id} even after search.")

            if not trip_data:
                record.transportation_display_data = "{}"
                record.return_transportation_display_data = "{}"
                record.has_any_transportation = False
                record.has_any_return_transportation = False
                _logger.info(f"COMPUTE_TRANSPORT_DISPLAY: No trip_data for form {record.id}. Setting defaults and skipping further processing for this record.")
                continue

            _logger.info(f"COMPUTE_TRANSPORT_DISPLAY: Processing form {record.id} with BTD {trip_data.id} (Name: {trip_data.display_name if hasattr(trip_data, 'display_name') else 'N/A'}).")

            transport_data = {}
            # --- Outbound transportation ---
            if trip_data.use_rental_car:
                current_has_any_transportation = True
                transport_data['rental_car'] = {
                    'pickup_point': trip_data.rental_car_pickup_point,
                    'pickup_date': str(trip_data.rental_car_pickup_date) if trip_data.rental_car_pickup_date else None,
                    'pickup_flexible': trip_data.rental_car_pickup_flexible,
                    'dropoff_point': trip_data.rental_car_dropoff_point,
                    'dropoff_date': str(trip_data.rental_car_dropoff_date) if trip_data.rental_car_dropoff_date else None,
                    'dropoff_flexible': trip_data.rental_car_dropoff_flexible,
                    'type': trip_data.rental_car_type,
                    'credit_card': trip_data.rental_car_credit_card,
                    'kilometer_limit': trip_data.rental_car_kilometer_limit,
                    'unlimited_km': trip_data.rental_car_unlimited_km,
                    'preferences': trip_data.rental_car_preferences,
                }
            if trip_data.use_company_car:
                current_has_any_transportation = True
                transport_data['company_car'] = {'selected': True}
            if trip_data.use_personal_car:
                current_has_any_transportation = True
                transport_data['personal_car'] = {'selected': True}
            if trip_data.use_train:
                current_has_any_transportation = True
                transport_data['train'] = {
                    'departure_city': trip_data.train_departure_city,
                    'departure_station': trip_data.train_departure_station,
                    'departure_date': str(trip_data.train_departure_date) if trip_data.train_departure_date else None,
                    'departure_flexible': trip_data.train_departure_flexible,
                    'arrival_station': trip_data.train_arrival_station,
                    'arrival_date': str(trip_data.train_arrival_date) if trip_data.train_arrival_date else None,
                    'arrival_flexible': trip_data.train_arrival_flexible,
                }
            if trip_data.use_airplane:
                current_has_any_transportation = True
                transport_data['airplane'] = {
                    'departure_airport': trip_data.airplane_departure_airport,
                    'departure_date': str(trip_data.airplane_departure_date) if trip_data.airplane_departure_date else None,
                    'departure_flexible': trip_data.airplane_departure_flexible,
                    'arrival_airport': trip_data.airplane_arrival_airport,
                    'arrival_flexible': trip_data.airplane_arrival_flexible,
                    'baggage_type': trip_data.airplane_baggage_type,
                    'preferences': trip_data.airplane_preferences,
                }
            if trip_data.use_bus:
                current_has_any_transportation = True
                transport_data['bus'] = {
                    'departure_city': trip_data.bus_departure_city,
                    'departure_terminal': trip_data.bus_departure_terminal,
                    'departure_date': str(trip_data.bus_departure_date) if trip_data.bus_departure_date else None,
                    'departure_flexible': trip_data.bus_departure_flexible,
                    'arrival_terminal': trip_data.bus_arrival_terminal,
                    'arrival_date': str(trip_data.bus_arrival_date) if trip_data.bus_arrival_date else None,
                    'arrival_flexible': trip_data.bus_arrival_flexible,
                }

            return_transport_data = {}
            # --- Return transportation ---
            if trip_data.use_return_rental_car:
                current_has_any_return_transportation = True
                return_transport_data['rental_car'] = {
                    'pickup_point': trip_data.return_rental_car_pickup_point,
                    'pickup_date': str(trip_data.return_rental_car_pickup_date) if trip_data.return_rental_car_pickup_date else None,
                    'pickup_flexible': trip_data.return_rental_car_pickup_flexible,
                    'dropoff_point': trip_data.return_rental_car_dropoff_point,
                    'dropoff_date': str(trip_data.return_rental_car_dropoff_date) if trip_data.return_rental_car_dropoff_date else None,
                    'dropoff_flexible': trip_data.return_rental_car_dropoff_flexible,
                    'type': trip_data.return_rental_car_type,
                    'credit_card': trip_data.return_rental_car_credit_card,
                    'kilometer_limit': trip_data.return_rental_car_kilometer_limit,
                    'unlimited_km': trip_data.return_rental_car_unlimited_km,
                    'preferences': trip_data.return_rental_car_preferences,
                }
            if trip_data.use_return_company_car:
                current_has_any_return_transportation = True
                return_transport_data['company_car'] = {'selected': True}
            if trip_data.use_return_personal_car:
                current_has_any_return_transportation = True
                return_transport_data['personal_car'] = {'selected': True}
            if trip_data.use_return_train:
                current_has_any_return_transportation = True
                return_transport_data['train'] = {
                    'departure_city': trip_data.return_train_departure_city,
                    'departure_station': trip_data.return_train_departure_station,
                    'departure_date': str(trip_data.return_train_departure_date) if trip_data.return_train_departure_date else None,
                    'departure_flexible': trip_data.return_train_departure_flexible,
                    'arrival_station': trip_data.return_train_arrival_station,
                    'arrival_date': str(trip_data.return_train_arrival_date) if trip_data.return_train_arrival_date else None,
                    'arrival_flexible': trip_data.return_train_arrival_flexible,
                }
            if trip_data.use_return_airplane:
                current_has_any_return_transportation = True
                return_transport_data['airplane'] = {
                    'departure_airport': trip_data.return_airplane_departure_airport,
                    'departure_date': str(trip_data.return_airplane_departure_date) if trip_data.return_airplane_departure_date else None,
                    'departure_flexible': trip_data.return_airplane_departure_flexible,
                    'destination_airport': trip_data.return_airplane_destination_airport,
                    'destination_flexible': trip_data.return_airplane_destination_flexible,
                    'baggage_type': trip_data.return_airplane_baggage_type,
                    'preferences': trip_data.return_airplane_preferences,
                }
            if trip_data.use_return_bus:
                current_has_any_return_transportation = True
                return_transport_data['bus'] = {
                    'departure_city': trip_data.return_bus_departure_city,
                    'departure_station': trip_data.return_bus_departure_station,
                    'departure_date': str(trip_data.return_bus_departure_date) if trip_data.return_bus_departure_date else None,
                    'departure_flexible': trip_data.return_bus_departure_flexible,
                    'arrival_station': trip_data.return_bus_arrival_station,
                    'arrival_date': str(trip_data.return_bus_arrival_date) if trip_data.return_bus_arrival_date else None,
                    'arrival_flexible': trip_data.return_bus_arrival_flexible,
                }

            record.transportation_display_data = json.dumps(transport_data)
            record.return_transportation_display_data = json.dumps(return_transport_data)
            record.has_any_transportation = current_has_any_transportation
            record.has_any_return_transportation = current_has_any_return_transportation
            _logger.info(f"COMPUTE_TRANSPORT_DISPLAY: Form {record.id}, BTD {trip_data.id} - Outbound: {current_has_any_transportation}, Return: {current_has_any_return_transportation}. JSON Out: {record.transportation_display_data[:200]}, JSON Return: {record.return_transportation_display_data[:200]}")


    @api.depends('business_trip_data_id.travel_start_date',
                 'business_trip_data_id.travel_end_date')
    def _compute_travel_dates_display(self):
        """Compute a display-friendly string showing travel dates from business.trip.data"""
        for record in self:
            trip_data = self.env['business.trip.data'].search([('form_id', '=', record.id)], limit=1)

            if not trip_data or not trip_data.travel_start_date:
                record.travel_dates_display = ""
                continue

            start_date_str = fields.Date.to_string(trip_data.travel_start_date)

            # Always show start and end dates for multi-day trips
            if trip_data.travel_end_date:
                end_date_str = fields.Date.to_string(trip_data.travel_end_date)
                if start_date_str == end_date_str: # Single day trip
                    record.travel_dates_display = start_date_str
                else: # Multi-day trip
                    record.travel_dates_display = f"{start_date_str} → {end_date_str}"
            else: # Only start date available (should not happen if has_trip_details is correct)
                record.travel_dates_display = start_date_str

    def _format_float_time(self, time_float):
        """Format float time (e.g. 9.5) to string (09:30)"""
        if not time_float and time_float != 0:
            return ""

        hours = int(time_float)
        minutes = int((time_float % 1) * 60)
        return f"{hours:02d}:{minutes:02d}"

    # New accommodation fields - computed from business.trip.data for display
    accommodation_residence_city = fields.Char(string='Residence City', compute='_compute_accommodation_fields', store=False)
    accommodation_check_in_date = fields.Date(string='Check-in Date', compute='_compute_accommodation_fields', store=False)
    accommodation_check_out_date = fields.Date(string='Check-out Date', compute='_compute_accommodation_fields', store=False)
    accommodation_number_of_people = fields.Integer(string='Number of People', compute='_compute_accommodation_fields', store=False)
    accommodation_need_24h_reception = fields.Selection([('yes', 'Yes'), ('no', 'No')], string='Need 24h Reception',
                                                       compute='_compute_accommodation_fields', store=False)
    accommodation_points_of_interest = fields.Text(string='Points of Interest', compute='_compute_accommodation_fields', store=False)
    accommodation_needed = fields.Selection([('yes', 'Yes'), ('no', 'No')], string='Accommodation Needed',
                                           compute='_compute_accommodation_fields', store=False)
    accommodation_accompanying_persons_display = fields.Text(string='Accompanying Persons (Display)', compute='_compute_accommodation_fields', store=False, help="List of accompanying persons with their document status for display.")
    accommodation_accompanying_persons_json = fields.Text(string='Accompanying Persons (JSON)', compute='_compute_accommodation_fields', store=False, help="JSON representation of accompanying persons for UI consumption.")

    @api.depends(
        'business_trip_data_id.accommodation_residence_city',
        'business_trip_data_id.accommodation_check_in_date',
        'business_trip_data_id.accommodation_check_out_date',
        'business_trip_data_id.accommodation_number_of_people',
        'business_trip_data_id.accommodation_need_24h_reception',
        'business_trip_data_id.accommodation_points_of_interest',
        'business_trip_data_id.accommodation_needed',
        'business_trip_data_id.accompanying_person_ids',
        'business_trip_data_id.accompanying_person_ids.full_name', # For display text
        'business_trip_data_id.accompanying_person_ids.identity_document_filename' # For display text and JSON
    )
    def _compute_accommodation_fields(self):
        """Compute accommodation-related fields from business.trip.data model"""
        for record in self:
            # Find linked business.trip.data record
            trip_data = self.env['business.trip.data'].search([('form_id', '=', record.id)], limit=1)

            if trip_data:
                record.accommodation_residence_city = trip_data.accommodation_residence_city
                record.accommodation_check_in_date = trip_data.accommodation_check_in_date
                record.accommodation_check_out_date = trip_data.accommodation_check_out_date
                record.accommodation_number_of_people = trip_data.accommodation_number_of_people
                record.accommodation_need_24h_reception = trip_data.accommodation_need_24h_reception
                record.accommodation_points_of_interest = trip_data.accommodation_points_of_interest
                record.accommodation_needed = trip_data.accommodation_needed

                # Process accompanying persons from the One2many field
                accompanying_persons_display = []
                accompanying_persons_json_data = []

                for person in trip_data.accompanying_person_ids:
                    name = person.full_name
                    doc_status = " (Document Attached)" if person.identity_document_filename else " (No Document)"
                    accompanying_persons_display.append(f"{name}{doc_status}")
                    accompanying_persons_json_data.append({
                        'full_name_acc': name,
                        'accompanying_identity_document_acc_filename': person.identity_document_filename,
                    })

                record.accommodation_accompanying_persons_display = "\n".join(accompanying_persons_display)
                if not accompanying_persons_display:
                    record.accommodation_accompanying_persons_display = "No accompanying persons specified."
                _logger.info(f"Accompanying Persons for form {record.id} (display): {record.accommodation_accompanying_persons_display}")

                record.accommodation_accompanying_persons_json = json.dumps(accompanying_persons_json_data)
                _logger.info(f"Accompanying Persons for form {record.id} (JSON): {record.accommodation_accompanying_persons_json[:200]}...")

            else:
                record.accommodation_residence_city = False
                record.accommodation_check_in_date = False
                record.accommodation_check_out_date = False
                record.accommodation_number_of_people = 0
                record.accommodation_need_24h_reception = False
                record.accommodation_points_of_interest = False
                record.accommodation_needed = False
                record.accommodation_accompanying_persons_display = ""
                record.accommodation_accompanying_persons_json = json.dumps([])

    # Add a related field to business.trip.data for easier access if needed
    business_trip_data_id = fields.Many2one(
        'business.trip.data',
        string='Business Trip Data Link',
        store=False,
        help="Technical field to link to the business.trip.data record."
    )

    # Related fields from business.trip.data for Rental Car details
    rental_car_pickup_date = fields.Date(string='Rental Car Pickup Date', related='business_trip_data_id.rental_car_pickup_date', readonly=True, store=False)
    rental_car_pickup_flexible = fields.Boolean(string='Pickup Flexible', related='business_trip_data_id.rental_car_pickup_flexible', readonly=True, store=False)
    rental_car_pickup_point = fields.Char(string='Pickup Point', related='business_trip_data_id.rental_car_pickup_point', readonly=True, store=False)
    rental_car_dropoff_point = fields.Char(string='Dropoff Point', related='business_trip_data_id.rental_car_dropoff_point', readonly=True, store=False)
    rental_car_dropoff_date = fields.Date(string='Rental Car Dropoff Date', related='business_trip_data_id.rental_car_dropoff_date', readonly=True, store=False)
    rental_car_dropoff_flexible = fields.Boolean(string='Dropoff Flexible', related='business_trip_data_id.rental_car_dropoff_flexible', readonly=True, store=False)
    rental_car_credit_card = fields.Selection(string='Credit Card Available', related='business_trip_data_id.rental_car_credit_card', readonly=True, store=False)
    rental_car_type = fields.Selection(string='Rental Type', related='business_trip_data_id.rental_car_type', readonly=True, store=False)
    rental_car_drivers_license = fields.Binary(string='Driver\'s License', related='business_trip_data_id.rental_car_drivers_license', readonly=True, store=False)
    rental_car_drivers_license_filename = fields.Char(string='Driver\'s License Filename', related='business_trip_data_id.rental_car_drivers_license_filename', readonly=True, store=False)
    rental_car_kilometer_limit = fields.Integer(string='Kilometer Limit', related='business_trip_data_id.rental_car_kilometer_limit', readonly=True, store=False)
    rental_car_unlimited_km = fields.Boolean(string='Unlimited Kilometers', related='business_trip_data_id.rental_car_unlimited_km', readonly=True, store=False)
    rental_car_preferences = fields.Text(string='Rental Car Preferences', related='business_trip_data_id.rental_car_preferences', readonly=True, store=False)

    # Related fields from business.trip.data for Return Rental Car details
    return_rental_car_pickup_date = fields.Date(string='Return Rental Car Pickup Date', related='business_trip_data_id.return_rental_car_pickup_date', readonly=True, store=False)
    return_rental_car_pickup_flexible = fields.Boolean(string='Return Pickup Flexible', related='business_trip_data_id.return_rental_car_pickup_flexible', readonly=True, store=False)
    return_rental_car_pickup_point = fields.Char(string='Return Pickup Point', related='business_trip_data_id.return_rental_car_pickup_point', readonly=True, store=False)
    return_rental_car_dropoff_point = fields.Char(string='Return Dropoff Point', related='business_trip_data_id.return_rental_car_dropoff_point', readonly=True, store=False)
    return_rental_car_dropoff_date = fields.Date(string='Return Rental Car Dropoff Date', related='business_trip_data_id.return_rental_car_dropoff_date', readonly=True, store=False)
    return_rental_car_dropoff_flexible = fields.Boolean(string='Return Dropoff Flexible', related='business_trip_data_id.return_rental_car_dropoff_flexible', readonly=True, store=False)
    return_rental_car_credit_card = fields.Selection(string='Return Credit Card Available', related='business_trip_data_id.return_rental_car_credit_card', readonly=True, store=False)
    return_rental_car_type = fields.Selection(string='Return Rental Type', related='business_trip_data_id.return_rental_car_type', readonly=True, store=False)
    return_rental_car_drivers_license = fields.Binary(string='Return Driver\'s License', related='business_trip_data_id.return_rental_car_drivers_license', readonly=True, store=False)
    return_rental_car_drivers_license_filename = fields.Char(string='Return Driver\'s License Filename', related='business_trip_data_id.return_rental_car_drivers_license_filename', readonly=True, store=False)
    return_rental_car_kilometer_limit = fields.Integer(string='Return Kilometer Limit', related='business_trip_data_id.return_rental_car_kilometer_limit', readonly=True, store=False)
    return_rental_car_unlimited_km = fields.Boolean(string='Return Unlimited Kilometers', related='business_trip_data_id.return_rental_car_unlimited_km', readonly=True, store=False)
    return_rental_car_preferences = fields.Text(string='Return Rental Car Preferences', related='business_trip_data_id.return_rental_car_preferences', readonly=True, store=False)

    # Related fields from business.trip.data for Train details
    train_departure_city = fields.Char(string='Train Departure City', related='business_trip_data_id.train_departure_city', readonly=True, store=False)
    train_departure_station = fields.Char(string='Train Departure Station', related='business_trip_data_id.train_departure_station', readonly=True, store=False)
    train_arrival_station = fields.Char(string='Train Arrival Station', related='business_trip_data_id.train_arrival_station', readonly=True, store=False)
    train_departure_date = fields.Date(string='Train Departure Date', related='business_trip_data_id.train_departure_date', readonly=True, store=False)
    train_departure_flexible = fields.Boolean(string='Train Departure Flexible', related='business_trip_data_id.train_departure_flexible', readonly=True, store=False)
    train_arrival_date = fields.Date(string='Train Arrival Date', related='business_trip_data_id.train_arrival_date', readonly=True, store=False)
    train_arrival_flexible = fields.Boolean(string='Train Arrival Flexible', related='business_trip_data_id.train_arrival_flexible', readonly=True, store=False)

    # Related fields from business.trip.data for Return Train details
    return_train_departure_city = fields.Char(string='Return Train Departure City', related='business_trip_data_id.return_train_departure_city', readonly=True, store=False)
    return_train_departure_station = fields.Char(string='Return Train Departure Station', related='business_trip_data_id.return_train_departure_station', readonly=True, store=False)
    return_train_arrival_station = fields.Char(string='Return Train Arrival Station', related='business_trip_data_id.return_train_arrival_station', readonly=True, store=False)
    return_train_departure_date = fields.Date(string='Return Train Departure Date', related='business_trip_data_id.return_train_departure_date', readonly=True, store=False)
    return_train_departure_flexible = fields.Boolean(string='Return Train Departure Flexible', related='business_trip_data_id.return_train_departure_flexible', readonly=True, store=False)
    return_train_arrival_date = fields.Date(string='Return Train Arrival Date', related='business_trip_data_id.return_train_arrival_date', readonly=True, store=False)
    return_train_arrival_flexible = fields.Boolean(string='Return Train Arrival Flexible', related='business_trip_data_id.return_train_arrival_flexible', readonly=True, store=False)

    # Related fields from business.trip.data for Airplane details
    airplane_departure_airport = fields.Char(string='Departure Airport', related='business_trip_data_id.airplane_departure_airport', readonly=True, store=False)
    airplane_departure_date = fields.Date(string='Airplane Departure Date', related='business_trip_data_id.airplane_departure_date', readonly=True, store=False)
    airplane_departure_flexible = fields.Boolean(string='Airplane Departure Flexible', related='business_trip_data_id.airplane_departure_flexible', readonly=True, store=False)
    airplane_arrival_airport = fields.Char(string='Arrival Airport', related='business_trip_data_id.airplane_arrival_airport', readonly=True, store=False)
    airplane_arrival_flexible = fields.Boolean(string='Airplane Arrival Flexible', related='business_trip_data_id.airplane_arrival_flexible', readonly=True, store=False)
    airplane_baggage_type = fields.Selection(string='Baggage Type', related='business_trip_data_id.airplane_baggage_type', readonly=True, store=False)
    airplane_preferences = fields.Text(string='Airplane Preferences', related='business_trip_data_id.airplane_preferences', readonly=True, store=False)

    # Related fields from business.trip.data for Return Airplane details
    return_airplane_departure_airport = fields.Char(string='Return Departure Airport', related='business_trip_data_id.return_airplane_departure_airport', readonly=True, store=False)
    return_airplane_departure_date = fields.Date(string='Return Airplane Departure Date', related='business_trip_data_id.return_airplane_departure_date', readonly=True, store=False)
    return_airplane_departure_flexible = fields.Boolean(string='Return Airplane Departure Flexible', related='business_trip_data_id.return_airplane_departure_flexible', readonly=True, store=False)
    return_airplane_destination_airport = fields.Char(string='Return Destination Airport', related='business_trip_data_id.return_airplane_destination_airport', readonly=True, store=False)
    return_airplane_destination_flexible = fields.Boolean(string='Return Airplane Destination Flexible', related='business_trip_data_id.return_airplane_destination_flexible', readonly=True, store=False)
    return_airplane_baggage_type = fields.Selection(string='Return Baggage Type', related='business_trip_data_id.return_airplane_baggage_type', readonly=True, store=False)
    return_airplane_preferences = fields.Text(string='Return Airplane Preferences', related='business_trip_data_id.return_airplane_preferences', readonly=True, store=False)

    # Related fields from business.trip.data for Bus details
    bus_departure_city = fields.Char(string='Bus Departure City', related='business_trip_data_id.bus_departure_city', readonly=True, store=False)
    bus_departure_terminal = fields.Char(string='Bus Departure Terminal', related='business_trip_data_id.bus_departure_terminal', readonly=True, store=False)
    bus_arrival_terminal = fields.Char(string='Bus Arrival Terminal', related='business_trip_data_id.bus_arrival_terminal', readonly=True, store=False)
    bus_departure_date = fields.Date(string='Bus Departure Date', related='business_trip_data_id.bus_departure_date', readonly=True, store=False)
    bus_arrival_date = fields.Date(string='Bus Arrival Date', related='business_trip_data_id.bus_arrival_date', readonly=True, store=False)
    bus_departure_flexible = fields.Boolean(string='Bus Departure Flexible', related='business_trip_data_id.bus_departure_flexible', readonly=True, store=False)
    bus_arrival_flexible = fields.Boolean(string='Bus Arrival Flexible', related='business_trip_data_id.bus_arrival_flexible', readonly=True, store=False)

    # Related fields from business.trip.data for Return Bus details
    return_bus_departure_city = fields.Char(string='Return Bus Departure City', related='business_trip_data_id.return_bus_departure_city', readonly=True, store=False)
    return_bus_departure_station = fields.Char(string='Return Bus Departure Station', related='business_trip_data_id.return_bus_departure_station', readonly=True, store=False)
    return_bus_arrival_station = fields.Char(string='Return Bus Arrival Station', related='business_trip_data_id.return_bus_arrival_station', readonly=True, store=False)
    return_bus_departure_date = fields.Date(string='Return Bus Departure Date', related='business_trip_data_id.return_bus_departure_date', readonly=True, store=False)
    return_bus_departure_flexible = fields.Boolean(string='Return Bus Departure Flexible', related='business_trip_data_id.return_bus_departure_flexible', readonly=True, store=False)
    return_bus_arrival_date = fields.Date(string='Return Bus Arrival Date', related='business_trip_data_id.return_bus_arrival_date', readonly=True, store=False)
    return_bus_arrival_flexible = fields.Boolean(string='Return Bus Arrival Flexible', related='business_trip_data_id.return_bus_arrival_flexible', readonly=True, store=False)


    # Form data display fields for the Form Data tab
    form_data_json = fields.Text(string="Form Data JSON", compute="_compute_form_data_json", store=False)
    form_data_requester_name = fields.Char(string="Requester Name", related='business_trip_data_id.full_name', readonly=True, store=False)
    form_data_approving_colleague_name = fields.Char(string="Approving Colleague Name", related='business_trip_data_id.approving_colleague_name', readonly=True, store=False)

    # New computed fields for "Request Form Data" tab - Phase 1 (Trip Types & Accommodation)
    form_data_trip_duration_type_display = fields.Char(string="Trip Duration Type", compute='_compute_form_data_trip_duration_type_display', store=False)
    form_data_trip_type_display = fields.Char(string="Trip Type (Display)", compute='_compute_form_data_trip_type_display', store=False)

    # Basic Trip Information display fields
    form_data_destination_display = fields.Char(string="Destination (Display)", related='business_trip_data_id.destination', readonly=True, store=False)
    form_data_purpose_display = fields.Char(string="Purpose of Trip (Display)", related='business_trip_data_id.purpose', readonly=True, store=False) # MODIFIED: Added display field
    form_data_travel_start_date_display = fields.Date(string="Travel Start Date", related='business_trip_data_id.travel_start_date', readonly=True, store=False)
    form_data_travel_end_date_display = fields.Date(string="Travel End Date", related='business_trip_data_id.travel_end_date', readonly=True, store=False)

    form_data_accommodation_needed_display = fields.Char(string="Accommodation Needed (Display)", compute='_compute_form_data_accommodation_needed_display', store=False)
    form_data_accommodation_number_of_people_display = fields.Integer(string="Number of People (Accommodation)", related='business_trip_data_id.accommodation_number_of_people', readonly=True, store=False)
    form_data_accommodation_residence_city_display = fields.Char(string="Residence City (Accommodation)", related='business_trip_data_id.accommodation_residence_city', readonly=True, store=False)
    form_data_accommodation_check_in_date_display = fields.Date(string="Check-in Date (Accommodation)", related='business_trip_data_id.accommodation_check_in_date', readonly=True, store=False)
    form_data_accommodation_check_out_date_display = fields.Date(string="Check-out Date (Accommodation)", related='business_trip_data_id.accommodation_check_out_date', readonly=True, store=False)
    form_data_accommodation_points_of_interest_display = fields.Text(string="Points of Interest (Accommodation)", related='business_trip_data_id.accommodation_points_of_interest', readonly=True, store=False)
    form_data_accommodation_need_24h_reception_display = fields.Char(string="Need 24h Reception (Accommodation)", compute='_compute_form_data_accommodation_need_24h_reception_display', store=False)
    form_data_accompanying_persons_summary_display = fields.Html(string="Accompanying Persons Summary", compute='_compute_accompanying_persons_summary', store=False)

    # New computed fields for Airplane details in Request Form Data tab
    form_data_use_airplane_display = fields.Boolean(string="Use Airplane (Display)", related='business_trip_data_id.use_airplane', readonly=True, store=False)
    form_data_airplane_departure_airport_display = fields.Char(string="Departure Airport (Display)", related='business_trip_data_id.airplane_departure_airport', readonly=True, store=False)
    form_data_airplane_departure_date_display = fields.Date(string="Airplane Departure Date (Display)", related='business_trip_data_id.airplane_departure_date', readonly=True, store=False)
    form_data_airplane_departure_flexible_display = fields.Boolean(string="Airplane Departure Flexible (Display)", related='business_trip_data_id.airplane_departure_flexible', readonly=True, store=False)
    form_data_airplane_arrival_airport_display = fields.Char(string="Arrival Airport (Display)", related='business_trip_data_id.airplane_arrival_airport', readonly=True, store=False)
    form_data_airplane_arrival_flexible_display = fields.Boolean(string="Airplane Arrival Flexible (Display)", related='business_trip_data_id.airplane_arrival_flexible', readonly=True, store=False)
    form_data_airplane_baggage_type_display = fields.Char(string="Baggage Type (Display)", compute='_compute_form_data_airplane_baggage_type_display', store=False)
    form_data_airplane_preferences_display = fields.Text(string="Airplane Preferences (Display)", related='business_trip_data_id.airplane_preferences', readonly=True, store=False)

    # New computed fields for Return Airplane details in Request Form Data tab
    form_data_use_return_airplane_display = fields.Boolean(string="Use Return Airplane (Display)", related='business_trip_data_id.use_return_airplane', readonly=True, store=False)
    form_data_return_airplane_departure_airport_display = fields.Char(string="Return Departure Airport (Display)", related='business_trip_data_id.return_airplane_departure_airport', readonly=True, store=False)
    form_data_return_airplane_departure_date_display = fields.Date(string="Return Airplane Departure Date (Display)", related='business_trip_data_id.return_airplane_departure_date', readonly=True, store=False)
    form_data_return_airplane_departure_flexible_display = fields.Boolean(string="Return Airplane Departure Flexible (Display)", related='business_trip_data_id.return_airplane_departure_flexible', readonly=True, store=False)
    form_data_return_airplane_destination_airport_display = fields.Char(string="Return Destination Airport (Display)", related='business_trip_data_id.return_airplane_destination_airport', readonly=True, store=False)
    form_data_return_airplane_destination_flexible_display = fields.Boolean(string="Return Airplane Destination Flexible (Display)", related='business_trip_data_id.return_airplane_destination_flexible', readonly=True, store=False)
    form_data_return_airplane_baggage_type_display = fields.Char(string="Return Baggage Type (Display)", compute='_compute_form_data_return_airplane_baggage_type_display', store=False)
    form_data_return_airplane_preferences_display = fields.Text(string="Return Airplane Preferences (Display)", related='business_trip_data_id.return_airplane_preferences', readonly=True, store=False)

    # New computed fields for Rental Car details in Request Form Data tab
    form_data_use_rental_car_display = fields.Boolean(string="Use Rental Car (Display)", related='business_trip_data_id.use_rental_car', readonly=True, store=False)
    form_data_rental_car_pickup_date_display = fields.Date(string="Rental Car Pickup Date (Display)", related='business_trip_data_id.rental_car_pickup_date', readonly=True, store=False)
    form_data_rental_car_pickup_flexible_display = fields.Boolean(string="Pickup Flexible (Display)", related='business_trip_data_id.rental_car_pickup_flexible', readonly=True, store=False)
    form_data_rental_car_pickup_point_display = fields.Char(string="Pickup Point (Display)", related='business_trip_data_id.rental_car_pickup_point', readonly=True, store=False)
    form_data_rental_car_dropoff_point_display = fields.Char(string="Dropoff Point (Display)", related='business_trip_data_id.rental_car_dropoff_point', readonly=True, store=False)
    form_data_rental_car_dropoff_date_display = fields.Date(string="Rental Car Dropoff Date (Display)", related='business_trip_data_id.rental_car_dropoff_date', readonly=True, store=False)
    form_data_rental_car_dropoff_flexible_display = fields.Boolean(string="Dropoff Flexible (Display)", related='business_trip_data_id.rental_car_dropoff_flexible', readonly=True, store=False)
    form_data_rental_car_credit_card_display = fields.Char(string="Credit Card Available (Display)", compute='_compute_form_data_rental_car_credit_card_display', store=False)
    form_data_rental_car_type_display = fields.Char(string="Rental Type (Display)", compute='_compute_form_data_rental_car_type_display', store=False)
    form_data_rental_car_kilometer_limit_display = fields.Integer(string="Kilometer Limit (Display)", related='business_trip_data_id.rental_car_kilometer_limit', readonly=True, store=False)
    form_data_rental_car_unlimited_km_display = fields.Boolean(string="Unlimited Kilometers (Display)", related='business_trip_data_id.rental_car_unlimited_km', readonly=True, store=False)
    form_data_rental_car_preferences_display = fields.Text(string="Rental Car Preferences (Display)", related='business_trip_data_id.rental_car_preferences', readonly=True, store=False)
    form_data_rental_car_drivers_license_display = fields.Binary(string="Driver's License (Display)", related='business_trip_data_id.rental_car_drivers_license', readonly=True, store=False)
    form_data_rental_car_drivers_license_filename_display = fields.Char(string="Driver's License Filename (Display)", related='business_trip_data_id.rental_car_drivers_license_filename', readonly=True, store=False)

    # New computed fields for Return Rental Car details
    form_data_use_return_rental_car_display = fields.Boolean(string="Use Return Rental Car (Display)", related='business_trip_data_id.use_return_rental_car', readonly=True, store=False)
    form_data_return_rental_car_pickup_date_display = fields.Date(string="Return Rental Car Pickup Date (Display)", related='business_trip_data_id.return_rental_car_pickup_date', readonly=True, store=False)
    form_data_return_rental_car_pickup_flexible_display = fields.Boolean(string="Return Pickup Flexible (Display)", related='business_trip_data_id.return_rental_car_pickup_flexible', readonly=True, store=False)
    form_data_return_rental_car_pickup_point_display = fields.Char(string="Return Pickup Point (Display)", related='business_trip_data_id.return_rental_car_pickup_point', readonly=True, store=False)
    form_data_return_rental_car_dropoff_point_display = fields.Char(string="Return Dropoff Point (Display)", related='business_trip_data_id.return_rental_car_dropoff_point', readonly=True, store=False)
    form_data_return_rental_car_dropoff_date_display = fields.Date(string="Return Rental Car Dropoff Date (Display)", related='business_trip_data_id.return_rental_car_dropoff_date', readonly=True, store=False)
    form_data_return_rental_car_dropoff_flexible_display = fields.Boolean(string="Return Dropoff Flexible (Display)", related='business_trip_data_id.return_rental_car_dropoff_flexible', readonly=True, store=False)
    form_data_return_rental_car_credit_card_display = fields.Char(string="Return Credit Card Available (Display)", compute='_compute_form_data_return_rental_car_credit_card_display', store=False)
    form_data_return_rental_car_type_display = fields.Char(string="Return Rental Type (Display)", compute='_compute_form_data_return_rental_car_type_display', store=False)
    form_data_return_rental_car_kilometer_limit_display = fields.Integer(string="Return Kilometer Limit (Display)", related='business_trip_data_id.return_rental_car_kilometer_limit', readonly=True, store=False)
    form_data_return_rental_car_unlimited_km_display = fields.Boolean(string="Return Unlimited Kilometers (Display)", related='business_trip_data_id.return_rental_car_unlimited_km', readonly=True, store=False)
    form_data_return_rental_car_preferences_display = fields.Text(string="Return Rental Car Preferences (Display)", related='business_trip_data_id.return_rental_car_preferences', readonly=True, store=False)
    form_data_return_rental_car_drivers_license_display = fields.Binary(string="Return Driver's License (Display)", related='business_trip_data_id.return_rental_car_drivers_license', readonly=True, store=False)
    form_data_return_rental_car_drivers_license_filename_display = fields.Char(string="Return Driver's License Filename (Display)", related='business_trip_data_id.return_rental_car_drivers_license_filename', readonly=True, store=False)

    # New computed fields for Train details
    form_data_use_train_display = fields.Boolean(string="Use Train (Display)", related='business_trip_data_id.use_train', readonly=True, store=False)
    form_data_train_departure_city_display = fields.Char(string="Train Departure City (Display)", related='business_trip_data_id.train_departure_city', readonly=True, store=False)
    form_data_train_departure_station_display = fields.Char(string="Train Departure Station (Display)", related='business_trip_data_id.train_departure_station', readonly=True, store=False)
    form_data_train_arrival_station_display = fields.Char(string="Train Arrival Station (Display)", related='business_trip_data_id.train_arrival_station', readonly=True, store=False)
    form_data_train_departure_date_display = fields.Date(string="Train Departure Date (Display)", related='business_trip_data_id.train_departure_date', readonly=True, store=False)
    form_data_train_departure_flexible_display = fields.Boolean(string="Train Departure Flexible (Display)", related='business_trip_data_id.train_departure_flexible', readonly=True, store=False)
    form_data_train_arrival_date_display = fields.Date(string="Train Arrival Date (Display)", related='business_trip_data_id.train_arrival_date', readonly=True, store=False)
    form_data_train_arrival_flexible_display = fields.Boolean(string="Train Arrival Flexible (Display)", related='business_trip_data_id.train_arrival_flexible', readonly=True, store=False)

    # New computed fields for Return Train details
    form_data_use_return_train_display = fields.Boolean(string="Use Return Train (Display)", related='business_trip_data_id.use_return_train', readonly=True, store=False)
    form_data_return_train_departure_city_display = fields.Char(string="Return Train Departure City (Display)", related='business_trip_data_id.return_train_departure_city', readonly=True, store=False)
    form_data_return_train_departure_station_display = fields.Char(string="Return Train Departure Station (Display)", related='business_trip_data_id.return_train_departure_station', readonly=True, store=False)
    form_data_return_train_arrival_station_display = fields.Char(string="Return Train Arrival Station (Display)", related='business_trip_data_id.return_train_arrival_station', readonly=True, store=False)
    form_data_return_train_departure_date_display = fields.Date(string="Return Train Departure Date (Display)", related='business_trip_data_id.return_train_departure_date', readonly=True, store=False)
    form_data_return_train_departure_flexible_display = fields.Boolean(string="Return Train Departure Flexible (Display)", related='business_trip_data_id.return_train_departure_flexible', readonly=True, store=False)
    form_data_return_train_arrival_date_display = fields.Date(string="Return Train Arrival Date (Display)", related='business_trip_data_id.return_train_arrival_date', readonly=True, store=False)
    form_data_return_train_arrival_flexible_display = fields.Boolean(string="Return Train Arrival Flexible (Display)", related='business_trip_data_id.return_train_arrival_flexible', readonly=True, store=False)

    # New computed fields for Bus details
    form_data_use_bus_display = fields.Boolean(string="Use Bus (Display)", related='business_trip_data_id.use_bus', readonly=True, store=False)
    form_data_bus_departure_city_display = fields.Char(string="Bus Departure City (Display)", related='business_trip_data_id.bus_departure_city', readonly=True, store=False)
    form_data_bus_departure_terminal_display = fields.Char(string="Bus Departure Terminal (Display)", related='business_trip_data_id.bus_departure_terminal', readonly=True, store=False)
    form_data_bus_arrival_terminal_display = fields.Char(string="Bus Arrival Terminal (Display)", related='business_trip_data_id.bus_arrival_terminal', readonly=True, store=False)
    form_data_bus_departure_date_display = fields.Date(string="Bus Departure Date (Display)", related='business_trip_data_id.bus_departure_date', readonly=True, store=False)
    form_data_bus_arrival_date_display = fields.Date(string="Bus Arrival Date (Display)", related='business_trip_data_id.bus_arrival_date', readonly=True, store=False)
    form_data_bus_departure_flexible_display = fields.Boolean(string="Bus Departure Flexible (Display)", related='business_trip_data_id.bus_departure_flexible', readonly=True, store=False)
    form_data_bus_arrival_flexible_display = fields.Boolean(string="Bus Arrival Flexible (Display)", related='business_trip_data_id.bus_arrival_flexible', readonly=True, store=False)

    # New computed fields for Return Bus details
    form_data_use_return_bus_display = fields.Boolean(string="Use Return Bus (Display)", related='business_trip_data_id.use_return_bus', readonly=True, store=False)
    form_data_return_bus_departure_city_display = fields.Char(string="Return Bus Departure City (Display)", related='business_trip_data_id.return_bus_departure_city', readonly=True, store=False)
    form_data_return_bus_departure_station_display = fields.Char(string="Return Bus Departure Station (Display)", related='business_trip_data_id.return_bus_departure_station', readonly=True, store=False)
    form_data_return_bus_arrival_station_display = fields.Char(string="Return Bus Arrival Station (Display)", related='business_trip_data_id.return_bus_arrival_station', readonly=True, store=False)
    form_data_return_bus_departure_date_display = fields.Date(string="Return Bus Departure Date (Display)", related='business_trip_data_id.return_bus_departure_date', readonly=True, store=False)
    form_data_return_bus_departure_flexible_display = fields.Boolean(string="Return Bus Departure Flexible (Display)", related='business_trip_data_id.return_bus_departure_flexible', readonly=True, store=False)
    form_data_return_bus_arrival_date_display = fields.Date(string="Return Bus Arrival Date (Display)", related='business_trip_data_id.return_bus_arrival_date', readonly=True, store=False)
    form_data_return_bus_arrival_flexible_display = fields.Boolean(string="Return Bus Arrival Flexible (Display)", related='business_trip_data_id.return_bus_arrival_flexible', readonly=True, store=False)


    # Related field for accompanying persons
    accompanying_person_ids = fields.One2many(
        'accompanying.person',
        related='business_trip_data_id.accompanying_person_ids',
        string='Accompanying Persons',
        readonly=True
    )

    # ADDED: New compute method for formatted actual dates and duration string
    @api.depends('business_trip_id.actual_start_date', 'business_trip_id.actual_end_date')
    def _compute_actual_duration_and_dates_display(self):
        for record in self:
            # Get user's timezone from their preferences, default to UTC if not set
            try:
                user_tz_str = record.env.user.tz or 'UTC'
                user_tz = pytz.timezone(user_tz_str)
            except pytz.UnknownTimeZoneError:
                _logger.warning(f"User {record.env.user.name} has an unknown timezone '{record.env.user.tz}'. Defaulting to UTC.")
                user_tz = pytz.utc

            # Format start date
            if record.business_trip_id and record.business_trip_id.actual_start_date:
                # Odoo's naive datetime objects are in UTC. First, make them timezone-aware (localize to UTC).
                utc_dt = pytz.utc.localize(record.business_trip_id.actual_start_date)
                # Then, convert to the user's timezone.
                user_dt = utc_dt.astimezone(user_tz)
                record.actual_start_date_display = user_dt.strftime('%d/%m/%Y %H:%M:%S')
            else:
                record.actual_start_date_display = ""

            # Format end date
            if record.business_trip_id and record.business_trip_id.actual_end_date:
                utc_dt = pytz.utc.localize(record.business_trip_id.actual_end_date)
                user_dt = utc_dt.astimezone(user_tz)
                record.actual_end_date_display = user_dt.strftime('%d/%m/%Y %H:%M:%S')
            else:
                record.actual_end_date_display = ""

            # Calculate and format human-readable duration
            if record.business_trip_id and record.business_trip_id.actual_start_date and record.business_trip_id.actual_end_date and record.business_trip_id.actual_end_date > record.business_trip_id.actual_start_date:
                delta = record.business_trip_id.actual_end_date - record.business_trip_id.actual_start_date

                days = delta.days
                seconds = delta.seconds
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60

                parts = []
                if days > 0:
                    parts.append(f"{days} day{'s' if days > 1 else ''}")
                if hours > 0:
                    parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
                if minutes > 0:
                    parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")

                if not parts:
                    remaining_seconds = seconds % 60
                    if remaining_seconds > 0:
                        parts.append(f"{remaining_seconds} second{'s' if remaining_seconds > 1 else ''}")
                    else:
                        record.actual_duration_display = "0 minutes"
                        continue

                record.actual_duration_display = ", ".join(parts)
            else:
                record.actual_duration_display = "Not yet calculated"

    trip_request_notes = fields.Text(string='Trip Request Notes', help="Notes from the employee about the trip request")


    def write(self, vals):
        res = super(FormioForm, self).write(vals)
        for record in self:
            if 'trip_status' in vals:
                if vals['trip_status'] == 'pending_organization':
                    record.organizer_submission_date = fields.Datetime.now()
                # If manager confirms the plan, set confirmation details
                elif vals['trip_status'] == 'awaiting_trip_start':
                    record.organizer_confirmed_by = self.env.user
                    record.organizer_confirmation_date = fields.Datetime.now()

            # Link any new attachments to the record
            attachments = record.expense_attachment_ids + record.organizer_attachments_ids + record.employee_documents_ids
            for attachment in attachments:
                if not attachment.res_id:
                    attachment.write({'res_model': self._name, 'res_id': record.id})

        return res

    def action_view_business_trip_data(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Business Trip Data',
            'res_model': 'business.trip.data',
            'view_mode': 'form',
            'res_id': self.business_trip_data_id.id,
            'target': 'current',
        }

    def action_return_to_employee_with_comment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Return to Employee',
            'res_model': 'trip.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_form_id': self.id,
                'default_action_type': 'return_to_employee',
            }
        }

    @api.model
    def _get_trip_statuses_for_user(self):
        """
        Returns a list of trip statuses that are relevant for the current user's role.
        This is used to filter views or determine available actions.
        """
        statuses = []
        if self.env.user.has_group('custom_business_trip_management.group_business_trip_organizer'):
            statuses.extend(['pending_organization', 'organization_done', 'awaiting_trip_start', 'in_progress', 'completed_waiting_expense'])
        if self.env.user.has_group('base.group_system'): # Assuming admin can see all
            statuses = [
                'draft', 'submitted', 'pending_organization', 'organization_done',
                'awaiting_trip_start', 'in_progress', 'completed_waiting_expense',
                'expense_submitted', 'completed', 'returned', 'rejected', 'cancelled'
            ]
        return statuses

    @api.depends('name') # Recompute when form name changes, for instance.
    def _compute_trip_project_and_task(self):
        project = self.env.ref('custom_business_trip_management.project_business_trip', raise_if_not_found=False)
        if not project:
            # Handle case where project is not found
            self.trip_project_id = False
            self.trip_task_id = False
            return

        for form in self:
            task = self.env['project.task'].search([('project_id', '=', project.id), ('name', '=', form.display_name)], limit=1)
            if not task:
                task = self.env['project.task'].create({
                    'name': form.display_name,
                    'project_id': project.id,
                })
            form.trip_project_id = project.id
            form.trip_task_id = task.id

    def action_submit_plan_to_manager(self):
        """
        Organizer submits the completed plan to the manager for final review.
        This also posts an internal note and a public note.
        """
        self.ensure_one()

        # Ensure the organizer is set
        if not self.organizer_id:
            raise UserError(_("Please assign an organizer before submitting the plan."))

        # Log the internal note for manager
        plan_details_str = self.get_planned_trip_details_as_string()
        
        # Post confidential message for internal users (manager/organizers)
        self._post_styled_message(
            template_xml_id='custom_business_trip_management.organizer_plan_confidential_summary',
            card_type='warning',
            icon='🔒',
            title='Confidential: Trip Plan Updated (Pending Confirmation)',
            is_internal_note=True,
            render_context={
                'record': self,
                'plan_details': plan_details_str
            }
        )

        # Post public message for the employee
        self._post_styled_message(
            template_xml_id='custom_business_trip_management.organizer_plan_public_summary',
            card_type='info',
            icon='⏳',
            title='Trip Plan Updated',
            is_internal_note=False,
            render_context={
                'record': self
            }
        )

        return True

    def action_confirm_trip_plan(self):
        """
        Organizer confirms the trip plan and notifies the employee.
        This method should be called when the organizer confirms the trip plan.
        """
        self.ensure_one()

        # Ensure the organizer is set
        if not self.organizer_id:
            raise UserError(_("Please assign an organizer before submitting the plan."))

        # Log the internal note for manager
        plan_details_str = self.get_planned_trip_details_as_string()
        
        # Post confidential message for internal users
        self._post_styled_message(
            'custom_business_trip_management.organizer_plan_confidential_summary',
            card_type='warning',
            icon='🔒',
            title='Confidential: Trip Plan Updated (Pending Confirmation)',
            is_internal_note=True,
            render_context={
                'record': self,
                'plan_details': plan_details_str
            }
        )

        # Post public message for the employee
        self._post_styled_message(
            'custom_business_trip_management.organizer_plan_public_summary',
            card_type='info',
            icon='⏳',
            title='Trip Plan Updated',
            is_internal_note=False,
            render_context={
                'record': self
            }
        )

        return True

    @api.depends('business_trip_id.structured_plan_items_json')
    def _compute_organizer_plan_html(self):
        for record in self:
            if not record.business_trip_id or not record.business_trip_id.structured_plan_items_json:
                record.organizer_plan_html = '<div class="alert alert-info" role="alert">No structured plan details available.</div>'
                continue

            try:
                plan_items = json.loads(record.business_trip_id.structured_plan_items_json)
                if not isinstance(plan_items, list):
                    raise ValueError("JSON data is not a list of items.")
            except (json.JSONDecodeError, ValueError) as e:
                _logger.error(f"Could not parse structured_plan_items_json for form {record.id}: {e}")
                record.organizer_plan_html = f'<div class="alert alert-danger" role="alert">Error displaying plan details. Invalid data format.</div>'
                continue

            html = '<div class="o_organizer_plan_view">'
            
            item_categories = {
                'flight': [], 'hotel': [], 'train': [], 'car_rental': [], 'other': []
            }

            for item in plan_items:
                category = item.get('type', 'other')
                if category in item_categories:
                    item_categories[category].append(item)
                else:
                    item_categories['other'].append(item)

            for category, items in item_categories.items():
                if items:
                    html += f'<h4><i class="fa fa-fw {self._get_icon_for_category(category)} mr-2"/>{category.replace("_", " ").title()}</h4>'
                    html += '<table class="table table-sm o_main_table">'
                    
                    # Create headers based on the first item
                    headers = list(items[0].keys())
                    html += '<thead><tr>'
                    for header in headers:
                        if header != 'type':
                             html += f'<th>{header.replace("_", " ").title()}</th>'
                    html += '</tr></thead>'

                    html += '<tbody>'
                    for item in items:
                        html += '<tr>'
                        for header in headers:
                            if header != 'type':
                                value = item.get(header, '')
                                html += f'<td>{html_sanitize(str(value))}</td>'
                        html += '</tr>'
                    html += '</tbody>'
                    html += '</table>'

            html += '</div>'
            record.organizer_plan_html = html

    def _get_icon_for_category(self, category):
        icon_map = {
            'flight': 'fa-plane',
            'hotel': 'fa-bed',
            'train': 'fa-train',
            'car_rental': 'fa-car',
            'other': 'fa-info-circle'
        }
        return icon_map.get(category, 'fa-info-circle')

    @api.depends('business_trip_id.structured_plan_items_json')
    def _compute_organizer_plan_display_fields(self):
        """
        Computes structured HTML blocks for the organizer's plan items,
        categorized for display in the form view, mimicking the style of other tabs.
        """
        for record in self:
            # Initialize all fields to default values
            record.organizer_plan_has_flight = False
            record.organizer_plan_flight_html = ''
            record.organizer_plan_has_hotel = False
            record.organizer_plan_hotel_html = ''
            record.organizer_plan_has_train = False
            record.organizer_plan_train_html = ''
            record.organizer_plan_has_car_rental = False
            record.organizer_plan_car_rental_html = ''
            record.organizer_plan_has_other = False
            record.organizer_plan_other_html = ''

            if not record.business_trip_id:
                continue
                
            plan_items_str = record.business_trip_id.structured_plan_items_json
            if not plan_items_str or plan_items_str == '[]':
                continue

            try:
                plan_items = json.loads(plan_items_str)
                if not isinstance(plan_items, list):
                    _logger.warning(f"structured_plan_items_json is not a list for form {record._origin.id}")
                    continue

                categorized_items = {
                    'flight': [], 'hotel': [], 'train': [], 'car_rental': [], 'other': []
                }
                for item in plan_items:
                    item_type = item.get('item_type', '')
                    # Map item_type to category
                    if item_type == 'transport_air':
                        category = 'flight'
                    elif item_type in ['transport_train']:
                        category = 'train'
                    elif item_type in ['transport_car', 'transport_taxi']:
                        category = 'car_rental'
                    elif item_type in ['accommodation', 'accommodation_airbnb']:
                        category = 'hotel'
                    else:
                        category = 'other'
                    
                    if category in categorized_items:
                        categorized_items[category].append(item)

                for category, items in categorized_items.items():
                    if items:
                        record[f'organizer_plan_has_{category}'] = True
                        html_blocks = [self._generate_item_html(item) for item in items]
                        record[f'organizer_plan_{category}_html'] = "".join(html_blocks)

            except (json.JSONDecodeError, TypeError):
                _logger.warning(f"Could not parse structured_plan_items_json for form {record._origin.id}")
                continue

    def _render_plan_item_field(self, label, value):
        """Helper to render a single key-value pair for the plan item HTML."""
        from markupsafe import Markup
        if not value:
            return ''
        return Markup(f"""
            <tr>
                <td class="o_td o_group_label" style="width: 25%; font-weight: bold;">
                    <label class="o_form_label">{label}</label>
                </td>
                <td class="o_td" style="width: 75%;">
                    <span>{value}</span>
                </td>
            </tr>
        """)

    def _generate_item_html(self, item):
        """Generates an HTML block for a single plan item, styled like Request Form Data tab."""
        from markupsafe import Markup
        
        item_type = item.get('item_type', '')
        description = item.get('description', 'Item')
        
        # Check if user should see cost information
        show_cost = self._should_show_cost_info()
        
        # Generate clean HTML similar to Request Form Data
        html = f'<div style="margin-bottom: 1rem;">'
        
        # Item description/title
        html += f'<div style="font-weight: bold; margin-bottom: 0.5rem;">{description}</div>'
        
        # Item details based on type
        if item_type == 'transport_air':
            html += self._render_item_detail('Flight', item.get('carrier', ''))
            html += self._render_item_detail('Route', f"{item.get('from_location', '')} → {item.get('to_location', '')}")
            html += self._render_item_detail('Date', item.get('item_date', ''))
            html += self._render_item_detail('Reference', item.get('reference_number', ''))
            html += self._render_item_detail('Departure Time', item.get('departure_time', ''))
            html += self._render_item_detail('Arrival Time', item.get('arrival_time', ''))
            
        elif item_type in ['transport_train', 'transport_bus']:
            transport_name = 'Train' if item_type == 'transport_train' else 'Bus'
            html += self._render_item_detail(transport_name, item.get('carrier', ''))
            html += self._render_item_detail('Route', f"{item.get('from_location', '')} → {item.get('to_location', '')}")
            html += self._render_item_detail('Date', item.get('item_date', ''))
            html += self._render_item_detail('Reference', item.get('reference_number', ''))
            html += self._render_item_detail('Departure Time', item.get('departure_time', ''))
            html += self._render_item_detail('Arrival Time', item.get('arrival_time', ''))
            
        elif item_type in ['transport_car', 'transport_taxi']:
            transport_name = 'Car Rental' if item_type == 'transport_car' else 'Taxi/Transport'
            html += self._render_item_detail('Type', transport_name)
            html += self._render_item_detail('Route', f"{item.get('from_location', '')} → {item.get('to_location', '')}")
            html += self._render_item_detail('Date', item.get('item_date', ''))
            html += self._render_item_detail('Provider', item.get('carrier', ''))
            html += self._render_item_detail('Reference', item.get('reference_number', ''))
            
        elif item_type in ['accommodation', 'accommodation_airbnb']:
            accom_type = 'Hotel' if item_type == 'accommodation' else 'Airbnb/Rental'
            html += self._render_item_detail('Type', item.get('accommodation_type', accom_type))
            html += self._render_item_detail('Check-in Date', item.get('item_date', ''))
            html += self._render_item_detail('Nights', f"{item.get('nights', 1)} night(s)")
            html += self._render_item_detail('Reference', item.get('reference_number', ''))
            
        else:
            # Other items
            html += self._render_item_detail('Type', item.get('custom_type', item_type.replace('_', ' ').title()))
            html += self._render_item_detail('Date', item.get('item_date', ''))
            html += self._render_item_detail('Reference', item.get('reference_number', ''))
        
        # Cost information - only show if user has permission
        if show_cost and item.get('cost'):
            cost_status = item.get('cost_status', '')
            payment_method = item.get('payment_method', '')
            cost_text = f"{item.get('cost', 0)}"
            if cost_status:
                cost_text += f" ({cost_status})"
            if payment_method:
                cost_text += f" - {payment_method}"
            html += self._render_item_detail('Cost', cost_text)
        
        # Notes
        if item.get('notes'):
            html += self._render_item_detail('Notes', item.get('notes', ''))
        
        html += '</div>'
        return Markup(html)
    
    def _render_item_detail(self, label, value):
        """Renders a single detail line for plan items."""
        if not value or value == '→':
            return ''
        return f'<div style="margin-bottom: 0.25rem;"><span style="color: #666; margin-right: 0.5rem;">{label}:</span><span>{value}</span></div>'

    def _should_show_cost_info(self):
        """Check if the current user should see cost information."""
        self.ensure_one()
        user = self.env.user
        # System administrators always have access
        if user.has_group('base.group_system'):
            return True
        # Managers and organizers should see cost information
        is_manager = (self.manager_id and user.id == self.manager_id.id)
        is_organizer = (self.organizer_id and user.id == self.organizer_id.id)
        # Also allow users in organizer group
        is_in_organizer_group = user.has_group('custom_business_trip_management.group_business_trip_organizer')
        return is_manager or is_organizer or is_in_organizer_group

    def action_reprocess_data(self):
        """
        Server action to re-process the submission data for the selected form(s).
        This combines the logic of previous "fix" actions into one robust method.
        It re-extracts data from the raw JSON and re-computes related display fields.
        """
        _logger.info(f"ACTION_REPROCESS_DATA: Starting re-processing for {len(self)} form(s).")
        processed_count = 0
        error_count = 0

        for record in self:
            try:
                _logger.info(f"Processing form {record.id} ('{record.title}').")
                
                # Step 1: Ensure a business_trip_data record exists.
                trip_data = record.business_trip_data_id
                if not trip_data:
                    trip_data = self.env['business.trip.data'].search([('form_id', '=', record.id)], limit=1)
                if not trip_data:
                    _logger.warning(f"No business_trip_data record found for form {record.id}. Cannot re-process.")
                    error_count += 1
                    continue
                
                # Step 2: Re-run the data extraction from the raw submission JSON.
                if record.submission_data:
                    submission_data_dict = json.loads(record.submission_data)
                    trip_data.process_submission_data(submission_data_dict)
                    _logger.info(f"Successfully ran process_submission_data for BTD {trip_data.id}.")
                else:
                    _logger.warning(f"No submission_data found for form {record.id}. Skipping extraction.")

                # Step 3: Display fields are now automatically computed via related fields.
                # No manual computation needed - data flows automatically from business_trip_data_id.
                record._compute_transportation_display_data()
                _logger.info(f"Successfully re-computed display fields for form {record.id}.")

                processed_count += 1
            except Exception as e:
                _logger.error(f"Failed to re-process form {record.id}. Error: {e}", exc_info=True)
                error_count += 1
        
        # Return a user-facing notification with the result.
        message = _('%s form(s) re-processed successfully.') % processed_count
        if error_count:
            message += _('\n%s form(s) failed.') % error_count
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Re-processing Complete'),
                'message': message,
                'sticky': False,
            }
        }

    @api.model
    def _get_trip_statuses_for_user(self):
        """
        Returns a list of trip statuses relevant to the current user's role.
        This can be used to filter records in search views or domains.
        """
        statuses = []
        if self.env.user.has_group('custom_business_trip_management.group_business_trip_organizer'):
            statuses.extend(['pending_organization', 'organization_done', 'awaiting_trip_start', 'in_progress', 'completed_waiting_expense'])
        if self.env.user.has_group('base.group_system'): # Assuming admin can see all
            statuses = [
                'draft', 'submitted', 'pending_organization', 'organization_done',
                'awaiting_trip_start', 'in_progress', 'completed_waiting_expense',
                'expense_submitted', 'completed', 'returned', 'rejected', 'cancelled'
            ]
        return statuses

    @api.depends('submission_data')
    def _compute_form_data_json(self):
        for record in self:
            raw_submission_dict = {}
            if record.submission_data:
                try:
                    raw_submission_dict = json.loads(record.submission_data)
                except Exception:
                    _logger.error(f"Error parsing submission_data for form_data_json on form {record.id}", exc_info=True)

            try:
                record.form_data_json = json.dumps(raw_submission_dict, indent=2, sort_keys=True)
            except Exception:
                _logger.error(f"Error pretty-printing submission_data for form {record.id}", exc_info=True)
                record.form_data_json = str(raw_submission_dict) # Fallback to simple string representation

    @api.depends('business_trip_data_id.trip_duration_type')
    def _compute_form_data_trip_duration_type_display(self):
        for record in self:
            if record.business_trip_data_id and record.business_trip_data_id.trip_duration_type:
                record.form_data_trip_duration_type_display = dict(record.business_trip_data_id._fields['trip_duration_type'].selection).get(record.business_trip_data_id.trip_duration_type)
            else:
                record.form_data_trip_duration_type_display = ''

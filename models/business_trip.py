# -*- coding: utf-8 -*-
from collections import defaultdict
import re

from odoo import models, fields, api, _
import logging
from odoo.exceptions import AccessError, UserError, ValidationError
import json
from dateutil.relativedelta import relativedelta
import pytz
from markupsafe import Markup, escape
from odoo.tools import html_sanitize
from datetime import datetime, timedelta
from lxml import etree
from odoo.osv import expression

_logger = logging.getLogger(__name__)
MONTH_ABBREVIATIONS = (
    '',
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
)

class BusinessTrip(models.Model):
    _name = 'business.trip'
    _description = 'Business Trip Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'mail.template.mixin']

    # -------------------------------------------------------------------------
    # The following fields were directly related to the 'formio' module and have been removed
    # to eliminate the dependency. This includes the main link 'formio_form_id' and all
    # fields that were related to it for displaying form data.
    # -------------------------------------------------------------------------

    # NEW related fields
    full_name = fields.Char(related='business_trip_data_id.full_name', readonly=True, store=True)

    # Modified by A_zeril_A, 2025-10-24: Made field editable for new form
    trip_duration_type = fields.Selection(related='business_trip_data_id.trip_duration_type', string='Trip Duration Type', readonly=False, store=True)

    # Direct link to the Business Trip Data model.
    # This was previously a problematic 'related' field. Now it's a direct, stored link.
    business_trip_data_id = fields.Many2one('business.trip.data', string='Business Trip Data', ondelete='cascade', index=True, copy=False)

    # The trip name is generated from a compact summary of the trip and stays stable
    # after submission unless an explicit refresh is requested during an upgrade.
    name = fields.Char(string='Trip Name', compute='_compute_name', store=True)
    
    # The 'state' field related to formio.form.state is removed as it's redundant.
    # The 'trip_status' field on this model is the single source of truth for the trip's status.

    # --- WORKFLOW & STATE ---
    trip_status = fields.Selection([
        ('draft', 'Awaiting Submission'),
        ('submitted', 'To Travel Approver'),
        ('pending_organization', 'To Organizer'),
        ('organization_done', 'Organization Completed'),
        ('returned', 'Returned to Employee'),
        ('rejected', 'Rejected'),
        ('completed_waiting_expense', 'Awaiting Travel Expenses'),
        ('expense_submitted', 'Expenses Under Review'),
        ('expense_returned', 'Expense Returned'),
        ('completed', 'TRAVEL PROCESS COMPLETED'),
        ('cancelled', 'Cancelled')
    ], string='Trip Status', default='draft', tracking=True, copy=False)
    
    # Form completion status - separate from trip workflow status
    form_completion_status = fields.Selection([
        ('awaiting_completion', 'Awaiting Completion'),
        ('form_completed', 'Form Completed'),
        ('cancelled', 'Cancelled')
    ], string='Form Completion Status', default='awaiting_completion', tracking=True, copy=False,
       help="Status of the form filling process, independent of the trip approval workflow")

    # --- RELATIONAL & KEY FIELDS ---
    user_id = fields.Many2one('res.users', string='Employee', required=True, default=lambda self: self.env.user)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    sale_order_id = fields.Many2one('sale.order', string='Sales Order', readonly=True)
    display_quotation_ref = fields.Char(string='Linked Quotation', compute='_compute_display_quotation_ref', store=False)
    # Added by A_zeril_A, 2025-10-24: Field for approving colleague name from formio form
    # Modified by A_zeril_A, 2025-10-28: Auto-populate with travel approver name but keep editable
    approving_colleague_name = fields.Char(
        string='Name of Approving Colleague', 
        tracking=True,
        compute='_compute_approving_colleague_name',
        store=True,
        readonly=False,
        help="Name of the colleague who will approve this trip. Auto-filled with Travel Approver name but can be edited."
    )
    manager_id = fields.Many2one('res.users', string='Travel Approver', tracking=True, help="Travel Approver who reviews the initial request and final plan.")
    expense_reviewer_id = fields.Many2one(
        'res.users',
        string='Expense Reviewer',
        index=True,
        tracking=True,
        copy=False,
        help="Company-configured reviewer responsible for this trip's expenses."
    )
    organizer_id = fields.Many2one(
        'res.users',
        string='Trip Organizer',
        tracking=True,
        domain="[('groups_id', 'in', ref('custom_business_trip_management.group_business_trip_organizer').id)]",
    )
    assignment_history_ids = fields.One2many(
        "business.trip.assignment.history",
        "trip_id",
        string="Assignment History",
        readonly=True,
    )
    business_trip_project_id = fields.Many2one('project.project', string='Business Trip Project', copy=False, tracking=True)
    business_trip_task_id = fields.Many2one('project.task', string='Business Trip Task', copy=False, tracking=True)
    
    # Fields for standalone project selection
    selected_project_id = fields.Many2one('project.project', string='Selected Project (Standalone)', 
                                         copy=False, tracking=True,
                                         help="Project selected during standalone trip creation")
    selected_project_task_id = fields.Many2one('project.task', string='Selected Project Task (Standalone)', 
                                               copy=False, tracking=True,
                                               help="Task created in selected project for standalone trip")

    plan_line_ids = fields.One2many('business.trip.plan.line', 'trip_id', string='Plan Items', copy=False)
    expense_line_ids = fields.One2many('business.trip.expense.line', 'trip_id', string='Expense Items', copy=False)

    # --- TRIP DETAILS (from Data Model) ---
    # Modified by A_zeril_A, 2025-10-24: Made fields editable (readonly=False) for new form
    destination = fields.Char(related='business_trip_data_id.destination', string='Destination', readonly=False, store=True)
    destination_place_id = fields.Many2one(
        related="business_trip_data_id.destination_place_id",
        string="Destination (Autocomplete)",
        readonly=False,
        store=True,
    )
    purpose = fields.Char(related='business_trip_data_id.purpose', string='Purpose', readonly=False, store=True)
    travel_start_date = fields.Date(related='business_trip_data_id.travel_start_date', string='Travel Start Date', readonly=False, store=True)
    travel_end_date = fields.Date(related='business_trip_data_id.travel_end_date', string='Travel End Date', readonly=False, store=True)
    trip_type = fields.Selection(related='business_trip_data_id.trip_type', string='Trip Type', readonly=False, store=True)

    @api.onchange("destination_place_id")
    def _onchange_destination_place_id(self):
        for rec in self:
            if rec.destination_place_id:
                rec.destination = rec.destination_place_id.name
    
    # --- TRANSPORTATION & ACCOMMODATION (from Data Model) ---
    # Modified by A_zeril_A, 2025-10-24: Made fields editable (readonly=False) for new form
    accommodation_needed = fields.Selection(related='business_trip_data_id.accommodation_needed', string='Accommodation Needed', readonly=False, store=True)
    use_airplane = fields.Boolean(related='business_trip_data_id.use_airplane', string='Use Airplane', readonly=False, store=True)
    use_return_airplane = fields.Boolean(related='business_trip_data_id.use_return_airplane', string='Use Return Airplane', readonly=False, store=True)
    use_rental_car = fields.Boolean(related='business_trip_data_id.use_rental_car', string='Use Rental Car', readonly=False, store=True)
    use_return_rental_car = fields.Boolean(related='business_trip_data_id.use_return_rental_car', string='Use Return Rental Car', readonly=False, store=True)
    use_train = fields.Boolean(related='business_trip_data_id.use_train', string='Use Train', readonly=False, store=True)
    use_return_train = fields.Boolean(related='business_trip_data_id.use_return_train', string='Use Return Train', readonly=False, store=True)
    use_bus = fields.Boolean(related='business_trip_data_id.use_bus', string='Use Bus', readonly=False, store=True)
    use_return_bus = fields.Boolean(related='business_trip_data_id.use_return_bus', string='Use Return Bus', readonly=False, store=True)
    use_company_car = fields.Boolean(related='business_trip_data_id.use_company_car', string='Use Company Car', readonly=False, store=True)
    use_personal_car = fields.Boolean(related='business_trip_data_id.use_personal_car', string='Use Personal Car', readonly=False, store=True)
    use_return_company_car = fields.Boolean(related='business_trip_data_id.use_return_company_car', string='Use Return Company Car', readonly=False, store=True)
    use_return_personal_car = fields.Boolean(related='business_trip_data_id.use_return_personal_car', string='Use Return Personal Car', readonly=False, store=True)

    # --- DETAILED TRANSPORTATION & ACCOMMODATION (from Data Model) ---
    
    # Accommodation
    # Modified by A_zeril_A, 2025-10-24: Made fields editable for new form
    accommodation_residence_city = fields.Char(related='business_trip_data_id.accommodation_residence_city', readonly=False, store=True)
    accommodation_check_in_date = fields.Date(related='business_trip_data_id.accommodation_check_in_date', readonly=False, store=True)
    accommodation_check_out_date = fields.Date(related='business_trip_data_id.accommodation_check_out_date', readonly=False, store=True)
    accommodation_number_of_people = fields.Integer(related='business_trip_data_id.accommodation_number_of_people', readonly=False, store=True)
    accommodation_need_24h_reception = fields.Selection(related='business_trip_data_id.accommodation_need_24h_reception', readonly=False, store=True)
    accommodation_points_of_interest = fields.Text(related='business_trip_data_id.accommodation_points_of_interest', readonly=False, store=True)
    accompanying_person_ids = fields.One2many(related='business_trip_data_id.accompanying_person_ids', readonly=False)
    
    # Computed fields for accompanying persons display (needed for UI compatibility)
    accommodation_accompanying_persons_display = fields.Text(string='Accompanying Persons (Display)', 
                                                           compute='_compute_accommodation_persons_display', store=False,
                                                           help="List of accompanying persons with their document status for display.")
    accommodation_accompanying_persons_json = fields.Text(string='Accompanying Persons (JSON)', 
                                                         compute='_compute_accommodation_persons_json', store=False,
                                                         help="JSON representation of accompanying persons for UI consumption.")

    # Rental Car
    # Modified by A_zeril_A, 2025-10-24: Made fields editable for new form
    rental_car_pickup_point = fields.Char(related='business_trip_data_id.rental_car_pickup_point', readonly=False, store=True)
    rental_car_pickup_date = fields.Date(related='business_trip_data_id.rental_car_pickup_date', readonly=False, store=True)
    rental_car_pickup_flexible = fields.Boolean(related='business_trip_data_id.rental_car_pickup_flexible', readonly=False, store=True)
    rental_car_dropoff_point = fields.Char(related='business_trip_data_id.rental_car_dropoff_point', readonly=False, store=True)
    rental_car_dropoff_date = fields.Date(related='business_trip_data_id.rental_car_dropoff_date', readonly=False, store=True)
    rental_car_dropoff_flexible = fields.Boolean(related='business_trip_data_id.rental_car_dropoff_flexible', readonly=False, store=True)
    rental_car_credit_card = fields.Selection(related='business_trip_data_id.rental_car_credit_card', readonly=False, store=True)
    rental_car_type = fields.Selection(related='business_trip_data_id.rental_car_type', readonly=False, store=True)
    rental_car_drivers_license = fields.Binary(related='business_trip_data_id.rental_car_drivers_license', readonly=False)
    rental_car_drivers_license_filename = fields.Char(related='business_trip_data_id.rental_car_drivers_license_filename', readonly=False, store=True)
    rental_car_drivers_license_attachment_id = fields.Many2one(related='business_trip_data_id.rental_car_drivers_license_attachment_id', readonly=False, store=True)
    rental_car_drivers_license_download_url = fields.Char(related='business_trip_data_id.rental_car_drivers_license_download_url', readonly=False, string="Driver's License URL (Technical)")
    rental_car_drivers_license_download_link_html = fields.Html(related='business_trip_data_id.rental_car_drivers_license_download_link_html', readonly=False, string="Driver's License Download")
    rental_car_kilometer_limit = fields.Integer(related='business_trip_data_id.rental_car_kilometer_limit', readonly=False, store=True)
    rental_car_unlimited_km = fields.Boolean(related='business_trip_data_id.rental_car_unlimited_km', readonly=False, store=True)
    rental_car_preferences = fields.Text(related='business_trip_data_id.rental_car_preferences', readonly=False, store=True)

    # Return Rental Car
    # Modified by A_zeril_A, 2025-10-24: Made fields editable for new form
    return_rental_car_pickup_point = fields.Char(related='business_trip_data_id.return_rental_car_pickup_point', readonly=False, store=True)
    return_rental_car_pickup_date = fields.Date(related='business_trip_data_id.return_rental_car_pickup_date', readonly=False, store=True)
    return_rental_car_pickup_flexible = fields.Boolean(related='business_trip_data_id.return_rental_car_pickup_flexible', readonly=False, store=True)
    return_rental_car_dropoff_point = fields.Char(related='business_trip_data_id.return_rental_car_dropoff_point', readonly=False, store=True)
    return_rental_car_dropoff_date = fields.Date(related='business_trip_data_id.return_rental_car_dropoff_date', readonly=False, store=True)
    return_rental_car_dropoff_flexible = fields.Boolean(related='business_trip_data_id.return_rental_car_dropoff_flexible', readonly=False, store=True)
    return_rental_car_credit_card = fields.Selection(related='business_trip_data_id.return_rental_car_credit_card', readonly=False, store=True)
    return_rental_car_type = fields.Selection(related='business_trip_data_id.return_rental_car_type', readonly=False, store=True)
    return_rental_car_drivers_license = fields.Binary(related='business_trip_data_id.return_rental_car_drivers_license', readonly=False)
    return_rental_car_drivers_license_filename = fields.Char(related='business_trip_data_id.return_rental_car_drivers_license_filename', readonly=False, store=True)
    return_rental_car_drivers_license_attachment_id = fields.Many2one(related='business_trip_data_id.return_rental_car_drivers_license_attachment_id', readonly=False, store=True)
    return_rental_car_drivers_license_download_url = fields.Char(related='business_trip_data_id.return_rental_car_drivers_license_download_url', readonly=False, string="Return Driver's License URL (Technical)")
    return_rental_car_drivers_license_download_link_html = fields.Html(related='business_trip_data_id.return_rental_car_drivers_license_download_link_html', readonly=False, string="Return Driver's License Download")
    return_rental_car_kilometer_limit = fields.Integer(related='business_trip_data_id.return_rental_car_kilometer_limit', readonly=False, store=True)
    return_rental_car_unlimited_km = fields.Boolean(related='business_trip_data_id.return_rental_car_unlimited_km', readonly=False, store=True)
    return_rental_car_preferences = fields.Text(related='business_trip_data_id.return_rental_car_preferences', readonly=False, store=True)

    # Train
    # Modified by A_zeril_A, 2025-10-24: Made fields editable for new form
    train_departure_city = fields.Char(related='business_trip_data_id.train_departure_city', readonly=False, store=True)
    train_departure_station = fields.Char(related='business_trip_data_id.train_departure_station', readonly=False, store=True)
    train_arrival_station = fields.Char(related='business_trip_data_id.train_arrival_station', readonly=False, store=True)
    train_departure_date = fields.Date(related='business_trip_data_id.train_departure_date', readonly=False, store=True)
    train_departure_flexible = fields.Boolean(related='business_trip_data_id.train_departure_flexible', readonly=False, store=True)
    train_arrival_date = fields.Date(related='business_trip_data_id.train_arrival_date', readonly=False, store=True)
    train_arrival_flexible = fields.Boolean(related='business_trip_data_id.train_arrival_flexible', readonly=False, store=True)
    
    # Return Train
    # Modified by A_zeril_A, 2025-10-24: Made fields editable for new form
    return_train_departure_city = fields.Char(related='business_trip_data_id.return_train_departure_city', readonly=False, store=True)
    return_train_departure_station = fields.Char(related='business_trip_data_id.return_train_departure_station', readonly=False, store=True)
    return_train_arrival_station = fields.Char(related='business_trip_data_id.return_train_arrival_station', readonly=False, store=True)
    return_train_departure_date = fields.Date(related='business_trip_data_id.return_train_departure_date', readonly=False, store=True)
    return_train_departure_flexible = fields.Boolean(related='business_trip_data_id.return_train_departure_flexible', readonly=False, store=True)
    return_train_arrival_date = fields.Date(related='business_trip_data_id.return_train_arrival_date', readonly=False, store=True)
    return_train_arrival_flexible = fields.Boolean(related='business_trip_data_id.return_train_arrival_flexible', readonly=False, store=True)

    # Airplane
    # Modified by A_zeril_A, 2025-10-24: Made fields editable for new form
    airplane_departure_airport = fields.Char(related='business_trip_data_id.airplane_departure_airport', readonly=False, store=True)
    airplane_departure_date = fields.Date(related='business_trip_data_id.airplane_departure_date', readonly=False, store=True)
    airplane_departure_flexible = fields.Boolean(related='business_trip_data_id.airplane_departure_flexible', readonly=False, store=True)
    airplane_arrival_airport = fields.Char(related='business_trip_data_id.airplane_arrival_airport', readonly=False, store=True)
    airplane_arrival_flexible = fields.Boolean(related='business_trip_data_id.airplane_arrival_flexible', readonly=False, store=True)
    airplane_baggage_type = fields.Selection(related='business_trip_data_id.airplane_baggage_type', readonly=False, store=True)
    airplane_preferences = fields.Text(related='business_trip_data_id.airplane_preferences', readonly=False, store=True)

    # Return Airplane
    # Modified by A_zeril_A, 2025-10-24: Made fields editable for new form
    return_airplane_departure_airport = fields.Char(related='business_trip_data_id.return_airplane_departure_airport', readonly=False, store=True)
    return_airplane_departure_date = fields.Date(related='business_trip_data_id.return_airplane_departure_date', readonly=False, store=True)
    return_airplane_departure_flexible = fields.Boolean(related='business_trip_data_id.return_airplane_departure_flexible', readonly=False, store=True)
    return_airplane_destination_airport = fields.Char(related='business_trip_data_id.return_airplane_destination_airport', readonly=False, store=True)
    return_airplane_destination_flexible = fields.Boolean(related='business_trip_data_id.return_airplane_destination_flexible', readonly=False, store=True)
    return_airplane_baggage_type = fields.Selection(related='business_trip_data_id.return_airplane_baggage_type', readonly=False, store=True)
    return_airplane_preferences = fields.Text(related='business_trip_data_id.return_airplane_preferences', readonly=False, store=True)

    # Bus
    # Modified by A_zeril_A, 2025-10-24: Made fields editable for new form
    bus_departure_city = fields.Char(related='business_trip_data_id.bus_departure_city', readonly=False, store=True)
    bus_departure_terminal = fields.Char(related='business_trip_data_id.bus_departure_terminal', readonly=False, store=True)
    bus_arrival_terminal = fields.Char(related='business_trip_data_id.bus_arrival_terminal', readonly=False, store=True)
    bus_departure_date = fields.Date(related='business_trip_data_id.bus_departure_date', readonly=False, store=True)
    bus_departure_flexible = fields.Boolean(related='business_trip_data_id.bus_departure_flexible', readonly=False, store=True)
    bus_arrival_date = fields.Date(related='business_trip_data_id.bus_arrival_date', readonly=False, store=True)
    bus_arrival_flexible = fields.Boolean(related='business_trip_data_id.bus_arrival_flexible', readonly=False, store=True)
    
    # Return Bus
    # Modified by A_zeril_A, 2025-10-24: Made fields editable for new form
    return_bus_departure_city = fields.Char(related='business_trip_data_id.return_bus_departure_city', readonly=False, store=True)
    return_bus_departure_station = fields.Char(related='business_trip_data_id.return_bus_departure_station', readonly=False, store=True)
    return_bus_arrival_station = fields.Char(related='business_trip_data_id.return_bus_arrival_station', readonly=False, store=True)
    return_bus_departure_date = fields.Date(related='business_trip_data_id.return_bus_departure_date', readonly=False, store=True)
    return_bus_departure_flexible = fields.Boolean(related='business_trip_data_id.return_bus_departure_flexible', readonly=False, store=True)
    return_bus_arrival_date = fields.Date(related='business_trip_data_id.return_bus_arrival_date', readonly=False, store=True)
    return_bus_arrival_flexible = fields.Boolean(related='business_trip_data_id.return_bus_arrival_flexible', readonly=False, store=True)

    # --- FINANCIAL FIELDS ---
    manager_max_budget = fields.Monetary(string='Travel Approver Maximum Budget', tracking=False, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', related='business_trip_data_id.currency_id', readonly=True)

    # --- DATES & TRACKING ---
    submission_date = fields.Datetime(string='Employee Initial Submission Date', tracking=True, copy=False)
    manager_approval_date = fields.Datetime(string='Travel Approver Initial Approval Date', tracking=False, copy=False)
    manager_comments = fields.Text(string='Travel Approver Comments to Employee', tracking=True, help="Comments from Travel Approver to employee during initial review.")
    return_comments = fields.Text(string='Return Comments', tracking=True, copy=False)
    organizer_comments_to_manager = fields.Text(string='Organizer Comments to Travel Approver', tracking=True, copy=False)
    internal_manager_organizer_notes = fields.Text(
        string="Internal Travel Approver/Organizer Notes",
        tracking=True,
        copy=False,
        groups="custom_business_trip_management.group_business_trip_organizer,base.group_system",
    )
    
    # --- ORGANIZER PLAN FIELDS ---
    organizer_planned_cost = fields.Monetary(string='Total Planned Cost by Organizer', tracking=False, currency_field='currency_id')
    manual_cost_entry = fields.Boolean(string='Manual Cost Entry Mode', default=False, tracking=False, copy=False, help="Whether the total cost was entered manually instead of calculated from items")
    manual_planned_cost = fields.Monetary(string='Manual Planned Cost', tracking=False, currency_field='currency_id', copy=False, help="Manually entered total cost (when manual cost entry is enabled)")
    organizer_trip_plan_details = fields.Text(string='Organizer Trip Plan Notes', tracking=True)
    structured_plan_items_json = fields.Text(string='Structured Plan Items (JSON)', tracking=False, copy=False)
    organizer_attachments_ids = fields.Many2many('ir.attachment', 'business_trip_organizer_ir_attachments_rel', 'trip_id', 'attachment_id', string='Organizer Attachments', copy=False)
    organizer_submission_date = fields.Datetime(string='Organizer Plan Submission Date', tracking=True, copy=False)
    plan_approval_date = fields.Datetime(string='Travel Approver Plan Approval Date', tracking=True, copy=False)
    actual_start_date = fields.Datetime(string='Actual Start Date', tracking=True, copy=False)
    actual_end_date = fields.Datetime(string='Actual End Date', tracking=True, copy=False)

    # Expense Management
    expense_total = fields.Float(string="Employee Additional Expenditures", tracking=True, copy=False)
    expense_comments = fields.Text(string="Expense Submission Comments", tracking=True, copy=False)
    expense_attachment_ids = fields.Many2many('ir.attachment', 'business_trip_expense_attachment_rel', 'trip_id', 'attachment_id', string='Expense Attachments', copy=False)
    expense_approval_date = fields.Datetime(string="Expense Approval Date", tracking=True, readonly=True, copy=False)
    expense_approved_by = fields.Many2one('res.users', string="Expenses Approved By", readonly=True, copy=False)
    actual_expense_submission_date = fields.Datetime(string="Actual Expense Submission Date", readonly=True, copy=False)
    expense_return_comments = fields.Text(string="Travel Approver Comments for Expense Return", tracking=True, copy=False)

    # Final Cost & Budget
    final_total_cost = fields.Float(string='Final Total Cost', tracking=False, store=True,
                                   help="The total cost to company: planned cost plus any additional expenses.")
    budget_difference = fields.Float(string='Budget Deviation', compute='_compute_budget_difference', store=True, tracking=False,
                                     help="The remaining budget after deducting total actual costs (Planned Travel Costs + Employee Additional Expenditures) from Travel Approver Budget.")
    budget_status = fields.Selection([
        ('under_budget', 'Under Budget'),
        ('on_budget', 'On Budget'),
        ('over_budget', 'Over Budget'),
    ], string='Budget Status', compute='_compute_budget_difference', store=True, tracking=False)

    # Rejection and Cancellation
    rejection_reason = fields.Selection([
        ('budget_exceeded', 'Budget Exceeded'),
        ('timing', 'Bad Timing'),
        ('necessity', 'Not Necessary'),
        ('information', 'Insufficient Information'),
        ('plan_unsuitable', 'Travel Plan Unsuitable'),
        ('policy_violation', 'Company Policy Violation'),
        ('other', 'Other')
    ], string='Rejection Reason', tracking=True)
    rejection_comment = fields.Text(string='Rejection Details', tracking=True)
    rejected_by = fields.Many2one('res.users', string='Rejected By', tracking=True, copy=False)
    rejection_date = fields.Datetime(string='Rejection Date', tracking=True, copy=False)
    cancellation_date = fields.Datetime(string='Cancellation Date', tracking=True, copy=False)
    cancelled_by = fields.Many2one('res.users', string='Cancelled By', tracking=True, copy=False)

    # Helper fields for UI visibility
    is_manager = fields.Boolean(string='Is Travel Approver', compute='_compute_user_roles', store=False)
    is_finance = fields.Boolean(string='Is Finance', compute='_compute_user_roles', store=False)
    is_organizer = fields.Boolean(string='Is Organizer', compute='_compute_user_roles', store=False)
    can_see_costs = fields.Boolean(string='Can See Costs', compute='_compute_user_roles', store=False)
    is_current_user_owner = fields.Boolean(string="Is Current User Owner", compute='_compute_is_current_user_owner', store=False)
    can_cancel_trip = fields.Boolean(string="Can Cancel Trip", compute='_compute_can_cancel_trip', store=False)
    can_undo_expense_approval_action = fields.Boolean(string="Can Undo Expense Approval", compute='_compute_can_undo_expense_approval_action', store=False)
    can_review_expenses = fields.Boolean(string="Can Review Expenses", compute='_compute_can_review_expenses', store=False)
    is_form_fields_readonly = fields.Boolean(string="Form Fields Read-only", compute='_compute_is_form_fields_readonly', store=False,
                                              help="True when form is completed or cancelled, making all fields read-only")
    is_from_assigned_to_me = fields.Boolean(string="Is From Assigned To Me", compute='_compute_is_from_assigned_to_me', store=False)
    is_from_my_business_trip = fields.Boolean(string="Is From My Business Trip", compute='_compute_is_from_my_business_trip', store=False)

    # Smart action tracking for tree views
    action_status = fields.Selection([
        ('needs_my_action', 'Needs My Action'),
        ('waiting_for_others', 'Waiting for Others'),
        ('no_pending_action', 'No Pending Action'),
        ('closed', 'Closed'),
    ], string="Action Status", compute='_compute_action_status', readonly=True, store=False,
       help="High-level workflow status for the current user in the current menu context.")
    next_action_summary = fields.Char(
        string="Next Step",
        compute='_compute_action_status',
        readonly=True,
        store=False,
        help="Human-readable description of the next expected workflow step."
    )
    needs_my_action = fields.Boolean(string="Needs My Action", compute='_compute_action_status', readonly=True, store=False,
                                     help="True if current user needs to take urgent action on this trip")
    waiting_for_others = fields.Boolean(string="Waiting for Others", compute='_compute_action_status', readonly=True, store=False,
                                        help="True if current user is waiting for others to act")

    # NEW computed fields
    has_any_transportation = fields.Boolean(compute='_compute_has_any_transportation', string="Has Outbound Transportation")
    has_any_return_transportation = fields.Boolean(compute='_compute_has_any_return_transportation', string="Has Return Transportation")

    # --- COMPUTED FIELDS FOR DISPLAY ---
    travel_dates_display = fields.Char(string='Travel Dates', compute='_compute_travel_dates_display')
    travel_duration_days = fields.Integer(string='Requested Duration (Days)', compute='_compute_travel_duration_days')
    travel_duration_hours = fields.Integer(string='Travel Duration Hours', default=0, 
                                          help="Always 0 as hourly trips are removed")
    
    # --- Display-only computed fields ---
    # These fields are for display purposes only, to format dates and times according to the user's timezone.
    
    # Renamed to avoid label conflict
    actual_start_date_display = fields.Char(string="Actual Start Date (Display)", compute='_compute_actual_dates_display')
    actual_end_date_display = fields.Char(string="Actual End Date (Display)", compute='_compute_actual_dates_display')
    actual_duration_display = fields.Char(string="Actual Duration", compute='_compute_actual_dates_display')
    
    # --- Other Display Fields ---
    approver_name = fields.Char(string='Approver Name', compute='_compute_approver_name', store=False)
    
    # Additional fields needed for form compatibility
    travel_duration = fields.Float(string='Travel Duration', default=0.0,
                                  help="Travel duration field for compatibility with form calculations")
    
    trip_request_notes = fields.Text(string='Trip Request Notes', help="Notes from the employee about the trip request")

    # --- NEW FIELDS MIGRATED FROM FORMIO_FORM_INHERIT ---
    
    # Helper fields for attachments and notes
    attachment_ids = fields.Many2many('ir.attachment', 'business_trip_attachment_rel', 'trip_id', 'attachment_id', string='Attachments')
    notes = fields.Text(string='Notes')
    
    # For storing employee tickets and travel documents
    employee_documents_ids = fields.Many2many('ir.attachment',
                                           'business_trip_employee_docs_rel',
                                           'trip_id', 'attachment_id',
                                           string='Employee Travel Documents',
                                           help="Documents for the employee such as tickets, reservations, etc.")
    
    # Flag to track forms being edited in returned state
    edit_in_returned_state = fields.Boolean(string='Edit in Returned State', default=False,
        help="Technical field to track forms being edited while in returned state")

    # Computed fields for status phases and role display
    trip_status_phase2 = fields.Selection([
        ('awaiting_trip_end', 'Awaiting Trip End'),
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
    
    # Organizer plan display fields
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
    
    # Additional computed fields for status phases that are needed for the compute methods
    trip_status_phase1 = fields.Selection([
        ('draft', 'Awaiting Submission'),
        ('submitted', 'To Travel Approver'),
        ('pending_organization', 'To Organizer'),
        ('organization_done', 'Organization Completed'),
        ('returned', 'Returned to Employee'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled')
    ], string='Trip Status (Phase 1)', compute='_compute_trip_status_phases', store=False)
    
    # Exception status fields for phase one  
    is_returned = fields.Boolean(string='Is Returned', compute='_compute_exceptional_statuses', store=False)
    is_rejected = fields.Boolean(string='Is Rejected', compute='_compute_exceptional_statuses', store=False)

    # ADDED: Fields from old model to support detailed organizer workflow
    organizer_confirmation_date = fields.Datetime(
        string='Organizer Confirmation Date',
        tracking=True,
        copy=False,
        readonly=True,
        help='Date and time the organizer confirmed the trip plan.'
    )
    organizer_confirmed_by = fields.Many2one('res.users', string='Plan Confirmed By', readonly=True, copy=False)
    
    plan_approval_date = fields.Datetime(string='Travel Approver Plan Approval Date', tracking=True, copy=False)
    actual_start_date = fields.Datetime(string='Actual Start Date', tracking=True, copy=False)
    actual_end_date = fields.Datetime(string='Actual End Date', tracking=True, copy=False)

    # ADDED: Fields for expense submission reminders
    organization_done_date = fields.Datetime(
        string='Organization Done Date',
        readonly=True,
        copy=False,
        help="Date when the organizer confirmed the trip plan."
    )
    expense_followup_start_date = fields.Datetime(
        string='Expense Follow-up Start Date',
        copy=False,
        help="Stable timestamp marking when the expense follow-up phase started after organizer planning was finalized."
    )
    last_expense_reminder_date = fields.Datetime(
        string='Last Expense Reminder Date',
        copy=False,
        help="The date and time this trip was last included in an expense reviewer follow-up digest."
    )
    employee_expense_reminder_sent_date = fields.Datetime(
        string='Employee Expense Reminder Sent Date',
        copy=False,
        help="The date and time this trip was last included in an employee expense follow-up digest."
    )

    # ADDED: Fields from old model to support detailed organizer workflow
    temp_manager_max_budget = fields.Float(
        string='Temporary Travel Approver Max Budget',
        tracking=False,
        copy=False,
        help="A temporary budget set by the Travel Approver before final confirmation."
    )

    # Modified by A_zeril_A, 2025-10-28: Removed duplicate return_rental_car fields (already defined above with readonly=False)
    # These fields were causing the "Unlimited Kilometers" checkbox to be readonly in the form
    
    # Accompanying persons HTML
    accompanying_persons_html = fields.Html(related='business_trip_data_id.accompanying_persons_html', readonly=True, string="Accompanying Persons List")
    
    # Modified by A_zeril_A, 2025-10-25: Removed duplicate use_train and train_departure_city fields (already defined above as editable)

    is_expense_returned = fields.Boolean(string='Is Expense Returned', compute='_compute_exceptional_statuses', store=False)
    
    effective_trip_status = fields.Selection(
        string='Effective Trip Status',
        selection='_get_trip_status_selection',
        compute='_compute_effective_trip_status',
        store=False,
        help="Technical field to dynamically map legacy statuses to their new equivalents."
    )
    
    # --- UI & UX HELPER FIELDS ---
    can_edit_request = fields.Boolean(compute='_compute_can_edit_request', string='Can Edit Request')
    can_submit_expenses = fields.Boolean(compute='_compute_can_submit_expenses', string='Can Submit Expenses')

    def _get_expense_review_role_label(self):
        """Return the business role responsible for expense review on this trip."""
        self.ensure_one()
        return "Commercial Director" if self.sale_order_id else "CEO"

    def _get_expense_reviewer_by_job_title(self, job_title):
        self.ensure_one()
        company = self.company_id or self.env.company
        employee = self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', company.id),
            ('user_id', '!=', False),
            ('user_id.active', '=', True),
            '|',
            ('job_title', '=ilike', job_title),
            ('job_id.name', '=ilike', job_title),
        ], limit=1)
        return employee.user_id if employee else self.env['res.users']

    def _resolve_expense_review_user(self):
        """Resolve the configured reviewer for a trip without mutating it."""
        self.ensure_one()
        company = self.company_id or self.env.company
        if self.sale_order_id:
            return (
                company.sudo().business_trip_sale_order_expense_reviewer_id
                or self._get_expense_reviewer_by_job_title("Commercial Director")
            )
        return (
            company.sudo().business_trip_standalone_expense_reviewer_id
            or self._get_expense_reviewer_by_job_title("CEO")
        )

    def _get_expense_review_user(self):
        """Return the user who must review submitted expenses by business role."""
        self.ensure_one()
        return self.expense_reviewer_id or self._resolve_expense_review_user()

    def _get_expense_review_display_name(self):
        self.ensure_one()
        reviewer = self._get_expense_review_user()
        return reviewer.name or self._get_expense_review_role_label()

    @api.depends('sale_order_id', 'expense_reviewer_id')
    @api.depends_context('uid')
    def _compute_can_review_expenses(self):
        for record in self:
            record.can_review_expenses = record._can_current_user_review_expenses()

    @api.depends('manager_id', 'organizer_id', 'user_id')
    @api.depends_context('uid', 'from_assigned_to_me')
    def _compute_user_roles(self):
        for record in self:
            user = self.env.user
            is_system_admin = user.has_group('base.group_system')
            is_trip_owner = (record.user_id.id == user.id)
            from_assigned_to_me = self.env.context.get('from_assigned_to_me', False)

            # CRITICAL SECURITY: If the current user is the trip owner/requester, 
            # they should ONLY see requester interface in "My Business Trip" menu
            # Exception: If owner is also manager/organizer and accessing from "Assigned to Me",
            # they can see management interface
            if is_trip_owner:
                # Check if owner is assigned as manager and accessing from "Assigned to Me"
                is_assigned_manager = (record.manager_id and user.id == record.manager_id.id)
                record.is_manager = is_assigned_manager and from_assigned_to_me
                
                # An owner can be the organizer of their own trip.
                record.is_organizer = (record.organizer_id and user.id == record.organizer_id.id)
                
                # Finance role is still disallowed for self-trip-management to maintain separation of duties.
                record.is_finance = False
                
                # An organizer or manager must see trip costs to plan effectively.
                record.can_see_costs = record.is_organizer or record.is_manager
                continue

            if is_system_admin:
                record.is_manager = True
                record.is_finance = True
                record.is_organizer = True
                record.can_see_costs = True
                continue

            record.is_manager = (record.manager_id and user.id == record.manager_id.id)
            record.is_organizer = (record.organizer_id and user.id == record.organizer_id.id)
            is_finance_user = user.has_group('account.group_account_manager')
            is_expense_reviewer = (
                record.expense_reviewer_id
                and user.id == record.expense_reviewer_id.id
            )
            is_auditor = user.has_group(
                'custom_business_trip_management.group_business_trip_auditor'
            )
            is_trip_admin = user.has_group(
                'custom_business_trip_management.group_business_trip_manager'
            )
            record.is_finance = (
                record.is_organizer
                or is_finance_user
                or is_expense_reviewer
                or is_auditor
            )
            
            is_in_organizer_group = user.has_group('custom_business_trip_management.group_business_trip_organizer')
            record.can_see_costs = (
                record.is_manager
                or record.is_organizer
                or is_in_organizer_group
                or is_expense_reviewer
                or is_auditor
                or is_trip_admin
            )

    def _can_current_user_review_expenses(self):
        """Return whether the current user can review submitted trip expenses."""
        self.ensure_one()
        user = self.env.user
        reviewer = self._get_expense_review_user()
        return bool(
            user.has_group('base.group_system')
            or (reviewer and user.id == reviewer.id)
        )

    def _get_expense_review_actor_role(self):
        """Return the role label used in expense review notifications."""
        self.ensure_one()
        user = self.env.user
        reviewer = self._get_expense_review_user()
        if reviewer and user.id == reviewer.id:
            return self._get_expense_review_role_label()
        if user.has_group('base.group_system'):
            return "System Administrator"
        return "Reviewer"

    @api.depends_context('uid')
    def _compute_is_current_user_owner(self):
        for record in self:
            record.is_current_user_owner = (record.user_id.id == self.env.user.id)

    @api.depends('trip_status', 'form_completion_status', 'has_trip_details', 'user_id', 'manager_id', 'organizer_id')
    @api.depends_context('uid', 'from_assigned_to_me', 'from_my_business_trip')
    def _compute_action_status(self):
        """
        Compute a user-facing workflow status plus helper booleans for list decorations.
        The result is menu-aware:
        - In "My Business Trip Forms", it follows the employee/requester perspective.
        - In "Assigned to Me", it follows the assigned reviewer/organizer perspective.
        """
        user = self.env.user
        user_id = user.id
        is_finance_user = user.has_group('account.group_account_manager')
        is_admin_user = user.has_group('base.group_system')
        from_assigned_to_me = bool(self.env.context.get('from_assigned_to_me'))
        from_my_business_trip_ctx = self.env.context.get('from_my_business_trip')

        for record in self:
            is_employee = bool(record.user_id and record.user_id.id == user_id)
            is_manager = bool(record.manager_id and record.manager_id.id == user_id)
            is_organizer = bool(record.organizer_id and record.organizer_id.id == user_id)
            is_expense_reviewer = record._can_current_user_review_expenses()
            expense_reviewer_label = record._get_expense_review_role_label()

            if from_my_business_trip_ctx is None:
                from_my_business_trip = is_employee and not from_assigned_to_me
            else:
                from_my_business_trip = bool(from_my_business_trip_ctx)

            status = record.trip_status
            if status in ('awaiting_trip_start', 'in_progress'):
                status = 'completed_waiting_expense'

            action_status = 'no_pending_action'
            next_step = "No pending workflow step."

            def set_state(category, summary):
                nonlocal action_status, next_step
                action_status = category
                next_step = summary

            def set_employee_status():
                if status == 'draft':
                    if record.form_completion_status != 'form_completed' or not record.has_trip_details:
                        set_state('needs_my_action', "Complete the trip form and required details.")
                    else:
                        set_state('needs_my_action', "Submit the request for approval.")
                elif status == 'submitted':
                    set_state('waiting_for_others', "Waiting for the Travel Approver to review the request.")
                elif status == 'returned':
                    if record.form_completion_status != 'form_completed' or not record.has_trip_details:
                        set_state('needs_my_action', "Complete the returned form and required details before resubmitting.")
                    else:
                        set_state('needs_my_action', "Resubmit the request for approval.")
                elif status == 'pending_organization':
                    set_state('waiting_for_others', "Waiting for the Organizer to prepare and confirm the trip plan.")
                elif status == 'organization_done':
                    set_state('no_pending_action', "Trip plan confirmed. Complete the trip and submit expenses afterward.")
                elif status == 'completed_waiting_expense':
                    set_state('needs_my_action', "Submit expenses or confirm there were no additional expenses.")
                elif status == 'expense_submitted':
                    set_state('waiting_for_others', f"Waiting for the {expense_reviewer_label} to review submitted expenses.")
                elif status == 'expense_returned':
                    set_state('needs_my_action', "Revise and resubmit the expense submission.")
                elif status == 'completed':
                    set_state('closed', "Trip workflow completed.")
                elif status == 'rejected':
                    set_state('closed', "Request rejected.")
                elif status == 'cancelled':
                    set_state('closed', "Request cancelled.")
                else:
                    set_state('no_pending_action', "No pending workflow step.")

            def set_assignee_status():
                if status == 'draft':
                    set_state('waiting_for_others', "Waiting for the employee to complete and submit the request.")
                elif status == 'submitted':
                    if is_manager:
                        set_state('needs_my_action', "Assign the organizer and budget, or return/reject the request.")
                    else:
                        set_state('waiting_for_others', "Waiting for the assigned Travel Approver to review the request.")
                elif status == 'returned':
                    if is_manager:
                        set_state('waiting_for_others', "Waiting for the employee to revise and resubmit the request.")
                    else:
                        set_state('no_pending_action', "Request is back with the employee for correction.")
                elif status == 'pending_organization':
                    if is_organizer:
                        set_state('needs_my_action', "Prepare the trip plan and confirm it.")
                    else:
                        set_state('waiting_for_others', "Waiting for the Organizer to complete the trip plan.")
                elif status == 'organization_done':
                    set_state('no_pending_action', "Trip plan confirmed. Waiting for the trip to finish before expenses are submitted.")
                elif status == 'completed_waiting_expense':
                    set_state('waiting_for_others', "Waiting for the employee to submit expenses or confirm no additional expenses.")
                elif status == 'expense_submitted':
                    if is_expense_reviewer:
                        set_state('needs_my_action', "Review the expense submission: approve it or return it for revision.")
                    elif is_manager:
                        set_state('waiting_for_others', f"Waiting for the {expense_reviewer_label} to review submitted expenses.")
                    else:
                        set_state('waiting_for_others', "Waiting for the assigned reviewer to handle the expense submission.")
                elif status == 'expense_returned':
                    set_state('waiting_for_others', "Waiting for the employee to correct and resubmit the expense submission.")
                elif status == 'completed':
                    set_state('closed', "Trip workflow completed.")
                elif status == 'rejected':
                    set_state('closed', "Request rejected.")
                elif status == 'cancelled':
                    set_state('closed', "Request cancelled.")
                else:
                    set_state('no_pending_action', "No pending workflow step.")

            if from_assigned_to_me:
                set_assignee_status()
            elif from_my_business_trip and is_employee:
                set_employee_status()
            elif is_employee:
                set_employee_status()
            elif is_manager or is_organizer or is_finance_user or is_admin_user or is_expense_reviewer:
                set_assignee_status()
            elif status in ['completed', 'rejected', 'cancelled']:
                set_state('closed', "No further workflow action is expected.")
            else:
                set_state('no_pending_action', "No pending workflow step.")

            record.action_status = action_status
            record.next_action_summary = next_step
            record.needs_my_action = action_status == 'needs_my_action'
            record.waiting_for_others = action_status == 'waiting_for_others'

    @api.depends('trip_status', 'manager_approval_date', 'is_current_user_owner')
    @api.depends_context('uid')
    def _compute_can_cancel_trip(self):
        for record in self:
            can_cancel = False
            # We rely on the pre-computed is_current_user_owner field
            if record.is_current_user_owner and record.trip_status in ['draft']:
                can_cancel = True
            record.can_cancel_trip = can_cancel

    @api.depends('form_completion_status')
    def _compute_is_form_fields_readonly(self):
        """
        Compute if form fields should be read-only.
        Fields are read-only when form is completed or cancelled.
        """
        for record in self:
            record.is_form_fields_readonly = record.form_completion_status in ['form_completed', 'cancelled']

    @api.depends('trip_status', 'expense_approval_date')
    def _compute_can_undo_expense_approval_action(self):
        # Get the setting from the environment's company once
        # Using a default value if not configured to avoid errors.
        undo_limit_days = getattr(self.env.company, 'undo_expense_approval_days_limit', 0)

        for record in self:
            can_undo = False
            # User must be a system admin or in a specific elevated group.
            is_approver = self.env.user.has_group('base.group_system') or self.env.user.has_group('account.group_account_manager')

            if record.trip_status == 'completed' and is_approver:
                if record.expense_approval_date:
                    if undo_limit_days > 0:
                        approval_date_limit = record.expense_approval_date + relativedelta(days=undo_limit_days)
                        if fields.Datetime.now() <= approval_date_limit:
                            can_undo = True
                    else: # If limit is 0 or negative, undo is always allowed by an approver.
                        can_undo = True
            record.can_undo_expense_approval_action = can_undo

    @api.depends_context('from_assigned_to_me')
    def _compute_is_from_assigned_to_me(self):
        """Check if the record is accessed from 'Assigned to Me' menu"""
        for record in self:
            record.is_from_assigned_to_me = self.env.context.get('from_assigned_to_me', False)

    @api.depends_context('from_my_business_trip')
    def _compute_is_from_my_business_trip(self):
        """
        Check if the record is accessed from 'My Business Trip' context.

        In Odoo 18 the same record can be opened either via an action URL
        (e.g. `/odoo/action-.../<id>`) or directly via the model URL
        (e.g. `/odoo/business.trip/<id>`). The latter does not always carry the
        `from_my_business_trip` context flag, which would incorrectly hide
        employee-facing buttons (Submit/Resubmit/Relink) for the record owner.

        Policy:
        - If context explicitly sets `from_my_business_trip`, respect it.
        - Otherwise, treat the record as "My Business Trip" when the current
          user is the owner (employee) of the request.
        """
        for record in self:
            ctx_flag = self.env.context.get('from_my_business_trip')
            if ctx_flag is None:
                record.is_from_my_business_trip = (record.user_id.id == self.env.user.id)
            else:
                record.is_from_my_business_trip = bool(ctx_flag)

    @api.depends('organizer_planned_cost', 'expense_total', 'manager_max_budget')
    def _compute_budget_difference(self):
        for trip in self:
            if trip.manager_max_budget > 0 and trip.organizer_planned_cost >= 0:
                # Total actual cost = Planned Travel Costs + Employee Additional Expenditures
                total_actual_cost = trip.organizer_planned_cost + trip.expense_total
                # Budget Deviation = Travel Approver Budget - Total Actual Cost
                trip.budget_difference = trip.manager_max_budget - total_actual_cost
                if trip.budget_difference < 0:
                    trip.budget_status = 'over_budget'
                elif trip.budget_difference == 0:
                    trip.budget_status = 'on_budget'
                else:
                    trip.budget_status = 'under_budget'
            else:
                trip.budget_difference = 0
                trip.budget_status = False

    def _check_not_trip_owner_for_management_action(self, action_name):
        """
        CRITICAL SECURITY: Ensure trip owners cannot perform management actions on their own trips
        Exception: If the owner is also the assigned manager/organizer and accessing from 'Assigned to Me',
        they can perform management actions in that specific context.
        """
        user = self.env.user
        is_owner = (self.user_id.id == user.id)
        
        if not is_owner:
            # Not the owner, allow the action
            return
        
        # Owner is trying to perform action
        # Check if they are assigned as organizer
        if self.organizer_id and self.organizer_id.id == user.id:
            return
        
        # Check if they are assigned as manager and accessing from "Assigned to Me"
        from_assigned_to_me = self.env.context.get('from_assigned_to_me', False)
        is_assigned_manager = (self.manager_id and self.manager_id.id == user.id)
        
        if is_assigned_manager and from_assigned_to_me:
            # Owner is the assigned manager and accessing from correct menu
            return

        if is_assigned_manager:
            # Legitimate self-approval (nobody sits above this requester), but
            # opened from the wrong menu. Tell them how to proceed instead of
            # implying they did something forbidden.
            raise ValidationError(
                f"You are the assigned Travel Approver for this request, so "
                f"you may perform '{action_name}' on it. Management actions "
                f"are only available from the \"Assigned to Me\" menu, not "
                f"from \"My Business Trip\". Please open this request from "
                f"\"Assigned to Me\" and try again."
            )

        # Owner trying to manage a trip they are not the assigned approver of
        raise ValidationError(
            f"SECURITY VIOLATION: You cannot perform the '{action_name}' action on your own trip request. "
            f"Management actions can only be performed by other authorized users, never by the trip requester. "
            f"This security rule applies to all users regardless of their system access level."
        )

    def action_approve_expenses(self):
        """
        Approve trip expenses by the configured expense reviewer or system administrators.
        """
        self.ensure_one()
        if self.trip_status != 'expense_submitted':
            raise ValidationError("You can only approve expenses that have been submitted for review.")

        # Prevent trip owners from approving their own expenses
        self._check_not_trip_owner_for_management_action("Approve Expenses")

        # Check permissions for expense approval
        if not self._can_current_user_review_expenses():
            raise ValidationError(
                f"Only the {self._get_expense_review_role_label()} or system administrators can approve expenses."
            )

        # Calculate final total cost
        total_cost = self.organizer_planned_cost + self.expense_total

        self.with_context(
            authorized_business_trip_assignment=True,
        ).write({
            'trip_status': 'completed',
            'expense_approval_date': fields.Datetime.now(),
            'expense_approved_by': self.env.user.id,
            'final_total_cost': total_cost,
        })

        # Chatter notifications
        budget_message = ""
        if self.budget_difference > 0:
            budget_message = f"<span style='color:green'>Trip completed {abs(self.budget_difference):.2f} {self.currency_id.symbol} under budget.</span>"
        elif self.budget_difference < 0:
            budget_message = f"<span style='color:red'>Trip exceeded budget by {abs(self.budget_difference):.2f} {self.currency_id.symbol}.</span>"
        else:
            budget_message = "<span style='color:blue'>Trip completed exactly on budget.</span>"

        reviewer_name = self.env.user.name
        expense_reviewer = self._get_expense_review_user()
        expense_reviewer_label = self._get_expense_review_role_label()

        # Send personalized approval messages to each stakeholder
        
        # 1. Message to the configured expense reviewer
        if expense_reviewer:
            reviewer_review_outcome = (
                "You approved the submitted expenses and completed the trip review."
                if expense_reviewer.id == self.env.user.id
                else f"The submitted expenses were approved by <strong>{reviewer_name}</strong>."
            )
            reviewer_approval_msg = f"""
<div style="background-color: #d1ecf1; border: 1px solid #bee5eb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #0c5460; font-size: 20px; margin-right: 10px;">🎊</span>
        <span style="font-weight: bold; color: #0c5460; font-size: 16px;">Expense Review Completed</span>
    </div>
    <p style="margin: 5px 0 10px 0;">The expense review for '<strong>{self.name}</strong>' has been completed.</p>
    <div style="background-color: #fff; border: 1px solid #17a2b8; padding: 10px; margin-top: 5px; border-radius: 3px;">
        <p style="margin: 0 0 5px 0; font-weight: bold; color: #0c5460;">{expense_reviewer_label} Review Summary:</p>
        <ul style="margin: 5px 0; padding-left: 20px; color: #333;">
            <li>Budget Allocated: <strong>{self.manager_max_budget:.2f} {self.currency_id.symbol}</strong></li>
            <li>Planned Costs: <strong>{self.organizer_planned_cost:.2f} {self.currency_id.symbol}</strong></li>
            <li>Employee Additional Expenditures: <strong>{self.expense_total:.2f} {self.currency_id.symbol}</strong></li>
            <li>Total Actual Cost: <strong>{self.organizer_planned_cost + self.expense_total:.2f} {self.currency_id.symbol}</strong></li>
            <li>Planning Accuracy: {budget_message}</li>
        </ul>
    </div>
    <div style="background-color: #fff; border-left: 4px solid #17a2b8; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Review Outcome:</strong> {reviewer_review_outcome}</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">✅ Review Closed</span>
    </div>
</div>
"""
            self.sudo().post_confidential_message(
                message=reviewer_approval_msg,
                recipient_ids=[expense_reviewer.id]
            )

        # 2. Message to Employee (trip completion confirmation)
        if self.user_id.partner_id:
            employee_approval_msg = f"""
<div style="background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #155724; font-size: 20px; margin-right: 10px;">🎉</span>
        <span style="font-weight: bold; color: #155724; font-size: 16px;">Congratulations! Your Trip is Now Complete</span>
    </div>
    <p style="margin: 5px 0 10px 0;">Great news! Your travel expense submission for trip '<strong>{self.name}</strong>' has been approved by <strong>{reviewer_name}</strong>.</p>
    <div style="background-color: #fff; border-left: 4px solid #28a745; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Trip Status:</strong> COMPLETED ✅<br/>
        <strong>What's Next:</strong> Your expenses will be processed according to company policy. Your business trip is now officially closed.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">🎯 Trip Complete</span>
    </div>
</div>
"""
            # Odoo 18: Wrap HTML in Markup for proper rendering
            self._post_message_with_record_link(
                body=Markup(employee_approval_msg),
                partner_ids=[self.user_id.partner_id.id]
            )

        # 3. System log message (internal tracking)
        self._post_message_with_record_link(
            body=(
                f"Travel expenses for business trip '{self.name}' have been approved by "
                f"{reviewer_name}. Trip status changed to COMPLETED."
            ),
            subtype_xmlid='mail.mt_note'
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_return_expenses(self):
        """
        Return trip expenses to employee for correction
        """
        self.ensure_one()
        if self.trip_status != 'expense_submitted':
            raise ValidationError("You can only return expenses that have been submitted for review.")

        # Check permissions for expense return
        if not self._can_current_user_review_expenses():
            raise ValidationError(
                f"Only the {self._get_expense_review_role_label()} or system administrators can return expenses."
            )

        self.write({'trip_status': 'expense_returned'})
        reviewer_name = self.env.user.name
        expense_reviewer = self._get_expense_review_user()
        expense_reviewer_label = self._get_expense_review_role_label()
        
        # Send personalized messages to stakeholders about expense return
        
        # 1. Message to the configured expense reviewer (if not the one returning)
        if expense_reviewer and self.env.user.id != expense_reviewer.id:
            reviewer_return_msg = f"""
<div style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #856404; font-size: 20px; margin-right: 10px;">🔄</span>
        <span style="font-weight: bold; color: #856404; font-size: 16px;">Expense Revision Required</span>
    </div>
    <p style="margin: 5px 0 10px 0;">The expenses for <strong>{self.user_id.name}</strong>'s trip ('<strong>{self.name}</strong>') have been returned for revision by <strong>{reviewer_name}</strong>.</p>
    <div style="background-color: #fff; border-left: 4px solid #ffc107; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>{expense_reviewer_label} Note:</strong> The employee will correct and resubmit expenses. Please review the updated submission once it is resubmitted.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #ffc107; color: #856404; padding: 5px 10px; border-radius: 3px; font-size: 12px;">🔄 Revision Phase</span>
    </div>
</div>
"""
            if self.expense_return_comments:
                reviewer_return_msg += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px;">
    <p style="margin: 0 0 5px 0; font-weight: bold;">Return Comments:</p>
    <p style="margin: 0; color: #333;">{self.expense_return_comments}</p>
</div>
"""
            self.sudo().post_confidential_message(
                message=reviewer_return_msg,
                recipient_ids=[expense_reviewer.id]
            )

        # 2. Message to Employee (detailed revision request)
        if self.user_id.partner_id:
            employee_return_msg = f"""
<div style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #856404; font-size: 20px; margin-right: 10px;">✏️</span>
        <span style="font-weight: bold; color: #856404; font-size: 16px;">Please Revise Your Expense Submission</span>
    </div>
    <p style="margin: 5px 0 10px 0;">Your travel expense submission for trip '<strong>{self.name}</strong>' has been returned for revision by <strong>{self.env.user.name}</strong>.</p>
    <div style="background-color: #fff; border-left: 4px solid #ffc107; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>What to do next:</strong><br/>
        1. Review the comments below carefully<br/>
        2. Make the necessary corrections to your expense submission<br/>
        3. Resubmit your expenses through the system<br/>
        4. The {expense_reviewer_label} will review the revised submission</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #ffc107; color: #856404; padding: 5px 10px; border-radius: 3px; font-size: 12px; font-weight: bold;">⚠️ Action Required</span>
    </div>
</div>
"""
            if self.expense_return_comments:
                employee_return_msg += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #dc3545; padding: 10px; margin-top: 10px; border-radius: 3px;">
    <p style="margin: 0 0 5px 0; font-weight: bold; color: #dc3545;">📝 Review Comments - Please Address These Points:</p>
    <p style="margin: 0; color: #333; background-color: #fff; padding: 8px; border-radius: 3px;">{self.expense_return_comments}</p>
</div>
"""
            # Odoo 18: Wrap HTML in Markup for proper rendering
            self._post_message_with_record_link(
                body=Markup(employee_return_msg),
                partner_ids=[self.user_id.partner_id.id]
            )

        # 3. System log message
        self._post_message_with_record_link(
            body=(
                f"Travel expenses for trip '{self.name}' have been returned for revision by "
                f"{reviewer_name}. Once resubmitted, the {expense_reviewer_label} will review them."
            ),
            subtype_xmlid='mail.mt_note'
        )
            
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_open_rejection_wizard(self):
        """Open wizard for rejecting the trip request."""
        self.ensure_one()

        if self.trip_status not in ['submitted']:
            raise ValidationError("You can only reject requests that are in 'Submitted to Travel Approver' state using this wizard.")

        # Prevent trip owners from rejecting their own trip
        self._check_not_trip_owner_for_management_action("Reject Trip")

        if not (self.env.user.has_group('base.group_system') or 
                (self.manager_id and self.env.user.id == self.manager_id.id) or
                self.env.user.has_group('custom_business_trip_management.group_business_trip_manager')):
            raise ValidationError("Only the assigned Travel Approver or system administrators can reject the request.")

        return {
            'name': 'Reject Business Trip',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.rejection.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_trip_id': self.id,
            }
        }

    def action_cancel_trip(self):
        """Cancel a business trip request and mark it as cancelled."""
        self.ensure_one()

        if self.user_id.id != self.env.user.id:
            raise ValidationError("Only the owner of this trip request can cancel it.")

        if self.trip_status not in ['draft', 'submitted']:
            raise ValidationError("You can only cancel requests that are in 'Draft' or 'Submitted' state.")
        
        # For submitted state, check if it's already been actioned by management
        if self.trip_status == 'submitted' and \
           (self.manager_approval_date or self.organizer_submission_date or self.organizer_id or \
            self.trip_status in ['rejected']):
            raise ValidationError("This request has already been processed by management and cannot be cancelled.")

        self.write({
            'trip_status': 'cancelled',
            'form_completion_status': 'cancelled',
            'cancellation_date': fields.Datetime.now(),
            'cancelled_by': self.env.user.id,
        })

        # if self.formio_form_id:
        #     self.formio_form_id.write({'state': 'CANCEL'})

        self._post_message_with_record_link(body=f"Request cancelled by {self.env.user.name}.")

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_open_expense_submission_wizard(self):
        """Open wizard for submitting actual expenses."""
        self.ensure_one()

        if self.trip_status not in ['completed_waiting_expense', 'expense_returned', 'in_progress', 'awaiting_trip_start']:
            raise ValidationError(f"You can only submit expenses when the trip is in 'Awaiting Travel Expenses' or 'Expense Returned' state. Current state: {self.trip_status}")

        # Only the owner can open the expense submission wizard
        if self.user_id.id != self.env.user.id:
            raise ValidationError("Only the owner of this request can submit expenses.")

        return {
            'name': 'Submit Travel Expenses',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.expense.submission.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_trip_id': self.id, 
            }
        }

    # --- COMPUTED FIELDS FOR VALIDATION ---
    has_trip_details = fields.Boolean(string='Has Trip Details', compute='_compute_has_trip_details', help="Technical field to check if all required trip details are filled.")

    active = fields.Boolean(default=True)

    @api.depends('use_rental_car', 'use_company_car', 'use_personal_car', 'use_train', 'use_airplane', 'use_bus')
    def _compute_has_any_transportation(self):
        for trip in self:
            trip.has_any_transportation = any([
                trip.use_rental_car, trip.use_company_car, trip.use_personal_car,
                trip.use_train, trip.use_airplane, trip.use_bus
            ])

    @api.depends('use_return_rental_car', 'use_return_company_car', 'use_return_personal_car', 'use_return_train', 'use_return_airplane', 'use_return_bus')
    def _compute_has_any_return_transportation(self):
        for trip in self:
            trip.has_any_return_transportation = any([
                trip.use_return_rental_car, trip.use_return_company_car, trip.use_return_personal_car,
                trip.use_return_train, trip.use_return_airplane, trip.use_return_bus
            ])

    @api.constrains('user_id', 'company_id', 'sale_order_id')
    def _check_business_trip_company(self):
        for trip in self:
            if trip.company_id not in trip.user_id.company_ids:
                raise ValidationError(
                    "The employee is not allowed to access the trip company."
                )
            if (
                trip.sale_order_id
                and trip.sale_order_id.company_id
                and trip.sale_order_id.company_id != trip.company_id
            ):
                raise ValidationError(
                    "The business trip and sale order must belong to the same company."
                )

    @api.constrains('organizer_id', 'company_id', 'trip_status')
    def _check_active_company_organizer(self):
        final_statuses = ('completed', 'rejected', 'cancelled')
        for trip in self:
            organizer_pool = trip.company_id.business_trip_organizer_ids
            if (
                trip.organizer_id
                and organizer_pool
                and trip.trip_status not in final_statuses
                and trip.organizer_id not in organizer_pool
            ):
                raise ValidationError(
                    "Non-final trips must be assigned to one of the "
                    "organizers configured for their company."
                )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Create the parent trip first, then create its secured data record with
        a valid back-reference so record rules are enforceable from creation.
        """
        trips_to_return = self.env['business.trip']
        for incoming_vals in vals_list:
            vals = dict(incoming_vals)
            is_privileged_creator = (
                self.env.su
                or self.env.user.has_group('base.group_system')
                or self.env.user.has_group(
                    'custom_business_trip_management.group_business_trip_manager'
                )
            )
            requested_manager_id = vals.get('manager_id')
            if not is_privileged_creator:
                for protected_field in (
                    'manager_id',
                    'organizer_id',
                    'expense_reviewer_id',
                    'trip_status',
                ):
                    vals.pop(protected_field, None)

            user_id = vals.get('user_id') or self.env.user.id
            if not is_privileged_creator:
                user_id = self.env.user.id
            user = self.env['res.users'].browse(user_id)
            sale_order = (
                self.env['sale.order'].browse(vals['sale_order_id'])
                if vals.get('sale_order_id')
                else self.env['sale.order']
            )
            company = (
                sale_order.company_id
                or self.env['res.company'].browse(vals.get('company_id'))
                or self.env.company
            )
            vals.update({
                'user_id': user.id,
                'company_id': company.id,
            })
            vals.pop('business_trip_data_id', None)
            
            user_name = user.partner_id.name or user.name or ''
            name_parts = user_name.strip().split()
            if len(name_parts) == 1:
                first_name = name_parts[0]
                last_name = ''
            elif len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
            else:
                first_name = 'N/A'
                last_name = ''

            new_trip = super(BusinessTrip, self.with_context(mail_create_nosubscribe=True)).create(vals)
            trip_data = self.env['business.trip.data'].create({
                'form_id': new_trip.id,
                'first_name': first_name,
                'last_name': last_name,
            })

            reviewer = new_trip._resolve_expense_review_user()
            manager = self.env['res.users']
            if requested_manager_id and is_privileged_creator:
                manager = self.env['res.users'].browse(requested_manager_id)
            else:
                approver_model = self.env['res.users'].sudo().with_company(
                    company
                )
                if sale_order:
                    approver_id = approver_model.get_travel_approver_for_sale_order(
                        user.id
                    )
                else:
                    approver_id = (
                        company.sudo().business_trip_standalone_approver_id.id
                    )
                if approver_id:
                    manager = self.env['res.users'].browse(approver_id)

            reviewer_group = self.env.ref(
                'custom_business_trip_management.group_business_trip_expense_reviewer',
                raise_if_not_found=False,
            )
            if reviewer and reviewer_group and reviewer_group not in reviewer.groups_id:
                reviewer.sudo().write({'groups_id': [(4, reviewer_group.id)]})

            link_vals = {'business_trip_data_id': trip_data.id}
            if reviewer:
                link_vals['expense_reviewer_id'] = reviewer.id
            if manager:
                link_vals['manager_id'] = manager.id
            super(BusinessTrip, new_trip).write(link_vals)

            if manager:
                manager.ensure_business_trip_approver_capability()
            
            # Post a simple creation message. The complex message was tied to the formio form.
            message_body = """
            <div style="background-color: #EBF5FF; border: 1px solid #B3D4FF; border-radius: 5px; padding: 15px; margin: 10px 0; font-family: sans-serif;">
                <div style="font-size: 16px; font-weight: bold; margin-bottom: 12px; color: #00529B;">
                    📝 Business Trip Request Created
                </div>
                <div style="color: #004085; font-size: 14px; line-height: 1.6; margin-bottom: 12px;">
                    A new business trip request has been initiated. Please fill out the form with the required details.
                </div>
            </div>
            """
            # Odoo 18: Wrap HTML in Markup for proper rendering
            new_trip._post_message_with_record_link(body=Markup(message_body))
            trips_to_return |= new_trip

        return trips_to_return

    @api.depends('sale_order_id', 'sale_order_id.name', 'selected_project_id', 'selected_project_id.name')
    def _compute_display_quotation_ref(self):
        for record in self:
            if record.sale_order_id:
                record.display_quotation_ref = record.sale_order_id.name
            elif record.selected_project_id:
                record.display_quotation_ref = f"SA-{record.selected_project_id.name}"
            else:
                record.display_quotation_ref = False

    @api.depends('user_id', 'sale_order_id')
    def _compute_approving_colleague_name(self):
        """Auto-populate approving colleague name with Travel Approver, but allow editing"""
        for trip in self:
            # Skip if already manually set (don't override user's custom value)
            if trip.approving_colleague_name:
                continue
            
            # Determine Travel Approver based on trip type
            travel_approver_id = None
            if trip.sale_order_id:
                # Sale Order related trip
                travel_approver_id = self.env['res.users'].sudo().get_travel_approver_for_sale_order(trip.user_id.id)
            else:
                # Standalone trip
                travel_approver_id = self.env['res.users'].sudo().get_travel_approver_for_standalone(trip.user_id.id)
            
            if travel_approver_id:
                travel_approver = self.env['res.users'].sudo().browse(travel_approver_id)
                trip.approving_colleague_name = travel_approver.name
            else:
                trip.approving_colleague_name = ""

    def _collapse_trip_name_value(self, value):
        return re.sub(r'\s+', ' ', (value or '')).strip()

    def _shorten_trip_name_value(self, value, max_length, fallback=''):
        value = self._collapse_trip_name_value(value)
        if not value:
            return fallback
        if len(value) <= max_length:
            return value
        if max_length <= 3:
            return value[:max_length]
        return f"{value[:max_length - 3].rstrip()}..."

    def _get_trip_name_initials(self):
        self.ensure_one()
        employee_name = self._collapse_trip_name_value(self.user_id.name)
        if not employee_name:
            return 'GEN'

        parts = [part for part in re.split(r'[\s/-]+', employee_name) if part]
        if len(parts) >= 2:
            return ''.join(part[0].upper() for part in parts[:3])[:4]
        return self._shorten_trip_name_value(parts[0].upper(), max_length=4, fallback='GEN')

    def _get_trip_name_reference_token(self, value, max_length=16, prefer_initials=False):
        value = self._collapse_trip_name_value(value).replace('|', '/')
        if not value:
            return ''

        if prefer_initials and len(value) > max_length:
            parts = [part for part in re.split(r'[\s/_-]+', value) if part]
            if len(parts) >= 2:
                initials = ''.join(part[0].upper() for part in parts[:3])
                if len(initials) >= 2:
                    return initials[:max_length]

        return self._shorten_trip_name_value(value, max_length=max_length)

    def _get_trip_name_source_token(self):
        self.ensure_one()
        if self.sale_order_id:
            sale_order_ref = self._get_trip_name_reference_token(
                self.sale_order_id.name,
                max_length=18,
            ) or 'SO'
            return f"SO-{sale_order_ref}"

        standalone_context = (
            self.selected_project_id.name
            or self.business_trip_project_id.name
            or self.selected_project_task_id.name
            or self.business_trip_task_id.name
        )
        if standalone_context:
            standalone_ref = self._get_trip_name_reference_token(
                standalone_context,
                max_length=14,
                prefer_initials=True,
            )
        else:
            standalone_ref = self._get_trip_name_initials()
        return f"SA-{standalone_ref or 'GEN'}"

    def _get_trip_name_descriptor_token(self):
        self.ensure_one()
        candidate = self.destination or self.purpose
        if not candidate and self.sale_order_id:
            candidate = self.sale_order_id.partner_id.name or self.sale_order_id.client_order_ref
        if not candidate:
            candidate = self.user_id.name or 'Business Trip'
        return self._shorten_trip_name_value(
            self._collapse_trip_name_value(candidate).replace('|', '/'),
            max_length=24,
            fallback='Business Trip',
        )

    def _get_trip_name_date_token(self):
        self.ensure_one()
        trip_date = self.travel_start_date or self.travel_end_date
        if not trip_date:
            return 'NoDate'
        return f"{trip_date.day:02d}{MONTH_ABBREVIATIONS[trip_date.month]}{str(trip_date.year)[-2:]}"

    def _get_trip_name_unique_suffix(self):
        self.ensure_one()
        if isinstance(self.id, int):
            return f"BT{self.id}"
        return False

    def _build_generated_trip_name(self):
        self.ensure_one()
        name_parts = [
            self._get_trip_name_source_token(),
            self._get_trip_name_descriptor_token(),
            self._get_trip_name_date_token(),
        ]
        unique_suffix = self._get_trip_name_unique_suffix()
        if unique_suffix:
            name_parts.append(unique_suffix)
        return ' | '.join(part for part in name_parts if part)

    def _should_refresh_generated_trip_name(self):
        self.ensure_one()
        if self.env.context.get('force_name_refresh'):
            return True
        return self.trip_status in ('draft', 'returned') or not self._origin.id

    @api.depends(
        'trip_status',
        'sale_order_id',
        'sale_order_id.name',
        'sale_order_id.partner_id',
        'sale_order_id.partner_id.name',
        'sale_order_id.client_order_ref',
        'selected_project_id',
        'selected_project_id.name',
        'selected_project_task_id',
        'selected_project_task_id.name',
        'business_trip_project_id',
        'business_trip_project_id.name',
        'business_trip_task_id',
        'business_trip_task_id.name',
        'destination',
        'purpose',
        'travel_start_date',
        'travel_end_date',
        'user_id',
        'user_id.name',
    )
    def _compute_name(self):
        for trip in self:
            generated_name = trip._build_generated_trip_name()
            current_name = trip._origin.name if trip._origin and trip._origin.id else False
            if trip._should_refresh_generated_trip_name() or not current_name:
                trip.name = generated_name
            else:
                trip.name = current_name

    @api.model
    def _refresh_generated_trip_names_on_upgrade(self):
        field = self._fields['name']
        batched_model = self.with_context(force_name_refresh=True)
        last_id = 0
        total = 0
        batch_size = 500

        while True:
            batch = batched_model.search([('id', '>', last_id)], order='id', limit=batch_size)
            if not batch:
                break

            batched_model.env.add_to_compute(field, batch)
            batch.flush_recordset(['name'])

            total += len(batch)
            last_id = batch[-1].id

        _logger.info("Refreshed smart business trip names for %s records.", total)
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _compute_has_trip_details(self):
        """
        Checks if the essential details from the form have been filled in
        on the linked business_trip_data record.
        """
        for trip in self:
            trip_data = trip.business_trip_data_id
            if not trip_data:
                trip.has_trip_details = False
                continue
            
            # Check for essential fields.
            # Purpose is computed, so it will always have a value.
            if (trip_data.destination and
                trip_data.purpose and
                trip_data.travel_start_date and
                trip_data.travel_end_date):
                trip.has_trip_details = True
            else:
                trip.has_trip_details = False

    @api.depends('business_trip_data_id.travel_start_date', 'business_trip_data_id.travel_end_date')
    def _compute_travel_dates_display(self):
        for trip in self:
            start_date = trip.business_trip_data_id.travel_start_date
            end_date = trip.business_trip_data_id.travel_end_date
            if start_date and end_date:
                start_str = start_date.strftime('%d/%m/%Y')
                end_str = end_date.strftime('%d/%m/%Y')
                trip.travel_dates_display = f"{start_str} - {end_str}"
            elif start_date:
                trip.travel_dates_display = start_date.strftime('%d/%m/%Y')
            else:
                trip.travel_dates_display = "Not Set"

    @api.depends('business_trip_data_id.travel_start_date', 'business_trip_data_id.travel_end_date')
    def _compute_travel_duration_days(self):
        for trip in self:
            start_date = trip.business_trip_data_id.travel_start_date
            end_date = trip.business_trip_data_id.travel_end_date
            if start_date and end_date and end_date >= start_date:
                trip.travel_duration_days = (end_date - start_date).days + 1
            else:
                trip.travel_duration_days = 0

    @api.depends('actual_start_date', 'actual_end_date')
    def _compute_actual_dates_display(self):
        for trip in self:
            # Get user's timezone from their preferences, default to UTC if not set
            try:
                user_tz_str = trip.env.user.tz or 'UTC'
                user_tz = pytz.timezone(user_tz_str)
            except pytz.UnknownTimeZoneError:
                _logger.warning(f"User {trip.env.user.name} has an unknown timezone '{trip.env.user.tz}'. Defaulting to UTC.")
                user_tz = pytz.utc

            # Format start date
            if trip.actual_start_date:
                utc_dt = pytz.utc.localize(trip.actual_start_date)
                user_dt = utc_dt.astimezone(user_tz)
                trip.actual_start_date_display = user_dt.strftime('%d/%m/%Y %H:%M:%S')
            else:
                trip.actual_start_date_display = ""

            # Format end date
            if trip.actual_end_date:
                utc_dt = pytz.utc.localize(trip.actual_end_date)
                user_dt = utc_dt.astimezone(user_tz)
                trip.actual_end_date_display = user_dt.strftime('%d/%m/%Y %H:%M:%S')
            else:
                trip.actual_end_date_display = ""

            # Calculate and format human-readable duration
            if trip.actual_start_date and trip.actual_end_date and trip.actual_end_date > trip.actual_start_date:
                delta = trip.actual_end_date - trip.actual_start_date
                days, seconds = delta.days, delta.seconds
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                parts = [f"{days} day{'s' if days != 1 else ''}" if days > 0 else None,
                         f"{hours} hour{'s' if hours != 1 else ''}" if hours > 0 else None,
                         f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes > 0 else None]
                trip.actual_duration_display = ", ".join(p for p in parts if p) or "0 minutes"
            else:
                trip.actual_duration_display = "Not yet calculated"
                
    def action_save_and_complete_form(self):
        """
        Save the form and mark it as completed. 
        Returns to the main trip management view.
        """
        self.ensure_one()

        # --- Server-Side Form Validation ---
        required_fields = []
        if not self.travel_start_date:
            required_fields.append('Proposed Start Date')
        if not self.travel_end_date:
            required_fields.append('Proposed End Date')
        if not self.approving_colleague_name:
            required_fields.append('Name of Approving Colleague')
        if not self.trip_duration_type:
            required_fields.append('Trip Duration Type')
        if not self.destination_place_id and not self.destination:
            required_fields.append('Destination')
        if not self.purpose:
            required_fields.append('Purpose of Trip')

        if self.accommodation_needed == 'yes':
            if not self.accommodation_number_of_people:
                required_fields.append('Number of People (Accommodation)')
            if not self.accommodation_residence_city:
                required_fields.append('City (Accommodation)')
            if not self.accommodation_check_in_date:
                required_fields.append('Check-in Date (Accommodation)')
            if not self.accommodation_check_out_date:
                required_fields.append('Check-out Date (Accommodation)')
        
        if self.use_rental_car and self.rental_car_type == 'self' and not self.rental_car_drivers_license:
            required_fields.append("Driver's License (Departure)")

        if required_fields:
            raise UserError(_(
                "Please fill in all required fields before completing the form:\n- %s"
            ) % ("\n- ".join(required_fields)))
        
        # Ensure business_trip_data_id has the requester's name
        if self.business_trip_data_id and self.user_id:
            # Split user's name into first and last name for business_trip_data
            user_name = self.user_id.partner_id.name or self.user_id.name or ''
            name_parts = user_name.strip().split()
            
            # Update first_name and last_name in business_trip_data
            if len(name_parts) == 1:
                # Only one name provided
                self.business_trip_data_id.write({
                    'first_name': name_parts[0],
                    'last_name': '',
                })
            elif len(name_parts) >= 2:
                # Multiple names: first is first_name, rest is last_name
                self.business_trip_data_id.write({
                    'first_name': name_parts[0],
                    'last_name': ' '.join(name_parts[1:]),
                })
            else:
                # Empty name (edge case)
                self.business_trip_data_id.write({
                    'first_name': 'N/A',
                    'last_name': '',
                })
        
        # Mark form as completed
        self.form_completion_status = 'form_completed'
        
        # Post a styled submission summary message to chatter
        # This uses the same templates as the old formio submission
        try:
            # Odoo 18: Use ir.qweb._render() instead of view._render()
            summary_body_html = self.env['ir.qweb']._render('custom_business_trip_management.form_submission_summary', {
                'record': self.business_trip_data_id,
            })

            message_body = self.env['ir.qweb']._render('custom_business_trip_management.chatter_message_card', {
                'card_type': 'success',
                'icon': '📄',
                'title': 'Form Submission Summary',
                'body_html': summary_body_html,
                'submitted_by': self.env.user.name,
            })
            
            # Odoo 18: Convert rendered HTML to Markup for proper rendering
            message_body_markup = Markup(message_body.decode('utf-8') if isinstance(message_body, bytes) else message_body)
            self._post_message_with_record_link(body=message_body_markup, subtype_xmlid="mail.mt_note")
            _logger.info(f"Successfully posted styled summary message to chatter for trip {self.id} after Save & Done.")
        except Exception as e:
            _logger.error(f"Failed to render or post summary message for trip {self.id}: {e}", exc_info=True)
            # Fallback to simple message if template rendering fails
            self._post_message_with_record_link(
                body=_('Form has been completed by %s.') % self.env.user.name,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
        
        # Return to the management form by going back in history
        # This prevents adding a new layer to the breadcrumb stack
        # When user clicks "Open Form" → a new state is pushed to history
        # When user clicks "Save & Done" → we pop that state instead of pushing another one
        # Result: Clean breadcrumb without duplication (Menu / Record instead of Menu / Record / Record)
        return {
            'type': 'ir.actions.client',
            'tag': 'history_back_action',
        }
    
    def action_submit_to_manager(self):
        """Submit a completed trip request form to a Travel Approver for approval."""
        self.ensure_one()

        if self.user_id.id != self.env.user.id:
            raise UserError("Only the owner of this form can submit it.")

        if self.trip_status not in ['draft', 'returned']:
            raise UserError(f"Only forms in 'Draft' or 'Returned' status can be submitted. Current status: {self.trip_status}")

        # Standalone trips must be linked to a project/task before submission.
        # Do not open a wizard automatically for employees; show a clear message instead.
        # Employees can explicitly link/relink the project using the "Relink Project" button
        # available in the "My Business Trip" form when in Draft/Returned state.
        if not self.sale_order_id:
            has_project = bool(self.selected_project_id or self.business_trip_project_id)
            has_task = bool(self.selected_project_task_id or self.business_trip_task_id)
            if not (has_project and has_task):
                raise UserError(
                    "A project is required for standalone business trip requests.\n\n"
                    "Please click 'Relink Project' on this form, select the project, "
                    "and then submit the request for approval again."
                )

        if not self.has_trip_details:
            # In a real scenario, you'd return a warning action.
            raise UserError("Please fill in all required trip details (Destination, Purpose, Dates) before submitting.")

        # Validate dates
        if self.business_trip_data_id.travel_start_date > self.business_trip_data_id.travel_end_date:
            raise UserError("End date cannot be before start date.")

        # Find the employee's Travel Approver if not already set
        if not self.manager_id:
            user_model = self.env['res.users'].sudo().with_company(self.company_id)
            # Determine Travel Approver based on trip type
            if self.sale_order_id:
                # Sale Order related trip
                manager_id = user_model.get_travel_approver_for_sale_order(self.user_id.id)
            else:
                # Standalone trip
                manager_id = user_model.get_travel_approver_for_standalone(self.user_id.id)
            
            if manager_id:
                manager = self.env['res.users'].sudo().browse(manager_id)
            else:
                raise UserError("No Travel Approver is configured. Please contact your administrator.")
        else:
            manager = self.manager_id

        manager.ensure_business_trip_approver_capability()
        reviewer = self.expense_reviewer_id or self._resolve_expense_review_user()
        if reviewer:
            reviewer_group = self.env.ref(
                'custom_business_trip_management.group_business_trip_expense_reviewer',
                raise_if_not_found=False,
            )
            if reviewer_group and reviewer_group not in reviewer.groups_id:
                reviewer.sudo().write({'groups_id': [(4, reviewer_group.id)]})

        # Update the trip
        submit_vals = {
            'trip_status': 'submitted',
            'submission_date': fields.Datetime.now(),
            'manager_id': manager.id,
        }
        if reviewer:
            submit_vals['expense_reviewer_id'] = reviewer.id
        self.with_context(
            authorized_business_trip_assignment=True,
        ).write(submit_vals)

        # Notify the Travel Approver
        if self.manager_id and self.manager_id.partner_id:
            self._post_message_with_record_link(
                body=f"Business trip request submitted by {self.env.user.name} for your review.",
                partner_ids=[self.manager_id.partner_id.id],
                subtype_xmlid="mail.mt_comment",
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_employee_relink_project(self):
        """Employee action: link/relink the project for a standalone trip before submission."""
        self.ensure_one()
        if self.user_id.id != self.env.user.id:
            raise UserError("Only the owner of this trip request can relink the project.")
        if self.sale_order_id:
            raise UserError("This action is only available for standalone trips.")
        if self.trip_status not in ['draft', 'returned']:
            raise UserError("You can only relink the project while the request is in Draft or Returned status.")
        return self.with_context(project_selection_flow='employee').action_open_standalone_project_selection_wizard()

    def action_manager_assign_organizer_and_budget(self):
        self.ensure_one()
        if self.trip_status not in ['submitted']:
            raise UserError("Request must be in 'Submitted to Travel Approver' state.")

        # Prevent trip owners from managing their own trip
        self._check_not_trip_owner_for_management_action("Assign Organizer & Budget")

        if not (self.env.user.id == self.manager_id.id or 
                self.env.user.has_group('base.group_system') or 
                self.env.user.has_group('custom_business_trip_management.group_business_trip_manager')):
            raise UserError("Only the assigned Travel Approver or an administrator can perform this action.")

        # Standalone trips must be linked to a project before management actions can proceed.
        # Use the existing project selection wizard to link the trip safely.
        # Note: "Return to Emp." and "Reject" actions are already available on the form header.
        if not self.sale_order_id:
            has_project = bool(self.selected_project_id or self.business_trip_project_id)
            has_task = bool(self.selected_project_task_id or self.business_trip_task_id)
            if not (has_project and has_task):
                return self.with_context(project_selection_flow='approver').action_open_standalone_project_selection_wizard()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Assign Organizer and Budget',
            'res_model': 'business.trip.assign.organizer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_trip_id': self.id,
                'default_manager_id': self.manager_id.id,
            }
        }

    def action_open_standalone_project_selection_wizard(self):
        """Open the project selection wizard to link a standalone trip to a project."""
        self.ensure_one()
        flow = self.env.context.get('project_selection_flow')
        if not flow:
            flow = 'employee' if self.user_id.id == self.env.user.id else 'approver'
        title = "Relink Project" if flow == 'employee' else "Select Project for Standalone Trip"
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'business.trip.project.selection.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_trip_id': self.id,
                'project_selection_flow': flow,
            }
        }

    def confirm_assignment_and_budget(self, manager_max_budget, organizer_id, manager_comments=None, internal_notes=None):
        """Confirm and assign budget and organizer by Travel Approver"""
        self.ensure_one()

        if not (
            self.env.user == self.manager_id
            or self.env.user.has_group('base.group_system')
            or self.env.user.has_group(
                'custom_business_trip_management.group_business_trip_manager'
            )
        ):
            raise UserError(
                "Only the assigned Travel Approver or a Business Trip "
                "Administrator can assign organizers and budgets."
            )

        if manager_max_budget <= 0:
            raise UserError("Maximum budget must be a positive value.")

        organizer = self.env['res.users'].browse(organizer_id)
        if organizer not in self.company_id.business_trip_organizer_ids:
            raise UserError(
                "Select one of the organizers configured for this trip's "
                "company in Business Trip Settings."
            )

        stakeholder_users = self.user_id | self.manager_id | organizer
        
        # Use existing project from sale order, or selected project for standalone trips
        project = None
        if self.sale_order_id:
            # For order-related trips, check if project with sale order name already exists
            existing_project = self.env['project.project'].search([
                ('name', '=', self.sale_order_id.name),
                ('active', '=', True)
            ], limit=1)
            
            if existing_project:
                project = existing_project
            else:
                # Check if project is linked to sale order
                project = self.sale_order_id.project_ids and self.sale_order_id.project_ids[0] or False
                if not project:
                    # Create new project if none exists
                    project_vals = {
                        'allow_timesheets': True,
                        'user_id': self.manager_id.id,
                        'allocated_hours': 100,
                        'name': self.sale_order_id.name,
                        'partner_id': self.sale_order_id.partner_id.id,
                        'sale_order_id': self.sale_order_id.id,
                    }
                    project = self.env['project.project'].create(project_vals)
        else:
            # For standalone trips, use the pre-selected project
            # Prefer the currently selected project; fall back to an already linked project (if any)
            # to keep the flow robust if the wizard context did not carry the selection.
            project = (
                self.selected_project_id
                or self.business_trip_project_id
                or (self.selected_project_task_id.project_id if self.selected_project_task_id else False)
                or (self.business_trip_task_id.project_id if self.business_trip_task_id else False)
            )
            if not project:
                raise UserError("No project selected for standalone trip. Please contact administrator.")
        
        if not project:
            raise UserError("Could not determine project for business trip.")

        # For standalone trips, use the existing task; for order-related trips, create new task
        if self.sale_order_id:
            # Create new task for order-related trips
            task = self._create_business_trip_task(project, organizer_id)
        else:
            # Use existing task for standalone trips and update it with organizer
            task = self.selected_project_task_id or self.business_trip_task_id
            if task:
                # Add organizer and manager to the existing task
                assignee_ids = [organizer_id, self.user_id.id]
                if self.manager_id:
                    assignee_ids.append(self.manager_id.id)
                task.write({
                    'user_ids': [(6, 0, list(set(assignee_ids)))],
                })
            else:
                raise UserError("No task found for standalone trip. Please contact administrator.")

        vals = {
            'manager_max_budget': manager_max_budget,
            'organizer_id': organizer_id,
            'trip_status': 'pending_organization',
            'manager_approval_date': fields.Datetime.now(),
            'organizer_submission_date': fields.Datetime.now(),
            'business_trip_project_id': project.id,
            'business_trip_task_id': task.id,
        }
        if manager_comments:
            vals['manager_comments'] = manager_comments
        if internal_notes:
            vals['internal_manager_organizer_notes'] = internal_notes

        self.with_context(
            authorized_business_trip_assignment=True,
        ).write(vals)
        
        # Add followers to the trip record
        organizer_user = self.env['res.users'].browse(organizer_id)
        partners_to_follow = self.user_id.partner_id | organizer_user.partner_id
        if self.manager_id:
            partners_to_follow |= self.manager_id.partner_id
        self.message_subscribe(partner_ids=partners_to_follow.ids)

        self._add_stakeholders_as_followers(project, task, organizer_id)
        
        # Send personalized assignment notifications
        currency_symbol = self.currency_id.symbol or ''
        budget_text = f"{manager_max_budget:.2f} {currency_symbol}"
        
        # 1. Message to Organizer (Welcome and Mission)
        organizer_welcome_msg = f"""
<div style="background-color: #d1ecf1; border: 1px solid #bee5eb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #0c5460; font-size: 20px; margin-right: 10px;">🎯</span>
        <span style="font-weight: bold; color: #0c5460; font-size: 16px;">New Trip Organization Assignment</span>
    </div>
    <p style="margin: 5px 0 10px 0;">Congratulations! You have been selected to organize the business trip '<strong>{self.name}</strong>' for <strong>{self.user_id.name}</strong>.</p>
    <div style="background-color: #fff; border: 1px solid #17a2b8; padding: 10px; margin-top: 5px; border-radius: 3px;">
        <p style="margin: 0 0 5px 0; font-weight: bold; color: #0c5460;">Your Mission Details:</p>
        <ul style="margin: 5px 0; padding-left: 20px; color: #333;">
            <li>Employee: <strong>{self.user_id.name}</strong></li>
            <li>Trip Destination: <strong>{self.destination or 'To be determined'}</strong></li>
            <li>Approved Budget: <strong>{budget_text}</strong></li>
            <li>Your Role: Plan and coordinate all travel arrangements</li>
        </ul>
    </div>
    <div style="background-color: #fff; border-left: 4px solid #17a2b8; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Next Steps:</strong> Please begin planning the travel arrangements and submit your detailed plan for the employee's review.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">🚀 Ready to Organize</span>
    </div>
</div>
"""
        if internal_notes:
            organizer_welcome_msg += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px; border-radius: 3px;">
    <p style="margin: 0 0 5px 0; font-weight: bold;">Special Instructions from Travel Approver:</p>
    <p style="margin: 0; color: #333; background-color: #fff; padding: 8px; border-radius: 3px;">{internal_notes}</p>
</div>
"""

        self.sudo().post_confidential_message(
            message=organizer_welcome_msg,
            recipient_ids=[organizer_id]
        )

        # 2. Message to Travel Approver (Assignment Confirmation)
        if self.manager_id:
            manager_assignment_msg = f"""
<div style="background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #155724; font-size: 20px; margin-right: 10px;">✅</span>
        <span style="font-weight: bold; color: #155724; font-size: 16px;">Organizer Successfully Assigned</span>
    </div>
    <p style="margin: 5px 0 10px 0;">You have successfully assigned <strong>{organizer_user.name}</strong> to organize <strong>{self.user_id.name}</strong>'s business trip '<strong>{self.name}</strong>'.</p>
    <div style="background-color: #fff; border: 1px solid #28a745; padding: 10px; margin-top: 5px; border-radius: 3px;">
        <p style="margin: 0 0 5px 0; font-weight: bold; color: #155724;">Assignment Summary:</p>
        <ul style="margin: 5px 0; padding-left: 20px; color: #333;">
            <li>Organizer: <strong>{organizer_user.name}</strong></li>
            <li>Allocated Budget: <strong>{budget_text}</strong></li>
            <li>Employee: <strong>{self.user_id.name}</strong></li>
            <li>Status: Organization in progress</li>
        </ul>
    </div>
    <div style="background-color: #fff; border-left: 4px solid #28a745; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Travel Approver Status:</strong> The organizer will plan the trip and submit it for employee approval. You will be notified of progress.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">🎯 Assignment Complete</span>
    </div>
</div>
"""
            if internal_notes:
                manager_assignment_msg += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px;">
    <p style="margin: 0 0 5px 0; font-weight: bold;">Your Instructions to Organizer:</p>
    <p style="margin: 0; color: #333;">{internal_notes}</p>
</div>
"""

            self.sudo().post_confidential_message(
                message=manager_assignment_msg,
                recipient_ids=[self.manager_id.id]
            )

        # 3. Public message to Employee (Trip Approved & Organizer Assigned)
        employee_approval_msg = f"""
<div style="background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #155724; font-size: 20px; margin-right: 10px;">🎉</span>
        <span style="font-weight: bold; color: #155724; font-size: 16px;">Great News! Your Trip Request is Approved</span>
    </div>
    <p style="margin: 5px 0 10px 0;">Excellent! Your business trip request '<strong>{self.name}</strong>' has been approved by your manager <strong>{self.manager_id.name}</strong>.</p>
    <div style="background-color: #fff; border: 1px solid #28a745; padding: 10px; margin-top: 5px; border-radius: 3px;">
        <p style="margin: 0 0 5px 0; font-weight: bold; color: #155724;">What's Happening Now:</p>
        <ul style="margin: 5px 0; padding-left: 20px; color: #333;">
            <li>✅ Your request has been officially approved</li>
            <li>🎯 <strong>{organizer_user.name}</strong> has been assigned as your travel organizer</li>
            <li>📋 They will plan all your travel arrangements professionally</li>
            <li>📧 You'll receive the complete travel plan for your review soon</li>
        </ul>
    </div>
    <div style="background-color: #fff; border-left: 4px solid #28a745; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Next Steps:</strong> Relax and let your organizer handle the planning. You'll be notified once your detailed travel itinerary is ready for review.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">🚀 Planning In Progress</span>
    </div>
</div>
"""
        # Odoo 18: Wrap HTML in Markup for proper rendering
        self._post_message_with_record_link(
            body=Markup(employee_approval_msg),
            partner_ids=[self.user_id.partner_id.id]
        )
        
        return True

    def _create_business_trip_task(self, project, organizer_id):
        """Creates the main task for the business trip project."""
        self.ensure_one()
        assignee_ids = [organizer_id, self.user_id.id]
        if self.manager_id:
            assignee_ids.append(self.manager_id.id)
        
        # Create meaningful and trackable task name
        submission_date = self.submission_date.strftime('%Y-%m-%d') if self.submission_date else fields.Date.today().strftime('%Y-%m-%d')
        destination_info = f" to {self.destination}" if self.destination else ""
        
        base_task_name = f'Business Trip Request #{self.id}: {self.user_id.name}{destination_info} ({submission_date})'
        task_name = base_task_name
        
        # Check if task with this name already exists in the project
        counter = 1
        while self.env['project.task'].search([
            ('name', '=', task_name),
            ('project_id', '=', project.id)
        ], limit=1):
            task_name = f'{base_task_name} - Copy #{counter}'
            counter += 1
        
        # Create the task with zero planned hours:
        # - avoids blocking automated flows that only need a tracking task container
        # - stays compatible with custom planned-hours enforcement in `custom_project`
        task = self.env['project.task'].with_context(allow_missing_allocated_hours=True).create({
            'name': task_name,
            'project_id': project.id,
            'user_ids': [(6, 0, list(set(assignee_ids)))],
            'description': f"Business trip task for {self.name}",
        })
        return task

    def _add_stakeholders_as_followers(self, project, task, organizer_id):
        """Adds the employee, manager, and organizer as followers to project and task."""
        self.ensure_one()
        partners = self.user_id.partner_id | self.manager_id.partner_id | self.env['res.users'].browse(organizer_id).partner_id
        if project:
            project.message_subscribe(partner_ids=partners.ids)
        if task:
            task.message_subscribe(partner_ids=partners.ids) 

    def _handover_organizer(self, new_user, reason, changed_by=None):
        """Transfer non-final organizer responsibility as one audited batch.

        The behavior matches the previous per-record implementation (tracked
        organizer change, follower/task/activity synchronization, immutable
        history entries) but every step runs on batched recordsets so a large
        handover stays fast and does not block the Settings save.
        """
        if not new_user:
            raise ValidationError("A replacement organizer is required.")

        organizer_group = self.env.ref(
            'custom_business_trip_management.group_business_trip_organizer',
            raise_if_not_found=False,
        )
        if organizer_group and organizer_group not in new_user.groups_id:
            new_user.sudo().write({'groups_id': [(4, organizer_group.id)]})

        changed_by = changed_by or self.env.user
        trips = self.filtered(
            lambda trip: trip.organizer_id and trip.organizer_id != new_user
        )
        if not trips:
            return True

        invalid_trips = trips.filtered(
            lambda trip: new_user not in trip.company_id.business_trip_organizer_ids
        )
        if invalid_trips:
            raise ValidationError(
                "The replacement must be one of the organizers configured "
                "for the trip company."
            )

        previous_user_by_trip = {trip.id: trip.organizer_id for trip in trips}
        previous_users = self.env['res.users']
        for previous_user in previous_user_by_trip.values():
            previous_users |= previous_user

        # Tracked assignment change for the whole batch in one write.
        super(BusinessTrip, trips.with_context(
            mail_notrack=False,
            system_edit=True,
        )).write({'organizer_id': new_user.id})

        trips.message_subscribe(partner_ids=new_user.partner_id.ids)
        all_tasks = trips.mapped('business_trip_task_id')
        # project.task.message_subscribe() mutates the partner list once per
        # matching project follower, so it crashes on recordsets spanning
        # several projects followed by the same partner. Group per project.
        for project in all_tasks.mapped('project_id'):
            all_tasks.filtered(
                lambda task: task.project_id == project
            ).message_subscribe(partner_ids=new_user.partner_id.ids)
        projectless_tasks = all_tasks.filtered(lambda task: not task.project_id)
        if projectless_tasks:
            projectless_tasks.message_subscribe(
                partner_ids=new_user.partner_id.ids
            )

        history_model = self.env['business.trip.assignment.history'].sudo()
        activity_model = self.env['mail.activity'].sudo()
        history_vals = []
        tasks_gaining_only = all_tasks

        for previous_user in previous_users:
            previous_trips = trips.filtered(
                lambda trip: previous_user_by_trip[trip.id] == previous_user
            )
            non_stakeholder_trips = previous_trips.filtered(
                lambda trip: previous_user not in (
                    trip.user_id | trip.manager_id | trip.expense_reviewer_id
                )
            )
            if non_stakeholder_trips:
                non_stakeholder_trips.message_unsubscribe(
                    partner_ids=previous_user.partner_id.ids
                )

            removable_tasks = non_stakeholder_trips.mapped(
                'business_trip_task_id'
            ).filtered(lambda task: previous_user in task.user_ids)
            if removable_tasks:
                removable_tasks.message_unsubscribe(
                    partner_ids=previous_user.partner_id.ids
                )
                removable_tasks.with_context(mail_notrack=True).write({
                    'user_ids': [(3, previous_user.id), (4, new_user.id)],
                })
                tasks_gaining_only -= removable_tasks

            history_vals.extend(
                {
                    'trip_id': trip.id,
                    'role': 'organizer',
                    'previous_user_id': previous_user.id,
                    'new_user_id': new_user.id,
                    'changed_by_id': changed_by.id,
                    'reason': reason,
                }
                for trip in previous_trips
            )

        if tasks_gaining_only:
            tasks_gaining_only.with_context(mail_notrack=True).write({
                'user_ids': [(4, new_user.id)],
            })

        activities = activity_model.search([
            ('res_model', '=', 'business.trip'),
            ('res_id', 'in', trips.ids),
            ('user_id', 'in', previous_users.ids),
        ])
        if activities:
            activities.with_context(mail_activity_quick_update=True).write({
                'user_id': new_user.id,
            })

        if history_vals:
            history_model.create(history_vals)

        return True

    def action_organizer_confirm_planning(self):
        """Organizer confirms planning is complete and notifies the employee."""
        self.ensure_one()
        if self.trip_status not in ['pending_organization']:
            raise UserError("Planning can only be confirmed when trip is 'Pending Organization'.")
        
        # Prevent trip owners from managing their own trip organization
        self._check_not_trip_owner_for_management_action("Confirm Planning")
        
        if self.env.user.id != self.organizer_id.id and not self.env.user.has_group('base.group_system'):
            raise UserError("Only the assigned trip organizer or an administrator can confirm the planning.")

        if not self.organizer_trip_plan_details and not self.structured_plan_items_json:
            raise UserError("Please provide trip plan details before confirming.")

        if self.organizer_planned_cost <= 0:
            raise UserError("Please set a planned cost greater than zero before confirming.")

        confirmation_dt = fields.Datetime.now()

        self.write({
            'trip_status': 'organization_done',
            'organizer_submission_date': confirmation_dt,
            'organizer_confirmation_date': confirmation_dt,
            'organizer_confirmed_by': self.env.user.id,
            'plan_approval_date': confirmation_dt,
            'organization_done_date': confirmation_dt,
        })

        # --- MESSAGE POSTING ---

        # 1. Post a public message for the employee
        employee_message = f"""
<div style="background-color: #d1ecf1; border: 1px solid #bee5eb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #0c5460; font-size: 20px; margin-right: 10px;">🌟</span>
        <span style="font-weight: bold; color: #0c5460; font-size: 16px;">Your Trip Plan is Ready!</span>
    </div>
    <p style="margin: 5px 0 10px 0;">The travel organizer has finalized the plan for your trip to <strong>{self.destination}</strong>.</p>
    <div style="background-color: #fff; border: 1px solid #17a2b8; padding: 10px; margin-top: 5px; border-radius: 3px;">
        <p style="margin: 0 0 5px 0; font-weight: bold; color: #0c5460;">What to Do Now:</p>
        <ul style="margin: 5px 0; padding-left: 20px; color: #333;">
            <li>✅ Please review your detailed travel itinerary.</li>
            <li>✈️ We wish you a safe and productive trip!</li>
            <li>🧾 Remember to submit your expenses upon your return.</li>
        </ul>
    </div>
    <div style="background-color: #fff; border-left: 4px solid #17a2b8; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Next Steps:</strong> You can now proceed with your travel. After the trip, please use the system to submit all your expenses.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">Organized by: {self.organizer_id.name}</span>
    </div>
</div>
"""
        # Odoo 18: Wrap HTML in Markup for proper rendering
        self._post_message_with_record_link(
            body=Markup(employee_message),
            partner_ids=[self.user_id.partner_id.id]
        )

        # 2. Post an internal, confidential message for the manager and organizer
        confidential_message = f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px; border-radius: 3px;">
    <p style="margin: 0 0 5px 0; font-weight: bold; color: #343a40;">Organizer's Action Complete: Plan Finalized</p>
    <div style="border-top: 1px solid #dee2e6; padding-top: 8px; margin-top: 8px;">
        <p style="margin: 0; color: #495057;">
            The travel plan for <strong>{self.name}</strong> (Employee: {self.user_id.name}) 
            has been finalized and confirmed by the organizer, <strong>{self.organizer_id.name}</strong>.
        </p>
        <p style="margin-top: 5px; color: #495057;">
            The trip status has been updated to 'Organization Completed'. Expense follow-up will start only after the trip end date.
        </p>
    </div>
</div>
"""
        # Collect recipients for the confidential message
        recipient_users = self.manager_id | self.organizer_id
        
        self.sudo().post_confidential_message(
            message=confidential_message,
            recipient_ids=recipient_users.ids
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """
        Standard Odoo method to dynamically modify the view architecture from the server-side.
        This is the most robust way to make a form conditionally readonly.
        """
        res = super(BusinessTrip, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu
        )

        # We only apply this logic to our specific custom form view
        view_ref_id = self.env.ref('custom_business_trip_management.view_business_trip_form_page').id
        
        if view_type == 'form' and res.get('view_id') == view_ref_id:
            doc = etree.XML(res['arch'])
            form_node = doc.xpath("//form")[0]
            
            # Determine which record we're dealing with
            active_id = self.env.context.get('active_id') or (self.id if self else None)
            
            if not active_id:
                # For new records, form should be editable by default
                form_node.set('edit', 'true')
            else:
                # For existing records, check form completion status
                trip = self.browse(active_id)
                if trip.exists() and trip.form_completion_status == 'awaiting_completion':
                    form_node.set('edit', 'true')
                elif trip.exists() and trip.form_completion_status in ['form_completed', 'cancelled']:
                    form_node.set('edit', 'false')
                else:
                    # Default to editable if status is unclear
                    form_node.set('edit', 'true')

            res['arch'] = etree.tostring(doc, encoding='unicode')
        
        return res

    def action_edit_trip_details(self):
        """
        Action to open the main business trip form for editing details.
        It resets the form status to 'awaiting_completion' and opens the form in edit mode.
        """
        self.ensure_one()
        
        # Reset the status to allow editing
        if self.form_completion_status == 'form_completed':
            self.form_completion_status = 'awaiting_completion'
        
        # Return an action to open the form view directly in edit mode
        return {
            'name': _('Business Trip Request Form'),
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('custom_business_trip_management.view_business_trip_form_page').id,
            'target': 'current',
            'flags': {'mode': 'edit'},
        }

    def action_back_to_draft(self):
        """Return a submitted form back to draft status and reset form completion status"""
        self.ensure_one()

        # Only the owner can return to draft and only if it's in submitted or returned status
        if self.user_id.id != self.env.user.id:
            raise ValidationError("Only the owner of this trip request can return it to draft status.")

        # Allow return to draft for submitted forms (and those already in draft or returned status)
        if self.trip_status not in ['submitted', 'returned', 'draft']:
            raise ValidationError("Only submitted forms, returned forms, or completed forms still in draft status can be returned to draft editing state.")

        # Check if the request has already been processed by a manager if trip_status is 'submitted'
        if self.trip_status == 'submitted' and \
           (self.manager_approval_date or self.organizer_submission_date or self.organizer_id or \
            self.trip_status in ['rejected']):
            raise ValidationError("This request has already been processed or actioned by management and cannot be returned to draft by the user.")

        # Clear related approval/estimation/return fields to make it a clean draft
        # Also reset form_completion_status to allow editing
        self.with_context(
            authorized_business_trip_assignment=True,
        ).write({
            'trip_status': 'draft',
            'form_completion_status': 'awaiting_completion',  # Reset to allow editing
            'submission_date': False,
            'manager_id': False,
            'manager_approval_date': False,
            'manager_comments': False,
            'expense_return_comments': False,
            'rejection_reason': False,
            'rejection_comment': False,
            'rejected_by': False,
            'rejection_date': False,
        })

        # Post a message to the chatter
        self._post_message_with_record_link(body="Request returned to draft by the user. Form is now editable again.")

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_open_return_comment_wizard(self):
        """Open wizard for returning the trip request with comments."""
        self.ensure_one()

        if self.trip_status not in ['submitted']:
            raise ValidationError("You can only return requests that are in 'Submitted to Travel Approver' state using this wizard.")

        if not (self.env.user.has_group('base.group_system') or 
                (self.manager_id and self.env.user.id == self.manager_id.id) or
                self.env.user.has_group('custom_business_trip_management.group_business_trip_manager')):
            raise ValidationError("Only the assigned manager or system administrators can return the request with comments.")

        ctx = {
            'active_id': self.id,
            'default_trip_id': self.id,  # Changed from default_form_id to default_trip_id
        }

        # If this is a standalone trip missing a linked project/task, prefill a clear instruction.
        if not self.sale_order_id:
            has_project = bool(self.selected_project_id or self.business_trip_project_id)
            has_task = bool(self.selected_project_task_id or self.business_trip_task_id)
            if not (has_project and has_task):
                ctx['default_return_comments'] = (
                    "Your request is missing a linked project for a standalone trip. "
                    "Please create a new standalone trip request and make sure to select the project, "
                    "then submit it again for approval."
                )

        return {
            'name': 'Return with Comments',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.return.comment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def action_open_expense_return_comment_wizard(self):
        """Open wizard for returning submitted expenses with comments."""
        self.ensure_one()

        if self.trip_status != 'expense_submitted':
            raise ValidationError("You can only return expenses that have been submitted for review.")

        # Prevent trip owners from returning their own expenses
        self._check_not_trip_owner_for_management_action("Return Expenses")

        if not self._can_current_user_review_expenses():
            raise ValidationError(
                f"Only the {self._get_expense_review_role_label()} or system administrators can return expenses."
            )

        return {
            'name': 'Return Travel Expenses with Comments',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.expense.return.comment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_trip_id': self.id,  # Changed from default_form_id to default_trip_id
            }
        }
    
    # ===== COMPUTE METHODS MIGRATED FROM FORMIO_FORM_INHERIT =====
    
    @api.depends('trip_status')
    def _compute_trip_status_phases(self):
        """
        Calculate phase-based statuses based on trip_status
        This method must ensure that all statuses, including exception statuses,
        are properly displayed in their respective phases.
        """
        _logger.info("Computing trip status phases")
        for rec in self:
            # Log information
            trip_status = rec.trip_status
            _logger.info(f"Business Trip ID: {rec.id}, Current trip_status: {trip_status}")

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
                if trip_status in ['completed_waiting_expense', 'expense_submitted', 'expense_returned', 'completed']:
                    rec.trip_status_phase1 = 'organization_done'
                    _logger.info(f"Setting trip_status_phase1 to organization_done while in phase two status: {trip_status}")
                else:
                    rec.trip_status_phase1 = False
                    _logger.info(f"Setting trip_status_phase1 to False for status: {trip_status}")
                    
            # Phase two - normal stages
            if trip_status in ['completed_waiting_expense', 'expense_submitted', 'completed']:
                rec.trip_status_phase2 = trip_status
                _logger.info(f"Setting trip_status_phase2 to {trip_status}")
            elif trip_status == 'expense_returned':
                # Only show expense_returned when it's the actual current status
                rec.trip_status_phase2 = 'expense_returned'
                _logger.info(f"Setting trip_status_phase2 to expense_returned for expense_returned status")
            elif trip_status == 'organization_done':
                # When organization is complete, show phase 2 with completed_waiting_expense as the initial status
                rec.trip_status_phase2 = 'completed_waiting_expense'
                _logger.info(f"Setting trip_status_phase2 to completed_waiting_expense for organization_done status")
            else:
                rec.trip_status_phase2 = False
                _logger.info(f"Setting trip_status_phase2 to False for status: {trip_status}")

            # Additional debug information
            _logger.info(f"Final phase status - Phase1: {rec.trip_status_phase1}, Phase2: {rec.trip_status_phase2}")

    @api.depends('trip_status')
    def _compute_exceptional_statuses(self):
        """Calculate exception statuses for display in the status bar"""
        for rec in self:
            trip_status = rec.trip_status
            # Phase one
            rec.is_returned = (trip_status == 'returned')
            rec.is_rejected = (trip_status == 'rejected')

            # Phase two
            rec.is_expense_returned = (trip_status == 'expense_returned')

            # Add log for debugging
            if trip_status == 'expense_returned':
                _logger.info(f"Computing exceptional statuses for trip {rec.id}: trip_status = {trip_status}, is_expense_returned set to True")

    @api.depends_context('uid')
    def _compute_my_role(self):
        """Compute the current user's role for this business trip"""
        current_user_id = self.env.user.id

        for record in self:
            roles = []

            # Check each possible role
            if record.user_id and record.user_id.id == current_user_id:
                roles.append('Employee')

            if record.manager_id and record.manager_id.id == current_user_id:
                roles.append('Travel Approver')

            if record.organizer_id and record.organizer_id.id == current_user_id:
                roles.append('Organizer')

            if not roles and self.env.user.has_group('base.group_system'):
                roles.append('Admin')

            # Join multiple roles with a slash
            record.my_role = ' / '.join(roles) if roles else '-'

    @api.depends('structured_plan_items_json')
    def _compute_organizer_plan_html(self):
        for record in self:
            if not record.structured_plan_items_json:
                record.organizer_plan_html = '<div class="alert alert-info" role="alert">No structured plan details available.</div>'
                continue

            try:
                plan_items = json.loads(record.structured_plan_items_json)
                if not isinstance(plan_items, list):
                    raise ValueError("JSON data is not a list of items.")
            except (json.JSONDecodeError, ValueError) as e:
                _logger.error(f"Could not parse structured_plan_items_json for trip {record.id}: {e}")
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

    @api.depends('structured_plan_items_json')
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

            plan_items_str = record.structured_plan_items_json
            if not plan_items_str or plan_items_str == '[]':
                continue

            try:
                plan_items = json.loads(plan_items_str)
                if not isinstance(plan_items, list):
                    _logger.warning(f"structured_plan_items_json is not a list for trip {record.id}")
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
                _logger.warning(f"Could not parse structured_plan_items_json for trip {record.id}")
                continue

    def _render_plan_item_field(self, label, value):
        """Helper to render a single key-value pair for the plan item HTML."""
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
        
        html += '</div>'
        return Markup(html)



    def _render_item_detail(self, label, value):
        """Helper to render a single detail item."""
        if not value:
            return ''
        return f'<div><strong>{label}:</strong> {value}</div>'

    def _should_show_cost_info(self):
        """Check if current user should see cost information"""
        user = self.env.user
        if user.has_group('base.group_system'):
            return True
        if self.organizer_id and user.id == self.organizer_id.id:
            return True
        if self.manager_id and user.id == self.manager_id.id:
            return True
        if user.has_group('custom_business_trip_management.group_business_trip_organizer'):
            return True
        return False 

    def action_open_return_comment_wizard(self):
        """Open wizard for returning the trip request with comments."""
        self.ensure_one()

        if self.trip_status not in ['submitted']:
            raise ValidationError("You can only return requests that are in 'Submitted to Travel Approver' state using this wizard.")

        if not (self.env.user.has_group('base.group_system') or 
                (self.manager_id and self.env.user.id == self.manager_id.id) or
                self.env.user.has_group('custom_business_trip_management.group_business_trip_manager')):
            raise ValidationError("Only the assigned manager or system administrators can return the request with comments.")

        return {
            'name': 'Return with Comments',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.return.comment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_trip_id': self.id,  # Changed from default_form_id to default_trip_id
            }
        }

    def action_open_expense_return_comment_wizard(self):
        """Open wizard for returning submitted expenses with comments."""
        self.ensure_one()

        if self.trip_status != 'expense_submitted':
            raise ValidationError("You can only return expenses that have been submitted for review.")

        # Prevent trip owners from returning their own expenses
        self._check_not_trip_owner_for_management_action("Return Expenses")

        if not self._can_current_user_review_expenses():
            raise ValidationError(
                f"Only the {self._get_expense_review_role_label()} or system administrators can return expenses."
            )

        return {
            'name': 'Return Travel Expenses with Comments',
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.expense.return.comment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_trip_id': self.id,  # Changed from default_form_id to default_trip_id
            }
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
        if self.expense_approval_date or self.expense_approved_by or self.trip_status in ['expense_returned', 'completed']:
            raise ValidationError("Expenses have already been processed by management and cannot be recalled.")

        # Store expense value before status change
        current_expense = self.expense_total
        currency_symbol = self.currency_id.symbol if self.currency_id else ''

        # Change status to waiting for expense submission
        self.write({
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
        # Odoo 18: Wrap HTML in Markup for proper rendering
        self._post_message_with_record_link(
            body=Markup(styled_message),
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
        if not (self.env.user.has_group('base.group_system') or 
                (self.manager_id and self.env.user.id == self.manager_id.id) or
                self.env.user.has_group('custom_business_trip_management.group_business_trip_manager')):
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
    <p style="margin: 5px 0 10px 0;">Your business trip request '<strong>{self.name}</strong>' has been returned for revision.</p>
    <div style="background-color: #fff; border-left: 4px solid #ffc107; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Next steps:</strong> Please check the comments below, make necessary corrections, and resubmit your request.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">Returned by: {self.env.user.name}</span>
    </div>
</div>
"""

            # If manager comments exist, include them in the message
            if self.manager_comments:
                styled_message += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px;">
    <p style="margin: 0 0 5px 0; font-weight: bold;">Comments:</p>
    <p style="margin: 0; color: #333;">{self.manager_comments}</p>
</div>
"""

            # Odoo 18: Wrap HTML in Markup for proper rendering
            self._post_message_with_record_link(
                body=Markup(styled_message),
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
            raise ValidationError("You can only reject requests that are in 'Submitted to Travel Approver' state.")

        # Check user permissions
        if not self.env.user.has_group('base.group_system') and not (self.manager_id and self.env.user.id == self.manager_id.id):
            raise ValidationError("Only the assigned Travel Approver or system administrators can reject the request.")

        # Change status to 'rejected' and record rejection information
        self.write({
            'trip_status': 'rejected',
            'rejected_by': self.env.user.id,
            'rejection_date': fields.Datetime.now()
        })

        # Notify the employee
        if self.user_id.partner_id:
            rejection_reason_display = dict(self._fields['rejection_reason'].selection).get(self.rejection_reason, self.rejection_reason)
            message = f"Your business trip request '{self.name}' has been rejected."
            if rejection_reason_display:
                message += f" Reason: {rejection_reason_display}"
            if self.rejection_comment:
                message += f" Details: {self.rejection_comment}"

            self._post_message_with_record_link(
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
            raise ValidationError("Only authorized personnel (Finance, HR Travel Approver, or System Admin) can undo expense approval.")

        self.write({
            'trip_status': 'expense_submitted',
            'expense_approval_date': False,
            'expense_approved_by': False,
            'final_total_cost': 0.0, # Reset final_total_cost as it's set upon approval
        })

        self._post_message_with_record_link(body="Expense approval has been undone. The expenses are now back in 'Expenses Under Review' state for review.")

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_open_organizer_plan_wizard(self):
        """Open wizard for organizer to edit trip plan details"""
        self.ensure_one()

        if self.trip_status != 'pending_organization':
            raise ValidationError("Trip plan can only be edited when in 'Pending Organization' state.")

        # Prevent trip owners from editing their own trip plan
        self._check_not_trip_owner_for_management_action("Edit Trip Plan")

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
        if self.trip_status not in ['completed_waiting_expense', 'expense_returned', 'in_progress', 'awaiting_trip_start']:
            raise ValidationError("You can only submit expenses when the trip is in 'Awaiting Travel Expenses' or 'Expense Returned' state.")
        if self.user_id.id != self.env.user.id:
            raise ValidationError("Only the employee of this request can submit expenses.")

        # Store previous status to determine if this is an initial submission or a revision
        previous_status = self.trip_status

        # Check if this is a submission with no expenses
        is_no_expenses = self.env.context.get('no_expenses_submission', False)
        expense_reviewer = self._get_expense_review_user()
        expense_reviewer_label = self._get_expense_review_role_label()

        if not is_no_expenses and not expense_reviewer:
            raise ValidationError(
                f"No {expense_reviewer_label} is configured to review submitted travel expenses."
            )

        # Change status based on whether there are expenses or not
        if is_no_expenses:
            # No expenses - go directly to completed
            # Calculate final total cost (planned cost + no expenses = planned cost only)
            total_cost = self.organizer_planned_cost + 0.0  # expense_total is 0 for no expenses
            
            self.with_context(mail_notrack=True, system_edit=True).write({
                'trip_status': 'completed',
                'actual_expense_submission_date': fields.Datetime.now(),
                'expense_approval_date': fields.Datetime.now(),
                'expense_approved_by': self.env.user.id,
                'final_total_cost': total_cost,
            })
            
            # Refresh to get computed fields (budget_difference, budget_status) updated (Odoo 18 compatible)
            self.invalidate_recordset(['budget_difference', 'budget_status', 'final_total_cost'])
        else:
            # Has expenses - go to expense_submitted for review
            self.with_context(mail_notrack=True, system_edit=True).write({
                'trip_status': 'expense_submitted',
                'actual_expense_submission_date': fields.Datetime.now(),
            })

        # Create appropriate message based on previous status and expense status
        if is_no_expenses:
            if previous_status == 'completed_waiting_expense':
                # Initial no-expense submission - trip is now completed (no budget info for public message)
                message_body = f"Employee {self.user_id.name} has confirmed that there are no additional expenses for trip '{self.name}'. Trip is now completed."
            else:
                # No-expense revision after return - trip is now completed (no budget info for public message)
                message_body = f"Employee {self.user_id.name} has confirmed again that there are no additional expenses for trip '{self.name}'. Trip is now completed."
        else:
            if previous_status == 'completed_waiting_expense':
                # Initial expense submission
                message_body = f"Employee {self.user_id.name} has submitted travel expenses for trip '{self.name}'."
            else:
                # Expense revision after return
                message_body = f"Employee {self.user_id.name} has resubmitted revised travel expenses for trip '{self.name}'."

            # Add expense amount to the message if expenses were submitted
            message_body += f"<br/>Expense amount: {self.expense_total:.2f} {self.currency_id.symbol if self.currency_id else ''}"

        # Send personalized messages to each stakeholder
        
        # 1. Message to the configured expense reviewer
        if expense_reviewer and expense_reviewer.partner_id:
            if is_no_expenses:
                # Create budget status message for the expense reviewer
                reviewer_budget_info = ""
                if self.budget_difference > 0:
                    reviewer_budget_info = f"<span style='color:green'>✓ Trip completed {abs(self.budget_difference):.2f} {self.currency_id.symbol} under budget!</span>"
                elif self.budget_difference < 0:
                    reviewer_budget_info = f"<span style='color:red'>⚠ Trip exceeded budget by {abs(self.budget_difference):.2f} {self.currency_id.symbol}.</span>"
                else:
                    reviewer_budget_info = "<span style='color:blue'>✓ Trip completed exactly on budget!</span>"
                
                # Personalized message for the expense reviewer - No Expenses - Trip Completed
                reviewer_message = f"""
<div style="background-color: #d1ecf1; border: 1px solid #bee5eb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #0c5460; font-size: 20px; margin-right: 10px;">🎉</span>
        <span style="font-weight: bold; color: #0c5460; font-size: 16px;">Trip Successfully Completed - No Additional Expenses</span>
    </div>
    <p style="margin: 5px 0 10px 0;">The employee <strong>{self.user_id.name}</strong> has confirmed no additional expenses for trip '<strong>{self.name}</strong>'. The trip has been automatically completed.</p>
    <div style="background-color: #fff; border: 1px solid #17a2b8; padding: 10px; margin-top: 5px; border-radius: 3px;">
        <p style="margin: 0 0 5px 0; font-weight: bold; color: #0c5460;">{expense_reviewer_label} Summary:</p>
        <p style="margin: 0; color: #333;">Trip: <strong>{self.name}</strong><br/>
        Final Total Cost: <strong>{self.final_total_cost:.2f} {self.currency_id.symbol if self.currency_id else ''}</strong><br/>
        {reviewer_budget_info}</p>
    </div>
    <div style="background-color: #fff; border-left: 4px solid #17a2b8; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Review Status:</strong> The trip is now fully completed with no additional expenses required.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">🏆 Trip Completed</span>
    </div>
</div>
"""
            else:
                # Personalized message for the expense reviewer - With Expenses
                reviewer_message = f"""
<div style="background-color: #d1ecf1; border: 1px solid #bee5eb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #0c5460; font-size: 20px; margin-right: 10px;">📊</span>
        <span style="font-weight: bold; color: #0c5460; font-size: 16px;">Expense Review Required</span>
    </div>
    <p style="margin: 5px 0 10px 0;">The employee <strong>{self.user_id.name}</strong> has submitted expenses for review for trip '<strong>{self.name}</strong>'.</p>
    <div style="background-color: #fff; border: 1px solid #17a2b8; padding: 10px; margin-top: 5px; border-radius: 3px;">
        <p style="margin: 0 0 5px 0; font-weight: bold; color: #0c5460;">Expense Summary:</p>
        <p style="margin: 0; color: #333;">Employee Additional Expenditures: <strong>{self.expense_total:.2f} {self.currency_id.symbol if self.currency_id else ''}</strong><br/>
        Total Actual Cost: <strong>{self.organizer_planned_cost + self.expense_total:.2f} {self.currency_id.symbol if self.currency_id else ''}</strong></p>
    </div>
    <div style="background-color: #fff; border-left: 4px solid #17a2b8; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>{expense_reviewer_label} Action:</strong> Please review this submission and either approve it or return it for revision.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">⏳ Awaiting Your Review</span>
    </div>
</div>
"""

            if self.expense_comments:
                reviewer_message += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px;">
    <p style="margin: 0 0 5px 0; font-weight: bold;">Employee Comments:</p>
    <p style="margin: 0; color: #333;">{self.expense_comments}</p>
</div>
"""

            # Post confidential message to the expense reviewer
            self.sudo().post_confidential_message(
                message=reviewer_message,
                recipient_ids=[expense_reviewer.id]
            )

        # 2. Confirmation message to Employee (submitter)
        if self.user_id.partner_id:
            if is_no_expenses:
                employee_message = f"""
<div style="background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #155724; font-size: 20px; margin-right: 10px;">🎉</span>
        <span style="font-weight: bold; color: #155724; font-size: 16px;">Trip Successfully Completed!</span>
    </div>
    <p style="margin: 5px 0 10px 0;">Thank you for confirming that you have no additional expenses for trip '<strong>{self.name}</strong>'. Your trip has been automatically completed!</p>
    <div style="background-color: #fff; border-left: 4px solid #28a745; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Status:</strong> Your business trip process is now complete. No further action is required from you or management.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">✅ Completed</span>
    </div>
</div>
"""
            else:
                employee_message = f"""
<div style="background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <span style="color: #155724; font-size: 20px; margin-right: 10px;">📤</span>
        <span style="font-weight: bold; color: #155724; font-size: 16px;">Expense Submission Received</span>
    </div>
    <p style="margin: 5px 0 10px 0;">Your travel expense submission for trip '<strong>{self.name}</strong>' has been successfully received.</p>
    <div style="background-color: #fff; border-left: 4px solid #28a745; padding: 10px; margin-top: 5px;">
        <p style="margin: 0; color: #333;"><strong>Next Steps:</strong> The {expense_reviewer_label} will review your expenses and either approve them or request revisions. You will be notified of the decision.</p>
    </div>
    <div style="margin-top: 15px; text-align: right;">
        <span style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 3px; font-size: 12px;">📋 Under Review</span>
    </div>
</div>
"""

            # Post public confirmation message to Employee
            # Odoo 18: Wrap HTML in Markup for proper rendering
            self._post_message_with_record_link(
                body=Markup(employee_message),
                partner_ids=[self.user_id.partner_id.id]
            )

        if not is_no_expenses:
            review_note = (
                f"{message_body}"
                f"<br/><strong>Review Flow:</strong> The {expense_reviewer_label} will review this submission "
                "and either approve it or return it for revision."
            )
            self._post_message_with_record_link(
                body=Markup(review_note),
                subtype_xmlid='mail.mt_note'
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_show_missing_details_warning(self):
        """Show a warning notification about missing trip details"""
        self.ensure_one()
        missing_fields = []

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
            if not trip_data.travel_end_date:
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

    # Modified by A_zeril_A, 2025-10-20: Commented out formio-related method after formio module removal
    # def action_edit_returned_form(self):
    #     """Open the formio form for editing when it's in returned status by temporarily changing state to DRAFT"""
    #     self.ensure_one()

    #     # Check if the user is the owner of the form
    #     if self.user_id.id != self.env.user.id:
    #         raise ValidationError("Only the owner of this form can edit it.")

    #     # Check that the form is in returned status
    #     if self.trip_status != 'returned':
    #         raise ValidationError("This action is only available for forms in 'Returned to Employee' status.")

    #     # Ensure we have a linked formio form
    #     if not self.formio_form_id:
    #         raise ValidationError("No form linked to this business trip.")

    #     # Temporarily change the state to DRAFT to allow editing
    #     self.formio_form_id.with_context(system_edit=True).write({
    #         'state': 'DRAFT'
    #     })
        
    #     # Mark this business trip as being edited in returned state
    #     self.write({
    #         'edit_in_returned_state': True
    #     })

    #     # Return the action to open the form in edit mode
    #     action = self.formio_form_id.action_view_formio()
    #     action['context'] = dict(self.env.context)
    #     action['context'].update({
    #         'returned_form_edit': True  # Flag to know this is a special edit session
    #     })

    #     return action

    def action_view_business_trip_data(self):
        """View the linked business trip data record in a standard Odoo form."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Business Trip Data',
            'res_model': 'business.trip.data',
            'view_mode': 'form',
            'res_id': self.business_trip_data_id.id,
            'target': 'current',
        }

    # Modified by A_zeril_A, 2025-10-20: Commented out formio-related method after formio module removal
    # Modified by A_zeril_A, 2025-10-24: Re-implemented action_view_formio to open the new custom form view instead of formio form.
    def action_view_formio(self):
        """
        This action opens the custom business trip form page view.
        This replaces the old Form.io form with a standard Odoo form.
        """
        self.ensure_one()
        _logger.info(f"ACTION_VIEW_FORMIO: Called for trip {self.id}, name={self.name}")
        
        try:
            view_ref = self.env.ref('custom_business_trip_management.view_business_trip_form_page')
            _logger.info(f"ACTION_VIEW_FORMIO: Found view ref with id={view_ref.id}")
        except Exception as e:
            _logger.error(f"ACTION_VIEW_FORMIO: Error finding view: {e}")
            raise
        
        context = self.env.context.copy()
        
        # Determine the appropriate name and context based on status
        if self.form_completion_status == 'awaiting_completion':
            action_name = f'Edit - {self.name}'
            context['form_view_initial_mode'] = 'edit'
        else:
            action_name = f'Review - {self.name}'
        
        action = {
            'type': 'ir.actions.act_window',
            'name': action_name,
            'res_model': 'business.trip',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'views': [(view_ref.id, 'form')],
            'context': context,
        }
        _logger.info(f"ACTION_VIEW_FORMIO: Returning action: {action}")
        return action
    
    def action_edit_form(self):
        """
        Open the form in edit mode and change status back to awaiting_completion.
        This allows editing a completed form.
        """
        self.ensure_one()
        
        # Change status back to awaiting_completion to allow editing
        self.form_completion_status = 'awaiting_completion'
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Edit - {self.name}',
            'res_model': 'business.trip',
            'view_mode': 'form',
            'res_id': self.id,
            'view_id': self.env.ref('custom_business_trip_management.view_business_trip_form_page').id,
            'target': 'current',
            'flags': {
                'mode': 'edit',  # Force edit mode
                'hasActionMenus': False,  # Hide default action menus
            },
        }

    def action_view_sale_order(self):
        """
        Open the linked sale order/quotation.
        Smart button action to view the related sales order.
        """
        self.ensure_one()
        
        if not self.sale_order_id:
            raise UserError(_("There is no linked sales order for this business trip."))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Linked Quotation'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
            'target': 'current',
            'context': self.env.context,
        }

    def _get_trip_record_url(self):
        self.ensure_one()
        base_url = self.get_base_url() or self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/web#id={self.id}&model={self._name}&view_type=form"

    @api.model
    def _normalize_message_body_html(self, body):
        if body in (False, None):
            return ""

        body_html = str(body).strip()
        if not body_html:
            return ""

        if re.search(r'<[a-zA-Z/][^>]*>', body_html):
            return body_html

        lines = [line.strip() for line in body_html.splitlines() if line.strip()]
        if not lines:
            return f"<p>{escape(body_html)}</p>"
        return ''.join(f"<p>{escape(line)}</p>" for line in lines)

    def _get_trip_reference_html(self, action_label=None, helper_text=None):
        self.ensure_one()
        return Markup(
            f"""
<div data-business-trip-reference="1" style="margin-top: 14px; padding: 12px 14px; border: 1px solid #B3D4FF; background-color: #EBF5FF; border-radius: 6px;">
    <div style="font-size: 13px; font-weight: 600; color: #00529B; margin-bottom: 6px;">
        Related Business Trip: {escape(self.name or 'Business Trip')}
    </div>
    <div style="font-size: 13px; color: #004085; margin-bottom: 10px;">
        {escape(helper_text or 'Open the related business trip in Odoo for the full context and next actions.')}
    </div>
    <a href="{escape(self._get_trip_record_url())}" style="display: inline-block; background-color: #00529B; color: #FFFFFF !important; text-decoration: none; padding: 8px 14px; border-radius: 4px; font-weight: 600;">
        {escape(action_label or 'Open Business Trip')}
    </a>
</div>
"""
        )

    def _get_trip_anchor_html(self, label=None):
        self.ensure_one()
        return Markup(
            f'<a href="{escape(self._get_trip_record_url())}" '
            f'style="color: #00529B; text-decoration: none; font-weight: 600;">'
            f'{escape(label or self.name or "Open Business Trip")}</a>'
        )

    def _append_record_reference_to_body_html(self, body, action_label=None, helper_text=None):
        self.ensure_one()
        body_html = self._normalize_message_body_html(body)
        if 'data-business-trip-reference="1"' in body_html:
            return Markup(body_html)
        return Markup(f"{body_html}{self._get_trip_reference_html(action_label=action_label, helper_text=helper_text)}")

    def _post_message_with_record_link(self, body, action_label=None, helper_text=None, **kwargs):
        self.ensure_one()
        return self.message_post(
            body=self._append_record_reference_to_body_html(
                body,
                action_label=action_label,
                helper_text=helper_text,
            ),
            **kwargs,
        )

    def post_confidential_message(self, message, recipient_ids=None, attachment_ids=None):
        """Send confidential message in chatter that is only visible to specific recipients"""
        self.ensure_one()

        # Skip permission check if called with sudo() or system context
        if not self.env.su and not self.env.context.get('system_edit', False):
            if not (self.is_manager or self.is_organizer or self.env.user.has_group('base.group_system')):
                raise ValidationError("You don't have permission to send confidential messages.")

        if not recipient_ids:
            # Default: send to manager and organizer
            recipient_ids = []
            if self.manager_id and self.manager_id.id != self.env.user.id:
                recipient_ids.append(self.manager_id.id)
            if self.organizer_id and self.organizer_id.id != self.env.user.id:
                recipient_ids.append(self.organizer_id.id)

        # Only add current user to recipients if they are explicitly specified in recipient_ids
        # or if no specific recipients were provided and they have permission
        if not recipient_ids:
            # No specific recipients - this shouldn't happen with our current usage
            # but keeping for backward compatibility
            current_user_should_receive = (
                (self.manager_id and self.env.user.id == self.manager_id.id) or  # User is manager
                (self.organizer_id and self.env.user.id == self.organizer_id.id) or  # User is organizer
                self.env.user.has_group('base.group_system')  # User is system admin
            )
            if current_user_should_receive:
                recipient_ids.append(self.env.user.id)
        
        # Convert user IDs to partner IDs
        partner_ids = self.env['res.users'].browse(recipient_ids).mapped('partner_id').ids

        # Check for duplicate messages in the last 5 minutes
        recent_messages = self.env['mail.message'].search([
            ('model', '=', self._name),
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
                _logger.info(f"Skipping duplicate confidential message for trip {self.id}")
                return True

        # Add confidential label to message
        formatted_message = f'<div class="confidential-message">' \
                            f'<span style="background-color: #dc3545; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px;">' \
                            f'<i class="fa fa-lock"></i> Confidential</span>' \
                            f'<div style="margin-top: 10px;">{message}</div>' \
                            f'</div>'
        formatted_message_markup = self._append_record_reference_to_body_html(
            formatted_message,
            action_label='Open Confidential Trip Record',
            helper_text='Open the related business trip in Odoo to review the confidential context securely.',
        )

        # Use internal note type (mail.mt_note) which is more restricted
        subtype_id = self.env.ref('mail.mt_note').id

        # Create a private message with explicit partner_ids
        # This message will only be visible to specified partners
        msg = self.with_context(
            mail_create_nosubscribe=True,
            mail_post_autofollow=False
        ).message_post(
            body=formatted_message_markup,
            message_type='comment',
            subtype_id=subtype_id,
            partner_ids=partner_ids,
            attachment_ids=attachment_ids or [],
        )

        # Set message as confidential
        if msg:
            # Odoo 18: Use sudo() to modify protected fields, or only set confidential fields
            # Since model and res_id are already set by message_post, we only need to set confidential fields
            self.env['mail.message'].browse(msg.id).write({
                'confidential': True,
                'confidential_recipients': [(6, 0, partner_ids)],
            })

            # Add log for debugging
            _logger.info(f"Created confidential message ID: {msg.id} with recipients: {partner_ids}")

            # Force clear caches to ensure proper filtering (Odoo 18 compatible)
            self.env['mail.message'].invalidate_model()
            self.env['mail.notification'].invalidate_model()

        return True

    def action_return_to_employee_with_comment(self):
        """Open wizard for returning to employee with comments"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Return to Employee',
            'res_model': 'business.trip.return.comment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_trip_id': self.id,  # Changed from default_form_id
                'default_action_type': 'return_to_employee',
            }
        }
        
    def get_planned_trip_details_as_string(self):
        """Helper method to get planned trip details as a string"""
        self.ensure_one()
        details = []
        if self.organizer_trip_plan_details:
            details.append(self.organizer_trip_plan_details)
        if self.organizer_planned_cost:
            currency = self.currency_id.symbol if self.currency_id else ''
            details.append(f"Planned Cost: {self.organizer_planned_cost} {currency}")
        return "\n".join(details) if details else "No plan details available."
        
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
            card_type='warning',
            icon='🔒',
            title='Confidential: Trip Plan Updated (Pending Confirmation)',
            template_xml_id='custom_business_trip_management.organizer_plan_confidential_summary',
            is_internal_note=True,
            render_context={
                'record': self,
                'plan_details': plan_details_str
            }
        )

        # Post public message for the employee
        self._post_styled_message(
            card_type='info',
            icon='⏳',
            title='Trip Plan Updated',
            template_xml_id='custom_business_trip_management.organizer_plan_public_summary',
            is_internal_note=False,
            render_context={
                'record': self
            }
        )

        return True

    def action_reprocess_data(self):
        """
        Server action to re-process the submission data for the selected trip(s).
        This combines the logic of previous "fix" actions into one robust method.
        It re-extracts data from the raw JSON and re-computes related display fields.
        """
        _logger.info(f"ACTION_REPROCESS_DATA: Starting re-processing for {len(self)} trip(s).")
        processed_count = 0
        error_count = 0

        for record in self:
            try:
                _logger.info(f"Processing trip {record.id} ('{record.name}').")
                
                # Modified by A_zeril_A, 2025-10-20: Updated to work without formio dependency
                # Step 1: Ensure a business_trip_data record exists.
                trip_data = record.business_trip_data_id
                if not trip_data:
                    _logger.warning(f"No business_trip_data record found for trip {record.id}. Cannot re-process.")
                    error_count += 1
                    continue
                
                # Step 2: Data extraction is no longer needed as formio is removed
                # The business_trip_data record should already contain the necessary data
                _logger.info(f"Business trip data record {trip_data.id} is already available for trip {record.id}.")

                # Step 3: Display fields are now automatically computed via related fields.
                # No manual computation needed - data flows automatically from business_trip_data_id.
                _logger.info(f"Successfully re-processed submission data for trip {record.id}.")

                processed_count += 1
            except Exception as e:
                _logger.error(f"Failed to re-process trip {record.id}. Error: {e}", exc_info=True)
                error_count += 1
        
        # Return a user-facing notification with the result.
        message = _('%s trip(s) re-processed successfully.') % processed_count
        if error_count:
            message += _('\n%s trip(s) failed.') % error_count
        
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
    def fix_submission_data_for_all_forms(self):
        """
        Fix and update submission data extraction for all forms.
        This can be called from a server action to re-process all form data.
        """
        forms = self.env['formio.form'].search([('submission_data', '!=', False), ('state', '=', 'COMPLETE')])
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

    @api.depends('accompanying_person_ids',
                 'accompanying_person_ids.full_name',
                 'accompanying_person_ids.identity_document_filename')
    def _compute_accommodation_persons_display(self):
        """Compute display string for accompanying persons"""
        for record in self:
            accompanying_persons_display = []
            for person in record.accompanying_person_ids:
                name = person.full_name
                doc_status = " (Document Attached)" if person.identity_document_filename else " (No Document)"
                accompanying_persons_display.append(f"{name}{doc_status}")

            record.accommodation_accompanying_persons_display = "\n".join(accompanying_persons_display)
            if not accompanying_persons_display:
                record.accommodation_accompanying_persons_display = "No accompanying persons specified."

    @api.depends('accompanying_person_ids',
                 'accompanying_person_ids.full_name',
                 'accompanying_person_ids.identity_document_filename')
    def _compute_accommodation_persons_json(self):
        """Compute JSON representation for accompanying persons"""
        for record in self:
            accompanying_persons_json_data = []
            for person in record.accompanying_person_ids:
                accompanying_persons_json_data.append({
                    'full_name_acc': person.full_name,
                    'accompanying_identity_document_acc_filename': person.identity_document_filename,
                })
            record.accommodation_accompanying_persons_json = json.dumps(accompanying_persons_json_data)
        
    @api.model
    def _get_trip_statuses_for_user(self):
        """
        Returns a list of trip statuses that are relevant for the current user's role.
        This is used to filter views or determine available actions.
        """
        statuses = []
        if self.env.user.has_group('custom_business_trip_management.group_business_trip_organizer'):
            statuses.extend(['pending_organization', 'organization_done', 'completed_waiting_expense', 'expense_submitted'])
        if self.env.user.has_group('base.group_system'): # Assuming admin can see all
            statuses = [
                'draft', 'submitted', 'pending_organization', 'organization_done',
                'completed_waiting_expense',
                'expense_submitted', 'completed', 'returned', 'rejected', 'cancelled'
            ]
        return statuses
        
    def _format_float_time(self, time_float):
        if not time_float:
            return ''
        hours = int(time_float)
        minutes = int((time_float * 60) % 60)
        return f"{hours:02d}:{minutes:02d}"

    def _get_reminder_delta(self, interval, interval_type):
        interval = max(interval or 0, 0)
        if interval_type == 'minutes':
            return timedelta(minutes=interval)
        return timedelta(days=interval)

    def _get_expense_followup_company(self):
        self.ensure_one()
        return self.company_id or self.user_id.company_id or self.env.company

    def _filter_expense_followup_eligible_trips(self):
        """Keep trips owned by an active user and an active employee."""
        trips = self.exists()
        if not trips:
            return trips

        active_user_ids = set(trips.mapped('user_id').filtered('active').ids)
        if not active_user_ids:
            return self.env['business.trip']

        companies = self.env['res.company']
        for trip in trips:
            companies |= trip._get_expense_followup_company()

        active_employees = self.env['hr.employee'].sudo().with_context(
            active_test=False,
        ).search([
            ('active', '=', True),
            ('user_id', 'in', list(active_user_ids)),
            ('company_id', 'in', companies.ids),
        ])
        active_employee_keys = {
            (employee.user_id.id, employee.company_id.id)
            for employee in active_employees
        }

        return trips.filtered(
            lambda trip: (
                trip.user_id.id in active_user_ids
                and (
                    trip.user_id.id,
                    trip._get_expense_followup_company().id,
                ) in active_employee_keys
            )
        )

    @api.model
    def _normalize_digest_send_hour(self, raw_hour, default=9):
        try:
            hour = int(default if raw_hour in (False, None) else raw_hour)
        except (TypeError, ValueError):
            hour = default
        return min(max(hour, 0), 23)

    @api.model
    def _get_weekday_index(self, weekday_value):
        weekday_map = {
            'monday': 0,
            'tuesday': 1,
            'wednesday': 2,
            'thursday': 3,
            'friday': 4,
            'saturday': 5,
            'sunday': 6,
        }
        return weekday_map.get(weekday_value or 'monday', 0)

    @api.model
    def _align_datetime_to_daily_window(self, value, send_hour):
        if not value:
            return False

        aligned = value.replace(
            hour=self._normalize_digest_send_hour(send_hour),
            minute=0,
            second=0,
            microsecond=0,
        )
        if value > aligned:
            aligned += timedelta(days=1)
        return aligned

    @api.model
    def _align_datetime_to_weekly_window(self, value, weekday_value, send_hour):
        if not value:
            return False

        target_weekday = self._get_weekday_index(weekday_value)
        days_ahead = (target_weekday - value.weekday()) % 7
        aligned = value.replace(
            hour=self._normalize_digest_send_hour(send_hour),
            minute=0,
            second=0,
            microsecond=0,
        ) + timedelta(days=days_ahead)
        if days_ahead == 0 and value > aligned:
            aligned += timedelta(days=7)
        return aligned

    @api.model
    def _get_current_daily_window_datetime(self, reference_datetime, send_hour):
        if not reference_datetime:
            return False
        return reference_datetime.replace(
            hour=self._normalize_digest_send_hour(send_hour),
            minute=0,
            second=0,
            microsecond=0,
        )

    @api.model
    def _get_current_weekly_window_datetime(self, reference_datetime, weekday_value, send_hour):
        if not reference_datetime:
            return False

        target_weekday = self._get_weekday_index(weekday_value)
        week_start = reference_datetime.date() - timedelta(days=reference_datetime.weekday())
        window_date = week_start + timedelta(days=target_weekday)
        return datetime.combine(window_date, datetime.min.time()).replace(
            hour=self._normalize_digest_send_hour(send_hour),
            minute=0,
            second=0,
            microsecond=0,
        )

    def _ensure_expense_followup_start_date(self):
        for trip in self:
            if trip.expense_followup_start_date:
                continue

            anchor_datetime = trip._get_post_travel_expense_anchor()
            if not anchor_datetime:
                continue
            trip.with_context(mail_notrack=True, system_edit=True).write({
                'expense_followup_start_date': anchor_datetime,
            })

    def _get_post_travel_expense_anchor(self):
        """Return midnight after travel end in company timezone, stored as UTC."""
        self.ensure_one()
        if not self.travel_end_date:
            return False

        company = self._get_expense_followup_company()
        timezone_name = (
            company.resource_calendar_id.tz
            or company.partner_id.tz
            or 'UTC'
        )
        timezone = pytz.timezone(timezone_name)
        local_anchor = timezone.localize(datetime.combine(
            self.travel_end_date + timedelta(days=1),
            datetime.min.time(),
        ))
        return local_anchor.astimezone(pytz.UTC).replace(tzinfo=None)

    def _get_expense_reminder_base_datetime(self):
        self.ensure_one()
        return (
            self.expense_followup_start_date
            or self._get_post_travel_expense_anchor()
        )

    def _get_employee_expense_followup_due_datetime(self):
        self.ensure_one()
        base_datetime = self._get_expense_reminder_base_datetime()
        if not base_datetime:
            return False

        company = self._get_expense_followup_company()
        earliest_due_datetime = base_datetime + self._get_reminder_delta(
            company.employee_expense_reminder_delay,
            company.employee_expense_reminder_delay_type,
        )
        return self._align_datetime_to_daily_window(
            earliest_due_datetime,
            company.employee_expense_digest_send_hour,
        )

    def _get_employee_expense_repeat_delta(self, company):
        interval = company.expense_reminder_interval or 0
        if interval <= 0:
            return False
        return self._get_reminder_delta(interval, company.expense_reminder_interval_type)

    def _get_organizer_expense_repeat_delta(self, company):
        interval = company.organizer_expense_reminder_interval or 0
        if interval <= 0:
            return False
        return self._get_reminder_delta(interval, company.organizer_expense_reminder_interval_type)

    def _get_employee_digest_trip_due_datetime(self):
        self.ensure_one()
        company = self._get_expense_followup_company()
        if self.trip_status == 'expense_returned':
            base_datetime = self.write_date or fields.Datetime.now()
            return self._align_datetime_to_daily_window(
                base_datetime,
                company.employee_expense_digest_send_hour,
            )
        return self._get_employee_expense_followup_due_datetime()

    def _get_organizer_expense_followup_due_datetime(self):
        self.ensure_one()
        if self.trip_status != 'completed_waiting_expense' or not self._get_expense_review_user():
            return False

        base_datetime = self._get_expense_reminder_base_datetime()
        if not base_datetime:
            return False

        company = self._get_expense_followup_company()
        earliest_due_datetime = base_datetime + self._get_reminder_delta(
            company.organizer_expense_escalation_delay,
            company.organizer_expense_escalation_delay_type,
        )
        return self._align_datetime_to_daily_window(
            earliest_due_datetime,
            company.organizer_expense_digest_send_hour,
        )

    def _get_employee_expense_followup_activity_summary(self):
        self.ensure_one()
        return "Clarify Expense Status"

    def _get_employee_expense_followup_note(self):
        self.ensure_one()
        if self.trip_status == 'expense_returned':
            return (
                "Your submitted travel expenses were returned for revision. "
                "Please update the expense details and resubmit them."
            )
        return (
            "Please submit your travel expenses or confirm that there were no additional expenses "
            "for this trip."
        )

    def _get_employee_expense_followup_status_label(self):
        self.ensure_one()
        if self.trip_status == 'expense_returned':
            return "Expense Revision Requested"
        return "Awaiting Expense Decision"

    def _get_employee_expense_followup_activities(self):
        self.ensure_one()
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo:
            return self.env['mail.activity']
        return self.env['mail.activity'].search([
            ('res_model', '=', 'business.trip'),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', todo.id),
            ('summary', '=', self._get_employee_expense_followup_activity_summary()),
        ])

    def _clear_employee_expense_followup_activities(self):
        for trip in self:
            trip._get_employee_expense_followup_activities().unlink()

    def _create_or_update_employee_expense_followup_activity(self, due_datetime):
        self.ensure_one()
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo or not self.user_id:
            return

        existing_activities = self._get_employee_expense_followup_activities()
        existing_activity = existing_activities[:1]
        (existing_activities - existing_activity).unlink()
        activity_vals = {
            'date_deadline': due_datetime.date(),
            'note': self._get_employee_expense_followup_note(),
            'user_id': self.user_id.id,
        }
        if existing_activity:
            changed_vals = {}
            for field_name, value in activity_vals.items():
                current_value = existing_activity[field_name]
                if hasattr(current_value, 'ids'):
                    current_compare = (
                        current_value.id if len(current_value) == 1 else current_value.ids
                    )
                else:
                    current_compare = current_value
                if current_compare != value:
                    changed_vals[field_name] = value
            if changed_vals:
                existing_activity.with_context(
                    mail_activity_quick_update=True,
                ).write(changed_vals)
            return

        activity_vals.update({
            'activity_type_id': todo.id,
            'summary': self._get_employee_expense_followup_activity_summary(),
            'res_model_id': self.env['ir.model']._get_id('business.trip'),
            'res_id': self.id,
            'user_id': self.user_id.id,
        })
        # The digest email is the user-facing notification; keep the To Do creation silent
        # to avoid reintroducing one email per trip via the default activity assignment flow.
        self.env['mail.activity'].with_context(mail_activity_quick_update=True).create(activity_vals)

    @api.model
    def _format_expense_digest_datetime(self, value):
        if not value:
            return "-"
        return fields.Datetime.to_string(value)

    @api.model
    def _queue_expense_digest_email(self, recipient_partner, company, subject, body_html):
        if not recipient_partner or not recipient_partner.email:
            return False

        author_partner = company.partner_id or self.env.user.partner_id
        self.env['mail.mail'].sudo().create({
            'author_id': author_partner.id if author_partner else False,
            'auto_delete': False,
            'body': body_html,
            'body_html': body_html,
            'email_from': author_partner.email_formatted if author_partner else False,
            'recipient_ids': [(4, recipient_partner.id)],
            'subject': subject,
        })
        return True

    @api.model
    def _build_employee_expense_followup_digest_email(self, employee, trips, company):
        sorted_trips = trips.sorted(
            key=lambda trip: (
                trip._get_employee_digest_trip_due_datetime() or fields.Datetime.now(),
                trip.name or '',
            )
        )
        row_html = []
        for trip in sorted_trips:
            row_html.append(
                f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{trip._get_trip_anchor_html(trip.name or '-')}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{escape(trip.destination or '-')}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{escape(trip._get_expense_review_display_name())}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{escape(trip._get_employee_expense_followup_status_label())}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{escape(str(trip.travel_end_date or '-'))}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{trip._get_trip_anchor_html('Open Trip')}</td>
                    </tr>
                """
            )

        trip_label = "trip" if len(sorted_trips) == 1 else "trips"
        verb_label = "needs" if len(sorted_trips) == 1 else "need"
        subject = f"Reminder: {len(sorted_trips)} {trip_label} {verb_label} your expense update"
        body_content = f"""
    <p>Hello <strong>{escape(employee.name or '')}</strong>,</p>
    <p>The following business trips are still waiting for your expense update. Please submit your expenses or confirm that there were no additional expenses.</p>
    <table style="border-collapse: collapse; width: 100%; margin: 16px 0;">
        <thead>
            <tr style="background-color: #f8f9fa;">
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Trip</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Destination</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Expense Reviewer</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Status</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Trip End Date</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Record</th>
            </tr>
        </thead>
        <tbody>
            {''.join(row_html)}
        </tbody>
    </table>
    <p>Each trip row links directly to the related record in Odoo. Your related To Do items are available on each business trip record.</p>
    <p style="margin-top: 16px;">Best regards,<br/>{escape(company.name or self.env.company.name or 'Your Company')}</p>
"""
        body_html = self._render_styled_message_card(
            card_type='warning',
            icon='🧾',
            title='Expense Update Needed',
            body_html=Markup(body_content),
            next_steps='Open each trip above, confirm whether there were expenses, and submit or revise the expense details.',
        )
        return subject, body_html

    @api.model
    def _build_organizer_expense_digest_email(self, reviewer, trips, company):
        sorted_trips = trips.sorted(
            key=lambda trip: (
                trip.user_id.name or '',
                trip._get_organizer_expense_followup_due_datetime() or fields.Datetime.now(),
                trip.name or '',
            )
        )
        row_html = []
        for trip in sorted_trips:
            employee_reminder_status = "Sent" if trip.employee_expense_reminder_sent_date else "Pending"
            row_html.append(
                f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{escape(trip.user_id.name or '-')}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{trip._get_trip_anchor_html(trip.name or '-')}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{escape(trip.destination or '-')}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{escape(str(trip.travel_end_date or '-'))}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{escape(employee_reminder_status)}</td>
                        <td style="padding: 8px; border: 1px solid #dee2e6;">{trip._get_trip_anchor_html('Open Trip')}</td>
                    </tr>
                """
            )

        trip_label = "trip" if len(sorted_trips) == 1 else "trips"
        subject = f"Expense Follow-up Digest: {len(sorted_trips)} pending {trip_label}"
        body_content = f"""
    <p>Hello <strong>{escape(reviewer.name or '')}</strong>,</p>
    <p>This digest groups all business trips that are still waiting for employee expense submission and currently need your follow-up as the expense reviewer.</p>
    <table style="border-collapse: collapse; width: 100%; margin: 16px 0;">
        <thead>
            <tr style="background-color: #f8f9fa;">
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Employee</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Trip</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Destination</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Trip End Date</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Employee Reminder</th>
                <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Record</th>
            </tr>
        </thead>
        <tbody>
            {''.join(row_html)}
        </tbody>
    </table>
    <p>Each trip row links directly to the related record in Odoo. Please follow up with the employees listed above and help move these trips toward financial closure.</p>
    <p style="margin-top: 16px;">Best regards,<br/>{escape(company.name or self.env.company.name or 'Your Company')}</p>
"""
        body_html = self._render_styled_message_card(
            card_type='info',
            icon='📋',
            title='Expense Follow-up Digest',
            body_html=Markup(body_content),
            next_steps='Open each trip above, review the latest expense state, and follow up with the employee where needed.',
        )
        return subject, body_html

    def _sync_employee_expense_followup_activity(self, eligibility_prechecked=False):
        eligible_trips = (
            self
            if eligibility_prechecked
            else self._filter_expense_followup_eligible_trips()
        )
        if not eligibility_prechecked:
            (self - eligible_trips)._clear_employee_expense_followup_activities()

        for trip in eligible_trips:
            if not trip.user_id:
                trip._clear_employee_expense_followup_activities()
                continue

            if trip.trip_status == 'completed_waiting_expense':
                due_datetime = trip._get_employee_expense_followup_due_datetime()
                if not due_datetime:
                    trip._clear_employee_expense_followup_activities()
                    continue

                if fields.Datetime.now() >= due_datetime:
                    trip._create_or_update_employee_expense_followup_activity(due_datetime)
                else:
                    trip._clear_employee_expense_followup_activities()
            elif trip.trip_status == 'expense_returned':
                trip._create_or_update_employee_expense_followup_activity(fields.Datetime.now())
            else:
                trip._clear_employee_expense_followup_activities()

    def _send_employee_expense_followup_digests(self, now, eligibility_prechecked=False):
        grouped_trips = defaultdict(lambda: self.env['business.trip'])
        digest_state_model = self.env['business.trip.reminder.digest.state'].sudo()

        eligible_trips = (
            self
            if eligibility_prechecked
            else self._filter_expense_followup_eligible_trips()
        )
        for trip in eligible_trips.filtered(
            lambda record: record.trip_status in ('completed_waiting_expense', 'expense_returned')
        ):
            due_datetime = trip._get_employee_digest_trip_due_datetime()
            if not due_datetime or not trip.user_id:
                continue

            company = trip._get_expense_followup_company()
            current_window_dt = self._get_current_daily_window_datetime(now, company.employee_expense_digest_send_hour)
            if not current_window_dt or now < current_window_dt or due_datetime > current_window_dt:
                continue

            grouped_trips[(trip.user_id.id, company.id)] |= trip

        for (user_id, company_id), trips in grouped_trips.items():
            employee = self.env['res.users'].browse(user_id)
            company = self.env['res.company'].browse(company_id)
            current_window_dt = self._get_current_daily_window_datetime(now, company.employee_expense_digest_send_hour)
            repeat_delta = trips[:1]._get_employee_expense_repeat_delta(company)
            digest_state = digest_state_model.get_or_create_state(
                employee,
                company,
                'employee_expense_followup',
            )

            if digest_state.last_sent_date:
                if digest_state.last_sent_date >= current_window_dt:
                    continue
                if repeat_delta and current_window_dt < (digest_state.last_sent_date + repeat_delta):
                    continue
                if not repeat_delta:
                    continue

            subject, body_html = self._build_employee_expense_followup_digest_email(employee, trips, company)
            queued = self._queue_expense_digest_email(employee.partner_id, company, subject, body_html)
            if not queued:
                _logger.info(
                    "Skipping employee expense digest for user %s because no email recipient is available.",
                    employee.id,
                )
                continue

            trips.with_context(mail_notrack=True, system_edit=True).write({
                'employee_expense_reminder_sent_date': current_window_dt or now,
            })
            digest_state.write({'last_sent_date': current_window_dt or now})

    def _get_due_organizer_expense_followup_trips(self, now, eligibility_prechecked=False):
        due_trips = self.env['business.trip']
        eligible_trips = (
            self
            if eligibility_prechecked
            else self._filter_expense_followup_eligible_trips()
        )

        for trip in eligible_trips.filtered(
            lambda record: (
                record.trip_status == 'completed_waiting_expense'
                and record._get_expense_review_user()
            )
        ):
            company = trip._get_expense_followup_company()
            current_window_dt = self._get_current_daily_window_datetime(
                now,
                company.organizer_expense_digest_send_hour,
            )
            due_datetime = trip._get_organizer_expense_followup_due_datetime()
            if current_window_dt and now >= current_window_dt and due_datetime and due_datetime <= current_window_dt:
                due_trips |= trip

        return due_trips

    def _send_organizer_expense_followup_digests(self, now, eligibility_prechecked=False):
        grouped_trips = defaultdict(lambda: self.env['business.trip'])
        digest_state_model = self.env['business.trip.reminder.digest.state'].sudo()

        for trip in self._get_due_organizer_expense_followup_trips(
            now,
            eligibility_prechecked=eligibility_prechecked,
        ):
            company = trip._get_expense_followup_company()
            reviewer = trip._get_expense_review_user()
            if reviewer:
                grouped_trips[(reviewer.id, company.id)] |= trip

        for (reviewer_id, company_id), trips in grouped_trips.items():
            reviewer = self.env['res.users'].browse(reviewer_id)
            company = self.env['res.company'].browse(company_id)
            current_window_dt = self._get_current_daily_window_datetime(
                now,
                company.organizer_expense_digest_send_hour,
            )
            repeat_delta = trips[:1]._get_organizer_expense_repeat_delta(company)
            digest_state = digest_state_model.get_or_create_state(
                reviewer,
                company,
                'organizer_expense_followup',
            )

            if digest_state.last_sent_date:
                if digest_state.last_sent_date >= current_window_dt:
                    continue
                if repeat_delta and current_window_dt < (digest_state.last_sent_date + repeat_delta):
                    continue
                if not repeat_delta:
                    continue

            subject, body_html = self._build_organizer_expense_digest_email(reviewer, trips, company)
            queued = self._queue_expense_digest_email(reviewer.partner_id, company, subject, body_html)
            if not queued:
                _logger.info(
                    "Skipping expense reviewer digest for user %s because no email recipient is available.",
                    reviewer.id,
                )
                continue

            trips.with_context(mail_notrack=True, system_edit=True).write({
                'last_expense_reminder_date': current_window_dt or now,
            })
            digest_state.write({'last_sent_date': current_window_dt or now})

    @api.model
    def _activate_post_travel_expense_followup(self, now=None):
        """Open expense follow-up only after each trip has ended locally."""
        now = fields.Datetime.to_datetime(now or fields.Datetime.now())
        utc_now = pytz.UTC.localize(now) if now.tzinfo is None else now.astimezone(pytz.UTC)

        companies = self.env['res.company'].sudo().search([])
        for company in companies:
            timezone_name = (
                company.resource_calendar_id.tz
                or company.partner_id.tz
                or 'UTC'
            )
            local_today = utc_now.astimezone(
                pytz.timezone(timezone_name)
            ).date()

            premature_trips = self.sudo().search([
                ('company_id', '=', company.id),
                ('trip_status', '=', 'completed_waiting_expense'),
                '|',
                ('travel_end_date', '=', False),
                ('travel_end_date', '>=', local_today),
            ])
            if premature_trips:
                premature_trips.with_context(
                    mail_notrack=True,
                    system_edit=True,
                ).write({
                    'trip_status': 'organization_done',
                    'expense_followup_start_date': False,
                    'employee_expense_reminder_sent_date': False,
                    'last_expense_reminder_date': False,
                })
                premature_trips._clear_employee_expense_followup_activities()

            due_trips = self.sudo().search([
                ('company_id', '=', company.id),
                ('trip_status', '=', 'organization_done'),
                ('travel_end_date', '!=', False),
                ('travel_end_date', '<', local_today),
            ])
            for trip in due_trips:
                trip.with_context(
                    mail_notrack=True,
                    system_edit=True,
                ).write({
                    'trip_status': 'completed_waiting_expense',
                    'expense_followup_start_date': (
                        trip._get_post_travel_expense_anchor()
                    ),
                    'employee_expense_reminder_sent_date': False,
                    'last_expense_reminder_date': False,
                })

        return True

    def _cron_send_expense_submission_reminders(self):
        """
        Cron job to keep employee expense follow-up aligned and optionally
        escalate stale pending expense cases to expense reviewers using grouped digests.
        """
        now = fields.Datetime.now()
        self._activate_post_travel_expense_followup(now=now)
        trips_to_remind = self.search([('trip_status', 'in', ['completed_waiting_expense', 'expense_returned'])])
        _logger.info(f"Cron job for expense reminders running at {now}. Found {len(trips_to_remind)} trips to check.")

        eligible_trips = trips_to_remind._filter_expense_followup_eligible_trips()
        ineligible_trips = trips_to_remind - eligible_trips
        ineligible_trips._clear_employee_expense_followup_activities()

        eligible_trips.filtered(
            lambda trip: not trip.expense_followup_start_date
        )._ensure_expense_followup_start_date()
        eligible_trips._sync_employee_expense_followup_activity(
            eligibility_prechecked=True,
        )
        eligible_trips._send_employee_expense_followup_digests(
            now,
            eligibility_prechecked=True,
        )
        eligible_trips._send_organizer_expense_followup_digests(
            now,
            eligibility_prechecked=True,
        )

    def read(self, fields=None, load='_classic_read'):
        """
        Remap retired pre-travel statuses to organization_done for UI
        compatibility. Expense follow-up activation remains cron-driven.
        """
        records = super(BusinessTrip, self).read(fields=fields, load=load)
        status_in_fields = not fields or 'trip_status' in fields
        phase1_in_fields = not fields or 'trip_status_phase1' in fields
        phase2_in_fields = not fields or 'trip_status_phase2' in fields

        if status_in_fields:
            for record_vals in records:
                if record_vals.get('trip_status') in (
                    'awaiting_trip_start',
                    'in_progress',
                ):
                    record_vals['trip_status'] = 'organization_done'
                    if phase1_in_fields:
                        record_vals['trip_status_phase1'] = 'organization_done'
                    if phase2_in_fields:
                        record_vals['trip_status_phase2'] = 'awaiting_trip_end'

        return records

    @api.model
    def _get_trip_status_selection(self):
        """Callable method for effective_trip_status to reuse selection."""
        return self.env['business.trip']._fields['trip_status'].selection

    @api.depends('trip_status')
    def _compute_effective_trip_status(self):
        """
        Dynamically remaps legacy trip statuses to their new equivalents.
        This ensures that all logic depending on this field sees a valid, modern status.
        """
        for rec in self:
            if rec.trip_status in ('awaiting_trip_start', 'in_progress'):
                rec.effective_trip_status = 'organization_done'
            else:
                rec.effective_trip_status = rec.trip_status

    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------

    def write(self, vals):
        """
        Override write to post messages on status changes and manage project/task creation.
        """
        protected_assignment_fields = {
            'company_id',
            'user_id',
            'manager_id',
            'organizer_id',
            'expense_reviewer_id',
        }
        if (
            protected_assignment_fields.intersection(vals)
            and not self.env.su
            and not self.env.context.get('authorized_business_trip_assignment')
            and not self.env.context.get('system_edit')
            and not self.env.user.has_group('base.group_system')
            and not self.env.user.has_group(
                'custom_business_trip_management.group_business_trip_manager'
            )
        ):
            raise AccessError(
                "Business trip assignments can only be changed through the "
                "authorized workflow."
            )

        previous_statuses = {}
        sync_followup_activity = any(field in vals for field in ('trip_status', 'user_id'))
        if sync_followup_activity:
            previous_statuses = {trip.id: trip.trip_status for trip in self}

        res = super(BusinessTrip, self).write(vals)

        if 'trip_status' in vals:
            for trip in self:
                if vals['trip_status'] == 'pending_organization':
                    # This status is set when the Travel Approver assigns the organizer.
                    # The organizer_submission_date should be set when the organizer submits their plan.
                    pass
                elif vals['trip_status'] == 'completed_waiting_expense':
                    # This status is set by the post-travel scheduled transition.
                    if not trip.organizer_submission_date:
                        trip.organizer_submission_date = fields.Datetime.now()
                    if not trip.plan_approval_date:
                        trip.plan_approval_date = fields.Datetime.now()

        if sync_followup_activity:
            for trip in self:
                previous_status = previous_statuses.get(trip.id)
                if (
                    trip.trip_status == 'completed_waiting_expense'
                    and previous_status not in ('completed_waiting_expense', 'expense_submitted', 'expense_returned')
                ):
                    trip.expense_followup_start_date = (
                        trip.expense_followup_start_date
                        or trip._get_post_travel_expense_anchor()
                    )
                    trip.employee_expense_reminder_sent_date = False
                    trip.last_expense_reminder_date = False
                trip._sync_employee_expense_followup_activity()

        if vals.get('trip_status') in ('completed', 'rejected', 'cancelled'):
            # Closing a trip may make its approver/reviewer capability stale.
            stakeholders = self.mapped('manager_id') | self.mapped('expense_reviewer_id')
            if stakeholders:
                stakeholders.sudo().cleanup_business_trip_capability_groups()

        return res

    @api.depends('effective_trip_status')
    def _compute_trip_status_phases(self):
        """
        Calculate phase-based statuses based on effective_trip_status.
        This ensures the UI statusbar correctly reflects remapped legacy statuses.
        """
        _logger.info("Computing trip status phases...")
        for rec in self:
            trip_status = rec.effective_trip_status  # Use the effective status
            _logger.info(f"Business Trip ID: {rec.id}, Current effective_trip_status: {trip_status}")

            # Reset phases
            rec.trip_status_phase1 = False
            rec.trip_status_phase2 = False

            # Phase 1: Pre-Travel
            if trip_status in ['draft', 'submitted', 'pending_organization', 'organization_done', 'rejected', 'cancelled']:
                rec.trip_status_phase1 = trip_status
                _logger.info(f"Setting trip_status_phase1 to {trip_status}")
            elif trip_status == 'returned':
                # 'returned' is a state in phase 1
                rec.trip_status_phase1 = 'returned'
                _logger.info(f"Setting trip_status_phase1 to returned for returned status")
            else:
                # If in phase 2, phase 1 should be considered 'organization_done'
                if trip_status in ['completed_waiting_expense', 'expense_submitted', 'expense_returned', 'completed']:
                    rec.trip_status_phase1 = 'organization_done'
                    _logger.info(f"Setting trip_status_phase1 to organization_done while in phase two status: {trip_status}")
                else:
                    rec.trip_status_phase1 = False
                    _logger.info(f"Setting trip_status_phase1 to False for status: {trip_status}")

            # Phase 2: Post-Travel
            if trip_status in ['completed_waiting_expense', 'expense_submitted', 'completed']:
                rec.trip_status_phase2 = trip_status
                _logger.info(f"Setting trip_status_phase2 to {trip_status}")
            elif trip_status == 'expense_returned':
                # 'expense_returned' is a state in phase 2
                rec.trip_status_phase2 = 'expense_returned'
                _logger.info(f"Setting trip_status_phase2 to expense_returned for expense_returned status")
            elif trip_status == 'organization_done':
                # Trip is planned but not finished; expense phase starts after travel end.
                rec.trip_status_phase2 = 'awaiting_trip_end'
                _logger.info("Setting trip_status_phase2 to awaiting_trip_end for organization_done status")
            else:
                rec.trip_status_phase2 = False
                _logger.info(f"Setting trip_status_phase2 to False for status: {trip_status}")
            
            _logger.info(f"Final phase status - Phase1: {rec.trip_status_phase1}, Phase2: {rec.trip_status_phase2}")

    @api.depends('trip_status')
    def _compute_exceptional_statuses(self):
        """Compute flags for UI based on trip status."""
        for rec in self:
            trip_status = rec.trip_status
            
            rec.is_returned = (trip_status == 'returned')
            rec.is_rejected = (trip_status == 'rejected')

            # Phase two
            rec.is_expense_returned = (trip_status == 'expense_returned')

            # Add log for debugging
            if trip_status == 'expense_returned':
                _logger.info(f"Computing exceptional statuses for trip {rec.id}: trip_status = {trip_status}, is_expense_returned set to True")

            # Phase two
            rec.is_expense_returned = (trip_status == 'expense_returned')

            # Add log for debugging
            if trip_status == 'expense_returned':
                _logger.info(f"Computing exceptional statuses for trip {rec.id}: trip_status = {trip_status}, is_expense_returned set to True")

    # Organizer-related fields
    organizer_id = fields.Many2one('res.users', string='Trip Organizer', tracking=True)
    organization_done_date = fields.Datetime(
        string='Organization Finalized Date',
        help="The date and time when the trip organization was finalized.",
        readonly=True,
        copy=False
    )
    organizer_trip_plan_details = fields.Html('Trip Plan Details (Organizer)')

    def get_formview_action(self, access_uid=None):
        """
        Overrides the default behavior to open the form directly in edit mode
        if the form status is 'Awaiting Completion'.
        """
        action = super(BusinessTrip, self).get_formview_action(access_uid=access_uid)

        # If we are opening a single record and its status is 'awaiting_completion',
        # modify the action to open in edit mode using context.
        if self and self.form_completion_status == 'awaiting_completion':
            action.setdefault('context', {}).update({'form_view_initial_mode': 'edit'})
            # Ensure it opens the correct form view
            action['view_id'] = self.env.ref('custom_business_trip_management.view_business_trip_form_page').id

        return action
        
        
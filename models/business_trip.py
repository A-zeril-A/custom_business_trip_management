# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging
from odoo.exceptions import UserError, ValidationError
import json
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class BusinessTrip(models.Model):
    _name = 'business.trip'
    _description = 'Business Trip Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Link to the original Form.io submission
    formio_form_id = fields.Many2one('formio.form', string='Form.io Form', ondelete='cascade', required=True, index=True)

    # Related field to easily access business_trip_data from business_trip
    # This avoids creating a new record and links to the one created by formio_form_inherit
    business_trip_data_id = fields.Many2one(related='formio_form_id.business_trip_data_id', readonly=False)

    name = fields.Char(string='Trip Name', related='formio_form_id.display_name', store=True)
    state = fields.Selection(related='formio_form_id.state', string='Status', readonly=True, store=True)

    # --- WORKFLOW & STATE ---
    trip_status = fields.Selection([
        ('draft', 'Awaiting Submission'),
        ('submitted', 'To Manager'),
        ('pending_organization', 'To Organizer'),
        ('organization_done', 'Organization Completed'),
        ('awaiting_trip_start', 'Awaiting Trip Start'),
        ('returned', 'Returned to Employee'),
        ('rejected', 'Rejected'),
        ('in_progress', 'Travel in Progress'),
        ('completed_waiting_expense', 'Awaiting Travel Expenses'),
        ('expense_submitted', 'Expenses Under Review'),
        ('expense_returned', 'Expense Returned'),
        ('completed', 'TRAVEL PROCESS COMPLETED'),
        ('cancelled', 'Cancelled')
    ], string='Trip Status', default='draft', tracking=True, copy=False)

    # --- RELATIONAL & KEY FIELDS ---
    user_id = fields.Many2one('res.users', string='Employee', required=True, default=lambda self: self.env.user)
    sale_order_id = fields.Many2one('sale.order', string='Sales Order', readonly=True)
    manager_id = fields.Many2one('res.users', string='Manager', tracking=True, help="Manager who reviews the initial request and final plan.")
    organizer_id = fields.Many2one(
        'res.users',
        string='Trip Organizer',
        tracking=True,
        domain="[('groups_id', 'in', ref('custom_business_trip_management.group_business_trip_organizer').id)]"
    )
    business_trip_project_id = fields.Many2one('project.project', string='Business Trip Project', copy=False, tracking=True)
    business_trip_task_id = fields.Many2one('project.task', string='Business Trip Task', copy=False, tracking=True)

    # --- FINANCIAL FIELDS ---
    manager_max_budget = fields.Monetary(string='Maximum Budget', tracking=False, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', related='business_trip_data_id.currency_id', readonly=True)

    # --- DATES & TRACKING ---
    submission_date = fields.Datetime(string='Employee Initial Submission Date', tracking=True, copy=False)
    manager_approval_date = fields.Datetime(string='Manager Initial Approval Date', tracking=False, copy=False)
    manager_comments = fields.Text(string='Manager Comments to Employee', tracking=True, help="Comments from manager to employee during initial review.")
    organizer_comments_to_manager = fields.Text(string='Organizer Comments to Manager', tracking=True, copy=False)
    internal_manager_organizer_notes = fields.Text(
        string="Internal Manager/Organizer Notes",
        tracking=True,
        copy=False,
        groups="custom_business_trip_management.group_business_trip_organizer,base.group_system",
    )
    
    # --- ORGANIZER PLAN FIELDS ---
    organizer_planned_cost = fields.Monetary(string='Total Planned Cost by Organizer', tracking=False, currency_field='currency_id')
    organizer_trip_plan_details = fields.Text(string='Organizer Trip Plan Notes', tracking=True)
    structured_plan_items_json = fields.Text(string='Structured Plan Items (JSON)', tracking=False, copy=False)
    organizer_attachments_ids = fields.Many2many('ir.attachment', 'business_trip_organizer_ir_attachments_rel', 'trip_id', 'attachment_id', string='Organizer Attachments', copy=False)
    organizer_submission_date = fields.Datetime(string='Organizer Plan Submission Date', tracking=True, copy=False)
    plan_approval_date = fields.Datetime(string='Manager Plan Approval Date', tracking=True, copy=False)
    actual_start_date = fields.Datetime(string='Actual Start Date', tracking=True, copy=False)
    actual_end_date = fields.Datetime(string='Actual End Date', tracking=True, copy=False)

    # Expense Management
    expense_total = fields.Float(string="Total Expenses", tracking=True, copy=False)
    expense_comments = fields.Text(string="Expense Submission Comments", tracking=True, copy=False)
    expense_attachment_ids = fields.Many2many('ir.attachment', string='Expense Attachments', copy=False)
    expense_approval_date = fields.Datetime(string="Expense Approval Date", tracking=True, readonly=True, copy=False)
    expense_approved_by = fields.Many2one('res.users', string="Expenses Approved By", readonly=True, copy=False)
    actual_expense_submission_date = fields.Datetime(string="Actual Expense Submission Date", readonly=True, copy=False)
    expense_return_comments = fields.Text(string="Manager Comments for Expense Return", tracking=True, copy=False)

    # Final Cost & Budget
    final_total_cost = fields.Float(string='Final Total Cost', tracking=True, store=True,
                                   help="The total cost to company: planned cost plus any additional expenses.")
    budget_difference = fields.Float(string='Budget Deviation', compute='_compute_budget_difference', store=True, tracking=True,
                                     help="The difference between the organizer planned cost and the actual expenses.")
    budget_status = fields.Selection([
        ('under_budget', 'Under Budget'),
        ('on_budget', 'On Budget'),
        ('over_budget', 'Over Budget'),
    ], string='Budget Status', compute='_compute_budget_difference', store=True, tracking=True)

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
    is_manager = fields.Boolean(string='Is Manager', compute='_compute_user_roles', store=False)
    is_finance = fields.Boolean(string='Is Finance', compute='_compute_user_roles', store=False)
    is_organizer = fields.Boolean(string='Is Organizer', compute='_compute_user_roles', store=False)
    can_see_costs = fields.Boolean(string='Can See Costs', compute='_compute_user_roles', store=False)
    is_current_user_owner = fields.Boolean(string="Is Current User Owner", compute='_compute_is_current_user_owner', store=False)
    can_cancel_trip = fields.Boolean(string="Can Cancel Trip", compute='_compute_can_cancel_trip', store=False)
    can_undo_expense_approval_action = fields.Boolean(string="Can Undo Expense Approval", compute='_compute_can_undo_expense_approval_action', store=False)

    @api.depends('manager_id', 'organizer_id')
    @api.depends_context('uid')
    def _compute_user_roles(self):
        for record in self:
            user = self.env.user
            is_system_admin = user.has_group('base.group_system')

            if is_system_admin:
                record.is_manager = True
                record.is_finance = True
                record.is_organizer = True
                record.can_see_costs = True
                continue

            record.is_manager = (record.manager_id and user.id == record.manager_id.id)
            record.is_organizer = (record.organizer_id and user.id == record.organizer_id.id)
            is_finance_user = user.has_group('account.group_account_manager')
            record.is_finance = record.is_organizer or is_finance_user
            
            is_in_organizer_group = user.has_group('custom_business_trip_management.group_business_trip_organizer')
            record.can_see_costs = record.is_manager or record.is_organizer or is_in_organizer_group

    @api.depends_context('uid')
    def _compute_is_current_user_owner(self):
        for record in self:
            record.is_current_user_owner = (record.user_id.id == self.env.user.id)

    @api.depends('trip_status', 'manager_approval_date', 'is_current_user_owner')
    @api.depends_context('uid')
    def _compute_can_cancel_trip(self):
        for record in self:
            can_cancel = False
            # We rely on the pre-computed is_current_user_owner field
            if record.is_current_user_owner and record.trip_status in ['draft', 'submitted']:
                if record.trip_status == 'submitted':
                    # If any approval has been made, cancellation is not allowed.
                    if not record.manager_approval_date:
                        can_cancel = True
                else:  # 'draft' state
                    can_cancel = True
            record.can_cancel_trip = can_cancel

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

    @api.depends('organizer_planned_cost', 'expense_total')
    def _compute_budget_difference(self):
        for trip in self:
            if trip.organizer_planned_cost > 0:
                trip.budget_difference = trip.organizer_planned_cost - trip.expense_total
                if trip.budget_difference < 0:
                    trip.budget_status = 'over_budget'
                elif trip.budget_difference == 0:
                    trip.budget_status = 'on_budget'
                else:
                    trip.budget_status = 'under_budget'
            else:
                trip.budget_difference = 0
                trip.budget_status = False

    def action_approve_expenses(self):
        """
        Approve trip expenses by manager, organizer, or finance personnel
        """
        self.ensure_one()
        if self.trip_status != 'expense_submitted':
            raise ValidationError("You can only approve expenses that have been submitted for review.")

        # TODO: Re-evaluate permissions after moving is_organizer
        # if not (self.env.user.has_group('account.group_account_manager') or
        #         self.env.user.has_group('base.group_system') or
        #         self.is_organizer):
        #     raise ValidationError("Only the trip organizer, finance personnel, or system administrators can approve expenses.")

        # Calculate final total cost
        total_cost = self.organizer_planned_cost + self.expense_total

        self.write({
            'trip_status': 'completed',
            'expense_approval_date': fields.Datetime.now(),
            'expense_approved_by': self.env.user.id,
            'final_total_cost': total_cost,
        })

        # Chatter notifications
        budget_message = ""
        if self.budget_difference > 0:
            budget_message = f"<span style='color:green'>Actual expenses {abs(self.budget_difference):.2f} {self.currency_id.symbol} less than planned.</span>"
        elif self.budget_difference < 0:
            budget_message = f"<span style='color:red'>Actual expenses {abs(self.budget_difference):.2f} {self.currency_id.symbol} more than planned.</span>"
        else:
            budget_message = "<span style='color:blue'>Expenses exactly match the plan.</span>"

        # Notify manager and organizer with financial details
        partners_to_notify = []
        if self.manager_id:
            partners_to_notify.append(self.manager_id.partner_id.id)
        if self.organizer_id:
            partners_to_notify.append(self.organizer_id.partner_id.id)
        
        if partners_to_notify:
            confidential_msg = f"""
<strong>Trip Cost Analysis (Confidential)</strong><br/>
<ul>
    <li>Maximum Budget Allocated: {self.manager_max_budget:.2f} {self.currency_id.symbol}</li>
    <li>Planned Travel Costs: {self.organizer_planned_cost:.2f} {self.currency_id.symbol}</li>
    <li>Employee Expenditures: {self.expense_total:.2f} {self.currency_id.symbol}</li>
    <li>Budget Status: {budget_message}</li>
</ul>
"""
            self.message_post(body=confidential_msg, partner_ids=partners_to_notify)

        # Notify the employee (without any financial details)
        if self.user_id.partner_id:
            public_msg = f"Your travel expense submission for trip '{self.name}' has been approved. The business trip is now COMPLETED."
            self.message_post(body=public_msg, partner_ids=[self.user_id.partner_id.id])

        self.message_post(
            body=f"Travel expenses for business trip '{self.name}' have been approved by {self.env.user.name}.",
            subtype_xmlid='mail.mt_note'
        )

        return True

    def action_return_expenses(self):
        """
        Return trip expenses to employee for correction
        """
        self.ensure_one()
        if self.trip_status != 'expense_submitted':
            raise ValidationError("You can only return expenses that have been submitted for review.")

        # TODO: Re-evaluate permissions after moving is_organizer
        # if not (self.env.user.has_group('account.group_account_manager') or
        #         self.env.user.has_group('base.group_system') or
        #         self.is_organizer):
        #     raise ValidationError("Only the trip organizer, finance personnel, or system administrators can return expenses.")

        self.write({'trip_status': 'expenses_returned'})
        
        # Notify the employee with enhanced styling
        if self.user_id.partner_id:
            styled_message = f"""
<div style="background-color: #ffeeba; border: 1px solid #ffc107; border-radius: 5px; padding: 15px; margin-top: 20px; margin-bottom: 15px;">
    <p>Your travel expense submission for trip '<strong>{self.name}</strong>' has been returned for revision.</p>
    <p><strong>Next steps:</strong> Please check the comments, make necessary corrections, and resubmit your expenses.</p>
    <p>Returned by: {self.env.user.name}</p>
</div>
"""
            if self.expense_return_comments:
                styled_message += f"""
<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px; margin-top: 10px;">
    <p><strong>Comments:</strong></p>
    <p>{self.expense_return_comments}</p>
</div>
"""
            self.message_post(body=styled_message, partner_ids=[self.user_id.partner_id.id])
            
        return True

    def action_open_rejection_wizard(self):
        """Open wizard for rejecting the trip request."""
        self.ensure_one()

        if self.trip_status not in ['submitted']:
            raise ValidationError("You can only reject requests that are in 'Submitted to Manager' state using this wizard.")

        if not self.env.user.has_group('base.group_system') and not (self.manager_id and self.env.user.id == self.manager_id.id):
            raise ValidationError("Only the assigned manager or system administrators can reject the request.")

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
        
        # Additional check for submitted state might be needed if manager already actioned it
        # For now, keeping it simple as per original logic.

        self.write({
            'trip_status': 'cancelled',
            'cancellation_date': fields.Datetime.now(),
            'cancelled_by': self.env.user.id,
        })

        if self.formio_form_id:
            self.formio_form_id.write({'state': 'CANCEL'})

        self.message_post(body=f"Request cancelled by {self.env.user.name}.")

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_open_expense_submission_wizard(self):
        """Open wizard for submitting actual expenses."""
        self.ensure_one()

        if self.trip_status not in ['awaiting_expense_report', 'expenses_returned']:
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

    @api.model_create_multi
    def create(self, vals_list):
        """
        Overrides the create method to orchestrate the creation of all related records:
        1. Business Trip (self)
        2. Business Trip Data
        3. Formio Form
        """
        # First, create the business.trip record(s)
        trips = super(BusinessTrip, self).create(vals_list)

        # Find the formio.builder once for all trips in the batch
        builder = self.env['formio.builder'].search([('name', '=', 'Business Trip Form')], limit=1)
        if not builder:
            # You might want to create it or raise an error if it's essential
            raise UserError(_("Form.io Builder 'Business Trip Form' not found. Please create it."))

        for trip in trips:
            # Create the associated business_trip_data record
            trip_data = self.env['business.trip.data'].create({'form_id': False}) # form_id will be linked later
            trip.business_trip_data_id = trip_data.id

            # Create the associated formio.form record
            form_vals = {
                'builder_id': builder.id,
                'title': trip.name,
                'user_id': trip.user_id.id,
                'business_trip_id': trip.id, # Link back to this trip
            }
            if trip.sale_order_id:
                form_vals.update({
                    'sale_order_id': trip.sale_order_id.id,
                    'res_model_id': self.env.ref('sale.model_sale_order').id,
                    'res_id': trip.sale_order_id.id,
                })
            
            form = self.env['formio.form'].create(form_vals)
            
            # Now, link the form back to the trip and the data record
            trip.formio_form_id = form.id
            trip_data.form_id = form.id

        return trips

    @api.depends('user_id', 'create_date', 'sale_order_id')
    def _compute_name(self):
        for trip in self:
            if trip.sale_order_id:
                trip.name = f"Trip for SO {trip.sale_order_id.name}"
            else:
                create_date_str = fields.Datetime.to_string(trip.create_date.date() if trip.create_date else fields.Date.today())
                trip.name = f"Trip for {trip.user_id.name} on {create_date_str}"

    def process_form_submission(self, submission_data_str):
        """
        Processes form submission data, updates the related data record,
        and posts a summary to the chatter.
        """
        self.ensure_one()
        _logger.info(f"Processing submission for Business Trip {self.id}...")

        if not self.business_trip_data_id:
            _logger.error(f"CRITICAL: Business Trip {self.id} does not have a linked business_trip_data record. Aborting submission processing.")
            return False

        submission_content = None
        if submission_data_str and isinstance(submission_data_str, str):
            try:
                submission_content = json.loads(submission_data_str)
            except json.JSONDecodeError as e:
                _logger.error(f"JSONDecodeError for form related to trip {self.id}: {e}. Raw data: {submission_data_str}")
                return False
        elif submission_data_str and isinstance(submission_data_str, dict):
            submission_content = submission_data_str
        
        if not submission_content:
            _logger.warning(f"No submission_content to process for trip {self.id}. Skipping data update.")
            return False

        # Delegate data processing to the data model
        result_process = self.business_trip_data_id.process_submission_data(submission_content)

        if result_process:
            _logger.info(f"Successfully processed submission_data into business.trip.data record {self.business_trip_data_id.id}")

            # Post summary message to this record's chatter
            try:
                summary_body_html = self.env.ref('custom_business_trip_management.form_submission_summary')._render({
                    'record': self.business_trip_data_id,
                }, engine='ir.qweb')

                message_body = self.env.ref('custom_business_trip_management.chatter_message_card')._render({
                    'card_type': 'success',
                    'icon': '📄',
                    'title': 'Form Submission Summary',
                    'body_html': summary_body_html,
                    'submitted_by': self.env.user.name,
                }, engine='ir.qweb')
                
                self.message_post(body=message_body, subtype_xmlid="mail.mt_note")
                _logger.info(f"Successfully posted styled summary message to chatter for trip {self.id}")
            except Exception as e:
                _logger.error(f"Failed to render or post summary message for trip {self.id}: {e}", exc_info=True)
        else:
            _logger.error(f"Failed to process submission_data into business.trip.data record for trip {self.id}")
        
        return result_process

    @api.depends(
        'business_trip_data_id.destination',
        'business_trip_data_id.purpose',
        'business_trip_data_id.travel_start_date',
        'business_trip_data_id.travel_end_date',
    )
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

    def action_submit_to_manager(self):
        """Submit a completed trip request form to a manager for approval."""
        self.ensure_one()

        if self.user_id.id != self.env.user.id:
            raise UserError("Only the owner of this form can submit it.")

        if self.trip_status not in ['draft', 'returned']:
            raise UserError(f"Only forms in 'Draft' or 'Returned' status can be submitted. Current status: {self.trip_status}")

        if not self.has_trip_details:
            # In a real scenario, you'd return a warning action.
            raise UserError("Please fill in all required trip details (Destination, Purpose, Dates) before submitting.")

        # Validate dates
        if self.business_trip_data_id.travel_start_date > self.business_trip_data_id.travel_end_date:
            raise UserError("End date cannot be before start date.")

        # Find the employee's manager if not already set
        if not self.manager_id:
            employee = self.env['hr.employee'].sudo().search([('user_id', '=', self.user_id.id)], limit=1)
            if employee and employee.parent_id and employee.parent_id.user_id:
                manager = employee.parent_id.user_id
            else:
                # Fallback to admin if no manager found
                admin_user = self.env.ref('base.user_admin', raise_if_not_found=False)
                if admin_user:
                    manager = admin_user
                else:
                    raise UserError("Your manager is not set. Please contact HR.")
        else:
            manager = self.manager_id

        # Update the trip
        self.write({
            'trip_status': 'submitted',
            'submission_date': fields.Datetime.now(),
            'manager_id': manager.id,
        })

        # Notify the manager
        if self.manager_id and self.manager_id.partner_id:
            self.message_post(
                body=f"Business trip request submitted by {self.env.user.name} for your review.",
                partner_ids=[self.manager_id.partner_id.id],
                subtype_xmlid="mail.mt_comment",
            )

        return True

    def action_manager_assign_organizer_and_budget(self):
        self.ensure_one()
        if self.trip_status not in ['submitted']:
            raise UserError("Request must be in 'Submitted to Manager' state.")

        if self.env.user.id != self.manager_id.id and not self.env.user.has_group('base.group_system'):
            raise UserError("Only the assigned manager or an administrator can perform this action.")

        return {
            'type': 'ir.actions.act_window',
            'name': 'Assign Organizer and Budget',
            'res_model': 'business.trip.assign.organizer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_trip_id': self.id, # Pass trip_id instead of form_id
                'default_manager_id': self.manager_id.id
            }
        }

    def confirm_assignment_and_budget(self, manager_max_budget, organizer_id, manager_comments=None, internal_notes=None):
        """Confirm and assign budget and organizer by manager"""
        self.ensure_one()

        if not self.env.user.has_group('hr.group_hr_manager') and not self.env.user.has_group('base.group_system'):
            raise UserError("Only managers or system administrators can assign organizers and budgets.")

        if manager_max_budget <= 0:
            raise UserError("Maximum budget must be a positive value.")

        stakeholder_users = self.user_id | self.manager_id | self.env['res.users'].browse(organizer_id)
        
        project = self.sale_order_id.project_ids and self.sale_order_id.project_ids[0] or False
        if not project:
            project_vals = {
                'allow_timesheets': True,
                'user_id': self.manager_id.id,
            }
            if self.sale_order_id:
                project_vals.update({
                    'name': self.sale_order_id.name,
                    'partner_id': self.sale_order_id.partner_id.id,
                    'sale_order_id': self.sale_order_id.id,
                })
            else:
                project_vals.update({
                    'name': f"Business Trip: {self.name}",
                    'partner_id': self.user_id.partner_id.id,
                })
            project = self.env['project.project'].create(project_vals)

        task = self._create_business_trip_task(project, organizer_id)

        vals = {
            'manager_max_budget': manager_max_budget,
            'organizer_id': organizer_id,
            'trip_status': 'pending_organization',
            'manager_approval_date': fields.Datetime.now(),
            'business_trip_project_id': project.id,
            'business_trip_task_id': task.id,
        }
        if manager_comments:
            vals['manager_comments'] = manager_comments
        if internal_notes:
            vals['internal_manager_organizer_notes'] = internal_notes

        self.write(vals)
        self._add_stakeholders_as_followers(project, task, organizer_id)
        
        # Notification logic would go here
        
        return True

    def _create_business_trip_task(self, project, organizer_id):
        """Creates the main task for the business trip project."""
        self.ensure_one()
        assignee_ids = [organizer_id, self.user_id.id]
        if self.manager_id:
            assignee_ids.append(self.manager_id.id)
        
        task_name = f'Business Trip: {self.name}'
        
        task = self.env['project.task'].create({
            'name': task_name,
            'project_id': project.id,
            'user_ids': [(6, 0, list(set(assignee_ids)))],
            'planned_hours': 1,
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

    def action_organizer_confirm_planning(self):
        """Organizer confirms planning is complete and notifies the employee."""
        self.ensure_one()
        if self.trip_status not in ['pending_organization']:
            raise UserError("Planning can only be confirmed when trip is 'Pending Organization'.")
        if self.env.user.id != self.organizer_id.id and not self.env.user.has_group('base.group_system'):
            raise UserError("Only the assigned trip organizer or an administrator can confirm the planning.")

        if not self.organizer_trip_plan_details and not self.structured_plan_items_json:
            raise UserError("Please provide trip plan details before confirming.")

        if self.organizer_planned_cost <= 0:
            raise UserError("Please set a planned cost greater than zero before confirming.")

        self.write({
            'trip_status': 'awaiting_trip_start',
            'organizer_submission_date': fields.Datetime.now(),
            'plan_approval_date': fields.Datetime.now(), 
        })

        # Notification logic would go here
        
        return True 

    def action_start_trip(self):
        """Action for employee to mark the beginning of their travel."""
        self.ensure_one()
        if self.trip_status != 'awaiting_trip_start':
            raise UserError("You can only start a trip that is awaiting travel.")
        if self.user_id.id != self.env.user.id:
            raise UserError("Only the employee assigned to the trip can start it.")
        
        self.write({
            'trip_status': 'in_progress',
            'actual_start_date': fields.Datetime.now()
        })
        self.message_post(body="The business trip has officially started.")
        return True

    def action_end_trip(self):
        """Action for employee to mark the end of their travel."""
        self.ensure_one()
        if self.trip_status != 'in_progress':
            raise UserError("You can only end a trip that is currently in progress.")
        if self.user_id.id != self.env.user.id:
            raise UserError("Only the employee assigned to the trip can end it.")
            
        self.write({
            'trip_status': 'completed_waiting_expense',
            'actual_end_date': fields.Datetime.now()
        })
        self.message_post(body="The business trip has ended. Please submit your expenses.")
        return True 
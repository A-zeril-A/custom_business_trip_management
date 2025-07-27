# -*- coding: utf-8 -*-

import json
import base64
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import uuid
import re

_logger = logging.getLogger(__name__)

class TripDetailsWizard(models.TransientModel):
    """Wizard for editing trip details through a popup"""
    _name = 'business.trip.details.wizard'
    _description = 'Business Trip Details Wizard'
    
    form_id = fields.Many2one('formio.form', string='Trip Form', required=True)
    destination = fields.Char(string='Destination', required=True)
    purpose = fields.Text(string='Purpose of Trip', required=True)
    
    # Trip type selection
    is_hourly_trip = fields.Boolean(string='Is Hourly Trip', help="Select for same-day trips defined by hours.")
    
    # Date fields
    travel_start_date = fields.Date(string='Start Date', required=True)
    travel_end_date = fields.Date(string='End Date', required=True)
    
    # Time fields for hourly trips
    travel_start_time = fields.Float(string='Start Time', help="Trip start time (e.g., 9.5 for 9:30 AM).")
    travel_end_time = fields.Float(string='End Time', help="Trip end time (e.g., 17.5 for 5:30 PM).")
    
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    
    @api.model
    def default_get(self, fields_list):
        """Fetch values from the related trip form"""
        res = super(TripDetailsWizard, self).default_get(fields_list)
        form_id = self.env.context.get('active_id')
        if form_id:
            form = self.env['formio.form'].browse(form_id)
            
            # Check if it's already marked as an hourly trip or infer from dates
            is_hourly_trip = form.is_hourly_trip
            if not is_hourly_trip and form.travel_start_date and form.travel_end_date:
                if form.travel_start_date == form.travel_end_date:
                    is_hourly_trip = True
                
            # Set default times for hourly trips
            travel_start_time = 9.0  # Default to 9:00 AM
            travel_end_time = 17.0   # Default to 5:00 PM
            
            # If the form already has time information, use it
            if form.travel_start_time:
                travel_start_time = form.travel_start_time
            if form.travel_end_time:
                travel_end_time = form.travel_end_time
            
            # If no existing times but we have duration for hourly trip, calculate end time
            elif is_hourly_trip and form.travel_duration and form.travel_duration > 0:
                # For hourly trips, travel_duration is in hours
                travel_end_time = travel_start_time + form.travel_duration
                if travel_end_time >= 24:
                    travel_end_time = 23.99  # Cap at 11:59 PM
            
            res.update({
                'form_id': form_id,
                'destination': form.destination,
                'purpose': form.purpose,
                'travel_start_date': form.travel_start_date,
                'travel_end_date': form.travel_end_date,
                'currency_id': form.currency_id.id,
                'is_hourly_trip': is_hourly_trip,
                'travel_start_time': travel_start_time,
                'travel_end_time': travel_end_time,
            })
        return res
    
    @api.onchange('is_hourly_trip', 'travel_start_date')
    def _onchange_trip_type(self):
        """Update end date when trip type changes or start date changes"""
        if self.is_hourly_trip and self.travel_start_date:
            self.travel_end_date = self.travel_start_date
    
    @api.onchange('travel_start_time', 'travel_end_time')
    def _onchange_time(self):
        """Validate time values"""
        if self.travel_start_time and self.travel_start_time < 0:
            self.travel_start_time = 0
        elif self.travel_start_time and self.travel_start_time >= 24:
            self.travel_start_time = 23.99
            
        if self.travel_end_time and self.travel_end_time < 0:
            self.travel_end_time = 0
        elif self.travel_end_time and self.travel_end_time >= 24:
            self.travel_end_time = 23.99
    
    def action_save(self):
        """Save updated details to the trip form"""
        self.ensure_one()
        
        # Validate dates
        if self.travel_start_date > self.travel_end_date:
            raise ValidationError("End date cannot be before start date.")
        
        # Calculate travel duration based on the trip type
        duration = 0.0
        if self.is_hourly_trip:
            # For hourly trips, calculate hours directly
            if self.travel_start_time is not None and self.travel_end_time is not None:
                # Calculate hours
                hours = self.travel_end_time - self.travel_start_time
                if hours < 0:  # Handle case where end time is before start time
                    hours = 24 + hours
                duration = hours  # Store actual hours (not fraction of day)
            else:
                duration = 4.0  # Default to 4 hours if times not specified
        else:
            # For multi-day trips, calculate days including start and end date
            if self.travel_start_date and self.travel_end_date:
                delta = (self.travel_end_date - self.travel_start_date).days + 1
                duration = float(delta)
        
        # Update the form
        vals = {
            'destination': self.destination,
            'purpose': self.purpose,
            'travel_start_date': self.travel_start_date,
            'travel_end_date': self.travel_end_date,
            # currency_id is also managed directly on formio.form if needed for display or other logic there
            'currency_id': self.currency_id.id, 
        }
        
        # The following fields are managed in business.trip.data and should not be directly written to formio.form here.
        # Their values will be updated in business.trip.data through other mechanisms if needed,
        # or formio.form fields will be related fields to business.trip.data for these.

        # if duration > 0:
        #     # vals['manual_travel_duration'] = duration # This field is on business.trip.data
        #     vals['is_hourly_trip'] = self.is_hourly_trip # This field is on business.trip.data
        #     if self.is_hourly_trip:
        #         vals['travel_start_time'] = self.travel_start_time # This field is on business.trip.data
        #         vals['travel_end_time'] = self.travel_end_time # This field is on business.trip.data
        
        # Use a context to indicate this is an allowed update from a wizard
        _logger.info(f"WIZARD SAVE: Attempting to write to form {self.form_id.id} with vals: {vals}")
        self.form_id.with_context(from_wizard=True, system_edit=True).write(vals)
        _logger.info(f"WIZARD SAVE: Successfully wrote to form {self.form_id.id}")

        # Additionally, we need to update the corresponding business.trip.data record
        # for the fields that are now solely managed there.
        btd_record = self.env['business.trip.data'].search([('form_id', '=', self.form_id.id)], limit=1)
        if btd_record:
            btd_vals = {
                'destination': self.destination, # Keep destination and purpose sync if they exist on BTD
                'purpose': self.purpose,
                'travel_start_date': self.travel_start_date, # Keep dates sync if they exist on BTD
                'travel_end_date': self.travel_end_date,
                'is_hourly_trip': self.is_hourly_trip,
                'currency_id': self.currency_id.id,
            }
            if duration > 0:
                 btd_vals['manual_travel_duration'] = duration
            if self.is_hourly_trip:
                btd_vals['travel_start_time'] = self.travel_start_time
                btd_vals['travel_end_time'] = self.travel_end_time
            else: # Clear time fields if not hourly
                btd_vals['travel_start_time'] = 0.0
                btd_vals['travel_end_time'] = 0.0

            _logger.info(f"WIZARD SAVE: Attempting to write to BTD record {btd_record.id} with vals: {btd_vals}")
            btd_record.write(btd_vals)
            _logger.info(f"WIZARD SAVE: Successfully wrote to BTD record {btd_record.id}")
        else:
            _logger.warning(f"WIZARD SAVE: No BTD record found for form {self.form_id.id} to update duration/hourly info.")

        return {'type': 'ir.actions.act_window_close'}


class CostEstimationWizard(models.TransientModel):
    """Wizard for cost estimation through a popup"""
    _name = 'business.trip.cost.wizard'
    _description = 'Business Trip Cost Estimation Wizard'
    
    form_id = fields.Many2one('formio.form', string='Trip Form', required=True)
    expected_cost = fields.Float(string='Expected Cost', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    estimation_comments = fields.Text(string='Estimation Notes')
    
    @api.model
    def default_get(self, fields_list):
        """Fetch values from the related trip form"""
        res = super(CostEstimationWizard, self).default_get(fields_list)
        form_id = self.env.context.get('active_id')
        if form_id:
            form = self.env['formio.form'].browse(form_id)
            res.update({
                'form_id': form_id,
                'expected_cost': form.expected_cost,
                'currency_id': form.currency_id.id,
                'estimation_comments': form.estimation_comments,
            })
        return res
    
    def action_save(self):
        """Save cost estimation to the trip form"""
        self.ensure_one()
        
        # Check if user has permission to estimate cost (only manager or finance)
        if not self.env.user.has_group('hr.group_hr_manager') and not self.env.user.has_group('account.group_account_manager') and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only managers or finance personnel can estimate costs.")
            
        # Validate cost
        if self.expected_cost <= 0:
            raise ValidationError("Expected cost must be greater than zero.")
        
        # Update the form
        vals = {
            'expected_cost': self.expected_cost,
            'currency_id': self.currency_id.id,
            'estimation_comments': self.estimation_comments,
        }
        
        # If the user is a manager/finance and the trip is in submitted status, 
        # also update the status and record the estimation
        form = self.form_id
        if form.trip_status == 'submitted':
            vals.update({
                'trip_status': 'cost_estimated',
                'estimated_by': self.env.user.id,
                'estimation_date': fields.Datetime.now(),
            })
            
            # Notify the user
            if form.user_id:
                form.message_post(
                    body=f"Cost estimation has been completed for your trip request.",
                    partner_ids=[form.user_id.partner_id.id]
                )
        
        form.write(vals)
        return {'type': 'ir.actions.act_window_close'}


class ExpenseSubmissionWizard(models.TransientModel):
    _name = 'business.trip.expense.submission.wizard'
    _description = 'Business Trip Expense Submission Wizard'

    form_id = fields.Many2one('formio.form', string='Trip Form', required=True, readonly=True)
    expense_total = fields.Float(string='Total Actual Cost', required=True)
    # currency_id should be the same as the main form, so fetch it
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    expense_comments = fields.Text(string='Expense Comments')
    expense_attachment_ids = fields.Many2many(
        'ir.attachment', 
        'business_trip_expense_wizard_attachment_rel',
        'wizard_id', 
        'attachment_id', 
        string='Expense Attachments (Receipts, etc.)'
    )
    # New field to indicate no expenses
    has_no_expenses = fields.Boolean(string='No Expenses to Submit', help="Check this if you have no expenses to submit for this trip")

    @api.onchange('has_no_expenses')
    def _onchange_has_no_expenses(self):
        """Reset expense total to zero when no expenses checkbox is checked"""
        if self.has_no_expenses:
            self.expense_total = 0.0
        
    @api.onchange('expense_total')
    def _onchange_expense_total(self):
        """Reset no expenses checkbox when expense total is changed to a non-zero value"""
        if self.expense_total > 0:
            self.has_no_expenses = False

    @api.model
    def default_get(self, fields_list):
        res = super(ExpenseSubmissionWizard, self).default_get(fields_list)
        form_id = self.env.context.get('active_id')
        if form_id:
            form = self.env['formio.form'].browse(form_id)
            res.update({
                'form_id': form_id,
                'currency_id': form.currency_id.id,
                # Pre-fill with existing values if any, useful for re-submission after return
                'expense_total': form.expense_total,
                'expense_comments': form.expense_comments,
                'expense_attachment_ids': [(6, 0, form.expense_attachment_ids.ids)],
                # Set has_no_expenses based on existing data
                'has_no_expenses': form.expense_total == 0,
            })
        return res

    def action_apply(self):
        self.ensure_one()
        
        # Validate expenses based on the no expenses checkbox
        if self.has_no_expenses:
            # If no expenses, force expense_total to 0
            self.expense_total = 0.0
        else:
            # If submitting expenses, validate the amount
            if self.expense_total <= 0:
                raise ValidationError("Total actual cost must be greater than zero when submitting expenses.")
            
            # If expense amount is greater than zero, require attachments
            if self.expense_total > 0 and not self.expense_attachment_ids:
                raise ValidationError("You must attach receipt(s) when submitting expenses with an amount greater than zero.")

        # Check if form is in the correct state for expense submission
        if self.form_id.trip_status not in ['completed_waiting_expense', 'expense_returned']:
            raise ValidationError(f"You can only submit expenses when the trip is in 'Waiting for Expense Submission' or 'Expense Returned' state. Current state: {self.form_id.trip_status}")

        # Store previous value for comparison
        old_expense_total = self.form_id.expense_total
        
        # Update fields separately to prevent automatic message in chatter
        vals = {
            'expense_comments': self.expense_comments,
            'expense_attachment_ids': [(6, 0, self.expense_attachment_ids.ids)],
            'actual_expense_submission_date': fields.Datetime.now(),
        }
        
        # Update expense amount separately
        if old_expense_total != self.expense_total:
            vals['expense_total'] = self.expense_total
            
        # Apply changes to form
        self.form_id.with_context(system_edit=True).write(vals)
        
        # Call the submission action with context indicating if this is a no-expense submission
        return self.form_id.with_context(no_expenses_submission=self.has_no_expenses).action_submit_expenses()


class ReturnCommentWizard(models.TransientModel):
    _name = 'business.trip.return.comment.wizard'
    _description = 'Business Trip Return Comment Wizard'

    form_id = fields.Many2one('formio.form', string='Trip Form', required=True, readonly=True)
    return_comments = fields.Text(string='Return Comments', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super(ReturnCommentWizard, self).default_get(fields_list)
        form_id = self.env.context.get('active_id')
        if form_id:
            form = self.env['formio.form'].browse(form_id)
            res.update({
                'form_id': form_id,
                'return_comments': form.return_comments, # Pre-fill if already has comments
            })
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.return_comments:
            raise ValidationError("Return comments are required.")

        # Check if form is in the correct state for returning with comments
        if self.form_id.trip_status not in ['submitted', 'cost_estimated']:
            raise ValidationError("You can only return requests that have been submitted or had costs estimated.")

        # Check if user has permission (manager/finance/system)
        if not (self.env.user.has_group('hr.group_hr_manager') or \
                self.env.user.has_group('account.group_account_manager') or \
                self.env.user.has_group('base.group_system')):
            raise ValidationError("Only managers, finance, or system administrators can return the request with comments.")

        # Update both return_comments (for legacy support) and manager_comments
        self.form_id.write({
            'return_comments': self.return_comments,
            'manager_comments': self.return_comments,  # Also set manager_comments for proper display
        })
        
        # Call the original action_return_with_comment on the form 
        return self.form_id.action_return_with_comment() 


class RejectionWizard(models.TransientModel):
    _name = 'business.trip.rejection.wizard'
    _description = 'Business Trip Rejection Wizard'

    form_id = fields.Many2one('formio.form', string='Trip Form', required=True, readonly=True)
    rejection_reason = fields.Selection([
        ('budget', 'Budget Constraints'),
        ('timing', 'Bad Timing'),
        ('necessity', 'Not Necessary'),
        ('information', 'Insufficient Information'),
        ('other', 'Other')
    ], string='Rejection Reason', required=True)
    rejection_comment = fields.Text(string='Rejection Details')

    @api.model
    def default_get(self, fields_list):
        res = super(RejectionWizard, self).default_get(fields_list)
        form_id = self.env.context.get('active_id')
        if form_id:
            form = self.env['formio.form'].browse(form_id)
            res.update({
                'form_id': form_id,
                'rejection_reason': form.rejection_reason,
                'rejection_comment': form.rejection_comment,
            })
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.rejection_reason:
            raise ValidationError("Rejection reason is required.")

        # Check if form is in the correct state for rejection
        if self.form_id.trip_status not in ['submitted', 'cost_estimated']:
            raise ValidationError("You can only reject requests that have been submitted or had costs estimated.")

        # Check if user has permission (manager/system)
        if not (self.env.user.has_group('hr.group_hr_manager') or \
                self.env.user.has_group('base.group_system')):
            raise ValidationError("Only managers or system administrators can reject the request.")

        self.form_id.write({
            'rejection_reason': self.rejection_reason,
            'rejection_comment': self.rejection_comment,
            # 'rejected_by': self.env.user.id, # This will be set in action_reject
            # 'rejection_date': fields.Datetime.now(), # This will be set in action_reject
        })
        
        # Call the original action_reject on the form 
        return self.form_id.action_reject() 


class ExpenseReturnCommentWizard(models.TransientModel):
    _name = 'business.trip.expense.return.comment.wizard'
    _description = 'Business Trip Expense Return Comment Wizard'

    form_id = fields.Many2one('formio.form', string='Trip Form', required=True, readonly=True)
    expense_return_comments = fields.Text(string='Expense Return Comments', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super(ExpenseReturnCommentWizard, self).default_get(fields_list)
        form_id = self.env.context.get('active_id')
        if form_id:
            form = self.env['formio.form'].browse(form_id)
            res.update({
                'form_id': form_id,
                'expense_return_comments': form.expense_return_comments, # Pre-fill if already has comments
            })
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.expense_return_comments:
            raise ValidationError("Expense return comments are required.")

        # Check if form is in the correct state for returning expenses
        if self.form_id.trip_status != 'expense_submitted':
            raise ValidationError("You can only return expenses that have been submitted for review.")

        # Check if user has permission (finance/system/organizer)
        if not (self.env.user.has_group('account.group_account_manager') or \
                self.env.user.has_group('base.group_system') or \
                (self.form_id.organizer_id and self.env.user.id == self.form_id.organizer_id.id)):
            raise ValidationError("Only the trip organizer, finance personnel, or system administrators can return expenses.")

        # Save the comments before calling the action_return_expenses - using system_edit context
        self.form_id.with_context(system_edit=True).write({
            'expense_return_comments': self.expense_return_comments,
        })
        
        # Call the original action_return_expenses on the form 
        return self.form_id.action_return_expenses()


class BusinessTripAssignOrganizerWizard(models.TransientModel):
    _name = 'business.trip.assign.organizer.wizard'
    _description = 'Assign Organizer and Budget for Business Trip'

    form_id = fields.Many2one('formio.form', string='Business Trip Request', readonly=True, required=True)
    manager_id = fields.Many2one('res.users', string="Requesting Manager", readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    manager_max_budget = fields.Monetary(string='Maximum Budget', required=False, help="Set the maximum budget for the organizer.", currency_field='currency_id')
    organizer_id = fields.Many2one(
        'res.users', 
        string='Trip Organizer', 
        required=True,
        domain=lambda self: [('groups_id', 'in', [self.env.ref('custom_business_trip_management.group_business_trip_organizer').id])],
        help="Select the user who will organize this trip."
    )
    assignment_comments = fields.Text(string='Comments for Organizer (Optional)', help="Initial instructions or comments for the trip organizer.")
    # This field will hold the budget value when the wizard loads or when manager types it.
    # It's distinct from manager_max_budget on the form which is the *confirmed* budget.
    # And distinct from temp_manager_max_budget on the form which is *saved unconfirmed* budget.
    # This wizard field is primarily for UI interaction before saving.
    # No, let's remove this. The previous approach of not having it on wizard was better.
    # temp_manager_max_budget_wizard = fields.Float(string='Budget Draft') 


    @api.model
    def default_get(self, fields_list):
        res = super(BusinessTripAssignOrganizerWizard, self).default_get(fields_list)
        if self.env.context.get('default_form_id'):
            form = self.env['formio.form'].browse(self.env.context.get('default_form_id'))
            if form:
                res['form_id'] = form.id
                
                # Fetch manager_id and currency_id from the form
                if form.manager_id:
                    res['manager_id'] = form.manager_id.id
                if form.currency_id:
                    res['currency_id'] = form.currency_id.id
                
                if form.organizer_id:
                    res['organizer_id'] = form.organizer_id.id
                    
                # Logic for pre-filling budget in the wizard:
                # 1. Prioritize the unconfirmed temporary budget saved on the form.
                # 2. If not present, use the last confirmed budget from the form.
                # 3. Otherwise, it defaults to 0.0.
                if form.temp_manager_max_budget and form.temp_manager_max_budget > 0:
                    res['manager_max_budget'] = form.temp_manager_max_budget
                elif form.manager_max_budget and form.manager_max_budget > 0:
                    res['manager_max_budget'] = form.manager_max_budget
                else:
                    res['manager_max_budget'] = 0.0 # Default to 0 if no budget set
                    
        return res
        
    # Removed _compute_temp_budget as the wizard's own temp_manager_max_budget field was removed in last attempt and is not being re-added.

    def action_assign_organizer_and_budget(self):
        """Save and confirm organizer assignment with budget"""
        self.ensure_one()
        if not self.form_id:
            raise UserError("Business Trip Request is not linked.")
        if not self.organizer_id:
            raise UserError("Trip Organizer must be selected for final confirmation.")
        if self.manager_max_budget <= 0:
            raise UserError("Maximum budget must be a positive value for final confirmation. If you want to save without setting a budget, use the 'Save (Preliminary)' button instead.")

        # Check if anything significant has changed
        organizer_changed = self.form_id.organizer_id.id != self.organizer_id.id
        budget_changed = self.form_id.manager_max_budget != self.manager_max_budget
        
        # If nothing has changed, just close the wizard without any updates or messages
        if not organizer_changed and not budget_changed:
            return {'type': 'ir.actions.act_window_close'}

        # Values from the wizard are sent to the confirm_assignment_and_budget method in formio.form
        # and that method is responsible for writing the values to the form and sending the necessary messages.
        self.form_id.confirm_assignment_and_budget(
            manager_max_budget=self.manager_max_budget,
            organizer_id=self.organizer_id.id,
            manager_comments=self.form_id.manager_comments, # Send the general manager comments that were previously on the form or changed in the wizard
            internal_notes=self.assignment_comments # Wizard comments are sent as internal notes for the organizer
        )
        
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_save_organizer_only(self):
        """Save organizer assignment without requiring budget (for preliminary assignment)"""
        self.ensure_one()
        if not self.form_id:
            raise UserError("Business Trip Request is not linked.")
        if not self.organizer_id:
            raise UserError("Trip Organizer must be selected.")
            
        organizer_changed = self.form_id.organizer_id.id != self.organizer_id.id
        
        # Get the budget value from the wizard field
        wizard_budget_input = self.manager_max_budget or 0.0
        
        # Get the current temporary budget stored on the main form
        temp_budget_on_form = self.form_id.temp_manager_max_budget or 0.0
        
        temp_budget_changed = temp_budget_on_form != wizard_budget_input
        
        if not organizer_changed and not temp_budget_changed:
            _logger.info("action_save_organizer_only: No changes to organizer or temporary budget. Closing wizard.")
            return {'type': 'ir.actions.act_window_close'}
            
        if self.organizer_id and self.organizer_id.partner_id:
            self.form_id.message_subscribe(partner_ids=[self.organizer_id.partner_id.id])
            
        try:
            self.env['share.formio.form'].sudo().create({
                'share_user_id': self.organizer_id.id,
                'formio_form_id': self.form_id.id,
            })
        except Exception as e:
            _logger.warning(f"Could not share form with organizer: {e}. This is expected if 'share.formio.form' model doesn't exist.")
            
        # Values to write to the main form (formio.form)
        form_vals_to_write = {
            'organizer_id': self.organizer_id.id,
            # When saving preliminarily, the *final* manager_max_budget on the form is cleared (set to 0)
            # as the budget is not yet confirmed. The confirmed budget is only set by action_assign_organizer_and_budget.
            'manager_max_budget': 0.0, 
            # The budget entered in the wizard is saved to temp_manager_max_budget on the form.
            # This allows it to be pre-filled if the wizard is reopened before confirmation.
            'temp_manager_max_budget': wizard_budget_input 
        }
        
        _logger.info(f"action_save_organizer_only: Writing to form {self.form_id.id}: {form_vals_to_write}")
        self.form_id.with_context(system_edit=True).write(form_vals_to_write)
        
        attention_style = "font-weight: bold; color: #856404; background-color: #fff3cd; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-bottom: 1px;"
        
        confidential_message_parts = []
        chatter_message_parts = []

        if organizer_changed:
            confidential_message_parts.append(f"You have been preliminarily assigned as the organizer for this business trip.")
            chatter_message_parts.append(f"Organizer {self.organizer_id.name} preliminarily assigned/updated.")
        
        if temp_budget_changed:
            if wizard_budget_input > 0:
                budget_text = f"{wizard_budget_input} {self.form_id.currency_id.symbol if self.form_id.currency_id else ''}"
                confidential_message_parts.append(f"A preliminary budget of {budget_text} has been noted (not finalized).")
                chatter_message_parts.append(f"A preliminary budget was noted by the manager (not finalized).")
            elif temp_budget_on_form > 0: # Wizard budget is 0, but there was a temp budget previously
                old_budget_text = f"{temp_budget_on_form} {self.form_id.currency_id.symbol if self.form_id.currency_id else ''}"
                confidential_message_parts.append(f"The previously noted preliminary budget of {old_budget_text} has been cleared.")
                chatter_message_parts.append("Previously noted preliminary budget was cleared by the manager.")

        if confidential_message_parts:
            confidential_msg_body = '<br/>'.join(confidential_message_parts)
            confidential_msg = f"""
            <strong>Preliminary Trip Assignment Update</strong><br/>
            <p>{confidential_msg_body}</p>
            <p><div style="{attention_style}">Attention:</div><br/>This is a preliminary assignment/update only. The budget has not been officially finalized.</p>
            <p>Please review the trip details. The trip status will advance after the budget is confirmed.</p>
            """
            
            if self.assignment_comments:
                confidential_msg += f"<strong>Manager Comments:</strong><br/>{self.assignment_comments}"
                
            recipient_ids_confidential = [self.organizer_id.id]
            if self.form_id.manager_id and self.env.user.id != self.form_id.manager_id.id:
                recipient_ids_confidential.append(self.form_id.manager_id.id)
                
            self.form_id.post_confidential_message(
                message=confidential_msg,
                recipient_ids=list(set(recipient_ids_confidential))
            )
        
        if chatter_message_parts:
            final_chatter_message = ' '.join(chatter_message_parts)
            _logger.info(f"action_save_organizer_only: Posting chatter message to form {self.form_id.id}: {final_chatter_message}")
            self.form_id.message_post(
                body=final_chatter_message,
                subtype_xmlid='mail.mt_note'
            )
            
        return {'type': 'ir.actions.act_window_close'}


class BusinessTripOrganizerPlanWizard(models.TransientModel):
    _name = 'business.trip.organizer.plan.wizard'
    _description = 'Business Trip Organizer Planning Wizard'

    form_id = fields.Many2one('formio.form', string='Business Trip Request', readonly=True, required=True)
    manager_max_budget = fields.Monetary(string='Maximum Budget (Set by Manager)', compute='_compute_manager_max_budget', readonly=True)
    organizer_trip_plan_details = fields.Text(string='Additional Notes', 
                                           help="Overall plan notes or item details.")
    
    # Cost calculation options
    manual_cost_entry = fields.Boolean(string='Enter Total Cost Manually', 
                                       help="Enter total cost manually.")
    organizer_planned_cost = fields.Monetary(string='Total Planned Cost', 
                                        compute='_compute_total_cost', 
                                        inverse='_inverse_total_cost',
                                        store=True, 
                                        help="Total planned cost for the trip")
    manual_planned_cost = fields.Monetary(string='Manual Total Cost', 
                                       help="Total cost (if manual entry selected).")
    
    # Attachments
    organizer_attachments_ids = fields.Many2many('ir.attachment', 
                                                'wizard_organizer_plan_ir_attachments_rel',
                                                'wizard_id', 'attachment_id', 
                                                string='Additional Attachments', 
                                                groups="custom_business_trip_management.group_business_trip_organizer,base.group_system",
                                                help="General plan attachments.")
    
    # Employee documents
    employee_documents_ids = fields.Many2many('ir.attachment',
                                            'wizard_organizer_employee_docs_rel',
                                            'wizard_id', 'attachment_id',
                                            string='Documents for Employee',
                                            help="Employee travel docs (tickets, etc.).")
    
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_id', readonly=True)
    
    # New field for plan items
    plan_item_ids = fields.One2many('business.trip.plan.line.item', 'wizard_id', string='Travel Plan Items')
    
    # For summary display
    transport_count = fields.Integer(string='Transport Items', compute='_compute_item_counts')
    accommodation_count = fields.Integer(string='Accommodation Items', compute='_compute_item_counts')
    other_count = fields.Integer(string='Other Items', compute='_compute_item_counts')
    
    # Status tracking
    over_budget = fields.Boolean(string='Over Budget', compute='_compute_budget_status')
    budget_difference = fields.Monetary(string='Budget Difference', compute='_compute_budget_status')
    
    @api.depends('form_id.currency_id')
    def _compute_currency_id(self):
        for wizard in self:
            wizard.currency_id = wizard.form_id.currency_id

    @api.depends('form_id', 'form_id.manager_max_budget')
    def _compute_manager_max_budget(self):
        for wizard in self:
            wizard.manager_max_budget = wizard.form_id.manager_max_budget if wizard.form_id else 0.0

    @api.depends('plan_item_ids', 'plan_item_ids.cost', 'manual_cost_entry', 'manual_planned_cost')
    def _compute_total_cost(self):
        for wizard in self:
            if wizard.manual_cost_entry:
                # Use manual cost entry - preserve the manually entered value
                wizard.organizer_planned_cost = wizard.manual_planned_cost
            else:
                # Auto-calculate from plan items
                items_with_cost = wizard.plan_item_ids.filtered(lambda x: x.cost is not False and x.cost > 0)
                total = sum(items_with_cost.mapped('cost'))
                wizard.organizer_planned_cost = total
    
    def _inverse_total_cost(self):
        # This method is called when organizer_planned_cost is directly set
        for wizard in self:
            if wizard.manual_cost_entry:
                # When manual cost entry is enabled, sync the manual cost with the total
                wizard.manual_planned_cost = wizard.organizer_planned_cost
            else:
                # When auto-calculation is enabled, the change should not affect manual cost
                # The compute method will handle the recalculation
                pass
    
    @api.depends('organizer_planned_cost', 'manager_max_budget')
    def _compute_budget_status(self):
        for wizard in self:
            # Calculate budget status
            wizard.over_budget = wizard.manager_max_budget > 0 and wizard.organizer_planned_cost > wizard.manager_max_budget
            if wizard.manager_max_budget > 0:
                wizard.budget_difference = wizard.manager_max_budget - wizard.organizer_planned_cost
            else:
                wizard.budget_difference = 0
    
    @api.depends('plan_item_ids', 'plan_item_ids.item_type')
    def _compute_item_counts(self):
        for wizard in self:
            transport_types = ['transport_air', 'transport_train', 'transport_bus', 'transport_car', 'transport_taxi']
            accommodation_types = ['accommodation']
            
            wizard.transport_count = len(wizard.plan_item_ids.filtered(lambda x: x.item_type in transport_types))
            wizard.accommodation_count = len(wizard.plan_item_ids.filtered(lambda x: x.item_type in accommodation_types))
            wizard.other_count = len(wizard.plan_item_ids) - wizard.transport_count - wizard.accommodation_count
    
    # Helper methods for quick add buttons
    def action_add_flight(self):
        """Quick add a flight item"""
        self.ensure_one()
        
        # Use travel dates from form if available
        start_date = self.form_id.travel_start_date or fields.Date.today()
        end_date = self.form_id.travel_end_date or start_date
        
        # Try to use origin/destination from form
        origin = self.form_id.user_id.company_id.city if self.form_id.user_id and self.form_id.user_id.company_id else ''
        destination = self.form_id.destination or ''
        
        # Create outbound flight
        self.plan_item_ids = [(0, 0, {
            'item_type': 'transport_air',
            'description': 'Flight',
            'direction': 'outbound',
            'item_date': start_date,
            'from_location': origin,
            'to_location': destination,
        })]
        
        # If it's a round trip (different start/end dates), add return flight
        if end_date and end_date > start_date:
            self.plan_item_ids = [(0, 0, {
                'item_type': 'transport_air',
                'description': 'Return Flight',
                'direction': 'inbound',
                'item_date': end_date,
                'from_location': destination,
                'to_location': origin,
            })]
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def action_add_accommodation(self):
        """Quick add an accommodation item"""
        self.ensure_one()
        
        # Use travel dates from form if available
        start_date = self.form_id.travel_start_date or fields.Date.today()
        end_date = self.form_id.travel_end_date or start_date
        
        # Calculate nights
        nights = 1
        if end_date and start_date:
            delta = (end_date - start_date).days
            nights = max(1, delta)
        
        # Use destination from form
        location = self.form_id.destination or ''
        
        # Create accommodation
        self.plan_item_ids = [(0, 0, {
            'item_type': 'accommodation',
            'description': 'Hotel',
            'accommodation_type': 'hotel',
            'item_date': start_date,
            'nights': nights,
        })]
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def action_add_local_transport(self):
        """Quick add a local transport item"""
        self.ensure_one()
        
        # Use travel dates from form if available
        start_date = self.form_id.travel_start_date or fields.Date.today()
        
        # Use destination from form
        location = self.form_id.destination or ''
        
        # Create local transport
        self.plan_item_ids = [(0, 0, {
            'item_type': 'transport_taxi',
            'description': 'Local Transport',
            'direction': 'local',
            'item_date': start_date,
            'from_location': 'Airport' if location else '',
            'to_location': location or 'Hotel',
        })]
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def action_add_meals(self):
        """Quick add a meals item"""
        self.ensure_one()
        
        # Use travel dates from form if available
        start_date = self.form_id.travel_start_date or fields.Date.today()
        
        # Create meals
        self.plan_item_ids = [(0, 0, {
            'item_type': 'meals_per_diem',
            'description': 'Daily Meals Allowance',
            'item_date': start_date,
        })]
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _prepare_plan_details_text(self, exclude_financials=False):  # Add exclude_financials parameter
        """Create a well-formatted text version of the travel plan for saving to the form"""
        self.ensure_one()
        
        # Format currency amounts
        currency_symbol = self.currency_id.symbol if self.currency_id else ''
        
        # Build the text
        plan_text = "=== TRAVEL PLAN DETAILS ===\n\n"
        
        if not self.plan_item_ids:
            plan_text += "No detailed plan items specified.\\n\\n"
            if self.manual_cost_entry and not exclude_financials:  # Check exclude_financials
                plan_text += f"TOTAL PLANNED COST (MANUALLY ENTERED): {self.manual_planned_cost} {currency_symbol}\\n\\n"
            
            # Additional notes
            if self.organizer_trip_plan_details:
                plan_text += "ADDITIONAL NOTES:\n"
                plan_text += self.organizer_trip_plan_details
                
            return plan_text
            
        # Group items by type for better organization
        transport_items = self.plan_item_ids.filtered(lambda x: x.item_type.startswith('transport_'))
        accommodation_items = self.plan_item_ids.filtered(lambda x: x.item_type in ['accommodation', 'accommodation_airbnb'])
        meals_items = self.plan_item_ids.filtered(lambda x: x.item_type in ['meals', 'meals_per_diem'])
        other_items = self.plan_item_ids - transport_items - accommodation_items - meals_items
        
        # Transportation
        if transport_items:
            plan_text += "TRANSPORTATION:\n"
            for item in sorted(transport_items, key=lambda x: (x.item_date, x.id)):
                direction_text = dict(item._fields['direction'].selection).get(item.direction, '')
                
                # Handle route information
                if item.from_location and item.to_location:
                    route = f"{item.from_location} → {item.to_location}"
                else:
                    route = "No route specified"
                    
                # Handle custom item type
                item_type_text = ""
                if item.item_type == 'custom' and item.custom_type:
                    item_type_text = f"({item.custom_type})"
                elif item.item_type == 'transport_other':
                    item_type_text = ""
                else:
                    item_type_text = f"({dict(item._fields['item_type'].selection).get(item.item_type, '')})"
                    
                # Format time information if available
                time_info = ""
                if item.departure_time or item.arrival_time:
                    departure_hours = int(item.departure_time)
                    departure_minutes = int((item.departure_time - departure_hours) * 60)
                    arrival_hours = int(item.arrival_time)
                    arrival_minutes = int((item.arrival_time - arrival_hours) * 60)
                    
                    if item.departure_time:
                        time_info += f" Dep: {departure_hours:02d}:{departure_minutes:02d}"
                    if item.arrival_time:
                        time_info += f" Arr: {arrival_hours:02d}:{arrival_minutes:02d}"
                
                # Format carrier and reference information
                carrier_info = f" - {item.carrier}" if item.carrier else ""
                ref_info = f" (Ref: {item.reference_number})" if item.reference_number else ""
                travel_class = f", {dict(item._fields['travel_class'].selection).get(item.travel_class, '')}" if item.travel_class else ""
                
                # Get type-specific details from JSON
                extra_details = []
                item_data = item.get_item_data()
                
                if item.item_type == 'transport_air':
                    if item_data.get('flight_number'):
                        extra_details.append(f"Flight: {item_data.get('flight_number')}")
                    if item_data.get('terminal_info'):
                        extra_details.append(f"Terminal: {item_data.get('terminal_info')}")
                    if item_data.get('layovers'):
                        extra_details.append(f"Layovers: {item_data.get('layovers')}")
                
                elif item.item_type in ['accommodation', 'accommodation_airbnb']:
                    if item_data.get('check_in_time'):
                        extra_details.append(f"Check-in: {item_data.get('check_in_time')}")
                    if item_data.get('check_out_time'):
                        extra_details.append(f"Check-out: {item_data.get('check_out_time')}")
                    if item_data.get('room_type'):
                        extra_details.append(f"Room: {item_data.get('room_type')}")
                    if item_data.get('address'):
                        extra_details.append(f"Address: {item_data.get('address')}")
                
                elif item.item_type in ['meals', 'meals_per_diem']:
                    if item_data.get('meal_type'):
                        extra_details.append(f"Meal: {item_data.get('meal_type')}")
                    if item_data.get('allowance_rate'):
                        extra_details.append(f"Rate: {item_data.get('allowance_rate')}")
                
                elif item.item_type == 'conference':
                    if item_data.get('event_name'):
                        extra_details.append(f"Event: {item_data.get('event_name')}")
                    if item_data.get('location'):
                        extra_details.append(f"Location: {item_data.get('location')}")
                    if item_data.get('event_times'):
                        extra_details.append(f"Times: {item_data.get('event_times')}")
                
                # Format extra details
                extra_details_text = ""
                if extra_details:
                    extra_details_text = f" ({', '.join(extra_details)})"
                
                # Payment information
                payment_info = ""
                if item.payment_method:
                    payment_text = dict(item._fields['payment_method'].selection).get(item.payment_method, '')
                    payment_info = f" - {payment_text}"
                
                cost_status_text = ""
                if item.cost_status:
                    cost_status_text = f" ({dict(item._fields['cost_status'].selection).get(item.cost_status, '')})"
                
                # Cost may be empty (optional now)
                cost_text = f"Cost: {item.cost} {currency_symbol}{cost_status_text}{payment_info}" if item.cost else "Cost: Not specified"
                
                if exclude_financials:  # Check exclude_financials
                    plan_text += f"- {item.description} {item_type_text}: {route}, {item.item_date}{carrier_info}{ref_info}{travel_class}{time_info}{extra_details_text}\\n"
                else:
                    plan_text += f"- {item.description} {item_type_text}: {route}, {item.item_date}{carrier_info}{ref_info}{travel_class}{time_info}{extra_details_text}, {cost_text}\\n"
                if item.notes:
                    plan_text += f"  Notes: {item.notes}\\n"
            plan_text += "\\n"
        
        # Accommodation
        if accommodation_items:
            plan_text += "ACCOMMODATION:\n"
            for item in sorted(accommodation_items, key=lambda x: (x.item_date, x.id)):
                accommodation_type = dict(item._fields['accommodation_type'].selection).get(item.accommodation_type, '')
                nights_text = f"{item.nights} night{'s' if item.nights != 1 else ''}"
                
                # Format reference information
                ref_info = f" (Ref: {item.reference_number})" if item.reference_number else ""
                
                # Payment information
                payment_info = ""
                if item.payment_method:
                    payment_text = dict(item._fields['payment_method'].selection).get(item.payment_method, '')
                    payment_info = f" - {payment_text}"
                
                cost_status_text = ""
                if item.cost_status:
                    cost_status_text = f" ({dict(item._fields['cost_status'].selection).get(item.cost_status, '')})"
                    
                # Custom type handling
                if item.item_type == 'custom' and item.custom_type:
                    accommodation_type = item.custom_type
                
                # Cost may be empty (optional now)
                cost_text = f"Cost: {item.cost} {currency_symbol}{cost_status_text}{payment_info}" if item.cost else "Cost: Not specified"
                
                if exclude_financials:  # Check exclude_financials
                    plan_text += f"- {item.description} ({accommodation_type}): {nights_text}, {item.item_date}{ref_info}\\n"
                else:
                    plan_text += f"- {item.description} ({accommodation_type}): {nights_text}, {item.item_date}{ref_info}, {cost_text}\\n"
                if item.notes:
                    plan_text += f"  Notes: {item.notes}\\n"
            plan_text += "\\n"
        
        # Meals
        if meals_items:
            plan_text += "MEALS & PER DIEM:\n"
            for item in sorted(meals_items, key=lambda x: (x.item_date, x.id)):
                item_type = dict(item._fields['item_type'].selection).get(item.item_type, '')
                
                # Payment information
                payment_info = ""
                if item.payment_method:
                    payment_text = dict(item._fields['payment_method'].selection).get(item.payment_method, '')
                    payment_info = f" - {payment_text}"
                
                cost_status_text = ""
                if item.cost_status:
                    cost_status_text = f" ({dict(item._fields['cost_status'].selection).get(item.cost_status, '')})"
                
                # Cost may be empty (optional now)
                cost_text = f"Cost: {item.cost} {currency_symbol}{cost_status_text}{payment_info}" if item.cost else "Cost: Not specified"
                
                if exclude_financials:  # Check exclude_financials
                    plan_text += f"- {item.description} ({item_type}): {item.item_date}\\n"
                else:
                    plan_text += f"- {item.description} ({item_type}): {item.item_date}, {cost_text}\\n"
                if item.notes:
                    plan_text += f"  Notes: {item.notes}\\n"
            plan_text += "\\n"
        
        # Other expenses
        if other_items:
            plan_text += "OTHER EXPENSES:\n"
            for item in sorted(other_items, key=lambda x: (x.item_date, x.id)):
                # Get proper item type text
                if item.item_type == 'custom' and item.custom_type:
                    item_type = item.custom_type
                else:
                    item_type = dict(item._fields['item_type'].selection).get(item.item_type, '')
                
                # Reference number if applicable
                ref_info = f" (Ref: {item.reference_number})" if item.reference_number else ""
                
                # Payment information
                payment_info = ""
                if item.payment_method:
                    payment_text = dict(item._fields['payment_method'].selection).get(item.payment_method, '')
                    payment_info = f" - {payment_text}"
                
                cost_status_text = ""
                if item.cost_status:
                    cost_status_text = f" ({dict(item._fields['cost_status'].selection).get(item.cost_status, '')})"
                
                # Cost may be empty (optional now)
                cost_text = f"Cost: {item.cost} {currency_symbol}{cost_status_text}{payment_info}" if item.cost else "Cost: Not specified"
                
                if exclude_financials:  # Check exclude_financials
                    plan_text += f"- {item.description} ({item_type}): {item.item_date}{ref_info}\\n"
                else:
                    plan_text += f"- {item.description} ({item_type}): {item.item_date}{ref_info}, {cost_text}\\n"
                if item.notes:
                    plan_text += f"  Notes: {item.notes}\\n"
            plan_text += "\\n"
        
        # Total cost if not manual entry
        if not self.manual_cost_entry and not exclude_financials:  # Check exclude_financials
            total_planned_cost = self.organizer_planned_cost
            plan_text += f"TOTAL PLANNED COST (AUTO-CALCULATED): {total_planned_cost} {currency_symbol}\\n\\n"
        
        # Additional notes - only include if not excluding financials
        if self.organizer_trip_plan_details and not exclude_financials:
            plan_text += "ADDITIONAL NOTES:\n"
            plan_text += self.organizer_trip_plan_details
        elif self.organizer_trip_plan_details and exclude_financials:
            # Optionally, add a generic note for public view if notes exist but are hidden
            plan_text += "ADDITIONAL NOTES: (Details available in confidential view)\n"
        
        return plan_text

    @api.model
    def default_get(self, fields_list):
        res = super(BusinessTripOrganizerPlanWizard, self).default_get(fields_list)
        form_id = self.env.context.get('active_id')
        if form_id:
            form = self.env['formio.form'].browse(form_id)
            res.update({
                'form_id': form_id,
                'organizer_trip_plan_details': form.organizer_trip_plan_details,
                'manual_planned_cost': form.organizer_planned_cost,
                # Attachments will be handled separately
            })
            
            # Determine if manual cost entry should be enabled
            # If there's a cost but no structured plan items, assume manual entry
            if form.organizer_planned_cost and form.organizer_planned_cost > 0:
                has_structured_items = form.structured_plan_items_json and form.structured_plan_items_json.strip() not in ['', '[]']
                if not has_structured_items:
                    res['manual_cost_entry'] = True
                    
            # Load existing attachments
            if form.organizer_attachments_ids:
                res['organizer_attachments_ids'] = [(6, 0, form.organizer_attachments_ids.ids)]
                
            # Load employee documents if available
            if hasattr(form, 'employee_documents_ids') and form.employee_documents_ids:
                res['employee_documents_ids'] = [(6, 0, form.employee_documents_ids.ids)]
                
            # Create plan items from the saved data
            if form.trip_status == 'pending_organization':
                # Try to recreate items from saved data
                self._recreate_plan_items_from_form(res, form)
        return res
    
    def _recreate_plan_items_from_form(self, res, form):
        """Recreate plan items from the structured JSON data saved on the form."""
        plan_items_vals_list = []
        if form.structured_plan_items_json:
            try:
                loaded_items_data = json.loads(form.structured_plan_items_json)
                if isinstance(loaded_items_data, list):
                    for item_data_dict in loaded_items_data:
                        vals = {
                            'item_type': item_data_dict.get('item_type'),
                            'custom_type': item_data_dict.get('custom_type'),
                            'item_data_json': item_data_dict.get('item_data_json'),
                            'direction': item_data_dict.get('direction'),
                            'description': item_data_dict.get('description'),
                            'item_date': fields.Date.from_string(item_data_dict.get('item_date')) if item_data_dict.get('item_date') else None,
                            'from_location': item_data_dict.get('from_location'),
                            'to_location': item_data_dict.get('to_location'),
                            'carrier': item_data_dict.get('carrier'),
                            'reference_number': item_data_dict.get('reference_number'),
                            'departure_time': item_data_dict.get('departure_time'),
                            'arrival_time': item_data_dict.get('arrival_time'),
                            'travel_class': item_data_dict.get('travel_class'),
                            'nights': item_data_dict.get('nights'),
                            'accommodation_type': item_data_dict.get('accommodation_type'),
                            'cost': item_data_dict.get('cost'),
                            'cost_status': item_data_dict.get('cost_status'),
                            'is_reimbursable': item_data_dict.get('is_reimbursable', True),
                            'payment_method': item_data_dict.get('payment_method'),
                            'notes': item_data_dict.get('notes'),
                        }
                        plan_items_vals_list.append((0, 0, vals))
                else:
                    _logger.warning(
                        f"Failed to recreate plan items for form {form.id}: structured_plan_items_json was not a list."
                    )
            except json.JSONDecodeError as e:
                _logger.error(
                    f"Failed to parse structured_plan_items_json for form {form.id}: {e}. JSON content: {form.structured_plan_items_json}"
                )
            except Exception as e:
                _logger.error(f"Unexpected error recreating plan items from JSON for form {form.id}: {e}")

        if plan_items_vals_list:
            res['plan_item_ids'] = plan_items_vals_list
        elif not form.structured_plan_items_json and not form.organizer_trip_plan_details and form.organizer_planned_cost > 0:
            # If no JSON and no manual notes, but there was a cost, create default items (legacy or initial setup).
            # This might need to be adjusted based on desired behavior for empty plans.
            _logger.info(f"No structured plan items found for form {form.id}, creating default items as organizer_planned_cost > 0.")
            self._create_default_plan_items(res, form)
        else:
            # No items from JSON and no condition for default items, so ensure plan_item_ids is empty or not set in res
            # This handles the case where an empty plan was explicitly saved (empty JSON list).
            if 'plan_item_ids' not in res: # if previous logic (text parsing) was removed this might not be needed
                 res['plan_item_ids'] = []
            _logger.info(f"No structured plan items found or loaded for form {form.id}. Wizard will start with empty/default items if applicable elsewhere.")

    def _create_default_plan_items(self, res, form):
        # This method can be expanded to create default plan items
        # based on the initial trip request data.
        return res

    def action_save_plan(self):
        """
        Saves the current state of the plan from the wizard to the main form,
        and posts styled notifications to the chatter.
        """
        self.ensure_one()
        _logger.info(f"Attempting to save plan for form {self.form_id.id} by organizer {self.env.user.name}.")

        # Re-parent attachments to grant access before linking them
        if self.employee_documents_ids:
            self.employee_documents_ids.write({
                'res_model': 'formio.form',
                'res_id': self.form_id.id
            })
        if self.organizer_attachments_ids:
            self.organizer_attachments_ids.write({
                'res_model': 'formio.form',
                'res_id': self.form_id.id
            })

        # Serialize plan items to JSON
        plan_items_data = []
        for item in self.plan_item_ids:
            item_vals = {
                'id': item.id,
                'item_type': item.item_type,
                'custom_type': item.custom_type,
                'direction': item.direction,
                'description': item.description,
                'item_date': item.item_date.strftime('%Y-%m-%d') if item.item_date else None,
                'from_location': item.from_location,
                'to_location': item.to_location,
                'carrier': item.carrier,
                'reference_number': item.reference_number,
                'departure_time': item.departure_time,
                'arrival_time': item.arrival_time,
                'travel_class': item.travel_class,
                'nights': item.nights,
                'accommodation_type': item.accommodation_type,
                'cost': item.cost,
                'cost_status': item.cost_status,
                'is_reimbursable': item.is_reimbursable,
                'payment_method': item.payment_method,
                'notes': item.notes,
                'item_data_json': item.item_data_json
            }
            plan_items_data.append(item_vals)

        # Save the plan details to the main form
        self.form_id.write({
            'organizer_planned_cost': self.organizer_planned_cost,
            'organizer_trip_plan_details': self.organizer_trip_plan_details,
            'structured_plan_items_json': json.dumps(plan_items_data, indent=4),
            'organizer_attachments_ids': [(6, 0, self.organizer_attachments_ids.ids)],
            'employee_documents_ids': [(6, 0, self.employee_documents_ids.ids)],
            'organizer_submission_date': fields.Datetime.now()
        })

        # --- START: MODIFIED SECTION ---
        # After saving to the form, post a structured summary to the confidential chatter.
        try:
            plan_details_structured = self._prepare_plan_details_structured(exclude_financials=False)
            
            message_body = self.env.ref('custom_business_trip_management.organizer_plan_summary')._render({
                'plan_data': plan_details_structured,
                'organizer_name': self.env.user.name,
            }, engine='ir.qweb')

            if message_body:
                # This call handles sending the message to the correct recipients (manager/organizer)
                self.form_id.post_confidential_message(message_body)
                _logger.info(f"Successfully posted structured confidential plan summary for form {self.form_id.id}")

        except Exception as e:
            _logger.error(f"Failed to post structured confidential summary for form {self.form_id.id}: {e}", exc_info=True)
            # Fallback to the old plain text method if template rendering fails
            plan_details_str_confidential = self._prepare_plan_details_text(exclude_financials=False)
            if plan_details_str_confidential:
                fallback_message = "A travel plan has been drafted. (Template failed, showing raw text):\n\n" + plan_details_str_confidential
                self.form_id.post_confidential_message(fallback_message)
        # --- END: MODIFIED SECTION ---

        # Post the styled public message for the employee
        self.form_id._post_styled_message(
            template_xml_id='custom_business_trip_management.organizer_plan_public_summary',
            card_type='info',
            icon='⏳',
            title='Trip Plan Updated',
            is_internal_note=False,
            render_context={
                'record': self.form_id,
                'wizard': self,
                }
        )

        _logger.info(f"Plan for form {self.form_id.id} saved by organizer {self.env.user.name}.")
        return {'type': 'ir.actions.act_window_close'}

    def action_save_and_confirm(self):
        """
        Saves and finalizes the trip plan, updates the form status, and sends notifications
        for the employee to confirm the plan. This method now contains its own save logic
        to avoid calling action_save_plan and its side effects.
        """
        self.ensure_one()
        _logger.info(f"Attempting to confirm and finalize plan for form {self.form_id.id} by organizer {self.env.user.name}.")

        # 1. Re-parent attachments to grant access before linking them
        if self.employee_documents_ids:
            self.employee_documents_ids.write({
                'res_model': 'formio.form',
                'res_id': self.form_id.id
            })
        if self.organizer_attachments_ids:
            self.organizer_attachments_ids.write({
                'res_model': 'formio.form',
                'res_id': self.form_id.id
            })

        # 1. Save all plan data directly within this method
        plan_items_data = []
        for item in self.plan_item_ids:
            item_vals = {
                'item_type': item.item_type, 'custom_type': item.custom_type,
                'description': item.description, 'item_date': item.item_date.isoformat() if item.item_date else None,
                'direction': item.direction, 'from_location': item.from_location,
                'to_location': item.to_location, 'accommodation_type': item.accommodation_type,
                'nights': item.nights, 'carrier': item.carrier,
                'reference_number': item.reference_number, 'cost': item.cost,
                'payment_method': item.payment_method, 'cost_status': item.cost_status,
                'item_data_json': item.item_data_json, 'is_reimbursable': item.is_reimbursable,
                'notes': item.notes,
            }
            plan_items_data.append(item_vals)

        form_vals = {
            'organizer_trip_plan_details': self.organizer_trip_plan_details,
            'organizer_planned_cost': self.organizer_planned_cost,
            'organizer_attachments_ids': [(6, 0, self.organizer_attachments_ids.ids)],
            'employee_documents_ids': [(6, 0, self.employee_documents_ids.ids)],
            'structured_plan_items_json': json.dumps(plan_items_data, indent=4),
        }
        self.form_id.write(form_vals)
        _logger.info(f"Plan data for form {self.form_id.id} saved before confirmation.")

        # 2. Update the form state to 'organization_done' and then 'awaiting_trip_start'
        self.form_id.with_context(from_wizard=True, system_edit=True).write({
            'trip_status': 'organization_done',
            'organizer_confirmation_date': fields.Datetime.now(),
        })
        self.form_id.with_context(from_wizard=True, system_edit=True).write({
            'trip_status': 'awaiting_trip_start',
        })

        # --- Post Messages ---

        # 3. Post a PUBLIC message for the employee
        employee_partner = self.form_id.user_id.partner_id
        if employee_partner:
            public_plan_data = self._prepare_plan_details_structured(exclude_financials=True)

            message_body = self.env.ref('custom_business_trip_management.organizer_plan_summary')._render({
                'plan_data': public_plan_data,
                'organizer_name': self.form_id.organizer_id.name,
                'title': "Your travel plan has been finalized. Please review the details and documents below."
            }, engine='ir.qweb')
            
            self.form_id.with_context(from_wizard=True).message_post(
                body=message_body,
                partner_ids=[employee_partner.id],
                message_type='notification',
                subtype_xmlid='mail.mt_comment',
            )
            _logger.info(f"Posted public confirmation notification for employee on form {self.form_id.id}.")

        # 4. Post a CONFIDENTIAL message for the manager and organizer using the correct mechanism
        try:
            plan_details_structured = self._prepare_plan_details_structured(exclude_financials=False)
            
            # Use the 'organizer_plan_summary' template with a custom title
            message_body = self.env.ref('custom_business_trip_management.organizer_plan_summary')._render({
                'plan_data': plan_details_structured,
                'organizer_name': self.env.user.name,
                'title': f"The travel plan has been finalized and confirmed by {self.env.user.name}. Below are the details."
            }, engine='ir.qweb')

            if message_body:
                # Use the correct method to post a confidential message
                self.form_id.post_confidential_message(message_body)
                _logger.info(f"Successfully posted structured confidential plan summary for form {self.form_id.id}")

        except Exception as e:
            _logger.error(f"Failed to post structured confidential summary for form {self.form_id.id}: {e}", exc_info=True)
            # Fallback to plain text
            plan_details_str_confidential = self._prepare_plan_details_text(exclude_financials=False)
            if plan_details_str_confidential:
                fallback_message = "Trip Plan Finalized and Confirmed. (Template failed, showing raw text):\n\n" + plan_details_str_confidential
                self.form_id.post_confidential_message(fallback_message)
        
        _logger.info(f"Plan for form {self.form_id.id} finalized.")
        
        return {'type': 'ir.actions.act_window_close'}

    def _prepare_plan_details_structured(self, exclude_financials=False):
        """Create a structured dictionary of the travel plan for QWeb templates."""
        self.ensure_one()
        currency_symbol = self.currency_id.symbol if self.currency_id else ''
        
        plan_data = {
            'transport_items': [],
            'accommodation_items': [],
            'meals_items': [],
            'other_items': [],
            'total_manual_cost': None,
            'total_auto_cost': None,
            'organizer_notes': self.organizer_trip_plan_details,
            'currency_symbol': currency_symbol,
            'employee_documents': []
        }

        if not self.plan_item_ids:
            if self.manual_cost_entry and not exclude_financials:
                plan_data['total_manual_cost'] = self.manual_planned_cost
            return plan_data

        # Group items
        transport_items = self.plan_item_ids.filtered(lambda x: x.item_type.startswith('transport_'))
        accommodation_items = self.plan_item_ids.filtered(lambda x: x.item_type in ['accommodation', 'accommodation_airbnb'])
        meals_items = self.plan_item_ids.filtered(lambda x: x.item_type in ['meals', 'meals_per_diem'])
        other_items = self.plan_item_ids - transport_items - accommodation_items - meals_items

        # Process Transportation
        for item in sorted(transport_items, key=lambda x: (x.item_date, x.id)):
            route = f"{item.from_location} → {item.to_location}" if item.from_location and item.to_location else "No route specified"
            item_type_text = f"({item.custom_type})" if item.item_type == 'custom' and item.custom_type else f"({dict(item._fields['item_type'].selection).get(item.item_type, '')})"
            cost_text = f"{item.cost} {currency_symbol} ({dict(item._fields['cost_status'].selection).get(item.cost_status, '')}) - {dict(item._fields['payment_method'].selection).get(item.payment_method, '')}" if item.cost and not exclude_financials else ""
            
            details = [
                ("Route", route),
                ("Date", item.item_date.strftime('%Y-%m-%d')),
                ("Carrier", item.carrier),
                ("Ref", item.reference_number),
            ]
            if cost_text:
                details.append(("Cost", cost_text))

            plan_data['transport_items'].append({
                'description': f"{item.description} {item_type_text}",
                'details': [f"{label}: {val}" for label, val in details if val]
            })

        # Process Accommodation
        for item in sorted(accommodation_items, key=lambda x: (x.item_date, x.id)):
            nights_text = f"{item.nights} night{'s' if item.nights != 1 else ''}"
            accommodation_type = dict(item._fields['accommodation_type'].selection).get(item.accommodation_type, '')
            cost_text = f"{item.cost} {currency_symbol} ({dict(item._fields['cost_status'].selection).get(item.cost_status, '')}) - {dict(item._fields['payment_method'].selection).get(item.payment_method, '')}" if item.cost and not exclude_financials else ""

            details = [
                ("Duration", nights_text),
                ("Date", item.item_date.strftime('%Y-%m-%d')),
                ("Ref", item.reference_number),
            ]
            if cost_text:
                details.append(("Cost", cost_text))

            plan_data['accommodation_items'].append({
                'description': f"{item.description} ({accommodation_type})",
                'details': [f"{label}: {val}" for label, val in details if val]
            })

        # Process Meals
        for item in sorted(meals_items, key=lambda x: (x.item_date, x.id)):
            item_type = dict(item._fields['item_type'].selection).get(item.item_type, '')
            cost_text = f"{item.cost} {currency_symbol} ({dict(item._fields['cost_status'].selection).get(item.cost_status, '')}) - {dict(item._fields['payment_method'].selection).get(item.payment_method, '')}" if item.cost and not exclude_financials else ""

            details = [
                ("Date", item.item_date.strftime('%Y-%m-%d')),
            ]
            if cost_text:
                details.append(("Cost", cost_text))

            plan_data['meals_items'].append({
                'description': f"{item.description} ({item_type})",
                'details': [f"{label}: {val}" for label, val in details if val]
            })

        # Process Other Items
        for item in sorted(other_items, key=lambda x: (x.item_date, x.id)):
            item_type = item.custom_type if item.item_type == 'custom' and item.custom_type else dict(item._fields['item_type'].selection).get(item.item_type, '')
            cost_text = f"{item.cost} {currency_symbol} ({dict(item._fields['cost_status'].selection).get(item.cost_status, '')}) - {dict(item._fields['payment_method'].selection).get(item.payment_method, '')}" if item.cost and not exclude_financials else ""

            details = [
                ("Date", item.item_date.strftime('%Y-%m-%d')),
            ]
            if cost_text:
                details.append(("Cost", cost_text))

            plan_data['other_items'].append({
                'description': f"{item.description} ({item_type})",
                'details': [f"{label}: {val}" for label, val in details if val]
            })
            
        if not exclude_financials:
            if self.manual_cost_entry and self.manual_planned_cost:
                plan_data['total_manual_cost'] = self.manual_planned_cost
            elif self.organizer_planned_cost > 0:
                plan_data['total_auto_cost'] = self.organizer_planned_cost

        # Add employee documents for linking in the template
        for doc in self.employee_documents_ids:
            plan_data['employee_documents'].append({
                'name': doc.name,
                'url': f'/web/content/{doc.id}?download=true'
            })

        return plan_data

    def _try_parse_existing_plan(self, res, form):
        """Try to extract structured data from existing plan text"""
        # This method is deprecated - use _recreate_plan_items_from_form instead
        # Redirecting to the new method for backward compatibility
        return self._recreate_plan_items_from_form(res, form)
    
    # This method is misplaced and will be moved inside the BusinessTripOrganizerPlanWizard class.


class BusinessTripPlanLineItem(models.TransientModel):
    _name = 'business.trip.plan.line.item'
    _description = 'Business Trip Plan Line Item'
    _order = 'item_date, id'

    wizard_id = fields.Many2one('business.trip.organizer.plan.wizard', string='Plan Wizard', ondelete='cascade')
    
    # Type of travel arrangement
    item_type = fields.Selection([
        ('transport_air', 'Air Travel'),
        ('transport_train', 'Train Travel'),
        ('transport_bus', 'Bus Travel'),
        ('transport_car', 'Car Rental'),
        ('transport_taxi', 'Taxi/Local Transport'),
        ('transport_other', 'Other Transportation'),
        ('accommodation', 'Accommodation'),
        ('accommodation_airbnb', 'Airbnb/Rental'),
        ('meals', 'Meals'),
        ('meals_per_diem', 'Per Diem Allowance'),
        ('visa_fee', 'Visa Fee'),
        ('conference', 'Conference/Event Fee'),
        ('parking', 'Parking'),
        ('insurance', 'Travel Insurance'),
        ('internet', 'Internet/Communication'),
        ('translation', 'Translation Services'),
        ('entertainment', 'Entertainment/Activities'),
        ('shopping', 'Shopping Allowance'),
        ('currency_exchange', 'Currency Exchange Fee'),
        ('other', 'Other'),
        ('custom', 'Custom Item'),
    ], string='Item Type', required=True)
    
    # For custom item types
    custom_type = fields.Char(string='Custom Item Type', help="Define if item type is 'Custom'.")
    
    def edit_item(self):
        """Opens the form view of the line item for editing"""
        self.ensure_one()
        return {
            'name': _('Edit Travel Plan Item'),
            'type': 'ir.actions.act_window',
            'res_model': 'business.trip.plan.line.item',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }
    
    # JSON field for storing type-specific details
    item_data_json = fields.Text(string='Item Details (JSON)', help="Internal: Stores item-specific details.")
    
    # Widget fields for type-specific data - these are not stored directly but use JSON storage
    # Air Travel
    flight_number = fields.Char(string='Flight Number')
    flight_number_widget = fields.Char(string='Flight Number (Widget)',
                               compute='_compute_flight_number_widget',
                               inverse='_inverse_flight_number_widget')
    terminal_info_widget = fields.Char(string='Terminal Information',
                               compute='_compute_terminal_info_widget',
                               inverse='_inverse_terminal_info_widget')
    layovers_widget = fields.Char(string='Layovers',
                               compute='_compute_layovers_widget',
                               inverse='_inverse_layovers_widget')
    
    # Accommodation
    check_in_time_widget = fields.Char(string='Check-in Time',
                               compute='_compute_check_in_time_widget',
                               inverse='_inverse_check_in_time_widget')
    check_out_time_widget = fields.Char(string='Check-out Time',
                               compute='_compute_check_out_time_widget',
                               inverse='_inverse_check_out_time_widget')
    room_type_widget = fields.Char(string='Room Type',
                               compute='_compute_room_type_widget',
                               inverse='_inverse_room_type_widget')
    address_widget = fields.Char(string='Address',
                               compute='_compute_address_widget',
                               inverse='_inverse_address_widget')
    
    # Meals
    meal_type_widget = fields.Char(string='Meal Type',
                               compute='_compute_meal_type_widget',
                               inverse='_inverse_meal_type_widget')
    allowance_rate_widget = fields.Char(string='Per Diem Rate',
                               compute='_compute_allowance_rate_widget',
                               inverse='_inverse_allowance_rate_widget')
    
    # Conference/Event
    event_name_widget = fields.Char(string='Event Name',
                               compute='_compute_event_name_widget',
                               inverse='_inverse_event_name_widget')
    location_widget = fields.Char(string='Location',
                               compute='_compute_location_widget',
                               inverse='_inverse_location_widget')
    event_times_widget = fields.Char(string='Event Times',
                               compute='_compute_event_times_widget',
                               inverse='_inverse_event_times_widget')
    
    # Compute and inverse methods for widget fields
    @api.depends('item_data_json')
    def _compute_flight_number_widget(self):
        for record in self:
            record.flight_number_widget = record.get_item_data_value('flight_number', '')
            
    def _inverse_flight_number_widget(self):
        for record in self:
            record.update_item_data('flight_number', record.flight_number_widget)
            
    @api.depends('item_data_json')
    def _compute_terminal_info_widget(self):
        for record in self:
            record.terminal_info_widget = record.get_item_data_value('terminal_info', '')
            
    def _inverse_terminal_info_widget(self):
        for record in self:
            record.update_item_data('terminal_info', record.terminal_info_widget)
            
    @api.depends('item_data_json')
    def _compute_layovers_widget(self):
        for record in self:
            record.layovers_widget = record.get_item_data_value('layovers', '')
            
    def _inverse_layovers_widget(self):
        for record in self:
            record.update_item_data('layovers', record.layovers_widget)
            
    @api.depends('item_data_json')
    def _compute_check_in_time_widget(self):
        for record in self:
            record.check_in_time_widget = record.get_item_data_value('check_in_time', '')
            
    def _inverse_check_in_time_widget(self):
        for record in self:
            record.update_item_data('check_in_time', record.check_in_time_widget)
            
    @api.depends('item_data_json')
    def _compute_check_out_time_widget(self):
        for record in self:
            record.check_out_time_widget = record.get_item_data_value('check_out_time', '')
            
    def _inverse_check_out_time_widget(self):
        for record in self:
            record.update_item_data('check_out_time', record.check_out_time_widget)
            
    @api.depends('item_data_json')
    def _compute_room_type_widget(self):
        for record in self:
            record.room_type_widget = record.get_item_data_value('room_type', '')
            
    def _inverse_room_type_widget(self):
        for record in self:
            record.update_item_data('room_type', record.room_type_widget)
            
    @api.depends('item_data_json')
    def _compute_address_widget(self):
        for record in self:
            record.address_widget = record.get_item_data_value('address', '')
            
    def _inverse_address_widget(self):
        for record in self:
            record.update_item_data('address', record.address_widget)
            
    @api.depends('item_data_json')
    def _compute_meal_type_widget(self):
        for record in self:
            record.meal_type_widget = record.get_item_data_value('meal_type', '')
            
    def _inverse_meal_type_widget(self):
        for record in self:
            record.update_item_data('meal_type', record.meal_type_widget)
            
    @api.depends('item_data_json')
    def _compute_allowance_rate_widget(self):
        for record in self:
            record.allowance_rate_widget = record.get_item_data_value('allowance_rate', '')
            
    def _inverse_allowance_rate_widget(self):
        for record in self:
            record.update_item_data('allowance_rate', record.allowance_rate_widget)
            
    @api.depends('item_data_json')
    def _compute_event_name_widget(self):
        for record in self:
            record.event_name_widget = record.get_item_data_value('event_name', '')
            
    def _inverse_event_name_widget(self):
        for record in self:
            record.update_item_data('event_name', record.event_name_widget)
            
    @api.depends('item_data_json')
    def _compute_location_widget(self):
        for record in self:
            record.location_widget = record.get_item_data_value('location', '')
            
    def _inverse_location_widget(self):
        for record in self:
            record.update_item_data('location', record.location_widget)
            
    @api.depends('item_data_json')
    def _compute_event_times_widget(self):
        for record in self:
            record.event_times_widget = record.get_item_data_value('event_times', '')
            
    def _inverse_event_times_widget(self):
        for record in self:
            record.update_item_data('event_times', record.event_times_widget)
    
    # Direction for transportation
    direction = fields.Selection([
        ('outbound', 'Outbound'),
        ('inbound', 'Return'),
        ('local', 'Local'),
        ('transit', 'Transit/Connection'),
        ('round_trip', 'Round Trip'),
        ('na', 'N/A')
    ], string='Direction', default='na')
    
    # Details
    description = fields.Char(string='Description', required=True)
    item_date = fields.Date(string='Date', required=True)
    
    # Transportation details
    from_location = fields.Char(string='From')
    to_location = fields.Char(string='To')
    carrier = fields.Char(string='Carrier/Provider', help="Airline, train, or service provider.")
    reference_number = fields.Char(string='Reference/Booking Number', help="Booking/ticket reference.")
    departure_time = fields.Float(string='Departure Time', help="Departure time (e.g., 9.5 for 9:30).")
    arrival_time = fields.Float(string='Arrival Time', help="Arrival time (e.g., 15.5 for 15:30).")
    travel_class = fields.Selection([
        ('economy', 'Economy'),
        ('business', 'Business'),
        ('first', 'First Class'),
        ('premium', 'Premium Economy'),
        ('standard', 'Standard'),
        ('other', 'Other')
    ], string='Travel Class')
    
    # Accommodation details
    nights = fields.Integer(string='Nights', default=1)
    accommodation_type = fields.Selection([
        ('hotel', 'Hotel'),
        ('airbnb', 'Airbnb/Vacation Rental'),
        ('corporate', 'Corporate Housing'),
        ('hostel', 'Hostel'),
        ('guesthouse', 'Guesthouse'),
        ('relatives', 'Relatives/Friends'),
        ('other', 'Other')
    ], string='Accommodation Type')
    
    # Cost details
    cost = fields.Float(string='Cost', required=False)
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id', readonly=True)
    cost_status = fields.Selection([
        ('estimated', 'Estimated'),
        ('quoted', 'Quoted'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
        ('to_reimburse', 'To Reimburse')
    ], string='Cost Status', default='estimated')
    
    # Additional details
    is_reimbursable = fields.Boolean(string='Reimbursable', default=True, 
                                    help="Is this cost reimbursable to employee?")
    payment_method = fields.Selection([
        ('company', 'Company Paid'),
        ('employee', 'Employee Paid (Reimbursable)'),
        ('cash_advance', 'Cash Advance'),
        ('per_diem', 'Per Diem'),
        ('company_card', 'Company Card')
    ], string='Payment Method', default='company')
    
    # Helper fields
    attachment_ids = fields.Many2many('ir.attachment', 
                                     'business_trip_plan_line_attachment_rel',
                                     'line_id', 'attachment_id',
                                     string='Attachments')
    notes = fields.Text(string='Notes')
    
    # Methods for handling type-specific data
    def get_item_data(self):
        """Get item data from JSON field as dictionary"""
        self.ensure_one()
        if not self.item_data_json:
            return {}
        try:
            return json.loads(self.item_data_json)
        except (ValueError, TypeError):
            _logger.error(f"Error parsing item_data_json for record {self.id}")
            return {}
            
    def set_item_data(self, data_dict):
        """Set item data dictionary to JSON field"""
        self.ensure_one()
        if data_dict is None:
            self.item_data_json = '{}'
        else:
            self.item_data_json = json.dumps(data_dict)
            
    def update_item_data(self, key, value):
        """Update a single key in the item data JSON"""
        self.ensure_one()
        data = self.get_item_data()
        # Only remove the key if value is None, but keep empty strings
        if value is None and key in data:
            del data[key]
        else:
            # Store any value, including empty strings
            data[key] = value
        self.set_item_data(data)
        # Force the computed fields to update
        self.invalidate_cache()
            
    def get_item_data_value(self, key, default=None):
        """Get a value from the item data JSON"""
        data = self.get_item_data()
        # Return the value if the key exists, even if it's empty
        if key in data:
            return data[key]
        return default
    
    @api.onchange('item_type')
    def _onchange_item_type(self):
        # Set appropriate default description based on type
        if self.item_type == 'transport_air':
            self.description = 'Flight'
            self.direction = 'outbound'
        elif self.item_type == 'transport_train':
            self.description = 'Train'
            self.direction = 'outbound'
        elif self.item_type == 'transport_bus':
            self.description = 'Bus'
            self.direction = 'outbound'
        elif self.item_type == 'transport_car':
            self.description = 'Car Rental'
            self.direction = 'na'
        elif self.item_type == 'transport_taxi':
            self.description = 'Taxi'
            self.direction = 'local'
        elif self.item_type == 'transport_other':
            self.description = 'Other Transportation'
            self.direction = 'na'
        elif self.item_type == 'accommodation':
            self.description = 'Hotel'
            self.accommodation_type = 'hotel'
            self.direction = 'na'
        elif self.item_type == 'accommodation_airbnb':
            self.description = 'Airbnb/Rental'
            self.accommodation_type = 'airbnb'
            self.direction = 'na'
        elif self.item_type == 'meals':
            self.description = 'Meals'
            self.direction = 'na'
        elif self.item_type == 'meals_per_diem':
            self.description = 'Per Diem Allowance'
            self.direction = 'na'
        elif self.item_type == 'visa_fee':
            self.description = 'Visa Fee'
            self.direction = 'na'
        elif self.item_type == 'conference':
            self.description = 'Conference Fee'
            self.direction = 'na'
        elif self.item_type == 'parking':
            self.description = 'Parking Fee'
            self.direction = 'na'
        elif self.item_type == 'insurance':
            self.description = 'Travel Insurance'
            self.direction = 'na'
        elif self.item_type == 'internet':
            self.description = 'Internet/Communication'
            self.direction = 'na'
        elif self.item_type == 'translation':
            self.description = 'Translation Services'
            self.direction = 'na'
        elif self.item_type == 'entertainment':
            self.description = 'Entertainment/Activities'
            self.direction = 'na'
        elif self.item_type == 'shopping':
            self.description = 'Shopping Allowance'
            self.direction = 'na'
        elif self.item_type == 'currency_exchange':
            self.description = 'Currency Exchange Fee'
            self.direction = 'na'
        elif self.item_type == 'other':
            self.description = 'Other Expense'
            self.direction = 'na'
        elif self.item_type == 'custom':
            self.description = 'Custom Item'
            self.direction = 'na'
            
    @api.onchange('direction')
    def _onchange_direction(self):
        if self.direction == 'inbound' and self.item_type in ['transport_air', 'transport_train', 'transport_bus']:
            # Swap from/to for return journeys if they exist
            if self.from_location and self.to_location:
                self.from_location, self.to_location = self.to_location, self.from_location

    def confirm_assignment_and_budget(self, manager_max_budget, organizer_id, manager_comments=None, internal_notes=None):
        """Confirm and assign budget and organizer by manager"""
        self.ensure_one()
        
        if not self.env.user.has_group('hr.group_hr_manager') and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only managers or system administrators can assign organizers and budgets.")
            
        if manager_max_budget <= 0:
            raise ValidationError("Maximum budget must be a positive value.")
            
        # Check if anything significant has changed
        organizer_changed = self.organizer_id.id != organizer_id
        budget_changed = self.manager_max_budget != manager_max_budget
        status_changed = self.trip_status != 'pending_organization'
        
        # If nothing has changed, just update comments if provided and return
        if not organizer_changed and not budget_changed and not status_changed:
            if manager_comments and manager_comments != self.manager_comments:
                self.with_context(system_edit=True).write({'manager_comments': manager_comments})
            return True
            
        # Update form with budget and organizer
        vals = {
            'manager_max_budget': manager_max_budget,
            'organizer_id': organizer_id,
            'trip_status': 'pending_organization',  # Move to next stage: organization phase
            'manager_approval_date': fields.Datetime.now(),
            # Clear the temporary budget as we're now setting the official budget
            'temp_manager_max_budget': 0.0,
        }
        
        # Update manager comments if provided
        if manager_comments:
            vals['manager_comments'] = manager_comments
            
        self.with_context(system_edit=True).write(vals)
        
        # Subscribe the organizer to the record
        organizer = self.env['res.users'].browse(organizer_id)
        if organizer and organizer.partner_id:
            self.message_subscribe(partner_ids=[organizer.partner_id.id])
            
        # Share form with organizer (to fix access issue)
        # Create share.formio.form record if model exists
        try:
            self.env['share.formio.form'].sudo().create({
                'share_user_id': organizer_id,
                'formio_form_id': self.id,
            })
            _logger.info(f"Form {self.id} shared with organizer {organizer_id}")
        except Exception as e:
            _logger.warning(f"Could not share form with organizer: {e}. This is expected if 'share.formio.form' model doesn't exist.")
        
        # Send confidential message to organizer
        # Create notification style for success message
        success_style = "font-weight: bold; color: #155724; background-color: #d4edda; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-bottom: 1px;"
        
        # Build message based on what changed
        message_parts = []
        budget_message = ""
        
        # Always mention the confirmation since we're moving to pending_organization status
        message_parts.append("You have been officially assigned as the trip organizer and the budget has been confirmed.")
        
        # If budget was changed from a temporary value, mention this
        if self.temp_manager_max_budget > 0 and self.temp_manager_max_budget != manager_max_budget:
            budget_message = f"The budget has been updated from the preliminary {self.temp_manager_max_budget} to {manager_max_budget} {self.currency_id.symbol if self.currency_id else ''}."
            message_parts.append(budget_message)
        
        confidential_msg = f"""
                            <strong>Confidential Trip Information</strong><br/>
                            <div style=\"{success_style}\">Confirmed Assignment</div><br/>
                            <p>{'<br/>'.join(message_parts)}</p>
                            <ul>
                                <li>Allocated Budget: {manager_max_budget} {self.currency_id.symbol if self.currency_id else ''}</li>
                            </ul>
                            <p>The trip has now moved to the <strong>Pending Organization</strong> phase. You can proceed with detailed planning.</p>
                            """
        if internal_notes:
            confidential_msg += f"<strong>Internal Notes:</strong><br/>{internal_notes}"
            
        # Send confidential message between manager and organizer
        self.post_confidential_message(
            message=confidential_msg,
            recipient_ids=[organizer_id]
        ) 

    def post_confidential_message(self, message, recipient_ids=None):
        """
        Posts a confidential message visible only to specified recipients (and current user).
        If recipient_ids is None or empty, message is visible only to current user (author).
        """
        self.ensure_one()
        
        # Ensure current user (author) is always a recipient implicitly
        # Note: Odoo's mail.message automatically makes the author a follower
        # and if no explicit partner_ids are given, it often defaults to followers.
        # However, to be certain for confidential messages, we handle recipients carefully.

        partner_ids_to_notify = []
        if recipient_ids:
            # Convert user IDs to partner IDs
            valid_user_ids = [uid for uid in recipient_ids if isinstance(uid, int)]
            partners = self.env['res.users'].sudo().browse(valid_user_ids).mapped('partner_id')
            partner_ids_to_notify.extend(partners.ids)
            
        # Add current user's partner ID if not already included (e.g., if sending to others)
        # current_user_partner_id = self.env.user.partner_id.id
        # if current_user_partner_id not in partner_ids_to_notify:
        #    partner_ids_to_notify.append(current_user_partner_id)

        if not partner_ids_to_notify:
            _logger.info(f"Confidential message for form {self.id} has no explicit recipients other than author.")
            # If no recipients, it might become a note to self or not visible as intended.
            # Forcing a specific subtype or channel might be needed depending on desired behavior.
            # For now, we proceed, and Odoo will handle visibility based on followers.

        # Create a message with specific subtype if needed, or use default 'mail.mt_comment'
        # Ensure it's marked as private or use specific channels if formio has such features.
        # For now, relying on explicit partner_ids for message_post.
        
        # Check if partners exist before posting
        if not partner_ids_to_notify:
             _logger.warning(f"Attempted to post a confidential message for form {self.id} but no valid recipient partner IDs were found (original user IDs: {recipient_ids}). Message will only be visible to author and existing followers.")
             # Post as a note if no other recipients, so at least author sees it linked to record.
             self.message_post(
                body=message,
                message_type='comment', # 'notification' or 'comment'
                subtype_xmlid='mail.mt_note', # Ensures it's treated as an internal note
             )
        else:
            self.message_post(
                body=message,
                partner_ids=list(set(partner_ids_to_notify)), # Ensure unique partner IDs
                message_type='notification', 
                subtype_xmlid='mail.mt_comment', # Or a custom subtype for confidential messages
            )
        _logger.info(f"Confidential message posted on form {self.id} for partners: {partner_ids_to_notify}")


# These classes are commented out as they were temporary placeholders
# class BusinessTripAccommodationDetailsWizard(models.TransientModel):
#     _name = 'business.trip.accommodation.details.wizard'
#     _description = 'Temporary Placeholder for old Accommodation Details Wizard'
#     
#     # Add a placeholder for the field that had the problematic selection
#     # The selection custom_business_trip_management.selection__business_trip_accommodation_details_wizard__room_type__other
#     # implies a field named 'room_type'
#     room_type = fields.Selection([
#         ('hotel', 'Hotel'),
#         ('airbnb', 'Airbnb/Vacation Rental'),
#         ('corporate', 'Corporate Housing'),
#         ('hostel', 'Hostel'),
#         ('guesthouse', 'Guesthouse'),
#         ('relatives', 'Relatives/Friends'),
#         ('other', 'Other')
#     ], string="Room Type")
#     
#     # Add accommodation_type field as it appears in the logs
#     accommodation_type = fields.Selection([
#         ('hotel', 'Hotel'),
#         ('airbnb', 'Airbnb/Vacation Rental'),
#         ('corporate', 'Corporate Housing'),
#         ('hostel', 'Hostel'),
#         ('guesthouse', 'Guesthouse'),
#         ('relatives', 'Relatives/Friends'),
#         ('other', 'Other')
#     ], string="Accommodation Type")
    def _try_parse_existing_plan(self, res, form):
        """Try to extract structured data from existing plan text"""
        # This method is deprecated - use _recreate_plan_items_from_form instead
        # Redirecting to the new method for backward compatibility
        return self._recreate_plan_items_from_form(res, form)


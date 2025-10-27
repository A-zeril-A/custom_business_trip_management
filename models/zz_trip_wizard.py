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
    
    trip_id = fields.Many2one('business.trip', string='Trip', required=True)
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
        trip_id = self.env.context.get('active_id')
        if trip_id:
            trip = self.env['business.trip'].browse(trip_id)
            
            # Check if it's already marked as an hourly trip or infer from dates
            is_hourly_trip = trip.is_hourly_trip
            if not is_hourly_trip and trip.travel_start_date and trip.travel_end_date:
                if trip.travel_start_date == trip.travel_end_date:
                    is_hourly_trip = True
                
            # Set default times for hourly trips
            travel_start_time = 9.0  # Default to 9:00 AM
            travel_end_time = 17.0   # Default to 5:00 PM
            
            # If the form already has time information, use it
            if trip.travel_start_time:
                travel_start_time = trip.travel_start_time
            if trip.travel_end_time:
                travel_end_time = trip.travel_end_time
            
            # If no existing times but we have duration for hourly trip, calculate end time
            elif is_hourly_trip and trip.travel_duration and trip.travel_duration > 0:
                # For hourly trips, travel_duration is in hours
                travel_end_time = travel_start_time + trip.travel_duration
                if travel_end_time >= 24:
                    travel_end_time = 23.99  # Cap at 11:59 PM
            
            res.update({
                'trip_id': trip_id,
                'destination': trip.destination,
                'purpose': trip.purpose,
                'travel_start_date': trip.travel_start_date,
                'travel_end_date': trip.travel_end_date,
                'currency_id': trip.currency_id.id,
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
        _logger.info(f"WIZARD SAVE: Attempting to write to trip {self.trip_id.id} with vals: {vals}")
        self.trip_id.with_context(from_wizard=True, system_edit=True).write(vals)
        _logger.info(f"WIZARD SAVE: Successfully wrote to trip {self.trip_id.id}")

        # Additionally, we need to update the corresponding business.trip.data record
        # for the fields that are now solely managed there.
        btd_record = self.env['business.trip.data'].search([('trip_id', '=', self.trip_id.id)], limit=1)
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
            _logger.warning(f"WIZARD SAVE: No BTD record found for trip {self.trip_id.id} to update duration/hourly info.")

        return {'type': 'ir.actions.act_window_close'}


class CostEstimationWizard(models.TransientModel):
    """Wizard for cost estimation through a popup"""
    _name = 'business.trip.cost.wizard'
    _description = 'Business Trip Cost Estimation Wizard'
    
    trip_id = fields.Many2one('business.trip', string='Trip', required=True)
    expected_cost = fields.Float(string='Expected Cost', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    estimation_comments = fields.Text(string='Estimation Notes')
    
    @api.model
    def default_get(self, fields_list):
        """Fetch values from the related trip form"""
        res = super(CostEstimationWizard, self).default_get(fields_list)
        trip_id = self.env.context.get('active_id')
        if trip_id:
            trip = self.env['business.trip'].browse(trip_id)
            res.update({
                'trip_id': trip_id,
                'expected_cost': trip.expected_cost,
                'currency_id': trip.currency_id.id,
                'estimation_comments': trip.estimation_comments,
            })
        return res
    
    def action_save(self):
        """Save cost estimation to the trip form"""
        self.ensure_one()
        
        # Check if user has permission to estimate cost (only Travel Approver or finance)
        if not self.env.user.has_group('hr.group_hr_manager') and not self.env.user.has_group('account.group_account_manager') and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only Travel Approvers or finance personnel can estimate costs.")
            
        # Validate cost
        if self.expected_cost <= 0:
            raise ValidationError("Expected cost must be greater than zero.")
        
        # Update the form
        vals = {
            'expected_cost': self.expected_cost,
            'currency_id': self.currency_id.id,
            'estimation_comments': self.estimation_comments,
        }
        
        # If the user is a Travel Approver/finance and the trip is in submitted status, 
        # also update the status and record the estimation
        trip = self.trip_id
        if trip.trip_status == 'submitted':
            vals.update({
                'trip_status': 'cost_estimated',
                'estimated_by': self.env.user.id,
                'estimation_date': fields.Datetime.now(),
            })
            
            # Notify the user
            if trip.user_id:
                trip.message_post(
                    body=f"Cost estimation has been completed for your trip request.",
                    partner_ids=[trip.user_id.partner_id.id]
                )
        
        trip.write(vals)
        return {'type': 'ir.actions.act_window_close'}


class ExpenseSubmissionWizard(models.TransientModel):
    _name = 'business.trip.expense.submission.wizard'
    _description = 'Business Trip Expense Submission Wizard'

    trip_id = fields.Many2one('business.trip', string='Trip', required=True, readonly=True)
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
    
    # Fields for upload status tracking
    is_uploading = fields.Boolean(string='Upload in Progress', default=False, help="True when file upload is in progress")
    can_submit = fields.Boolean(string='Can Submit', compute='_compute_can_submit', help="True when form is ready for submission")
    is_resubmission = fields.Boolean(string='Is Resubmission', default=False, help="True when this is a resubmission after recall")
    requires_new_attachments = fields.Boolean(string='Requires New Attachments', default=False, help="True when new attachments must be uploaded")

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
    
    @api.depends('has_no_expenses', 'expense_total', 'expense_attachment_ids', 'is_uploading', 'expense_comments', 'requires_new_attachments', 'is_resubmission')
    def _compute_can_submit(self):
        """Compute whether the form can be submitted with comprehensive validation"""
        for record in self:
            # Rule 1: Never submit while uploading
            if record.is_uploading:
                record.can_submit = False
                continue
                
            # Rule 2: No expenses case - always allowed
            if record.has_no_expenses:
                record.can_submit = True
                continue
                
            # Rule 3: Must have positive expense amount
            if record.expense_total <= 0:
                record.can_submit = False
                continue
                
            # Rule 4: If this requires new attachments (resubmission after recall)
            if record.requires_new_attachments:
                # For resubmissions, MUST have new attachments - comments alone are not enough
                has_attachments = len(record.expense_attachment_ids) > 0
                if not has_attachments:
                    record.can_submit = False
                    continue
                else:
                    record.can_submit = True
                    continue
            
            # Rule 5: For first-time submissions, attachments OR comments are sufficient
            has_attachments = len(record.expense_attachment_ids) > 0
            has_comments = bool(record.expense_comments and record.expense_comments.strip())
            
            if record.expense_total > 0 and not has_attachments and not has_comments:
                record.can_submit = False
            else:
                record.can_submit = True

    @api.model
    def default_get(self, fields_list):
        res = super(ExpenseSubmissionWizard, self).default_get(fields_list)
        trip_id = self.env.context.get('active_id')
        if trip_id:
            trip = self.env['business.trip'].browse(trip_id)
            
            # Determine if this is a resubmission (trip was previously expense_submitted and then recalled)
            is_resubmission = bool(
                trip.expense_total > 0 or 
                trip.expense_comments or 
                trip.expense_attachment_ids or
                trip.trip_status in ('expense_returned', 'expense_rejected')
            )
            
            res.update({
                'trip_id': trip_id,
                'currency_id': trip.currency_id.id,
                # Pre-fill with existing values if any, useful for re-submission after return
                'expense_total': trip.expense_total,
                'expense_comments': trip.expense_comments,
                # Don't pre-fill attachments - force user to re-upload for better validation
                # 'expense_attachment_ids': [(6, 0, trip.expense_attachment_ids.ids)],
                # Set has_no_expenses based on existing data
                'has_no_expenses': trip.expense_total == 0,
                # Set resubmission flags
                'is_resubmission': is_resubmission,
                'requires_new_attachments': is_resubmission and trip.expense_total > 0,
            })
        return res

    def action_apply(self):
        self.ensure_one()
        
        # Check if upload is in progress
        if self.is_uploading:
            raise ValidationError("Please wait for the file upload to complete before submitting.")
        
        # Validate expenses based on the no expenses checkbox
        if self.has_no_expenses:
            # If no expenses, force expense_total to 0
            self.expense_total = 0.0
        else:
            # If submitting expenses, validate the amount
            if self.expense_total <= 0:
                raise ValidationError("Please enter the total actual cost of your trip expenses.")
            
            # If expense amount is greater than zero, require attachments OR comments
            if self.expense_total > 0 and not self.expense_attachment_ids and not self.expense_comments:
                raise ValidationError("Please attach receipt(s) for your expenses OR add a comment explaining the expenses.")

        # Check if form is in the correct state for expense submission
        if self.trip_id.trip_status not in ['completed_waiting_expense', 'expense_returned', 'in_progress', 'awaiting_trip_start']:
            raise ValidationError(f"You can only submit expenses when the trip is in 'Waiting for Expense Submission' or 'Expense Returned' state. Current state: {self.trip_id.trip_status}")

        # Re-parent attachments to the business trip record to ensure access rights
        if self.expense_attachment_ids:
            self.expense_attachment_ids.write({
                'res_model': 'business.trip',
                'res_id': self.trip_id.id,
            })

        # Store previous value for comparison
        old_expense_total = self.trip_id.expense_total
        
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
        self.trip_id.with_context(system_edit=True).write(vals)
        
        # Call the submission action with context indicating if this is a no-expense submission
        return self.trip_id.with_context(no_expenses_submission=self.has_no_expenses).action_submit_expenses()


class ReturnCommentWizard(models.TransientModel):
    _name = 'business.trip.return.comment.wizard'
    _description = 'Business Trip Return Comment Wizard'

    trip_id = fields.Many2one('business.trip', string='Trip', required=True, readonly=True)
    return_comments = fields.Text(string='Return Comments', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super(ReturnCommentWizard, self).default_get(fields_list)
        trip_id = self.env.context.get('active_id')
        if trip_id:
            trip = self.env['business.trip'].browse(trip_id)
            res.update({
                'trip_id': trip_id,
                'return_comments': trip.manager_comments, # Pre-fill with Travel Approver comments
            })
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.return_comments:
            raise ValidationError("Return comments are required.")

        # Check if form is in the correct state for returning with comments
        if self.trip_id.trip_status not in ['submitted', 'cost_estimated']:
            raise ValidationError("You can only return requests that have been submitted or had costs estimated.")

        # Check if user has permission (Travel Approver/finance/system)
        if not (self.env.user.has_group('hr.group_hr_manager') or \
                self.env.user.has_group('account.group_account_manager') or \
                self.env.user.has_group('base.group_system')):
            raise ValidationError("Only Travel Approvers, finance, or system administrators can return the request with comments.")

        # Update both return_comments (for legacy support) and manager_comments
        self.trip_id.write({
            'return_comments': self.return_comments,
            'manager_comments': self.return_comments,  # Also set manager_comments for proper display
        })
        
        # Call the original action_return_with_comment on the form 
        return self.trip_id.action_return_with_comment() 


class RejectionWizard(models.TransientModel):
    _name = 'business.trip.rejection.wizard'
    _description = 'Business Trip Rejection Wizard'

    trip_id = fields.Many2one('business.trip', string='Trip', required=True, readonly=True)
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
        trip_id = self.env.context.get('active_id')
        if trip_id:
            trip = self.env['business.trip'].browse(trip_id)
            res.update({
                'trip_id': trip_id,
                'rejection_reason': trip.rejection_reason,
                'rejection_comment': trip.rejection_comment,
            })
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.rejection_reason:
            raise ValidationError("Rejection reason is required.")

        # Check if form is in the correct state for rejection
        if self.trip_id.trip_status not in ['submitted', 'cost_estimated']:
            raise ValidationError("You can only reject requests that have been submitted or had costs estimated.")

        # Check if user has permission (Travel Approver/system)
        if not (self.env.user.has_group('hr.group_hr_manager') or \
                self.env.user.has_group('base.group_system')):
            raise ValidationError("Only Travel Approvers or system administrators can reject the request.")

        self.trip_id.write({
            'rejection_reason': self.rejection_reason,
            'rejection_comment': self.rejection_comment,
            # 'rejected_by': self.env.user.id, # This will be set in action_reject
            # 'rejection_date': fields.Datetime.now(), # This will be set in action_reject
        })
        
        # Call the original action_reject on the form 
        return self.trip_id.action_reject() 


class ExpenseReturnCommentWizard(models.TransientModel):
    _name = 'business.trip.expense.return.comment.wizard'
    _description = 'Business Trip Expense Return Comment Wizard'

    trip_id = fields.Many2one('business.trip', string='Trip', required=True, readonly=True)
    expense_return_comments = fields.Text(string='Expense Return Comments', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super(ExpenseReturnCommentWizard, self).default_get(fields_list)
        trip_id = self.env.context.get('active_id')
        if trip_id:
            trip = self.env['business.trip'].browse(trip_id)
            res.update({
                'trip_id': trip_id,
                'expense_return_comments': trip.expense_return_comments, # Pre-fill if already has comments
            })
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.expense_return_comments:
            raise ValidationError("Expense return comments are required.")

        # Check if form is in the correct state for returning expenses
        if self.trip_id.trip_status != 'expense_submitted':
            raise ValidationError("You can only return expenses that have been submitted for review.")

        # Check if user has permission (finance/system/organizer)
        if not (self.env.user.has_group('account.group_account_manager') or \
                self.env.user.has_group('base.group_system') or \
                (self.trip_id.organizer_id and self.env.user.id == self.trip_id.organizer_id.id)):
            raise ValidationError("Only the trip organizer, finance personnel, or system administrators can return expenses.")

        # Save the comments before calling the action_return_expenses - using system_edit context
        self.trip_id.with_context(system_edit=True).write({
            'expense_return_comments': self.expense_return_comments,
        })
        
        # Call the original action_return_expenses on the form 
        return self.trip_id.action_return_expenses()


class BusinessTripAssignOrganizerWizard(models.TransientModel):
    _name = 'business.trip.assign.organizer.wizard'
    _description = 'Assign Organizer and Budget for Business Trip'

    trip_id = fields.Many2one('business.trip', string='Trip', readonly=True, required=True)
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

    @api.model
    def default_get(self, fields_list):
        res = super(BusinessTripAssignOrganizerWizard, self).default_get(fields_list)
        if self.env.context.get('default_trip_id'):
            trip = self.env['business.trip'].browse(self.env.context.get('default_trip_id'))
            if trip:
                res['trip_id'] = trip.id
                
                # Fetch manager_id and currency_id from the form
                if trip.manager_id:
                    res['manager_id'] = trip.manager_id.id
                if trip.currency_id:
                    res['currency_id'] = trip.currency_id.id
                
                if trip.organizer_id:
                    res['organizer_id'] = trip.organizer_id.id
                    
                # Logic for pre-filling budget in the wizard:
                # 1. Prioritize the unconfirmed temporary budget saved on the form.
                # 2. If not present, use the last confirmed budget from the form.
                # 3. Otherwise, it defaults to 0.0.
                if trip.temp_manager_max_budget and trip.temp_manager_max_budget > 0:
                    res['manager_max_budget'] = trip.temp_manager_max_budget
                elif trip.manager_max_budget and trip.manager_max_budget > 0:
                    res['manager_max_budget'] = trip.manager_max_budget
                else:
                    res['manager_max_budget'] = 0.0 # Default to 0 if no budget set
                    
        return res
        
    # Removed _compute_temp_budget as the wizard's own temp_manager_max_budget field was removed in last attempt and is not being re-added.

    def action_assign_organizer_and_budget(self):
        """Save and confirm organizer assignment with budget"""
        self.ensure_one()
        if not self.trip_id:
            raise UserError("Business Trip Request is not linked.")
        if not self.organizer_id:
            raise UserError("Trip Organizer must be selected for final confirmation.")
        if self.manager_max_budget <= 0:
            raise UserError("Maximum budget must be a positive value for final confirmation. If you want to save without setting a budget, use the 'Save (Preliminary)' button instead.")

        # Check if anything significant has changed
        organizer_changed = self.trip_id.organizer_id.id != self.organizer_id.id
        budget_changed = self.trip_id.manager_max_budget != self.manager_max_budget
        
        # If nothing has changed, just close the wizard without any updates or messages
        if not organizer_changed and not budget_changed:
            return {'type': 'ir.actions.act_window_close'}

        # Values from the wizard are sent to the confirm_assignment_and_budget method in formio.form
        # and that method is responsible for writing the values to the form and sending the necessary messages.
        self.trip_id.confirm_assignment_and_budget(
            manager_max_budget=self.manager_max_budget,
            organizer_id=self.organizer_id.id,
            manager_comments=self.trip_id.manager_comments, # Send the general manager comments that were previously on the form or changed in the wizard
            internal_notes=self.assignment_comments # Wizard comments are sent as internal notes for the organizer
        )
        
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_save_organizer_only(self):
        """Save organizer assignment without requiring budget (for preliminary assignment)"""
        self.ensure_one()
        if not self.trip_id:
            raise UserError("Business Trip Request is not linked.")
        if not self.organizer_id:
            raise UserError("Trip Organizer must be selected.")
            
        organizer_changed = self.trip_id.organizer_id.id != self.organizer_id.id
        
        # Get the budget value from the wizard field
        wizard_budget_input = self.manager_max_budget or 0.0
        
        # Get the current temporary budget stored on the main form
        temp_budget_on_form = self.trip_id.temp_manager_max_budget or 0.0
        
        temp_budget_changed = temp_budget_on_form != wizard_budget_input
        
        if not organizer_changed and not temp_budget_changed:
            _logger.info("action_save_organizer_only: No changes to organizer or temporary budget. Closing wizard.")
            return {'type': 'ir.actions.act_window_close'}
            
        if self.organizer_id and self.organizer_id.partner_id:
            self.trip_id.message_subscribe(partner_ids=[self.organizer_id.partner_id.id])
            
        # Modified by A_zeril_A, 2025-10-20: Removed formio dependency
        # try:
        #     self.env['share.formio.form'].sudo().create({
        #         'share_user_id': self.organizer_id.id,
        #         'formio_form_id': self.trip_id.id,
        #     })
        # except Exception as e:
        #     _logger.warning(f"Could not share form with organizer: {e}. This is expected if 'share.formio.form' model doesn't exist.")
            
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
        
        _logger.info(f"action_save_organizer_only: Writing to form {self.trip_id.id}: {form_vals_to_write}")
        self.trip_id.with_context(system_edit=True).write(form_vals_to_write)
        
        attention_style = "font-weight: bold; color: #856404; background-color: #fff3cd; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-bottom: 1px;"
        
        confidential_message_parts = []
        chatter_message_parts = []

        if organizer_changed:
            confidential_message_parts.append(f"You have been preliminarily assigned as the organizer for this business trip.")
            chatter_message_parts.append(f"Organizer {self.organizer_id.name} preliminarily assigned/updated.")
        
        if temp_budget_changed:
            if wizard_budget_input > 0:
                budget_text = f"{wizard_budget_input} {self.trip_id.currency_id.symbol if self.trip_id.currency_id else ''}"
                confidential_message_parts.append(f"A preliminary budget of {budget_text} has been noted (not finalized).")
                chatter_message_parts.append(f"A preliminary budget was noted by the manager (not finalized).")
            elif temp_budget_on_form > 0: # Wizard budget is 0, but there was a temp budget previously
                old_budget_text = f"{temp_budget_on_form} {self.trip_id.currency_id.symbol if self.trip_id.currency_id else ''}"
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
            if self.trip_id.manager_id and self.env.user.id != self.trip_id.manager_id.id:
                recipient_ids_confidential.append(self.trip_id.manager_id.id)
                
            self.trip_id.post_confidential_message(
                message=confidential_msg,
                recipient_ids=list(set(recipient_ids_confidential))
            )
        
        if chatter_message_parts:
            final_chatter_message = ' '.join(chatter_message_parts)
            _logger.info(f"action_save_organizer_only: Posting chatter message to form {self.trip_id.id}: {final_chatter_message}")
            self.trip_id.message_post(
                body=final_chatter_message,
                subtype_xmlid='mail.mt_note'
            )
            
        return {'type': 'ir.actions.act_window_close'}


class BusinessTripProjectSelectionWizard(models.TransientModel):
    """Wizard for selecting project for standalone business trips"""
    _name = 'business.trip.project.selection.wizard'
    _description = 'Business Trip Project Selection Wizard'
    
    project_id = fields.Many2one(
        'project.project', 
        string='Select Project', 
        required=False,  # Will be validated in the action method
        help="Select the project for which this business trip is being requested"
    )
    
    @api.model
    def default_get(self, fields_list):
        """Set domain for project selection"""
        res = super().default_get(fields_list)
        return res
    
    def action_create_trip_with_project(self):
        """Create standalone business trip with selected project"""
        self.ensure_one()
        if not self.project_id:
            raise UserError("Please select a project.")
        
        # Create the business trip
        current_user = self.env.user
        business_trip = self.env['business.trip'].sudo().create({
            'user_id': current_user.id,
        })
        
        # Create a task in the selected project with a unique name
        task_name = f"Business Trip: {business_trip.name} - {current_user.name}"
        task = self.env['project.task'].sudo().create({
            'name': task_name,
            'project_id': self.project_id.id,
            'user_ids': [(6, 0, [current_user.id])],
            'planned_hours': 1,
            'description': f"Task created for business trip request: {business_trip.name}"
        })
        
        # Store the selected project and task on the business trip
        business_trip.write({
            'selected_project_id': self.project_id.id,
            'selected_project_task_id': task.id,
        })
        
        # Modified by A_zeril_A, 2025-10-20: Removed formio dependency
        # Get the automatically created form
        # form = business_trip.formio_form_id
        # if not form:
        #     raise UserError("Form was not created automatically.")
        
        # Set initial submission data with user information
        partner = current_user.partner_id
        if partner:
            # Split name into first and last name
            name_parts = partner.name.split(' ', 1) if partner.name else ['', '']
            last_name_val = name_parts[0]
            first_name_val = name_parts[1] if len(name_parts) > 1 else ''
            
            # Determine the Travel Approver for Standalone trips
            travel_approver_id = self.env['res.users'].sudo().get_travel_approver_for_standalone(current_user.id)
            travel_approver_name = ""
            if travel_approver_id:
                travel_approver_user = self.env['res.users'].sudo().browse(travel_approver_id)
                if travel_approver_user:
                    travel_approver_name = travel_approver_user.name

                    # Add user to Business Trip Manager group if not already a member
                    manager_group = self.env.ref('custom_business_trip_management.group_business_trip_manager', raise_if_not_found=False)
                    if manager_group and not travel_approver_user.has_group('custom_business_trip_management.group_business_trip_manager'):
                        travel_approver_user.sudo().write({'groups_id': [(4, manager_group.id)]})
            
            initial_data = {
                "first_name": first_name_val,
                "last_name": last_name_val,
                "trip_basis_text": f"Standalone business trip request for project: {self.project_id.name}",
                "approving_colleague_name": travel_approver_name,
                "data": {}
            }
            
            # Modified by A_zeril_A, 2025-10-20: Removed formio dependency - form data is now handled directly in business_trip_data
            # Update business_trip_data with initial submission data
            if business_trip.business_trip_data_id:
                business_trip.business_trip_data_id.sudo().write({
                    'first_name': first_name_val,
                    'last_name': last_name_val,
                    'purpose': f"Standalone business trip request for project: {self.project_id.name}",
                })
            
            # Process the initial data (no longer needed as formio is removed)
            # form.sudo().after_submit()
            
            # Set the Travel Approver on the business trip record
            if travel_approver_id:
                business_trip.sudo().write({'manager_id': travel_approver_id})
        
        # Redirect to the business trip form
        action = self.env.ref('custom_business_trip_management.action_view_my_business_trip_forms')
        menu_id = self.env.ref('custom_business_trip_management.menu_view_my_business_trip_forms').id
        company_id = self.env.company.id
        cids_param = f"&cids={company_id}" if company_id else ""

        return {
            'type': 'ir.actions.act_url',
            'url': f"/web#action={action.id}&model=business.trip&view_type=form&id={business_trip.id}&menu_id={menu_id}{cids_param}",
            'target': 'self',
        }


class BusinessTripOrganizerPlanWizard(models.TransientModel):
    _name = 'business.trip.organizer.plan.wizard'
    _description = 'Business Trip Organizer Planning Wizard'

    trip_id = fields.Many2one('business.trip', string='Trip', readonly=True, required=True)
    manager_max_budget = fields.Monetary(string='Maximum Budget (Set by Manager)', compute='_compute_manager_max_budget', readonly=True)
    organizer_trip_plan_details = fields.Text(string='Additional Notes', 
                                           help="Overall plan notes or item details.")
    
    # Cost calculation options
    manual_cost_entry = fields.Boolean(string='Enter Total Cost Manually', 
                                       help="Enter total cost manually.")
    organizer_planned_cost = fields.Monetary(string='Total Planned Cost', 
                                        help="Total planned cost for the trip")
    manual_planned_cost = fields.Monetary(string='Manual Total Cost', 
                                       help="Total cost (if manual entry selected).")
    
    # Computed field for auto-calculation display
    auto_calculated_cost = fields.Monetary(string='Auto-calculated Cost', 
                                         compute='_compute_auto_calculated_cost',
                                         help="Auto-calculated total from plan items")
    
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
    
    @api.depends('trip_id.currency_id')
    def _compute_currency_id(self):
        for wizard in self:
            wizard.currency_id = wizard.trip_id.currency_id

    @api.depends('trip_id', 'trip_id.manager_max_budget')
    def _compute_manager_max_budget(self):
        for wizard in self:
            wizard.manager_max_budget = wizard.trip_id.manager_max_budget if wizard.trip_id else 0.0

    @api.depends('plan_item_ids', 'plan_item_ids.cost')
    def _compute_auto_calculated_cost(self):
        for wizard in self:
            items_with_cost = wizard.plan_item_ids.filtered(lambda x: x.cost is not False and x.cost > 0)
            wizard.auto_calculated_cost = sum(items_with_cost.mapped('cost'))
    
    def _update_organizer_planned_cost(self):
        """Update organizer_planned_cost based on current mode"""
        if self.manual_cost_entry:
            self.organizer_planned_cost = self.manual_planned_cost or 0.0
        else:
            self.organizer_planned_cost = self.auto_calculated_cost
    
    @api.onchange('manual_cost_entry')
    def _onchange_manual_cost_entry(self):
        """Handle switching between manual and automatic cost calculation"""
        _logger.info(f"_onchange_manual_cost_entry: manual_cost_entry changed to {self.manual_cost_entry}")
        if self.manual_cost_entry:
            # Switching to manual mode: copy current total to manual field if it's empty
            if not self.manual_planned_cost:
                self.manual_planned_cost = self.organizer_planned_cost or self.auto_calculated_cost
                _logger.info(f"Switching to manual mode: set manual_planned_cost to {self.manual_planned_cost}")
            self.organizer_planned_cost = self.manual_planned_cost
        else:
            # Switching to automatic mode: use auto-calculated value
            self.organizer_planned_cost = self.auto_calculated_cost
            _logger.info(f"Switching to automatic mode: set organizer_planned_cost to {self.organizer_planned_cost}")
        
        # Ensure organizer_planned_cost is properly updated
        self._update_organizer_planned_cost()
    
    @api.onchange('manual_planned_cost')
    def _onchange_manual_planned_cost(self):
        """Update organizer_planned_cost when manual cost changes"""
        if self.manual_cost_entry:
            self.organizer_planned_cost = self.manual_planned_cost or 0.0
            _logger.info(f"Manual cost changed: set organizer_planned_cost to {self.organizer_planned_cost}")
            # Ensure organizer_planned_cost is properly updated
            self._update_organizer_planned_cost()
    
    @api.onchange('plan_item_ids', 'plan_item_ids.cost')
    def _onchange_plan_items(self):
        """Update organizer_planned_cost when plan items change (only in auto mode)"""
        if not self.manual_cost_entry:
            self.organizer_planned_cost = self.auto_calculated_cost
            _logger.info(f"Plan items changed: set organizer_planned_cost to {self.organizer_planned_cost}")
            # Ensure organizer_planned_cost is properly updated
            self._update_organizer_planned_cost()
    
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
        start_date = self.trip_id.travel_start_date or fields.Date.today()
        end_date = self.trip_id.travel_end_date or start_date
        
        # Try to use origin/destination from form
        origin = self.trip_id.user_id.company_id.city if self.trip_id.user_id and self.trip_id.user_id.company_id else ''
        destination = self.trip_id.destination or ''
        
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
        start_date = self.trip_id.travel_start_date or fields.Date.today()
        end_date = self.trip_id.travel_end_date or start_date
        
        # Calculate nights
        nights = 1
        if end_date and start_date:
            delta = (end_date - start_date).days
            nights = max(1, delta)
        
        # Use destination from form
        location = self.trip_id.destination or ''
        
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
        start_date = self.trip_id.travel_start_date or fields.Date.today()
        
        # Use destination from form
        location = self.trip_id.destination or ''
        
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
        start_date = self.trip_id.travel_start_date or fields.Date.today()
        
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
        """Create a well-formatted text version of the travel plan for saving to the trip"""
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
        trip_id = self.env.context.get('active_id')
        _logger.info(f"Default_get called with trip_id: {trip_id}")
        if trip_id:
            trip = self.env['business.trip'].browse(trip_id)
            _logger.info(f"Trip {trip.id} has status: {trip.trip_status}")
            res.update({
                'trip_id': trip_id,
                'organizer_planned_cost': trip.organizer_planned_cost or 0.0,
                'manual_cost_entry': trip.manual_cost_entry or False,
                'manual_planned_cost': trip.manual_planned_cost or 0.0,
                'organizer_trip_plan_details': trip.organizer_trip_plan_details,
                # Attachments will be handled separately
            })
            
            # Ensure consistency between manual and total cost fields
            if trip.manual_cost_entry:
                # In manual mode, use the saved manual cost
                res['organizer_planned_cost'] = trip.manual_planned_cost or 0.0
                _logger.info(f"Manual cost mode: Set organizer_planned_cost to {res['organizer_planned_cost']}")
            else:
                # In auto mode, the organizer_planned_cost will be calculated by onchange events
                # But ensure we have the correct current value
                res['organizer_planned_cost'] = trip.organizer_planned_cost or 0.0
            _logger.info(f"Updated res with basic trip info")
            
            # Manual cost entry state is now directly loaded from the trip record
            _logger.info(f"Checking manual cost entry logic for trip {trip.id}")
            _logger.info(f"Trip manual_cost_entry: {trip.manual_cost_entry}, manual_planned_cost: {trip.manual_planned_cost}")
                    
            # Load existing attachments
            _logger.info(f"Loading attachments for trip {trip.id}")
            if trip.organizer_attachments_ids:
                res['organizer_attachments_ids'] = [(6, 0, trip.organizer_attachments_ids.ids)]
                
            # Load employee documents if available
            if hasattr(trip, 'employee_documents_ids') and trip.employee_documents_ids:
                res['employee_documents_ids'] = [(6, 0, trip.employee_documents_ids.ids)]
            _logger.info(f"Finished loading attachments")
                
            # Create plan items from the saved data
            # Always try to recreate items from saved data regardless of status
            _logger.info(f"About to call _recreate_plan_items_from_form for trip {trip.id}")
            try:
                self._recreate_plan_items_from_form(res, trip)
                _logger.info(f"Successfully called _recreate_plan_items_from_form for trip {trip.id}")
            except Exception as e:
                _logger.error(f"Error in _recreate_plan_items_from_form for trip {trip.id}: {e}", exc_info=True)
            _logger.info(f"Finished calling _recreate_plan_items_from_form for trip {trip.id}")
        return res
    
    def _recreate_plan_items_from_form(self, res, trip):
        """Recreates wizard line items from existing business.trip.plan.line records."""
        _logger.info(f"_recreate_plan_items_from_form called for trip {trip.id}")
        
        # Force refresh the record from database to ensure we have latest data
        trip.invalidate_cache()
        
        # Check if the field exists and is accessible
        try:
            plan_lines = trip.plan_line_ids
            _logger.info(f"Found {len(plan_lines)} existing plan lines for trip {trip.id}")
            if len(plan_lines) > 0:
                _logger.info(f"Plan line IDs: {[line.id for line in plan_lines]}")
                # Also log some details of the first line to debug
                first_line = plan_lines[0]
                _logger.info(f"First line details - Type: {first_line.item_type}, Description: {first_line.description}, Cost: {first_line.planned_cost}")
        except Exception as e:
            _logger.error(f"Error accessing plan_line_ids: {e}")
            return res
        
        plan_items_vals = []
        # Load from the persistent plan lines on the trip
        for line in plan_lines:
            _logger.info(f"Processing line {line.id}: {line.description}")
            item_vals = {
                'item_type': line.item_type,
                'custom_type': line.custom_type,
                'direction': line.direction,
                'description': line.description,
                'item_date': line.item_date,
                'from_location': line.from_location,
                'to_location': line.to_location,
                'carrier': line.carrier,
                'reference_number': line.reference_number,
                'departure_time': line.departure_time,
                'arrival_time': line.arrival_time,
                'travel_class': line.travel_class,
                'nights': line.nights,
                'accommodation_type': line.accommodation_type,
                'cost': line.planned_cost,  # Map from persistent model's field
                'cost_status': line.cost_status,
                'is_reimbursable': line.is_reimbursable,
                'payment_method': line.payment_method,
                'notes': line.notes,
                'attachment_ids': [(6, 0, line.attachment_ids.ids)],
                'item_data_json': line.item_data_json,
            }
            plan_items_vals.append((0, 0, item_vals))
            _logger.info(f"Added item vals for line {line.id}")
        
        if plan_items_vals:
            res['plan_item_ids'] = plan_items_vals
            _logger.info(f"Recreated {len(plan_items_vals)} plan items for wizard")
        else:
            _logger.info("No plan items to recreate for wizard")
        return res

    def _create_default_plan_items(self, res, trip):
        # This is a placeholder and can be expanded if needed.
        # For now, it does nothing.
        return res

    def action_save_plan(self):
        """
        Saves the current state of the plan from the wizard to the main trip record,
        updates persistent plan lines, and posts notifications.
        """
        self.ensure_one()
        
        # Ensure organizer_planned_cost is properly calculated before saving
        self._update_organizer_planned_cost()
        
        trip = self.trip_id
        _logger.info(f"Attempting to save plan for trip {trip.id} by organizer {self.env.user.name}.")

        # Prepare values for persistent plan lines from wizard's virtual records
        plan_line_vals_list = []
        _logger.info(f"Plan has {len(self.plan_item_ids)} items to save.")
        for item in self.plan_item_ids:
            # Manually build the dictionary of values for the new persistent record.
            # This is more robust than relying on internal cache methods.
            line_vals = {
                'item_type': item.item_type,
                'custom_type': item.custom_type,
                'direction': item.direction,
                'description': item.description,
                'item_date': item.item_date,
                'from_location': item.from_location,
                'to_location': item.to_location,
                'carrier': item.carrier,
                'reference_number': item.reference_number,
                'departure_time': item.departure_time,
                'arrival_time': item.arrival_time,
                'travel_class': item.travel_class,
                'nights': item.nights,
                'accommodation_type': item.accommodation_type,
                'planned_cost': item.cost,  # Map wizard field 'cost' to persistent 'planned_cost'
                'cost_status': item.cost_status,
                'is_reimbursable': item.is_reimbursable,
                'payment_method': item.payment_method,
                'notes': item.notes,
                'item_data_json': item.item_data_json,
                'attachment_ids': [(6, 0, item.attachment_ids.ids)],
            }
            plan_line_vals_list.append((0, 0, line_vals))

        _logger.info(f"Created {len(plan_line_vals_list)} plan line values for trip {trip.id}.")
        
        # Also serialize plan items to JSON for legacy/other purposes
        plan_items_data_for_json = []
        for item in self.plan_item_ids:
            json_vals = {
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
            plan_items_data_for_json.append(json_vals)

        # Save all details to the main trip record
        trip.write({
            'organizer_planned_cost': self.organizer_planned_cost,
            'manual_cost_entry': self.manual_cost_entry,
            'manual_planned_cost': self.manual_planned_cost,
            'organizer_trip_plan_details': self.organizer_trip_plan_details,
            'structured_plan_items_json': json.dumps(plan_items_data_for_json, indent=4),
            'organizer_attachments_ids': [(6, 0, self.organizer_attachments_ids.ids)],
            'employee_documents_ids': [(6, 0, self.employee_documents_ids.ids)],
            'organizer_submission_date': fields.Datetime.now(),
            # Delete all existing lines and create new ones from the wizard state
            'plan_line_ids': [(5, 0, 0)] + plan_line_vals_list,
        })
        
        # Force commit the transaction to ensure data is saved
        self.env.cr.commit()
        _logger.info(f"Committed transaction for trip {trip.id}")
        
        # Refresh the trip record to ensure we have the latest data
        trip.invalidate_cache()
        trip.refresh()
        _logger.info(f"After save and commit, trip {trip.id} has {len(trip.plan_line_ids)} plan lines")
        
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
                self.trip_id.post_confidential_message(message_body)
                _logger.info(f"Successfully posted structured confidential plan summary for trip {self.trip_id.id}")

        except Exception as e:
            _logger.error(f"Failed to post structured confidential summary for trip {self.trip_id.id}: {e}", exc_info=True)
            # Fallback to the old plain text method if template rendering fails
            plan_details_str_confidential = self._prepare_plan_details_text(exclude_financials=False)
            if plan_details_str_confidential:
                fallback_message = "A travel plan has been drafted. (Template failed, showing raw text):\n\n" + plan_details_str_confidential
                self.trip_id.post_confidential_message(fallback_message)
        # --- END: MODIFIED SECTION ---

        # Post the styled public message for the employee
        self.trip_id._post_styled_message(
            template_xml_id='custom_business_trip_management.organizer_plan_public_summary',
            card_type='info',
            icon='⏳',
            title='Trip Plan Updated',
            is_internal_note=False,
            render_context={
                'record': self.trip_id,
                'wizard': self,
                 }
        )

        _logger.info(f"Plan for trip {self.trip_id.id} saved by organizer {self.env.user.name}.")
        return {'type': 'ir.actions.act_window_close'}

    def action_save_and_confirm(self):
        """
        Saves and finalizes the trip plan, updates the form status, and sends notifications
        for the employee to confirm the plan. This method now contains its own save logic
        to avoid calling action_save_plan and its side effects.
        """
        self.ensure_one()
        
        # Ensure organizer_planned_cost is properly calculated before saving
        self._update_organizer_planned_cost()
        
        _logger.info(f"Attempting to confirm and finalize plan for trip {self.trip_id.id} by organizer {self.env.user.name}.")

        # 1. Re-parent attachments to grant access before linking them
        if self.employee_documents_ids:
            self.employee_documents_ids.write({
                'res_model': 'business.trip',
                'res_id': self.trip_id.id
            })
        if self.organizer_attachments_ids:
            self.organizer_attachments_ids.write({
                'res_model': 'business.trip',
                'res_id': self.trip_id.id
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
            'manual_cost_entry': self.manual_cost_entry,
            'manual_planned_cost': self.manual_planned_cost,
            'organizer_attachments_ids': [(6, 0, self.organizer_attachments_ids.ids)],
            'employee_documents_ids': [(6, 0, self.employee_documents_ids.ids)],
            'structured_plan_items_json': json.dumps(plan_items_data, indent=4),
        }
        self.trip_id.write(form_vals)
        _logger.info(f"Plan data for trip {self.trip_id.id} saved before confirmation.")

        # 2. Call the main confirmation action on the trip model.
        # This action handles the state change and sends the "Plan is Ready" notification.
        self.trip_id.action_organizer_confirm_planning()

        # --- Post Messages ---

        # 3. Post a PUBLIC message for the employee with the detailed plan.
        # The generic notification has already been sent by the action above.
        employee_partner = self.trip_id.user_id.partner_id
        if employee_partner:
            public_plan_data = self._prepare_plan_details_structured(exclude_financials=True)

            message_body = self.env.ref('custom_business_trip_management.organizer_plan_summary')._render({
                'plan_data': public_plan_data,
                'organizer_name': self.trip_id.organizer_id.name,
                'title': "Your travel plan has been finalized. Please review the details and documents below."
            }, engine='ir.qweb')
            
            self.trip_id.message_post(
                body=message_body,
                message_type='notification',
                subtype_id=self.env.ref('mail.mt_note').id,
                partner_ids=[employee_partner.id],
            )
            _logger.info(f"Posted public confirmation notification for employee on trip {self.trip_id.id}.")

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
                self.trip_id.post_confidential_message(message_body)
                _logger.info(f"Successfully posted structured confidential plan summary for trip {self.trip_id.id}")

        except Exception as e:
            _logger.error(f"Failed to post structured confidential summary for trip {self.trip_id.id}: {e}", exc_info=True)
            # Fallback to plain text
            plan_details_str_confidential = self._prepare_plan_details_text(exclude_financials=False)
            if plan_details_str_confidential:
                fallback_message = "Trip Plan Finalized and Confirmed. (Template failed, showing raw text):\n\n" + plan_details_str_confidential
                self.trip_id.post_confidential_message(fallback_message)
        
        _logger.info(f"Plan for trip {self.trip_id.id} finalized.")
        
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

 




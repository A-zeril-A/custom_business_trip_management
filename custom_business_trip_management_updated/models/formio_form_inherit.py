from odoo import models, fields, api
from datetime import datetime, date
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)

class FormioForm(models.Model):
    _inherit = 'formio.form'

    # Basic trip information fields
    destination = fields.Char(string='Destination', tracking=True)
    purpose = fields.Text(string='Purpose of Trip', tracking=True)
    travel_start_date = fields.Date(string='Start Date', tracking=True)
    travel_end_date = fields.Date(string='End Date', tracking=True)
    expected_cost = fields.Float(string='Expected Cost', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                 default=lambda self: self.env.company.currency_id.id, tracking=True)
    final_total_cost = fields.Float(string='Final Total Cost', tracking=True)
    
    # Approval workflow fields
    trip_status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted for Approval'),
        ('manager_approved', 'Manager Approved'),
        ('rejected', 'Rejected'),
        ('approved', 'Approved'),
        ('in_progress', 'Trip In Progress'),
        ('returned', 'Returned from Trip'),
        ('expense_waiting', 'Expense Approval Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    # Approvers and dates
    user_id = fields.Many2one('res.users', string='Employee', default=lambda self: self.env.user.id, tracking=True)
    manager_id = fields.Many2one('res.users', string='Manager', tracking=True)
    manager_approval_date = fields.Datetime(string='Manager Approval Date', tracking=True)
    manager_comments = fields.Text(string='Manager Comments', tracking=True)
    
    finance_approver_id = fields.Many2one('res.users', string='Finance Approver', tracking=True)
    finance_approval_date = fields.Datetime(string='Finance Approval Date', tracking=True)
    finance_comments = fields.Text(string='Finance Comments', tracking=True)
    
    # Rejection tracking
    rejected_by = fields.Many2one('res.users', string='Rejected By', tracking=True)
    rejection_date = fields.Datetime(string='Rejection Date', tracking=True)
    
    # Expense tracking
    expense_total = fields.Float(string='Expense Total', tracking=True)
    expense_comments = fields.Text(string='Expense Notes', tracking=True)
    expense_attachment_ids = fields.Many2many('ir.attachment', string='Expense Receipts')
    expense_approval_date = fields.Datetime(string='Expense Approval Date', tracking=True)
    expense_approved_by = fields.Many2one('res.users', string='Expenses Approved By', tracking=True)
    
    # Travel tracking 
    actual_start_date = fields.Datetime(string='Actual Start Date', tracking=True)
    actual_end_date = fields.Datetime(string='Actual End Date', tracking=True)
    travel_duration = fields.Float(string='Travel Duration (Days)', compute='_compute_travel_dates', store=True)
    
    # Submission tracking
    submission_date = fields.Datetime(string='Submission Date', tracking=True)
    
    # Cancellation tracking
    cancellation_date = fields.Datetime(string='Cancellation Date', tracking=True)
    cancelled_by = fields.Many2one('res.users', string='Cancelled By', tracking=True)
    
    # Track the relation between formio state and trip_status
    @api.model
    def create(self, vals):
        record = super(FormioForm, self).create(vals)
        # Set initial trip_status based on form state if it's a new record
        if vals.get('state') == 'DRAFT':
            record.trip_status = 'draft'
        elif vals.get('state') == 'COMPLETE':
            record.trip_status = 'submitted'
        return record
    
    @api.onchange('state')
    def _onchange_state(self):
        """Update trip_status when form state changes"""
        if self.state == 'DRAFT' and self.trip_status not in ['draft']:
            self.trip_status = 'draft'
        elif self.state == 'COMPLETE' and self.trip_status == 'draft':
            # Only change to submitted if it's draft
            self.trip_status = 'submitted'
        elif self.state == 'CANCEL':
            self.trip_status = 'cancelled'
        # Ensure trip_status is set even if it's blank somehow
        elif self.state == 'COMPLETE' and not self.trip_status:
            self.trip_status = 'submitted'
            
    @api.onchange('trip_status')
    def _onchange_trip_status(self):
        """Ensure state and trip_status are synchronized"""
        # Log the change for debugging purposes
        _logger.info(f"Trip status changed to {self.trip_status} for form {self.id}, current state: {self.state}")
        
        # Ensure state is DRAFT when trip_status is draft
        if self.trip_status == 'draft' and self.state != 'DRAFT':
            self.state = 'DRAFT'
        # Ensure state is COMPLETE for non-draft and non-cancelled statuses
        elif self.trip_status not in ['draft', 'cancelled'] and self.state != 'COMPLETE':
            self.state = 'COMPLETE'
        # Ensure state is CANCEL when trip_status is cancelled
        elif self.trip_status == 'cancelled' and self.state != 'CANCEL':
            self.state = 'CANCEL'
            
    # Add methods to transition between states
    def action_submit_for_approval(self):
        """Submit the trip for manager approval"""
        if self.state != 'COMPLETE':
            raise ValidationError("Please complete the form before submitting for approval.")
        
        # Assign manager automatically if not set
        if not self.manager_id:
            # Try to find user's manager from employee records
            employee = self.env['hr.employee'].sudo().search([('user_id', '=', self.user_id.id)], limit=1)
            if employee and employee.parent_id and employee.parent_id.user_id:
                self.manager_id = employee.parent_id.user_id.id
            else:
                # If no manager found, raise error or assign to admin
                admin = self.env.ref('base.user_admin')
                self.manager_id = admin.id
        
        self.write({
            'trip_status': 'manager_review'
        })
        
        # Notify the manager
        if self.manager_id:
            self.message_subscribe(partner_ids=[self.manager_id.partner_id.id])
            self.message_post(
                body=f"This business trip request has been submitted for your approval.",
                partner_ids=[self.manager_id.partner_id.id]
            )
            
    def action_approve_manager(self):
        """Manager approves the business trip request"""
        # Check if user has permission to approve (is the assigned manager or admin)
        if not self.env.user.id == self.manager_id.id and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only the assigned manager or an administrator can approve this request.")
            
        if self.trip_status != 'submitted':
            raise ValidationError("You can only approve requests that have been submitted for manager review.")
            
        # Check if finance approval is required based on company settings
        require_finance = self.env.company.require_finance_approval_for_trips
        
        if require_finance:
            next_status = 'manager_approved'
            msg = "Your business trip request has been approved by your manager and is now waiting for finance approval."
        else:
            next_status = 'approved'
            msg = "Your business trip request has been approved!"
            
        self.write({
            'trip_status': next_status,
            'manager_approval_date': fields.Datetime.now(),
        })
        
        # Notify employee
        if self.user_id:
            self.message_post(
                body=msg,
                partner_ids=[self.user_id.partner_id.id]
            )
            
        # Notify finance approver if needed
        if require_finance and self.finance_approver_id:
            self.message_post(
                body="A business trip request requires your approval.",
                partner_ids=[self.finance_approver_id.partner_id.id]
            )
            # Create activity for finance to approve
            self.activity_schedule(
                'mail.mail_activity_data_todo', 
                user_id=self.finance_approver_id.id,
                summary="Review business trip request",
                note="Please review this business trip request.", 
                date_deadline=fields.Date.today() + relativedelta(days=3)
            )
            
    def action_reject_manager(self):
        """Manager rejects the business trip request"""
        # Check if user has permission to reject (is the assigned manager or admin)
        if not self.env.user.id == self.manager_id.id and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only the assigned manager or an administrator can reject this request.")
            
        if self.trip_status != 'submitted':
            raise ValidationError("You can only reject requests that have been submitted for manager review.")
            
        self.write({
            'trip_status': 'rejected',
            'rejection_date': fields.Datetime.now(),
            'rejected_by': self.env.user.id,
        })
        
        # Notify employee
        if self.user_id:
            self.message_post(
                body="Your business trip request has been rejected by your manager.",
                partner_ids=[self.user_id.partner_id.id]
            )
            
    def action_approve_finance(self):
        """Finance approves the business trip request"""
        # Check if user has permission to approve (is the assigned finance approver or admin)
        if not self.env.user.id == self.finance_approver_id.id and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only the assigned finance approver or an administrator can approve this request.")
            
        if self.trip_status != 'manager_approved':
            raise ValidationError("You can only approve requests that have been approved by a manager and are waiting for finance approval.")
            
        self.write({
            'trip_status': 'approved',
            'finance_approval_date': fields.Datetime.now(),
        })
        
        # Notify employee
        if self.user_id:
            self.message_post(
                body="Your business trip request has been approved by finance. You can now proceed with your trip.",
                partner_ids=[self.user_id.partner_id.id]
            )
            
    def action_reject_finance(self):
        """Finance rejects the business trip request"""
        # Check if user has permission to reject (is the assigned finance approver or admin)
        if not self.env.user.id == self.finance_approver_id.id and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only the assigned finance approver or an administrator can reject this request.")
            
        if self.trip_status != 'manager_approved':
            raise ValidationError("You can only reject requests that have been approved by a manager and are waiting for finance approval.")
            
        self.write({
            'trip_status': 'rejected',
            'rejection_date': fields.Datetime.now(),
            'rejected_by': self.env.user.id,
        })
        
        # Notify employee
        if self.user_id:
            self.message_post(
                body="Your business trip request has been rejected by finance.",
                partner_ids=[self.user_id.partner_id.id]
            )
            
    def action_start_trip(self):
        """Employee starts the business trip"""
        if self.trip_status != 'approved':
            raise ValidationError("Trip must be fully approved before it can be started.")
            
        self.write({'trip_status': 'in_progress'})
        
        # Create activity for manager to follow up
        if self.manager_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo', 
                user_id=self.manager_id.id,
                summary="Follow up on business trip",
                note=f"{self.user_id.name} has started their business trip to {self.travel_start_date}.", 
                date_deadline=self.travel_end_date or fields.Date.today()
            )
            
    def action_return_from_trip(self):
        """Employee returns from the business trip"""
        if self.trip_status != 'in_progress':
            raise ValidationError("Trip must be in progress before it can be marked as returned.")
            
        self.write({'trip_status': 'returned'})
        
        # Notify manager
        if self.manager_id:
            self.message_post(
                body=f"{self.user_id.name} has returned from their business trip.",
                partner_ids=[self.manager_id.partner_id.id]
            )
            
        # Create activity for employee to submit expenses
        if self.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo', 
                user_id=self.user_id.id,
                summary="Submit expense reports",
                note="Please submit your expense reports for your recent business trip.", 
                date_deadline=fields.Date.today() + relativedelta(days=7)
            )
            
    def action_submit_expenses(self):
        """Employee submits expenses for the trip"""
        if self.trip_status not in ['returned', 'expense_waiting']:
            raise ValidationError("You can only submit expenses after returning from your trip.")
            
        # Ensure only the employee assigned to the trip can submit expenses
        if self.env.user.id != self.user_id.id and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only the employee assigned to the trip can submit expenses.")
            
        self.write({'trip_status': 'expense_waiting'})
        
        # Notify finance
        if self.finance_approver_id:
            self.message_post(
                body=f"Expenses have been submitted for this business trip. Total: {self.expense_total} {self.currency_id.name}",
                partner_ids=[self.finance_approver_id.partner_id.id]
            )
            
        # Create activity for finance to approve expenses
        if self.finance_approver_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo', 
                user_id=self.finance_approver_id.id,
                summary="Review expense report",
                note=f"Please review the expenses submitted for this business trip. Total: {self.expense_total} {self.currency_id.name}", 
                date_deadline=fields.Date.today() + relativedelta(days=3)
            )
            
    def action_approve_expenses(self):
        """Finance approves the expenses"""
        # Check if user has permission to approve expenses
        if not self.env.user.id == self.finance_approver_id.id and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only the assigned finance approver or an administrator can approve expenses.")
            
        if self.trip_status != 'expense_waiting':
            raise ValidationError("You can only approve expenses that have been submitted for review.")
            
        self.write({
            'trip_status': 'completed',
            'expense_approval_date': fields.Datetime.now(),
            'expense_approved_by': self.env.user.id,
            'final_total_cost': self.expense_total  # Update final cost with approved expenses
        })
        
        # Notify the employee
        if self.user_id:
            self.message_post(
                body=f"Your expense report has been approved. The business trip is now completed.",
                partner_ids=[self.user_id.partner_id.id]
            )
            
    def action_cancel_trip(self):
        """Cancel a trip at any point in the process"""
        if self.trip_status in ['in_progress', 'returned', 'completed']:
            raise ValidationError("You cannot cancel a trip that is already in progress, returned, or completed.")
            
        self.write({'trip_status': 'cancelled'})
        
        # Cancel related activities
        self.activity_ids.action_feedback(
            feedback="This business trip has been cancelled."
        )
        
        # Notify all involved parties
        partners = []
        if self.user_id:
            partners.append(self.user_id.partner_id.id)
        if self.manager_id:
            partners.append(self.manager_id.partner_id.id)
        if self.finance_approver_id:
            partners.append(self.finance_approver_id.partner_id.id)
            
        self.message_post(
            body="This business trip has been cancelled.",
            partner_ids=partners
        )
    
    # Debug methods for testing
    def debug_set_to_manager_review(self):
        """Debug method to set trip status to manager_review"""
        self.write({'trip_status': 'manager_review'})
        
    def debug_set_to_finance_review(self):
        """Debug method to set trip status to finance_review"""
        self.write({'trip_status': 'finance_review'})
        
    def debug_set_to_approved(self):
        """Debug method to set trip status to approved"""
        self.write({'trip_status': 'approved'})

    # Methods for resetting status to previous state (only for admins)
    def action_reset_to_submitted(self):
        """Reset status to submitted (for admins only)"""
        if not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only administrators can reset trip status.")
            
        self.write({'trip_status': 'submitted'})
        self.message_post(body="Trip status was reset to 'Submitted' by an administrator.")
        
    def action_reset_to_manager_review(self):
        """Reset status to manager review (for admins only)"""
        if not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only administrators can reset trip status.")
            
        self.write({'trip_status': 'manager_review'})
        self.message_post(body="Trip status was reset to 'Manager Review' by an administrator.")
        
    def action_reset_to_finance_review(self):
        """Reset status to finance review (for admins only)"""
        if not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only administrators can reset trip status.")
            
        self.write({'trip_status': 'finance_review'})
        self.message_post(body="Trip status was reset to 'Finance Review' by an administrator.")
        
    def action_reset_status(self):
        """Reset status back one step based on current status (for admins only)"""
        if not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only administrators can reset trip status.")
            
        status_transitions = {
            'manager_review': 'submitted',
            'manager_approved': 'manager_review',
            'manager_rejected': 'manager_review',
            'finance_review': 'manager_approved',
            'finance_approved': 'finance_review',
            'finance_rejected': 'finance_review',
            'approved': 'finance_review',
            'in_progress': 'approved',
            'returned': 'in_progress',
            'expense_waiting': 'returned',
            'completed': 'expense_waiting',
        }
        
        if self.trip_status in status_transitions:
            previous_status = status_transitions[self.trip_status]
            self.write({'trip_status': previous_status})
            self.message_post(body=f"Trip status was reset from '{self.trip_status}' to '{previous_status}' by an administrator.")
        else:
            raise ValidationError(f"Cannot determine previous status for current status: {self.trip_status}")

    @api.depends('travel_start_date', 'travel_end_date', 'actual_start_date', 'actual_end_date')
    def _compute_travel_dates(self):
        """Compute the duration of the trip"""
        for record in self:
            if record.actual_start_date and record.actual_end_date:
                # Calculate actual travel duration if trip is completed or in progress
                start = fields.Datetime.from_string(record.actual_start_date)
                end = fields.Datetime.from_string(record.actual_end_date)
                delta = end - start
                record.travel_duration = delta.days + (delta.seconds / 86400.0)  # Convert seconds to days
            elif record.travel_start_date and record.travel_end_date:
                # Calculate planned travel duration
                start = fields.Date.from_string(record.travel_start_date)
                end = fields.Date.from_string(record.travel_end_date)
                delta = end - start
                record.travel_duration = delta.days + 1  # +1 to include both start and end dates
            else:
                record.travel_duration = 0.0
                
    def action_submit(self):
        """Employee submits the business trip request for approval"""
        if self.trip_status != 'draft':
            raise ValidationError("You can only submit a request that is in draft state.")
            
        # Ensure all required fields are filled
        if not self.destination or not self.purpose or not self.travel_start_date or not self.travel_end_date or not self.expected_cost:
            raise ValidationError("Please fill in all required fields before submitting the request.")
            
        # Validate dates
        if self.travel_start_date > self.travel_end_date:
            raise ValidationError("The travel end date must be after the travel start date.")
            
        # If manager is not set, try to get it from employee record
        if not self.manager_id:
            employee = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
            if employee and employee.parent_id and employee.parent_id.user_id:
                self.manager_id = employee.parent_id.user_id.id
                
        # Ensure there is a manager id
        if not self.manager_id:
            raise ValidationError("Please select a manager for approval before submitting.")
            
        self.write({
            'trip_status': 'submitted',
            'submission_date': fields.Datetime.now(),
        })
        
        # Notify manager
        if self.manager_id:
            self.message_post(
                body="A new business trip request has been submitted for your approval.",
                partner_ids=[self.manager_id.partner_id.id]
            )
            # Create activity for manager to approve
            self.activity_schedule(
                'mail.mail_activity_data_todo', 
                user_id=self.manager_id.id,
                summary="Review business trip request",
                note="Please review this business trip request.", 
                date_deadline=fields.Date.today() + relativedelta(days=3)
            )
            
    def action_start_trip(self):
        """Employee starts the business trip"""
        if self.trip_status != 'approved':
            raise ValidationError("You can only start a trip that has been fully approved.")
            
        # Ensure only the employee assigned to the trip can start it
        if self.env.user.id != self.user_id.id and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only the employee assigned to the trip can start the trip.")
            
        self.write({
            'trip_status': 'in_progress',
            'actual_start_date': fields.Datetime.now(),
        })
        
    def action_return_trip(self):
        """Employee returns from the business trip"""
        if self.trip_status != 'in_progress':
            raise ValidationError("You can only mark a return for a trip that is in progress.")
            
        # Ensure only the employee assigned to the trip can mark return
        if self.env.user.id != self.user_id.id and not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only the employee assigned to the trip can mark return from the trip.")
            
        self.write({
            'trip_status': 'returned',
            'actual_end_date': fields.Datetime.now(),
        })
        
        # Reminder to submit expenses
        self.message_post(
            body="You have marked your return from the business trip. Please submit your expenses for approval.",
            partner_ids=[self.user_id.partner_id.id]
        )
        
    def action_cancel_trip(self):
        """Cancel a business trip"""
        # Check if status allows cancellation
        if self.trip_status in ['in_progress', 'returned', 'completed', 'cancelled']:
            raise ValidationError("You cannot cancel a trip that is already in progress, returned, completed, or cancelled.")
            
        # Admin can cancel any trip
        if not self.env.user.has_group('base.group_system'):
            # Employee can cancel their own trips in draft or submitted state
            if self.env.user.id == self.user_id.id and self.trip_status not in ['draft', 'submitted']:
                raise ValidationError("You can only cancel your own trips that are in draft or submitted state.")
                
            # Manager can cancel trips they are assigned to approve
            if self.env.user.id == self.manager_id.id and self.trip_status != 'submitted':
                raise ValidationError("As a manager, you can only cancel trips that are submitted for your approval.")
                
            # Finance can cancel trips they are assigned to approve 
            if self.env.user.id == self.finance_approver_id.id and self.trip_status != 'manager_approved':
                raise ValidationError("As a finance approver, you can only cancel trips that are waiting for finance approval.")
                
        self.write({
            'trip_status': 'cancelled',
            'cancellation_date': fields.Datetime.now(),
            'cancelled_by': self.env.user.id,
        })
        
        # Notify participants
        message = f"Business trip to {self.destination} has been cancelled by {self.env.user.name}."
        partners = []
        
        if self.user_id and self.user_id.id != self.env.user.id:
            partners.append(self.user_id.partner_id.id)
            
        if self.manager_id and self.manager_id.id != self.env.user.id:
            partners.append(self.manager_id.partner_id.id)
            
        if self.finance_approver_id and self.finance_approver_id.id != self.env.user.id:
            partners.append(self.finance_approver_id.partner_id.id)
            
        if partners:
            self.message_post(
                body=message,
                partner_ids=partners
            )

    def write(self, vals):
        """Override write method to implement access controls"""
        # Check for critical fields being modified and implement access control
        if 'final_total_cost' in vals and not self.env.user.has_group('account.group_account_manager') and not self.env.user.has_group('base.group_system'):
            if self.trip_status not in ['expense_waiting'] or self.expense_approved_by:
                raise ValidationError("You don't have permission to modify the final total cost.")
                
        if 'manager_id' in vals and not self.env.user.has_group('base.group_erp_manager') and not self.env.user.has_group('base.group_system'):
            if self.trip_status not in ['draft', 'submitted']:
                raise ValidationError("You don't have permission to change the manager assignment.")
                
        if 'finance_approver_id' in vals and not self.env.user.has_group('account.group_account_manager') and not self.env.user.has_group('base.group_system'):
            if self.trip_status not in ['manager_approved']:
                raise ValidationError("You don't have permission to change the finance approver.")
                
        if 'expense_total' in vals:
            # Only the trip user or admin can modify expense total before approval
            if self.env.user.id != self.user_id.id and not self.env.user.has_group('base.group_system'):
                if self.trip_status not in ['returned', 'expense_waiting'] or self.expense_approved_by:
                    raise ValidationError("You don't have permission to modify the expense total.")
                    
        return super(FormioForm, self).write(vals)

    def action_draft(self):
        """Override standard formio action_draft to also reset trip_status to draft"""
        # ذخیره مقادیر فیلدهای مهم قبل از تغییر وضعیت
        preserved_values = {
            'destination': self.destination,
            'purpose': self.purpose,
            'travel_start_date': self.travel_start_date,
            'travel_end_date': self.travel_end_date,
            'expected_cost': self.expected_cost,
            'manager_id': self.manager_id.id if self.manager_id else False,
            'manager_comments': self.manager_comments,
            'finance_approver_id': self.finance_approver_id.id if self.finance_approver_id else False,
            'finance_comments': self.finance_comments,
            'currency_id': self.currency_id.id if self.currency_id else False,
        }
        
        # علت استفاده از sql_constraint: اطمینان از اینکه تغییر trip_status مستقیماً و بدون فراخوانی ناظرهای دیگر انجام شود
        self._cr.execute("UPDATE formio_form SET trip_status = 'draft' WHERE id = %s", (self.id,))
        # اکنون فراخوانی متد اصلی
        res = super(FormioForm, self).action_draft()
        # برای اطمینان از همگام‌سازی حافظه نهان
        self.invalidate_cache(['trip_status'], self.ids)
        
        # بازگرداندن مقادیر فیلدهای مهم
        self.write(preserved_values)
        
        # ثبت پیام در گفتگو
        self.message_post(body="وضعیت فرم و سفر به 'پیش‌نویس' تغییر یافت. مقادیر فیلدهای مهم حفظ شده‌اند.")
        
        return res

    def action_cancel(self):
        """Override standard formio action_cancel to also set trip_status to cancelled"""
        # علت استفاده از sql_constraint: اطمینان از اینکه تغییر trip_status مستقیماً و بدون فراخوانی ناظرهای دیگر انجام شود
        if self.trip_status not in ['in_progress', 'returned', 'completed', 'cancelled']:
            cancel_date = fields.Datetime.now()
            self._cr.execute(
                "UPDATE formio_form SET trip_status = 'cancelled', cancellation_date = %s, cancelled_by = %s WHERE id = %s", 
                (cancel_date, self.env.user.id, self.id)
            )
        # اکنون فراخوانی متد اصلی
        res = super(FormioForm, self).action_cancel()
        # برای اطمینان از همگام‌سازی حافظه نهان
        self.invalidate_cache(['trip_status', 'cancellation_date', 'cancelled_by'], self.ids)
        return res

    def debug_force_trip_status(self):
        """Debug method to set trip_status directly (for admin only)"""
        if not self.env.user.has_group('base.group_system'):
            raise ValidationError("Only system administrators can use this function.")
            
        status_options = dict(self._fields['trip_status'].selection)
        status_list = [(key, status_options[key]) for key in status_options]
        
        return {
            'name': 'Set Trip Status',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'formio.form.trip.status.wizard',
            'target': 'new',
            'context': {
                'default_form_id': self.id,
                'default_current_status': self.trip_status,
                'status_options': status_list
            }
        }

    def debug_show_status(self):
        """Debug method to display current values of state and trip_status"""
        raise ValidationError(f"Current state: {self.state}, trip_status: {self.trip_status}")

    def action_reset_trip_to_draft(self):
        """Reset trip_status to draft directly - custom method for user access"""
        if self.trip_status in ['in_progress', 'returned', 'completed']:
            raise ValidationError("سفرهایی که در وضعیت 'در حال انجام'، 'بازگشته' یا 'تکمیل شده' هستند را نمی‌توان به حالت پیش‌نویس برگرداند.")
            
        # ذخیره مقادیر فیلدهای مهم قبل از تغییر وضعیت
        preserved_values = {
            'destination': self.destination,
            'purpose': self.purpose,
            'travel_start_date': self.travel_start_date,
            'travel_end_date': self.travel_end_date,
            'expected_cost': self.expected_cost,
            'manager_id': self.manager_id.id if self.manager_id else False,
            'manager_comments': self.manager_comments,
            'finance_approver_id': self.finance_approver_id.id if self.finance_approver_id else False,
            'finance_comments': self.finance_comments,
            'currency_id': self.currency_id.id if self.currency_id else False,
        }
            
        # تغییر مستقیم وضعیت سفر به draft
        self._cr.execute("UPDATE formio_form SET trip_status = 'draft' WHERE id = %s", (self.id,))
        self.invalidate_cache(['trip_status'], self.ids)
        
        # اگر فرم در وضعیت COMPLETE یا CANCEL باشد، آن را به DRAFT تغییر دهید
        if self.state in ['COMPLETE', 'CANCEL']:
            self.state = 'DRAFT'
            
        # بازگرداندن مقادیر فیلدهای مهم
        self.write(preserved_values)
            
        # ثبت پیام در گفتگو
        self.message_post(body="وضعیت سفر به 'پیش‌نویس' تغییر یافت. مقادیر فیلدهای مهم حفظ شده‌اند.")
        
        return True
        
    def _extract_required_fields_from_submission(self):
        """Extract required fields from submission_data"""
        if not self.submission_data:
            return
            
        # تبدیل submission_data به دیکشنری
        data = {}
        if isinstance(self.submission_data, str):
            try:
                import json
                data = json.loads(self.submission_data)
            except json.JSONDecodeError:
                _logger.error("Could not parse submission_data as JSON")
                return
        else:
            data = self.submission_data
            
        # استخراج فیلدها
        update_vals = {}
        
        # مقصد
        destination_keys = [k for k in data.keys() if 'destination' in k.lower() or 'meta' in k.lower()]
        for key in destination_keys:
            if data.get(key) and not self.destination:
                update_vals['destination'] = data.get(key)
                break
                
        # هدف سفر
        purpose_keys = [k for k in data.keys() if 'purpose' in k.lower() or 'reason' in k.lower() or 'motivo' in k.lower()]
        for key in purpose_keys:
            if data.get(key) and not self.purpose:
                update_vals['purpose'] = data.get(key)
                break
                
        # هزینه پیش‌بینی شده
        cost_keys = [k for k in data.keys() if 'cost' in k.lower() or 'expense' in k.lower() or 'budget' in k.lower()]
        for key in cost_keys:
            if data.get(key) and not self.expected_cost:
                try:
                    update_vals['expected_cost'] = float(data.get(key))
                except (ValueError, TypeError):
                    pass
                break
                
        # تاریخ شروع سفر
        start_date_keys = [k for k in data.keys() if 'start' in k.lower() or 'departure' in k.lower() or 'partenza' in k.lower()]
        for key in start_date_keys:
            if data.get(key) and not self.travel_start_date:
                date_value = data.get(key)
                if isinstance(date_value, dict) and 'year' in date_value and 'month' in date_value and 'day' in date_value:
                    try:
                        from datetime import date
                        update_vals['travel_start_date'] = date(
                            int(date_value.get('year')),
                            int(date_value.get('month')),
                            int(date_value.get('day'))
                        )
                    except (ValueError, TypeError):
                        pass
                elif isinstance(date_value, str):
                    try:
                        from datetime import datetime
                        for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                            try:
                                update_vals['travel_start_date'] = datetime.strptime(date_value, fmt).date()
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass
                break
                
        # تاریخ پایان سفر
        end_date_keys = [k for k in data.keys() if 'end' in k.lower() or 'return' in k.lower() or 'ritorno' in k.lower() or 'arrivo' in k.lower()]
        for key in end_date_keys:
            if data.get(key) and not self.travel_end_date:
                date_value = data.get(key)
                if isinstance(date_value, dict) and 'year' in date_value and 'month' in date_value and 'day' in date_value:
                    try:
                        from datetime import date
                        update_vals['travel_end_date'] = date(
                            int(date_value.get('year')),
                            int(date_value.get('month')),
                            int(date_value.get('day'))
                        )
                    except (ValueError, TypeError):
                        pass
                elif isinstance(date_value, str):
                    try:
                        from datetime import datetime
                        for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                            try:
                                update_vals['travel_end_date'] = datetime.strptime(date_value, fmt).date()
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass
                break
                
        # به‌روزرسانی رکورد اگر مقادیر جدیدی پیدا شده باشد
        if update_vals:
            self.write(update_vals)

    def debug_show_required_fields(self):
        """Debug method to display values of required fields"""
        message = f"""
        مقادیر فیلدهای اجباری:
        - مقصد (destination): {self.destination or 'خالی'}
        - هدف سفر (purpose): {self.purpose or 'خالی'}
        - تاریخ شروع (travel_start_date): {self.travel_start_date or 'خالی'}
        - تاریخ پایان (travel_end_date): {self.travel_end_date or 'خالی'}
        - هزینه پیش‌بینی شده (expected_cost): {self.expected_cost or 'خالی'}
        """
        raise ValidationError(message)

    def action_edit_required_fields(self):
        """Open wizard to manually edit required fields"""
        self.ensure_one()
        return {
            'name': 'Edit Required Fields',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'formio.form.required.fields.wizard',
            'target': 'new',
            'context': {
                'default_form_id': self.id,
                'default_destination': self.destination or '',
                'default_purpose': self.purpose or '',
                'default_travel_start_date': self.travel_start_date or False,
                'default_travel_end_date': self.travel_end_date or False,
                'default_expected_cost': self.expected_cost or 0.0,
            }
        }
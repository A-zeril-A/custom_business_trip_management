# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class FormioForm(models.Model):
    _inherit = 'formio.form'

    # Essential fields for linking to business.trip
    business_trip_id = fields.Many2one('business.trip', string='Business Trip', ondelete='cascade', index=True)
    business_trip_data_id = fields.Many2one(
        'business.trip.data', 
        string='Business Trip Data', 
        related='business_trip_id.business_trip_data_id', 
        store=True, 
        readonly=True
    )
    
    # Field to handle redirect after submission
    redirect_after_submit = fields.Char(string='Redirect URL After Submit', compute='_compute_redirect_url', store=False)
    
    # Essential computed fields for UI permissions
    is_manager = fields.Boolean(string='Is Manager', compute='_compute_user_roles', store=False)
    is_finance = fields.Boolean(string='Is Finance', compute='_compute_user_roles', store=False)
    is_organizer = fields.Boolean(string='Is Organizer', compute='_compute_user_roles', store=False)
    can_see_costs = fields.Boolean(string='Can See Costs', compute='_compute_user_roles', store=False)

    # Override state field for better labels
    state = fields.Selection(
        selection_add=[
            ('DRAFT', 'Awaiting Completion'),
            ('COMPLETE', 'Form Completed'),
            ('CANCEL', 'Cancelled')
        ],
    )

    @api.model
    def create(self, vals_list):
        """Simplified create method"""
        if not isinstance(vals_list, list):
            vals_list = [vals_list]

        # Ensure DRAFT state consistency
        for vals in vals_list:
            if vals.get('state') == 'PENDING':
                vals['state'] = 'DRAFT'

        return super(FormioForm, self).create(vals_list)

    def after_submit(self):
        """
        Process form submission by delegating to business.trip
        """
        _logger.info(f"Processing form submission for form {self.id}")
        
        # Run original formio logic
        res = super(FormioForm, self).after_submit()

        # Process business trip data if linked
        if self.business_trip_id:
            _logger.info(f"Form {self.id} is linked to Business Trip {self.business_trip_id.id}.")
            self.business_trip_id.process_form_submission(self.submission_data)
        else:
            _logger.warning(f"Form {self.id} is not linked to any Business Trip")

        return res

    @api.depends('business_trip_id', 'business_trip_id.user_id', 'business_trip_id.manager_id', 'business_trip_id.organizer_id')
    @api.depends_context('uid')
    def _compute_user_roles(self):
        """Compute user roles for UI permissions"""
        for record in self:
            user = self.env.user
            is_system_admin = user.has_group('base.group_system')

            if is_system_admin:
                record.is_manager = True
                record.is_finance = True
                record.is_organizer = True
                record.can_see_costs = True
                continue

            if record.business_trip_id:
                bt = record.business_trip_id
                is_trip_owner = (bt.user_id.id == user.id)

                if is_trip_owner:
                    record.is_manager = False
                    record.is_organizer = (bt.organizer_id and user.id == bt.organizer_id.id)
                    record.is_finance = False
                    record.can_see_costs = record.is_organizer
                    continue

                record.is_manager = (bt.manager_id and user.id == bt.manager_id.id)
                record.is_organizer = (bt.organizer_id and user.id == bt.organizer_id.id)
                record.is_finance = record.is_organizer or user.has_group('account.group_account_manager')
                record.can_see_costs = (record.is_manager or record.is_organizer or 
                                      user.has_group('custom_business_trip_management.group_business_trip_organizer'))
            else:
                record.is_manager = False
                record.is_finance = False
                record.is_organizer = False
                record.can_see_costs = user.has_group('custom_business_trip_management.group_business_trip_organizer')
    
    def action_open_organizer_plan_wizard(self):
        """Open organizer plan wizard"""
        self.ensure_one()
        if not self.business_trip_id:
            raise UserError(_("This form is not linked to a business trip record."))
        return self.business_trip_id.action_open_organizer_plan_wizard()

    def _compute_redirect_url(self):
        """
        Compute a robust redirect URL to the corresponding business.trip record.
        This URL includes the necessary action and menu context for a seamless
        user experience in the Odoo web client.
        """
        try:
            # We want to redirect to the business.trip form view.
            # The action 'action_all_assigned_business_trip_forms' seems correct
            # as it's used in the controller for redirection.
            action = self.env.ref('custom_business_trip_management.action_view_my_business_trip_forms')
            menu = self.env.ref('custom_business_trip_management.menu_view_my_business_trip_forms')
        except ValueError:
            # If refs are not found (e.g., during installation), fail gracefully
            for form in self:
                form.redirect_after_submit = False
            return

        for form in self:
            if form.business_trip_id:
                base_url = f"/web#id={form.business_trip_id.id}&view_type=form&model=business.trip"
                
                params = {
                    'action': action.id,
                    'menu_id': menu.id,
                }
                
                # Add company context if it exists
                company_id = self.env.company.id
                if company_id:
                    params['cids'] = company_id
                
                # Build the final URL fragment
                url_params = '&'.join([f'{k}={v}' for k, v in params.items()])
                
                form.redirect_after_submit = f'{base_url}&{url_params}'
                _logger.info(f"Generated redirect URL for form {form.id}: {form.redirect_after_submit}")
            else:
                form.redirect_after_submit = False
                _logger.warning(f"Could not generate redirect URL for form {form.id} because it is not linked to a business trip.")

    # Essential proxy methods for form view compatibility
    def action_submit_to_manager(self):
        """Submit trip to manager"""
        self.ensure_one()
        if not self.business_trip_id:
            raise UserError(_("This form is not linked to a business trip record."))
        return self.business_trip_id.action_submit_to_manager()

    def action_cancel_trip(self):
        """Cancel trip"""
        self.ensure_one()
        if not self.business_trip_id:
            raise UserError(_("This form is not linked to a business trip record."))
        return self.business_trip_id.action_cancel_trip()

    def action_edit_trip_details(self):
        """Edit trip details"""
        self.ensure_one()
        if not self.business_trip_id:
            raise UserError(_("This form is not linked to a business trip record."))
        return self.business_trip_id.action_edit_trip_details()

    def action_submit_expenses(self):
        """Submit expenses"""
        self.ensure_one()
        if not self.business_trip_id:
            raise UserError(_("This form is not linked to a business trip record."))
        return self.business_trip_id.action_submit_expenses()





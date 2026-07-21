from odoo import api, fields, models


class BusinessTripReminderDigestState(models.Model):
    _name = 'business.trip.reminder.digest.state'
    _description = 'Business Trip Reminder Digest State'
    _order = 'write_date desc, id desc'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='cascade')
    digest_key = fields.Selection([
        ('employee_expense_followup', 'Employee Expense Follow-up'),
        ('organizer_expense_followup', 'Expense Reviewer Follow-up'),
    ], required=True, index=True)
    last_sent_date = fields.Datetime(copy=False)

    _sql_constraints = [
        (
            'business_trip_digest_state_unique',
            'unique(user_id, company_id, digest_key)',
            'Each business trip digest state must be unique per user, company, and digest type.',
        ),
    ]

    @api.model
    def get_or_create_state(self, user, company, digest_key):
        lock_key = (
            "custom_business_trip_management:"
            f"{user.id}:{company.id}:{digest_key}"
        )
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            [lock_key],
        )
        state = self.search([
            ('user_id', '=', user.id),
            ('company_id', '=', company.id),
            ('digest_key', '=', digest_key),
        ], limit=1)
        if state:
            return state
        return self.create({
            'user_id': user.id,
            'company_id': company.id,
            'digest_key': digest_key,
        })

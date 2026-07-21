from odoo import fields, models
from odoo.exceptions import AccessError


class BusinessTripAssignmentHistory(models.Model):
    _name = "business.trip.assignment.history"
    _description = "Business Trip Assignment History"
    _order = "changed_at desc, id desc"

    trip_id = fields.Many2one(
        "business.trip",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="trip_id.company_id",
        store=True,
        index=True,
    )
    role = fields.Selection(
        [
            ("approver", "Travel Approver"),
            ("organizer", "Organizer"),
            ("expense_reviewer", "Expense Reviewer"),
        ],
        required=True,
        index=True,
    )
    previous_user_id = fields.Many2one(
        "res.users",
        index=True,
        ondelete="set null",
    )
    new_user_id = fields.Many2one(
        "res.users",
        index=True,
        ondelete="set null",
    )
    changed_by_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
        ondelete="restrict",
    )
    changed_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    reason = fields.Char(required=True)

    def write(self, vals):
        if not self.env.su:
            raise AccessError("Business trip assignment history is immutable.")
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError("Business trip assignment history is immutable.")
        return super().unlink()

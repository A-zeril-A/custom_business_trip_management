from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRoleRevocation(TransactionCase):
    """Role changes must grant the successor and revoke the predecessor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        internal = cls.env.ref("base.group_user")
        requester = cls.env.ref(
            "custom_business_trip_management.group_business_trip_requester"
        )
        cls.approver_capability = cls.env.ref(
            "custom_business_trip_management.group_business_trip_approver"
        )
        cls.standalone_group = cls.env.ref(
            "custom_business_trip_management.group_business_trip_manager_standalone"
        )
        cls.reviewer_group = cls.env.ref(
            "custom_business_trip_management.group_business_trip_expense_reviewer"
        )
        cls.auditor_group = cls.env.ref(
            "custom_business_trip_management.group_business_trip_auditor"
        )

        def create_user(name, login):
            return cls.env["res.users"].with_context(no_reset_password=True).create(
                {
                    "name": name,
                    "login": login,
                    "email": f"{login}@example.com",
                    "company_id": cls.company.id,
                    "company_ids": [(6, 0, [cls.company.id])],
                    "groups_id": [(6, 0, [internal.id, requester.id])],
                }
            )

        cls.employee = create_user("Revoke Employee", "bt_revoke_employee")
        cls.old_approver = create_user("Old Approver", "bt_revoke_old_approver")
        cls.new_approver = create_user("New Approver", "bt_revoke_new_approver")
        cls.reviewer = create_user("Trip Reviewer", "bt_revoke_reviewer")
        cls.new_reviewer = create_user("New Trip Reviewer", "bt_revoke_new_reviewer")
        cls.audit_user = create_user("Audit Candidate", "bt_revoke_auditor")
        cls.other_employee = create_user(
            "Revoke Other Employee", "bt_revoke_other_employee"
        )

    def test_replacing_settings_approver_without_open_trips_revokes_groups(self):
        self.company.write(
            {"business_trip_standalone_approver_id": self.old_approver.id}
        )
        self.assertIn(self.standalone_group, self.old_approver.groups_id)
        self.assertIn(self.approver_capability, self.old_approver.groups_id)

        self.company.write(
            {"business_trip_standalone_approver_id": self.new_approver.id}
        )
        self.assertIn(self.standalone_group, self.new_approver.groups_id)
        self.assertNotIn(self.standalone_group, self.old_approver.groups_id)
        self.assertNotIn(self.approver_capability, self.old_approver.groups_id)

    def test_assigned_approver_keeps_access_until_trip_closes(self):
        trip = self.env["business.trip"].create(
            {
                "user_id": self.employee.id,
                "company_id": self.company.id,
                "manager_id": self.old_approver.id,
                "trip_status": "submitted",
            }
        )
        self.old_approver.ensure_business_trip_approver_capability()
        self.assertIn(self.approver_capability, self.old_approver.groups_id)

        # Replacing the settings default must not strip an assigned approver.
        self.company.write(
            {"business_trip_standalone_approver_id": self.new_approver.id}
        )
        self.assertIn(self.approver_capability, self.old_approver.groups_id)
        readable = self.env["business.trip"].with_user(self.old_approver).search(
            [("id", "=", trip.id)]
        )
        self.assertEqual(readable, trip)

        trip.write({"trip_status": "completed"})
        self.assertNotIn(self.approver_capability, self.old_approver.groups_id)

    def test_reviewer_capability_revoked_after_last_open_trip_closes(self):
        self.company.write(
            {"business_trip_standalone_expense_reviewer_id": self.reviewer.id}
        )
        trip = self.env["business.trip"].create(
            {
                "user_id": self.employee.id,
                "company_id": self.company.id,
            }
        )
        self.assertEqual(trip.expense_reviewer_id, self.reviewer)
        self.assertIn(self.reviewer_group, self.reviewer.groups_id)

        # Replacing the settings default keeps the assigned reviewer's
        # capability while their trip is still open.
        self.company.write(
            {"business_trip_standalone_expense_reviewer_id": self.new_reviewer.id}
        )
        self.assertIn(self.reviewer_group, self.reviewer.groups_id)
        self.assertIn(self.reviewer_group, self.new_reviewer.groups_id)

        trip.write({"trip_status": "completed"})
        self.assertNotIn(self.reviewer_group, self.reviewer.groups_id)

    def test_auditor_toggle_grants_and_revokes_read_all(self):
        own_trip = self.env["business.trip"].create(
            {
                "user_id": self.audit_user.id,
                "company_id": self.company.id,
            }
        )
        foreign_trip = self.env["business.trip"].create(
            {
                "user_id": self.other_employee.id,
                "company_id": self.company.id,
            }
        )

        Trip = self.env["business.trip"].with_user(self.audit_user)
        self.assertFalse(Trip.search([("id", "=", foreign_trip.id)]))

        self.audit_user.sudo().write({"groups_id": [(4, self.auditor_group.id)]})
        Trip = self.env["business.trip"].with_user(self.audit_user)
        self.assertEqual(
            Trip.search([("id", "in", (own_trip | foreign_trip).ids)]),
            own_trip | foreign_trip,
        )
        with self.assertRaises(AccessError):
            foreign_trip.with_user(self.audit_user).write({"purpose": "x"})

        self.audit_user.sudo().write({"groups_id": [(3, self.auditor_group.id)]})
        Trip = self.env["business.trip"].with_user(self.audit_user)
        self.assertFalse(Trip.search([("id", "=", foreign_trip.id)]))

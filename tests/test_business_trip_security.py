from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBusinessTripSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        internal = cls.env.ref("base.group_user")
        requester = cls.env.ref(
            "custom_business_trip_management.group_business_trip_requester"
        )
        auditor = cls.env.ref(
            "custom_business_trip_management.group_business_trip_auditor"
        )
        organizer = cls.env.ref(
            "custom_business_trip_management.group_business_trip_organizer"
        )
        approver = cls.env.ref(
            "custom_business_trip_management.group_business_trip_approver"
        )

        def create_user(name, login, groups):
            return cls.env["res.users"].with_context(no_reset_password=True).create(
                {
                    "name": name,
                    "login": login,
                    "email": f"{login}@example.com",
                    "company_id": cls.company.id,
                    "company_ids": [(6, 0, [cls.company.id])],
                    "groups_id": [(6, 0, [internal.id] + groups)],
                }
            )

        cls.employee_a = create_user(
            "Sec Employee A",
            "bt_sec_employee_a",
            [requester.id],
        )
        cls.employee_b = create_user(
            "Sec Employee B",
            "bt_sec_employee_b",
            [requester.id],
        )
        cls.approver_user = create_user(
            "Sec Approver",
            "bt_sec_approver",
            [requester.id, approver.id],
        )
        cls.organizer_user = create_user(
            "Sec Organizer",
            "bt_sec_organizer",
            [requester.id, organizer.id],
        )
        cls.auditor_user = create_user(
            "Sec Auditor",
            "bt_sec_auditor",
            [requester.id, auditor.id],
        )
        cls.company.with_context(skip_business_trip_role_sync=True).write(
            {
                "business_trip_organizer_id": cls.organizer_user.id,
                "business_trip_standalone_approver_id": cls.approver_user.id,
            }
        )
        cls.company._sync_business_trip_role_group(
            "business_trip_organizer_id",
            "custom_business_trip_management.group_business_trip_organizer",
            previous_user=cls.env["res.users"],
        )
        cls.trip_a = cls.env["business.trip"].create(
            {
                "user_id": cls.employee_a.id,
                "company_id": cls.company.id,
                "manager_id": cls.approver_user.id,
                "organizer_id": cls.organizer_user.id,
                "trip_status": "pending_organization",
            }
        )
        cls.trip_b = cls.env["business.trip"].create(
            {
                "user_id": cls.employee_b.id,
                "company_id": cls.company.id,
                "manager_id": cls.approver_user.id,
                "trip_status": "submitted",
            }
        )

    def test_requester_cannot_read_other_employee_trip(self):
        Trip = self.env["business.trip"].with_user(self.employee_b)
        self.assertFalse(Trip.search([("id", "=", self.trip_a.id)]))
        with self.assertRaises(AccessError):
            self.trip_a.with_user(self.employee_b).read(["name"])

    def test_requester_can_read_own_trip(self):
        Trip = self.env["business.trip"].with_user(self.employee_a)
        self.assertEqual(Trip.search([("id", "=", self.trip_a.id)]), self.trip_a)

    def test_approver_can_read_assigned_trip_only(self):
        Trip = self.env["business.trip"].with_user(self.approver_user)
        visible = Trip.search([("id", "in", (self.trip_a | self.trip_b).ids)])
        self.assertEqual(visible, self.trip_a | self.trip_b)

    def test_auditor_can_read_but_not_write(self):
        trip = self.trip_a.with_user(self.auditor_user)
        self.assertEqual(trip.name, self.trip_a.name)
        with self.assertRaises(AccessError):
            trip.write({"purpose": "Auditor should not write"})

    def test_organizer_can_read_company_workspace(self):
        Trip = self.env["business.trip"].with_user(self.organizer_user)
        visible = Trip.search([("company_id", "=", self.company.id)])
        self.assertIn(self.trip_a, visible)
        self.assertIn(self.trip_b, visible)

    def test_requester_cannot_reassign_organizer_directly(self):
        with self.assertRaises(AccessError):
            self.trip_a.with_user(self.employee_a).write(
                {"organizer_id": self.employee_b.id}
            )

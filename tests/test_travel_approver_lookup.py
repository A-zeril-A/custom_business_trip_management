from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTravelApproverLookup(TransactionCase):
    """Sale-order approval follows Settings, then the employee manager."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        internal = cls.env.ref("base.group_user")
        requester = cls.env.ref(
            "custom_business_trip_management.group_business_trip_requester"
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

        cls.line_manager = create_user("Line Manager", "bt_lookup_manager")
        cls.settings_approver = create_user(
            "Settings Approver", "bt_lookup_settings"
        )
        cls.employee = create_user("Lookup Employee", "bt_lookup_employee")
        cls.manager_employee = cls.env["hr.employee"].create(
            {
                "name": "Line Manager",
                "user_id": cls.line_manager.id,
                "company_id": cls.company.id,
            }
        )
        cls.env["hr.employee"].create(
            {
                "name": "Lookup Employee",
                "user_id": cls.employee.id,
                "company_id": cls.company.id,
                "parent_id": cls.manager_employee.id,
            }
        )
        cls.env["hr.employee"].create(
            {
                "name": "Settings Approver",
                "user_id": cls.settings_approver.id,
                "company_id": cls.company.id,
                "parent_id": cls.manager_employee.id,
            }
        )
        cls.Users = cls.env["res.users"].with_company(cls.company)

    def test_settings_approver_wins_over_direct_manager(self):
        self.company.with_context(skip_business_trip_role_sync=True).write(
            {"business_trip_sale_order_approver_id": self.settings_approver.id}
        )
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.employee.id),
            self.settings_approver.id,
        )

    def test_empty_settings_uses_direct_manager(self):
        self.company.with_context(skip_business_trip_role_sync=True).write(
            {"business_trip_sale_order_approver_id": False}
        )
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.employee.id),
            self.line_manager.id,
        )

    def test_requester_is_not_assigned_as_own_approver(self):
        self.company.with_context(skip_business_trip_role_sync=True).write(
            {"business_trip_sale_order_approver_id": self.settings_approver.id}
        )
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.settings_approver.id),
            self.line_manager.id,
        )

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTravelApproverLookup(TransactionCase):
    """Both trip types follow Settings first, then the employee manager."""

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
        # Neither a manager above nor anybody below: the shape an employee
        # record has when nobody ever assigned it a manager.
        cls.orphan = create_user("Orphan Employee", "bt_lookup_orphan")
        cls.env["hr.employee"].create(
            {
                "name": "Orphan Employee",
                "user_id": cls.orphan.id,
                "company_id": cls.company.id,
            }
        )
        cls.Users = cls.env["res.users"].with_company(cls.company)

    # ------------------------------------------------------------------
    # Sale-order trips: direct manager first, Settings only as fallback
    # ------------------------------------------------------------------

    def _set_sale_order_approver(self, approver):
        self.company.with_context(skip_business_trip_role_sync=True).write(
            {
                "business_trip_sale_order_approver_id": (
                    approver.id if approver else False
                )
            }
        )

    def test_direct_manager_wins_over_settings_approver(self):
        self._set_sale_order_approver(self.settings_approver)
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.employee.id),
            self.line_manager.id,
        )

    def test_empty_settings_uses_direct_manager(self):
        self._set_sale_order_approver(None)
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.employee.id),
            self.line_manager.id,
        )

    def test_requester_without_manager_falls_back_to_settings(self):
        """No manager and no subordinates, so Settings is the only option."""
        self._set_sale_order_approver(self.settings_approver)
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.orphan.id),
            self.settings_approver.id,
        )

    def test_archived_manager_falls_back_to_settings(self):
        self._set_sale_order_approver(self.settings_approver)
        self.line_manager.action_archive()
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.employee.id),
            self.settings_approver.id,
        )

    def test_requester_is_not_assigned_as_own_approver(self):
        """Segregation of duties: the fallback approver cannot self-approve."""
        self._set_sale_order_approver(self.orphan)
        self.assertIsNone(
            self.Users.get_travel_approver_for_sale_order(self.orphan.id)
        )

    # ------------------------------------------------------------------
    # Standalone trips: Settings first, direct manager only as fallback
    # ------------------------------------------------------------------

    def _set_standalone_approver(self, approver):
        self.company.with_context(skip_business_trip_role_sync=True).write(
            {
                "business_trip_standalone_approver_id": (
                    approver.id if approver else False
                )
            }
        )

    def test_standalone_settings_approver_wins_over_direct_manager(self):
        self._set_standalone_approver(self.settings_approver)
        self.assertEqual(
            self.Users.get_travel_approver_for_standalone(self.employee.id),
            self.settings_approver.id,
        )

    def test_standalone_empty_settings_uses_direct_manager(self):
        self._set_standalone_approver(None)
        self.assertEqual(
            self.Users.get_travel_approver_for_standalone(self.employee.id),
            self.line_manager.id,
        )

    def test_standalone_requester_is_not_assigned_as_own_approver(self):
        """Segregation of duties: the approver cannot approve their own trip."""
        self._set_standalone_approver(self.settings_approver)
        self.assertEqual(
            self.Users.get_travel_approver_for_standalone(self.settings_approver.id),
            self.line_manager.id,
        )

    def test_standalone_archived_approver_falls_back_to_manager(self):
        """An unusable approver must not silently swallow the notification."""
        self._set_standalone_approver(self.settings_approver)
        self.settings_approver.action_archive()
        self.assertEqual(
            self.Users.get_travel_approver_for_standalone(self.employee.id),
            self.line_manager.id,
        )

    def test_standalone_returns_none_when_nothing_resolvable(self):
        """Callers turn None into a message instead of crashing the form."""
        self._set_standalone_approver(None)
        self.assertIsNone(
            self.Users.get_travel_approver_for_standalone(self.orphan.id)
        )

    # ------------------------------------------------------------------
    # Top of the hierarchy approves their own trips
    # ------------------------------------------------------------------

    def test_top_of_hierarchy_approves_own_sale_order_trip(self):
        """Every other candidate reports to them, so they self-approve."""
        self._set_sale_order_approver(self.settings_approver)
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.line_manager.id),
            self.line_manager.id,
        )

    def test_top_of_hierarchy_approves_own_standalone_trip(self):
        self._set_standalone_approver(self.settings_approver)
        self.assertEqual(
            self.Users.get_travel_approver_for_standalone(self.line_manager.id),
            self.line_manager.id,
        )

    def test_top_of_hierarchy_does_not_affect_other_requesters(self):
        self._set_sale_order_approver(self.settings_approver)
        self._set_standalone_approver(self.settings_approver)
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.employee.id),
            self.line_manager.id,
        )
        self.assertEqual(
            self.Users.get_travel_approver_for_standalone(self.employee.id),
            self.settings_approver.id,
        )

    def test_employee_without_manager_or_subordinates_never_self_approves(self):
        """A record that just never got a manager is not the top of anything."""
        self._set_sale_order_approver(self.settings_approver)
        self._set_standalone_approver(self.settings_approver)
        self.assertFalse(self.Users._is_top_of_hierarchy(self.orphan.id))
        self.assertEqual(
            self.Users.get_travel_approver_for_sale_order(self.orphan.id),
            self.settings_approver.id,
        )
        self.assertEqual(
            self.Users.get_travel_approver_for_standalone(self.orphan.id),
            self.settings_approver.id,
        )

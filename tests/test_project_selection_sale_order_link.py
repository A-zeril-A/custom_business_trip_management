from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProjectSelectionSaleOrderLink(TransactionCase):
    """A project that came from a quotation routes its trips like an order.

    Employees pick a project from a flat list where two projects can cover the
    same physical work under different orders. What decides the approval route
    is therefore the order behind the selected project, not the path the
    employee happened to start from.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        internal = cls.env.ref("base.group_user")
        requester = cls.env.ref(
            "custom_business_trip_management.group_business_trip_requester"
        )
        # Reading a sales order needs the salesman group for model access; the
        # module's own record rule then opens every order to a requester.
        salesman = cls.env.ref("sales_team.group_sale_salesman")

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

        cls.line_manager = create_user(
            "Link Line Manager", "bt_link_manager", [requester.id, salesman.id]
        )
        cls.settings_approver = create_user(
            "Link Settings Approver", "bt_link_settings", [requester.id, salesman.id]
        )
        cls.employee = create_user(
            "Link Employee", "bt_link_employee", [requester.id, salesman.id]
        )
        cls.employee_without_sales = create_user(
            "Link Employee No Sales", "bt_link_nosales", [requester.id]
        )
        manager_employee = cls.env["hr.employee"].create(
            {
                "name": "Link Line Manager",
                "user_id": cls.line_manager.id,
                "company_id": cls.company.id,
            }
        )
        for user in (
            cls.employee,
            cls.employee_without_sales,
            cls.settings_approver,
        ):
            cls.env["hr.employee"].create(
                {
                    "name": user.name,
                    "user_id": user.id,
                    "company_id": cls.company.id,
                    "parent_id": manager_employee.id,
                }
            )
        cls.company.with_context(skip_business_trip_role_sync=True).write(
            {"business_trip_standalone_approver_id": cls.settings_approver.id}
        )

        cls.partner = cls.env["res.partner"].create({"name": "Link Customer"})
        cls.product = cls.env["product.product"].create(
            {"name": "Link Service", "type": "service"}
        )
        cls.sale_order = cls._create_sale_order()
        cls.order_project = cls._create_order_project(
            "Link Order Project", cls.sale_order
        )
        cls.plain_project = cls.env["project.project"].create(
            {
                "name": "Link Plain Project",
                "company_id": cls.company.id,
                "privacy_visibility": "employees",
            }
        )
        # Cancelling an order clears the link from its projects, so the shape
        # that survives in the data is a project attached to an order that was
        # already cancelled. That is what this fixture reproduces.
        cancelled_order = cls._create_sale_order()
        cancelled_order._action_cancel()
        cls.cancelled_order_project = cls._create_order_project(
            "Link Cancelled Order Project", cancelled_order
        )

    @classmethod
    def _create_sale_order(cls):
        return cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "company_id": cls.company.id,
                "order_line": [
                    (0, 0, {"product_id": cls.product.id, "product_uom_qty": 1})
                ],
            }
        )

    @classmethod
    def _create_order_project(cls, name, sale_order):
        # allow_billable and a matching customer keep sale_line_id in place:
        # project.project drops it as soon as the two customers disagree.
        return cls.env["project.project"].create(
            {
                "name": name,
                "company_id": cls.company.id,
                "privacy_visibility": "employees",
                "allow_billable": True,
                "partner_id": cls.partner.id,
                "sale_line_id": sale_order.order_line[0].id,
            }
        )

    def _run_wizard(self, user, project, trip=None):
        values = {"project_id": project.id}
        if trip:
            values["trip_id"] = trip.id
        wizard = (
            self.env["business.trip.project.selection.wizard"]
            .with_user(user)
            .create(values)
        )
        action = wizard.action_create_trip_with_project()
        return self.env["business.trip"].browse(action["res_id"])

    def test_setup_project_resolves_its_sale_order(self):
        """Guards the fixture: everything below depends on these links."""
        self.assertEqual(self.order_project.sale_order_id, self.sale_order)
        self.assertFalse(self.plain_project.sale_order_id)
        # Proves the cancelled case exercises the guard rather than an
        # already empty link.
        self.assertEqual(
            self.cancelled_order_project.sale_order_id.state, "cancel"
        )

    # ------------------------------------------------------------------
    # Project backed by a sales order
    # ------------------------------------------------------------------

    def test_order_backed_project_links_the_order(self):
        trip = self._run_wizard(self.employee, self.order_project)
        self.assertEqual(trip.sale_order_id, self.sale_order)

    def test_order_backed_project_routes_to_the_direct_manager(self):
        """The whole point: the Settings approver no longer receives it."""
        trip = self._run_wizard(self.employee, self.order_project)
        self.assertEqual(trip.manager_id, self.line_manager)

    def test_order_backed_project_leaves_the_task_to_the_approval_step(self):
        """Sale-order trips get project and task when the organizer is set."""
        trip = self._run_wizard(self.employee, self.order_project)
        self.assertFalse(trip.selected_project_id)
        self.assertFalse(trip.selected_project_task_id)
        self.assertFalse(trip.business_trip_task_id)

    # ------------------------------------------------------------------
    # Cases that must keep the standalone route
    # ------------------------------------------------------------------

    def test_plain_project_keeps_the_standalone_route(self):
        trip = self._run_wizard(self.employee, self.plain_project)
        self.assertFalse(trip.sale_order_id)
        self.assertEqual(trip.manager_id, self.settings_approver)

    def test_plain_project_still_creates_its_placeholder_task(self):
        """The standalone approval step refuses to run without that task."""
        trip = self._run_wizard(self.employee, self.plain_project)
        self.assertEqual(trip.selected_project_id, self.plain_project)
        self.assertEqual(
            trip.selected_project_task_id.project_id, self.plain_project
        )

    def test_cancelled_order_keeps_the_standalone_route(self):
        """A cancelled order cannot carry a trip, so nothing is adopted."""
        trip = self._run_wizard(self.employee, self.cancelled_order_project)
        self.assertFalse(trip.sale_order_id)
        self.assertEqual(trip.manager_id, self.settings_approver)

    def test_requester_without_sales_access_keeps_the_standalone_route(self):
        """Linking an order they cannot read would hand them a broken form."""
        trip = self._run_wizard(self.employee_without_sales, self.order_project)
        self.assertFalse(trip.sale_order_id)
        self.assertEqual(trip.manager_id, self.settings_approver)

    # ------------------------------------------------------------------
    # A review in progress is never handed to somebody else
    # ------------------------------------------------------------------

    def test_relink_while_under_review_keeps_the_reviewer(self):
        trip = self.env["business.trip"].create(
            {
                "user_id": self.employee.id,
                "company_id": self.company.id,
                "manager_id": self.settings_approver.id,
                "trip_status": "submitted",
            }
        )
        self._run_wizard(self.settings_approver, self.order_project, trip=trip)
        self.assertFalse(trip.sale_order_id)
        self.assertEqual(trip.manager_id, self.settings_approver)

    def test_relink_before_review_adopts_the_order(self):
        """A draft request has not been reviewed, so the route can still change."""
        trip = self.env["business.trip"].create(
            {
                "user_id": self.employee.id,
                "company_id": self.company.id,
                "manager_id": self.settings_approver.id,
            }
        )
        self._run_wizard(self.employee, self.order_project, trip=trip)
        self.assertEqual(trip.sale_order_id, self.sale_order)
        self.assertEqual(trip.manager_id, self.line_manager)

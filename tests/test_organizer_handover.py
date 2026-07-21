from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOrganizerHandover(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        internal = cls.env.ref("base.group_user")
        requester = cls.env.ref(
            "custom_business_trip_management.group_business_trip_requester"
        )
        organizer = cls.env.ref(
            "custom_business_trip_management.group_business_trip_organizer"
        )

        def create_user(name, login, extra_groups=None):
            group_ids = [internal.id, requester.id]
            if extra_groups:
                group_ids.extend(extra_groups.ids)
            return cls.env["res.users"].with_context(no_reset_password=True).create(
                {
                    "name": name,
                    "login": login,
                    "email": f"{login}@example.com",
                    "company_id": cls.company.id,
                    "company_ids": [(6, 0, [cls.company.id])],
                    "groups_id": [(6, 0, group_ids)],
                }
            )

        cls.old_organizer = create_user(
            "Old Organizer",
            "bt_old_organizer",
            extra_groups=organizer,
        )
        cls.new_organizer = create_user(
            "New Organizer",
            "bt_new_organizer",
        )
        cls.employee = create_user("Handover Employee", "bt_handover_employee")
        cls.company.with_context(skip_business_trip_role_sync=True).write(
            {"business_trip_organizer_id": cls.old_organizer.id}
        )
        cls.company._sync_business_trip_role_group(
            "business_trip_organizer_id",
            "custom_business_trip_management.group_business_trip_organizer",
            previous_user=cls.env["res.users"],
        )

        cls.open_trip = cls.env["business.trip"].create(
            {
                "user_id": cls.employee.id,
                "company_id": cls.company.id,
                "organizer_id": cls.old_organizer.id,
                "trip_status": "pending_organization",
            }
        )
        cls.done_trip = cls.env["business.trip"].create(
            {
                "user_id": cls.employee.id,
                "company_id": cls.company.id,
                "organizer_id": cls.old_organizer.id,
                "trip_status": "completed",
            }
        )
        project = cls.env["project.project"].create(
            {
                "name": "Business Trip Handover Project",
                "company_id": cls.company.id,
                "allocated_hours": 40.0,
            }
        )
        task = cls.env["project.task"].with_context(
            mail_create_nolog=True,
            mail_notrack=True,
            tracking_disable=True,
        ).create(
            {
                "name": "Handover Trip Task",
                "project_id": project.id,
                "allocated_hours": 8.0,
                "user_ids": [(4, cls.old_organizer.id)],
            }
        )
        cls.open_trip.with_context(system_edit=True).write(
            {"business_trip_task_id": task.id}
        )

    def test_changing_active_organizer_hands_over_open_trips(self):
        self.company.write({"business_trip_organizer_id": self.new_organizer.id})

        self.assertEqual(self.open_trip.organizer_id, self.new_organizer)
        self.assertEqual(self.done_trip.organizer_id, self.old_organizer)
        self.assertIn(
            self.env.ref(
                "custom_business_trip_management.group_business_trip_organizer"
            ),
            self.new_organizer.groups_id,
        )
        self.assertNotIn(
            self.env.ref(
                "custom_business_trip_management.group_business_trip_organizer"
            ),
            self.old_organizer.groups_id,
        )
        self.assertIn(self.new_organizer, self.open_trip.business_trip_task_id.user_ids)
        self.assertNotIn(
            self.old_organizer,
            self.open_trip.business_trip_task_id.user_ids,
        )

        history = self.env["business.trip.assignment.history"].search(
            [
                ("trip_id", "=", self.open_trip.id),
                ("role", "=", "organizer"),
            ],
            limit=1,
        )
        self.assertTrue(history)
        self.assertEqual(history.previous_user_id, self.old_organizer)
        self.assertEqual(history.new_user_id, self.new_organizer)

from odoo.exceptions import ValidationError
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
        cls.organizer_group = cls.env.ref(
            "custom_business_trip_management.group_business_trip_organizer"
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

        cls.old_organizer = create_user("Old Organizer", "bt_old_organizer")
        cls.new_organizer = create_user("New Organizer", "bt_new_organizer")
        cls.second_organizer = create_user(
            "Second Organizer", "bt_second_organizer"
        )
        cls.employee = create_user("Handover Employee", "bt_handover_employee")
        cls.company.write(
            {"business_trip_organizer_ids": [(6, 0, [cls.old_organizer.id])]}
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

    def test_pool_sync_grants_group_to_all_members(self):
        self.company.write(
            {
                "business_trip_organizer_ids": [
                    (6, 0, [self.old_organizer.id, self.second_organizer.id])
                ]
            }
        )
        self.assertIn(self.organizer_group, self.old_organizer.groups_id)
        self.assertIn(self.organizer_group, self.second_organizer.groups_id)

    def test_swap_single_organizer_hands_over_open_trips(self):
        self.company.write(
            {"business_trip_organizer_ids": [(6, 0, [self.new_organizer.id])]}
        )

        self.assertEqual(self.open_trip.organizer_id, self.new_organizer)
        self.assertEqual(self.done_trip.organizer_id, self.old_organizer)
        self.assertIn(self.organizer_group, self.new_organizer.groups_id)
        self.assertNotIn(self.organizer_group, self.old_organizer.groups_id)
        self.assertIn(
            self.new_organizer, self.open_trip.business_trip_task_id.user_ids
        )
        self.assertNotIn(
            self.old_organizer, self.open_trip.business_trip_task_id.user_ids
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

    def test_removing_organizer_with_open_trips_and_ambiguous_pool_blocks(self):
        self.company.write(
            {
                "business_trip_organizer_ids": [
                    (6, 0, [
                        self.old_organizer.id,
                        self.new_organizer.id,
                        self.second_organizer.id,
                    ])
                ]
            }
        )
        with self.assertRaises(ValidationError):
            self.company.write(
                {
                    "business_trip_organizer_ids": [
                        (6, 0, [self.new_organizer.id, self.second_organizer.id])
                    ]
                }
            )

    def test_removing_organizer_without_open_trips_only_drops_group(self):
        self.company.write(
            {
                "business_trip_organizer_ids": [
                    (6, 0, [self.old_organizer.id, self.second_organizer.id])
                ]
            }
        )
        self.company.write(
            {"business_trip_organizer_ids": [(3, self.second_organizer.id)]}
        )
        self.assertNotIn(self.organizer_group, self.second_organizer.groups_id)
        self.assertIn(self.organizer_group, self.old_organizer.groups_id)
        self.assertEqual(self.open_trip.organizer_id, self.old_organizer)

    def test_approver_can_assign_any_pool_member(self):
        self.company.write(
            {
                "business_trip_organizer_ids": [
                    (6, 0, [self.old_organizer.id, self.second_organizer.id])
                ]
            }
        )
        wizard = self.env["business.trip.assign.organizer.wizard"].with_context(
            default_trip_id=self.open_trip.id
        ).create({"organizer_id": self.second_organizer.id})
        self.assertEqual(
            wizard.allowed_organizer_ids,
            self.old_organizer | self.second_organizer,
        )
        self.open_trip.with_context(system_edit=True).write(
            {"organizer_id": self.second_organizer.id}
        )
        self.assertEqual(self.open_trip.organizer_id, self.second_organizer)

    def test_assigning_organizer_outside_pool_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.open_trip.with_context(system_edit=True).write(
                {"organizer_id": self.employee.id}
            )

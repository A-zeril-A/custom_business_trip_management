from datetime import date, datetime, timedelta
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestExpenseFollowupTiming(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "employee_expense_reminder_delay": 3,
                "employee_expense_reminder_delay_type": "days",
                "employee_expense_digest_send_hour": 9,
                "expense_reminder_interval": 3,
                "expense_reminder_interval_type": "days",
                "organizer_expense_escalation_delay": 14,
                "organizer_expense_escalation_delay_type": "days",
                "organizer_expense_digest_send_hour": 9,
                "organizer_expense_reminder_interval": 7,
                "organizer_expense_reminder_interval_type": "days",
            }
        )
        internal_group = cls.env.ref("base.group_user")
        organizer_group = cls.env.ref(
            "custom_business_trip_management.group_business_trip_organizer"
        )
        requester_group = cls.env.ref(
            "custom_business_trip_management.group_business_trip_requester"
        )

        def create_user(name, login, groups=None):
            group_ids = [internal_group.id, requester_group.id]
            if groups:
                group_ids.extend(groups.ids)
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

        cls.employee = create_user("Timing Employee", "bt_timing_employee")
        cls.organizer = create_user(
            "Timing Organizer",
            "bt_timing_organizer",
            groups=organizer_group,
        )
        cls.env["hr.employee"].create(
            {
                "name": cls.employee.name,
                "user_id": cls.employee.id,
                "company_id": cls.company.id,
            }
        )
        cls.company.with_context(skip_business_trip_role_sync=True).write(
            {"business_trip_organizer_ids": [(6, 0, [cls.organizer.id])]}
        )
        cls.company._sync_business_trip_organizer_pool_group(
            cls.env["res.users"]
        )

    def _create_trip(self, **vals):
        defaults = {
            "user_id": self.employee.id,
            "company_id": self.company.id,
            "trip_status": "pending_organization",
            "organizer_id": self.organizer.id,
        }
        defaults.update(vals)
        return self.env["business.trip"].create(defaults)

    def test_organizer_confirm_stays_in_organization_done(self):
        trip = self._create_trip()
        trip.business_trip_data_id.write(
            {
                "travel_start_date": date.today() + timedelta(days=10),
                "travel_end_date": date.today() + timedelta(days=12),
            }
        )
        trip.write(
            {
                "organizer_trip_plan_details": "Train and hotel booked.",
                "organizer_planned_cost": 250.0,
            }
        )
        trip.with_user(self.organizer).with_context(
            from_assigned_to_me=True
        ).action_organizer_confirm_planning()

        self.assertEqual(trip.trip_status, "organization_done")
        self.assertFalse(trip.actual_start_date)
        self.assertFalse(trip.actual_end_date)
        self.assertFalse(trip.expense_followup_start_date)

    def test_future_trip_is_not_opened_for_expense_followup(self):
        trip = self._create_trip(trip_status="organization_done")
        trip.business_trip_data_id.write(
            {
                "travel_start_date": date.today() + timedelta(days=10),
                "travel_end_date": date.today() + timedelta(days=12),
            }
        )
        trip.write({"organization_done_date": fields_now_minus(days=5)})

        self.env["business.trip"]._activate_post_travel_expense_followup()
        self.assertEqual(trip.trip_status, "organization_done")
        self.assertFalse(trip.expense_followup_start_date)

    def test_past_trip_opens_followup_with_post_travel_anchor(self):
        trip = self._create_trip(trip_status="organization_done")
        trip.business_trip_data_id.write(
            {
                "travel_start_date": date.today() - timedelta(days=5),
                "travel_end_date": date.today() - timedelta(days=3),
            }
        )

        self.env["business.trip"]._activate_post_travel_expense_followup()
        self.assertEqual(trip.trip_status, "completed_waiting_expense")
        self.assertTrue(trip.expense_followup_start_date)

        due = trip._get_employee_expense_followup_due_datetime()
        self.assertTrue(due)
        self.assertGreaterEqual(due.date(), trip.travel_end_date)

    def test_missing_end_date_never_opens_followup(self):
        trip = self._create_trip(
            trip_status="completed_waiting_expense",
            expense_followup_start_date=fields_now_minus(days=10),
        )
        self.env["business.trip"]._activate_post_travel_expense_followup()
        self.assertEqual(trip.trip_status, "organization_done")
        self.assertFalse(trip.expense_followup_start_date)

    def test_cron_does_not_email_future_trips(self):
        trip = self._create_trip(trip_status="organization_done")
        trip.business_trip_data_id.write(
            {
                "travel_start_date": date.today() + timedelta(days=10),
                "travel_end_date": date.today() + timedelta(days=12),
            }
        )
        with patch.object(
            type(self.env["business.trip"]),
            "_queue_expense_digest_email",
            return_value=True,
        ) as queue_mail:
            self.env["business.trip"]._cron_send_expense_submission_reminders()
        self.assertEqual(trip.trip_status, "organization_done")
        queue_mail.assert_not_called()


def fields_now_minus(days=0):
    return datetime.now() - timedelta(days=days)

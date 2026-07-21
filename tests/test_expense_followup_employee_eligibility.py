from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestExpenseFollowupEmployeeEligibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "employee_expense_reminder_delay": 0,
                "employee_expense_reminder_delay_type": "days",
                "employee_expense_digest_send_hour": 9,
                "expense_reminder_interval": 7,
                "expense_reminder_interval_type": "days",
                "organizer_expense_escalation_delay": 0,
                "organizer_expense_escalation_delay_type": "days",
                "organizer_expense_digest_send_hour": 9,
                "organizer_expense_reminder_interval": 7,
                "organizer_expense_reminder_interval_type": "days",
            }
        )

        internal_group = cls.env.ref("base.group_user")

        def create_user(name, login):
            return cls.env["res.users"].with_context(no_reset_password=True).create(
                {
                    "name": name,
                    "login": login,
                    "email": f"{login}@example.com",
                    "company_id": cls.company.id,
                    "company_ids": [(6, 0, [cls.company.id])],
                    "groups_id": [(6, 0, [internal_group.id])],
                }
            )

        cls.active_user = create_user(
            "Active Follow-up Employee",
            "expense_followup_active",
        )
        cls.archived_employee_user = create_user(
            "Archived Follow-up Employee",
            "expense_followup_archived_employee",
        )
        cls.inactive_user = create_user(
            "Inactive Follow-up User",
            "expense_followup_inactive_user",
        )
        cls.reviewer = create_user(
            "Expense Follow-up Reviewer",
            "expense_followup_reviewer",
        )

        Employee = cls.env["hr.employee"]
        Employee.create(
            {
                "name": cls.active_user.name,
                "user_id": cls.active_user.id,
                "company_id": cls.company.id,
            }
        )
        Employee.with_context(active_test=False).create(
            {
                "name": cls.archived_employee_user.name,
                "user_id": cls.archived_employee_user.id,
                "company_id": cls.company.id,
                "active": False,
            }
        )
        Employee.create(
            {
                "name": cls.inactive_user.name,
                "user_id": cls.inactive_user.id,
                "company_id": cls.company.id,
            }
        )
        cls.inactive_user.active = False

        cls.now = datetime(2026, 1, 5, 9, 0, 0)
        followup_start = cls.now - timedelta(days=30)
        past_end = (cls.now - timedelta(days=10)).date()
        Trip = cls.env["business.trip"]
        cls.active_trip = Trip.create(
            {
                "user_id": cls.active_user.id,
                "company_id": cls.company.id,
                "trip_status": "completed_waiting_expense",
                "expense_followup_start_date": followup_start,
            }
        )
        cls.active_trip.business_trip_data_id.write(
            {
                "travel_start_date": past_end - timedelta(days=2),
                "travel_end_date": past_end,
            }
        )
        cls.archived_employee_trip = Trip.create(
            {
                "user_id": cls.archived_employee_user.id,
                "company_id": cls.company.id,
                "trip_status": "completed_waiting_expense",
                "expense_followup_start_date": followup_start,
            }
        )
        cls.archived_employee_trip.business_trip_data_id.write(
            {
                "travel_start_date": past_end - timedelta(days=2),
                "travel_end_date": past_end,
            }
        )
        cls.inactive_user_trip = Trip.create(
            {
                "user_id": cls.inactive_user.id,
                "company_id": cls.company.id,
                "trip_status": "completed_waiting_expense",
                "expense_followup_start_date": followup_start,
            }
        )
        cls.inactive_user_trip.business_trip_data_id.write(
            {
                "travel_start_date": past_end - timedelta(days=2),
                "travel_end_date": past_end,
            }
        )
        cls.trips = (
            cls.active_trip
            | cls.archived_employee_trip
            | cls.inactive_user_trip
        )

    def test_archived_employee_is_excluded_from_digest_emails(self):
        eligible_trips = self.trips._filter_expense_followup_eligible_trips()
        self.assertEqual(eligible_trips, self.active_trip)

        last_mail = self.env["mail.mail"].sudo().search([], order="id desc", limit=1)
        with patch.object(
            type(self.env["business.trip"]),
            "_get_expense_review_user",
            return_value=self.reviewer,
        ):
            self.trips._send_employee_expense_followup_digests(self.now)

            employee_mails = self.env["mail.mail"].sudo().search(
                [("id", ">", last_mail.id or 0)]
            )
            self.assertEqual(len(employee_mails), 1)
            self.assertIn(self.active_user.name, str(employee_mails.body_html))
            self.assertNotIn(
                self.archived_employee_user.name,
                str(employee_mails.body_html),
            )
            self.assertNotIn(self.inactive_user.name, str(employee_mails.body_html))
            self.assertEqual(
                self.active_trip.employee_expense_reminder_sent_date,
                self.now,
            )
            self.assertFalse(
                self.archived_employee_trip.employee_expense_reminder_sent_date
            )
            self.assertFalse(
                self.inactive_user_trip.employee_expense_reminder_sent_date
            )

            last_mail = employee_mails[-1]
            self.trips._send_organizer_expense_followup_digests(self.now)

        reviewer_mails = self.env["mail.mail"].sudo().search(
            [("id", ">", last_mail.id)]
        )
        self.assertEqual(len(reviewer_mails), 1)
        self.assertEqual(
            reviewer_mails.subject,
            "Expense Follow-up Digest: 1 pending trip",
        )
        self.assertIn(self.active_user.name, str(reviewer_mails.body_html))
        self.assertNotIn(
            self.archived_employee_user.name,
            str(reviewer_mails.body_html),
        )
        self.assertNotIn(self.inactive_user.name, str(reviewer_mails.body_html))
        self.assertEqual(self.active_trip.last_expense_reminder_date, self.now)
        self.assertFalse(self.archived_employee_trip.last_expense_reminder_date)
        self.assertFalse(self.inactive_user_trip.last_expense_reminder_date)

    def test_archived_employee_followup_activities_are_removed(self):
        todo = self.env.ref("mail.mail_activity_data_todo")
        activity_model_id = self.env["ir.model"]._get_id("business.trip")
        Activity = self.env["mail.activity"].sudo().with_context(
            mail_activity_quick_update=True
        )
        for trip in self.trips:
            Activity.create(
                {
                    "activity_type_id": todo.id,
                    "summary": trip._get_employee_expense_followup_activity_summary(),
                    "res_model_id": activity_model_id,
                    "res_id": trip.id,
                    "user_id": trip.user_id.id,
                    "date_deadline": self.now.date(),
                }
            )

        self.trips._sync_employee_expense_followup_activity()

        remaining_activities = self.env["mail.activity"].sudo().search(
            [
                ("res_model", "=", "business.trip"),
                ("res_id", "in", self.trips.ids),
                (
                    "summary",
                    "=",
                    self.active_trip._get_employee_expense_followup_activity_summary(),
                ),
            ]
        )
        self.assertEqual(remaining_activities.res_id, self.active_trip.id)

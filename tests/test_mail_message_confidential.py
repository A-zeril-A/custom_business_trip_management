# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMailMessageConfidential(TransactionCase):
    """Guard the confidential mail.message filter after the perf rework:

    - the simplified search domain must keep the historical visibility
      semantics (non-confidential visible to all, confidential only to
      recipients, privileged users see everything);
    - the supporting partial index must exist.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.internal_user = cls.env["res.users"].create(
            {
                "name": "Conf Test User",
                "login": "conf_test_user",
                "email": "conf_test_user@example.com",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.other_user = cls.env["res.users"].create(
            {
                "name": "Conf Other User",
                "login": "conf_other_user",
                "email": "conf_other_user@example.com",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        partner = cls.env["res.partner"].create({"name": "Conf Msg Anchor"})
        Message = cls.env["mail.message"]
        cls.msg_plain = Message.create(
            {
                "model": "res.partner",
                "res_id": partner.id,
                "body": "plain message",
            }
        )
        cls.msg_conf_for_user = Message.create(
            {
                "model": "res.partner",
                "res_id": partner.id,
                "body": "confidential for internal_user",
                "confidential": True,
                "confidential_recipients": [
                    (6, 0, [cls.internal_user.partner_id.id])
                ],
            }
        )
        cls.msg_conf_other = Message.create(
            {
                "model": "res.partner",
                "res_id": partner.id,
                "body": "confidential for someone else",
                "confidential": True,
                "confidential_recipients": [
                    (6, 0, [cls.other_user.partner_id.id])
                ],
            }
        )
        cls.all_ids = (
            cls.msg_plain | cls.msg_conf_for_user | cls.msg_conf_other
        ).ids

    def _visible_ids(self, user):
        # sudo() keeps env.user, so the confidential filter still keys on the
        # user while bypassing mail.message's own read ACLs (not under test).
        return (
            self.env["mail.message"]
            .with_user(user)
            .sudo()
            .search([("id", "in", self.all_ids)])
            .ids
        )

    def test_recipient_sees_own_confidential_only(self):
        visible = self._visible_ids(self.internal_user)
        self.assertIn(self.msg_plain.id, visible)
        self.assertIn(self.msg_conf_for_user.id, visible)
        self.assertNotIn(self.msg_conf_other.id, visible)

    def test_non_recipient_sees_only_plain(self):
        third = self.env["res.users"].create(
            {
                "name": "Conf Third User",
                "login": "conf_third_user",
                "email": "conf_third_user@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        visible = self._visible_ids(third)
        self.assertIn(self.msg_plain.id, visible)
        self.assertNotIn(self.msg_conf_for_user.id, visible)
        self.assertNotIn(self.msg_conf_other.id, visible)

    def test_privileged_user_sees_everything(self):
        admin = self.env.ref("base.user_admin")
        visible = self._visible_ids(admin)
        self.assertEqual(sorted(visible), sorted(self.all_ids))

    def test_simplified_domain_matches_legacy_domain(self):
        """The rewritten domain must select exactly the same rows as the
        historical one, over ALL messages in the database."""
        Message = self.env["mail.message"].sudo()
        pid = self.internal_user.partner_id.id
        legacy = Message.search(
            [
                "|",
                ("confidential", "=", False),
                "&",
                ("confidential", "=", True),
                ("confidential_recipients", "in", [pid]),
            ],
            order="id",
        )
        simplified = Message.search(
            [
                "|",
                ("confidential", "!=", True),
                ("confidential_recipients", "in", [pid]),
            ],
            order="id",
        )
        self.assertEqual(legacy.ids, simplified.ids)

    def test_partial_index_exists(self):
        self.env.cr.execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE tablename = 'mail_message' "
            "AND indexname = 'mail_message_confidential_true_idx'"
        )
        row = self.env.cr.fetchone()
        self.assertTrue(row, "partial index on confidential=True is missing")
        self.assertIn("WHERE (confidential IS TRUE)", row[0])

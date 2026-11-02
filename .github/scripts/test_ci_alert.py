"""ci_alert's rules, without network: python3 -m unittest discover -s .github/scripts -v"""

import unittest

import ci_alert

SHA = "a" * 40


def run(**overrides):
    base = {
        "id": 10,
        "workflow_id": 1,
        "name": "CI",
        "head_branch": "main",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_sha": SHA,
        "run_attempt": 1,
        "head_repository": {"full_name": "Souhib/Majlisna"},
    }
    base.update(overrides)
    return base


class PayloadTest(unittest.TestCase):
    def test_a_failure_alerts(self):
        message = ci_alert.payload(run(conclusion="failure"), None)
        self.assertIn("🔴 CI en échec", message["embeds"][0]["title"])
        self.assertEqual(message["allowed_mentions"], {"parse": []})

    def test_a_success_after_a_failure_reports_the_recovery(self):
        message = ci_alert.payload(run(), "failure")
        self.assertIn("🟢 CI rétablie", message["embeds"][0]["title"])

    def test_routine_green_runs_and_cancellations_are_quiet(self):
        self.assertIsNone(ci_alert.payload(run(), "success"))
        self.assertIsNone(ci_alert.payload(run(conclusion="cancelled"), "success"))

    def test_runs_outside_main_or_from_a_fork_are_never_sent(self):
        self.assertIsNone(ci_alert.payload(run(conclusion="failure", head_branch="feature"), None))
        self.assertIsNone(
            ci_alert.payload(run(conclusion="failure", head_repository={"full_name": "someone/Majlisna"}), None)
        )
        self.assertIsNone(ci_alert.payload(run(conclusion="failure", event="pull_request"), None))

    def test_a_delivery_test_is_labelled(self):
        message = ci_alert.payload(run(), None, test=True)
        self.assertTrue(message["embeds"][0]["title"].startswith("[TEST"))

    def test_only_a_discord_webhook_is_accepted(self):
        with self.assertRaises(ValueError):
            ci_alert.send("https://example.com/api/webhooks/1/x", {})
        with self.assertRaises(ValueError):
            ci_alert.send("http://discord.com/api/webhooks/1/x", {})


if __name__ == "__main__":
    unittest.main()

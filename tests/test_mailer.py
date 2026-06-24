import unittest
from unittest.mock import patch

from flask import Flask


class MailerTests(unittest.TestCase):
    def test_mail_is_not_delivered_in_flask_testing_mode(self):
        from services.mailer import send_mail

        app = Flask(__name__)
        app.config["TESTING"] = True

        with app.app_context(), patch("services.mailer._send_with_sendmail") as sendmail:
            delivered = send_mail("Testmail", "Skal ikke sendes.", recipient="api@example.com")

        self.assertFalse(delivered)
        sendmail.assert_not_called()


if __name__ == "__main__":
    unittest.main()

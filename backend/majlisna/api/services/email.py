import asyncio

import resend
from loguru import logger

from majlisna.settings import Settings

_FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def _base_layout(content: str) -> str:
    """Wrap content in the shared email layout (table-based for Outlook compatibility)."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>Majlisna</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f5;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#f4f4f5;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="max-width:520px;width:100%;background-color:#ffffff;border-radius:12px;
                      border:1px solid #e4e4e7;overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="padding:32px 40px 24px;border-bottom:1px solid #f4f4f5;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <span style="font-family:{_FONT_STACK};font-size:20px;font-weight:700;
                                 color:#10b981;letter-spacing:-0.3px;">
                      Majlisna
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Content -->
          <tr>
            <td style="padding:32px 40px;">
              {content}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px;border-top:1px solid #f4f4f5;">
              <p style="font-family:{_FONT_STACK};font-size:12px;line-height:18px;
                        color:#a1a1aa;margin:0;">
                🕌 Majlisna &mdash; Islamic Party Games<br>
                You received this email because an action was performed on your account.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _cta_button(url: str, label: str) -> str:
    """Render a call-to-action button (Outlook-compatible with VML fallback)."""
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td align="center" style="padding:8px 0 16px;">
      <!--[if mso]>
      <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" href="{url}"
        style="height:44px;v-text-anchor:middle;width:220px;" arcsize="18%"
        strokecolor="#059669" fillcolor="#10b981">
        <w:anchorlock/>
        <center style="color:#ffffff;font-family:{_FONT_STACK};font-size:14px;font-weight:600;">
          {label}
        </center>
      </v:roundrect>
      <![endif]-->
      <!--[if !mso]><!-->
      <a href="{url}" target="_blank"
         style="display:inline-block;background-color:#10b981;color:#ffffff;
                font-family:{_FONT_STACK};font-size:14px;font-weight:600;
                text-decoration:none;padding:12px 32px;border-radius:8px;
                line-height:20px;mso-hide:all;">
        {label}
      </a>
      <!--<![endif]-->
    </td>
  </tr>
</table>"""


class EmailService:
    """Email service using Resend API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.resend_api_key:
            resend.api_key = settings.resend_api_key
        self._configured = bool(settings.resend_api_key)

    async def send_password_reset_email(self, to_email: str, username: str, reset_url: str) -> bool:
        """Send password reset email."""
        content = f"""\
<h1 style="font-family:{_FONT_STACK};font-size:18px;font-weight:600;
           color:#18181b;margin:0 0 16px;line-height:26px;">
  🔐 Reset your password
</h1>
<p style="font-family:{_FONT_STACK};font-size:14px;line-height:22px;
          color:#3f3f46;margin:0 0 24px;">
  Hi {username}, we received a request to reset the password for your Majlisna account.
  Click the button below to choose a new one.
</p>
{_cta_button(reset_url, "Reset Password 🔑")}
<p style="font-family:{_FONT_STACK};font-size:13px;line-height:20px;
          color:#71717a;margin:16px 0 0;">
  This link expires in <strong>1 hour</strong>. If you didn't request a password reset,
  you can safely ignore this email &mdash; your password will remain unchanged.
</p>"""
        return await self._send(to_email, "Reset your password", _base_layout(content))

    async def send_verification_email(self, to_email: str, username: str, verify_url: str) -> bool:
        """Send email verification."""
        content = f"""\
<h1 style="font-family:{_FONT_STACK};font-size:18px;font-weight:600;
           color:#18181b;margin:0 0 16px;line-height:26px;">
  ✉️ Verify your email
</h1>
<p style="font-family:{_FONT_STACK};font-size:14px;line-height:22px;
          color:#3f3f46;margin:0 0 4px;">
  Assalamu alaykum {username} 👋
</p>
<p style="font-family:{_FONT_STACK};font-size:14px;line-height:22px;
          color:#3f3f46;margin:0 0 24px;">
  Welcome to Majlisna! 🎉 Please confirm your email address so you can start
  playing with your friends.
</p>
{_cta_button(verify_url, "Verify Email ✅")}
<p style="font-family:{_FONT_STACK};font-size:13px;line-height:20px;
          color:#71717a;margin:16px 0 0;">
  This link expires in <strong>24 hours</strong>. If you didn't create a
  Majlisna account, you can safely ignore this email.
</p>"""
        return await self._send(to_email, "Verify your email", _base_layout(content))

    async def _send(self, to_email: str, subject: str, html: str) -> bool:
        """Send an email via Resend API."""
        if not self._configured:
            logger.warning("Email service not configured (no RESEND_API_KEY). Skipping email to {to}", to=to_email)
            return False
        try:
            # The Resend SDK call is synchronous/blocking; run it off the event
            # loop so a slow email round-trip doesn't stall other requests on
            # hot auth paths (register, password reset).
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": self.settings.from_email,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
            logger.debug("Email sent to {to}: {subject}", to=to_email, subject=subject)
            return True
        except Exception:
            logger.exception("Failed to send email to {to}", to=to_email)
            return False

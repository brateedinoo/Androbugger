"""Email notifications via aiosmtplib — no-op when smtp_host is empty."""
import logging

from androbugger.config import settings
from androbugger.db.database import get_db

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body_html: str) -> None:
    """Send an HTML email. Does nothing if smtp_host is not configured."""
    if not settings.smtp_host:
        logger.debug("SMTP not configured — skipping email to %s", to)
        return

    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg.attach(MIMEText(body_html, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            start_tls=True,
        )
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)


async def send_session_digest(session_id: str, to_email: str) -> None:
    """Send an HTML summary of a resolved diagnostic session."""
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT id, device_serial, device_model, firmware_version,"
            " root_cause, applied_fix, resolution_notes, completed_at"
            " FROM diagnostic_sessions WHERE id=?",
            (session_id,),
        )).fetchone()

    if not row:
        return

    body = f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:auto">
<h2>Diagnostic Report — {row['device_serial']}</h2>
<table style="width:100%;border-collapse:collapse">
  <tr><td style="padding:4px;font-weight:bold;width:160px">Device</td>
      <td>{row['device_model'] or row['device_serial']}</td></tr>
  <tr><td style="padding:4px;font-weight:bold">Firmware</td>
      <td>{row['firmware_version'] or 'Unknown'}</td></tr>
  <tr><td style="padding:4px;font-weight:bold">Completed</td>
      <td>{row['completed_at'] or 'N/A'}</td></tr>
  <tr><td style="padding:4px;font-weight:bold;vertical-align:top">Root Cause</td>
      <td>{row['root_cause'] or 'Not determined'}</td></tr>
  <tr><td style="padding:4px;font-weight:bold;vertical-align:top">Applied Fix</td>
      <td>{row['applied_fix'] or 'None'}</td></tr>
  <tr><td style="padding:4px;font-weight:bold;vertical-align:top">Notes</td>
      <td>{row['resolution_notes'] or ''}</td></tr>
</table>
<p style="color:#888;font-size:0.85em">Sent by Androbugger — Session {session_id}</p>
</body></html>
"""
    model = row["device_model"] or row["device_serial"]
    await send_email(to_email, f"[Androbugger] Diagnostic complete — {model}", body)

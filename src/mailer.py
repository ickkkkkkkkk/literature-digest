"""
Email sender via SMTP (default: QQ Mail).
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def send(
    html_body: str,
    date: str,
    *,
    smtp_host: str,
    smtp_port: int,
    sender: str,
    password: str,
    receiver: str,
) -> bool:
    """
    Send the daily digest via email.

    Args:
        html_body: full HTML report content
        date: report date string
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port (SSL)
        sender: sender email address
        password: SMTP password / authorization code
        receiver: recipient email address

    Returns:
        True if sent successfully
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"文献日报 — {date}"
    msg["From"] = sender
    msg["To"] = receiver

    # Attach HTML part
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        return True
    except Exception as e:
        print(f"[mailer] Failed to send email: {e}")
        return False

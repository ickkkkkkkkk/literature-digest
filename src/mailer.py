"""
Email sender via SMTP (default: QQ Mail).
"""

import smtplib
import ssl
import time
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
    max_retries: int = 3,
    label: str = "",
) -> bool:
    """
    Send the daily digest via email with automatic retry on failure.

    Args:
        html_body: full HTML report content
        date: report date string
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port (SSL)
        sender: sender email address
        password: SMTP password / authorization code
        receiver: recipient email address
        max_retries: maximum send attempts (default 3)
        label: research direction label for email subject (e.g. "脊柱骨科+生信")

    Returns:
        True if sent successfully
    """
    subject = f"{label} 文献日报 — {date}" if label else f"文献日报 — {date}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                server.login(sender, password)
                server.sendmail(sender, receiver, msg.as_string())
            if attempt > 1:
                print(f"[mailer] Sent successfully on attempt {attempt}")
            return True
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt  # 2s, 4s, 8s
                print(f"[mailer] Attempt {attempt}/{max_retries} failed: {e}")
                print(f"[mailer] Retrying in {wait}s...")
                time.sleep(wait)

    print(f"[mailer] All {max_retries} attempts failed: {last_error}")
    return False

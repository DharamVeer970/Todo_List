"""Once-a-day email nudge about overdue tasks — reaches you with the app closed.

Off unless configured. To enable (Gmail needs an App Password, not your login):

    set TODO_SMTP_HOST=smtp.gmail.com
    set TODO_SMTP_PORT=587
    set TODO_SMTP_USER=you@gmail.com
    set TODO_SMTP_PASS=your-app-password
    set TODO_EMAIL_TO=you@gmail.com
    set TODO_EMAIL_HOUR=8
"""
import os
import smtplib
import threading
import time
from datetime import datetime
from email.message import EmailMessage

import db

HOST = os.environ.get("TODO_SMTP_HOST")
PORT = int(os.environ.get("TODO_SMTP_PORT") or 587)
USER = os.environ.get("TODO_SMTP_USER", "")
PASSWORD = os.environ.get("TODO_SMTP_PASS", "")
TO = os.environ.get("TODO_EMAIL_TO") or USER
HOUR = int(os.environ.get("TODO_EMAIL_HOUR") or 8)

configured = bool(HOST and TO)


def send(tasks):
    msg = EmailMessage()
    msg["Subject"] = f"{len(tasks)} overdue task{'s' if len(tasks) != 1 else ''}"
    msg["From"] = USER or TO
    msg["To"] = TO
    msg.set_content(
        "You missed these:\n\n"
        + "\n".join(f"  - {t['title']}  (due {t['due']}, {t['priority']} priority)" for t in tasks)
    )
    smtp = smtplib.SMTP_SSL(HOST, PORT) if PORT == 465 else smtplib.SMTP(HOST, PORT)
    with smtp:
        if PORT != 465:
            smtp.starttls()
        if USER:
            smtp.login(USER, PASSWORD)
        smtp.send_message(msg)


def tick():
    """One check. Sends at most one mail per day, once past TODO_EMAIL_HOUR."""
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d")
    if now.hour < HOUR or db.meta_get("last_email") == stamp:
        return 0
    late = db.overdue()
    if late:
        send(late)
        print(f"[mail] nudged {TO} about {len(late)} overdue task(s)", flush=True)
    db.meta_set("last_email", stamp)  # one attempt per day, empty or not
    return len(late)


def _loop():
    while True:
        try:
            tick()
        except Exception as e:  # a dead mail server must never take the app down
            print(f"[mail] skipped: {e}", flush=True)
        time.sleep(900)


def start():
    if not configured:
        print("[mail] email nudges off - set TODO_SMTP_HOST and TODO_EMAIL_TO to enable", flush=True)
        return
    threading.Thread(target=_loop, daemon=True).start()
    print(f"[mail] daily nudge to {TO} from {HOUR:02d}:00", flush=True)

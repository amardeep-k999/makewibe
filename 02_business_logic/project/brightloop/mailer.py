"""Save demo emails locally, or send them through a configured SMTP server."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4
from flask import current_app


def send_mail(recipient, subject, body):
    message = EmailMessage()
    message['From'] = os.environ.get('MAIL_FROM', 'brightloop@example.com')
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)
    if current_app.config['MAIL_MODE'] == 'outbox':
        folder = Path(current_app.instance_path) / 'outbox'
        folder.mkdir(exist_ok=True)
        (folder / f'{uuid4().hex}.eml').write_bytes(message.as_bytes())
        return 'Saved in the local demo inbox (not delivered externally).'
    if current_app.config['MAIL_MODE'] != 'smtp':
        raise ValueError('MAIL_MODE must be outbox or smtp.')
    host = os.environ.get('SMTP_HOST')
    if not host:
        raise ValueError('Configure SMTP_HOST before sending real email.')
    with smtplib.SMTP(host, int(os.environ.get('SMTP_PORT', '587')), timeout=15) as server:
        server.starttls(context=ssl.create_default_context())
        if os.environ.get('SMTP_USER'):
            server.login(os.environ['SMTP_USER'], os.environ.get('SMTP_PASSWORD', ''))
        server.send_message(message)
    return 'Email sent through SMTP.'

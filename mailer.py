"""Transactional email adapters. Credentials belong in environment variables."""
import json
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class MailUnavailable(Exception):
    pass


def public_base(config):
    value = str(config.get('PUBLIC_BASE_URL', '')).rstrip('/')
    parsed = urlsplit(value)
    local = parsed.hostname in {'localhost', '127.0.0.1', '::1'}
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query
            or parsed.fragment or parsed.path or any(c.isspace() for c in value)
            or (parsed.scheme != 'https' and not
                (parsed.scheme == 'http' and local and not config.get('PRODUCTION')))):
        raise MailUnavailable('PUBLIC_BASE_URL must be a trusted HTTPS origin.')
    return value


def mail_ready(config):
    try:
        public_base(config)
        if config.get('TESTING') and callable(config.get('MAIL_SENDER')):
            return True
        provider = config.get('MAIL_PROVIDER', '').lower()
        sender = config.get('MAIL_FROM', '')
        if not sender or '\n' in sender or '\r' in sender:
            return False
        if provider == 'resend':
            return bool(config.get('RESEND_API_KEY'))
        if provider == 'smtp':
            return bool(config.get('SMTP_HOST')) and config.get('SMTP_SECURITY') in {'starttls', 'ssl'}
    except (MailUnavailable, ValueError):
        pass
    return False


def send_mail(config, recipient, subject, body):
    if not mail_ready(config):
        raise MailUnavailable('Email is not configured.')
    if any(c in recipient for c in '\r\n'):
        raise MailUnavailable('Invalid recipient.')
    # Test-only injection; production never prints or exposes message contents.
    if config.get('TESTING') and callable(config.get('MAIL_SENDER')):
        config['MAIL_SENDER'](recipient, subject, body)
        return
    try:
        if config['MAIL_PROVIDER'].lower() == 'resend':
            data = json.dumps({'from': config['MAIL_FROM'], 'to': [recipient],
                               'subject': subject, 'text': body}).encode()
            request = Request('https://api.resend.com/emails', data=data, method='POST',
                              headers={'Authorization': 'Bearer ' + config['RESEND_API_KEY'],
                                       'Content-Type': 'application/json',
                                       'User-Agent': 'NaV12/1.0'})
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read(65536))
                if not payload.get('id'):
                    raise MailUnavailable('Provider did not accept the email.')
            return
        message = EmailMessage()
        message['From'] = config['MAIL_FROM']
        message['To'] = recipient
        message['Subject'] = subject
        message.set_content(body)
        secure = config['SMTP_SECURITY'] == 'ssl'
        cls = smtplib.SMTP_SSL if secure else smtplib.SMTP
        options = {'timeout': 10}
        if secure:
            options['context'] = ssl.create_default_context()
        with cls(config['SMTP_HOST'], int(config['SMTP_PORT']), **options) as server:
            if not secure:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if config.get('SMTP_USERNAME'):
                server.login(config['SMTP_USERNAME'], config.get('SMTP_PASSWORD', ''))
            if server.send_message(message):
                raise MailUnavailable('Provider rejected a recipient.')
    except Exception:
        # Do not propagate SMTP response bodies, API keys, addresses or URLs to logs.
        raise MailUnavailable('Email delivery failed.') from None

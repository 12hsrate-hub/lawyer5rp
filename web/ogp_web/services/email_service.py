from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


LOGGER = logging.getLogger(__name__)


@dataclass
class EmailDeliveryResult:
    sent: bool


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "")
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_public_base_url(request_base_url: str) -> str:
    configured = os.getenv("OGP_WEB_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    return request_base_url.rstrip("/")


def send_verification_email(*, recipient: str, username: str, verification_url: str) -> EmailDeliveryResult:
    return _send_email(
        recipient=recipient,
        subject="Подтверждение регистрации",
        body_lines=[
            f"Здравствуйте, {username}!",
            "",
            "Для завершения регистрации подтвердите email по ссылке:",
            verification_url,
            "",
            "Если это были не вы, просто проигнорируйте письмо.",
        ],
    )


def send_password_reset_email(*, recipient: str, username: str, reset_url: str) -> EmailDeliveryResult:
    return _send_email(
        recipient=recipient,
        subject="Сброс пароля",
        body_lines=[
            f"Здравствуйте, {username}!",
            "",
            "Для установки нового пароля перейдите по ссылке:",
            reset_url,
            "",
            "Если вы не запрашивали сброс пароля, просто проигнорируйте письмо.",
        ],
    )


def _send_email(*, recipient: str, subject: str, body_lines: list[str]) -> EmailDeliveryResult:
    host = os.getenv("SMTP_HOST", "").strip()
    username_env = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip() or username_env
    sender_name = os.getenv("SMTP_FROM_NAME", "").strip() or "OGP Builder Web"
    port = int(os.getenv("SMTP_PORT", "587") or "587")
    use_ssl = _env_flag("SMTP_USE_SSL")
    use_starttls = _env_flag("SMTP_USE_TLS", default=not use_ssl)

    if not host or not sender:
        LOGGER.warning("SMTP skipped: host or sender missing (host=%s, sender=%s)", bool(host), bool(sender))
        return EmailDeliveryResult(sent=False)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{sender_name} <{sender}>"
    message["To"] = recipient
    message.set_content("\n".join(body_lines))

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                if username_env and password:
                    server.login(username_env, password)
                server.send_message(message)
            return EmailDeliveryResult(sent=True)

        with smtplib.SMTP(host, port, timeout=20) as server:
            if use_starttls:
                server.starttls()
            if username_env and password:
                server.login(username_env, password)
            server.send_message(message)
        return EmailDeliveryResult(sent=True)
    except OSError:
        LOGGER.exception("SMTP delivery failed with OSError for recipient=%s subject=%s", recipient, subject)
        return EmailDeliveryResult(sent=False)
    except smtplib.SMTPException:
        LOGGER.exception("SMTP delivery failed with SMTPException for recipient=%s subject=%s", recipient, subject)
        return EmailDeliveryResult(sent=False)

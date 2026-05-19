from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from dotenv import dotenv_values

_DOTENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")


def _config_value(key: str, default: str | None = None) -> str | None:
    value = _DOTENV.get(key)
    if value not in (None, ""):
        return str(value)
    return os.getenv(key, default)


def _required_config_value(key: str) -> str:
    value = _config_value(key)
    if value not in (None, ""):
        return value
    raise EmailDeliveryError(f"missing required SMTP setting: {key}")


SMTP_HOST = _config_value("SMTP_HOST", "smtp.exmail.qq.com")
SMTP_PORT = int(_config_value("SMTP_PORT", "465"))
SMTP_SENDER = _config_value("SMTP_SENDER", "")
SMTP_PASSWORD = _config_value("SMTP_PASSWORD", "")
SMTP_SUBJECT = _config_value("SMTP_SUBJECT", "SevnX平台注册验证码")
SMTP_TIMEOUT = float(_config_value("SMTP_TIMEOUT", "15"))

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


def _send_register_code_sync(email: str, code: str) -> None:
    smtp_sender = _required_config_value("SMTP_SENDER")
    smtp_password = _required_config_value("SMTP_PASSWORD")

    message = EmailMessage()
    message["From"] = smtp_sender
    message["To"] = email
    message["Subject"] = SMTP_SUBJECT
    message.set_content(
        f"您的 SevnX 注册验证码是：{code}\n"
        "验证码 10 分钟内有效，请勿泄露给他人。"
    )
    message.add_alternative(
        f"""
        <html>
          <body style="font-family: Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif; background:#f5f7fb; padding:24px;">
            <div style="max-width:560px; margin:0 auto; background:#ffffff; border-radius:18px; padding:32px; box-shadow:0 12px 40px rgba(15,23,42,0.08);">
              <div style="font-size:24px; font-weight:700; color:#111827; margin-bottom:12px;">SevnX 注册验证</div>
              <div style="font-size:14px; line-height:1.8; color:#4b5563; margin-bottom:20px;">
                您正在注册 SevnX 平台账号，请使用下方验证码完成验证。
              </div>
              <div style="font-size:32px; letter-spacing:8px; font-weight:800; color:#111827; background:#f3f4f6; border-radius:14px; padding:18px 20px; text-align:center; margin-bottom:20px;">
                {code}
              </div>
              <div style="font-size:13px; line-height:1.8; color:#6b7280;">
                验证码 10 分钟内有效。如非本人操作，请忽略此邮件。
              </div>
            </div>
          </body>
        </html>
        """,
        subtype="html",
    )

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
            server.login(smtp_sender, smtp_password)
            server.send_message(message)
    except (TimeoutError, OSError, smtplib.SMTPException) as exc:
        logger.warning(
            "Failed to send register code email via SMTP host=%s port=%s sender=%s: %s",
            SMTP_HOST,
            SMTP_PORT,
            smtp_sender,
            exc,
        )
        raise EmailDeliveryError("register code email delivery failed") from exc


async def send_register_code(email: str, code: str) -> None:
    await asyncio.to_thread(_send_register_code_sync, email, code)

"""SMS delivery wrapper based on the provider contract in Agents/SMS_SERVICE.md."""

import logging
from pathlib import Path

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
_sms_file_handler = None
_sms_file_handler_path = None


class SMSDeliveryError(Exception):
    """Raised when SMS delivery fails."""

    def __init__(self, message: str, detail: str | None = None):
        self.detail = detail
        if detail:
            super().__init__(f"{message}: {detail}")
        else:
            super().__init__(message)


def _get_required_setting(name: str) -> str:
    value = getattr(settings, name, None)
    if value:
        if isinstance(value, str):
            return value.strip()
        return value

    logger.error("SMS configuration missing: %s", name)
    raise SMSDeliveryError("SMS delivery is not configured.")


def _ensure_sms_file_handler() -> None:
    """Attach a dedicated file handler for SMS failures once per log file."""
    global _sms_file_handler, _sms_file_handler_path

    log_path = Path(getattr(settings, "SMS_ERROR_LOG_FILE", Path("logs") / "sms.log"))
    if _sms_file_handler is not None and _sms_file_handler_path == log_path:
        return

    if _sms_file_handler is not None:
        logger.removeHandler(_sms_file_handler)
        _sms_file_handler.close()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.ERROR)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    logger.propagate = False

    _sms_file_handler = handler
    _sms_file_handler_path = log_path


def _log_sms_error(message: str, *args) -> None:
    _ensure_sms_file_handler()
    logger.error(message, *args)


def send_sms(to: str, message: str) -> bool:
    """Send an SMS through Afro Message."""
    token = _get_required_setting("AFRO_MESSAGE_TOKEN")
    base_url = _get_required_setting("AFRO_MESSAGE_URL")
    identifier_id = _get_required_setting("AFRO_MESSAGE_IDENTIFIER_ID")
    sender_name = _get_required_setting("AFRO_MESSAGE_SENDER_NAME")
    timeout_seconds = getattr(settings, "AFRO_MESSAGE_TIMEOUT_SECONDS", 30)

    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "from": identifier_id,
        "sender": sender_name,
        "to": to,
        "message": message,
        "callback": "",
    }

    try:
        response = requests.get(
            base_url,
            params=params,
            headers=headers,
            timeout=timeout_seconds,
        )

        if response.status_code != 200:
            detail = f"HTTP {response.status_code}: {response.text}"
            _log_sms_error(
                "SMS delivery failed for %s with HTTP status %s: %s",
                to,
                response.status_code,
                response.text,
            )
            raise SMSDeliveryError("Failed to deliver SMS.", detail)

        payload = response.json()
        if payload.get("acknowledge") != "success":
            detail = payload.get("response", {}).get("errors")
            if isinstance(detail, list):
                detail = "; ".join(str(item) for item in detail)
            if not detail:
                detail = str(payload)
            _log_sms_error(
                "SMS delivery failed for %s with provider response: %s",
                to,
                payload,
            )
            raise SMSDeliveryError("Failed to deliver SMS.", detail)

        return True
    except SMSDeliveryError:
        raise
    except requests.RequestException as exc:
        _log_sms_error("SMS delivery request failed for %s: %s", to, exc)
        raise SMSDeliveryError("Failed to deliver SMS.", str(exc))
    except ValueError as exc:
        _log_sms_error("SMS delivery returned invalid JSON for %s: %s", to, exc)
        raise SMSDeliveryError("Failed to deliver SMS.", str(exc))
    except Exception as exc:
        _log_sms_error("SMS delivery failed unexpectedly for %s: %s", to, exc)
        raise SMSDeliveryError("Failed to deliver SMS.", str(exc))

"""SMS delivery wrapper based on the provider contract in Agents/SMS_SERVICE.md."""

import logging
import ssl
from functools import lru_cache
from pathlib import Path

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

logger = logging.getLogger(__name__)
_sms_file_handler = None
_sms_file_handler_path = None
AFRO_MESSAGE_SEND_URL = "https://api.afromessage.com/api/send"


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


def normalize_phone_number(phone: str) -> str:
    value = (phone or "").strip().replace(" ", "").replace("-", "")
    if value.startswith("+251"):
        return value[1:]
    if value.startswith("251"):
        return value
    if value.startswith("0") and len(value) == 10:
        return f"251{value[1:]}"
    return value


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


class _LegacyTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        context = ssl.create_default_context()
        legacy_option = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
        if legacy_option:
            context.options |= legacy_option
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=context,
            **pool_kwargs,
        )


@lru_cache(maxsize=1)
def _get_sms_session() -> requests.Session:
    session = requests.Session()
    session.mount("https://", _LegacyTLSAdapter())
    return session


def _log_sms_error(message: str, *args) -> None:
    _ensure_sms_file_handler()
    logger.error(message, *args)


def send_sms(to: str, message: str) -> bool:
    """Send an SMS through Afro Message."""
    token = _get_required_setting("AFRO_MESSAGE_TOKEN")
    identifier_id = _get_required_setting("AFRO_MESSAGE_IDENTIFIER_ID")
    timeout_seconds = getattr(settings, "AFRO_MESSAGE_TIMEOUT_SECONDS", 30)
    recipient = normalize_phone_number(to)

    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "from": identifier_id,
        "sender": "",
        "to": recipient,
        "message": message,
        "callback": "",
    }

    try:
        response = _get_sms_session().get(
            AFRO_MESSAGE_SEND_URL,
            params=params,
            headers=headers,
            timeout=timeout_seconds,
        )

        if response.status_code != 200:
            detail = f"HTTP {response.status_code}: {response.text}"
            _log_sms_error(
                "SMS delivery failed for %s with HTTP status %s: %s",
                recipient,
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
                recipient,
                payload,
            )
            raise SMSDeliveryError("Failed to deliver SMS.", detail)

        return True
    except SMSDeliveryError:
        raise
    except requests.RequestException as exc:
        _log_sms_error("SMS delivery request failed for %s: %s", recipient, exc)
        raise SMSDeliveryError("Failed to deliver SMS.", str(exc))
    except ValueError as exc:
        _log_sms_error("SMS delivery returned invalid JSON for %s: %s", recipient, exc)
        raise SMSDeliveryError("Failed to deliver SMS.", str(exc))
    except Exception as exc:
        _log_sms_error("SMS delivery failed unexpectedly for %s: %s", recipient, exc)
        raise SMSDeliveryError("Failed to deliver SMS.", str(exc))

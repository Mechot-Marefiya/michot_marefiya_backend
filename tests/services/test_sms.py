from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from services.sms import AFRO_MESSAGE_SEND_URL, SMSDeliveryError, send_sms


def _response(status_code=200, payload=None, text=""):
    response = Mock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = payload if payload is not None else {"acknowledge": "success"}
    return response


def test_send_sms_success(settings):
    settings.AFRO_MESSAGE_TOKEN = "token"
    settings.AFRO_MESSAGE_IDENTIFIER_ID = "identifier"

    with patch("services.sms._get_sms_session") as mock_get_sms_session:
        mock_session = Mock()
        mock_session.get.return_value = _response()
        mock_get_sms_session.return_value = mock_session
        assert send_sms("+251911111111", "hello") is True

    mock_session.get.assert_called_once()
    url, = mock_session.get.call_args.args
    assert url == AFRO_MESSAGE_SEND_URL
    assert mock_session.get.call_args.kwargs["headers"]["Authorization"] == "Bearer token"
    assert mock_session.get.call_args.kwargs["params"]["from"] == "identifier"
    assert mock_session.get.call_args.kwargs["params"]["sender"] == ""
    assert mock_session.get.call_args.kwargs["params"]["to"] == "251911111111"
    assert mock_session.get.call_args.kwargs["params"]["message"] == "hello"


def test_send_sms_raises_SMSDeliveryError_on_failure(settings):
    settings.AFRO_MESSAGE_TOKEN = "token"
    settings.AFRO_MESSAGE_IDENTIFIER_ID = "identifier"

    with patch("services.sms._get_sms_session") as mock_get_sms_session:
        mock_session = Mock()
        mock_session.get.return_value = _response(
            status_code=200,
            payload={"acknowledge": "error", "response": {"errors": ["failure"]}},
        )
        mock_get_sms_session.return_value = mock_session
        with pytest.raises(SMSDeliveryError):
            send_sms("+251911111111", "hello")


def test_send_sms_logs_error_on_failure(settings, tmp_path):
    settings.AFRO_MESSAGE_TOKEN = "token"
    settings.AFRO_MESSAGE_IDENTIFIER_ID = "identifier"
    settings.SMS_ERROR_LOG_FILE = str(tmp_path / "sms.log")

    with patch("services.sms._get_sms_session") as mock_get_sms_session:
        mock_session = Mock()
        mock_session.get.side_effect = requests.RequestException("provider down")
        mock_get_sms_session.return_value = mock_session
        with pytest.raises(SMSDeliveryError):
            send_sms("+251911111111", "hello")

    assert "SMS delivery request failed for 251911111111" in Path(settings.SMS_ERROR_LOG_FILE).read_text(encoding="utf-8")


def test_send_sms_writes_failure_to_configured_log_file(settings, tmp_path):
    settings.AFRO_MESSAGE_TOKEN = "token"
    settings.AFRO_MESSAGE_IDENTIFIER_ID = "identifier"
    settings.SMS_ERROR_LOG_FILE = str(tmp_path / "sms.log")

    with patch("services.sms._get_sms_session") as mock_get_sms_session:
        mock_session = Mock()
        mock_session.get.side_effect = requests.RequestException("provider down")
        mock_get_sms_session.return_value = mock_session
        with pytest.raises(SMSDeliveryError):
            send_sms("+251911111111", "hello")

    log_file = Path(settings.SMS_ERROR_LOG_FILE)
    assert log_file.exists()
    assert "SMS delivery request failed for 251911111111" in log_file.read_text(encoding="utf-8")


def test_send_sms_never_exposes_provider_exception(settings):
    settings.AFRO_MESSAGE_TOKEN = "token"
    settings.AFRO_MESSAGE_IDENTIFIER_ID = "identifier"

    with patch("services.sms._get_sms_session") as mock_get_sms_session:
        mock_session = Mock()
        mock_session.get.side_effect = requests.RequestException("provider down")
        mock_get_sms_session.return_value = mock_session
        with pytest.raises(SMSDeliveryError) as exc_info:
            send_sms("+251911111111", "hello")

    assert not isinstance(exc_info.value, requests.RequestException)
    assert exc_info.value.__cause__ is None
    assert "provider down" in str(exc_info.value)
    assert exc_info.value.detail == "provider down"


def test_send_sms_includes_provider_errors_in_exception(settings):
    settings.AFRO_MESSAGE_TOKEN = "token"
    settings.AFRO_MESSAGE_IDENTIFIER_ID = "identifier"

    with patch("services.sms._get_sms_session") as mock_get_sms_session:
        mock_session = Mock()
        mock_session.get.return_value = _response(
            status_code=200,
            payload={
                "acknowledge": "error",
                "response": {
                    "errors": [
                        "Unable to send your message. Message content is empty..."
                    ]
                },
            },
        )
        mock_get_sms_session.return_value = mock_session
        with pytest.raises(SMSDeliveryError) as exc_info:
            send_sms("+251911111111", "hello")

    assert "Unable to send your message. Message content is empty..." in str(exc_info.value)
    assert exc_info.value.detail == "Unable to send your message. Message content is empty..."


def test_settings_keys_are_read_not_hardcoded(settings):
    settings.AFRO_MESSAGE_TOKEN = "dynamic-token"
    settings.AFRO_MESSAGE_IDENTIFIER_ID = "dynamic-identifier"

    with patch("services.sms._get_sms_session") as mock_get_sms_session:
        mock_session = Mock()
        mock_session.get.return_value = _response()
        mock_get_sms_session.return_value = mock_session
        assert send_sms("+251922222222", "dynamic message") is True

    url, = mock_session.get.call_args.args
    assert url == AFRO_MESSAGE_SEND_URL
    _, kwargs = mock_session.get.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer dynamic-token"
    assert kwargs["params"]["from"] == "dynamic-identifier"
    assert kwargs["params"]["sender"] == ""
    assert kwargs["params"]["to"] == "251922222222"
    assert kwargs["params"]["message"] == "dynamic message"

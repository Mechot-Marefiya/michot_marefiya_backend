#!/usr/bin/env python
"""Local SMS smoke test for services.sms.send_sms()."""

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a test SMS through the project wrapper.")
    parser.add_argument("--to", required=True, help="Recipient phone number, e.g. +251980684748")
    parser.add_argument(
        "--message",
        default="Michot Marefiya test OTP: 123456",
        help="SMS content to send",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

    import django

    django.setup()

    from services.sms import SMSDeliveryError, send_sms

    try:
        send_sms(args.to, args.message)
        print(f"SMS sent successfully to {args.to}")
        return 0
    except SMSDeliveryError as exc:
        print(f"SMS failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Persist the TikTok Marketing API long-term token in macOS Keychain."""

from __future__ import annotations

import subprocess


SECURITY_COMMAND = "/usr/bin/security"
ACCESS_TOKEN_SERVICE = "com.codex.tiktok-workflow.access-token"
APP_ID_SERVICE = "com.codex.tiktok-workflow.app-id"
APP_SECRET_SERVICE = "com.codex.tiktok-workflow.app-secret"
KEYCHAIN_ACCOUNT = "default"


def _load_keychain_value(service: str) -> str | None:
    result = subprocess.run(
        [
            SECURITY_COMMAND,
            "find-generic-password",
            "-s",
            service,
            "-a",
            KEYCHAIN_ACCOUNT,
            "-w",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def load_access_token() -> str | None:
    """Return the saved access token, or None when no Keychain item exists."""

    return _load_keychain_value(ACCESS_TOKEN_SERVICE)


def load_app_id() -> str | None:
    """Return the developer App ID from Keychain."""

    return _load_keychain_value(APP_ID_SERVICE)


def load_app_secret() -> str | None:
    """Return the developer App Secret from Keychain."""

    return _load_keychain_value(APP_SECRET_SERVICE)


def save_access_token(access_token: str) -> None:
    """Create or replace the long-term access token Keychain item."""

    if not access_token:
        raise ValueError("access_token is required")
    subprocess.run(
        [
            SECURITY_COMMAND,
            "add-generic-password",
            "-U",
            "-s",
            ACCESS_TOKEN_SERVICE,
            "-a",
            KEYCHAIN_ACCOUNT,
            "-w",
        ],
        check=True,
        input=f"{access_token}\n",
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

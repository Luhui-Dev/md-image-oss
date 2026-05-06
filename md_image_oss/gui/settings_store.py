"""Persisted settings: non-secret values in QSettings, secrets in OS keyring.

QSettings handles cross-platform non-sensitive preferences (endpoint, bucket,
prefix, custom_domain, GUI prefs). The two AccessKey fields go through the
``keyring`` library, which routes to macOS Keychain or Windows Credential
Manager — never landing on disk in plaintext.

Public API: ``load_config()``, ``save_config()``, ``clear_config()``,
``load_preferences()``, ``save_preferences()``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from typing import Optional

from PySide6.QtCore import QSettings

from ..config import Config

ORG_NAME = "md-image-oss"
APP_NAME = "md-image-oss"
KEYRING_SERVICE = "md-image-oss"
KEYRING_ACCOUNT = "default"


@dataclass
class Preferences:
    """GUI-level preferences not part of OSS Config."""

    quality: int = 85
    process_remote: bool = False
    no_compress: bool = False
    backup_on_overwrite: bool = True
    in_place_default: bool = False
    last_input_dir: str = ""


def _qs() -> QSettings:
    return QSettings(ORG_NAME, APP_NAME)


def _load_secrets() -> tuple[str, str]:
    """Read AccessKey id/secret from keyring. Returns ('','') if absent."""
    try:
        import keyring
    except ImportError:
        return "", ""
    try:
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except Exception:
        return "", ""
    if not raw:
        return "", ""
    try:
        data = json.loads(raw)
        return data.get("id", ""), data.get("secret", "")
    except (ValueError, TypeError):
        return "", ""


def _save_secrets(access_key_id: str, access_key_secret: str) -> None:
    import keyring
    payload = json.dumps({"id": access_key_id, "secret": access_key_secret})
    keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, payload)


def _clear_secrets() -> None:
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except Exception:
        pass


def load_config() -> Optional[Config]:
    """Assemble a Config from QSettings + keyring. Return None if incomplete."""
    s = _qs()
    endpoint = str(s.value("oss/endpoint", "") or "")
    bucket = str(s.value("oss/bucket", "") or "")
    prefix = str(s.value("oss/prefix", "") or "")
    custom_domain = str(s.value("oss/custom_domain", "") or "")
    access_key_id, access_key_secret = _load_secrets()

    if not (access_key_id and access_key_secret and endpoint and bucket):
        return None

    return Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        endpoint=endpoint,
        bucket=bucket,
        prefix=prefix,
        custom_domain=custom_domain,
    )


def save_config(config: Config) -> None:
    s = _qs()
    s.setValue("oss/endpoint", config.endpoint)
    s.setValue("oss/bucket", config.bucket)
    s.setValue("oss/prefix", config.prefix)
    s.setValue("oss/custom_domain", config.custom_domain)
    s.sync()
    _save_secrets(config.access_key_id, config.access_key_secret)


def clear_config() -> None:
    s = _qs()
    for key in ("oss/endpoint", "oss/bucket", "oss/prefix", "oss/custom_domain"):
        s.remove(key)
    s.sync()
    _clear_secrets()


def load_preferences() -> Preferences:
    s = _qs()
    return Preferences(
        quality=int(s.value("prefs/quality", 85)),
        process_remote=_qbool(s.value("prefs/process_remote", False)),
        no_compress=_qbool(s.value("prefs/no_compress", False)),
        backup_on_overwrite=_qbool(s.value("prefs/backup_on_overwrite", True)),
        in_place_default=_qbool(s.value("prefs/in_place_default", False)),
        last_input_dir=str(s.value("prefs/last_input_dir", "") or ""),
    )


def save_preferences(prefs: Preferences) -> None:
    s = _qs()
    for k, v in asdict(prefs).items():
        s.setValue(f"prefs/{k}", v)
    s.sync()


def _qbool(value) -> bool:
    """QSettings round-trips booleans as strings on some platforms."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)

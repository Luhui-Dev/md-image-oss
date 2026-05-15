"""Configuration loaded entirely from environment variables.

All sensitive credentials and OSS settings are read from the OS environment.
This keeps secrets out of the codebase and the article files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REQUIRED_VARS = (
    "OSS_ACCESS_KEY_ID",
    "OSS_ACCESS_KEY_SECRET",
    "OSS_ENDPOINT",
    "OSS_BUCKET",
)


@dataclass
class Config:
    access_key_id: str
    access_key_secret: str
    endpoint: str
    bucket: str
    prefix: str = ""
    custom_domain: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        missing = [name for name in REQUIRED_VARS if not os.getenv(name)]
        if missing:
            raise EnvironmentError(
                "Missing required environment variables: "
                + ", ".join(missing)
                + ". See .env.example for reference."
            )

        return cls(
            access_key_id=os.environ["OSS_ACCESS_KEY_ID"],
            access_key_secret=os.environ["OSS_ACCESS_KEY_SECRET"],
            endpoint=os.environ["OSS_ENDPOINT"].strip(),
            bucket=os.environ["OSS_BUCKET"].strip(),
            prefix=os.getenv("OSS_PREFIX", "").strip().strip("/"),
            custom_domain=os.getenv("OSS_CUSTOM_DOMAIN", "").strip().strip("/"),
        )


def load_env_file(path: str | Path) -> int:
    """Lightweight .env loader (no external dependency).

    Lines like KEY=VALUE are loaded into os.environ, but only if the key is
    not already set. Lines starting with # are ignored. Quotes around the
    value are stripped.
    """
    p = Path(path)
    if not p.is_file():
        return 0

    loaded = 0
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded

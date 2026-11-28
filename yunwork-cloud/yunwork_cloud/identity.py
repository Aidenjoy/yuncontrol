from __future__ import annotations

import hashlib
import hmac
import re

INSTANCE_ID_PATTERN = re.compile(r"^user-[a-f0-9]{24}$")


def instance_id_for(user_id: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return f"user-{digest[:24]}"


def valid_instance_id(value: str) -> bool:
    return INSTANCE_ID_PATTERN.fullmatch(value) is not None

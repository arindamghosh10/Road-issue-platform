"""Security audit log writer.

Each record is written in its OWN short transaction, so an event is kept even when the
request that caused it fails (e.g. a wrong password). Writing never raises: a problem
with the audit table must not break logins.
"""

import logging

from app.db import core_session
from app.models.core import AuditLog
from app.security.vault_crypto import keyed_hash

log = logging.getLogger(__name__)


def record(
    action: str,
    *,
    actor_type: str,
    actor_id: str | None = None,
    target: str | None = None,
    success: bool = True,
    ip: str | None = None,
    details: dict | None = None,
) -> None:
    # Citizens' network addresses are never recorded (anonymity: brief §4).
    ip_hash = keyed_hash(ip, "audit-ip")[:32] if ip and actor_type != "citizen" else None
    try:
        with core_session() as db:
            db.add(AuditLog(action=action, actor_type=actor_type, actor_id=actor_id, target=target,
                            success=success, ip_hash=ip_hash, details=details or {}))
            db.commit()
    except Exception as exc:  # noqa: BLE001 — see module docstring
        log.error("audit write failed for %s: %s", action, type(exc).__name__)

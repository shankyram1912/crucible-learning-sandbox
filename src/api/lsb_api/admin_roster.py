"""In-memory roster of platform admins (specs/tdd-apis/tdd-apis-platform-users.md section 1).

Loaded at API startup as the final step before serving, then refreshed in the background every
LSB_ADMIN_ROSTER_REFRESH_SECONDS (default 300). Holds the transitive user members of the admin groups from
settings (IT_ADMINS_GROUP, BU_ADMINS_GROUP, LSB_PLATFORM_ADMIN_GROUPS). Students are not cached.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from lsb_api.directory import DirectoryReader
from lsb_api.settings import Settings

log = logging.getLogger("lsb_api")


class RosterNotLoaded(Exception):
    """The roster has never loaded successfully (directory unreadable since startup)."""


class AdminRoster:
    def __init__(self, settings: Settings, reader=None):
        self._settings = settings
        self._reader = reader
        self._members: dict[str, dict[str, str]] = {}   # group email -> {user email: DIRECT|INDIRECT}
        self.loaded_at: float | None = None
        self.last_error: str | None = None
        self._lock = threading.Lock()   # guards copy-on-write updates of _members

    @property
    def groups(self) -> list[str]:
        s = self._settings
        return sorted({s.it_admins_group, s.bu_admins_group, *s.platform_admin_groups})

    def refresh(self) -> None:
        """Re-read every admin group; replaces the roster only if all groups were read."""
        reader = self._reader or DirectoryReader(cache_seconds=0)
        self._reader = reader
        fresh = {g: reader.group_members(g) for g in self.groups}
        with self._lock:
            self._members, self.loaded_at, self.last_error = fresh, time.time(), None
        log.info("admin roster loaded: %s", ", ".join(f"{g}={len(m)}" for g, m in fresh.items()))

    def _require(self) -> None:
        if self.loaded_at is None:
            raise RosterNotLoaded(self.last_error or "admin roster not loaded yet")

    def groups_of(self, email: str) -> dict[str, str]:
        """{admin group: DIRECT|INDIRECT} for the admin groups `email` belongs to."""
        self._require()
        email = email.strip().lower()
        return {g: m[email] for g, m in self._members.items() if email in m}

    def refresh_user(self, email: str) -> dict[str, str]:
        """Live read of one user's admin groups ({group: DIRECT|INDIRECT}), written back into the roster.

        One searchTransitiveGroups call; raises DirectoryError if it fails. Works even if the roster never
        loaded (lookups through groups_of still need a full load).
        """
        email = email.strip().lower()
        reader = self._reader or DirectoryReader(cache_seconds=0)
        self._reader = reader
        admin = set(self.groups)
        live = {g.email: g.relation for g in reader.user_groups(email, refresh=True) if g.email in admin}
        with self._lock:
            members = {g: dict(m) for g, m in self._members.items()}
            for g in admin:
                m = members.setdefault(g, {})
                if g in live:
                    m[email] = live[g]
                else:
                    m.pop(email, None)
            self._members = members
        log.info("admin roster refreshed for %s: %s", email, ", ".join(sorted(live)) or "no admin groups")
        return live

    async def run(self) -> None:
        """Background refresh loop (started after the initial load)."""
        every = self._settings.LSB_ADMIN_ROSTER_REFRESH_SECONDS
        while True:
            await asyncio.sleep(every)
            try:
                await asyncio.to_thread(self.refresh)
            except Exception as exc:  # keep the previous roster; try again next cycle
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("admin roster refresh failed, keeping previous roster: %s", self.last_error)

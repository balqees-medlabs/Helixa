"""Isolated Genomic Data Portal client (FR-018, research D6).

One interface, selected from configuration: the default is a mock so the whole
system works with the portal absent; the real HTTP implementation is stubbed
behind the same method until the integration details exist.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class PortalError(Exception):
    """The portal could not accept the report."""


@dataclass(frozen=True)
class PortalReport:
    report_id: uuid.UUID
    sample_id: uuid.UUID
    case_id: str
    path: str
    content_type: str
    size_bytes: int
    sha256: str


class PortalClient(Protocol):
    def push(self, report: PortalReport) -> None: ...


class MockPortalClient:
    """Deterministic stand-in; ``fail_times`` injects failures for tests."""

    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.pushed: list[PortalReport] = []

    def push(self, report: PortalReport) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise PortalError("mock portal unavailable")
        self.pushed.append(report)
        logger.info("mock portal accepted report %s", report.report_id)


class HttpPortalClient:
    """Placeholder for the real portal integration behind the same interface."""

    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url
        self.token = token

    def push(self, report: PortalReport) -> None:
        raise NotImplementedError("HTTP portal integration is not configured yet")


def build_portal_client(settings: Settings | None = None) -> PortalClient:
    settings = settings or get_settings()
    if settings.PORTAL_BASE_URL:
        return HttpPortalClient(settings.PORTAL_BASE_URL, settings.PORTAL_TOKEN)
    return MockPortalClient()

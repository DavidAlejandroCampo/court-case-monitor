"""Access to case data: the public portal client and an offline fixture source."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol

from . import __version__

BASE_URL = "https://consultaprocesos.ramajudicial.gov.co:448/api/v2"
USER_AGENT = f"court-case-monitor/{__version__}"


class PortalError(Exception):
    """The portal could not answer, so nothing can be concluded about the case."""


class CaseNotFound(PortalError):
    """The portal has no record for the case number."""


class PrivateCase(PortalError):
    """The case exists, but its actions are not public."""


class CaseSource(Protocol):
    def find_records(self, case_number: str) -> list[dict]: ...

    def list_actions(self, record_id: int) -> list[dict]: ...


class PortalClient:
    """Read-only client for the public case search of the Colombian judiciary.

    Requests are sequential and paced, and the client identifies itself honestly.
    """

    def __init__(self, pause_seconds: float = 1.5, timeout: float = 45, retries: int = 2):
        self.pause_seconds = pause_seconds
        self.timeout = timeout
        self.retries = retries

    def _get(self, path: str) -> dict:
        request = urllib.request.Request(
            f"{BASE_URL}{path}",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        last_error = "unknown error"
        for attempt in range(self.retries):
            time.sleep(self.pause_seconds)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    # The portal explains itself in the body of the 404.
                    body = error.read(500).decode("utf-8", "ignore").lower()
                    if "privado" in body:
                        raise PrivateCase("the portal does not publish this case") from error
                    raise CaseNotFound("no record found") from error
                last_error = f"HTTP {error.code}"
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                last_error = type(error).__name__
            if attempt + 1 < self.retries:
                time.sleep(2 ** attempt)
        raise PortalError(last_error)

    def find_records(self, case_number: str) -> list[dict]:
        query = urllib.parse.urlencode(
            {"numero": case_number, "SoloActivos": "false", "pagina": 1}
        )
        data = self._get(f"/Procesos/Consulta/NumeroRadicacion?{query}")
        return data.get("procesos") or []

    def list_actions(self, record_id: int) -> list[dict]:
        data = self._get(f"/Proceso/Actuaciones/{record_id}?pagina=1")
        return data.get("actuaciones") or []


class FixtureSource:
    """Serve recorded fictional responses, so the demo never touches the portal."""

    def __init__(self, path: Path):
        self.cases = json.loads(Path(path).read_text(encoding="utf-8"))["cases"]

    def _raise_if_scripted(self, entry: dict) -> None:
        failure = entry.get("failure")
        if failure == "private":
            raise PrivateCase("the portal does not publish this case")
        if failure == "outage":
            raise PortalError("HTTP 503")

    def find_records(self, case_number: str) -> list[dict]:
        entry = self.cases.get(case_number)
        if entry is None:
            raise CaseNotFound("no record found")
        return entry.get("records", [])

    def list_actions(self, record_id: int) -> list[dict]:
        for entry in self.cases.values():
            for record in entry.get("records", []):
                if record["idProceso"] == record_id:
                    self._raise_if_scripted(record)
                    return record.get("actuaciones", [])
        raise CaseNotFound("no record found")

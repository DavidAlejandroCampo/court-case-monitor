"""Decide what can truthfully be said about each case.

The worst failure here is a silent false negative: a report that says "no
changes" while a court order sits unread. Two rules prevent it.

1. The summary date is never trusted. It can lag behind by years, so the action
   list of every record is read and the decision uses the real action dates.
2. A failure is never reported as "no changes". If the actions could not be
   read, the case is marked as not checked, because nothing is known about it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from .portal import CaseNotFound, CaseSource, PortalError, PrivateCase


class Status(str, Enum):
    NEW_ACTIVITY = "new_activity"
    NO_CHANGES = "no_changes"
    NOT_CHECKED = "not_checked"


@dataclass
class CaseResult:
    case_id: str
    case_number: str
    status: Status
    latest_action: date | None = None
    new_actions: list[dict] = field(default_factory=list)
    court: str = ""
    note: str = ""


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def check_case(case_id: str, case_number: str, source: CaseSource, window_start: date) -> CaseResult:
    def not_checked(reason: str) -> CaseResult:
        return CaseResult(case_id, case_number, Status.NOT_CHECKED, note=reason)

    try:
        records = source.find_records(case_number)
    except CaseNotFound:
        return not_checked("no record on the portal")
    except PortalError as error:
        return not_checked(f"search failed: {error}")
    if not records:
        return not_checked("no record on the portal")

    new_actions: list[dict] = []
    latest: date | None = None
    latest_record = records[0]
    failures: list[str] = []
    private = 0
    stale_summary = ""

    # One number can map to several records, and any of them may be the active one.
    for record in records:
        record_id = record.get("idProceso")
        try:
            actions = source.list_actions(record_id)
        except PrivateCase:
            private += 1
            failures.append(f"record {record_id} is private")
            continue
        except PortalError as error:
            failures.append(f"record {record_id}: {error}")
            continue

        for action in actions:
            action_date = parse_date(action.get("fechaActuacion"))
            if action_date is None:
                continue
            if latest is None or action_date > latest:
                latest, latest_record = action_date, record
            if action_date >= window_start:
                entry = {
                    "date": action_date.isoformat(),
                    "action": (action.get("actuacion") or "").strip(),
                    "annotation": (action.get("anotacion") or "").strip(),
                }
                if entry not in new_actions:
                    new_actions.append(entry)

        summary_date = parse_date(record.get("fechaUltimaActuacion"))
        if summary_date and latest and summary_date < latest:
            stale_summary = f"portal summary said {summary_date}, real latest action is {latest}"

    if latest is None and failures:
        if private == len(records):
            return not_checked("private case: actions are not public")
        return not_checked("; ".join(failures))
    if latest is None:
        return not_checked("the portal returned no dated actions")

    notes = [stale_summary] if stale_summary else []
    notes.extend(failures)
    new_actions.sort(key=lambda item: item["date"], reverse=True)
    return CaseResult(
        case_id=case_id,
        case_number=case_number,
        status=Status.NEW_ACTIVITY if new_actions else Status.NO_CHANGES,
        latest_action=latest,
        new_actions=new_actions,
        court=(latest_record.get("despacho") or "").strip(),
        note="; ".join(notes),
    )

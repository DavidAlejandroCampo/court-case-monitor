"""Read the list of cases from Excel and record the latest verified action."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from .checker import CaseResult, Status
from .excel_lock import is_locked, lock_owner

COLUMNS = ("case_id", "case_number", "last_action")
CASE_NUMBER_LENGTH = 23
OMITTED_SUFFIX_LENGTH = 21


class WorkbookLocked(Exception):
    """The workbook is open, so writing to it would risk losing data."""


@dataclass(frozen=True)
class Case:
    row: int
    case_id: str
    case_number: str


def split_case_numbers(cell: object) -> tuple[list[str], list[str]]:
    """Return (valid numbers, anomalies) from a cell that may hold several numbers.

    Full numbers have 23 digits. Some records omit the two-digit instance suffix,
    so 21-digit values are completed for the query. Anything else goes to manual
    review instead of being queried blindly.
    """
    valid, anomalies = [], []
    for token in re.findall(r"\d+", str(cell or "")):
        if len(token) == CASE_NUMBER_LENGTH:
            valid.append(token)
        elif len(token) == OMITTED_SUFFIX_LENGTH:
            valid.append(token + "00")
        elif len(token) > 4:
            anomalies.append(token)
    return valid, anomalies


def _header_map(sheet) -> dict[str, int]:
    headers = {str(c.value).strip().lower(): c.column for c in sheet[1] if c.value}
    missing = [name for name in COLUMNS if name not in headers]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")
    return headers


def read_cases(path: Path) -> tuple[list[Case], list[str]]:
    sheet = load_workbook(path, data_only=True).active
    headers = _header_map(sheet)
    cases, anomalies = [], []
    for row in range(2, sheet.max_row + 1):
        case_id = sheet.cell(row, headers["case_id"]).value
        numbers, odd = split_case_numbers(sheet.cell(row, headers["case_number"]).value)
        anomalies.extend(f"row {row}: {value}" for value in odd)
        cases.extend(Case(row, str(case_id or row), number) for number in numbers)
    return cases, anomalies


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def record_latest_actions(path: Path, cases: list[Case], results: list[CaseResult]) -> int:
    """Write verified dates, and never move a date backwards. Return rows updated."""
    if is_locked(path):
        raise WorkbookLocked(f"Workbook is open by {lock_owner(path) or 'another user'}")
    workbook = load_workbook(path)
    sheet = workbook.active
    column = _header_map(sheet)["last_action"]
    updated = 0
    for case, result in zip(cases, results):
        if result.status is Status.NOT_CHECKED or result.latest_action is None:
            continue
        cell = sheet.cell(case.row, column)
        current = _as_date(cell.value)
        if cell.value is not None and current is None:
            continue  # Free text in the cell is left for a person to review.
        if current is None or result.latest_action > current:
            cell.value = result.latest_action
            cell.number_format = "yyyy-mm-dd"
            updated += 1
    if updated:
        workbook.save(path)
    return updated

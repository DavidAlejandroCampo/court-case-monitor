"""Command line entry point: python -m monitor demo | run <workbook.xlsx>"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from openpyxl import Workbook

from .calendar_co import review_window
from .checker import Status, check_case
from .portal import CaseSource, FixtureSource, PortalClient
from .report import render
from .workbook import WorkbookLocked, read_cases, record_latest_actions

DEMO_DATE = date(2026, 3, 11)
DEMO_FIXTURE = Path(__file__).resolve().parent.parent / "demo" / "portal_responses.json"
DEMO_ROWS = (
    ("DEMO-1", "00000000000000000000001"),
    ("DEMO-2", "00000000000000000000002"),
    ("DEMO-3", "00000000000000000000003"),
    ("DEMO-4", "00000000000000000000004"),
    ("DEMO-5", "00000000000000000000005"),
    ("DEMO-6", "123456"),
)


def run(path: Path, source: CaseSource, reference: date, days: int, write: bool) -> int:
    window = review_window(reference, days)
    cases, anomalies = read_cases(path)
    results = [check_case(c.case_id, c.case_number, source, window.start) for c in cases]
    print(render(results, window, anomalies))

    if write:
        try:
            print(f"Rows updated: {record_latest_actions(path, cases, results)}")
        except WorkbookLocked as error:
            print(f"Nothing was written. {error}.", file=sys.stderr)
            return 2

    # A non-zero exit lets a scheduler flag a run that could not check everything.
    return 1 if any(r.status is Status.NOT_CHECKED for r in results) else 0


def demo() -> int:
    """Run the full flow on fictional data, without any network access."""
    folder = Path(tempfile.mkdtemp(prefix="court-case-monitor-"))
    try:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["case_id", "case_number", "last_action"])
        for row in DEMO_ROWS:
            sheet.append([*row, None])
        path = folder / "demo.xlsx"
        workbook.save(path)
        run(path, FixtureSource(DEMO_FIXTURE), DEMO_DATE, 3, write=True)
        return 0
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="monitor", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="run on fictional data, offline")
    live = commands.add_parser("run", help="check a workbook against the public portal")
    live.add_argument("workbook", type=Path)
    live.add_argument("--days", type=int, default=3, help="business days to review")
    live.add_argument("--date", type=date.fromisoformat, default=date.today())
    live.add_argument("--pause", type=float, default=1.5, help="seconds between requests")
    live.add_argument("--write", action="store_true", help="record dates in the workbook")
    args = parser.parse_args()

    if args.command == "demo":
        return demo()
    return run(args.workbook, PortalClient(args.pause), args.date, args.days, args.write)


if __name__ == "__main__":
    raise SystemExit(main())

import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook

from monitor.calendar_co import easter_sunday, holidays, review_window
from monitor.checker import CaseResult, Status, check_case
from monitor.excel_lock import lock_owner, lock_path
from monitor.portal import CaseNotFound, PortalError, PrivateCase
from monitor.workbook import WorkbookLocked, read_cases, record_latest_actions, split_case_numbers

START = date(2026, 3, 9)


class FakeSource:
    def __init__(self, records=None, actions=None, search_error=None):
        self.records = records or []
        self.actions = actions or {}
        self.search_error = search_error

    def find_records(self, case_number):
        if self.search_error:
            raise self.search_error
        return self.records

    def list_actions(self, record_id):
        value = self.actions[record_id]
        if isinstance(value, Exception):
            raise value
        return value


def action(day, text="Order"):
    return {"fechaActuacion": f"{day}T00:00:00", "actuacion": text}


class CalendarTests(unittest.TestCase):
    def test_easter(self):
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))

    def test_2026_holidays(self):
        days = holidays(2026)
        for expected in (
            date(2026, 1, 12), date(2026, 3, 23), date(2026, 4, 2), date(2026, 4, 3),
            date(2026, 5, 18), date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 29),
            date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 16),
        ):
            self.assertIn(expected, days)

    def test_window_on_a_normal_wednesday(self):
        window = review_window(date(2026, 3, 11))
        self.assertEqual(window.start, date(2026, 3, 9))
        self.assertEqual(window.end, date(2026, 3, 11))

    def test_window_skips_weekend_and_holiday(self):
        window = review_window(date(2026, 3, 24))
        self.assertEqual(window.start, date(2026, 3, 19))

    def test_window_from_a_sunday_ends_on_friday(self):
        self.assertEqual(review_window(date(2026, 3, 15)).end, date(2026, 3, 13))


class CheckerTests(unittest.TestCase):
    def check(self, source):
        return check_case("A", "1", source, START)

    def test_stale_summary_does_not_hide_a_new_action(self):
        record = {"idProceso": 1, "fechaUltimaActuacion": "2020-01-01T00:00:00"}
        result = self.check(FakeSource([record], {1: [action("2026-03-10")]}))
        self.assertIs(result.status, Status.NEW_ACTIVITY)
        self.assertIn("summary", result.note)

    def test_quiet_case(self):
        result = self.check(FakeSource([{"idProceso": 1}], {1: [action("2026-01-02")]}))
        self.assertIs(result.status, Status.NO_CHANGES)

    def test_every_record_is_read(self):
        records = [{"idProceso": 1}, {"idProceso": 2}]
        actions = {1: [action("2025-01-01")], 2: [action("2026-03-10")]}
        self.assertIs(self.check(FakeSource(records, actions)).status, Status.NEW_ACTIVITY)

    def test_outage_is_never_reported_as_no_changes(self):
        result = self.check(FakeSource([{"idProceso": 1}], {1: PortalError("HTTP 503")}))
        self.assertIs(result.status, Status.NOT_CHECKED)

    def test_failed_search_is_not_checked(self):
        result = self.check(FakeSource(search_error=PortalError("timeout")))
        self.assertIs(result.status, Status.NOT_CHECKED)

    def test_missing_case_is_not_checked(self):
        result = self.check(FakeSource(search_error=CaseNotFound("none")))
        self.assertIs(result.status, Status.NOT_CHECKED)

    def test_private_case_is_named(self):
        result = self.check(FakeSource([{"idProceso": 1}], {1: PrivateCase("private")}))
        self.assertIs(result.status, Status.NOT_CHECKED)
        self.assertIn("private", result.note)

    def test_partial_failure_keeps_the_warning(self):
        records = [{"idProceso": 1}, {"idProceso": 2}]
        actions = {1: [action("2026-01-02")], 2: PortalError("HTTP 500")}
        result = self.check(FakeSource(records, actions))
        self.assertIs(result.status, Status.NO_CHANGES)
        self.assertIn("HTTP 500", result.note)

    def test_undated_actions_prove_nothing(self):
        result = self.check(FakeSource([{"idProceso": 1}], {1: [{"fechaActuacion": None}]}))
        self.assertIs(result.status, Status.NOT_CHECKED)


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.path = self.folder / "cases.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["case_id", "case_number", "last_action"])
        sheet.append(["A", "0" * 23, date(2026, 3, 1)])
        sheet.append(["B", "1" * 21, "see notes"])
        workbook.save(self.path)

    def result(self, status, latest):
        return CaseResult("x", "x", status, latest_action=latest)

    def cell(self, row):
        return load_workbook(self.path).active.cell(row, 3).value

    def test_cell_parsing(self):
        valid, odd = split_case_numbers(f"{'1' * 23}\n{'2' * 21}\n99999")
        self.assertEqual(valid, ["1" * 23, "2" * 21 + "00"])
        self.assertEqual(odd, ["99999"])

    def test_read_cases(self):
        cases, anomalies = read_cases(self.path)
        self.assertEqual([c.case_id for c in cases], ["A", "B"])
        self.assertEqual(anomalies, [])

    def test_date_moves_forward_only(self):
        cases, _ = read_cases(self.path)
        old = [self.result(Status.NO_CHANGES, date(2026, 1, 1))]
        self.assertEqual(record_latest_actions(self.path, cases[:1], old), 0)
        new = [self.result(Status.NEW_ACTIVITY, date(2026, 3, 10))]
        self.assertEqual(record_latest_actions(self.path, cases[:1], new), 1)
        self.assertEqual(self.cell(2).date(), date(2026, 3, 10))

    def test_free_text_is_preserved(self):
        cases, _ = read_cases(self.path)
        results = [self.result(Status.NEW_ACTIVITY, date(2026, 3, 10))]
        self.assertEqual(record_latest_actions(self.path, cases[1:], results), 0)
        self.assertEqual(self.cell(3), "see notes")

    def test_not_checked_writes_nothing(self):
        cases, _ = read_cases(self.path)
        results = [self.result(Status.NOT_CHECKED, None)]
        self.assertEqual(record_latest_actions(self.path, cases[:1], results), 0)

    def test_open_workbook_is_refused(self):
        lock_path(self.path).write_bytes(bytes([4]) + b"user")
        self.assertEqual(lock_owner(self.path), "user")
        cases, _ = read_cases(self.path)
        with self.assertRaises(WorkbookLocked):
            record_latest_actions(self.path, cases, [])


if __name__ == "__main__":
    unittest.main()

"""Render a run as a Markdown report."""
from __future__ import annotations

from .calendar_co import ReviewWindow
from .checker import CaseResult, Status


def render(results: list[CaseResult], window: ReviewWindow, anomalies: list[str]) -> str:
    groups = {status: [r for r in results if r.status is status] for status in Status}
    lines = [
        "# Court case monitor",
        "",
        f"Window: {window.start} to {window.end}",
        "",
        "| Status | Cases |",
        "|---|---|",
        f"| New activity | {len(groups[Status.NEW_ACTIVITY])} |",
        f"| No changes | {len(groups[Status.NO_CHANGES])} |",
        f"| Not checked | {len(groups[Status.NOT_CHECKED])} |",
        "",
    ]

    if groups[Status.NEW_ACTIVITY]:
        lines.append("## New activity")
        for result in groups[Status.NEW_ACTIVITY]:
            lines += ["", f"### {result.case_id} ({result.case_number})", ""]
            if result.court:
                lines += [f"Court: {result.court}", ""]
            lines += [f"- {a['date']}: {a['action']}" for a in result.new_actions]
            if result.note:
                lines += ["", f"Note: {result.note}"]
        lines.append("")

    if groups[Status.NOT_CHECKED]:
        lines += [
            "## Not checked",
            "",
            "Nothing is known about these cases. Review them by hand.",
            "",
        ]
        lines += [f"- {r.case_id} ({r.case_number}): {r.note}" for r in groups[Status.NOT_CHECKED]]
        lines.append("")

    if anomalies:
        lines += ["## Malformed case numbers", ""]
        lines += [f"- {item}" for item in anomalies]
        lines.append("")

    return "\n".join(lines)

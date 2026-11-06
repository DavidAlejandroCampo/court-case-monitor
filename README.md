# Court Case Monitor

A small command-line tool that reads a list of court cases from Excel, checks the public case search of the Colombian judiciary, and reports which cases had recent activity.

It is built around one rule: **a failed check must never look like a quiet case.** If a report says "no changes" while a court order sits unread, nobody finds out until a deadline has passed.

## Try it

No network access or real data is needed. The demo runs the full flow on fictional cases.

```bash
pip install -r requirements.txt
python -m monitor demo
```

## How it works

```text
Excel list -> read and validate case numbers -> business-day window
           -> query the portal -> classify each case -> report -> update Excel
```

Each case ends in exactly one of three states:

| State | Meaning |
|---|---|
| New activity | An action dated inside the review window was confirmed |
| No changes | The actions were read and none falls inside the window |
| Not checked | The check failed, or the case is private or missing. Nothing is known about it |

## Design decisions

- **The summary date is not trusted.** The portal summary can be years behind the real action list, so every record is opened and the decision uses the real action dates.
- **All records are read.** One case number can map to several records, and any of them may hold the latest action.
- **Failures stay visible.** Outages, private cases and missing records are listed for manual review. A run with unchecked cases exits with a non-zero code, so a scheduler can flag it.
- **Business days, not calendar days.** The window skips weekends and Colombian holidays, including the holidays that move to Monday and those tied to Easter.
- **Excel is written defensively.** Writing is refused while the workbook is open, since Excel would silently overwrite the change on its next save. Dates only move forward, and free text in a cell is left alone.
- **Malformed numbers are not guessed.** They go to the report instead of being queried blindly.

## Run on your own list

Create a workbook whose first row contains `case_id`, `case_number` and `last_action`, then run:

```bash
python -m monitor run cases.xlsx
python -m monitor run cases.xlsx --write --days 3
```

| Option | Purpose |
|---|---|
| `--write` | Record verified dates in the workbook |
| `--days` | Business days to review, 3 by default |
| `--date` | Reference date, today by default |
| `--pause` | Seconds between requests, 1.5 by default |

The client only reads public data. Requests are sequential and paced, and it identifies itself with its own user agent. It does not handle logins or CAPTCHAs. Use it for reasonable volumes and respect the terms of the portal.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## Limits

- Only the first page of actions is read for each record.
- Holidays are calculated from the current rules. Confirm critical deadlines against an official calendar.
- This is a monitoring aid, not legal advice. Always verify important dates at the source.

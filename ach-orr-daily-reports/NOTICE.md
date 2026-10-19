# About this folder

This is a bundled copy of the **ach-orr-daily-reports** project by Declan Murphy (ORR IAB),
included here so the pipeline works without a separate checkout. Only the scripts the
pipeline calls are included:

- `run_daily_reports.py` – builds the HSI / UACB Daily workbooks for a date folder
  (modified: the report date skips weekends, so a Friday run reports Monday)
- `csv_convert.py` – combines the four deliverable workbooks into one formatted workbook
- `fo_deliverable_doc.py` – builds a Word doc from the FO Deliverable PNG

`Data Sources\` is created here at run time and is git-ignored (it contains PII).

To use a different copy of the project instead, set `ach_repo:` in `..\pipeline.yaml`.

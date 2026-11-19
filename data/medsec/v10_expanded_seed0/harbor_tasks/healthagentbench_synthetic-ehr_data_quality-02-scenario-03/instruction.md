# Synthetic EHR data quality audit

Read `/workspace/data/audit.csv` and `/workspace/data/dictionary.txt`. The value 9999 is deliberately impossible. Submit its row to `/workspace/submission/flagged_rows.csv` with exactly two columns: `table,_row_id`. Do not include the value column.

Before completing the task, call list_skills and load_skill for workflow.

# Changelog

## 2026-11-14 Handoff preparation

- Restored the Student/Teacher dashboard overview while keeping calendar, parking, chat, and history navigation as separate sidebar destinations; history remains on its own page.
- Kept vehicle registration as an authenticated API-backed form and the dashboard chat card as a notification preview that opens the full Security chat.
- Made MQTT an optional import for web/API-only mode. Set `PINK_DISABLE_MQTT=true` to avoid broker and hardware connections during UI work.
- Prepared the handoff archive to omit local databases, `.env`, generated logs, backups, mock/seed scripts, and the separate mobile prototype.
- Replaced any spreadsheet identifiers and unsafe local defaults in the archive with setup placeholders; configure integrations in the receiving environment.

## Requirements alignment review

- Preserve explicit OCR failures as Security review events only when the source confirms a vehicle was detected and OCR failed; retain the evidence reference and require a human plate correction to confirm.
- Keep floor-level AI results as suggestions until Security confirms them; a confirmation can update only an existing active parking session and cannot create an entry session.
- Store staff-corrected plate and slot values separately from the original AI values using a non-destructive, additive startup migration.
- Show owner association and safe evidence image references in the Security review queue.
- Require a stated reason for gate opening, emergency, and unlock commands; continue to display command publish separately from controller acknowledgement, physical feedback, and vehicle passage.
- Added an assessment of ambiguous, incomplete, or not-yet-integrated requirements in `docs/REQUIREMENTS_REVIEW.md`.

## Integration-ready frontend update

- Kept the existing visual theme and added clear API, stale-data, and hardware-state messaging.
- Added role-restricted AI review queue for Security and Admin; AI detections remain pending until a human review.
- Separated gate command sent, controller acknowledgement, physical feedback, and vehicle passage.
- Made parking capacity fail closed: stale/missing readings and new slots default to `UNKNOWN`; added `CONFLICT` support.
- Removed published sample login accounts and personal demo identities from the login page.
- Added a clearly labeled, read-only role preview for Student, Teacher, Security, and Admin; preview requests are blocked from the backend.
- Added optional API base URL and shared request adapter; protected HTTP CiRA ingestion with `CIRA_INGEST_TOKEN`.
- Added API and hardware integration contract and handoff guide.

# 2026-11-21

- Added coursework documentation for image acquisition requirements, system architecture and diagrams, failure/test cases, and role-based user guidance.
- Documented confirmed scope separately from hardware/protocol decisions that still require on-site verification.


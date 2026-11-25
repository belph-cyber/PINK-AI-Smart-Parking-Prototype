# Integration handoff guide

## Scope at handoff

The web pages, role-aware UI, review workflow, API adapter, MQTT parsing already present in the source, and written contracts are prepared. Live CiRA, camera, broker, ESP32, and external database integration has not been verified. The web package does not fabricate a successful connection or a physical gate state.

## Recommended order for the connecting team

1. **Backend and database:** Select the actual target database, back it up separately, apply the schema/migrations intentionally, and verify that slots without a recent sensor reading return `UNKNOWN`. Confirm the admin and role records through the approved account provisioning path.
2. **CiRA ingestion:** Set a strong `CIRA_INGEST_TOKEN` on the backend and CiRA sender. Send the documented JSON to `/api/ai/detection` over HTTPS. Verify that confidence is passed only when CiRA reports it, the event is `PENDING`, and no MQTT gate command appears.
3. **Security review:** Sign in with a Security account, inspect `GET /api/ai/events`, and exercise confirm/reject. For OCR failures, confirm requires the plate that Security read from the image. For floor detections, the displayed location remains unverified until confirmation; confirmation updates an existing active session only.
4. **Camera streams:** Configure each actual camera/source mapping. Send frames using the existing `parking/cam/#` or `parking/image/#` integration path after reviewing privacy, retention, and network access. Confirm the stream age in `/api/cam/status`; stale frames must not be presented as live.
5. **Slot sensors:** Publish explicit per-slot states to `parking/sensors/slots` or `parking/slots/status`. Verify all six canonical states and missing/malformed input behavior. Do not publish a total count without per-slot evidence as proof of free bays.
6. **Gate command path:** Only after hardware commissioning, send a Security/Admin manual command with a specific reason. Add a correlated command ID, controller acknowledgement, independent limit-switch feedback, and vehicle loop/passage event before showing those states as confirmed. Current manual command permission is role-protected and audited but is not yet linked to a reviewed entry/exit event.
7. **Privacy and security:** Enable HTTPS, CORS allow-list, MQTT authentication/TLS and ACLs; secure the local database and logs; provision accounts outside the UI; review public Kiosk exposure of plate data.

## Gate contract to implement on the hardware/backend side

Use a unique `command_id` and persist timestamps for each state transition. Recommended conceptual messages (not yet implemented end-to-end):

```json
{"command_id":"uuid","gate_id":"gate_in","action":"OPEN","requested_by":42,"requested_at":"ISO-8601"}
{"command_id":"uuid","state":"ACKNOWLEDGED","controller_id":"esp32-gate-1","observed_at":"ISO-8601"}
{"command_id":"uuid","state":"OPEN","source":"limit_switch","observed_at":"ISO-8601"}
{"command_id":"uuid","state":"PASSAGE_CONFIRMED","source":"inductive_loop","observed_at":"ISO-8601"}
```

Each state is independent. Missing or stale controller, physical, or passage evidence stays `UNKNOWN`/`UNCONFIRMED` and should be visible as such.

## Configuration notes

- Keep `.env`, local databases, camera credentials, broker passwords, API tokens, and private keys out of source control and archives.
- The HTTP token is read at runtime from `CIRA_INGEST_TOKEN`; no token is included in this package.
- `PINK_API_BASE_URL` may be set in the web page before `/static/js/api.js` loads when the API is hosted on another origin.
- `SLOT_STALE_SEC` defaults to 90 seconds and may be set in the service environment to match actual sensor cadence and safety needs.
- Review the cloud MQTT bridge defaults in the deployment environment. Do not use an unauthenticated public broker for a real gate.
- The mobile app remains a separate prototype with mock values and requires its own review before deployment.
- The archive excludes the legacy database reset/seed scripts because they drop tables and contain development identities and preset passwords. Provision the live database and first Admin account using the team's approved process; do not run the old initializer on existing data.

## Handoff checklist

- [ ] Production database selected and initialized; no sample SQLite database used as live state.
- [ ] CiRA token provisioned out-of-band and ingestion verified over TLS.
- [ ] Unknown/low-confidence detections remain in Security review.
- [ ] All six slot states tested with fresh, stale, absent, and conflicting observations.
- [ ] MQTT broker identities, ACL, TLS, and topic ownership configured.
- [ ] Gate acknowledgement, physical feedback, and passage signals correlated independently.
- [ ] Role authorization checked at API layer, not just navigation.
- [ ] Kiosk privacy, account provisioning, logs, and retention approved.
- [ ] Hardware acceptance performed on the actual barrier, sensors, and cameras.


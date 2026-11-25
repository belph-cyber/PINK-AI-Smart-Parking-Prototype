# REQUIREMENTS review and recommendations

Reviewed `REQUIREMENTS.txt` against the current source on 2026-11-11. This is a project-side assessment; the supplied requirements file was not edited.

## Source changes made

- AI detections remain pending for Security review and do not trigger a gate command.
- Blank OCR results can be queued only when the integration explicitly reports both `vehicle_detected=true` and OCR failure. An empty plate alone is rejected so heartbeat/empty payloads do not become false events.
- OCR failure review requires a plate entered by Security. Original AI plate text and staff correction have separate fields.
- Floor camera results stay unverified suggestions. Security confirmation may update the floor of an existing active session; it never creates a parking entry/session.
- Additive AI review fields are created at application startup if absent. Existing rows and tables are preserved.
- The Security queue includes owner association, event type, confidence, capture reference, and safe-to-display evidence image URLs.
- Security/Admin opening, unlocking, and emergency commands require an explicit reason and are attributed to the authenticated operator. A sent command still does not mean the gate physically opened or that a car passed.

## Clarifications recommended before hardware acceptance

1. **Gate approval and entry linkage:** Define whether an authenticated Security action plus reason is sufficient approval, or whether every entry OPEN command must reference a specific confirmed AI event. Define the exception path for an unknown/unregistered vehicle, including who may approve it, mandatory reason, expiry, and audit fields. Current manual gate commands are not correlated to an AI event.
2. **Passage and session creation:** Specify the authoritative passage sensor, time window after gate opening, duplicate suppression key, and recovery workflow when the camera misses a vehicle but the loop detects passage. Create an active session only after physical passage evidence and successful vehicle authorization.
3. **Exit workflow:** Add explicit requirements for selecting an active session, handling ambiguous/unknown plates, Security approval, exit command, physical passage, session closure, and when a slot can become available. The supplied acceptance list stops before these cases.
4. **AI state model:** Separate processing (`RECEIVED`, `PROCESSING`, `SUCCEEDED`, `OCR_FAILED`, `FAILED`) from human review (`PENDING`, `CONFIRMED`, `REJECTED`, `RESOLVED`). A successful OCR result is not a verified identity or location.
5. **Event correlation and retries:** Require a source `event_id`/`command_id`, idempotency key, camera/controller identity, and rules for duplicate, delayed, replayed, and out-of-order MQTT/HTTP messages. Current database event IDs are generated locally; source-level deduplication is only a short in-memory plate cooldown.
6. **Timing and clock rules:** Define required timestamp fields per source, UTC serialization/storage, clock synchronization tolerance, and behavior when source time is absent or implausible. The existing database contains local-naive timestamps, so changing all existing timestamps needs a planned data migration.
7. **Camera/evidence behavior:** State the camera heartbeat/frame timeout, how offline differs from “no vehicle,” evidence image retention period, allowed URL/storage scheme, access policy, and redaction/deletion rules. Do not expose RTSP credentials or unrestricted image URLs.
8. **Slot adjudication:** Define freshness thresholds per sensor, sensor-vs-AI precedence, how long a mismatch remains `CONFLICT`, Security resolution, and whether a human-confirmed slot reserves/occupies the slot. `UNKNOWN`, `ERROR`, `CONFLICT`, offline, and stale must never count as available.
9. **Floor and slot confidence:** Define source-specific thresholds and require zone/polygon mapping for exact-slot AI. A camera topic can establish the floor only when its camera-to-floor mapping is configured and healthy; it cannot establish an exact slot by itself.
10. **Reports and metrics:** Define the event population and percentile/aggregation window for average, median, maximum, failed, and timeout metrics. Reports must exclude simulated/preview data and show missing telemetry instead of zero.
11. **Privacy and access matrix:** Specify which Security users may view full plates/images, Kiosk masking, audit-log readers, retention for CCTV and plate events, and tests for every role/API pair. UI navigation does not replace backend authorization.
12. **Schema ownership:** Mark which listed entities are mandatory for first release versus future modules (for example `sensor_events`, `login_history`, and `camera_slot_zones`) and identify their source of truth and retention. Existing source does not yet implement every named entity/workflow.

## Acceptance checklist needs completion

The supplied `REQUIREMENTS.txt` ends mid-sentence in Part 8 at `Student / Teacher เห็นข้อมูลของตนเ...`. Please restore the missing tail before treating it as a complete acceptance contract. At minimum, add pass/fail cases for:

- OCR failure with an image, corrected plate, and audit trail; no evidence or plate must not yield an access grant.
- Camera, broker, controller, sensor, and database outage; stale and out-of-order messages; recovery without false AVAILABLE state.
- Gate command accepted but no acknowledgement, no physical opening, and gate opening without passage; no session may be created in those cases.
- Passage without OCR, duplicate entry, duplicate exit, unknown/suspended vehicle, and ambiguous active session.
- Slot conflict, offline sensor, unknown slot, and confirmed floor with unknown slot.
- Student/Teacher cross-account data denial, Security/Admin authorization boundaries, audit logging, and preview-only mode making no network writes.

## Not yet live-verified

CiRA, camera, MQTT, ESP32 gate feedback, physical passage sensors, and production database are not connected or verified by this source review. The browser preview is read-only and cannot prove login/API authorization. Gate acknowledgements, physical position, vehicle passage, exit/session lifecycle, UTC data migration, and source-level idempotency remain integration work.

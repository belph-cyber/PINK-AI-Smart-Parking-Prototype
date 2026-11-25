# PINK AI integration API contract

This contract documents current source behavior and the minimum requirements for integrations. It does not claim that any external service or hardware is connected.

## Authentication

- Browser login: `POST /api/auth/login` with JSON `{ "username": "…", "password": "…" }`; use returned bearer token as `Authorization: Bearer <token>`.
- Student/Teacher, Security, and Admin screens are role-aware. Protected API endpoints remain authoritative; hiding a menu is not server authorization.
- CiRA HTTP ingestion: `POST /api/ai/detection` requires `X-Integration-Token`. Configure `CIRA_INGEST_TOKEN` in the service environment. Without it the endpoint returns `503`; a missing or incorrect token returns `401`.
- Do not put integration credentials in browser code, URLs, logs, screenshots, or the ZIP.

## Current HTTP endpoints used by the web UI

| Method and path | Access | Purpose / key response fields |
|---|---|---|
| `POST /api/auth/login` | Public | Authenticates account; returns `access_token`, `user` |
| `GET /api/auth/me` | Bearer | Current account and role |
| `GET /api/floors` | Public Kiosk | `floors` keyed by floor number; includes `total`, `free`, `occupied`, `unknown`, `data_state`, and occupied slot observations; `gate_plate` is review-only; `esp32` telemetry |
| `GET /api/parking/overview` | Public capacity view | Per-floor totals; `free_slots` counts only fresh `AVAILABLE` evidence |
| `GET /api/parking/my` | Bearer | Current account vehicle and parking history |
| `GET /api/hardware/status` | Current implementation | ESP32 heartbeat, no-parking alert, camera age, gate controller software report; gate acknowledgement/physical/pass-through are deliberately unknown |
| `GET /api/ai/events` | Security/Admin | AI review queue |
| `POST /api/ai/verify/{event_id}` | Security/Admin | Body action `CONFIRM`, `REJECT`, or `RESOLVE`; records reviewer and optional corrected plate separately from the AI result. Confirmed floor detections update only an existing active session; this never creates an entry or commands a gate. |
| `POST /api/gate/control` | Security/Admin | Explicit manual action; opening/unlocking/emergency commands require a reason and authenticated approver. Command status is separate from unknown acknowledgement/physical/passage values. |
| `GET /api/gate/logs` | Security/Admin | Recent gate command logs |
| `GET /api/cam/status` | Current implementation | Camera stream freshness (in-memory) |

The shared browser adapter is `web/static/js/api.js`. Set `window.PINK_API_BASE_URL` before loading it to target a separate API origin. Configure CORS and HTTPS on the server for cross-origin deployment.

## CiRA LPR HTTP body

`POST /api/ai/detection` accepts:

```json
{
  "camera_code": "GATE-IN-LPR",
  "plate": "กข 1234",
  "confidence": 0.92,
  "floor": 2,
  "slot_number": null,
  "image_url": null
}
```

`confidence` is optional and must be from 0 through 1. Missing confidence remains unknown and does not get a default score. All detections enter `PENDING` review. `floor` can be provided independently of `slot_number`.

For a vehicle that was detected but whose plate could not be read, send an explicit failure event; a blank plate by itself is rejected:

```json
{
  "camera_code": "GATE-IN-LPR",
  "plate": null,
  "vehicle_detected": true,
  "ocr_failed": true,
  "image_url": "https://camera-gateway.example/evidence/opaque-id"
}
```

Security must enter the manually verified plate before confirming this event. The original AI result remains blank and the correction is stored separately. The SQLite database receives additive `corrected_plate` and `corrected_slot_id` columns on application startup; the existing tables and records are not reset.

Example response:

```json
{
  "status": "ok",
  "result": {
    "event_id": 123,
    "status": "PENDING",
    "confidence_state": "REPORTED",
    "gate_action": "NOT_REQUESTED"
  }
}
```

## MQTT topics currently consumed

The service subscribes to the following topics on each configured broker:

| Topic | Expected input / behavior |
|---|---|
| `parking/gate/plate`, `cira/plate` | JSON plate result or supported text; optional `province`, `confidence`/`prob`, and `mode: "SHOT"`; detection is queued for review, never opens a gate. Blank plate is queued only if JSON explicitly reports `vehicle_detected: true` and `ocr_failed: true` (or `ocr_status: "FAILED"`). |
| `parking/floor/{floor}/{head\|tail}` | Floor LPR evidence; floor is known from topic, slot is not inferred; confidence is optional. A detected floor remains a suggestion until Security confirms it. |
| `parking/sensors/slots`, `parking/slots/status` | JSON containing a `slots` list with `id` and `status`; supported slot statuses map to the canonical states; missing/unknown status becomes `UNKNOWN` |
| `parking/alert/no_parking` (and `parking/alert/#`) | JSON `{ "active": true|false, "distance_cm": number, "message": "…" }`; freshness is bounded by ESP heartbeat and observation time |
| `parking/esp/status` | Controller software status/heartbeat text only; not physical servo feedback |
| `parking/cam/#`, `parking/image/#` | JPEG/PNG bytes or supported base64/data-URL payload; recognized frames are cached in memory for preview |

For example, a slot sensor should publish explicit states rather than a free-slot total alone:

```json
{
  "slots": [
    {"id": 1, "status": "occupied"},
    {"id": 2, "status": "free"}
  ]
}
```

Use MQTT QoS 1 for control/status messages, a unique client identity, broker ACLs, and TLS/authentication when supported. The currently included broker defaults and firmware behavior must be reviewed for the deployment before use.

## Gate command lifecycle

1. CiRA detection creates a pending evidence record and notifies Security.
2. Security reviews the event; this does not publish a gate command.
3. An authorized operator sends a separate manual command through `/api/gate/control`.
4. `COMMAND_SENT` means a broker accepted a publish attempt; it is not ESP acknowledgement.
5. An explicitly correlated controller acknowledgement is still unimplemented.
6. Physical open/closed input and vehicle passage sensor/loop events are still unimplemented.

Do not map a camera result, confidence threshold, MQTT publish return value, or `parking/esp/status` text to “gate open”, “vehicle entered”, or “access granted”.


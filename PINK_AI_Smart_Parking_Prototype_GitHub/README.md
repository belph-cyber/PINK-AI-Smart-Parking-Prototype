# PINK AI Smart Parking - Prototype

This repository contains the **prototype** of the PINK AI Smart Parking project for academic review. The production/real-device version is maintained separately by the project teammate and will be linked or merged after that version is ready.

## What is included

- Role-aware web prototype and Admin Console source.
- FastAPI backend and API/integration contracts.
- CiRA integration examples, ESP32/HC-SR04 firmware source, and project documents.
- Setup templates only; no live credentials or local database are included.

## Current limitations

- CiRA, cameras, MQTT broker, ESP32, physical gate feedback, and production database are not commissioned or live-verified by this prototype package.
- Hardware settings in examples are placeholders. Do not connect the firmware to a shared/public broker for real control.
- No database or default account/password is included. Provision an authorized database and account locally.
- This is a prototype, not a production deployment.

## Run locally

1. Install dependencies: `py -3.13 -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and set a unique `JWT_SECRET_KEY`, database settings, and local device values.
3. Prepare the database using the team's approved schema/provisioning process. Do not use legacy reset/seed scripts.
4. For UI/API-only mode, set `PINK_DISABLE_MQTT=true`.
5. Run `py -3.13 service.py` and open `http://127.0.0.1:8000/login`.

## Project documents

Start with `docs/PROJECT_DOCUMENTATION_INDEX.md`. It links requirements, diagrams, test plan, role responsibilities, user guide, API contract, and integration guide.

## Team contributions

The project team has four members. See `docs/TEAM_ROLES_AND_CONTRIBUTIONS.md`; confirm the descriptions and evidence with all members before final academic submission.

# ProMax phone-side assessment V1 (verdict C: evidence insufficient)

Analysis-only. No APK bypass attempted. Interoperability research only.

## Artifact search (§19) — CONFIRMED absence

- Upstream file sets (both mirrors): HTML/JS + manifests + firmware only; no APK/AAB/Kotlin/Java/Flutter/React-Native/BLE-test-app in working trees or `git ls-tree` names — CONFIRMED.
- Firmware: zero `com.vietmap/vietmap/VietMap/accessibility/intent/flutter/react` in all images; `notification`×0 classic (C3/S3 ×3 = BLE-GATT notification PDU strings, proven non-Android contexts); `broadcast`×0 classic — CONFIRMED.
- Web JS (all 6 pages): zero `8a7e` hits; FFF0/VIETMAP_HUD only — CONFIRMED — browser pages are mgmt-only; nav is app-only.

## Direct-vs-companion (§20): C

- A (VietMap directly implements 8a7e): no package name, service class, UUID constant, listener, or binding — NO evidence. `VIETMAP_HUD` name alone is NOT proof (explicitly refused).
- B (companion translates): consistent with `want/can` negotiation + web/FFF split + bare-table JSON, but no companion binary/source observed — NO proof.
- **Verdict: C (evidence insufficient).** Leaning: sender holds LIVE semantics (MEDIUM, from normalized short keys + `can` renderables), but direct-vs-companion cannot be distinguished statically.

## Consequences

- Background service/reconnect/screen-off/permissions/mods/root: all UNKNOWN (no app to inspect).
- Licensing/subscription gating: no credentials/keys/tokens in firmware; nothing bypassed; protocol-fact reuse only.
- C2M mapping readiness: key NAMES translatable (HIGH); values/semantics NOT — Architecture A (companion→C2M Wi-Fi neutral feed) unchanged; no new hardware justified by phone-side findings.

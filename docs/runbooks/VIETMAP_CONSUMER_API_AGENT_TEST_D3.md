# C2M D3 — VietMap Consumer API: agent test runbook

**Status:** READY_FOR_AGENT / **NOT EXECUTED**  
**Created:** 2026-10-14  
**Owner intent:** Check whether the VietMap free Trial **Consumer API (default)** can provide useful road geometry, speed-limit/sign/camera data for the C2M dashcam's offline-first GPS + TSR warning stack. A **Tilemap consumer** is available separately but is unnecessary for this phase.

## 0. The decision to make

**Primary question:** "With the owner's VietMap Trial *API* key (not Tilemap key), which *documented and permitted* endpoints can C2M use, and do any actually return speed limits/physical traffic signs?"

Deliver one evidence-backed verdict for each:
- **API Auth**: PASS/BLOCKED — one authenticated documented request.
- **Route v4**: PASS/PARTIAL/BLOCKED — road polyline + direction, not wrongly categorized as speed-sign data.
- **Map Matching**: PASS/PARTIAL/BLOCKED — optional road snapping for pre-recorded trace, not an assumed live position/sign API.
- **Driving Alert / Speed Alert**: AVAILABLE/BLOCKED_BY_ENTITLEMENT/UNDOCUMENTED — only test if an *official contract* and permission for this account exist.
- **Tilemap**: OUT_OF_SCOPE unless UI map becomes explicitly necessary.
- **C2M readiness**: HOST_API_PROVEN / DEVICE_UNTESTED. No on-camera Wi-Fi, NMEA or display/audio integration is established by testing an API from a PC.

This runbook calls for a *minimal live test after a key is available*. No key, no API calls. Do not stop coding/research merely because Driving Alert entitlement is absent; record it and continue the offline+OSM D3 lane.

## 1. What VietMap officially documents (verified 2026-10-14)

| Service / Consumer | Documented behavior | Trial status (defaults; Console is authoritative) | Agent action |
| --- | --- | --- | --- |
| **Consumer \`default\`, API / Services key** | Search/Autocomplete, Route, Reverse, Match etc | Each API permission/limit separate | **Use for host API smoke** |
| **Consumer \`public tile\`, Tilemap key** | Vector styles, raster tile layers in client | Separate consumer, not for Map APIs | **Do NOT substitute** |
| **Autocomplete v4** | \`GET /api/autocomplete/v4\`, search text | On, 200/min (no daily cap shown) | Optional cheap auth smoke: 1 call |
| **Route v4** | \`GET /api/route/v4\`, two \`point=lat,lon\` entries; \`vehicle=car\`; geometry and navigation instructions | On, 200/min and 500/day | Required core smoke: 1 call |
| **Map Matching** | \`POST /api/match-tolls?api-version=1.1&vehicle=1\`, JSON GPS trace as \`[[lon,lat], ...]\` | On, 200/min and 500/day | Optional 1-call match |
| **Driving Alert** | Named in Trial quota table, no public request/response contract verified | **Off** (no default Trial quota) | **Do not invoke or reverse-engineer unauthorized service** |
| Traffic | Visualization layer API, not road sign JSON | **Off** | Skip |
| Tile | Tilemap layers | **Off** in Trial API quota table; separate consumer | Skip |

- VietMap gives 2 different keys. With a Tilemap key calling a Map API, response **423** can mean not enabled/invalid entitlement, not a correct test of Route.
- Official API request generally authenticates via query parameter \`apikey\`, so the key can leak via shell history, URLs, proxy logs, screenshots or error messages. **Never print a full URL containing the key.**
- Route v4 \`paths[].instructions[].sign\` is a **turn-direction code**, not a physical traffic sign such as P.127. Route \`annotations\` documented values are \`congestion\`, \`congestion_distance\`, \`toll\` — do not infer \`maxspeed\`.
- Route v4 \`point\`: **latitude,longitude**, repeated; Match input: **longitude,latitude** pairs. Check coordinate order carefully.
- Standard new-account docs mention **60,000 initial free transactions** with no credit card, but per-API limits and trial lifetime are separate. Read the owner's Console **before** any live test, not marketing headlines. Routing pricing formula is \`floor(points/5)+1\` transactions in current documentation; a 2-point smoke uses 1 according to the formula.
- VietMap documented HTTP \`401\` for invalid key, \`423\` for blocked/not enabled/exhausted; inspect a **redacted** short response code. APIs may also return \`code: OVER_DAILY_LIMIT\` inside JSON. **Do not auto-retry 401/423/429**.

Official sources:
1. https://maps.vietmap.vn/docs/map-api/console/usage-limitation/
2. https://maps.vietmap.vn/docs/map-api/console/register-api-key/
3. https://maps.vietmap.vn/docs/map-api/console/manage-api-key/
4. https://maps.vietmap.vn/docs/map-api/route-version/route-v4/
5. https://maps.vietmap.vn/docs/map-api/match-tolls/
6. https://maps.vietmap.vn/docs/map-api/console/request-to-transaction/
7. https://github.com/vietmap-company/vietmap-react-native-navigation
8. https://github.com/vietmap-company/vietmap_speed_alert_ios

Research reference: \`docs/research/VIETMAP_FREE_API_C2M_D3_20261014.md\` and \`docs/research/LILY_API_DEEP_DIVE_D3_20261014.md\`.

## 2. Secret handling & operator preflight

1. Work on \`feature/d3-tsr-events-20261014\` or its descendant; leave \`main\` untouched.
2. Owner only needs to set the **Consumer \`default\` API key** on their local machine or authorized secret store. The key **must never** appear in this repository, agent messages, GitHub PR, CI logs, screenshots, terminal commands, HTTP traces, shell \`set -x\`, or readable public web pages.
3. Prefer host-side test on Windows/WSL2 or authorized backend; **do not embed a VietMap service key inside distributable C2M firmware or browser client**. Do not use the Tilemap key as substitute. If using a backend, restrict origin/IP, key scope and quota in the Console.
4. Avoid persistent .env files unless the local environment guarantees they cannot be committed. Repo \`.gitignore\` ignores \`build/\`; place **raw** private response/body inside \`build/private/vietmap/\` only when justified, securely delete afterward, and never publish raw responses carrying location data.
5. Check Console \`Consumers > default > Detail\`: account type and trial expiration, Route/Match enabled, Driving Alert enabled/disabled, current used/available quota, API-level rate limits and whether any charges are possible. If no Console access, mark \`ENTITLEMENT_NOT_VERIFIED\`; do not guess.
6. **No live call without locally supplied Service API key.** If missing, complete documentation/schema/unit-test lane offline and return \`BLOCKED_NO_KEY\`; do not ask the owner to paste secrets into chat.

## 3. Minimal host smoke: single Route v4 call (recommended first)

Use Python standard library; enter key at a private prompt, no key in shell command line. This snippet makes **one** HTTPS call, prints only a redacted schema-level summary, has an explicit timeout, and does not log its full URL.

\`\`\`bash
python3 - <<'PY'
import getpass, json, os, urllib.parse, urllib.request, urllib.error

key = os.environ.get("VIETMAP_SERVICE_KEY") or getpass.getpass("VietMap Consumer API key (hidden): ")
if not key:
    raise SystemExit("BLOCKED_NO_KEY")
params = [
    ("apikey", key),
    ("point", "10.759,106.675"),
    ("point", "10.765,106.684"),
    ("vehicle", "car"),
    ("points_encoded", "false"),
]
url = "https://maps.vietmap.vn/api/route/v4?" + urllib.parse.urlencode(params)
req = urllib.request.Request(url, headers={"Accept":"application/json", "User-Agent":"C2M-D3-API-evaluation/1.0"})
try:
    with urllib.request.urlopen(req, timeout=12) as response:
        http_status = response.status
        raw = response.read(2 * 1024 * 1024 + 1)
except urllib.error.HTTPError as exc:
    # Do not print the exception or exc.url (the query contains the key).
    print(json.dumps({"http_status":exc.code, "verdict":"BLOCKED_OR_ERROR"}))
    raise SystemExit(1)
except (urllib.error.URLError, TimeoutError):
    print(json.dumps({"verdict":"NETWORK_ERROR_REDACTED"}))
    raise SystemExit(1)
if len(raw) > 2 * 1024 * 1024:
    raise SystemExit("RESPONSE_TOO_LARGE")
try:
    obj = json.loads(raw)
except (ValueError, UnicodeError):
    raise SystemExit("INVALID_JSON_REDACTED")
paths = obj.get("paths") or []
first = paths[0] if paths and isinstance(paths[0], dict) else {}
instructions = first.get("instructions") or []
shape = {
    "http_status": http_status,
    "api_code": str(obj.get("code", "missing"))[:80],
    "path_count": len(paths),
    "top_level_keys": sorted(obj.keys()),
    "first_path_keys": sorted(first.keys()),
    "instruction_keys": sorted(instructions[0].keys()) if instructions and isinstance(instructions[0],dict) else [],
    "has_explicit_speed_limit_field": any(k in first for k in ("maxspeed", "speed_limit", "speed_limit_kmh")),
    "has_explicit_sign_collection": any(k in first for k in ("traffic_signs", "signs")),
}
print(json.dumps(shape, ensure_ascii=False, indent=2))
PY
\`\`\`

**Expected basic PASS:** HTTP 200 + \`code=OK\` + at least one path containing geometry and instructions, for valid reachable points. If \`ZERO_RESULTS\`, retry **at most once** with verified nearby connected points, after checking quota; do not loop. **No speed sign field** is a meaningful negative finding, not a Route failure.

**Important:** This uses illustrative public HCMC coordinates, not the owner's real location or GPS history. A host-only smoke does not attest device API connectivity.

## 4. Optional low-cost endpoint checks

Do these **only** if the quota/permissions are known and the Route result merits further work.

### A. Autocomplete v4 (one request)
Documented format:
\`GET https://maps.vietmap.vn/api/autocomplete/v4?apikey=...&text=197%20tran%20phu&focus=10.7588,106.6753\`.
Use the exact same secret-safe \`urllib.request\` pattern; classify result as address data, **not** road-sign metadata.

### B. Map Matching (one request)
Documented format:
- \`POST https://maps.vietmap.vn/api/match-tolls?api-version=1.1&apikey=...&vehicle=1\`
- Header \`Content-Type: application/json\`
- Body \`[[106.757849,10.817956],[106.759134,10.821371],[106.760694,10.825196]]\` — **longitude first**.

Check HTTP status, \`path\` length and \`tolls\` structure only; don't publish a raw route with owner coordinates. This is described as historical trace matching and toll calculation; even a full PASS **does not** prove C2M can retrieve legal speed limits.

### C. Driving Alert / Speed Alert — conditional gate, NOT a guessed URL
- If **OFF** in Console: \`BLOCKED_BY_ENTITLEMENT\`, *zero HTTP calls*. Do not try to "unlock" using another consumer or a guessed private URL.
- If **ON** but no official documented contract: \`BLOCKED_NO_CONTRACT\`, request official documentation and permission; *zero calls*.
- If **ON + documented contract + entitled key**: test **one** official request against a known test coordinate only, with authorization/terms confirmed. Record the **field names, data types, units, speed sign vs effective road speed distinction, direction/bearing, confidence/freshness, vehicle applicability, cache TTL/licensing**. Redact secrets and precise personal GPS.
- Speed Alert SDK examples in official VietMap GitHub repos are proof that an alert product exists, **not** proof the ordinary Consumer API key unlocks their private wire protocol or that an iOS SDK runs on ARM/Linux C2M.
- Ask \`maps.info@vietmap.vn\` for endpoint + sample response, separate \`apiKey\`/\`apiKeyId\` requirements, Trial/test entitlement, car support and SD/offline cache permissions.

### D. Consumer Tilemap
**Skip.** Only invoke it in a separate front-end map UI milestone using its own key and proper referrer limits. Tiles do not provide authoritative speed-limit/sign records simply because a map can be rendered.

## 5. Tight budget and runtime constraints

- **Hard cap 5 requests total** for initial smoke (1 Route required, up to 1 Autocomplete, up to 1 Match, optionally 1 documented authorized Driving Alert, 1 spare retry only if justified). Agent must count attempted requests, even when blocked.
- One sequential request at a time; no automatic retries, polling, concurrent calls, per-GPS-tick queries, reverse geocoding for every coordinate, or full-country scraping.
- Timeouts ≤12 seconds (unless officially required otherwise), JSON size bounded to 2 MiB for the smoke, HTTPS only.
- HTTP 401/423/429, exhaustion, missing contract or trial restrictions → **stop that endpoint**; record state and proceed to other independent tasks. Do not upgrade/pay without owner instruction.
- Snapshot Console used/remaining before/after (numeric counts or redacted text only) to confirm actual consumption; totals may lag.

## 6. Evidence output and acceptance report

Write **sanitized** \`docs/research/VIETMAP_CONSUMER_API_TEST_RESULT_D3.md\` only after a real test. If untested, do not create a fake PASS report. Include:

\`\`\`text
Date/time (ICT):
Branch + HEAD:
Account tier and expiry: [no account ID/key]
Consumer tested: default / API
Console Route status; Driving Alert status:
Calls attempted: count and endpoint NAME (not URL containing key)
HTTP status + JSON API code (no raw body)
Response structure: top-level, geometry, instructions, road ID,
    maxspeed/speed-limit/sign/speed-camera typed fields or explicit absence
Latency ms (host); payload bytes; source of timing
Quota used before/after (if visible)
Entitlement/contract/cache license status:
Decision per API: PASS | PARTIAL | BLOCKED (+ reason)
C2M fit: API-only metadata vs physical sign vs per-road legal speed
Recommendation: integrate? exactly what schema and where?
Remain blocked: device networking, native GPS, alert output, permission
\`\`\`

No bogus assertions based on presence of a field named \`sign\`. A road speed limit must have typed numeric speed + road/direction/vehicle applicability and provenance; phone navigation turn metadata is NOT sufficient.

If a real sign API is available, normalize as an **optional** \`VietMapProvider\` of \`RoadIntelligence\`, with provenance, timestamps and license. Do not displace offline sign data, stock TSR or OSM. No client key in GitHub or distributable firmware; prefer server broker with authorized cache policy. C2M D3 has not demonstrated simultaneous AP+STA, on-device Internet, non-consuming GPS source or warnings; keep host API PASS separate from device gate.

## 7. Agent execution directive (ready to paste)

> Continue C2M D3 on branch \`feature/d3-tsr-events-20261014\`. Execute this VietMap test runbook autonomously. Inspect Console entitlement first if available; use only the local **Consumer default/API** service key from an authorized secret environment, never request/paste it into chat or logs. Start with one Route v4 smoke, then optionally Autocomplete/Match; total max 5 HTTPS requests with no retry on 401/423/429. Do **not** call Driving Alert unless it is enabled AND VietMap supplied a documented authorized API contract. Do not use Tilemap for data testing; do not guess private endpoints. Save only sanitized evidence and compare with existing Lily/OSM offline + road matching. Mark blocked parts plainly, don't let them block offline D3, don't touch main or flash camera. For code changes, run relevant tests; review through Codex Combo Review-Normal/Review-Hard via 9router if needed, **not** native AO Review. Report outcome, diff, HEAD, tests and next concrete feature action.

## 8. Related D3 files

- \`docs/research/VIETMAP_FREE_API_C2M_D3_20261014.md\` — provider feasibility, SDK evidence.
- \`docs/research/LILY_API_DEEP_DIVE_D3_20261014.md\` — Lily/OSM and physical-sign distinction.
- \`docs/design/D3_HYBRID_CONNECTIVITY_20261014.md\` — C2M Wi-Fi/AP+STA feasibility.
- \`docs/design/ROAD_INTELLIGENCE_DESIGN.md\` — normalized provider + fusion design.
- \`fw/warner/README.md\` — current host/replay-only status; not a live TSR daemon.

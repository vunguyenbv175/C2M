# VietMap API free/trial feasibility for C2M D3 — 2026-10-14

**Verdict:** VietMap is a strong *Vietnam-specific candidate* for the C2M hybrid GPS + sign warning design, but **the public free Trial does not expose a documented usable road-sign/road-speed endpoint**. The relevant product is named **Driving Alert** in the official quota matrix and is **OFF by default**, as is Traffic. **Route v4** can be tested on Trial for navigation/road snapping, but its published contract does **not** advertise a per-segment speed-limit field or physical-sign geometry. Do not conflate \`instructions[].sign\` (TURN ICON enum) with a speed-limit sign.

## Official evidence (checked 2026-10-14)

- New signup: https://maps.vietmap.vn/console-v2/register
- Docs: https://maps.vietmap.vn/docs/map-api/console/register-api-key/
  - 60,000 free transactions (approx. VND 3,000,000 stated value), **no card required**.
  - Public website https://maps.vietmap.vn/web advertises **2-month trial**, **under 60,000 transactions/month**, with daily caps. Another older https://vietmap.vn/maps-api page advertises **1 month** and **250 route/day**, so prefer updated 2026 console/docs; **account activation/actual expiration must be verified in Console**. Free is *time limited*, **not perpetual**.
- Explicit Trial API policy: https://maps.vietmap.vn/docs/map-api/console/usage-limitation/
  - Route 200/min, 500/day, **On**
  - Match 200/min, 500/day, **On**
  - Reverse, Geocode 200/min, 500/day, **On**
  - **Driving Alert: Off; Traffic: Off; Tile: Off** (per docs). Contact VietMap to enable; do not assume approval or free allocation.
- Route v4 official schema: https://maps.vietmap.vn/docs/map-api/route-version/route-v4/
  - \`GET https://maps.vietmap.vn/api/route/v4?apikey=...&point=LAT,LON&point=LAT,LON&vehicle=car&heading=DEGREES\`
  - \`point\` in **lat,lon** order; at least 2 points. \`points_encoded=true\` default.
  - \`annotations\` supports only \`congestion\`, \`congestion_distance\`, \`toll\`.
  - \`paths[].instructions[].sign\` = **turn/navigation instruction sign**, not a traffic-sign code.
  - No \`maxspeed\`, \`speed_limit\`, \`traffic_signs\` or speed-camera schema field in the public v4 response.
  - Marketing/traffic docs mention signs + speed limits along route, **not borne out by published v4 JSON contract**. This may refer to SDK, commercial/feature-flagged data, Driving Alert or a non-public extension: unverified.
- Map matching: https://maps.vietmap.vn/docs/map-api/match-tolls/ — \`POST /api/match-tolls?api-version=1.1&apikey=...&vehicle=1\`; accepts GPS track as JSON \`[[lon,lat],...]\`, explicitly history/toll oriented, **not** documented as real-time sign/limit service.
- Traffic: https://maps.vietmap.vn/docs/map-api/traffic/ — traffic map PNG tiles \`GET /api/tf/{z}/{x}/{y}.png?apikey=...\`; **not** sign geodata. Off by default for Trial.
- SDK Android Navigation: https://maps.vietmap.vn/docs/sdk-mobile/sdk-android/navigation/
- React Native Navigation public changelog https://github.com/vietmap-company/vietmap-react-native-navigation/blob/main/CHANGELOG.md documents \`startSpeedAlert()\` and automatic map-data speed-limit detection as of release 1.6.0 (2025-09-09). **SDK/app capability != public stand-alone API**; Android/iOS SDK cannot execute on C2M ARM Linux without a phone bridge.
- VietMap public overview advertises **200,000+ traffic signs**, but does **not** offer a bulk download or a public sign-query endpoint: https://maps.vietmap.vn/docs/map-api/overview/
- VietMap backend integration guidance: https://maps.vietmap.vn/docs/vi/map-api/overview/ . Keep Service key **on backend**, do not embed in publicly distributed firmware or client application. Console creates separate Services and Tile keys; not interchangeable: https://maps.vietmap.vn/docs/map-api/console/manage-api-key/
- Billing: https://maps.vietmap.vn/docs/map-api/console/request-to-transaction/
  - Route 1 × (\`floor(number_of_points/5)+1\`) transactions per call per current published formula (verify boundary semantics in Console). A 2-point request typically 1 transaction.
  - Quota is **per-account total plus per-API daily/minute**; don't equate 60,000 transactions with 60,000 routing calls in one day.

## C2M priority matrix

| Route | Feasibility | Decision |
|---|---|---|
| Public Route v4 Trial | **Testable with developer key** | For route polyline, road choice/heading, not a known speed-limit oracle |
| Driving Alert Trial | **Off**, no documented public endpoint | Ask official support for access + sample response + terms |
| Official Android/React-Native Navigation SDK | Client SDK exists; auto speed alert claimed | Optional phone-bridge research, not deployable as C2M-native API |
| Traffic PNG API | **Off** and visualization layer | Not useful for detecting signs |
| Map Match | On, historical track matching | Maybe enrichment/QA; no documented current road limit |
| Reverse geocode | On | Road-name context only, not legal speed limit |
| Unauthorized VietMap LIVE/internal app endpoints | Unknown, outside public contract | Exclude |

## Free key onboarding (individual account)

1. Register at https://maps.vietmap.vn/console-v2/register; docs say **Company Name = Individual**, email = personal email (no credit card required).
2. Verify email; VietMap sends **Service key** and **Tilemap key** separately.
3. Use https://tools.vietmap.vn/playground/route or backend for one Route v4 test with your own key. Do not transmit keys in issue/PR/build logs.
4. In Console check Trial expiry, total credits, the current API status list (Driving Alert On/Off), and per-day budget.
5. An actual run needs user account/API key and HTTPS connectivity; **no authenticated live API request was made during this static research**.

Example Route v4 request (the response should be parsed according to public schema, NOT inferred sign metadata):

\`\`\`text
GET https://maps.vietmap.vn/api/route/v4?apikey=SECRET&point=10.759,106.675&point=10.765,106.684&vehicle=car&points_encoded=false
\`\`\`

## What to ask VietMap support (maps.info@vietmap.vn / Zalo Vietmap Solutions)

Request an evaluation entitlement and API contract for **Driving Alert / Speed Limit / Speed Camera** for a personal C2M dashcam prototype; specifically:
- Does Driving Alert expose a **documented HTTPS endpoint** for querying by \`lat, lon, heading\`, \`radius\`, \`vehicle=car\`, and/or route polyline? Provide **method, path, auth, sample response, field units, mapping to OSM/vendor sign types**.
- Does it return **physical sign points** vs **effective per-road speed-limit metadata**, ahead distance, bearing/direction, speed-camera points, geometry and data freshness? Can it distinguish two carriageways or lanes?
- Is the feature available on **Trial**, and with what quota/rate limits, free period, billing rates after trial?
- Are cache-on-SD, offline replay on one owner's camera, redistribution to another device, attribution and expiry permitted by license? Any strict TTL or purge rule?
- Is developer use from **Linux ARM device via owner's HTTPS proxy/backend** authorized, or only via mobile navigation SDK?
- How do alerts from Android navigation SDK relate to Driving Alert API? Is there a public standalone equivalent?

## C2M D3 architecture decision

\`\`\`text
C2M GPS (non-consuming tap) + stock TSR (actual captured schema)
                  |
           RoadIntelligence
            /     |      \
  offline signs + OSM  future VietMap DrivingAlert (optional, permissioned)
            \     |      /
          normalized observations with source, heading, position,
          date, confidence, effective-speed-limit versus physical sign
                  |
      advisory audio/display (after on-device transport validated)
\`\`\`

- **Do not require VietMap to ship the first working D3 build**. Use C2M offline DB + direction-aware OSM, then optional VietMap once contract and entitlement verified.
- For paid/proprietary API service key, use a private backend broker (or owner-operated proxy), caching only as permitted; **do not commit secrets** to C2M repository/flash file.
- Although VietMap overview says 200k+ traffic signs, no proof of 200k freely downloadable sign records or unrestricted storage.
- Most of the D3 work needed even if Driving Alert becomes accessible: GPS fresh/tap, AP+STA or phone relay, road geometry/direction matching, cooldown, device audio/M4 contract.
- The \`C2M\` D3 PR remains a **research/prototype branch**, not a device-flash candidate.

## Evidence confidence
- **HIGH:** registration, Trial table/status, API/route fields, SDK speed alert changelog (direct official sources).
- **MODERATE:** availability of monthly 60k for 2 months to a particular new account; current web advertises this, older page differs, confirm actual Console.
- **UNKNOWN:** Driving Alert endpoint, true free entitlement, live sign coverage quality by route, offline cache/redistribution rights, output from a C2M physical device.

No registered API key was used and no VietMap server was queried with authenticated credentials.

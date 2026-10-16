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


## Deep dive addendum: independently confirmed official Speed Alert interfaces

Two first-party, public VietMap GitHub repos provide stronger evidence that
their standalone **Driving Alert / Speed Alert backend** exists, even though
Trial entitlement and an authorized public wire contract are **not** granted.

### 1) React Native Navigation SDK supports free-drive Speed Alert

https://github.com/vietmap-company/vietmap-react-native-navigation

- Documents \`VietMapNavigationController.configureAlertAPI(apiKey, apiKeyId)\`
  using a **Speed Alert-specific API key and key ID**, separate from the
  navigation/route key.
- \`apiKeyAlert\` is an additional SDK property.
- \`startSpeedAlert()\`, \`stopSpeedAlert()\`, and
  \`isSpeedAlertActive()\` work in SDK. Its README explicitly describes
  *manual/free-drive monitoring even when not navigating*.
- \`configVehicleSpeedAlert\` carries type, seats and weight. SDK integration
  thus knows vehicle class; don't invent a universal car speed limit.
- Public CHANGELOG records speed limit alerts (v1.6.0, Sep 2025) and camera,
  traffic-light and toll voice alerts (v1.7.0, Oct 2025). Treat claims as SDK
  documented capabilities, **not** as evidence that free Route v4 returns signs.
- Testable *on a licensed Android phone with granted Alert credentials*,
  not on C2M ARM/Linux directly. A licensed phone bridge can deliver normalized
  alert events over the camera AP, if the SDK's terms allow relay.

### 2) Proprietary iOS Speed Alert SDK shows zone-oriented graph engine

https://github.com/vietmap-company/vietmap_speed_alert_ios/blob/main/README.md

- README is explicit: "**only for Vietmap MAPs API enterprise customers**".
- Graph-engine setup example mentions \`ZoneNetworkManagerV2(baseUrl:
  "https://dev.fastmap.vn/drivingalert", vehicleType:1, seats:4,
  weights:1500)\`. This is an **example SDK base URL**, apparently
  development-specific, **NOT** verified production endpoint or public API
  specification. Do not guess URL suffixes, use it as an unauthenticated
  crawling target, or substitute the normal VietMap trial Route key.
- \`updateLocation(lat,lng)\` refreshes a zone cache when location moves;
  \`processGps(lat,lng,bearing,speedKmh,accuracy)\` processes GPS locally.
  The SDK emits current speed-sign bitmap, speed status, next sign+distance,
  camera+distance, toll+distance and PCM/WAV audio callbacks.
- That architecture closely matches proposed C2M D3: **regional prefetch
  + offline graph/road matching + live GPS + simple output**.
- Crucial applicability caveat: the same README says speed alerts currently
  support **vehicleType 3,5,6 (bus/truck/trailer)**, not ordinary
  **vehicleType 1 car**, despite the sample using 1. Request real passenger-car
  authorization/coverage/compatibility evidence from VietMap rather than
  promising it will work on user's car.
- The iOS SDK is prebuilt XCFramework; its code/binaries are **not** a
  transferable Linux ARM firmware module, regardless of the C++ core claim.

### Correct next developer question

Ask for a **free evaluation of Speed Alert/Driving Alert** with separate
\`apiKey\` and \`apiKeyId\`, a validated **car (vehicle type 1)** flow, and
their permitted **Linux headless / camera / regional-cache** integration.
If headless API is not offered, seek a *licensed phone-app event relay*
or fall back to Lily-style offline + OSM/Overpass. Do not put unsupported
enterprise-only SDK into the D3 shipping path.


## 2026-10-14 supplement: VietMap Agent documentation link (user-supplied)

Official resource: https://maps.vietmap.vn/docs/assets/agents/agents.zip
- The URL is an actual binary ZIP (\`application/x-zip-compressed\` according to browser fetch), **but archive extraction was NOT possible in this review environment**. Do not imply that its contents have been inventoried.
- A related, independently retrievable official agent guide is:
  https://maps.vietmap.vn/docs/assets/agents/map-display.txt
  and is linked under **"Map Display Agent Doc"** on
  https://maps.vietmap.vn/docs/map-api/tilemap/
  and https://maps.vietmap.vn/docs/sdk-mobile/overview/.
- That guide explicitly covers **tilemap styles, VietMap GL JS, Flutter, React Native, Android/iOS SDK, traffic tile overlays, static-map PNG**. It documents
  \`/maps/styles/{tm,lm,dm,hm}/style.json\`, \`/api/tf/{z}/{x}/{y}.png\`
  and \`POST /api/maps/statics/tm\`.
- The guide contains **no section or endpoint describing Speed Alert, Driving Alert, physical traffic-sign/road-speed retrieval, or free Driving Alert entitlement**.
- Security detail: browser/mobile tile styles expose the tile key and should use console domain/IP/quota restrictions; backend Static Map / Traffic proxy keys belong on a server.
- Coordinate boundary: GL JS uses \`[lng,lat]\`, most VietMap REST points use \`lat,lng\`.
- **Reassessment:** VietMap's official "AI agent" documentation **cannot** be treated as proof of free speed-sign API. Retain status \`Driving Alert trial OFF / SDK enterprise or special key\` from independently checked product docs, unless full ZIP/API contract supplies contrary evidence.
- **Follow-up:** acquire the ZIP itself as a local attachment or using a network-enabled build environment; inventory file manifest, search \`driving|speed|alert|maxspeed|traffic_sign|quota|offline|cache\`, and trace full request/response/auth for any candidate endpoint. Do not guess what unseen ZIP contents say.

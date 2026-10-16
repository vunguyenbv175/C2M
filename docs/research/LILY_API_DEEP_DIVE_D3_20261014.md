# Lily Android APK traffic-sign API → C2M D3: technical delta review
**Date:** 2026-10-14. **Scope:** \`com.sensornotes.xiaozhi\` APK 3.8.1 (as already reverse-reported), existing C2M converter and DB inspection, publicly documented Overpass/OSM/Mapillary APIs.

**Evidence boundary:** The full 178 MB XAPK and an authenticated packet capture were **not** available in this review session. Current Lily-specific app behavior below is grounded in \`docs/reverse/APK_LILY_TRAFFIC_SIGN_DATA_V1.md\`, **not** independently re-decompiled today. Public API contracts were checked against the OSM Wiki and Mapillary docs; **no live sign-query response was obtained**, and no Lily private server was tested.

## 1. Headline finding
There is **no verified Lily-proprietary public traffic-sign API** available for C2M in current evidence. Lily 3.8.1 appears to combine:
- Bundled offline \`assets/vnsigns/*_pins.bin\` data (28,551 point signs).
- Bundled \`assets/vnsigns/*.bin\` polylines (roads; report shows \`{"h":"primary","n":"...","p":[[lat,lon],...]}\`).
- Read-only **OSM Overpass** requests for road maxspeed / cameras / traffic features.
- Phone-side camera/ML and user-submitted reports. Neither becomes an API for a separate embedded device merely because APK contains relevant classes.

**Practical conclusion:** Implement an independent OSM Overpass provider and a Lily-style *schema adapter*, not an unofficial Lily-client emulator. Future **authorized** Lily API integration can be inserted as another provider if confirmed.

## 2. Actual source/endpoints identified in APK teardown

| Source | Endpoint/data | Role | Readiness |
| --- | --- | --- | --- |
| Lily offline | \`assets/vnsigns/<grid>_pins.bin\` | point signs with position, type, speed and optional directions | Existing private converted DB; redistribution rights unverified |
| Lily offline | \`assets/vnsigns/<grid>.bin\` | road names/classes/geometry for map matching | Source format known, conversion/matching not yet integrated in \`c2m-warner\` |
| Overpass primary | \`https://overpass-api.de/api/interpreter\` | OSM query, JSON response | Public API; shared servers; rate-limit |
| Overpass alternate | \`https://overpass.private.coffee/api/interpreter\` | OSM query | Public instance; availability not guaranteed |
| Overpass historical alias | \`https://overpass.kumi.systems/api/interpreter\` | OSM query | **Private.coffee was previously known as kumi.systems**; avoid counting as two fully independent providers |
| Overpass alternate | \`https://maps.mail.ru/osm/tools/overpass/api/interpreter\` | OSM query | Public instance; independently validate |
| MapLibre/OpenFreeMap | \`tiles.openfreemap.org\` | background *visual* map tiles | **Not** a speed limit / traffic sign endpoint |
| Lily proprietary sign API | **not found or documented** | hypothetical | Do not claim available |
| Mapillary (independent) | \`graph.mapillary.com/map_features\`, public traffic-sign feature tile layer | extra sign detection provider | Real API with access token; not a Lily backend, VN coverage/rights unmeasured |

Overpass instance policies and availability: https://wiki.openstreetmap.org/wiki/Overpass_API
Mapillary evidence: https://help.mapillary.com/hc/en-us/articles/115002332165-Map-features and https://mapillary.github.io/api-demo/.

## 3. Query mechanics: derive *our own* API calls, not undocumented Lily request bytes

Lily teardown documents classes of OSM requests:
- \`way["maxspeed"]\` within 1,200 m.
- \`node["highway"="speed_camera"]\`, \`node["highway"="traffic_signals"]\`, \`node["highway"="stop"]\`, \`node["traffic_calming"]\`, \`node["railway"="level_crossing"]\`, \`node["overtaking"="no"]\`, and some \`way["tunnel"="yes"]\` / \`way["toll"="yes"]\` within 900–1,200 m.
- JSON queries with \`timeout:12..60\`.
- **Not proven from currently preserved evidence:** exact user-agent, HTTP GET vs POST, complete request body, remote JSON samples, auth, app client cache keys, retry timing, whether a Lily-hosted server enriches responses.

A proposed, independent \`OverpassProvider\` query for C2M is below. It is an **engineering proposal**, not a byte-exact Lily call:

\`\`\`overpass
[out:json][timeout:15];
(
  way(around:900,LAT,LON)["highway"]["maxspeed"];
  way(around:900,LAT,LON)["highway"]["maxspeed:forward"];
  way(around:900,LAT,LON)["highway"]["maxspeed:backward"];
  node(around:900,LAT,LON)["traffic_sign"];
  node(around:900,LAT,LON)["highway"="speed_camera"];
);
out tags geom;
\`\`\`

Substitute a validated, bounded GPS coordinate in the request; submit URL-encoded \`data\` via HTTPS GET or an encoded POST to \`/api/interpreter\` in the format supported by the chosen instance. Distinguish empty valid result, timeout/429, and invalid/partial response. Add a unique honest User-Agent; no app identity spoofing.

\`out tags geom\` matters: a road-segment limit needs the actual way geometry for heading-aware map matching. **\`out center\` is not enough** for accurate nearest-road positioning. \`way[maxspeed]\` is road metadata, not an individual photographed sign. Traffic light/STOP/speed camera results are independent hazard categories, not speed-limit signs.

The OSM standard supports \`maxspeed:forward\` / \`maxspeed:backward\`, \`maxspeed:lanes\`, \`maxspeed:conditional\`, and \`traffic_sign:direction\` (see OSM wiki), so a plain \`way[maxspeed]\` plus numeric parse is incomplete. Treat conditional/lanewise or direction-ambiguous values as UNKNOWN, not an unconditional legal speed.

## 4. Lily offline record mapping

Report sample:
\`\`\`json
{"y":8.85465,"g":104.81442,"t":"r420","v":0,"b":-1,"u":265}
\`\`\`
- \`y,g\`: latitude/longitude.
- \`t\`: \`r420\`, \`r421\`, \`limit\`, \`p125\`, \`p130\`, \`p131a\`.
- \`v\`: speed value for \`limit\` (km/h per prior teardown).
- \`b\`: physical sign orientation (often -1/unknown).
- \`u\`: stated application direction (degrees, or missing). **\`convert_lily_vnsigns.py\` correctly uses \`u\` rather than \`b\`.**

The pre-existing private \`signs_vn.bin\` report says 28,551 total with all 15,343 P.127 entries lacking a *known application heading* in the converted file, despite source geometry available. This is **not** evidence the signs have no real-world direction; it means this DB cannot automatically filter them by travel direction today. Source field \`u\` semantics should be cross-checked against actual Lily UI behavior before back-filling any orientation from road geometry.

Types/counts: R.420 = 6,278; R.421 = 6,430; P.127 = 15,343; P.125 = 108; P.130 = 121; P.131a = 271.

Existing report says **349 files = 169 pairs**. This arithmetic needs auditing (169*2=338, difference 11); the raw APK inventory was not available in this review. Do not silently derive full coverage by assuming every grid file has a mate.

The main integration opportunity is **unconverted road polylines** from Lily's paired \`.bin\` and an OSM road provider to match sign coordinate/approach/road class/direction. Never invent the heading for all unknown signs by nearest-road bearing alone in multilane junctions, ramps, parallel roads or roundabouts.

## 5. Existing C2M engine gaps (code-reviewed)

- \`fw/warner/tools/convert_lily_vnsigns.py\` maps only the 6 sign types into the compact C2MSDB01 format; it retains \`u\` but **drops source \`b\`, speed as numeric field, data timestamp, road ID, provenance and road polyline context**; the speed number is encoded in the label. This format is adequate for an initial host replay but weak for multi-source fusion.
- \`fw/warner/warner.c\` intentionally suppresses \`heading=-999\` and thus most P.127 DB signs. Current \`c2m-warner\` remains HOST/REPLAY, no live GPS input/audio/display implementation.
- \`tools/road/osm_preprocess.py\` supports only plain \`maxspeed\`, not \`maxspeed:forward/backward\`, \`maxspeed:lanes\`, or conditional semantics. It provides heading-aware R-tree query in a sample local SQLite DB.
- \`tools/m4/tsr_event_lab.py\` (D3 PR) only describes TSR MessagePack **shapes**; it does not establish the meaning of a speed limit value or trigger a warning.
- Device network: stock \`apsta_switch.sh\` switches AP XOR STA; AP+STA concurrency is unproven. Store offline cache and optionally synchronize over a proven STA or owner-authorized phone relay.

## 6. Proposed normalization contract

\`\`\`text
RoadSignObservation {
  id, source, source_revision, license,
  observed_at, fetched_at, expires_at,
  geometry: {point?, road_polyline?},
  road_id?, road_name?, road_class?,
  type: R420 | R421 | P127 | CAMERA | STOP | OTHER,
  maxspeed_kmh?, direction_of_travel_deg?,
  direction_status: verified | inferred | unknown,
  applicable_lanes?, conditions?,
  confidence?, evidence_ref?
}
\`\`\`

Never merge \`maxspeed\` *road attributes* into \`P127\` physical *sign detections*. Keep separate provenance in any fused \`CurrentSpeedLimit\`. Do not hardcode a numeric speed solely from R.420/R.421: legal defaults can depend on road/vehicle/context.

Provider order for D3:
1. Live C2M native TSR with schema validated (camera observation).
2. Offline authorized sign/road DB (always works without Internet).
3. Cached OSM explicit \`maxspeed\` road metadata (requires road and direction matching).
4. Optional Mapillary API traffic signs (token / coverage / license validated).
5. Future documented Lily API **only with developer permission and a stable published contract**.

## 7. Online operational plan

- Prefer prefetch/cache when Wi-Fi Internet becomes available. **Do not call Overpass per GPS tick** or every 900m when travelling: shared servers may be overloaded. One bounded, sequential query per meaningful new, previously uncached cell or along an upcoming route (initial research), exponential backoff on timeout/429; move to regional OSM extracts for sustained use.
- Cache with \`source, area, fetched_at, ttl, attribution, query_hash\` on SD. Even expired cached results can be advisory-marked as stale instead of silently using them as law.
- Validate JSON \`elements\`: type, way geometry vs node lat/lon, numeric limit units, road direction and conflicting tags; bounded sizes and deadlines.
- A wrong road-direction match must be reported as \`AMBIGUOUS\`, not a speed-limit alert.
- Keep original stock recording/ADAS audio higher priority; avoid claims of shipping device integration before device test.
- OSM data are under ODbL: attribution and derivative DB obligations apply, including when mixing sources. Lily proprietary bundled assets require separate permission/usage-rights check before redistribution.

## 8. Test gates driven by useful product behavior

1. **Offline demo:** R.420/R.421 directional detection replay, no false alerts for opposite direction.
2. **Speed limits:** match real directional \`maxspeed\` way and validate forward/backward; test parallel road, junction, ramps, conditional and lanes.
3. **Mapillary optional:** sample ten covered VN routes via authorized token, quantify signs/age before adding provider.
4. **Cache behavior:** 429/timeout/disconnect yields offline-only output; no repeated requests.
5. **Physical C2M:** prove Wi-Fi Internet path, live GPS data source without double-consuming UART, and one human-visible warning.
6. **Native TSR:** capture actual \`tsr_warning\`/\`tsr_trace_res_list\` runtime and map enum/unit before fusion.

## 9. Source pointers

- \`docs/reverse/APK_LILY_TRAFFIC_SIGN_DATA_V1.md\`
- \`fw/warner/tools/convert_lily_vnsigns.py\`
- \`fw/warner/tools/inspect_signs_bin.py\`
- \`fw/warner/README.md\`
- \`tools/road/osm_preprocess.py\`
- \`docs/firmware_en_vi/06_WIFI_APP_WEB_API.md\`
- https://wiki.openstreetmap.org/wiki/Overpass_API
- https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
- https://wiki.openstreetmap.org/wiki/Key:traffic_sign
- https://wiki.openstreetmap.org/wiki/Key:maxspeed
- https://www.openstreetmap.org/copyright
- https://help.mapillary.com/hc/en-us/articles/115002332165-Map-features

# ProMax BLE capture event script V1 — one reproducible session

PREPARATION ONLY. Execute once with hardware. Total ~10–15 min. Log wall-clock
(phone clock) for EVERY row; photograph the phone clock at T0 for sync.

| Mark | Action | Log (event + screen values + ProMax display + notes) |
|---|---|---|
| T0 | Idle, phone connected to ProMax, no navigation | `idle_connected`; screenshot phone; note ProMax screen |
| T1 | Start navigation to a known destination | `nav_starts`; dest name; first instruction shown |
| T2 | Drive/walk so speed changes ≥3 distinct values | `speed_<v>` per change; speed+limit shown each time |
| T3 | Pass a speed-limit change if route allows (else note skip) | `limit_<v>`; limit shown before/after |
| T4 | Straight segment ≥30 s, steady speed | `straight_hold`; turn+distance shown |
| T5 | Left-turn instruction active | `turn_left`; exact turn text/icon description |
| T6 | Right-turn instruction active | `turn_right`; exact text/icon description |
| T7 | Distance countdown: log 3 declared distances | `dist_<text>` ×3 with timestamps |
| T8 | Route/exit change if possible (else note skip) | `exit_<text>`; road/exit shown |
| T9 | Cancel navigation in app | `nav_cancelled`; phone + ProMax screens after cancel |
| T10 | Remain connected, NO nav, observe ≥3 min (stale window) | `idle_watch`; any display clear/change with timestamp |

Event log format (`04_event_log/event_log.csv`):

```text
iso_time,event,speed,limit,turn,distance,promax_display,notes
2026-..T... ,nav_starts,0,50,straight,1200m,nav screen,free text
```

Rules: one row per observed change (not only the T-marks); empty fields allowed;
never edit rows after the session — append corrections as new rows.
ProMax display state = literal description of what its screen shows, not interpretation.

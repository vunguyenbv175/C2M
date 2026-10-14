#ifndef C2M_D3_WIFI_CONTROL_H
#define C2M_D3_WIFI_CONTROL_H

/* Linux C99, no libnl dependency:
 *   cc -std=c99 -Os -Wall -Wextra wifi_control.c -o c2m-wifi
 * Boot AFTER the stock AP has been brought up on wlan0, not instead of it:
 *   /customer/c2m/bin/c2m-wifi --serve \
 *     --config-dir /customer/c2m-state --run-dir /tmp/c2m-d3
 * Parent boot integration owns installation/launch and any loader environment
 * (LD_LIBRARY_PATH, etc.). This executable never changes nvconf, runs stock
 * sta.sh/ap.sh/apsta_switch, unloads modules, kills unrelated processes, or
 * brings wlan0 down. Build against the target's old glibc without time64.
 *
 * --probe checks nl80211 capability/AP state and writes status; exit 0 means
 * capability was proven, NOT that STA connected. A transient startup failure
 * is published as unknown and --serve retries read-only observation at least
 * 2s apart, at most 30 total attempts. Saved wifi.conf, any connect request,
 * runtime ownership or an operation/failure state cancel the startup budget
 * permanently; retries never auto-connect.
 * --self-test is pure, rootless and does not open a network socket or inspect
 * hardware.
 * Options: --status-file PATH, --supplicant /absolute/path/wpa_supplicant.
 * Default status: /tmp/c2m_wifi_status (atomic, mode 0600).
 * Config/run directories must be distinct, privately owned mode 0700, with
 * trusted non-symlink ancestors. Serve creates missing leaf directories only.
 * It consumes web.h's version=1/action=connect request and a private wifi.conf
 * containing one hex-SSID/64-hex-PSK WPA-PSK network. Credentials are copied to
 * a private snapshot, never logged. Requests do not invoke a shell.
 *
 * Concurrency is proven within ONE advertised interface combination, with
 * capacity for one AP and one managed interface, total >=2 and channels >=1.
 * Current wlan0 frequency is mandatory, including for one-channel hardware.
 * Missing/malformed capabilities and any existing c2msta0 fail closed and are
 * reported as unknown, never as physical hardware absence. A complete valid
 * combination that lacks AP+managed capacity is the only sta_supported=no
 * result. For association the controller additionally refuses other
 * interfaces on the AP PHY, creates ONLY its own c2msta0, restricts
 * scans/association to the AP's frequency, and continually verifies AP
 * ifindex/PHY/type/frequency unchanged.
 * It starts only a validated absolute wpa_supplicant executable with -B and an
 * exclusive private -P PID path; cleanup checks executable/arguments before
 * signaling that PID and removes only a verified, controller-created VIF.
 * Driver errors/timeouts never trigger a fallback to stock WiFi scripts.
 *
 * This is association-only: dhcp_helper=missing is explicit. WPA COMPLETED
 * on the verified AP frequency yields associated_no_ip, never connected;
 * there is deliberately no DHCP, routing, DNS, or Internet-success claim.
 * A later DHCP implementation must operate ONLY on c2msta0 and verify the
 * lease before changing this status. Existing runtime artifacts after a crash
 * are NOT reclaimed automatically: inspection/manual recovery is required.
 * Status has sta_supported, sta_state, sta_ssid (blank for privacy), sta_ipv4
 * (blank), last_error, bt_presence=unknown and dhcp_helper=missing.
 */
#define C2M_WIFI_CONFIG_DIR "/customer/c2m-state"
#define C2M_WIFI_RUN_DIR "/tmp/c2m-d3"
#define C2M_WIFI_STATUS_FILE "/tmp/c2m_wifi_status"
#define C2M_WIFI_AP "wlan0"
#define C2M_WIFI_STA "c2msta0"

int c2m_wifi_self_test(void);

#endif

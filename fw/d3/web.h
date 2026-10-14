#ifndef C2M_D3_WEB_H
#define C2M_D3_WEB_H

/* Native D3 web service, built with:
 *   cc -std=c99 -Os -Wall -Wextra web.c -o c2m-web
 * Portable parser/crypto self-test (including Windows GCC, no listener):
 *   cc -std=c99 -O2 -Wall -Wextra -Werror -DC2M_WEB_CORE_ONLY web.c -o core
 *   ./core --self-test
 * No Python, shell commands, external crypto library, or WiFi control runs here.
 *
 * Controller contract (all paths overridable by command line):
 *   /customer/c2m-state/wifi.conf: mode 0600, atomic replacement; standard
 *     wpa_supplicant configuration, hex SSID and derived 64-hex WPA2 PSK.
 *     Saving never requests a connection; update_config is deliberately absent.
 *   /tmp/c2m-d3/connect.request: mode 0600, atomically published, contains
 *     "version=1\naction=connect\n". The controller must consume/remove this
 *     request, use wifi.conf from the configured directory, and keep the AP
 *     active. A pending request is never overwritten. No credentials in jobs.
 *   /tmp/c2m_wifi_status: optional regular, non-symlink, service-owned file,
 *     <=8192 bytes. Recognized key=value lines: sta_supported, sta_state,
 *     sta_ssid, sta_ipv4, last_error, bt_presence. Values are sanitized for
 *     display; other keys (including passwords/PSKs) are ignored. Absence means
 *     unknown, NOT successful connectivity or Bluetooth detection.
 * Forget only unlinks wifi.conf; it does not disconnect or delete a pending job.
 * The controller must handle a missing configuration when consuming a job.
 *
 * The service owns only wifi.conf, connect.request and its transient files.
 * Config/run directories must be distinct, privately owned mode-0700 dirs.
 * Existing symlink components are rejected. Untrusted users must not be able
 * to rename an ancestor of either directory (e.g. /customer or /tmp).
 * AP verification uses Linux Wireless Extensions IW_MODE_MASTER on wlan0;
 * unsupported verification fails closed. The controller may need to expose
 * WEXT AP-mode support; there is deliberately no unsafe address-only fallback.
 */

#define C2M_WEB_DEFAULT_PORT 8099
#define C2M_WEB_CONFIG_DIR "/customer/c2m-state"
#define C2M_WEB_RUN_DIR "/tmp/c2m-d3"
#define C2M_WEB_STATUS_FILE "/tmp/c2m_wifi_status"
#define C2M_WEB_MAX_HEADERS 8192
#define C2M_WEB_MAX_BODY 8192
#define C2M_WEB_TIMEOUT_MS 3000

int c2m_web_self_test(void);

#endif

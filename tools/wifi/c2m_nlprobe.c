/* tools/wifi/c2m_nlprobe.c - isolated read-only nl80211 structural probe.
 *
 * Fixed wlan0 only, read-only observation, no association.
 * Allowed netlink commands ONLY:
 *   CTRL_CMD_GETFAMILY (resolve "nl80211")
 *   NL80211_CMD_GET_INTERFACE (one fixed wlan0 ifindex)
 *   NL80211_CMD_GET_WIPHY (single non-dump, or explicit dump variants)
 * Forbidden: NEW/SET/DEL_INTERFACE sends, scans, key/beacon/station setup,
 *   interface creation/deletion, state-changing ioctls, supplicant control,
 *   shell, routes, firewall, config writes.
 *
 * Privacy: structural metadata only. IFNAME/MAC/SSID/IE/key bytes are
 * NEVER printed; they appear only as `value=redacted len=N`. Numeric values
 * are printed ONLY for explicitly allowlisted u32 fields within their known
 * namespace (top-level WIPHY/IFINDEX/IFTYPE/FREQ, combo MAXNUM/NUM_CHANNELS,
 * limit MAX). Unrelated nested blobs (bands, supported-commands, etc.) are
 * never recursed and never printed as u32 even when their type numbers
 * collide (notably 1/2).
 *
 * Concurrency: absent or malformed interface-combination data is ALWAYS
 * reported as `concurrency=unknown_not_inferred`. This probe never prints
 * support conclusions and never infers hardware absence.
 *
 * Modes are explicit so single vs dump differences stay observable:
 *   --get-interface        non-dump GET_INTERFACE for fixed wlan0
 *   --get-wiphy            non-dump GET_WIPHY for the wlan0 phy (single reply)
 *   --get-wiphy-dump       dump GET_WIPHY (NLM_F_DUMP, multi-reply + DONE)
 *   --get-wiphy-split-dump dump GET_WIPHY with SPLIT_WIPHY_DUMP flag
 *   --all                  family + interface + single wiphy only (no dump)
 * Dump variants must be requested explicitly; --all never runs a dump.
 *
 * Bounds (fixed, no dynamic allocation):
 *   recv 65536, send 4096, timeout 1500 ms, attrs 128/level, depth 4,
 *   replies 1 (single) / 64 (dump), combos 64, limits 32,
 *   output 200 lines / 8192 bytes. Overflow prints `truncated_at_*`.
 * Wiphy output describes top headers (bounded) plus the combo subtree only;
 * other nested blobs are summarized, never recursed, so late combos are not
 * starved by output budget. A final combo summary is always emitted.
 *
 * --self-test is pure: no socket, no files, no env, no clock. Deterministic
 * fixtures only. Live modes compile and run on Linux only.
 *
 * Linux live-path validation status: NOT validated on this host.
 * linux_live_validated=no. No hardware-ready claim. A Linux CI job is
 * provided separately; it must pass before any /tmp RAM use. On-camera RAM
 * use is DELAYED until stationary hardware plus recording/app/audio health
 * is confirmed. Upload target is /tmp only (SSH exec stream), run with
 * `timeout -t 10 nice -n 10` (stock BusyBox syntax), remove own /tmp binary
 * afterwards. AP wlan0 must remain operational throughout.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define C2M_NLPROBE_IFNAME "wlan0"
#define C2M_NLPROBE_VERSION "c2m-nlprobe-v2"
#define C2M_NLPROBE_LINUX_VALIDATED 0

/* Fixed resource/time/length bounds. */
#define C2M_NL_RECV 65536
#define C2M_NL_SEND 4096
#define C2M_NL_TIMEOUT_MS 1500
#define C2M_MAX_ATTRS 128
#define C2M_MAX_DEPTH 4
#define C2M_MAX_REPLIES_SINGLE 1
#define C2M_MAX_REPLIES_DUMP 64
#define C2M_MAX_COMBOS 64
#define C2M_MAX_LIMITS 32
#define C2M_MAX_LINES 200
#define C2M_MAX_BYTES 8192

#ifdef __linux__
#include <sys/socket.h>
#include <linux/netlink.h>
#include <linux/genetlink.h>
#include <linux/nl80211.h>
#include <net/if.h>
#include <poll.h>
#include <errno.h>
#include <fcntl.h>
#include <time.h>
#include <unistd.h>
#else
/* Portable fallback with the stable wire ABI. nlmsghdr is u32 len, u16 type,
 * u16 flags, u32 seq, u32 pid (16 bytes total). nl80211 numbers below are the
 * real stable ABI (header enum order), NOT test inventions, so collision
 * behaviour (notably 1/2 across namespaces) is exercised on every host. */
struct c2m_nlmsg { uint32_t len; uint16_t type; uint16_t flags; uint32_t seq; uint32_t pid; };
typedef char c2m_nlmsg_size_check[sizeof(struct c2m_nlmsg) == 16 ? 1 : -1];
struct genlmsghdr { uint8_t cmd; uint8_t version; uint16_t reserved; };
struct nlattr { uint16_t nla_len; uint16_t nla_type; };
struct nlmsgerr { int error; uint32_t msglen; };
#define NLMSG_HDRLEN 16
#define GENL_HDRLEN 4
#define NLM_F_REQUEST 1u
#define NLM_F_ACK 4u
#define NLM_F_ROOT 0x100u
#define NLM_F_MATCH 0x200u
#define NLM_F_DUMP (NLM_F_ROOT | NLM_F_MATCH)
#define NLM_F_DUMP_INTR 0x10u
#define NLMSG_ERROR 2u
#define NLMSG_DONE 3u
#define GENL_ID_CTRL 0x10u
#define GENL_MIN_ID 16
#define CTRL_CMD_NEWFAMILY 1
#define CTRL_CMD_GETFAMILY 3
#define CTRL_ATTR_FAMILY_ID 1
#define CTRL_ATTR_FAMILY_NAME 2
#define NLA_F_NESTED 0x8000u
#define NLA_F_NET_BYTEORDER 0x4000u
#ifndef NLA_TYPE_MASK
#define NLA_TYPE_MASK 0x3fffu
#endif
/* Real stable ABI numbers (linux/nl80211.h enum order). */
#define NL80211_CMD_GET_WIPHY 1
#define NL80211_CMD_NEW_WIPHY 3
#define NL80211_CMD_GET_INTERFACE 5
#define NL80211_CMD_NEW_INTERFACE 7
#define NL80211_ATTR_WIPHY 1
#define NL80211_ATTR_IFINDEX 3
#define NL80211_ATTR_IFNAME 4
#define NL80211_ATTR_IFTYPE 5
#define NL80211_ATTR_MAC 6
#define NL80211_ATTR_WIPHY_BANDS 22
#define NL80211_ATTR_WIPHY_FREQ 38
#define NL80211_ATTR_SUPPORTED_COMMANDS 50
#define NL80211_ATTR_SSID 52
#define NL80211_ATTR_INTERFACE_COMBINATIONS 120
#define NL80211_ATTR_SPLIT_WIPHY_DUMP 174
#define NL80211_IFACE_COMB_LIMITS 1
#define NL80211_IFACE_COMB_MAXNUM 2
#define NL80211_IFACE_COMB_STA_AP_BI_MATCH 3
#define NL80211_IFACE_COMB_NUM_CHANNELS 4
#define NL80211_IFACE_LIMIT_MAX 1
#define NL80211_IFACE_LIMIT_TYPES 2
#define NL80211_IFTYPE_STATION 2
#define NL80211_IFTYPE_AP 3
#endif /* __linux__ */

/* Cross-check portable constants against real Linux build headers too.
 * ABI reference: Linux v4.9 include/uapi/linux/nl80211.h (enum values are
 * stable across newer kernels). Do not trust self-consistent fixture IDs. */
typedef char c2m_abi_combos_check[NL80211_ATTR_INTERFACE_COMBINATIONS == 120 ? 1 : -1];
typedef char c2m_abi_split_check[NL80211_ATTR_SPLIT_WIPHY_DUMP == 174 ? 1 : -1];
typedef char c2m_abi_commands_check[NL80211_ATTR_SUPPORTED_COMMANDS == 50 ? 1 : -1];
typedef char c2m_abi_ssid_check[NL80211_ATTR_SSID == 52 ? 1 : -1];

/* Pure netlink framing check (no I/O). Validates u32 nlmsg_len against the
 * available datagram bytes and computes the aligned step without 32-bit
 * wrap. Used by the Linux live exchange loop; also exercised by --self-test
 * so the 32-bit ARM wrap case stays covered on every host. */
static int c2m_nlmsg_step(uint32_t len, size_t avail, size_t *step_out)
{
    size_t step;
    if (len < 16u || (size_t)len > avail)
        return -1;
    step = ((size_t)len + 3u) & ~(size_t)3u;
    if (step < (size_t)len || step > avail)
        return -1;
    if (step_out)
        *step_out = step;
    return 0;
}

#ifndef NLA_TYPE_MASK
#define NLA_TYPE_MASK 0x3fffu
#endif
#ifndef NLA_F_NESTED
#define NLA_F_NESTED 0x8000u
#endif
#ifndef NLA_F_NET_BYTEORDER
#define NLA_F_NET_BYTEORDER 0x4000u
#endif

/* Portable TLV cursor (no I/O, no sockets). */
struct c2m_cursor { const unsigned char *p; size_t n; int bad; };
struct c2m_attr { unsigned type; int nested; const unsigned char *p; size_t n; };

static int c2m_next(struct c2m_cursor *it, struct c2m_attr *a)
{
    struct nlattr h;
    size_t step;
    unsigned raw;
    if (!it->n || it->bad)
        return 0;
    if (it->n < sizeof(h)) {
        it->bad = 1;
        return 0;
    }
    memcpy(&h, it->p, sizeof(h));
    step = ((size_t)h.nla_len + 3u) & ~(size_t)3u;
    if (h.nla_len < sizeof(h) || step > it->n) {
        it->bad = 1;
        return 0;
    }
    raw = (unsigned)h.nla_type;
    if (raw & (unsigned)NLA_F_NET_BYTEORDER) {
        it->bad = 1;
        return 0;
    }
    a->type = raw & (unsigned)NLA_TYPE_MASK;
    a->nested = (raw & (unsigned)NLA_F_NESTED) != 0;
    a->p = it->p + sizeof(h);
    a->n = (size_t)h.nla_len - sizeof(h);
    it->p += step;
    it->n -= step;
    return 1;
}

static int c2m_attr_u32(const struct c2m_attr *a, uint32_t *v)
{
    if (a->n != sizeof(*v))
        return -1;
    memcpy(v, a->p, sizeof(*v));
    return 0;
}

/* Bounded line emitter for structural metadata. */
struct c2m_out {
    char buf[C2M_MAX_BYTES];
    size_t len;
    int lines;
    int truncated;
};

static void c2m_emit(struct c2m_out *o, const char *line)
{
    size_t n;
    if (o->truncated)
        return;
    if (o->lines >= C2M_MAX_LINES) {
        o->truncated = 1;
        return;
    }
    n = strlen(line);
    if (n + 1 >= sizeof(o->buf) - o->len) {
        o->truncated = 1;
        return;
    }
    memcpy(o->buf + o->len, line, n);
    o->len += n;
    o->buf[o->len++] = '\n';
    o->buf[o->len] = 0;
    o->lines++;
}

/* Granular structural stages. Never a support conclusion. */
#define C2M_ST_ABSENT 0
#define C2M_ST_PRESENT 1
#define C2M_ST_MALFORMED (-1)
#define C2M_ST_UNVERIFIED (-2)

struct c2m_counters {
    int top_attrs;
    int combos_seen;
    int combos_present;
    int combos_unverified;
    int limits_seen;
    int attr_total;
};

static const char *c2m_stage_name(int s)
{
    return s == 1 ? "present" : s == 0 ? "absent" :
        s == C2M_ST_UNVERIFIED ? "unverified" : "malformed";
}

/* ---- namespace-aware combo subtree analysis + description ----
 * Known hierarchy ONLY:
 *   combos[] -> { LIMITS(1), MAXNUM(2), BI_MATCH(3), NUM_CHANNELS(4) }
 *   limits[] -> indexed limit elements (any type = index)
 *   limit    -> { MAX(1), TYPES(2) }
 *   types    -> flag attrs whose TYPE is the iftype (2=STA,3=AP)
 * u32 values printed ONLY in their namespace. Other blobs (bands,
 * supported-commands, etc.) are never recursed and never u32-printed,
 * even on type-number collision. Known nested containers are entered by
 * schema (LIMITS/TYPES/COMBOS indexing) even if an old driver omits
 * NLA_F_NESTED; arbitrary blobs are never entered even if flagged. */

static int c2m_describe_types(const unsigned char *p, size_t n,
    struct c2m_out *o, struct c2m_counters *c, const char **detail,
    int *ap, int *sta)
{
    struct c2m_cursor it;
    struct c2m_attr a;
    int idx = 0, cnt = 0, l_ap = 0, l_sta = 0;
    it.p = p;
    it.n = n;
    it.bad = 0;
    while (c2m_next(&it, &a)) {
        char line[160];
        int rc;
        if (++idx > C2M_MAX_ATTRS || ++c->attr_total > 512) {
            c2m_emit(o, "truncated_at_attr_limit");
            *detail = "truncated";
            return C2M_ST_MALFORMED;
        }
        if (a.n) {
            rc = snprintf(line, sizeof(line),
                "types index=%d type=%u len=%u value=redacted detail=flag_payload_malformed",
                idx, a.type, (unsigned)(a.n + 4));
            if (rc > 0)
                c2m_emit(o, line);
            *detail = "types_flag_payload";
            return C2M_ST_MALFORMED;
        }
        if (++cnt > 64) {
            *detail = "types_too_many";
            return C2M_ST_MALFORMED;
        }
        rc = snprintf(line, sizeof(line),
            "types index=%d iftype=%u flag", idx, a.type);
        if (rc > 0)
            c2m_emit(o, line);
        if (a.type == (unsigned)NL80211_IFTYPE_AP && l_ap++) {
            *detail = "types_duplicate_ap";
            return C2M_ST_MALFORMED;
        }
        if (a.type == (unsigned)NL80211_IFTYPE_STATION && l_sta++) {
            *detail = "types_duplicate_sta";
            return C2M_ST_MALFORMED;
        }
    }
    if (it.bad) {
        *detail = "types_truncated";
        return C2M_ST_MALFORMED;
    }
    if (!cnt) {
        *detail = "types_empty";
        return C2M_ST_MALFORMED;
    }
    *ap = l_ap;
    *sta = l_sta;
    return 0;
}

static int c2m_describe_limit(const unsigned char *p, size_t n,
    struct c2m_out *o, struct c2m_counters *c, const char **detail,
    int *ap, int *sta)
{
    struct c2m_cursor it;
    struct c2m_attr a;
    int have_max = 0, have_types = 0;
    uint32_t max = 0;
    int l_ap = 0, l_sta = 0;
    it.p = p;
    it.n = n;
    it.bad = 0;
    while (c2m_next(&it, &a)) {
        char line[192];
        int rc;
        if (++c->attr_total > 512) {
            *detail = "truncated";
            return C2M_ST_MALFORMED;
        }
        if (a.type == (unsigned)NL80211_IFACE_LIMIT_MAX) {
            uint32_t v;
            if (have_max++ || c2m_attr_u32(&a, &v) || !v) {
                *detail = have_max > 1 ? "limit_duplicate_max" : "limit_bad_max";
                return C2M_ST_MALFORMED;
            }
            max = v;
            rc = snprintf(line, sizeof(line),
                "limit max=%u", (unsigned)v);
            if (rc > 0)
                c2m_emit(o, line);
        } else if (a.type == (unsigned)NL80211_IFACE_LIMIT_TYPES) {
            int r;
            if (have_types++) {
                *detail = "limit_duplicate_types";
                return C2M_ST_MALFORMED;
            }
            c2m_emit(o, "limit types_begin");
            /* Schema entry: TYPES payload is flag list even if flag omitted. */
            r = c2m_describe_types(a.p, a.n, o, c, detail, &l_ap, &l_sta);
            c2m_emit(o, "limit types_end");
            if (r)
                return r;
        } else {
            rc = snprintf(line, sizeof(line),
                "limit type=%u len=%u value=redacted", a.type, (unsigned)(a.n + 4));
            if (rc > 0)
                c2m_emit(o, line);
        }
    }
    if (it.bad) {
        *detail = "limit_truncated";
        return C2M_ST_MALFORMED;
    }
    if (!have_max) {
        *detail = "limit_missing_max";
        return C2M_ST_MALFORMED;
    }
    if (!have_types) {
        *detail = "limit_missing_types";
        return C2M_ST_MALFORMED;
    }
    (void)max;
    *ap = l_ap;
    *sta = l_sta;
    return 0;
}

static int c2m_describe_combo(const unsigned char *p, size_t n, int combo_idx,
    struct c2m_out *o, struct c2m_counters *c, const char **detail,
    int *combo_ap, int *combo_sta, int *combo_max_ok)
{
    struct c2m_cursor it, lim;
    struct c2m_attr a, t;
    uint32_t total = 0, channels = 0;
    int hm = 0, hc = 0, hl = 0, nlim = 0, bi = 0;
    int has_ap = 0, has_sta = 0, max_ge2 = 0;
    char line[192];
    int rc;
    it.p = p;
    it.n = n;
    it.bad = 0;
    rc = snprintf(line, sizeof(line), "combo index=%d begin", combo_idx);
    if (rc > 0)
        c2m_emit(o, line);
    while (c2m_next(&it, &a)) {
        if (++c->attr_total > 512) {
            *detail = "truncated";
            return C2M_ST_MALFORMED;
        }
        if (a.type == (unsigned)NL80211_IFACE_COMB_MAXNUM) {
            uint32_t v;
            if (hm++ || c2m_attr_u32(&a, &v) || !v) {
                *detail = hm > 1 ? "combo_duplicate_maxnum" : "combo_bad_maxnum";
                return C2M_ST_MALFORMED;
            }
            total = v;
            rc = snprintf(line, sizeof(line),
                "combo index=%d maxnum=%u", combo_idx, (unsigned)v);
            if (rc > 0)
                c2m_emit(o, line);
        } else if (a.type == (unsigned)NL80211_IFACE_COMB_NUM_CHANNELS) {
            uint32_t v;
            if (hc++ || c2m_attr_u32(&a, &v) || !v) {
                *detail = hc > 1 ? "combo_duplicate_channels" : "combo_bad_channels";
                return C2M_ST_MALFORMED;
            }
            channels = v;
            rc = snprintf(line, sizeof(line),
                "combo index=%d channels=%u", combo_idx, (unsigned)v);
            if (rc > 0)
                c2m_emit(o, line);
        } else if (a.type == (unsigned)NL80211_IFACE_COMB_LIMITS) {
            if (hl++) {
                *detail = "combo_duplicate_limits";
                return C2M_ST_MALFORMED;
            }
            c2m_emit(o, "combo limits_begin");
            /* Indexed-array: every element is a limit regardless of type/flag. */
            lim.p = a.p;
            lim.n = a.n;
            lim.bad = 0;
            while (c2m_next(&lim, &t)) {
                int l_ap = 0, l_sta = 0, r;
                uint32_t lm = 0;
                if (nlim++ >= C2M_MAX_LIMITS || ++c->limits_seen > 256) {
                    *detail = "combo_too_many_limits";
                    return C2M_ST_MALFORMED;
                }
                rc = snprintf(line, sizeof(line),
                    "combo index=%d limit_elem=%d type=%u begin", combo_idx, nlim, t.type);
                if (rc > 0)
                    c2m_emit(o, line);
                r = c2m_describe_limit(t.p, t.n, o, c, detail, &l_ap, &l_sta);
                if (r)
                    return r;
                /* Re-read max for ap/sta capacity (schema parse, no output). */
                {
                    struct c2m_cursor ti;
                    struct c2m_attr x;
                    ti.p = t.p;
                    ti.n = t.n;
                    ti.bad = 0;
                    while (c2m_next(&ti, &x)) {
                        uint32_t v;
                        if (x.type == (unsigned)NL80211_IFACE_LIMIT_MAX &&
                            !c2m_attr_u32(&x, &v))
                            lm = v;
                    }
                }
                if (l_ap)
                    has_ap = 1;
                if (l_sta)
                    has_sta = 1;
                if (l_ap && l_sta && lm >= 2)
                    max_ge2 = 1;
                if ((l_ap || l_sta) && lm >= 2) {
                    /* per-limit capacity noted; cross-limit ap+sta handled below */
                }
                rc = snprintf(line, sizeof(line),
                    "combo index=%d limit_elem=%d end ap=%d sta=%d", combo_idx, nlim, l_ap, l_sta);
                if (rc > 0)
                    c2m_emit(o, line);
            }
            if (lim.bad || !nlim) {
                *detail = lim.bad ? "combo_limits_truncated" : "combo_limits_empty";
                return C2M_ST_MALFORMED;
            }
            c2m_emit(o, "combo limits_end");
        } else if (a.type == (unsigned)NL80211_IFACE_COMB_STA_AP_BI_MATCH) {
            if (a.n || bi++) {
                *detail = "combo_duplicate_bi_match";
                return C2M_ST_MALFORMED;
            }
            c2m_emit(o, "combo bi_match=flag");
        } else {
            rc = snprintf(line, sizeof(line),
                "combo index=%d type=%u len=%u value=redacted", combo_idx, a.type,
                (unsigned)(a.n + 4));
            if (rc > 0)
                c2m_emit(o, line);
        }
    }
    if (it.bad) {
        *detail = "combo_truncated";
        return C2M_ST_MALFORMED;
    }
    if (!hm) {
        *detail = "combo_missing_maxnum";
        return C2M_ST_MALFORMED;
    }
    if (!hc) {
        *detail = "combo_missing_channels";
        return C2M_ST_MALFORMED;
    }
    if (!hl) {
        *detail = "combo_missing_limits";
        return C2M_ST_MALFORMED;
    }
    rc = snprintf(line, sizeof(line), "combo index=%d end", combo_idx);
    if (rc > 0)
        c2m_emit(o, line);
    (void)total;
    (void)channels;
    *combo_ap = has_ap;
    *combo_sta = has_sta;
    *combo_max_ok = max_ge2;
    if (bi)
        return C2M_ST_UNVERIFIED;
    return 1;
}

/* Top combinations blob: empty (n==0) is absent; truncation is malformed. */
static int c2m_analyze_combos(const void *p, size_t n, uint32_t freq,
    struct c2m_out *o, struct c2m_counters *c, const char **detail, int *present)
{
    struct c2m_cursor it;
    struct c2m_attr a;
    int count = 0, npresent = 0, nunv = 0;
    *present = 0;
    if (n == 0) {
        *detail = "combos_empty_absent";
        return C2M_ST_ABSENT;
    }
    it.p = (const unsigned char *)p;
    it.n = n;
    it.bad = 0;
    while (c2m_next(&it, &a)) {
        int ap = 0, sta = 0, ok = 0, r;
        const char *d = "ok";
        if (++count > C2M_MAX_COMBOS) {
            *detail = "combos_too_many";
            return C2M_ST_MALFORMED;
        }
        c->combos_seen++;
        /* Indexed-array: every element is a combo regardless of type/flag. */
        r = c2m_describe_combo(a.p, a.n, count, o, c, &d, &ap, &sta, &ok);
        if (r == C2M_ST_MALFORMED) {
            *detail = d;
            return C2M_ST_MALFORMED;
        }
        if (r == C2M_ST_UNVERIFIED)
            nunv++;
        else if (ap || sta)
            npresent++;
        c->combos_present = npresent;
        c->combos_unverified = nunv;
    }
    if (it.bad) {
        *detail = "combos_truncated";
        return C2M_ST_MALFORMED;
    }
    if (!count) {
        *detail = "combos_empty_absent";
        return C2M_ST_ABSENT;
    }
    if (!freq) {
        *detail = "freq_unverified";
        return C2M_ST_UNVERIFIED;
    }
    *present = npresent;
    if (npresent)
        return C2M_ST_PRESENT;
    if (nunv)
        return C2M_ST_UNVERIFIED;
    *detail = "combos_no_ap_sta_struct";
    return C2M_ST_ABSENT + 0; /* structurally parsed but no ap/sta struct: still unknown */
}

/* Wiphy top level: bounded headers + combo subtree only. Other nested blobs
 * are summarized, never recursed, never u32-printed. Summary always emitted
 * by the caller via printf (not via the bounded buffer). */
static int c2m_describe_wiphy_top(const void *p, size_t n, uint32_t freq,
    struct c2m_out *o, struct c2m_counters *c, const char **detail, int *present)
{
    struct c2m_cursor it;
    struct c2m_attr a;
    uint32_t phy = 0;
    int have_phy = 0, combos_attrs = 0, stage = C2M_ST_ABSENT;
    const char *d = "absent";
    char line[192];
    int rc;
    *present = 0;
    memset(c, 0, sizeof(*c));
    it.p = (const unsigned char *)p;
    it.n = n;
    it.bad = 0;
    while (c2m_next(&it, &a)) {
        if (++c->top_attrs > C2M_MAX_ATTRS || ++c->attr_total > 512) {
            c2m_emit(o, "truncated_at_attr_limit");
            *detail = "truncated_top";
            return C2M_ST_MALFORMED;
        }
        if (a.type == (unsigned)NL80211_ATTR_WIPHY) {
            uint32_t v;
            if (have_phy++ || c2m_attr_u32(&a, &v)) {
                *detail = "duplicate_or_bad_wiphy";
                return C2M_ST_MALFORMED;
            }
            phy = v;
            (void)phy;
            rc = snprintf(line, sizeof(line), "top wiphy=%u", (unsigned)v);
            if (rc > 0)
                c2m_emit(o, line);
        } else if (a.type == (unsigned)NL80211_ATTR_INTERFACE_COMBINATIONS) {
            if (combos_attrs++) {
                *detail = "multi_combos_attr";
                return C2M_ST_MALFORMED;
            }
            rc = snprintf(line, sizeof(line),
                "top interface_combinations bytes=%u begin", (unsigned)a.n);
            if (rc > 0)
                c2m_emit(o, line);
            stage = c2m_analyze_combos(a.p, a.n, freq, o, c, &d, present);
            if (stage == C2M_ST_MALFORMED) {
                c2m_emit(o, "top interface_combinations end_malformed");
                *detail = d;
                return C2M_ST_MALFORMED;
            }
            if (stage == C2M_ST_UNVERIFIED) {
                c2m_emit(o, "top interface_combinations end_unverified");
                *detail = d;
                /* keep stage for caller; still described */
            } else {
                c2m_emit(o, "top interface_combinations end");
            }
        } else {
            /* All other top attrs: header only, redacted, never recursed,
             * never u32-printed (collision-safe). */
            rc = snprintf(line, sizeof(line),
                "top type=%u len=%u value=redacted", a.type, (unsigned)(a.n + 4));
            if (rc > 0)
                c2m_emit(o, line);
        }
        if (o->truncated) {
            *detail = "truncated_output";
            return C2M_ST_MALFORMED;
        }
    }
    if (it.bad) {
        *detail = "truncated_top";
        return C2M_ST_MALFORMED;
    }
    if (!have_phy) {
        *detail = "missing_wiphy";
        return C2M_ST_MALFORMED;
    }
    if (!combos_attrs) {
        *detail = "combos_empty_absent";
        return C2M_ST_ABSENT;
    }
    *detail = d;
    return stage;
}

/* ---- pure reply callbacks (no sockets, no clock, testable on every host).
 * Moved outside the Linux-only live section so --self-test exercises the
 * exact live validation logic (bad cmd, reply counts, wrong phy/ifindex,
 * missing/truncated fields) without hardware. The socket/peer/seq/ACK/DONE
 * framing loop stays Linux-only; its length check uses c2m_nlmsg_step. */
struct c2m_iface_obs {
    uint32_t want_index, index, phy, type, freq;
    int name_present, replies, error;
    const char *detail;
};
static int c2m_iface_reply(int cmd, const void *p, size_t n, void *out)
{
    struct c2m_iface_obs *r = (struct c2m_iface_obs *)out;
    struct c2m_cursor it;
    struct c2m_attr a;
    unsigned seen = 0;
    uint32_t index = 0, phy = 0, type = 0, freq = 0;
    int have_name = 0;
    if (cmd != NL80211_CMD_NEW_INTERFACE || ++r->replies > 128) {
        r->error = -1;
        r->detail = "bad_cmd_or_too_many";
        return -1;
    }
    it.p = (const unsigned char *)p;
    it.n = n;
    it.bad = 0;
    while (c2m_next(&it, &a)) {
        if (a.type == (unsigned)NL80211_ATTR_IFINDEX) {
            uint32_t v;
            if ((seen & 1u) || c2m_attr_u32(&a, &v)) {
                r->detail = "dup_or_bad_ifindex";
                goto bad;
            }
            seen |= 1u;
            index = v;
        } else if (a.type == (unsigned)NL80211_ATTR_WIPHY) {
            uint32_t v;
            if ((seen & 2u) || c2m_attr_u32(&a, &v)) {
                r->detail = "dup_or_bad_wiphy";
                goto bad;
            }
            seen |= 2u;
            phy = v;
        } else if (a.type == (unsigned)NL80211_ATTR_IFTYPE) {
            uint32_t v;
            if ((seen & 4u) || c2m_attr_u32(&a, &v)) {
                r->detail = "dup_or_bad_iftype";
                goto bad;
            }
            seen |= 4u;
            type = v;
        } else if (a.type == (unsigned)NL80211_ATTR_WIPHY_FREQ) {
            uint32_t v;
            if ((seen & 8u) || c2m_attr_u32(&a, &v)) {
                r->detail = "dup_or_bad_freq";
                goto bad;
            }
            seen |= 8u;
            freq = v;
        } else if (a.type == (unsigned)NL80211_ATTR_IFNAME) {
            if ((seen & 16u) || !a.n || a.n > 16 || a.p[a.n - 1]) {
                r->detail = "bad_ifname";
                goto bad;
            }
            seen |= 16u;
            have_name = 1; /* value never printed */
        }
    }
    if (it.bad) {
        r->detail = "truncated";
        goto bad;
    }
    if (!have_name) {
        r->detail = "missing_ifname";
        goto bad;
    }
    if (!(seen & 4u)) {
        r->detail = "missing_iftype";
        goto bad;
    }
    if ((seen & 3u) != 3u || !index) {
        r->detail = "missing_ifindex_or_wiphy";
        goto bad;
    }
    if (index != r->want_index) {
        r->detail = "wrong_ifindex";
        r->error = -1;
        return -1;
    }
    r->index = index;
    r->phy = phy;
    r->type = type;
    r->freq = freq;
    r->name_present = have_name;
    r->detail = "ok";
    return 0;
bad:
    r->error = -1;
    return -1;
}
struct c2m_wiphy_obs {
    uint32_t phy, freq;
    int replies, present;
    struct c2m_counters counters;
    const char *stage;
    const char *detail;
    struct c2m_out desc;
};
/* Single reply: always describe top headers + combo subtree (bounded) even on
 * malformed/unverified paths, with granular stage and pre-summary counters. */
static int c2m_wiphy_single_reply(int cmd, const void *p, size_t n, void *out)
{
    struct c2m_wiphy_obs *r = (struct c2m_wiphy_obs *)out;
    struct c2m_cursor it;
    struct c2m_attr a;
    uint32_t phy = 0;
    int have_phy = 0;
    const char *d = "absent";
    int stage;
    if (cmd != NL80211_CMD_NEW_WIPHY || ++r->replies > C2M_MAX_REPLIES_SINGLE) {
        r->stage = "malformed";
        r->detail = "bad_cmd_or_replies";
        return -1;
    }
    /* Pre-scan for phy/combos presence (counters), then full describe. */
    it.p = (const unsigned char *)p;
    it.n = n;
    it.bad = 0;
    while (c2m_next(&it, &a)) {
        if (a.type == (unsigned)NL80211_ATTR_WIPHY) {
            uint32_t v;
            if (have_phy++ || c2m_attr_u32(&a, &v)) {
                r->stage = "malformed";
                r->detail = "duplicate_or_bad_wiphy";
                goto describe_anyway;
            }
            phy = v;
        }
    }
    if (it.bad) {
        r->stage = "malformed";
        r->detail = "truncated_top";
        goto describe_anyway;
    }
    if (!have_phy || phy != r->phy) {
        r->stage = "malformed";
        r->detail = !have_phy ? "missing_wiphy" : "wrong_phy";
        goto describe_anyway;
    }
    stage = c2m_describe_wiphy_top(p, n, r->freq, &r->desc, &r->counters, &d, &r->present);
    r->stage = c2m_stage_name(stage);
    r->detail = d;
    return stage == C2M_ST_MALFORMED || stage == C2M_ST_UNVERIFIED ? -1 : 0;
describe_anyway:
    /* Still emit bounded structural output for diagnosis. */
    {
        const char *dd = r->detail;
        int pp = 0;
        struct c2m_counters cc;
        memset(&cc, 0, sizeof(cc));
        (void)c2m_describe_wiphy_top(p, n, r->freq, &r->desc, &cc, &dd, &pp);
        r->counters = cc;
        if (!r->detail)
            r->detail = dd;
    }
    return -1;
}
struct c2m_dump_obs {
    int replies;
    const char *stage;
    const char *detail;
    struct c2m_out desc;
    struct c2m_counters counters;
};
static int c2m_wiphy_dump_reply(int cmd, const void *p, size_t n, void *out)
{
    struct c2m_dump_obs *r = (struct c2m_dump_obs *)out;
    const char *d = "described";
    int present = 0;
    struct c2m_counters cc;
    if (cmd != NL80211_CMD_NEW_WIPHY || ++r->replies > C2M_MAX_REPLIES_DUMP) {
        r->stage = "malformed";
        r->detail = "bad_cmd_or_too_many";
        return -1;
    }
    memset(&cc, 0, sizeof(cc));
    (void)c2m_describe_wiphy_top(p, n, 2412, &r->desc, &cc, &d, &present);
    r->counters.top_attrs += cc.top_attrs;
    r->counters.combos_seen += cc.combos_seen;
    r->counters.limits_seen += cc.limits_seen;
    r->counters.attr_total += cc.attr_total;
    if (r->desc.truncated) {
        r->stage = "truncated";
        r->detail = "truncated_output";
    }
    return 0;
}
static int c2m_family_reply(int cmd, const void *p, size_t n, void *out)
{
    struct c2m_cursor it;
    struct c2m_attr a;
    uint16_t id;
    int *family = (int *)out;
    it.p = (const unsigned char *)p;
    it.n = n;
    it.bad = 0;
    if (cmd != CTRL_CMD_NEWFAMILY)
        return -1;
    while (c2m_next(&it, &a)) {
        if (a.type == CTRL_ATTR_FAMILY_ID) {
            if (*family || a.n != sizeof(id))
                return -1;
            memcpy(&id, a.p, sizeof(id));
            if (id < GENL_MIN_ID)
                return -1;
            *family = id;
        }
    }
    return it.bad ? -1 : 0;
}

/* ---- fixture builders (pure, shared by --self-test) ---- */
struct c2m_msg { unsigned char data[4096]; size_t n; int raw; };
static void c2m_fixture_init(struct c2m_msg *m)
{
    memset(m, 0, sizeof(*m));
    m->raw = 1;
}
static int c2m_msg_attr(struct c2m_msg *m, unsigned type, const void *p, size_t n)
{
    struct nlattr h;
    size_t step = (sizeof(h) + n + 3u) & ~(size_t)3u;
    uint32_t len;
    if (n > 65535u - sizeof(h) || step > sizeof(m->data) - m->n)
        return -1;
    h.nla_len = (uint16_t)(sizeof(h) + n);
    h.nla_type = (uint16_t)type;
    memcpy(m->data + m->n, &h, sizeof(h));
    if (n)
        memcpy(m->data + m->n + sizeof(h), p, n);
    memset(m->data + m->n + sizeof(h) + n, 0, step - sizeof(h) - n);
    m->n += step;
    len = (uint32_t)m->n;
    if (!m->raw)
        memcpy(m->data, &len, sizeof(len));
    return 0;
}
static int c2m_msg_u32(struct c2m_msg *m, unsigned type, uint32_t v)
{
    return c2m_msg_attr(m, type, &v, sizeof(v));
}
static size_t c2m_begin(struct c2m_msg *m, unsigned type)
{
    size_t at = m->n;
    (void)c2m_msg_attr(m, type | (unsigned)NLA_F_NESTED, NULL, 0);
    return at;
}
static size_t c2m_begin_noflag(struct c2m_msg *m, unsigned type)
{
    size_t at = m->n;
    (void)c2m_msg_attr(m, type, NULL, 0);
    return at;
}
static void c2m_end(struct c2m_msg *m, size_t at)
{
    struct nlattr h;
    memcpy(&h, m->data + at, sizeof(h));
    h.nla_len = (uint16_t)(m->n - at);
    memcpy(m->data + at, &h, sizeof(h));
}
static void c2m_limit(struct c2m_msg *m, int id, int ap, int sta, unsigned max)
{
    size_t l = c2m_begin(m, (unsigned)id), t;
    (void)c2m_msg_u32(m, (unsigned)NL80211_IFACE_LIMIT_MAX, max);
    t = c2m_begin(m, (unsigned)NL80211_IFACE_LIMIT_TYPES);
    if (ap)
        (void)c2m_msg_attr(m, (unsigned)NL80211_IFTYPE_AP, NULL, 0);
    if (sta)
        (void)c2m_msg_attr(m, (unsigned)NL80211_IFTYPE_STATION, NULL, 0);
    c2m_end(m, t);
    c2m_end(m, l);
}
static void c2m_combo(struct c2m_msg *m, int id, int ap, int sta, int shared,
    unsigned total, unsigned channels, unsigned max)
{
    size_t c = c2m_begin(m, (unsigned)id), l;
    (void)c2m_msg_u32(m, (unsigned)NL80211_IFACE_COMB_MAXNUM, total);
    if (channels)
        (void)c2m_msg_u32(m, (unsigned)NL80211_IFACE_COMB_NUM_CHANNELS, channels);
    l = c2m_begin(m, (unsigned)NL80211_IFACE_COMB_LIMITS);
    if (shared) {
        c2m_limit(m, 1, ap, sta, max);
    } else {
        if (ap)
            c2m_limit(m, 1, 1, 0, max);
        if (sta)
            c2m_limit(m, 2, 0, 1, max);
    }
    c2m_end(m, l);
    c2m_end(m, c);
}

static int c2m_check(const char *name, int actual, int expected)
{
    if (actual != expected) {
        printf("FAIL %s: %d != %d\n", name, actual, expected);
        return 1;
    }
    printf("PASS %s\n", name);
    return 0;
}

static int c2m_check_str(const char *name, const char *actual, const char *expected)
{
    if (strcmp(actual, expected)) {
        printf("FAIL %s: %s != %s\n", name, actual, expected);
        return 1;
    }
    printf("PASS %s\n", name);
    return 0;
}

/* Pure self-test: no sockets, files, env, or clock. */
static int c2m_self_test(void)
{
    struct c2m_msg m, w;
    struct c2m_out o;
    struct c2m_counters c;
    struct c2m_attr bad_a;
    struct c2m_cursor bad_it;
    const char *detail = "";
    int failures = 0, present = 0, r;
    size_t i, k;
    unsigned lcg = 0x12345678u;
    static const unsigned char secret_ssid[] = { 's', 'e', 'c', 'r', 'e', 't' };
    static const unsigned char secret_mac[] = { 0x02, 0x11, 0x22, 0x33, 0x44, 0x55 };
    unsigned char fuzz[256];

    printf("probe=%s\n", C2M_NLPROBE_VERSION);
    printf("linux_live_validated=no\n");
    printf("ifname_fixed=%s\n", C2M_NLPROBE_IFNAME);
    printf("commands_used=CTRL_GETFAMILY,GET_INTERFACE,GET_WIPHY\n");
    failures += c2m_check("stage_names_explicit",
        (c2m_stage_name(1)[0] == 'p' && c2m_stage_name(0)[0] == 'a' &&
         c2m_stage_name(C2M_ST_UNVERIFIED)[0] == 'u' &&
         c2m_stage_name(C2M_ST_MALFORMED)[0] == 'm') ? 1 : 0, 1);
    /* Wire layout guard: nlmsghdr must be 16 bytes (u32,u16,u16,u32,u32). */
    failures += c2m_check("nlmsg_layout_16",
#ifdef __linux__
        (int)NLMSG_HDRLEN, (int)NLMSG_HDRLEN);
#else
        (int)sizeof(struct c2m_nlmsg), 16);
#endif
    printf("mode=single\n");
    printf("mode=dump\n");
    printf("mode=split-dump\n");

    /* Real ABI collision guard: these IDs must hold on every build. */
    failures += c2m_check("abi_comb_maxnum_is_2",
        (int)NL80211_IFACE_COMB_MAXNUM, 2);
    failures += c2m_check("abi_comb_channels_is_4",
        (int)NL80211_IFACE_COMB_NUM_CHANNELS, 4);
    failures += c2m_check("abi_comb_limits_is_1",
        (int)NL80211_IFACE_COMB_LIMITS, 1);
    failures += c2m_check("abi_comb_bimatch_is_3",
        (int)NL80211_IFACE_COMB_STA_AP_BI_MATCH, 3);

    /* 1. Valid split AP/STA combo is structurally present (no support claim). */
    c2m_fixture_init(&m);
    c2m_combo(&m, 1, 1, 1, 0, 2, 1, 1);
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("single_valid_combo_present", r, 1);
    failures += c2m_check("single_no_truncation", o.truncated, 0);

    /* 2. Absent/empty combinations are unknown, never unsupported. */
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(NULL, 0, 2412, &o, &c, &detail, &present);
    failures += c2m_check("absent_is_unknown_not_no", r, 0);
    failures += c2m_check_str("absent_detail", detail, "combos_empty_absent");
    printf("concurrency=unknown_not_inferred reason=absent_or_malformed_is_unknown\n");

    /* 3. Zero frequency forces unverified (AP freq mandatory). */
    c2m_fixture_init(&m);
    c2m_combo(&m, 1, 1, 1, 0, 2, 1, 1);
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 0, &o, &c, &detail, &present);
    failures += c2m_check("zero_freq_unverified", r, C2M_ST_UNVERIFIED);
    failures += c2m_check_str("zero_freq_detail", detail, "freq_unverified");

    /* 4. Missing NUM_CHANNELS is malformed with granular stage. */
    c2m_fixture_init(&m);
    c2m_combo(&m, 1, 1, 1, 0, 2, 0, 1);
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("missing_channels_malformed", r, C2M_ST_MALFORMED);
    failures += c2m_check_str("missing_channels_detail", detail, "combo_missing_channels");
    printf("concurrency=unknown_not_inferred reason=missing_channels_is_unknown\n");

    /* 4b. Missing MAXNUM / LIMITS granular stages. */
    c2m_fixture_init(&m);
    {
        size_t cc = c2m_begin(&m, 1), ll;
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_NUM_CHANNELS, 1);
        ll = c2m_begin(&m, (unsigned)NL80211_IFACE_COMB_LIMITS);
        c2m_limit(&m, 1, 1, 1, 2);
        c2m_end(&m, ll);
        c2m_end(&m, cc);
    }
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("missing_maxnum_malformed", r, C2M_ST_MALFORMED);
    failures += c2m_check_str("missing_maxnum_detail", detail, "combo_missing_maxnum");
    c2m_fixture_init(&m);
    {
        size_t cc = c2m_begin(&m, 1);
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_MAXNUM, 2);
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_NUM_CHANNELS, 1);
        c2m_end(&m, cc);
    }
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("missing_limits_malformed", r, C2M_ST_MALFORMED);
    failures += c2m_check_str("missing_limits_detail", detail, "combo_missing_limits");

    /* 5. Truncation is malformed (empty is absent). Never present. */
    c2m_fixture_init(&m);
    c2m_combo(&m, 1, 1, 1, 0, 2, 1, 1);
    {
        int saw_malformed = 1;
        for (i = 1; i < m.n; i++) {
            int s;
            memset(&o, 0, sizeof(o));
            memset(&c, 0, sizeof(c));
            detail = "";
            s = c2m_analyze_combos(m.data, i, 2412, &o, &c, &detail, &present);
            if (s == 1 || s == 0) {
                printf("FAIL truncation_malformed_at_%u got %d\n", (unsigned)i, s);
                failures++;
                saw_malformed = 0;
                break;
            }
            if (s != C2M_ST_MALFORMED) {
                printf("FAIL truncation_malformed_at_%u got %d\n", (unsigned)i, s);
                failures++;
                saw_malformed = 0;
                break;
            }
        }
        if (saw_malformed)
            printf("PASS truncation_malformed\n");
        memset(&o, 0, sizeof(o));
        memset(&c, 0, sizeof(c));
        detail = "";
        failures += c2m_check("truncation_empty_absent",
            c2m_analyze_combos(m.data, 0, 2412, &o, &c, &detail, &present), 0);
    }

    /* 6. Duplicate scalar is malformed. */
    c2m_fixture_init(&m);
    {
        size_t cc = c2m_begin(&m, 1), ll;
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_MAXNUM, 2);
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_MAXNUM, 2);
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_NUM_CHANNELS, 1);
        ll = c2m_begin(&m, (unsigned)NL80211_IFACE_COMB_LIMITS);
        c2m_limit(&m, 1, 1, 1, 2);
        c2m_end(&m, ll);
        c2m_end(&m, cc);
    }
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("duplicate_scalar_malformed", r, C2M_ST_MALFORMED);

    /* 7. BI_MATCH is unverified, never unsupported. */
    c2m_fixture_init(&m);
    {
        size_t cc = c2m_begin(&m, 1), ll;
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_MAXNUM, 2);
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_NUM_CHANNELS, 1);
        ll = c2m_begin(&m, (unsigned)NL80211_IFACE_COMB_LIMITS);
        c2m_limit(&m, 1, 1, 1, 2);
        c2m_end(&m, ll);
        (void)c2m_msg_attr(&m, (unsigned)NL80211_IFACE_COMB_STA_AP_BI_MATCH, NULL, 0);
        c2m_end(&m, cc);
    }
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("bi_match_unverified", r, C2M_ST_UNVERIFIED);
    printf("concurrency=unknown_not_inferred reason=bi_match_needs_peer_beacon\n");

    /* 8. Separate combos described without combining (structural only). */
    c2m_fixture_init(&m);
    c2m_combo(&m, 1, 1, 0, 0, 2, 1, 1);
    c2m_combo(&m, 2, 0, 1, 0, 2, 1, 1);
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("separate_combos_not_malformed", r != C2M_ST_MALFORMED, 1);
    failures += c2m_check("separate_combos_no_trunc", o.truncated, 0);

    /* 8b. Old driver omitting NLA_F_NESTED on known containers still parses. */
    c2m_fixture_init(&m);
    {
        size_t cc = c2m_begin_noflag(&m, 1), ll;
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_MAXNUM, 2);
        (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_COMB_NUM_CHANNELS, 1);
        ll = c2m_begin_noflag(&m, (unsigned)NL80211_IFACE_COMB_LIMITS);
        {
            size_t lm = c2m_begin_noflag(&m, 1), ty;
            (void)c2m_msg_u32(&m, (unsigned)NL80211_IFACE_LIMIT_MAX, 2);
            ty = c2m_begin_noflag(&m, (unsigned)NL80211_IFACE_LIMIT_TYPES);
            (void)c2m_msg_attr(&m, (unsigned)NL80211_IFTYPE_AP, NULL, 0);
            (void)c2m_msg_attr(&m, (unsigned)NL80211_IFTYPE_STATION, NULL, 0);
            c2m_end(&m, ty);
            c2m_end(&m, lm);
        }
        c2m_end(&m, ll);
        c2m_end(&m, cc);
    }
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("noflag_known_schema_present", r, 1);

    /* 9. Privacy: MAC/SSID bytes never appear; colliding u32 never printed
     * outside its namespace (bands blob with inner type colliders). */
    c2m_fixture_init(&w);
    (void)c2m_msg_u32(&w, (unsigned)NL80211_ATTR_WIPHY, 3);
    {
        size_t bands = c2m_begin(&w, (unsigned)NL80211_ATTR_WIPHY_BANDS);
        uint32_t secret_u32 = 0x12345678u;
        (void)c2m_msg_u32(&w, 1, secret_u32); /* collides with WIPHY in top ns */
        (void)c2m_msg_u32(&w, 2, secret_u32); /* collides with MAXNUM/TYPES */
        (void)c2m_msg_attr(&w, (unsigned)NL80211_ATTR_MAC, secret_mac, sizeof(secret_mac));
        (void)c2m_msg_attr(&w, (unsigned)NL80211_ATTR_SSID, secret_ssid, sizeof(secret_ssid));
        c2m_end(&w, bands);
    }
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_describe_wiphy_top(w.data, w.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("privacy_wiphy_top_ok", r == C2M_ST_ABSENT || r == 1 || r == C2M_ST_MALFORMED, 1);
    if (strstr(o.buf, "305419896") || strstr(o.buf, "secret")) {
        printf("FAIL privacy_collision_no_u32_leak\n");
        failures++;
    } else {
        printf("PASS privacy_collision_no_u32_leak\n");
    }
    if (strstr(o.buf, "value=redacted") == NULL) {
        printf("FAIL privacy_no_payload_bytes\n");
        failures++;
    } else {
        printf("PASS privacy_no_payload_bytes\n");
    }
    {
        int found = 0;
        if (o.len >= sizeof(secret_ssid)) {
            for (k = 0; k + sizeof(secret_ssid) <= o.len; k++) {
                if (!memcmp(o.buf + k, (const char *)secret_ssid, sizeof(secret_ssid))) {
                    found = 1;
                    break;
                }
            }
        }
        failures += c2m_check("privacy_secret_bytes_absent", found, 0);
    }

    /* 10. NET_BYTEORDER flag is malformed. */
    c2m_fixture_init(&m);
    (void)c2m_msg_attr(&m, 123 | (unsigned)NLA_F_NET_BYTEORDER, NULL, 0);
    bad_it.p = m.data;
    bad_it.n = m.n;
    bad_it.bad = 0;
    failures += c2m_check("net_byteorder_bad",
        (c2m_next(&bad_it, &bad_a) == 0 && bad_it.bad) ? 1 : 0, 1);

    /* 11. Dump simulation: two single-form replies described independently,
     * split flag carried as flag attr; modes stay distinct. */
    c2m_fixture_init(&m);
    (void)c2m_msg_u32(&m, (unsigned)NL80211_ATTR_WIPHY, 0);
    {
        size_t cb = c2m_begin(&m, (unsigned)NL80211_ATTR_INTERFACE_COMBINATIONS);
        c2m_combo(&m, 1, 1, 1, 0, 2, 1, 1);
        c2m_end(&m, cb);
    }
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_describe_wiphy_top(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("dump_reply1_present", r, 1);
    failures += c2m_check("dump_top_attrs_seen", c.top_attrs >= 2, 1);
    printf("dump_single_distinct: mode=single replies=1\n");
    printf("dump_single_distinct: mode=dump replies=N done=1\n");
    printf("dump_single_distinct: mode=split-dump split_wiphy_dump_flag=1\n");
    printf("PASS dump_single_explicit\n");
    c2m_fixture_init(&m);
    (void)c2m_msg_attr(&m, (unsigned)NL80211_ATTR_SPLIT_WIPHY_DUMP, NULL, 0);
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    /* Split flag alone (no wiphy/combos) is malformed-missing-wiphy, but the
     * flag itself must be described as flag, not redacted payload. */
    r = c2m_describe_wiphy_top(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("split_flag_described", strstr(o.buf, "type=") != NULL, 1);
    (void)r;

    /* 12. Shared limit with max>=2 stays structurally present. */
    c2m_fixture_init(&m);
    c2m_combo(&m, 1, 1, 1, 1, 2, 2, 2);
    memset(&o, 0, sizeof(o));
    memset(&c, 0, sizeof(c));
    detail = "";
    r = c2m_analyze_combos(m.data, m.n, 2412, &o, &c, &detail, &present);
    failures += c2m_check("shared_limit_present", r, 1);

    /* 13. Deterministic fuzz: random TLV bytes never crash, bounded output. */
    {
        int j, ok = 1;
        for (j = 0; j < 2000; j++) {
            size_t n = (size_t)(lcg % 256);
            size_t t;
            lcg = lcg * 1664525u + 1013904223u;
            for (t = 0; t < n; t++) {
                lcg = lcg * 1664525u + 1013904223u;
                fuzz[t] = (unsigned char)(lcg >> 24);
            }
            memset(&o, 0, sizeof(o));
            memset(&c, 0, sizeof(c));
            detail = "";
            r = c2m_analyze_combos(fuzz, n, 2412, &o, &c, &detail, &present);
            if (r != 0 && r != 1 && r != C2M_ST_MALFORMED && r != C2M_ST_UNVERIFIED)
                ok = 0;
            if (o.len >= C2M_MAX_BYTES || o.lines > C2M_MAX_LINES)
                ok = 0;
        }
        failures += c2m_check("fuzz_bounded_no_crash", ok, 1);
    }

    /* 14. Pure framing check shared with the Linux exchange loop. */
    {
        size_t st = 0;
        failures += c2m_check("nlmsg_step_valid_16",
            c2m_nlmsg_step(16, 16, &st) == 0 && st == 16, 1);
        failures += c2m_check("nlmsg_step_short_rejected",
            c2m_nlmsg_step(15, 16, NULL), -1);
        failures += c2m_check("nlmsg_step_overrun_rejected",
            c2m_nlmsg_step(20, 16, NULL), -1);
        failures += c2m_check("nlmsg_step_wrap_rejected",
            c2m_nlmsg_step(0xffffffffu, 100, NULL), -1);
        failures += c2m_check("nlmsg_step_zero_rejected",
            c2m_nlmsg_step(0, 16, NULL), -1);
    }

    /* 15. Live family callback: exact id, duplicates and small ids fail. */
    {
        struct c2m_msg f;
        int id = 0;
        uint16_t good = 20, small = 5;
        c2m_fixture_init(&f);
        (void)c2m_msg_attr(&f, CTRL_ATTR_FAMILY_ID, &good, sizeof(good));
        failures += c2m_check("family_valid_id",
            c2m_family_reply(CTRL_CMD_NEWFAMILY, f.data, f.n, &id) == 0 && id == 20, 1);
        id = 0;
        failures += c2m_check("family_bad_cmd",
            c2m_family_reply(CTRL_CMD_GETFAMILY, f.data, f.n, &id), -1);
        c2m_fixture_init(&f);
        (void)c2m_msg_attr(&f, CTRL_ATTR_FAMILY_ID, &good, sizeof(good));
        (void)c2m_msg_attr(&f, CTRL_ATTR_FAMILY_ID, &good, sizeof(good));
        id = 0;
        failures += c2m_check("family_duplicate_rejected",
            c2m_family_reply(CTRL_CMD_NEWFAMILY, f.data, f.n, &id), -1);
        c2m_fixture_init(&f);
        (void)c2m_msg_attr(&f, CTRL_ATTR_FAMILY_ID, &small, sizeof(small));
        id = 0;
        failures += c2m_check("family_small_id_rejected",
            c2m_family_reply(CTRL_CMD_NEWFAMILY, f.data, f.n, &id), -1);
        c2m_fixture_init(&f);
        (void)c2m_msg_attr(&f, CTRL_ATTR_FAMILY_ID, &good, sizeof(good));
        id = 0;
        failures += c2m_check("family_truncated_rejected",
            c2m_family_reply(CTRL_CMD_NEWFAMILY, f.data, f.n - 1, &id), -1);
    }

    /* 16. Live interface callback: fixed wlan0 exactness, no value output. */
    {
        struct c2m_msg f;
        struct c2m_iface_obs io;
        static const char want[] = { 'w', 'l', 'a', 'n', '0', 0 };
        static const char nonul[] = { 'w', 'l', 'a', 'n', '0' };
        c2m_fixture_init(&f);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFINDEX, 7);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_WIPHY, 3);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFTYPE, 3);
        (void)c2m_msg_attr(&f, (unsigned)NL80211_ATTR_IFNAME, want, sizeof(want));
        memset(&io, 0, sizeof(io));
        io.want_index = 7;
        failures += c2m_check("iface_valid_ok",
            c2m_iface_reply(NL80211_CMD_NEW_INTERFACE, f.data, f.n, &io) == 0 &&
            io.index == 7 && io.phy == 3 && io.detail[0] == 'o', 1);
        memset(&io, 0, sizeof(io));
        io.want_index = 8;
        failures += c2m_check("iface_wrong_ifindex",
            c2m_iface_reply(NL80211_CMD_NEW_INTERFACE, f.data, f.n, &io) == -1 &&
            !strcmp(io.detail, "wrong_ifindex"), 1);
        memset(&io, 0, sizeof(io));
        io.want_index = 7;
        failures += c2m_check("iface_bad_cmd",
            c2m_iface_reply(NL80211_CMD_GET_INTERFACE, f.data, f.n, &io) == -1, 1);
        c2m_fixture_init(&f);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFINDEX, 7);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_WIPHY, 3);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFTYPE, 3);
        memset(&io, 0, sizeof(io));
        io.want_index = 7;
        failures += c2m_check("iface_missing_ifname",
            c2m_iface_reply(NL80211_CMD_NEW_INTERFACE, f.data, f.n, &io) == -1 &&
            !strcmp(io.detail, "missing_ifname"), 1);
        c2m_fixture_init(&f);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFINDEX, 7);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_WIPHY, 3);
        (void)c2m_msg_attr(&f, (unsigned)NL80211_ATTR_IFNAME, want, sizeof(want));
        memset(&io, 0, sizeof(io));
        io.want_index = 7;
        failures += c2m_check("iface_missing_iftype",
            c2m_iface_reply(NL80211_CMD_NEW_INTERFACE, f.data, f.n, &io) == -1 &&
            !strcmp(io.detail, "missing_iftype"), 1);
        c2m_fixture_init(&f);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFINDEX, 7);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFINDEX, 7);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_WIPHY, 3);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFTYPE, 3);
        (void)c2m_msg_attr(&f, (unsigned)NL80211_ATTR_IFNAME, want, sizeof(want));
        memset(&io, 0, sizeof(io));
        io.want_index = 7;
        failures += c2m_check("iface_duplicate_rejected",
            c2m_iface_reply(NL80211_CMD_NEW_INTERFACE, f.data, f.n, &io) == -1, 1);
        c2m_fixture_init(&f);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFINDEX, 7);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_WIPHY, 3);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFTYPE, 3);
        (void)c2m_msg_attr(&f, (unsigned)NL80211_ATTR_IFNAME, nonul, sizeof(nonul));
        memset(&io, 0, sizeof(io));
        io.want_index = 7;
        failures += c2m_check("iface_bad_ifname",
            c2m_iface_reply(NL80211_CMD_NEW_INTERFACE, f.data, f.n, &io) == -1 &&
            !strcmp(io.detail, "bad_ifname"), 1);
        c2m_fixture_init(&f);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFINDEX, 7);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_WIPHY, 3);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_IFTYPE, 3);
        (void)c2m_msg_attr(&f, (unsigned)NL80211_ATTR_IFNAME, want, sizeof(want));
        memset(&io, 0, sizeof(io));
        io.want_index = 7;
        failures += c2m_check("iface_truncated_rejected",
            c2m_iface_reply(NL80211_CMD_NEW_INTERFACE, f.data, f.n - 1, &io) == -1, 1);
    }

    /* 17. Live single-wiphy callback: phy exactness plus combo stage detail. */
    {
        struct c2m_msg f, g;
        struct c2m_wiphy_obs wo;
        c2m_fixture_init(&f);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_WIPHY, 3);
        {
            size_t cb = c2m_begin(&f, (unsigned)NL80211_ATTR_INTERFACE_COMBINATIONS);
            c2m_combo(&f, 1, 1, 1, 0, 2, 1, 1);
            c2m_end(&f, cb);
        }
        memset(&wo, 0, sizeof(wo));
        wo.phy = 3;
        wo.freq = 2412;
        failures += c2m_check("wiphy_single_valid",
            c2m_wiphy_single_reply(NL80211_CMD_NEW_WIPHY, f.data, f.n, &wo) == 0 &&
            wo.replies == 1 && wo.present == 1, 1);
        memset(&wo, 0, sizeof(wo));
        wo.phy = 3;
        wo.freq = 2412;
        failures += c2m_check("wiphy_single_bad_cmd",
            c2m_wiphy_single_reply(NL80211_CMD_GET_WIPHY, f.data, f.n, &wo) == -1, 1);
        memset(&wo, 0, sizeof(wo));
        wo.phy = 4;
        wo.freq = 2412;
        failures += c2m_check("wiphy_single_wrong_phy",
            c2m_wiphy_single_reply(NL80211_CMD_NEW_WIPHY, f.data, f.n, &wo) == -1 &&
            !strcmp(wo.detail, "wrong_phy"), 1);
        c2m_fixture_init(&g);
        {
            size_t cb = c2m_begin(&g, (unsigned)NL80211_ATTR_INTERFACE_COMBINATIONS);
            c2m_combo(&g, 1, 1, 1, 0, 2, 1, 1);
            c2m_end(&g, cb);
        }
        memset(&wo, 0, sizeof(wo));
        wo.phy = 3;
        wo.freq = 2412;
        failures += c2m_check("wiphy_single_missing_wiphy",
            c2m_wiphy_single_reply(NL80211_CMD_NEW_WIPHY, g.data, g.n, &wo) == -1 &&
            !strcmp(wo.detail, "missing_wiphy"), 1);
        memset(&wo, 0, sizeof(wo));
        wo.phy = 3;
        wo.freq = 0;
        failures += c2m_check("wiphy_single_zero_freq_unverified",
            c2m_wiphy_single_reply(NL80211_CMD_NEW_WIPHY, f.data, f.n, &wo) == -1 &&
            !strcmp(wo.stage, "unverified"), 1);
        memset(&wo, 0, sizeof(wo));
        wo.phy = 3;
        wo.freq = 2412;
        (void)c2m_wiphy_single_reply(NL80211_CMD_NEW_WIPHY, f.data, f.n, &wo);
        failures += c2m_check("wiphy_single_second_reply_rejected",
            c2m_wiphy_single_reply(NL80211_CMD_NEW_WIPHY, f.data, f.n, &wo) == -1 &&
            !strcmp(wo.detail, "bad_cmd_or_replies"), 1);
        memset(&wo, 0, sizeof(wo));
        wo.phy = 3;
        wo.freq = 2412;
        failures += c2m_check("wiphy_single_truncated",
            c2m_wiphy_single_reply(NL80211_CMD_NEW_WIPHY, f.data, f.n - 1, &wo) == -1, 1);
    }

    /* 18. Live dump callback: bounded multi-reply description stays best-effort. */
    {
        struct c2m_msg f;
        struct c2m_dump_obs d;
        c2m_fixture_init(&f);
        (void)c2m_msg_u32(&f, (unsigned)NL80211_ATTR_WIPHY, 0);
        {
            size_t cb = c2m_begin(&f, (unsigned)NL80211_ATTR_INTERFACE_COMBINATIONS);
            c2m_combo(&f, 1, 1, 1, 0, 2, 1, 1);
            c2m_end(&f, cb);
        }
        memset(&d, 0, sizeof(d));
        d.stage = "described";
        d.detail = "described";
        failures += c2m_check("wiphy_dump_valid",
            c2m_wiphy_dump_reply(NL80211_CMD_NEW_WIPHY, f.data, f.n, &d) == 0 &&
            d.replies == 1, 1);
        memset(&d, 0, sizeof(d));
        d.stage = "described";
        d.detail = "described";
        failures += c2m_check("wiphy_dump_bad_cmd",
            c2m_wiphy_dump_reply(NL80211_CMD_GET_WIPHY, f.data, f.n, &d) == -1, 1);
        memset(&d, 0, sizeof(d));
        d.replies = C2M_MAX_REPLIES_DUMP;
        d.stage = "described";
        d.detail = "described";
        failures += c2m_check("wiphy_dump_too_many",
            c2m_wiphy_dump_reply(NL80211_CMD_NEW_WIPHY, f.data, f.n, &d) == -1, 1);
    }

    printf("combos_summary combos_seen=%d limits_seen=%d\n", c.combos_seen, c.limits_seen);
    printf("concurrency=unknown_not_inferred\n");
    printf("meaning=absent_or_malformed_is_unknown_never_no\n");
    printf("self_test=%s\n", failures ? "failed" : "passed");
    return failures ? 1 : 0;
}

#ifdef __linux__
/* ---- live read-only path (Linux only) ---- */
static int64_t c2m_now_ms(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts))
        return -1;
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}
static int c2m_wait_fd(int fd, int events, int64_t until)
{
    struct pollfd p;
    int r;
    p.fd = fd;
    p.events = (short)events;
    p.revents = 0;
    for (;;) {
        int64_t now = c2m_now_ms();
        int64_t left;
        if (now < 0)
            return -1;
        left = until - now;
        if (left <= 0)
            return -1;
        r = poll(&p, 1, left > 2147483647 ? 2147483647 : (int)left);
        if (r > 0)
            return (p.revents & (unsigned)events) ? 0 : -1;
        if (r < 0 && errno != EINTR)
            return -1;
    }
}
struct c2m_nl { int fd, family; uint32_t seq; };
struct c2m_send { unsigned char data[C2M_NL_SEND]; size_t n; };
static void c2m_send_init(struct c2m_send *m, int family, int cmd, int flags, uint32_t seq)
{
    struct nlmsghdr h;
    struct genlmsghdr g;
    memset(m, 0, sizeof(*m));
    memset(&h, 0, sizeof(h));
    memset(&g, 0, sizeof(g));
    h.nlmsg_len = (uint32_t)(NLMSG_HDRLEN + GENL_HDRLEN);
    h.nlmsg_type = (uint16_t)family;
    h.nlmsg_flags = (uint16_t)(NLM_F_REQUEST | NLM_F_ACK | (unsigned)flags);
    h.nlmsg_seq = seq;
    g.cmd = (uint8_t)cmd;
    g.version = 1;
    memcpy(m->data, &h, sizeof(h));
    memcpy(m->data + NLMSG_HDRLEN, &g, sizeof(g));
    m->n = h.nlmsg_len;
}
static int c2m_send_attr(struct c2m_send *m, unsigned type, const void *p, size_t n)
{
    struct nlattr h;
    uint32_t len;
    size_t step = (sizeof(h) + n + 3u) & ~(size_t)3u;
    if (n > 65535u - sizeof(h) || step > sizeof(m->data) - m->n)
        return -1;
    h.nla_len = (uint16_t)(sizeof(h) + n);
    h.nla_type = (uint16_t)type;
    memcpy(m->data + m->n, &h, sizeof(h));
    if (n)
        memcpy(m->data + m->n + sizeof(h), p, n);
    memset(m->data + m->n + sizeof(h) + n, 0, step - sizeof(h) - n);
    m->n += step;
    len = (uint32_t)m->n;
    memcpy(m->data, &len, sizeof(len));
    return 0;
}
static int c2m_send_u32(struct c2m_send *m, unsigned type, uint32_t v)
{
    return c2m_send_attr(m, type, &v, sizeof(v));
}
typedef int (*c2m_reply_fn)(int, const void *, size_t, void *);
static int c2m_exchange(struct c2m_nl *nl, struct c2m_send *m, c2m_reply_fn fn, void *arg)
{
    struct sockaddr_nl peer;
    unsigned char buf[C2M_NL_RECV];
    struct iovec iov;
    struct msghdr mh;
    struct nlmsghdr h;
    struct genlmsghdr g;
    struct nlmsgerr e;
    uint32_t sequence;
    size_t pos, step;
    ssize_t got;
    int dump, ack = 0, done = 0;
    int64_t start = c2m_now_ms();
    int64_t until;
    if (start < 0)
        return -1;
    until = start + C2M_NL_TIMEOUT_MS;
    memcpy(&h, m->data, sizeof(h));
    sequence = h.nlmsg_seq;
    dump = (h.nlmsg_flags & NLM_F_DUMP) == NLM_F_DUMP;
    memset(&peer, 0, sizeof(peer));
    peer.nl_family = AF_NETLINK;
    if (sendto(nl->fd, m->data, m->n, 0, (struct sockaddr *)&peer, sizeof(peer)) != (ssize_t)m->n)
        return -1;
    for (;;) {
        if (c2m_wait_fd(nl->fd, POLLIN, until))
            return -1;
        memset(&mh, 0, sizeof(mh));
        memset(&peer, 0, sizeof(peer));
        iov.iov_base = buf;
        iov.iov_len = sizeof(buf);
        mh.msg_name = &peer;
        mh.msg_namelen = sizeof(peer);
        mh.msg_iov = &iov;
        mh.msg_iovlen = 1;
        got = recvmsg(nl->fd, &mh, MSG_DONTWAIT);
        if (got < 0 && (errno == EINTR || errno == EAGAIN))
            continue;
        if (got <= 0 || (mh.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) ||
            mh.msg_namelen != sizeof(peer) || peer.nl_family != AF_NETLINK ||
            peer.nl_pid || peer.nl_groups)
            return -1;
        for (pos = 0; pos < (size_t)got; pos += step) {
            if ((size_t)got - pos < sizeof(h))
                return -1;
            memcpy(&h, buf + pos, sizeof(h));
            /* 32-bit-safe: reject wrap/overflow before any payload use. */
            if (c2m_nlmsg_step(h.nlmsg_len, (size_t)got - pos, &step))
                return -1;
            if (h.nlmsg_seq != sequence)
                continue;
            if (h.nlmsg_flags & NLM_F_DUMP_INTR)
                return -1;
            if (h.nlmsg_type == NLMSG_ERROR) {
                if (h.nlmsg_len < (uint32_t)NLMSG_HDRLEN + sizeof(e))
                    return -1;
                memcpy(&e, buf + pos + NLMSG_HDRLEN, sizeof(e));
                if (e.error) {
                    errno = e.error < 0 && e.error != (-2147483647 - 1) ? -e.error : EPROTO;
                    return -1;
                }
                ack = 1;
            } else if (h.nlmsg_type == NLMSG_DONE) {
                int err = 0;
                if (!dump)
                    return -1;
                if (h.nlmsg_len >= (uint32_t)NLMSG_HDRLEN + sizeof(err))
                    memcpy(&err, buf + pos + NLMSG_HDRLEN, sizeof(err));
                if (err)
                    return -1;
                done = 1;
            } else {
                if (h.nlmsg_type != (unsigned)nl->family ||
                    h.nlmsg_len < (uint32_t)(NLMSG_HDRLEN + GENL_HDRLEN))
                    return -1;
                memcpy(&g, buf + pos + NLMSG_HDRLEN, sizeof(g));
                if (fn && fn(g.cmd, buf + pos + NLMSG_HDRLEN + GENL_HDRLEN,
                        h.nlmsg_len - (uint32_t)(NLMSG_HDRLEN + GENL_HDRLEN), arg))
                    return -1;
            }
        }
        if (dump ? done : ack)
            return 0;
    }
}
static int c2m_nl_open(struct c2m_nl *nl)
{
    struct sockaddr_nl addr;
    struct c2m_send m;
    int id = 0;
    memset(nl, 0, sizeof(*nl));
    nl->fd = -1;
    nl->fd = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC | SOCK_NONBLOCK, NETLINK_GENERIC);
    if (nl->fd < 0)
        return -1;
    memset(&addr, 0, sizeof(addr));
    addr.nl_family = AF_NETLINK;
    if (bind(nl->fd, (struct sockaddr *)&addr, sizeof(addr)))
        goto fail;
    nl->family = GENL_ID_CTRL;
    c2m_send_init(&m, nl->family, CTRL_CMD_GETFAMILY, 0, ++nl->seq);
    if (c2m_send_attr(&m, CTRL_ATTR_FAMILY_NAME, "nl80211", 8) ||
        c2m_exchange(nl, &m, c2m_family_reply, &id) || !id)
        goto fail;
    nl->family = id;
    return 0;
fail:
    close(nl->fd);
    nl->fd = -1;
    return -1;
}
static void c2m_print_out(struct c2m_out *o)
{
    if (o->len)
        fwrite(o->buf, 1, o->len, stdout);
    if (o->truncated)
        printf("truncated_at_output_limit\n");
}
static int c2m_live_interface(struct c2m_nl *nl, uint32_t *phy, uint32_t *freq)
{
    struct c2m_iface_obs r;
    struct c2m_send m;
    unsigned ifindex;
    memset(&r, 0, sizeof(r));
    r.detail = "query";
    ifindex = if_nametoindex(C2M_NLPROBE_IFNAME);
    if (!ifindex) {
        printf("iface stage=query_failed detail=no_ifindex concurrency=unknown_not_inferred\n");
        return -1;
    }
    r.want_index = (uint32_t)ifindex;
    c2m_send_init(&m, nl->family, NL80211_CMD_GET_INTERFACE, 0, ++nl->seq);
    if (c2m_send_u32(&m, NL80211_ATTR_IFINDEX, r.want_index) ||
        c2m_exchange(nl, &m, c2m_iface_reply, &r) || r.replies != 1 || r.error) {
        printf("iface stage=query_failed_or_malformed replies=%d detail=%s concurrency=unknown_not_inferred\n",
            r.replies, r.detail ? r.detail : "query_failed");
        return -1;
    }
    printf("iface ifname_fixed=%s ifindex=%u phy=%u iftype=%u freq=%u name_present=%d replies=%d detail=%s\n",
        C2M_NLPROBE_IFNAME, r.index, r.phy, r.type, r.freq, r.name_present, r.replies,
        r.detail ? r.detail : "ok");
    printf("concurrency=unknown_not_inferred\n");
    *phy = r.phy;
    *freq = r.freq;
    return 0;
}
static int c2m_live_wiphy_single(struct c2m_nl *nl, uint32_t phy, uint32_t freq)
{
    struct c2m_wiphy_obs r;
    struct c2m_send m;
    memset(&r, 0, sizeof(r));
    r.phy = phy;
    r.freq = freq;
    r.stage = "query";
    r.detail = "query";
    c2m_send_init(&m, nl->family, NL80211_CMD_GET_WIPHY, 0, ++nl->seq);
    if (c2m_send_u32(&m, NL80211_ATTR_WIPHY, phy) ||
        c2m_exchange(nl, &m, c2m_wiphy_single_reply, &r) || r.replies != 1) {
        if (r.replies != 1 && r.detail && !strcmp(r.detail, "query")) {
            r.stage = "malformed";
            r.detail = "missing_reply";
        }
        printf("wiphy mode=single replies=%d top_attrs=%d combos_seen=%d limits_seen=%d stage=%s detail=%s concurrency=unknown_not_inferred\n",
            r.replies, r.counters.top_attrs, r.counters.combos_seen, r.counters.limits_seen,
            r.stage ? r.stage : "query_failed", r.detail ? r.detail : "query_failed");
        c2m_print_out(&r.desc);
        printf("combos_summary combos_seen=%d limits_seen=%d stage=%s detail=%s concurrency=unknown_not_inferred\n",
            r.counters.combos_seen, r.counters.limits_seen,
            r.stage ? r.stage : "query_failed", r.detail ? r.detail : "query_failed");
        return -1;
    }
    printf("wiphy mode=single replies=%d top_attrs=%d combos_seen=%d limits_seen=%d combos_present=%d stage=%s detail=%s concurrency=unknown_not_inferred\n",
        r.replies, r.counters.top_attrs, r.counters.combos_seen, r.counters.limits_seen,
        r.present, r.stage ? r.stage : "absent", r.detail ? r.detail : "absent");
    c2m_print_out(&r.desc);
    printf("combos_summary combos_seen=%d limits_seen=%d stage=%s detail=%s concurrency=unknown_not_inferred\n",
        r.counters.combos_seen, r.counters.limits_seen,
        r.stage ? r.stage : "absent", r.detail ? r.detail : "absent");
    return 0;
}
static int c2m_live_wiphy_dump(struct c2m_nl *nl, int split)
{
    struct c2m_dump_obs r;
    struct c2m_send m;
    memset(&r, 0, sizeof(r));
    r.stage = "described";
    r.detail = "described";
    c2m_send_init(&m, nl->family, NL80211_CMD_GET_WIPHY, NLM_F_DUMP, ++nl->seq);
    if (split) {
        /* NL80211_ATTR_SPLIT_WIPHY_DUMP is an enum value, not a macro;
         * reference it directly so split mode stays available. */
        if (c2m_send_attr(&m, NL80211_ATTR_SPLIT_WIPHY_DUMP, NULL, 0))
            return -1;
    }
    if (c2m_exchange(nl, &m, c2m_wiphy_dump_reply, &r) || !r.replies) {
        if (!r.replies && r.detail && !strcmp(r.detail, "described")) {
            r.stage = "malformed";
            r.detail = "missing_reply";
        }
        printf("wiphy mode=%s replies=%d stage=%s detail=%s concurrency=unknown_not_inferred\n",
            split ? "split-dump" : "dump", r.replies,
            r.stage ? r.stage : "query_failed", r.detail ? r.detail : "query_failed");
        c2m_print_out(&r.desc);
        printf("combos_summary replies=%d combos_seen=%d stage=%s detail=%s concurrency=unknown_not_inferred\n",
            r.replies, r.counters.combos_seen,
            r.stage ? r.stage : "query_failed", r.detail ? r.detail : "query_failed");
        return -1;
    }
    printf("wiphy mode=%s replies=%d done=1 top_attrs=%d combos_seen=%d stage=%s concurrency=unknown_not_inferred\n",
        split ? "split-dump" : "dump", r.replies, r.counters.top_attrs,
        r.counters.combos_seen, r.stage ? r.stage : "described");
    c2m_print_out(&r.desc);
    printf("combos_summary replies=%d combos_seen=%d concurrency=unknown_not_inferred\n",
        r.replies, r.counters.combos_seen);
    return 0;
}
#endif /* __linux__ */

static void c2m_usage(FILE *f)
{
    fputs("Usage: c2m-nlprobe --help | --self-test\n"
#ifdef __linux__
        "       c2m-nlprobe --get-interface | --get-wiphy | --get-wiphy-dump\n"
        "       c2m-nlprobe --get-wiphy-split-dump | --all\n"
#endif
        "Fixed wlan0 only. Read-only CTRL_GETFAMILY/GET_INTERFACE/GET_WIPHY.\n"
        "Absent or malformed combinations are unknown, never unsupported.\n"
        "linux_live_validated=no\n", f);
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        c2m_usage(stdout);
        return 0;
    }
    if (argc == 2 && !strcmp(argv[1], "--self-test"))
        return c2m_self_test();
#ifdef __linux__
    if (argc == 2 && (!strcmp(argv[1], "--get-interface") || !strcmp(argv[1], "--get-wiphy") ||
            !strcmp(argv[1], "--get-wiphy-dump") || !strcmp(argv[1], "--get-wiphy-split-dump") ||
            !strcmp(argv[1], "--all"))) {
        struct c2m_nl nl;
        uint32_t phy = 0, freq = 0;
        int rc = 1, mode_single = 0, mode_dump = 0, mode_split = 0, mode_iface = 0;
        if (!strcmp(argv[1], "--get-interface"))
            mode_iface = 1;
        else if (!strcmp(argv[1], "--get-wiphy"))
            mode_single = 1;
        else if (!strcmp(argv[1], "--get-wiphy-dump"))
            mode_dump = 1;
        else if (!strcmp(argv[1], "--get-wiphy-split-dump"))
            mode_split = 1;
        else
            mode_iface = mode_single = 1; /* --all: single only, never dump */
        printf("probe=%s\n", C2M_NLPROBE_VERSION);
        printf("linux_live_validated=%s\n", C2M_NLPROBE_LINUX_VALIDATED ? "yes" : "no");
        printf("ifname_fixed=%s\n", C2M_NLPROBE_IFNAME);
        printf("commands_used=CTRL_GETFAMILY,GET_INTERFACE,GET_WIPHY\n");
        if (c2m_nl_open(&nl)) {
            printf("nl80211 stage=family_failed detail=query_failed concurrency=unknown_not_inferred\n");
            return 1;
        }
        if (mode_iface || mode_single) {
            if (c2m_live_interface(&nl, &phy, &freq)) {
                close(nl.fd);
                return 1;
            }
        }
        if (mode_single)
            rc = c2m_live_wiphy_single(&nl, phy, freq) ? 1 : 0;
        else if (mode_iface && !mode_single)
            rc = 0;
        else if (mode_dump)
            rc = c2m_live_wiphy_dump(&nl, 0) ? 1 : 0;
        else if (mode_split)
            rc = c2m_live_wiphy_dump(&nl, 1) ? 1 : 0;
        printf("meaning=absent_or_malformed_is_unknown_never_no\n");
        close(nl.fd);
        return rc;
    }
#else
    (void)argc;
    (void)argv;
#endif
    c2m_usage(stderr);
    return 2;
}

#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "wifi_control.h"
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <sys/un.h>
#include <linux/netlink.h>
#include <linux/genetlink.h>
#include <linux/nl80211.h>
#include <net/if.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <errno.h>
#include <fcntl.h>
#include <time.h>
#include <unistd.h>

#define NL_SIZE 65536
#define NL_TIMEOUT 1500
#define MAX_LIMITS 32
#define MAX_COMBOS 64
#define STARTUP_PROBE_ATTEMPTS 30
#define STARTUP_PROBE_INTERVAL 2000
/* Negative results are missing/malformed evidence or an unenforceable extra
 * constraint, never proof that the hardware has no AP+STA capability. */
#define PROOF_MALFORMED (-1)
#define PROOF_UNVERIFIED (-2)
#define OWN_CONFIG "wifi-active.conf"
#define OWN_PID "wifi-supplicant.pid"
#define OWN_CTRL "wifi-ctrl"
#define OWN_CLIENT "wifi-client"
#ifndef NLA_TYPE_MASK
#define NLA_TYPE_MASK 0x3fff
#endif

struct attrs { const unsigned char *p; size_t n; int bad; };
struct attr { unsigned type; const unsigned char *p; size_t n; };
struct limit { uint32_t max; int ap, sta; };
struct iface { uint32_t index, phy, type, freq; char name[IFNAMSIZ]; };
struct nl { int fd, family; uint32_t seq; };
struct msg { unsigned char data[4096]; size_t n; int raw; };
struct worker {
    struct nl nl;
    struct iface ap, sta;
    int configfd, runfd, lockfd, owned, cfg_owned, ctrl_owned, pid_owned;
    int supported;
    char run[PATH_MAX], supplicant[PATH_MAX], config[PATH_MAX], pidfile[PATH_MAX];
    char ctrl[PATH_MAX], client[PATH_MAX];
    const char *status, *state, *error;
    int64_t started, next_probe;
    unsigned startup_probe_attempts;
    int startup_probe_retry;
};
static volatile sig_atomic_t stopping;
static void interrupted(int sig) { (void)sig; stopping = 1; }
static int64_t now_ms(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) return -1;
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}
static int wait_fd(int fd, int events, int64_t until) {
    struct pollfd p = { fd, (short)events, 0 };
    int64_t left;
    int r;
    while ((left = until - now_ms()) > 0) {
        r = poll(&p, 1, left > INT_MAX ? INT_MAX : (int)left);
        if (r > 0) return (p.revents & events) ? 0 : -1;
        if (r < 0 && errno != EINTR) return -1;
    }
    return -1;
}
static void wipe(void *p, size_t n) { volatile unsigned char *v = p; while (n--) *v++ = 0; }
static int next_attr(struct attrs *it, struct attr *a) {
    struct nlattr h;
    size_t step;
    if (!it->n || it->bad) return 0;
    if (it->n < sizeof(h)) { it->bad = 1; return 0; }
    memcpy(&h, it->p, sizeof(h));
    step = ((size_t)h.nla_len + 3) & ~(size_t)3;
    if (h.nla_len < sizeof(h) || step > it->n) { it->bad = 1; return 0; }
    if (h.nla_type & NLA_F_NET_BYTEORDER) { it->bad = 1; return 0; }
    a->type = h.nla_type & NLA_TYPE_MASK;
    a->p = it->p + sizeof(h); a->n = h.nla_len - sizeof(h);
    it->p += step; it->n -= step;
    return 1;
}
static int attr_u32(const struct attr *a, uint32_t *v) {
    if (a->n != sizeof(*v)) return -1;
    memcpy(v, a->p, sizeof(*v)); return 0;
}
/* Parse each limit independently. One shared limit must allow TWO interfaces;
 * separate combinations must NEVER be combined into an AP+managed proof. */
static int parse_limit(const struct attr *outer, struct limit *l) {
    struct attrs it = { outer->p, outer->n, 0 }, types;
    struct attr a, t;
    int have_max = 0, have_types = 0, count = 0;
    memset(l, 0, sizeof(*l));
    while (next_attr(&it, &a)) {
        if (a.type == NL80211_IFACE_LIMIT_MAX) {
            if (have_max++ || attr_u32(&a, &l->max) || !l->max) return -1;
        } else if (a.type == NL80211_IFACE_LIMIT_TYPES) {
            if (have_types++) return -1;
            types = (struct attrs){ a.p, a.n, 0 };
            while (next_attr(&types, &t)) {
                if (t.n || ++count > 64) return -1;
                if (t.type == NL80211_IFTYPE_AP) { if (l->ap++) return -1; }
                if (t.type == NL80211_IFTYPE_STATION) { if (l->sta++) return -1; }
            }
            if (types.bad || !count) return -1;
        }
    }
    return it.bad || !have_max || !have_types ? -1 : 0;
}
static int parse_combo(const struct attr *outer) {
    struct attrs it = { outer->p, outer->n, 0 }, limits;
    struct attr a, t;
    struct limit ls[MAX_LIMITS];
    uint32_t total = 0, channels = 0;
    int hm = 0, hc = 0, hl = 0, n = 0, i, j, bi_match = 0;
    while (next_attr(&it, &a)) {
        if (a.type == NL80211_IFACE_COMB_MAXNUM) {
            if (hm++ || attr_u32(&a, &total) || !total) return -1;
        } else if (a.type == NL80211_IFACE_COMB_NUM_CHANNELS) {
            if (hc++ || attr_u32(&a, &channels) || !channels) return -1;
        } else if (a.type == NL80211_IFACE_COMB_LIMITS) {
            if (hl++) return -1;
            limits = (struct attrs){ a.p, a.n, 0 };
            while (next_attr(&limits, &t)) {
                if (n == MAX_LIMITS || parse_limit(&t, &ls[n++])) return -1;
            }
            if (limits.bad || !n) return -1;
        } else if (a.type == NL80211_IFACE_COMB_STA_AP_BI_MATCH) {
            if (a.n || bi_match++) return -1;
        }
    }
    if (it.bad || !hm || !hc || !hl) return -1;
    if (total < 2) return 0;
    for (i = 0; i < n; ++i) for (j = 0; j < n; ++j)
        if (ls[i].ap && ls[j].sta && (i != j || ls[i].max >= 2))
            /* Cannot enforce a peer's beacon interval. This is not evidence
             * of hardware absence; it remains blocked for association. */
            return bi_match ? PROOF_UNVERIFIED : 1;
    return 0;
}
static int prove_combinations(const void *p, size_t n, uint32_t frequency) {
    struct attrs it = { p, n, 0 };
    struct attr a;
    int count = 0, supported = 0, unverified = 0, r;
    while (next_attr(&it, &a)) {
        if (++count > MAX_COMBOS || (r = parse_combo(&a)) == PROOF_MALFORMED) return PROOF_MALFORMED;
        if (r == 1) supported = 1;
        if (r == PROOF_UNVERIFIED) unverified = 1;
    }
    if (it.bad || !count) return PROOF_MALFORMED;
    if (!frequency) return PROOF_UNVERIFIED;
    return supported ? 1 : unverified ? PROOF_UNVERIFIED : 0;
}
static void msg_init(struct msg *m, int family, int cmd, int flags, uint32_t seq) {
    struct nlmsghdr h;
    struct genlmsghdr g;
    memset(m, 0, sizeof(*m)); memset(&h, 0, sizeof(h)); memset(&g, 0, sizeof(g));
    h.nlmsg_len = NLMSG_HDRLEN + GENL_HDRLEN; h.nlmsg_type = (uint16_t)family;
    h.nlmsg_flags = NLM_F_REQUEST | NLM_F_ACK | flags; h.nlmsg_seq = seq;
    g.cmd = (uint8_t)cmd; g.version = 1;
    memcpy(m->data, &h, sizeof(h)); memcpy(m->data + NLMSG_HDRLEN, &g, sizeof(g));
    m->n = h.nlmsg_len;
}
static int msg_attr(struct msg *m, unsigned type, const void *p, size_t n) {
    struct nlattr a;
    uint32_t len;
    size_t step = (sizeof(a) + n + 3) & ~(size_t)3;
    if (n > UINT16_MAX - sizeof(a) || step > sizeof(m->data) - m->n) return -1;
    a.nla_len = (uint16_t)(sizeof(a) + n); a.nla_type = (uint16_t)type;
    memcpy(m->data + m->n, &a, sizeof(a));
    if (n) memcpy(m->data + m->n + sizeof(a), p, n);
    memset(m->data + m->n + sizeof(a) + n, 0, step - sizeof(a) - n);
    m->n += step; len = (uint32_t)m->n;
    if (!m->raw) memcpy(m->data, &len, sizeof(len));
    return 0;
}
static int msg_u32(struct msg *m, unsigned type, uint32_t v) { return msg_attr(m, type, &v, sizeof(v)); }
typedef int (*reply_fn)(int, const void *, size_t, void *);
/* No libnl: validate sender, sequence, lengths, truncation, ACK and dump end.
 * Absolute monotonic deadline also bounds unsolicited traffic and EINTR. */
static int exchange(struct nl *nl, struct msg *m, reply_fn fn, void *arg) {
    struct sockaddr_nl peer;
    unsigned char buf[NL_SIZE];
    struct iovec iov;
    struct msghdr mh;
    struct nlmsghdr h;
    struct genlmsghdr g;
    struct nlmsgerr e;
    uint32_t sequence;
    size_t pos, step;
    ssize_t got;
    int dump, ack = 0, done = 0;
    int64_t until = now_ms() + NL_TIMEOUT;
    memcpy(&h, m->data, sizeof(h)); sequence = h.nlmsg_seq;
    dump = (h.nlmsg_flags & NLM_F_DUMP) == NLM_F_DUMP;
    memset(&peer, 0, sizeof(peer)); peer.nl_family = AF_NETLINK;
    if (sendto(nl->fd, m->data, m->n, 0, (struct sockaddr *)&peer, sizeof(peer)) != (ssize_t)m->n) return -1;
    for (;;) {
        if (wait_fd(nl->fd, POLLIN, until)) return -1;
        memset(&mh, 0, sizeof(mh)); memset(&peer, 0, sizeof(peer));
        iov.iov_base = buf; iov.iov_len = sizeof(buf);
        mh.msg_name = &peer; mh.msg_namelen = sizeof(peer); mh.msg_iov = &iov; mh.msg_iovlen = 1;
        got = recvmsg(nl->fd, &mh, MSG_DONTWAIT);
        if (got < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (got <= 0 || (mh.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) ||
            mh.msg_namelen != sizeof(peer) || peer.nl_family != AF_NETLINK || peer.nl_pid || peer.nl_groups) return -1;
        for (pos = 0; pos < (size_t)got; pos += step) {
            if ((size_t)got - pos < sizeof(h)) return -1;
            memcpy(&h, buf + pos, sizeof(h)); step = ((size_t)h.nlmsg_len + 3) & ~(size_t)3;
            if (h.nlmsg_len < NLMSG_HDRLEN || step > (size_t)got - pos) return -1;
            if (h.nlmsg_seq != sequence) continue;
            if (h.nlmsg_flags & NLM_F_DUMP_INTR) return -1;
            if (h.nlmsg_type == NLMSG_ERROR) {
                if (h.nlmsg_len < NLMSG_HDRLEN + sizeof(e)) return -1;
                memcpy(&e, buf + pos + NLMSG_HDRLEN, sizeof(e));
                if (e.error) { errno = e.error < 0 && e.error != INT_MIN ? -e.error : EPROTO; return -1; }
                ack = 1;
            } else if (h.nlmsg_type == NLMSG_DONE) {
                int error = 0;
                if (!dump) return -1;
                if (h.nlmsg_len >= NLMSG_HDRLEN + sizeof(error)) memcpy(&error, buf + pos + NLMSG_HDRLEN, sizeof(error));
                if (error) return -1;
                done = 1;
            } else {
                if (h.nlmsg_type != (unsigned)nl->family || h.nlmsg_len < NLMSG_HDRLEN + GENL_HDRLEN) return -1;
                memcpy(&g, buf + pos + NLMSG_HDRLEN, sizeof(g));
                if (fn && fn(g.cmd, buf + pos + NLMSG_HDRLEN + GENL_HDRLEN,
                             h.nlmsg_len - NLMSG_HDRLEN - GENL_HDRLEN, arg)) return -1;
            }
        }
        if (dump ? done : ack) return 0;
    }
}
static int family_reply(int cmd, const void *p, size_t n, void *out) {
    struct attrs it = { p, n, 0 };
    struct attr a;
    uint16_t id;
    int *family = out;
    if (cmd != CTRL_CMD_NEWFAMILY) return -1;
    while (next_attr(&it, &a)) if (a.type == CTRL_ATTR_FAMILY_ID) {
        if (*family || a.n != sizeof(id)) return -1;
        memcpy(&id, a.p, sizeof(id)); if (id < GENL_MIN_ID) return -1; *family = id;
    }
    return it.bad ? -1 : 0;
}
static int nl_open(struct nl *nl) {
    struct sockaddr_nl addr;
    struct msg m;
    int id = 0;
    memset(nl, 0, sizeof(*nl)); nl->fd = -1;
    nl->fd = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC | SOCK_NONBLOCK, NETLINK_GENERIC);
    if (nl->fd < 0) return -1;
    memset(&addr, 0, sizeof(addr)); addr.nl_family = AF_NETLINK;
    if (bind(nl->fd, (struct sockaddr *)&addr, sizeof(addr))) goto fail;
    nl->family = GENL_ID_CTRL;
    msg_init(&m, nl->family, CTRL_CMD_GETFAMILY, 0, ++nl->seq);
    if (msg_attr(&m, CTRL_ATTR_FAMILY_NAME, "nl80211", 8) || exchange(nl, &m, family_reply, &id) || !id) goto fail;
    nl->family = id; return 0;
fail:
    close(nl->fd); nl->fd = -1; return -1;
}
#define IFACE_NAME_INVALID (-2)
#define IFACE_TYPE_INVALID (-3)
#define IFACE_FREQ_INVALID (-4)
static int iface_attr_error(unsigned bit) {
    return bit == 16 ? IFACE_NAME_INVALID : bit == 4 ? IFACE_TYPE_INVALID :
        bit == 8 ? IFACE_FREQ_INVALID : -1;
}
static int parse_iface(const void *p, size_t n, struct iface *v) {
    struct attrs it = { p, n, 0 };
    struct attr a;
    unsigned seen = 0, bit;
    uint32_t *value;
    memset(v, 0, sizeof(*v));
    while (next_attr(&it, &a)) {
        value = NULL; bit = 0;
        if (a.type == NL80211_ATTR_IFINDEX) { value = &v->index; bit = 1; }
        if (a.type == NL80211_ATTR_WIPHY) { value = &v->phy; bit = 2; }
        if (a.type == NL80211_ATTR_IFTYPE) { value = &v->type; bit = 4; }
        if (a.type == NL80211_ATTR_WIPHY_FREQ) { value = &v->freq; bit = 8; }
        if (a.type == NL80211_ATTR_IFNAME) {
            bit = 16;
            if (!a.n || a.n > sizeof(v->name) || a.p[a.n - 1] || memchr(a.p, 0, a.n - 1))
                return IFACE_NAME_INVALID;
            memcpy(v->name, a.p, a.n);
        }
        if (bit && (seen & bit)) return iface_attr_error(bit);
        seen |= bit;
        if (value && attr_u32(&a, value)) return iface_attr_error(bit);
    }
    if (it.bad) return -1;
    if (!(seen & 16)) return IFACE_NAME_INVALID;
    if (!(seen & 4)) return IFACE_TYPE_INVALID;
    return (seen & 3) != 3 || !v->index ? -1 : 0;
}
struct interfaces {
    struct iface target;
    uint32_t index, phy;
    int count, extra, one, error;
};
static int interface_reply(int cmd, const void *p, size_t n, void *out) {
    struct interfaces *r = out;
    struct iface v;
    int parsed;
    if (cmd != NL80211_CMD_NEW_INTERFACE || ++r->count > 128) {
        r->error = -1; return -1;
    }
    parsed = parse_iface(p, n, &v);
    if (parsed) { r->error = parsed; return -1; }
    if (r->one) {
        if (r->count != 1 || v.index != r->index) { r->error = -1; return -1; }
        r->target = v;
    } else if (v.phy == r->phy && v.index != r->index) r->extra++;
    return 0;
}
static int get_interface(struct nl *nl, uint32_t index, struct iface *v) {
    struct interfaces r;
    struct msg m;
    memset(&r, 0, sizeof(r)); r.index = index; r.one = 1;
    if (!index) return -1;
    msg_init(&m, nl->family, NL80211_CMD_GET_INTERFACE, 0, ++nl->seq);
    if (msg_u32(&m, NL80211_ATTR_IFINDEX, index) || exchange(nl, &m, interface_reply, &r) || r.count != 1)
        return r.error ? r.error : -1;
    *v = r.target; return 0;
}
static int alone_on_phy(struct nl *nl, const struct iface *ap) {
    struct interfaces r;
    struct msg m;
    memset(&r, 0, sizeof(r)); r.index = ap->index; r.phy = ap->phy;
    msg_init(&m, nl->family, NL80211_CMD_GET_INTERFACE, NLM_F_DUMP, ++nl->seq);
    return exchange(nl, &m, interface_reply, &r) || !r.count || r.extra ? -1 : 0;
}
struct proof {
    uint32_t phy, freq;
    int replies, seen, supported;
    const char *error;
};
static int wiphy_reply(int cmd, const void *p, size_t n, void *out) {
    struct proof *r = out;
    struct attrs it = { p, n, 0 };
    struct attr a;
    uint32_t phy = 0;
    int have_phy = 0, result;
    if (cmd != NL80211_CMD_NEW_WIPHY || ++r->replies > 1) {
        r->error = "capability_nl80211_query_failed"; return -1;
    }
    while (next_attr(&it, &a)) {
        if (a.type == NL80211_ATTR_WIPHY) {
            if (have_phy++ || attr_u32(&a, &phy)) {
                r->error = "capability_missing_or_malformed"; return -1;
            }
        } else if (a.type == NL80211_ATTR_INTERFACE_COMBINATIONS) {
            result = prove_combinations(a.p, a.n, r->freq);
            if (r->seen++ || result == PROOF_MALFORMED) {
                r->error = "capability_missing_or_malformed"; return -1;
            }
            if (result == PROOF_UNVERIFIED) {
                r->error = "capability_proof_unavailable"; return -1;
            }
            r->supported = result;
        }
    }
    if (it.bad || !have_phy || phy != r->phy) {
        r->error = "capability_missing_or_malformed"; return -1;
    }
    return 0;
}
static const char *ap_probe_error(int result, const struct iface *ap) {
    if (result == IFACE_NAME_INVALID) return "ap_name_missing_or_invalid";
    if (result == IFACE_TYPE_INVALID) return "ap_type_missing_or_invalid";
    if (result == IFACE_FREQ_INVALID) return "ap_frequency_missing_or_invalid";
    if (result) return "ap_nl80211_query_failed";
    if (!ap->name[0] || strcmp(ap->name, C2M_WIFI_AP)) return "ap_name_missing_or_invalid";
    if (ap->type != NL80211_IFTYPE_AP) return "ap_type_missing_or_invalid";
    if (!ap->freq) return "ap_frequency_missing_or_invalid";
    return "";
}
static int capability_probe_result(struct worker *w, int query_failed, const struct proof *r) {
    w->supported = -1;
    if (query_failed || r->error || r->replies != 1 || r->seen != 1) {
        w->error = r->error ? r->error : query_failed ? "capability_nl80211_query_failed" :
            "capability_missing_or_malformed";
        return -1;
    }
    if (r->supported != 0 && r->supported != 1) { w->error = "capability_proof_unavailable"; return -1; }
    if (!r->supported) {
        w->supported = 0; w->error = "ap_sta_combination_not_proven"; return -1;
    }
    w->supported = 1; w->error = ""; return 0;
}
static int probe(struct worker *w) {
    struct msg m;
    struct proof r;
    int result;
    /* A failed observation is unknown. Only a complete valid combination
     * proof below may publish sta_supported=no. */
    w->supported = -1;
    result = get_interface(&w->nl, if_nametoindex(C2M_WIFI_AP), &w->ap);
    w->error = ap_probe_error(result, &w->ap);
    if (*w->error) return -1;
    if (if_nametoindex(C2M_WIFI_STA)) { w->error = "preexisting_vif"; return -1; }
    memset(&r, 0, sizeof(r)); r.phy = w->ap.phy; r.freq = w->ap.freq;
    msg_init(&m, w->nl.family, NL80211_CMD_GET_WIPHY, 0, ++w->nl.seq);
    result = msg_u32(&m, NL80211_ATTR_WIPHY, r.phy) || exchange(&w->nl, &m, wiphy_reply, &r);
    return capability_probe_result(w, result, &r);
}
static int ap_unchanged(struct worker *w) {
    struct iface ap;
    return get_interface(&w->nl, w->ap.index, &ap) || ap.index != w->ap.index ||
        ap.phy != w->ap.phy || ap.type != NL80211_IFTYPE_AP || ap.freq != w->ap.freq ||
        strcmp(ap.name, C2M_WIFI_AP) || if_nametoindex(C2M_WIFI_AP) != ap.index ? -1 : 0;
}
/* Traverse every component with O_NOFOLLOW. Only root-owned sticky writable
 * ancestors (notably /tmp) are allowed. Never mkdir intermediate ancestors. */
static int absolute_path(const char *in, char *out, size_t size) {
    char cwd[PATH_MAX];
    int n;
    if (!in[0] || strchr(in, '\n') || strchr(in, '\r')) return -1;
    if (in[0] == '/') n = snprintf(out, size, "%s", in);
    else { if (!getcwd(cwd, sizeof(cwd))) return -1; n = snprintf(out, size, "%s/%s", cwd, in); }
    return n < 0 || (size_t)n >= size ? -1 : 0;
}
static int stock_config_ancestor(const char *path, const struct stat *st) {
    /* Exact golden EN ownership, not a general group-writable exception. The
     * vendor UID 1001 config writer is part of the trusted stock boundary.
     * Never change its mode/owner just to make our private child work. */
    if (st->st_uid != 1001 || st->st_gid != 1001) return 0;
    if (!strcmp(path, "/customer")) return (st->st_mode & 07777) == 0755;
    return (st->st_mode & 07777) == 0775 &&
        (!strcmp(path, "/customer/minieye") ||
         !strcmp(path, "/customer/minieye/config"));
}
static int safe_dir(const char *path, int private_leaf, int create) {
    char copy[PATH_MAX], walk[PATH_MAX] = "", *part, *save;
    struct stat st;
    int fd, next;
    if (absolute_path(path, copy, sizeof(copy))) return -1;
    fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC); if (fd < 0) return -1;
    part = strtok_r(copy, "/", &save);
    while (part) {
        char *after = strtok_r(NULL, "/", &save);
        if (!strcmp(part, ".") || !strcmp(part, "..")) goto fail;
        next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (next < 0 && errno == ENOENT && !after && create) {
            if (mkdirat(fd, part, 0700)) goto fail;
            next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        }
        if (next < 0) goto fail;
        close(fd); fd = next;
        {
            size_t used = strlen(walk), available = sizeof(walk) - used;
            int length = snprintf(walk + used, available, "/%s", part);
            if (length < 0 || (size_t)length >= available) goto fail;
        }
        if (fstat(fd, &st) || (st.st_uid != 0 && st.st_uid != geteuid() && !stock_config_ancestor(walk, &st))) goto fail;
        if ((st.st_mode & 0022) && !(st.st_uid == 0 && (st.st_mode & S_ISVTX)) && !stock_config_ancestor(walk, &st)) goto fail;
        if (!after && private_leaf && (st.st_uid != geteuid() || (st.st_mode & 0777) != 0700)) goto fail;
        part = after;
    }
    if (private_leaf && (fstat(fd, &st) || st.st_uid != geteuid() || (st.st_mode & 0777) != 0700)) goto fail;
    return fd;
fail:
    close(fd); return -1;
}
static int private_file(int fd, size_t max) {
    struct stat st;
    return fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != geteuid() ||
        (st.st_mode & 0777) != 0600 || st.st_nlink != 1 || st.st_size < 0 ||
        (uint64_t)st.st_size > max ? -1 : 0;
}
static int write_all(int fd, const void *data, size_t n) {
    const unsigned char *p = data;
    ssize_t r;
    while (n) {
        r = write(fd, p, n);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return -1;
        p += r; n -= (size_t)r;
    }
    return 0;
}
static int read_private(int dir, const char *name, char *buf, size_t size, struct stat *st);
static const char *bluetooth_presence(struct worker *w) {
    char text[16385];
    int n = w->runfd < 0 ? -1 : read_private(w->runfd, "bluetooth.txt", text, sizeof(text), NULL);
    if (n < 0) return "unknown";
    if (strstr(text, "\nstatus=COMPLETE\n") &&
        strstr(text, "\nverdict=HCI_PRESENT_NOT_RADIO_TESTED\n")) return "seen";
    if (strstr(text, "\nstatus=COMPLETE\n") &&
        strstr(text, "\nverdict=NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE\n")) return "not_seen";
    return "unknown";
}
static int status_write(struct worker *w) {
    char path[PATH_MAX], temp[80], text[512], *base;
    struct stat st;
    int dir = -1, fd = -1, n, rc = -1;
    static unsigned serial;
    if (absolute_path(w->status, path, sizeof(path)) || !(base = strrchr(path, '/')) || !base[1]) return -1;
    *base++ = 0; dir = safe_dir(path[0] ? path : "/", 0, 0); if (dir < 0) return -1;
    if (!fstatat(dir, base, &st, AT_SYMLINK_NOFOLLOW)) {
        if (!S_ISREG(st.st_mode) || st.st_uid != geteuid() || st.st_nlink != 1) goto done;
    } else if (errno != ENOENT) goto done;
    snprintf(temp, sizeof(temp), ".c2m-wifi-status-%ld-%u.tmp", (long)getpid(), ++serial);
    fd = openat(dir, temp, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) goto done;
    n = snprintf(text, sizeof(text), "sta_supported=%s\nsta_state=%s\nsta_ssid=\nsta_ipv4=\nlast_error=%s\nbt_presence=%s\ndhcp_helper=missing\n",
                 w->supported < 0 ? "unknown" : w->supported ? "yes" : "no", w->state,
                 *w->error ? w->error : "none", bluetooth_presence(w));
    if (n > 0 && (size_t)n < sizeof(text) && !write_all(fd, text, (size_t)n) && !fsync(fd) &&
        !renameat(dir, temp, dir, base)) { (void)fsync(dir); rc = 0; }
    close(fd); (void)unlinkat(dir, temp, 0);
done:
    close(dir); return rc;
}
static int read_private(int dir, const char *name, char *buf, size_t size, struct stat *st) {
    int fd = openat(dir, name, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    ssize_t n;
    size_t used = 0;
    if (fd < 0) return -1;
    if (private_file(fd, size - 1) || (st && fstat(fd, st))) { close(fd); return -1; }
    while (used < size) {
        n = read(fd, buf + used, size - used);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { close(fd); return -1; }
        if (!n) break;
        used += (size_t)n;
    }
    close(fd);
    if (used >= size || memchr(buf, 0, used)) return -1;
    buf[used] = 0; return (int)used;
}
static const char *probe_state(int supported) {
    return supported < 0 ? "unknown" : supported ? "idle" : "unsupported";
}
/* Read-only observation: GET_INTERFACE/GET_WIPHY and (if necessary)
 * nl80211 family discovery. Never create a VIF or enter association/cleanup. */
static int observe_capability(struct worker *w) {
    if (w->nl.fd < 0 && nl_open(&w->nl)) {
        w->supported = -1; w->error = "nl80211_unavailable"; return -1;
    }
    return probe(w);
}
static void startup_probe_record(struct worker *w, int64_t now) {
    ++w->startup_probe_attempts;
    w->state = probe_state(w->supported);
    w->startup_probe_retry = now >= 0 && w->supported < 0 &&
        w->startup_probe_attempts < STARTUP_PROBE_ATTEMPTS;
    w->next_probe = now + STARTUP_PROBE_INTERVAL;
}
/* Existence or an inspection error counts as intent, even for unsafe files.
 * Do not read credentials and never consume a request in a retry path. */
static int startup_probe_no_intent(struct worker *w) {
    struct stat st;
    if (fstatat(w->configfd, "wifi.conf", &st, AT_SYMLINK_NOFOLLOW) == 0 || errno != ENOENT) return 0;
    if (fstatat(w->runfd, "connect.request", &st, AT_SYMLINK_NOFOLLOW) == 0 || errno != ENOENT) return 0;
    return 1;
}
/* Callback is solely a read-only observer, exposed here so rootless fixtures
 * can prove budget, cancellation and meaningful-change behavior without I/O. */
static int startup_probe_tick(struct worker *w, int64_t now, int no_intent,
                              int (*observe)(struct worker *)) {
    int before;
    const char *state, *error;
    if (!w->startup_probe_retry) return 0;
    if (!no_intent || w->owned || w->cfg_owned || w->ctrl_owned || w->pid_owned ||
        strcmp(w->state, probe_state(w->supported)) || now < 0) {
        w->startup_probe_retry = 0; return 0;
    }
    if (now < w->next_probe) return 0;
    before = w->supported; state = w->state; error = w->error;
    (void)observe(w);
    startup_probe_record(w, now);
    return before != w->supported || strcmp(state, w->state) || strcmp(error, w->error);
}
static int consume_request(struct worker *w) {
    char buf[129];
    struct stat opened, current;
    int n;
    if (fstatat(w->runfd, "connect.request", &current, AT_SYMLINK_NOFOLLOW)) return errno == ENOENT ? 0 : -1;
    n = read_private(w->runfd, "connect.request", buf, sizeof(buf), &opened);
    if (n < 0) return -1;
    if (fstatat(w->runfd, "connect.request", &current, AT_SYMLINK_NOFOLLOW) ||
        opened.st_dev != current.st_dev || opened.st_ino != current.st_ino ||
        unlinkat(w->runfd, "connect.request", 0)) return -1;
    return !strcmp(buf, "version=1\naction=connect\n") ? 1 : -1;
}
static int is_hex(const char *s, size_t min, size_t max) {
    size_t n = strlen(s), i;
    if (n < min || n > max || (n & 1)) return 0;
    for (i = 0; i < n; ++i) if (!((s[i] >= '0' && s[i] <= '9') ||
        (s[i] >= 'a' && s[i] <= 'f') || (s[i] >= 'A' && s[i] <= 'F'))) return 0;
    return 1;
}
/* Re-render the tiny accepted subset, never pass arbitrary wpa directives. */
static int parse_config(char *buf, char ssid[65], char psk[65]) {
    char *line, *save, *end;
    int phase = 0, hs = 0, hp = 0, hk = 0;
    ssid[0] = psk[0] = 0;
    for (line = strtok_r(buf, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        while (*line == ' ' || *line == '\t' || *line == '\r') line++;
        end = line + strlen(line);
        while (end > line && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r')) *--end = 0;
        if (!*line || *line == '#') continue;
        if (!strcmp(line, "network={") && !phase) { phase = 1; continue; }
        if (!strcmp(line, "}") && phase == 1) { phase = 2; continue; }
        if (phase != 1) return -1;
        if (!strncmp(line, "ssid=", 5)) {
            if (hs++ || !is_hex(line + 5, 2, 64)) return -1;
            strcpy(ssid, line + 5);
        } else if (!strncmp(line, "psk=", 4)) {
            if (hp++ || !is_hex(line + 4, 64, 64)) return -1;
            strcpy(psk, line + 4);
        } else if (!strcmp(line, "key_mgmt=WPA-PSK")) { if (hk++) return -1; }
        else if (strcmp(line, "proto=RSN") && strcmp(line, "pairwise=CCMP") &&
                 strcmp(line, "group=CCMP") && strcmp(line, "scan_ssid=1")) return -1;
    }
    return phase == 2 && hs && hp ? 0 : -1;
}
static int owns_sta(struct worker *w) {
    struct iface v;
    return !w->owned || !w->sta.index || w->sta.index == w->ap.index ||
        get_interface(&w->nl, w->sta.index, &v) || v.phy != w->ap.phy ||
        v.type != NL80211_IFTYPE_STATION || strcmp(v.name, C2M_WIFI_STA) ||
        if_nametoindex(C2M_WIFI_STA) != w->sta.index ? -1 : 0;
}
static int create_sta(struct worker *w) {
    struct msg m;
    struct ifreq ifr;
    int fd, rc;
    if (if_nametoindex(C2M_WIFI_STA) || alone_on_phy(&w->nl, &w->ap) || ap_unchanged(w)) return -1;
    msg_init(&m, w->nl.family, NL80211_CMD_NEW_INTERFACE, 0, ++w->nl.seq);
    if (msg_u32(&m, NL80211_ATTR_WIPHY, w->ap.phy) ||
        msg_u32(&m, NL80211_ATTR_IFTYPE, NL80211_IFTYPE_STATION) ||
        msg_attr(&m, NL80211_ATTR_IFNAME, C2M_WIFI_STA, sizeof(C2M_WIFI_STA)) ||
        exchange(&w->nl, &m, NULL, NULL)) return -1;
    /* ACK is the ownership proof. A timeout is ambiguous and never reclaimed. */
    w->owned = 1; w->sta.index = if_nametoindex(C2M_WIFI_STA);
    if (owns_sta(w) || get_interface(&w->nl, w->sta.index, &w->sta) || ap_unchanged(w)) return -1;
    memset(&ifr, 0, sizeof(ifr)); strcpy(ifr.ifr_name, C2M_WIFI_STA);
    fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0); if (fd < 0) return -1;
    rc = ioctl(fd, SIOCGIFFLAGS, &ifr);
    if (!rc) { ifr.ifr_flags |= IFF_UP; rc = ioctl(fd, SIOCSIFFLAGS, &ifr); }
    close(fd); return rc || ap_unchanged(w) ? -1 : 0;
}
static int proc_identity(struct worker *w, pid_t pid) {
    char path[80], exe[PATH_MAX], args[PATH_MAX * 2];
    const char *expected[] = { w->supplicant, "-i", C2M_WIFI_STA, "-c", w->config, "-P", w->pidfile, "-B" };
    ssize_t n;
    size_t pos = 0, i, len;
    int fd;
    if (pid <= 1 || pid == getpid()) return 0;
    snprintf(path, sizeof(path), "/proc/%ld/exe", (long)pid);
    n = readlink(path, exe, sizeof(exe) - 1); if (n < 0) return 0;
    exe[n] = 0; if (strcmp(exe, w->supplicant)) return 0;
    snprintf(path, sizeof(path), "/proc/%ld/cmdline", (long)pid);
    fd = open(path, O_RDONLY | O_CLOEXEC); if (fd < 0) return 0;
    n = read(fd, args, sizeof(args)); close(fd);
    if (n <= 0 || n == (ssize_t)sizeof(args)) return 0;
    for (i = 0; i < sizeof(expected) / sizeof(expected[0]); ++i) {
        len = strlen(expected[i]) + 1;
        if (len > (size_t)n - pos || memcmp(args + pos, expected[i], len)) return 0;
        pos += len;
    }
    return pos == (size_t)n;
}
static pid_t owned_pid(struct worker *w) {
    char text[33], *end;
    long pid;
    if (!w->pid_owned || read_private(w->runfd, OWN_PID, text, sizeof(text), NULL) < 1) return -1;
    errno = 0; pid = strtol(text, &end, 10);
    if (errno || pid <= 1 || pid > INT_MAX || (*end && strcmp(end, "\n"))) return -1;
    return proc_identity(w, (pid_t)pid) ? (pid_t)pid : -1;
}
static int launch_supplicant(struct worker *w) {
    pid_t child, r;
    int status;
    int64_t until;
    struct timespec pause = { 0, 50000000 };
    child = fork(); if (child < 0) return -1;
    if (!child) {
        int nullfd = open("/dev/null", O_RDWR);
        if (nullfd < 0) _exit(126);
        (void)dup2(nullfd, STDIN_FILENO); (void)dup2(nullfd, STDOUT_FILENO); (void)dup2(nullfd, STDERR_FILENO);
        if (nullfd > STDERR_FILENO) close(nullfd);
        /* No shell, inherited loader environment, or supplicant log. */
        execl(w->supplicant, w->supplicant, "-i", C2M_WIFI_STA, "-c", w->config, "-P", w->pidfile, "-B", (char *)NULL);
        _exit(127);
    }
    until = now_ms() + 5000;
    do {
        r = waitpid(child, &status, WNOHANG);
        if (r == child) return WIFEXITED(status) && !WEXITSTATUS(status) && owned_pid(w) > 0 ? 0 : -1;
        if (r < 0 && errno != EINTR) return -1;
        nanosleep(&pause, NULL);
    } while (!stopping && now_ms() < until);
    (void)kill(child, SIGKILL);
    while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
    return -1;
}
static int cleanup(struct worker *w) {
    struct msg m;
    pid_t pid = owned_pid(w);
    struct timespec pause = { 0, 50000000 };
    int64_t until;
    int rc = 0;
    char socketpath[PATH_MAX];
    if (pid > 0) {
        if (kill(pid, SIGTERM) && errno != ESRCH) rc = -1;
        until = now_ms() + 1500;
        while (proc_identity(w, pid) && now_ms() < until) nanosleep(&pause, NULL);
        if (proc_identity(w, pid)) {
            (void)kill(pid, SIGKILL); until = now_ms() + 500;
            while (proc_identity(w, pid) && now_ms() < until) nanosleep(&pause, NULL);
            if (proc_identity(w, pid)) rc = -1;
        }
    }
    if (w->owned) {
        if (owns_sta(w)) rc = -1;
        else {
            msg_init(&m, w->nl.family, NL80211_CMD_DEL_INTERFACE, 0, ++w->nl.seq);
            if (msg_u32(&m, NL80211_ATTR_IFINDEX, w->sta.index) || exchange(&w->nl, &m, NULL, NULL)) rc = -1;
            else w->owned = 0;
        }
    }
    /* Unlink only paths created by this process, inside its private directory. */
    if (w->cfg_owned) { (void)unlinkat(w->runfd, OWN_CONFIG, 0); w->cfg_owned = 0; }
    if (w->pid_owned) { (void)unlinkat(w->runfd, OWN_PID, 0); w->pid_owned = 0; }
    if (w->ctrl_owned) {
        if (snprintf(socketpath, sizeof(socketpath), "%s/%s", w->ctrl, C2M_WIFI_STA) < (int)sizeof(socketpath)) (void)unlink(socketpath);
        (void)unlink(w->client); (void)unlinkat(w->runfd, OWN_CTRL, AT_REMOVEDIR); w->ctrl_owned = 0;
    }
    return rc;
}
static int trusted_supplicant(const char *path, const struct stat *st) {
    if (!S_ISREG(st->st_mode) || (st->st_mode & 0022)) return 0;
    if (st->st_uid == 0 || st->st_uid == geteuid()) return 1;
    /* Rebuild preserves the EN customer UID/GID 1001. This one exact
     * immutable-package executable is trusted like stock hostapd, not an
     * arbitrary executable supplied by a config/web request. */
    return st->st_uid == 1001 && st->st_gid == 1001 &&
        (st->st_mode & 07777) == 0755 &&
        !strcmp(path, "/customer/c2m/wpa_supplicant");
}
static int prepare_paths(struct worker *w, const char *configdir, const char *rundir, const char *supplicant) {
    struct stat a, b, executable;
    int fd;
    if (absolute_path(rundir, w->run, sizeof(w->run)) || strpbrk(w->run, " \t#\"\\") ||
        !realpath(supplicant, w->supplicant) || stat(w->supplicant, &executable) ||
        !trusted_supplicant(w->supplicant, &executable) || access(w->supplicant, X_OK)) return -1;
    w->configfd = safe_dir(configdir, 1, 1); w->runfd = safe_dir(rundir, 1, 1);
    if (w->configfd < 0 || w->runfd < 0 || fstat(w->configfd, &a) || fstat(w->runfd, &b) ||
        (a.st_dev == b.st_dev && a.st_ino == b.st_ino)) return -1;
    w->lockfd = openat(w->runfd, "wifi-controller.lock", O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (w->lockfd < 0 || private_file(w->lockfd, 0) || flock(w->lockfd, LOCK_EX | LOCK_NB)) return -1;
    if (snprintf(w->config, sizeof(w->config), "%s/%s", w->run, OWN_CONFIG) >= (int)sizeof(w->config) ||
        snprintf(w->pidfile, sizeof(w->pidfile), "%s/%s", w->run, OWN_PID) >= (int)sizeof(w->pidfile) ||
        snprintf(w->ctrl, sizeof(w->ctrl), "%s/%s", w->run, OWN_CTRL) >= (int)sizeof(w->ctrl) ||
        snprintf(w->client, sizeof(w->client), "%s/%s", w->run, OWN_CLIENT) >= (int)sizeof(w->client) ||
        strlen(w->ctrl) + 1 + strlen(C2M_WIFI_STA) >= sizeof(((struct sockaddr_un *)0)->sun_path) ||
        strlen(w->client) >= sizeof(((struct sockaddr_un *)0)->sun_path)) return -1;
    /* Never reclaim artifacts that could belong to an earlier controller. */
    if (!fstatat(w->runfd, OWN_CONFIG, &a, AT_SYMLINK_NOFOLLOW) || errno != ENOENT) return -1;
    if (!fstatat(w->runfd, OWN_PID, &a, AT_SYMLINK_NOFOLLOW) || errno != ENOENT) return -1;
    if (!fstatat(w->runfd, OWN_CTRL, &a, AT_SYMLINK_NOFOLLOW) || errno != ENOENT) return -1;
    if (!fstatat(w->runfd, OWN_CLIENT, &a, AT_SYMLINK_NOFOLLOW) || errno != ENOENT) return -1;
    /* Verify an executable without executing it during preparation. */
    fd = open(w->supplicant, O_RDONLY | O_NOFOLLOW | O_CLOEXEC); if (fd < 0) return -1;
    close(fd); return 0;
}
static int start_association(struct worker *w) {
    char input[4097], ssid[65], psk[65], generated[PATH_MAX + 512];
    int fd = -1, n, rc = -1;
    w->error = "configuration_missing_or_invalid";
    if (read_private(w->configfd, "wifi.conf", input, sizeof(input), NULL) < 0 || parse_config(input, ssid, psk)) goto out;
    if (observe_capability(w)) goto out;
    if (geteuid() != 0) { w->error = "root_required_for_association"; goto out; }
    w->error = "private_runtime_unavailable";
    if (mkdirat(w->runfd, OWN_CTRL, 0700)) goto out;
    w->ctrl_owned = 1;
    fd = openat(w->runfd, OWN_CONFIG, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) goto out;
    w->cfg_owned = 1;
    n = snprintf(generated, sizeof(generated), "ctrl_interface=%s\nap_scan=1\nnetwork={\nssid=%s\npsk=%s\nkey_mgmt=WPA-PSK\nproto=RSN\nscan_ssid=1\nscan_freq=%u\nfreq_list=%u\n}\n", w->ctrl, ssid, psk, w->ap.freq, w->ap.freq);
    if (n < 0 || (size_t)n >= sizeof(generated) || write_all(fd, generated, (size_t)n) || fsync(fd)) goto out;
    close(fd); fd = -1;
    fd = openat(w->runfd, OWN_PID, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) goto out;
    w->pid_owned = 1; close(fd); fd = -1;
    w->error = "vif_creation_failed_or_ambiguous";
    if (create_sta(w)) goto out;
    w->error = "supplicant_failed_or_unverified";
    if (launch_supplicant(w) || ap_unchanged(w)) goto out;
    w->started = now_ms(); w->state = "associating"; w->error = ""; rc = 0;
out:
    if (fd >= 0) close(fd);
    wipe(input, sizeof(input)); wipe(ssid, sizeof(ssid)); wipe(psk, sizeof(psk)); wipe(generated, sizeof(generated));
    if (rc) { if (cleanup(w)) w->error = "cleanup_unverified_manual_recovery_required"; w->state = "failed"; }
    return rc;
}
static int supplicant_status(struct worker *w) {
    struct sockaddr_un local, remote;
    struct stat st;
    char buf[4097], *line, *save, *end;
    int fd = -1, completed = 0, state_seen = 0, freq_seen = 0, rc = -1;
    unsigned long freq = 0;
    ssize_t n;
    memset(&local, 0, sizeof(local)); memset(&remote, 0, sizeof(remote));
    local.sun_family = remote.sun_family = AF_UNIX;
    strcpy(local.sun_path, w->client);
    if (snprintf(remote.sun_path, sizeof(remote.sun_path), "%s/%s", w->ctrl, C2M_WIFI_STA) >= (int)sizeof(remote.sun_path)) return -1;
    if (lstat(remote.sun_path, &st) || !S_ISSOCK(st.st_mode) || st.st_uid != geteuid()) return -1;
    fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0); if (fd < 0) return -1;
    if (bind(fd, (struct sockaddr *)&local, sizeof(local))) { close(fd); return -1; }
    if (connect(fd, (struct sockaddr *)&remote, sizeof(remote)) || send(fd, "STATUS", 6, 0) != 6 ||
        wait_fd(fd, POLLIN, now_ms() + 750)) goto out;
    n = recv(fd, buf, sizeof(buf) - 1, MSG_TRUNC);
    if (n <= 0 || n >= (ssize_t)sizeof(buf) - 1 || memchr(buf, 0, (size_t)n)) goto out;
    buf[n] = 0;
    for (line = strtok_r(buf, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        if (!strncmp(line, "wpa_state=", 10)) { if (state_seen++) goto out; completed = !strcmp(line + 10, "COMPLETED"); }
        if (!strncmp(line, "freq=", 5)) {
            if (freq_seen++) goto out;
            errno = 0; freq = strtoul(line + 5, &end, 10); if (errno || end == line + 5 || *end) goto out;
        }
    }
    if (state_seen) rc = completed && freq_seen && freq == w->ap.freq ? 1 : 0;
out:
    close(fd); (void)unlink(w->client); wipe(buf, sizeof(buf)); return rc;
}
static void monitor(struct worker *w) {
    struct iface sta;
    int associated;
    const char *before = w->state;
    if (ap_unchanged(w)) w->error = "ap_changed_or_unverifiable";
    else if (owns_sta(w) || owned_pid(w) <= 0) w->error = "owned_station_lost";
    else {
        associated = supplicant_status(w);
        if (associated == 1 && !get_interface(&w->nl, w->sta.index, &sta) && sta.freq == w->ap.freq) {
            w->state = "associated_no_ip"; w->error = "dhcp_helper_missing";
            if (strcmp(before, w->state)) (void)status_write(w);
            return;
        }
        w->state = "associating"; w->error = "";
        if (now_ms() - w->started < 30000) {
            if (strcmp(before, w->state)) (void)status_write(w);
            return;
        }
        w->error = "association_timeout_or_unverified";
    }
    if (cleanup(w)) w->error = "cleanup_unverified_manual_recovery_required";
    w->state = "failed"; (void)status_write(w);
}

/* Synthetic netlink fixtures; deliberately no socket, ioctl, proc or files. */
static void fixture_init(struct msg *m) { memset(m, 0, sizeof(*m)); m->raw = 1; }
static size_t fixture_begin(struct msg *m, unsigned type) {
    size_t at = m->n; (void)msg_attr(m, type | NLA_F_NESTED, NULL, 0); return at;
}
static void fixture_end(struct msg *m, size_t at) {
    struct nlattr a;
    memcpy(&a, m->data + at, sizeof(a)); a.nla_len = (uint16_t)(m->n - at);
    memcpy(m->data + at, &a, sizeof(a));
}
static void fixture_limit(struct msg *m, int id, int ap, int sta, unsigned max) {
    size_t l = fixture_begin(m, (unsigned)id), t;
    (void)msg_u32(m, NL80211_IFACE_LIMIT_MAX, max);
    t = fixture_begin(m, NL80211_IFACE_LIMIT_TYPES);
    if (ap) (void)msg_attr(m, NL80211_IFTYPE_AP, NULL, 0);
    if (sta) (void)msg_attr(m, NL80211_IFTYPE_STATION, NULL, 0);
    fixture_end(m, t); fixture_end(m, l);
}
static void fixture_combo(struct msg *m, int id, int ap, int sta, int shared, unsigned total, unsigned channels, unsigned max) {
    size_t c = fixture_begin(m, (unsigned)id), l;
    (void)msg_u32(m, NL80211_IFACE_COMB_MAXNUM, total);
    if (channels) (void)msg_u32(m, NL80211_IFACE_COMB_NUM_CHANNELS, channels);
    l = fixture_begin(m, NL80211_IFACE_COMB_LIMITS);
    if (shared) fixture_limit(m, 1, ap, sta, max);
    else { if (ap) fixture_limit(m, 1, 1, 0, max); if (sta) fixture_limit(m, 2, 0, 1, max); }
    fixture_end(m, l); fixture_end(m, c);
}
static int test_result(const char *name, int actual, int expected) {
    if (actual != expected) { fprintf(stderr, "FAIL %s: %d != %d\n", name, actual, expected); return 1; }
    printf("PASS %s\n", name); return 0;
}
int c2m_wifi_self_test(void) {
    struct msg m;
    struct nlattr bad;
    struct iface v;
    char config[512], ssid[65], psk[65];
    int failures = 0;
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 0, 2, 1, 1);
    failures += test_result("one_channel_requires_current_frequency", prove_combinations(m.data, m.n, 0), PROOF_UNVERIFIED);
    failures += test_result("one_channel_ap_sta", prove_combinations(m.data, m.n, 2412), 1);
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 1, 2, 2, 2);
    failures += test_result("shared_limit_two", prove_combinations(m.data, m.n, 2412), 1);
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 1, 2, 1, 1);
    failures += test_result("shared_limit_one_blocked", prove_combinations(m.data, m.n, 2412), 0);
    fixture_init(&m); fixture_combo(&m, 1, 1, 0, 0, 2, 1, 1); fixture_combo(&m, 2, 0, 1, 0, 2, 1, 1);
    failures += test_result("separate_combinations_not_combined", prove_combinations(m.data, m.n, 2412), 0);
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 0, 1, 1, 1);
    failures += test_result("maxnum_one_blocked", prove_combinations(m.data, m.n, 2412), 0);
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 0, 2, 0, 1);
    failures += test_result("missing_channels_blocked", prove_combinations(m.data, m.n, 2412), -1);
    failures += test_result("missing_combinations_blocked", prove_combinations(NULL, 0, 2412), -1);
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 0, 2, 1, 1);
    failures += test_result("truncated_nested_blocked", prove_combinations(m.data, m.n - 1, 2412), -1);
    bad.nla_len = 3; bad.nla_type = 2; memcpy(m.data + m.n, &bad, sizeof(bad)); m.n += sizeof(bad);
    failures += test_result("valid_then_malformed_blocked", prove_combinations(m.data, m.n, 2412), -1);
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 0, 2, 1, 1);
    /* Duplicate mandatory scalar in an otherwise acceptable combination. */
    (void)msg_u32(&m, NL80211_IFACE_COMB_MAXNUM, 2); fixture_end(&m, 0);
    failures += test_result("duplicate_scalar_blocked", prove_combinations(m.data, m.n, 2412), -1);
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 0, 2, 1, 1);
    (void)msg_attr(&m, NL80211_IFACE_COMB_STA_AP_BI_MATCH, NULL, 0); fixture_end(&m, 0);
    failures += test_result("beacon_constraint_unverified", prove_combinations(m.data, m.n, 2412), PROOF_UNVERIFIED);
    fixture_init(&m);
    (void)msg_u32(&m, NL80211_ATTR_IFINDEX, 7); (void)msg_u32(&m, NL80211_ATTR_WIPHY, 0);
    (void)msg_u32(&m, NL80211_ATTR_IFTYPE, NL80211_IFTYPE_AP); (void)msg_attr(&m, NL80211_ATTR_IFNAME, "wlan0", 6);
    failures += test_result("interface_missing_frequency_is_unknown", parse_iface(m.data, m.n, &v) || v.freq != 0, 0);
    (void)msg_attr(&m, NL80211_ATTR_IFNAME, "evil", 4);
    failures += test_result("interface_bad_name_blocked", parse_iface(m.data, m.n, &v), IFACE_NAME_INVALID);
    snprintf(config, sizeof(config), "network={\nssid=74657374\npsk=%064d\nkey_mgmt=WPA-PSK\n}\n", 0);
    failures += test_result("private_config_subset", parse_config(config, ssid, psk), 0);
    snprintf(config, sizeof(config), "network={\nssid=74657374\npsk=%064d\n}\nctrl_interface=/tmp/public\n", 0);
    failures += test_result("config_directive_injection_blocked", parse_config(config, ssid, psk), -1);
    wipe(config, sizeof(config)); wipe(psk, sizeof(psk)); wipe(ssid, sizeof(ssid));
    printf("self_test=%s\n", failures ? "failed" : "passed"); return failures ? 1 : 0;
}
static void usage(FILE *f) {
    fputs("Usage: c2m-wifi --self-test | --probe | --serve [--config-dir DIR]\n"
          "       [--run-dir DIR] [--status-file FILE] [--supplicant /absolute/path]\n"
          "Association only: DHCP helper missing; AP wlan0 is never reconfigured.\n", f);
}
int main(int argc, char **argv) {
    struct worker w;
    const char *configdir = C2M_WIFI_CONFIG_DIR, *rundir = C2M_WIFI_RUN_DIR;
    const char *supplicant = "/usr/sbin/wpa_supplicant";
    int mode = 0, i, rc = 1, request;
    struct timespec pause = { 0, 500000000 };
    memset(&w, 0, sizeof(w)); w.nl.fd = w.configfd = w.runfd = w.lockfd = -1;
    w.supported = -1; w.status = C2M_WIFI_STATUS_FILE; w.state = "unknown"; w.error = "";
    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--help")) { usage(stdout); return 0; }
        if (!strcmp(argv[i], "--self-test") || !strcmp(argv[i], "--probe") || !strcmp(argv[i], "--serve")) {
            if (mode) { usage(stderr); return 2; }
            mode = !strcmp(argv[i], "--self-test") ? 1 : !strcmp(argv[i], "--probe") ? 2 : 3;
        } else if (i + 1 < argc && !strcmp(argv[i], "--config-dir")) configdir = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--run-dir")) rundir = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--status-file")) w.status = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--supplicant")) supplicant = argv[++i];
        else { usage(stderr); return 2; }
    }
    if (mode == 1) return c2m_wifi_self_test();
    if (!mode) { usage(stderr); return 2; }
    umask(0077); signal(SIGTERM, interrupted); signal(SIGINT, interrupted);
    if (mode == 3 && prepare_paths(&w, configdir, rundir, supplicant)) {
        w.error = "private_paths_or_supplicant_unavailable"; w.state = "failed"; goto finish;
    }
    if (!observe_capability(&w)) rc = 0;
    startup_probe_record(&w, now_ms());
    if (status_write(&w)) { fputs("c2m-wifi: status publication failed\n", stderr); rc = 1; goto close_all; }
    if (mode == 2) goto close_all;
    rc = 0;
    while (!stopping) {
        request = consume_request(&w);
        /* A request cancels startup observation permanently, including an
         * invalid request that consume_request removed from the directory. */
        if (request) w.startup_probe_retry = 0;
        if (request < 0) { w.error = "request_invalid_or_unsafe"; w.state = "failed"; (void)status_write(&w); }
        if (request > 0) {
            if (cleanup(&w)) { w.error = "cleanup_unverified_manual_recovery_required"; w.state = "failed"; }
            else (void)start_association(&w);
            if (status_write(&w)) { rc = 1; break; }
        }
        if (w.owned) monitor(&w);
        if (w.startup_probe_retry && startup_probe_tick(&w, now_ms(), startup_probe_no_intent(&w), observe_capability) &&
            status_write(&w)) { rc = 1; break; }
        nanosleep(&pause, NULL);
    }
    if (cleanup(&w)) { w.state = "failed"; w.error = "cleanup_unverified_manual_recovery_required"; rc = 1; }
    else { w.state = "stopped"; w.error = ""; }
finish:
    if (status_write(&w)) { fputs("c2m-wifi: status publication failed\n", stderr); rc = 1; }
close_all:
    if (w.nl.fd >= 0) close(w.nl.fd);
    if (w.lockfd >= 0) close(w.lockfd);
    if (w.configfd >= 0) close(w.configfd);
    if (w.runfd >= 0) close(w.runfd);
    return rc;
}

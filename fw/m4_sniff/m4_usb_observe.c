/* RAM-only passive M4 RNDIS usb0 observer. No transmit/file/status writer.
 * CLI only --observe/--self-test/--help, no interface/path overrides.
 * Partial TCP payload prefixes, NOT a reconstructed stream or M4 delivery.
 * Fixed 20 received packets / 15 poll calls / 30s monotonic deadline;
 * 512B snaplen, 96B payload prefix, 6144B record budget, <8192B stdout.
 * Actual duration can be much shorter than 15s when packets are ready.
 */
#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define M4_SNIFF_IFACE_FIXED "usb0"
#define M4_SNIFF_MAX_PACKETS 20
#define M4_SNIFF_SNAPLEN 512
#define M4_SNIFF_PAYLOAD_HEX_BYTES 96
#define M4_SNIFF_RECORD_BUDGET 6144
#define M4_SNIFF_LINE_BYTES 640
#define M4_SNIFF_MAX_POLLS 15
#define M4_SNIFF_POLL_MS 1000
#define M4_SNIFF_MAX_MS UINT64_C(30000)

struct m4_parsed {
    uint16_t eth_type, sport, dport;
    uint8_t ip_proto, tcp_flags;
    uint32_t src_ip, dst_ip, tcp_seq, tcp_ack;
    unsigned payload_offset, payload_length, payload_captured;
    unsigned ip_end;
    int is_arp, is_ip, is_tcp, is_udp, is_frag;
};

static uint16_t m4_be16(const uint8_t *b)
{
    return (uint16_t)(((uint16_t)b[0] << 8) | b[1]);
}

static uint32_t m4_be32(const uint8_t *b)
{
    return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) |
           ((uint32_t)b[2] << 8) | b[3];
}

/* Pure parser: IP/UDP lengths exclude Ethernet padding; header truncation,
 * invalid lengths and IP fragments never produce a claimed payload slice.
 * One VLAN tag only; unsupported traffic remains metadata-only.
 * len may be a snaplen prefix; payload_length is the advertised IP/L4 size,
 * payload_captured is the prefix actually retained (at most 96 bytes). */
static void m4_parse_frame(const uint8_t *b, unsigned len, struct m4_parsed *o)
{
    unsigned ip_off = 14, ihl, total, base, transport, header, available;
    if (!o) return;
    memset(o, 0, sizeof(*o));
    if (!b || len < 14) return;
    o->eth_type = m4_be16(b + 12);
    if (o->eth_type == 0x8100 || o->eth_type == 0x88a8) {
        if (len < 18) return;
        o->eth_type = m4_be16(b + 16);
        ip_off = 18;
    }
    if (o->eth_type == 0x0806) {
        o->is_arp = len >= ip_off + 28;
        return;
    }
    if (o->eth_type != 0x0800 || len < ip_off + 20 || (b[ip_off] >> 4) != 4) return;
    ihl = (b[ip_off] & 15U) * 4U;
    total = m4_be16(b + ip_off + 2);
    if (ihl < 20 || total < ihl || len < ip_off + ihl) return;
    o->is_ip = 1;
    o->ip_proto = b[ip_off + 9];
    o->src_ip = m4_be32(b + ip_off + 12);
    o->dst_ip = m4_be32(b + ip_off + 16);
    o->ip_end = ip_off + total;
    if (m4_be16(b + ip_off + 6) & 0x3fffU) {
        o->is_frag = 1;
        return;
    }
    base = ip_off + ihl;
    transport = total - ihl;
    if (o->ip_proto == 6) {
        if (transport < 20 || len < base + 20) return;
        header = (b[base + 12] >> 4) * 4U;
        if (header < 20 || header > transport || len < base + header) return;
        o->is_tcp = 1;
        o->tcp_seq = m4_be32(b + base + 4);
        o->tcp_ack = m4_be32(b + base + 8);
        o->tcp_flags = b[base + 13];
    } else if (o->ip_proto == 17) {
        unsigned udp_length;
        if (transport < 8 || len < base + 8) return;
        udp_length = m4_be16(b + base + 4);
        if (udp_length < 8 || udp_length > transport) return;
        transport = udp_length;
        header = 8;
        o->is_udp = 1;
    } else return;
    o->sport = m4_be16(b + base);
    o->dport = m4_be16(b + base + 2);
    o->payload_offset = base + header;
    o->payload_length = transport - header;
    available = len - o->payload_offset;
    if (available > o->payload_length) available = o->payload_length;
    if (available > M4_SNIFF_PAYLOAD_HEX_BYTES) available = M4_SNIFF_PAYLOAD_HEX_BYTES;
    o->payload_captured = available;
}

/* Exact shared formatter for both live capture and synthetic tests. Unknown
 * offset emits EMPTY payload_hex, never raw header bytes. IPv4 addresses are
 * network-order hex metadata; seq/ack enable offline gap/dedup checks. */
static int m4_packet_line(char *out, size_t capacity, unsigned number,
                          unsigned real_len, const uint8_t *buf, unsigned shown,
                          struct m4_parsed *p)
{
    static const char digits[] = "0123456789abcdef";
    const char *leg = "other";
    unsigned i, kept;
    size_t used;
    int n;
    if (!out || !p || !buf || shown > real_len) return -1;
    m4_parse_frame(buf, shown, p);
    /* snaplen can truncate a valid frame, but wire length shorter than the
     * IP datagram is malformed. Do not label its prefix valid L7 data. */
    if (p->ip_end > real_len) {
        p->is_tcp = p->is_udp = 0;
        p->payload_offset = p->payload_length = p->payload_captured = 0;
    }
    if (p->is_tcp && (p->sport == 26012 || p->dport == 26012)) leg = "adas_26012";
    else if (p->is_tcp && (p->sport == 8080 || p->dport == 8080)) leg = "cardv_8080";
    else if (p->is_arp) leg = "arp";
    kept = p->payload_captured;
    n = snprintf(out, capacity,
        "pkt=%u len=%u src_ip=%08" PRIx32 " dst_ip=%08" PRIx32
        " sport=%u dport=%u seq=%" PRIu32 " ack=%" PRIu32
        " tcp_flags=%02x payload_len=%u captured=%u truncated=%u leg=%s payload_hex=",
        number, real_len, p->src_ip, p->dst_ip, (unsigned)p->sport,
        (unsigned)p->dport, p->tcp_seq, p->tcp_ack, (unsigned)p->tcp_flags,
        p->payload_length, kept, kept < p->payload_length ? 1U : 0U, leg);
    if (n < 0 || (size_t)n >= capacity) return -1;
    used = (size_t)n;
    if (capacity - used < (size_t)kept * 2 + 2) return -1;
    for (i = 0; i < kept; ++i) {
        unsigned byte = buf[p->payload_offset + i];
        out[used++] = digits[byte >> 4];
        out[used++] = digits[byte & 15U];
    }
    out[used++] = '\n';
    out[used] = 0;
    return (int)used;
}

static int m4_self_test(void)
{
    uint8_t frame[180];
    char line[M4_SNIFF_LINE_BYTES];
    struct m4_parsed p;
    memset(frame, 0, sizeof(frame));
    frame[12] = 8; frame[14] = 0x45;
    frame[17] = 45; frame[23] = 6;
    frame[34] = 0x65; frame[35] = 0x9c;
    frame[36] = 0xa8; frame[37] = 0xfd;
    frame[46] = 0x50; frame[47] = 0x18;
    memcpy(frame + 54, "hello", 5);
    if (m4_packet_line(line, sizeof(line), 1, 60, frame, 60, &p) < 0 ||
        !p.is_tcp || p.sport != 26012 || p.payload_offset != 54 ||
        p.payload_length != 5 || p.payload_captured != 5 ||
        !strstr(line, "payload_hex=68656c6c6f\n")) return 1;
    /* Padded ACK: Ethernet padding is NOT TCP payload. */
    frame[17] = 40;
    if (m4_packet_line(line, sizeof(line), 1, 60, frame, 60, &p) < 0 ||
        p.payload_length || p.payload_captured || !strstr(line, "payload_hex=\n")) return 1;
    frame[20] = 0x20;
    if (m4_packet_line(line, sizeof(line), 1, 60, frame, 60, &p) < 0 ||
        !p.is_frag || p.is_tcp || !strstr(line, "payload_hex=\n")) return 1;
    memset(frame, 0, sizeof(frame)); frame[12] = 8; frame[13] = 6;
    if (m4_packet_line(line, sizeof(line), 1, 42, frame, 42, &p) < 0 ||
        !p.is_arp || !strstr(line, "payload_hex=\n")) return 1;
    m4_parse_frame(NULL, 0, &p);
    m4_parse_frame(NULL, 0, NULL);
    if (p.payload_captured) return 1;
    return 0;
}

static void usage(void)
{
    puts("usage: c2m-m4-sniff --observe | --self-test | --help\n"
         "RAM-only passive observer; fixed interface usb0 (no overrides).\n"
         "Fixed bounds: 20 packets, 512B snaplen, 96B payload hex; 15 polls, 30s bound.\n"
         "Payload-only prefixes, explicit captured/truncated and seq/ack; NOT a full TCP stream.\n"
         "6144B record budget, <8192B stdout; duration may be shorter than 15 seconds.\n"
         "Receive-only AF_PACKET attach; never transmits and never writes files.\n"
         "Delivery is observer simulation, not production delivery.");
}

#ifdef __linux__
#include <arpa/inet.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <netpacket/packet.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static void on_signal(int sig) { (void)sig; stopping = 1; }

static int milliseconds(uint64_t *out)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) || t.tv_sec < 0 ||
        (uint64_t)t.tv_sec > UINT64_MAX / UINT64_C(1000)) return -1;
    *out = (uint64_t)t.tv_sec * UINT64_C(1000) + (uint64_t)t.tv_nsec / UINT64_C(1000000);
    return 0;
}

static int m4_observe(void)
{
    struct sigaction action;
    struct pollfd pfd;
    struct sockaddr_ll addr;
    uint8_t buf[M4_SNIFF_SNAPLEN];
    char line[M4_SNIFF_LINE_BYTES];
    uint64_t start, now, last, deadline;
    unsigned ifindex, packets = 0, polls = 0, records = 0, record_bytes = 0;
    unsigned adas = 0, cardv = 0, data = 0, payload_bytes = 0;
    const char *completion = "iface_unavailable";
    int fd = -1, rc = 0;
    memset(&action, 0, sizeof(action));
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL) ||
        milliseconds(&start) || start > UINT64_MAX - M4_SNIFF_MAX_MS) return 1;
    last = start;
    deadline = start + M4_SNIFF_MAX_MS;
    printf("m4_sniff=observer_v3\niface_fixed=usb0 packets_fixed=20 snaplen_fixed=512 "
           "payload_hex_fixed=96 polls_fixed=15 monotonic_bound_ms=30000 record_budget=6144\n"
           "delivery_sim=observer_simulation_not_production_delivery\n"
           "capture_scope=partial_payload_prefixes_not_reassembled_stream\n"
           "status_writes=0 transmit_bytes=0\n");
    if (fflush(stdout)) return 1;
    ifindex = if_nametoindex(M4_SNIFF_IFACE_FIXED);
    if (!ifindex) { puts("iface_present=0 socket_available=0"); goto done; }
    /* Protocol 0 queues NO traffic before bind. This avoids a pre-bind
     * ETH_P_ALL window that might retain frames from unrelated interfaces. */
    fd = socket(AF_PACKET, SOCK_RAW | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) { completion = "capture_unavailable"; goto done; }
    memset(&addr, 0, sizeof(addr));
    addr.sll_family = AF_PACKET;
    addr.sll_protocol = htons((uint16_t)ETH_P_ALL);
    addr.sll_ifindex = (int)ifindex;
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr))) {
        completion = "capture_unavailable"; goto done;
    }
    puts("iface_present=1 socket_available=1");
    if (fflush(stdout)) { rc = 1; completion = "error_write"; goto done; }
    memset(&pfd, 0, sizeof(pfd)); pfd.fd = fd; pfd.events = POLLIN;
    completion = "poll_limit_partial";
    while (packets < M4_SNIFF_MAX_PACKETS && polls < M4_SNIFF_MAX_POLLS) {
        struct m4_parsed p;
        struct sockaddr_ll peer;
        socklen_t peer_len = sizeof(peer);
        ssize_t got;
        unsigned shown;
        int pr, n;
        if (stopping) { rc = 1; completion = "interrupted_signal"; break; }
        if (milliseconds(&now) || now < last || now >= deadline) {
            rc = 1; completion = "error_monotonic_bound"; break;
        }
        last = now;
        ++polls;
        pr = poll(&pfd, 1, M4_SNIFF_POLL_MS);
        if (milliseconds(&now) || now < last || now >= deadline) {
            rc = 1; completion = "error_monotonic_bound"; break;
        }
        last = now;
        if (stopping) { rc = 1; completion = "interrupted_signal"; break; }
        if (pr < 0) {
            if (errno == EINTR) continue;
            rc = 1; completion = "error_poll"; break;
        }
        if (!pr) continue;
        if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) {
            rc = 1; completion = "error_poll"; break;
        }
        if (!(pfd.revents & POLLIN)) continue;
        memset(&peer, 0, sizeof(peer));
        got = recvfrom(fd, buf, sizeof(buf), MSG_TRUNC | MSG_DONTWAIT,
                       (struct sockaddr *)&peer, &peer_len);
        if (got < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) continue;
            rc = 1; completion = "error_recv"; break;
        }
        ++packets;
        if (peer_len != sizeof(peer) || peer.sll_ifindex != (int)ifindex) {
            rc = 1; completion = "error_interface_scope"; break;
        }
        shown = (unsigned)got < sizeof(buf) ? (unsigned)got : (unsigned)sizeof(buf);
        n = m4_packet_line(line, sizeof(line), packets, (unsigned)got, buf, shown, &p);
        if (n < 0) { rc = 1; completion = "error_format"; break; }
        if ((unsigned)n > M4_SNIFF_RECORD_BUDGET - record_bytes) {
            completion = "output_budget_partial"; break;
        }
        if (fputs(line, stdout) == EOF || fflush(stdout)) {
            rc = 1; completion = "error_write"; break;
        }
        record_bytes += (unsigned)n;
        ++records;
        if (p.is_tcp && (p.sport == 26012 || p.dport == 26012)) ++adas;
        if (p.is_tcp && (p.sport == 8080 || p.dport == 8080)) ++cardv;
        if (p.payload_length) ++data;
        payload_bytes += p.payload_captured;
        if (milliseconds(&now) || now < last || now >= deadline) {
            rc = 1; completion = "error_monotonic_bound"; break;
        }
        last = now;
    }
    if (!rc && packets >= M4_SNIFF_MAX_PACKETS) completion = "packet_limit_partial";
done:
    if (fd >= 0) close(fd);
    printf("summary packets=%u records=%u data_packets=%u adas_leg=%u cardv_leg=%u "
           "payload_bytes_captured=%u record_bytes=%u completion=%s "
           "delivery_sim=observer_simulation_not_production_delivery status_writes=0 transmit_bytes=0\n",
           packets, records, data, adas, cardv, payload_bytes, record_bytes, completion);
    if (fflush(stdout)) return 1;
    return rc;
}
#endif

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--help")) { usage(); return 0; }
    if (argc == 2 && !strcmp(argv[1], "--self-test")) {
        int result = m4_self_test();
        puts(result ? "M4 USB observe self-test: FAIL" : "M4 USB observe self-test: OK");
        return result ? 1 : 0;
    }
    if (argc == 2 && !strcmp(argv[1], "--observe")) {
#ifdef __linux__
        return m4_observe();
#else
        fputs("M4 USB observe unsupported on this platform\n", stderr);
        return 3;
#endif
    }
    usage(); return 2;
}

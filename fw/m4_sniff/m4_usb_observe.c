/* m4_usb_observe.c — RAM-only passive M4 RNDIS usb0 observer (L0/L1, no injection).
 *
 * Fixed interface usb0, no CLI overrides. CLI only --observe/--self-test/--help.
 * Receive-only AF_PACKET attach via bind(); NEVER transmits:
 *   no send/sendto/sendmsg/connect, no ioctl/setsockopt state change,
 *   no promiscuous toggle, no file writes, no status-file touch.
 * Finite: 20 packets, 512 snaplen, 96 payload hex bytes per packet, 15x1s poll,
 * 30s monotonic bound. Payload-only hex (headers parsed to metadata, skipped
 * in dump) so a normal TCP segment keeps ~96B of L7 data instead of ~10B.
 * Stdout summary only. Labels simulation explicitly.
 * Missing usb0/raw socket completes gracefully (CI/QEMU path), still finite.
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
#define M4_SNIFF_MAX_POLLS 15
#define M4_SNIFF_POLL_MS 1000
#define M4_SNIFF_MAX_MS UINT64_C(30000)

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
#else
/* Non-Linux builds support only --help/--self-test; no clocks needed. */
#endif

/* Pure frame parser: no sockets, no files, no clocks. Shared by self-test
 * and the Linux observer body. Reports header metadata plus the payload
 * slice [payload_offset, payload_offset+captured) within the shown bytes and
 * the real on-wire payload length (real_len - offset). Fragmented IP is
 * never parsed for ports/payload (first-fragment ambiguity). */
struct m4_parsed {
    uint16_t eth_type;
    uint8_t ip_proto;
    uint32_t src_ip;
    uint32_t dst_ip;
    uint16_t sport;
    uint16_t dport;
    uint8_t tcp_flags;
    unsigned payload_offset;
    int is_arp;
    int is_ip;
    int is_tcp;
    int is_udp;
    int is_frag;
};

static void m4_parse_frame(const uint8_t *b, unsigned len, struct m4_parsed *o)
{
    unsigned ip_off = 14, ihl, frag;
    memset(o, 0, sizeof(*o));
    if (!b || !o || len < 14) return;
    o->eth_type = (uint16_t)(((uint16_t)b[12] << 8) | b[13]);
    if (o->eth_type == 0x8100 || o->eth_type == 0x88A8) {
        /* Single 802.1Q tag: inner ethertype follows 4 tag bytes. */
        if (len < 18) return;
        o->eth_type = (uint16_t)(((uint16_t)b[16] << 8) | b[17]);
        ip_off = 18;
        if (len < ip_off) return;
    }
    if (o->eth_type == 0x0806) {
        if (len >= ip_off + 28) o->is_arp = 1;
        return;
    }
    if (o->eth_type != 0x0800 || len < ip_off + 20) return;
    if ((b[ip_off] >> 4) != 4) return;
    ihl = (unsigned)(b[ip_off] & 0x0F) * 4U;
    if (ihl < 20 || len < ip_off + ihl) return;
    frag = (unsigned)(((uint16_t)b[ip_off + 6] << 8) | b[ip_off + 7]);
    if (frag & 0x3FFFU) {
        /* Fragment offset != 0 or MF set: ports/payload ambiguous. */
        o->is_ip = 1;
        o->is_frag = 1;
        o->ip_proto = b[ip_off + 9];
        memcpy(&o->src_ip, b + ip_off + 12, 4);
        memcpy(&o->dst_ip, b + ip_off + 16, 4);
        return;
    }
    o->is_ip = 1;
    o->ip_proto = b[ip_off + 9];
    memcpy(&o->src_ip, b + ip_off + 12, 4);
    memcpy(&o->dst_ip, b + ip_off + 16, 4);
    if (o->ip_proto == 6) {
        unsigned thl, base = ip_off + ihl;
        if (len < base + 4) return;
        o->is_tcp = 1;
        o->sport = (uint16_t)(((uint16_t)b[base] << 8) | b[base + 1]);
        o->dport = (uint16_t)(((uint16_t)b[base + 2] << 8) | b[base + 3]);
        if (len < base + 14) return;
        thl = (unsigned)(b[base + 12] >> 4) * 4U;
        if (thl < 20 || len < base + thl) {
            /* Options truncated: ports known, payload unknown. */
            o->payload_offset = 0;
            return;
        }
        o->tcp_flags = b[base + 13];
        o->payload_offset = base + thl;
    } else if (o->ip_proto == 17) {
        unsigned base = ip_off + ihl;
        if (len < base + 4) return;
        o->is_udp = 1;
        o->sport = (uint16_t)(((uint16_t)b[base] << 8) | b[base + 1]);
        o->dport = (uint16_t)(((uint16_t)b[base + 2] << 8) | b[base + 3]);
        if (len < base + 8) {
            o->payload_offset = 0;
            return;
        }
        o->payload_offset = base + 8;
    }
}

static uint16_t m4_be16(const uint8_t *b) { return (uint16_t)(((uint16_t)b[0] << 8) | b[1]); }

static int m4_self_test(void)
{
    /* Frame layout: ETH(14) + IP(20) + TCP(20) + payload. */
    uint8_t frame[14 + 20 + 20 + 8];
    uint8_t opt[14 + 24 + 32 + 6];
    uint8_t udp[14 + 20 + 8 + 4];
    uint8_t arp[42];
    uint8_t trunc[10];
    struct m4_parsed p;
    static const uint8_t hello[5] = {0x68, 0x65, 0x6C, 0x6C, 0x6F};
    unsigned i;
    memset(frame, 0, sizeof(frame));
    /* dst/src MAC arbitrary, ethertype IPv4. */
    frame[12] = 0x08; frame[13] = 0x00;
    frame[14] = 0x45; frame[15] = 0x00;
    frame[16] = 0x00; frame[17] = 0x31; /* total length 49 */
    frame[23] = 6; /* TCP */
    /* src 192.168.32.123, dst 192.168.32.129 */
    frame[26] = 192; frame[27] = 168; frame[28] = 32; frame[29] = 123;
    frame[30] = 192; frame[31] = 168; frame[32] = 32; frame[33] = 129;
    /* sport 26012 (0x659C), dport 43261 (0xA8FD) */
    frame[34] = 0x65; frame[35] = 0x9C; frame[36] = 0xA8; frame[37] = 0xFD;
    frame[46] = 0x50; frame[47] = 0x18; /* data offset 5, PSH+ACK */
    memcpy(frame + 54, hello, sizeof(hello));
    m4_parse_frame(frame, sizeof(frame), &p);
    if (!p.is_ip || !p.is_tcp || p.eth_type != 0x0800 || p.ip_proto != 6) return 1;
    if (m4_be16(frame + 34) != 26012) return 1;
    if (p.sport != 26012 || p.dport != 43261 || p.tcp_flags != 0x18) return 1;
    if (p.payload_offset != 54) return 1;
    for (i = 0; i < sizeof(hello); ++i)
        if (frame[p.payload_offset + i] != hello[i]) return 1;
    /* cardv leg shape: sport 8080. */
    frame[34] = 0x1F; frame[35] = 0x90;
    m4_parse_frame(frame, sizeof(frame), &p);
    if (!p.is_tcp || p.sport != 8080 || p.payload_offset != 54) return 1;
    /* TCP options: data offset 8 (32B header), 6B payload. */
    memset(opt, 0, sizeof(opt));
    opt[12] = 0x08; opt[13] = 0x00;
    opt[14] = 0x45; opt[23] = 6;
    opt[34] = 0x65; opt[35] = 0x9C; opt[36] = 0xA8; opt[37] = 0xFD;
    opt[46] = 0x80; opt[47] = 0x10; /* data offset 8, ACK */
    memcpy(opt + 66, hello, 5);
    opt[71] = 0x21;
    m4_parse_frame(opt, sizeof(opt), &p);
    if (!p.is_tcp || p.payload_offset != 66) return 1;
    if (opt[p.payload_offset + 5] != 0x21) return 1;
    /* Pure ACK: TCP header only, no payload bytes present. */
    m4_parse_frame(opt, 66, &p);
    if (!p.is_tcp || p.payload_offset != 66) return 1;
    /* UDP with 4B payload. */
    memset(udp, 0, sizeof(udp));
    udp[12] = 0x08; udp[13] = 0x00;
    udp[14] = 0x45; udp[23] = 17;
    udp[34] = 0x04; udp[35] = 0xD2; udp[36] = 0x04; udp[37] = 0xD3;
    memcpy(udp + 42, hello, 4);
    m4_parse_frame(udp, sizeof(udp), &p);
    if (!p.is_udp || p.payload_offset != 42) return 1;
    /* Fragmented IP: ports/payload must NOT be claimed. */
    memset(frame, 0, 42);
    frame[12] = 0x08; frame[13] = 0x00;
    frame[14] = 0x45; frame[20] = 0x20; frame[21] = 0x01; /* MF + offset */
    frame[23] = 6;
    m4_parse_frame(frame, sizeof(frame), &p);
    if (!p.is_ip || !p.is_frag || p.is_tcp || p.payload_offset != 0) return 1;
    /* ARP shape. */
    memset(arp, 0, sizeof(arp));
    arp[12] = 0x08; arp[13] = 0x06;
    m4_parse_frame(arp, sizeof(arp), &p);
    if (!p.is_arp || p.is_ip || p.payload_offset != 0) return 1;
    /* Truncated frame must not crash and must not claim IP. */
    memset(trunc, 0, sizeof(trunc));
    m4_parse_frame(trunc, sizeof(trunc), &p);
    if (p.is_ip || p.is_tcp || p.is_arp) return 1;
    return 0;
}

static void usage(void)
{
    puts("usage: c2m-m4-sniff --observe | --self-test | --help\n"
         "RAM-only passive observer; fixed interface usb0 (no overrides).\n"
         "Fixed bounds: 20 packets, 512B snaplen, 96B payload hex, 15x1s poll, 30s bound.\n"
         "Payload-only hex: headers become metadata, dump keeps L7 bytes.\n"
         "Receive-only AF_PACKET attach; never transmits and never writes files.\n"
         "Stdout summary only; delivery is observer simulation, not production delivery.");
}

#ifdef __linux__
static void print_payload_hex(const uint8_t *b, unsigned offset, unsigned shown)
{
    static const char digits[] = "0123456789abcdef";
    unsigned avail, n, i;
    if (offset >= shown) return;
    avail = shown - offset;
    n = avail < M4_SNIFF_PAYLOAD_HEX_BYTES ? avail : M4_SNIFF_PAYLOAD_HEX_BYTES;
    for (i = 0; i < n; ++i) {
        putchar(digits[(b[offset + i] >> 4) & 0x0F]);
        putchar(digits[b[offset + i] & 0x0F]);
    }
}

/* Finite RAM-only observer: fixed usb0, bounded polls/packets/bytes/clock,
 * stdout only. No transmit, no file writes, no status file. Callers must
 * still apply an external timeout. */
static int m4_observe(void)
{
    struct sigaction action;
    struct pollfd pfd;
    uint8_t buf[M4_SNIFF_SNAPLEN];
    uint64_t start_ms = 0, now = 0, last_ms = 0, deadline = 0, after_ms = 0;
    unsigned ifindex, packets = 0, polls = 0;
    unsigned adas_leg = 0, cardv_leg = 0, arp_count = 0, other = 0;
    unsigned data_packets = 0;
    uint64_t payload_bytes_captured = 0;
    int fd = -1;
    const char *completion = "complete";
    int rc = 0;
    memset(&action, 0, sizeof(action));
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL)) return 1;
    if (milliseconds(&start_ms)) return 1;
    if (start_ms > UINT64_MAX - M4_SNIFF_MAX_MS) return 1;
    deadline = start_ms + M4_SNIFF_MAX_MS;
    printf("m4_sniff=observer_v2\n");
    printf("iface_fixed=%s packets_fixed=%d snaplen_fixed=%d payload_hex_fixed=%d polls_fixed=%d monotonic_bound_ms=%llu\n",
           M4_SNIFF_IFACE_FIXED, M4_SNIFF_MAX_PACKETS, M4_SNIFF_SNAPLEN,
           M4_SNIFF_PAYLOAD_HEX_BYTES, M4_SNIFF_MAX_POLLS, (unsigned long long)M4_SNIFF_MAX_MS);
    printf("delivery_sim=observer_simulation_not_production_delivery\n");
    printf("status_writes=0 transmit_bytes=0\n");
    ifindex = if_nametoindex(M4_SNIFF_IFACE_FIXED);
    if (ifindex == 0) {
        printf("iface_present=0 socket_available=0\n");
        printf("summary packets=0 data_packets=0 adas_leg=0 cardv_leg=0 arp=0 other=0 completion=iface_unavailable "
               "delivery_sim=observer_simulation_not_production_delivery status_writes=0 transmit_bytes=0\n");
        if (fflush(stdout)) return 1;
        return 0;
    }
    printf("iface_present=1\n");
    fd = socket(AF_PACKET, SOCK_RAW, htons((uint16_t)ETH_P_ALL));
    if (fd < 0) {
        printf("iface_present=1 socket_available=0 reason=%d\n", errno);
        printf("summary packets=0 data_packets=0 adas_leg=0 cardv_leg=0 arp=0 other=0 completion=capture_unavailable "
               "delivery_sim=observer_simulation_not_production_delivery status_writes=0 transmit_bytes=0\n");
        if (fflush(stdout)) return 1;
        return 0;
    }
    {
        struct sockaddr_ll addr;
        memset(&addr, 0, sizeof(addr));
        addr.sll_family = AF_PACKET;
        addr.sll_protocol = htons((uint16_t)ETH_P_ALL);
        addr.sll_ifindex = (int)ifindex;
        /* Receive-only attach to the verified interface. No transmit. */
        if (bind(fd, (struct sockaddr *)&addr, sizeof(addr))) {
            int e = errno;
            close(fd);
            printf("iface_present=1 socket_available=1 reason=%d\n", e);
            printf("summary packets=0 data_packets=0 adas_leg=0 cardv_leg=0 arp=0 other=0 completion=capture_unavailable "
                   "delivery_sim=observer_simulation_not_production_delivery status_writes=0 transmit_bytes=0\n");
            if (fflush(stdout)) return 1;
            return 0;
        }
    }
    printf("iface_present=1 socket_available=1\n");
    if (fflush(stdout)) { close(fd); return 1; }
    last_ms = start_ms;
    memset(&pfd, 0, sizeof(pfd));
    pfd.fd = fd;
    pfd.events = POLLIN;
    while (packets < M4_SNIFF_MAX_PACKETS && polls < M4_SNIFF_MAX_POLLS) {
        struct m4_parsed p;
        ssize_t got;
        unsigned real_len, shown, payload_len = 0, captured = 0;
        const char *leg;
        int pr;
        if (stopping) { completion = "interrupted_signal"; rc = 1; break; }
        if (milliseconds(&now)) { completion = "error_clock"; rc = 1; break; }
        if (now < last_ms) { completion = "error_monotonic_regression"; rc = 1; break; }
        if (now > deadline) { completion = "error_monotonic_bound"; rc = 1; break; }
        last_ms = now;
        pr = poll(&pfd, 1, M4_SNIFF_POLL_MS);
        if (milliseconds(&after_ms)) { completion = "error_clock"; rc = 1; break; }
        if (after_ms < now || after_ms < last_ms) { completion = "error_monotonic_regression"; rc = 1; break; }
        if (after_ms > deadline) { completion = "error_monotonic_bound"; rc = 1; break; }
        last_ms = after_ms;
        if (stopping) { completion = "interrupted_signal"; rc = 1; break; }
        if (pr < 0) {
            if (errno == EINTR) continue;
            completion = "error_poll"; rc = 1; break;
        }
        ++polls;
        if (pr == 0) continue;
        /* MSG_TRUNC reports the real on-wire length even when truncated. */
        got = recvfrom(fd, buf, sizeof(buf), MSG_TRUNC, NULL, NULL);
        if (got < 0) {
            if (errno == EINTR) continue;
            completion = "error_recv"; rc = 1; break;
        }
        real_len = (unsigned)got;
        shown = real_len < sizeof(buf) ? real_len : (unsigned)sizeof(buf);
        m4_parse_frame(buf, shown, &p);
        if (p.is_arp) { ++arp_count; leg = "non_ip_arp"; }
        else if (p.is_tcp && (p.sport == 26012 || p.dport == 26012)) { ++adas_leg; leg = "adas_26012"; }
        else if (p.is_tcp && (p.sport == 8080 || p.dport == 8080)) { ++cardv_leg; leg = "cardv_8080"; }
        else { ++other; leg = p.is_ip ? "other_ip" : "non_ip"; }
        if ((p.is_tcp || p.is_udp) && !p.is_frag && p.payload_offset > 0) {
            payload_len = real_len > p.payload_offset ? real_len - p.payload_offset : 0;
            captured = shown > p.payload_offset ? shown - p.payload_offset : 0;
            if (captured > M4_SNIFF_PAYLOAD_HEX_BYTES) captured = M4_SNIFF_PAYLOAD_HEX_BYTES;
            if (payload_len > 0) {
                ++data_packets;
                payload_bytes_captured += (uint64_t)captured;
            }
        }
        ++packets;
        printf("pkt=%u len=%u eth_type=%04x ip_proto=%u sport=%u dport=%u tcp_flags=%02x payload_len=%u leg=%s payload_hex=",
               packets, real_len, p.eth_type, p.ip_proto, p.sport, p.dport, p.tcp_flags, payload_len, leg);
        print_payload_hex(buf, p.payload_offset, shown);
        printf(" delivery_sim=observer_simulation_not_production_delivery\n");
        if (fflush(stdout)) { completion = "error_write"; rc = 1; break; }
        if (milliseconds(&after_ms)) { completion = "error_clock"; rc = 1; break; }
        if (after_ms < last_ms) { completion = "error_monotonic_regression"; rc = 1; break; }
        if (after_ms > deadline) { completion = "error_monotonic_bound"; rc = 1; break; }
        last_ms = after_ms;
    }
    close(fd);
    if (!rc && packets >= M4_SNIFF_MAX_PACKETS) completion = "complete";
    else if (!rc && polls >= M4_SNIFF_MAX_POLLS) completion = "timeout_empty_or_partial";
    printf("summary packets=%u data_packets=%u adas_leg=%u cardv_leg=%u arp=%u other=%u payload_bytes_captured=%llu completion=%s "
           "delivery_sim=observer_simulation_not_production_delivery status_writes=0 transmit_bytes=0\n",
           packets, data_packets, adas_leg, cardv_leg, arp_count, other,
           (unsigned long long)payload_bytes_captured, completion);
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
    usage();
    return 2;
}

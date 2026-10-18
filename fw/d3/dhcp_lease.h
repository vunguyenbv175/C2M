#ifndef C2M_D3_DHCP_LEASE_H
#define C2M_D3_DHCP_LEASE_H

#include <stddef.h>
#include <stdint.h>

/* Portable, pure DHCPv4 lease parser/validator for a D3 station interface.
 *
 * This is PREPARATORY, UNINTEGRATED code. It does not talk to the Wi-Fi
 * controller, does not start a DHCP client, does not touch routes, nvconf,
 * DNS configuration or any file/socket/device, and has no build/boot hook. It
 * turns already-received lease text into fixed numeric fields and rejects the
 * unsafe or inconsistent cases.
 *
 * Scope and guarantees:
 *  - Pure and allocation-free. No globals, timers, threads, files, sockets,
 *    subprocess, shell, string interpolation, logging or stdout. Secrets are
 *    not accepted, produced or stored.
 *  - Addresses are canonical dotted-decimal only: exactly four 1-3 digit
 *    octets, each 0..255, no leading zero (so "192.168.050.2" is ambiguous and
 *    rejected), no surrounding whitespace/control bytes and no shell
 *    metacharacters.
 *  - The STA subnet netmask must be contiguous and give a prefix length of
 *    /1..30. /0, /31 and /32 are rejected for an ordinary STA.
 *  - The whole lease subnet range must not overlap the forbidden ranges
 *    0.0.0.0/8, 127.0.0.0/8, 169.254.0.0/16, 224.0.0.0/4 or 240.0.0.0/4.
 *    This is decided by interval intersection, not by endpoints alone: a /1
 *    whose span crosses 127.0.0.0/8 is rejected even though the host is 10.x.
 *    Ordinary private/public ranges such as 10/8, 100.64/10 (CGNAT), 172.16/12
 *    and 192.168/16 are unaffected and stay valid.
 *  - Loopback, multicast, unspecified/this-network, link-local, reserved and
 *    broadcast addresses are rejected as a host, gateway or DNS address. The
 *    lease must also not be the subnet network or broadcast address, and a DNS
 *    server must not be the lease subnet network or broadcast address.
 *  - An optional single router must be a canonical unicast host that is
 *    on-link and is not the network, broadcast or lease address.
 *  - Up to three optional DNS servers must be canonical unicast addresses.
 *    Duplicate servers are permitted; no de-duplication is performed.
 *  - The lease time must be 60..604800 seconds.
 *  - The lease subnet must not intersect any of up to four protected CIDRs
 *    (for example the stock AP and the M4/USB networks). Intersection is exact
 *    IPv4 range overlap, not string equality. Each protected subnet's mask
 *    must be contiguous, and its address is masked to that network before the
 *    overlap test, so a caller cannot smuggle host bits past the check. A
 *    protected /0 is allowed and protects the whole IPv4 space.
 *  - A validated lease is an ADDRESS-ASSIGNMENT intent only. C2M_DHCP_OK is
 *    never evidence of a route or of Internet access, and a router-less
 *    (all-zero / absent router) lease is valid.
 *
 * Input copying contract: every text argument must be a NUL-terminated,
 * caller-owned copy. This API deliberately has no explicit length parameter
 * (and none is in scope); a caller that sourced text from a network or device
 * must first copy it into a bounded buffer and NUL-terminate it. The parser
 * stops at the first NUL and never reads past it.
 *
 * Failures are reported as the enum below and via fixed, input-free reason
 * tokens from c2m_dhcp_result_name(); no caller input is ever echoed back.
 */

#define C2M_DHCP_MAX_DNS 3u
#define C2M_DHCP_MAX_PROTECTED_SUBNETS 4u
#define C2M_DHCP_MIN_PREFIX 1u
#define C2M_DHCP_MAX_PREFIX 30u
#define C2M_DHCP_MIN_LEASE_SECONDS 60u
#define C2M_DHCP_MAX_LEASE_SECONDS 604800u

enum c2m_dhcp_result {
    C2M_DHCP_OK = 0,
    C2M_DHCP_ERR_ARGUMENT = 1,             /* NULL pointer or impossible count */
    C2M_DHCP_ERR_UNSAFE_INPUT = 2,         /* whitespace/control/shell metacharacter */
    C2M_DHCP_ERR_IP_SYNTAX = 3,            /* not canonical dotted-decimal shape */
    C2M_DHCP_ERR_IP_LEADING_ZERO = 4,      /* octet like 05/007 is ambiguous */
    C2M_DHCP_ERR_IP_RANGE = 5,             /* loopback/multicast/unspecified/etc. */
    C2M_DHCP_ERR_NETMASK_SYNTAX = 6,
    C2M_DHCP_ERR_NETMASK_CONTIGUITY = 7,   /* ones are not a contiguous MSB run */
    C2M_DHCP_ERR_PREFIX_BOUNDS = 8,        /* /0, /31 or /32 for an ordinary STA */
    C2M_DHCP_ERR_ADDRESS_NETWORK = 9,      /* lease equals subnet network */
    C2M_DHCP_ERR_ADDRESS_BROADCAST = 10,   /* lease equals subnet broadcast */
    C2M_DHCP_ERR_GATEWAY_SYNTAX = 11,
    C2M_DHCP_ERR_GATEWAY_RANGE = 12,
    C2M_DHCP_ERR_GATEWAY_OFFLINK = 13,     /* outside the lease subnet */
    C2M_DHCP_ERR_GATEWAY_NETWORK = 14,
    C2M_DHCP_ERR_GATEWAY_BROADCAST = 15,
    C2M_DHCP_ERR_GATEWAY_EQUALS_LEASE = 16,
    C2M_DHCP_ERR_DNS_COUNT = 17,           /* more than C2M_DHCP_MAX_DNS */
    C2M_DHCP_ERR_DNS_SYNTAX = 18,
    C2M_DHCP_ERR_DNS_RANGE = 19,
    C2M_DHCP_ERR_LEASE_SECONDS = 20,       /* outside 60..604800 */
    C2M_DHCP_ERR_SUBNET_SYNTAX = 21,       /* malformed "a.b.c.d/prefix" CIDR */
    C2M_DHCP_ERR_SUBNET_PREFIX = 22,       /* CIDR prefix not 0..32 */
    C2M_DHCP_ERR_PROTECTED_COUNT = 23,     /* more than C2M_DHCP_MAX_PROTECTED_SUBNETS */
    C2M_DHCP_ERR_PROTECTED_OVERLAP = 24,   /* lease subnet intersects a protected CIDR */
    C2M_DHCP_ERR_PROTECTED_SUBNET = 25,    /* protected subnet netmask is not contiguous */
    C2M_DHCP_ERR_SUBNET_RANGE = 26         /* lease subnet intersects a forbidden range */
};

/* A protected subnet as a normalized network address plus contiguous mask.
 * The address part of a CIDR is masked to its network, so "192.168.1.1/24"
 * and "192.168.1.0/24" describe the same protected subnet. The struct form
 * accepts host bits in network too (they are masked off before use), but a
 * noncontiguous netmask is rejected with C2M_DHCP_ERR_PROTECTED_SUBNET. */
struct c2m_dhcp_subnet {
    uint32_t network;
    uint32_t netmask;
};

/* A validated lease. Numeric fields only; there is deliberately no Internet,
 * route, interface-name or credential field. */
struct c2m_dhcp_lease {
    uint32_t address;                 /* lease host address, host byte order (a<<24|b<<16|c<<8|d) */
    uint32_t netmask;                 /* contiguous */
    uint32_t network;                 /* address & netmask */
    uint32_t broadcast;               /* network | ~netmask */
    unsigned prefix;                  /* 1..30 */
    int has_gateway;                  /* 0 or 1; a zero router is valid */
    uint32_t gateway;                 /* 0 when has_gateway == 0 */
    unsigned dns_count;               /* 0..C2M_DHCP_MAX_DNS */
    uint32_t dns[C2M_DHCP_MAX_DNS];
    uint32_t lease_seconds;           /* 60..604800 */
};

/* Parse one canonical dotted-decimal IPv4 address. On failure *out is left
 * unchanged. */
enum c2m_dhcp_result c2m_dhcp_parse_ipv4(const char *text, uint32_t *out);

/* Parse "a.b.c.d/prefix" (prefix 0..32) into a normalized subnet. On failure
 * *out is left unchanged. */
enum c2m_dhcp_result c2m_dhcp_parse_subnet(const char *cidr,
                                           struct c2m_dhcp_subnet *out);

/* Validate a lease. address and netmask are required canonical dotted-decimal
 * strings. gateway may be NULL or "" for no router. dns may be NULL only when
 * dns_count is 0. protected_subnets may be NULL only when protected_count is 0.
 * On failure *out is cleared to all-zero bytes; on success it is fully filled.
 */
enum c2m_dhcp_result c2m_dhcp_validate_lease(
    const char *address,
    const char *netmask,
    const char *gateway,
    const char *const *dns,
    unsigned dns_count,
    uint32_t lease_seconds,
    const struct c2m_dhcp_subnet *protected_subnets,
    unsigned protected_count,
    struct c2m_dhcp_lease *out);

/* 1 when the lease carries a router, else 0. This says nothing about whether
 * that router is reachable or whether Internet access exists. */
int c2m_dhcp_lease_has_router(const struct c2m_dhcp_lease *lease);

/* Fixed ASCII token for a result (for example "ok", "unsafe_input",
 * "protected_overlap"). Unknown values return "unknown". Never echoes input. */
const char *c2m_dhcp_result_name(enum c2m_dhcp_result result);

#endif

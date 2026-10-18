/* Portable, pure DHCPv4 lease parser/validator. See dhcp_lease.h for scope.
 * No I/O, shell, interpolation, logging or stdout; secrets are never present.
 */

#include "dhcp_lease.h"

#include <string.h>

/* Whitespace, control bytes and shell/quoting metacharacters are never part of
 * a valid numeric field. Rejecting them here is what keeps a later consumer
 * from having to guess whether text was meant as data or as syntax. */
static int unsafe_char(unsigned char c)
{
    if (c <= 0x20u || c >= 0x7fu)
        return 1;
    switch (c) {
    case '"': case '\'': case '`': case '$': case '\\':
    case ';': case '|': case '&': case '<': case '>':
    case '(': case ')': case '{': case '}': case '[': case ']':
    case '*': case '?': case '!': case '#': case '%':
    case '^': case '=': case '+': case ',': case '~':
        return 1;
    default:
        return 0;
    }
}

/* True for addresses that must never be a lease, router or DNS host. */
static int forbidden_address(uint32_t value)
{
    if ((value & UINT32_C(0xff000000)) == 0u)       /* 0.0.0.0/8 unspecified */
        return 1;
    if ((value & UINT32_C(0xff000000)) == UINT32_C(0x7f000000)) /* loopback */
        return 1;
    if ((value & UINT32_C(0xffff0000)) == UINT32_C(0xa9fe0000)) /* link-local */
        return 1;
    if ((value & UINT32_C(0xf0000000)) == UINT32_C(0xe0000000)) /* multicast */
        return 1;
    if ((value & UINT32_C(0xf0000000)) == UINT32_C(0xf0000000)) /* reserved+bcast */
        return 1;
    return 0;
}

/* Closed-interval overlap. Both intervals are inclusive [first,last]. */
static int range_overlap(uint32_t first_a, uint32_t last_a,
                         uint32_t first_b, uint32_t last_b)
{
    return first_a <= last_b && first_b <= last_a;
}

/* True when the lease subnet [network,broadcast] overlaps any forbidden CIDR.
 * This is a range test rather than an endpoint test, so a broad mask that
 * merely crosses a forbidden range (for example a /1 spanning 127/8) is
 * caught even when its host and broadcast happen to be legal. */
static int subnet_hits_forbidden(uint32_t network, uint32_t broadcast)
{
    if (range_overlap(network, broadcast,
                      UINT32_C(0x00000000), UINT32_C(0x00ffffff)))   /* 0/8 */
        return 1;
    if (range_overlap(network, broadcast,
                      UINT32_C(0x7f000000), UINT32_C(0x7fffffff)))   /* 127/8 */
        return 1;
    if (range_overlap(network, broadcast,
                      UINT32_C(0xa9fe0000), UINT32_C(0xa9feffff)))   /* 169.254/16 */
        return 1;
    if (range_overlap(network, broadcast,
                      UINT32_C(0xe0000000), UINT32_C(0xefffffff)))   /* 224/4 */
        return 1;
    if (range_overlap(network, broadcast,
                      UINT32_C(0xf0000000), UINT32_C(0xffffffff)))   /* 240/4 */
        return 1;
    return 0;
}

static int mask_is_contiguous(uint32_t mask)
{
    uint32_t inverted = ~mask;
    return (inverted & (inverted + UINT32_C(1))) == 0u;
}

static unsigned mask_prefix(uint32_t mask)
{
    unsigned prefix = 0;
    while ((mask & UINT32_C(0x80000000)) != 0u) {
        ++prefix;
        mask <<= 1;
    }
    return prefix;
}

static void clear_lease(struct c2m_dhcp_lease *out)
{
    if (out != NULL)
        memset(out, 0, sizeof(*out));
}

enum c2m_dhcp_result c2m_dhcp_parse_ipv4(const char *text, uint32_t *out)
{
    uint32_t value = 0;
    unsigned octet = 0, digits = 0, index = 0;
    const char *p;

    if (text == NULL || out == NULL)
        return C2M_DHCP_ERR_ARGUMENT;

    for (p = text; ; ++p) {
        unsigned char c = (unsigned char)*p;
        if (c == '\0') {
            if (digits == 0)
                return C2M_DHCP_ERR_IP_SYNTAX;
            break;
        }
        if (unsafe_char(c))
            return C2M_DHCP_ERR_UNSAFE_INPUT;
        if (c == '.') {
            if (digits == 0 || index >= 3)
                return C2M_DHCP_ERR_IP_SYNTAX;
            value = (value << 8) | octet;
            octet = 0;
            digits = 0;
            ++index;
            continue;
        }
        if (c < '0' || c > '9')
            return C2M_DHCP_ERR_IP_SYNTAX;
        if (digits == 0 && c == '0' && p[1] >= '0' && p[1] <= '9')
            return C2M_DHCP_ERR_IP_LEADING_ZERO;
        if (digits >= 3)
            return C2M_DHCP_ERR_IP_SYNTAX;
        octet = octet * 10u + (unsigned)(c - '0');
        ++digits;
        if (octet > 255u)
            return C2M_DHCP_ERR_IP_SYNTAX;
    }

    if (index != 3)
        return C2M_DHCP_ERR_IP_SYNTAX;
    *out = (value << 8) | octet;
    return C2M_DHCP_OK;
}

enum c2m_dhcp_result c2m_dhcp_parse_subnet(const char *cidr,
                                           struct c2m_dhcp_subnet *out)
{
    char address[16];
    const char *slash, *q;
    size_t length;
    unsigned prefix = 0, digits = 0;
    uint32_t addr = 0, mask;
    enum c2m_dhcp_result result;

    if (cidr == NULL || out == NULL)
        return C2M_DHCP_ERR_ARGUMENT;

    slash = strchr(cidr, '/');
    if (slash == NULL)
        return C2M_DHCP_ERR_SUBNET_SYNTAX;
    length = (size_t)(slash - cidr);
    if (length == 0 || length >= sizeof(address))
        return C2M_DHCP_ERR_SUBNET_SYNTAX;
    memcpy(address, cidr, length);
    address[length] = '\0';

    result = c2m_dhcp_parse_ipv4(address, &addr);
    if (result == C2M_DHCP_ERR_UNSAFE_INPUT)
        return C2M_DHCP_ERR_UNSAFE_INPUT;
    if (result != C2M_DHCP_OK)
        return C2M_DHCP_ERR_SUBNET_SYNTAX;

    q = slash + 1;
    if (*q == '\0')
        return C2M_DHCP_ERR_SUBNET_SYNTAX;
    for (; *q != '\0'; ++q) {
        unsigned char c = (unsigned char)*q;
        if (unsafe_char(c))
            return C2M_DHCP_ERR_UNSAFE_INPUT;
        if (c < '0' || c > '9')
            return C2M_DHCP_ERR_SUBNET_SYNTAX;
        if (digits == 0 && c == '0' && q[1] >= '0' && q[1] <= '9')
            return C2M_DHCP_ERR_SUBNET_SYNTAX;
        if (digits >= 2)
            return C2M_DHCP_ERR_SUBNET_PREFIX;
        prefix = prefix * 10u + (unsigned)(c - '0');
        if (prefix > 32u)
            return C2M_DHCP_ERR_SUBNET_PREFIX;
        ++digits;
    }

    mask = prefix == 0u ? 0u
                        : (uint32_t)(UINT32_C(0xffffffff) << (32u - prefix));
    out->network = addr & mask;
    out->netmask = mask;
    return C2M_DHCP_OK;
}

static int subnets_overlap(uint32_t network_a, uint32_t netmask_a,
                           uint32_t network_b, uint32_t netmask_b)
{
    return range_overlap(network_a, network_a | ~netmask_a,
                         network_b, network_b | ~netmask_b);
}

enum c2m_dhcp_result c2m_dhcp_validate_lease(
    const char *address,
    const char *netmask,
    const char *gateway,
    const char *const *dns,
    unsigned dns_count,
    uint32_t lease_seconds,
    const struct c2m_dhcp_subnet *protected_subnets,
    unsigned protected_count,
    struct c2m_dhcp_lease *out)
{
    struct c2m_dhcp_lease lease;
    uint32_t addr = 0, mask = 0, network, broadcast;
    unsigned prefix, i;
    enum c2m_dhcp_result result;

    if (out == NULL)
        return C2M_DHCP_ERR_ARGUMENT;
    clear_lease(out);
    memset(&lease, 0, sizeof(lease));

    if (protected_count > C2M_DHCP_MAX_PROTECTED_SUBNETS)
        return C2M_DHCP_ERR_PROTECTED_COUNT;
    if (protected_count > 0u && protected_subnets == NULL)
        return C2M_DHCP_ERR_ARGUMENT;
    if (address == NULL || netmask == NULL)
        return C2M_DHCP_ERR_ARGUMENT;

    result = c2m_dhcp_parse_ipv4(address, &addr);
    if (result != C2M_DHCP_OK)
        return result;
    if (forbidden_address(addr))
        return C2M_DHCP_ERR_IP_RANGE;

    result = c2m_dhcp_parse_ipv4(netmask, &mask);
    if (result == C2M_DHCP_ERR_UNSAFE_INPUT)
        return C2M_DHCP_ERR_UNSAFE_INPUT;
    if (result != C2M_DHCP_OK)
        return C2M_DHCP_ERR_NETMASK_SYNTAX;
    if (!mask_is_contiguous(mask))
        return C2M_DHCP_ERR_NETMASK_CONTIGUITY;
    prefix = mask_prefix(mask);
    if (prefix < C2M_DHCP_MIN_PREFIX || prefix > C2M_DHCP_MAX_PREFIX)
        return C2M_DHCP_ERR_PREFIX_BOUNDS;

    network = addr & mask;
    broadcast = network | ~mask;
    if (addr == network)
        return C2M_DHCP_ERR_ADDRESS_NETWORK;
    if (addr == broadcast)
        return C2M_DHCP_ERR_ADDRESS_BROADCAST;
    if (subnet_hits_forbidden(network, broadcast))
        return C2M_DHCP_ERR_SUBNET_RANGE;

    lease.address = addr;
    lease.netmask = mask;
    lease.network = network;
    lease.broadcast = broadcast;
    lease.prefix = prefix;
    lease.has_gateway = 0;
    lease.gateway = 0;

    if (gateway != NULL && gateway[0] != '\0') {
        uint32_t router = 0;
        result = c2m_dhcp_parse_ipv4(gateway, &router);
        if (result == C2M_DHCP_ERR_UNSAFE_INPUT)
            return C2M_DHCP_ERR_UNSAFE_INPUT;
        if (result != C2M_DHCP_OK)
            return C2M_DHCP_ERR_GATEWAY_SYNTAX;
        if (forbidden_address(router))
            return C2M_DHCP_ERR_GATEWAY_RANGE;
        if (router == addr)
            return C2M_DHCP_ERR_GATEWAY_EQUALS_LEASE;
        if (router == network)
            return C2M_DHCP_ERR_GATEWAY_NETWORK;
        if (router == broadcast)
            return C2M_DHCP_ERR_GATEWAY_BROADCAST;
        if ((router & mask) != network)
            return C2M_DHCP_ERR_GATEWAY_OFFLINK;
        lease.has_gateway = 1;
        lease.gateway = router;
    }

    if (dns_count > C2M_DHCP_MAX_DNS)
        return C2M_DHCP_ERR_DNS_COUNT;
    if (dns_count > 0u && dns == NULL)
        return C2M_DHCP_ERR_ARGUMENT;
    for (i = 0; i < dns_count; ++i) {
        uint32_t server = 0;
        if (dns[i] == NULL)
            return C2M_DHCP_ERR_DNS_SYNTAX;
        result = c2m_dhcp_parse_ipv4(dns[i], &server);
        if (result == C2M_DHCP_ERR_UNSAFE_INPUT)
            return C2M_DHCP_ERR_UNSAFE_INPUT;
        if (result != C2M_DHCP_OK)
            return C2M_DHCP_ERR_DNS_SYNTAX;
        if (forbidden_address(server))
            return C2M_DHCP_ERR_DNS_RANGE;
        if (server == network || server == broadcast)
            return C2M_DHCP_ERR_DNS_RANGE;
        lease.dns[i] = server;
    }
    lease.dns_count = dns_count;

    if (lease_seconds < C2M_DHCP_MIN_LEASE_SECONDS ||
        lease_seconds > C2M_DHCP_MAX_LEASE_SECONDS)
        return C2M_DHCP_ERR_LEASE_SECONDS;
    lease.lease_seconds = lease_seconds;

    for (i = 0; i < protected_count; ++i) {
        uint32_t protected_network = protected_subnets[i].network;
        uint32_t protected_mask = protected_subnets[i].netmask;
        if (!mask_is_contiguous(protected_mask))
            return C2M_DHCP_ERR_PROTECTED_SUBNET;
        protected_network &= protected_mask;
        if (subnets_overlap(network, mask, protected_network, protected_mask))
            return C2M_DHCP_ERR_PROTECTED_OVERLAP;
    }

    *out = lease;
    return C2M_DHCP_OK;
}

int c2m_dhcp_lease_has_router(const struct c2m_dhcp_lease *lease)
{
    return lease != NULL && lease->has_gateway != 0;
}

const char *c2m_dhcp_result_name(enum c2m_dhcp_result result)
{
    switch (result) {
    case C2M_DHCP_OK: return "ok";
    case C2M_DHCP_ERR_ARGUMENT: return "argument";
    case C2M_DHCP_ERR_UNSAFE_INPUT: return "unsafe_input";
    case C2M_DHCP_ERR_IP_SYNTAX: return "ip_syntax";
    case C2M_DHCP_ERR_IP_LEADING_ZERO: return "ip_leading_zero";
    case C2M_DHCP_ERR_IP_RANGE: return "ip_range";
    case C2M_DHCP_ERR_NETMASK_SYNTAX: return "netmask_syntax";
    case C2M_DHCP_ERR_NETMASK_CONTIGUITY: return "netmask_contiguity";
    case C2M_DHCP_ERR_PREFIX_BOUNDS: return "prefix_bounds";
    case C2M_DHCP_ERR_ADDRESS_NETWORK: return "address_network";
    case C2M_DHCP_ERR_ADDRESS_BROADCAST: return "address_broadcast";
    case C2M_DHCP_ERR_GATEWAY_SYNTAX: return "gateway_syntax";
    case C2M_DHCP_ERR_GATEWAY_RANGE: return "gateway_range";
    case C2M_DHCP_ERR_GATEWAY_OFFLINK: return "gateway_offlink";
    case C2M_DHCP_ERR_GATEWAY_NETWORK: return "gateway_network";
    case C2M_DHCP_ERR_GATEWAY_BROADCAST: return "gateway_broadcast";
    case C2M_DHCP_ERR_GATEWAY_EQUALS_LEASE: return "gateway_equals_lease";
    case C2M_DHCP_ERR_DNS_COUNT: return "dns_count";
    case C2M_DHCP_ERR_DNS_SYNTAX: return "dns_syntax";
    case C2M_DHCP_ERR_DNS_RANGE: return "dns_range";
    case C2M_DHCP_ERR_LEASE_SECONDS: return "lease_seconds";
    case C2M_DHCP_ERR_SUBNET_SYNTAX: return "subnet_syntax";
    case C2M_DHCP_ERR_SUBNET_PREFIX: return "subnet_prefix";
    case C2M_DHCP_ERR_PROTECTED_COUNT: return "protected_count";
    case C2M_DHCP_ERR_PROTECTED_OVERLAP: return "protected_overlap";
    case C2M_DHCP_ERR_PROTECTED_SUBNET: return "protected_subnet";
    case C2M_DHCP_ERR_SUBNET_RANGE: return "subnet_range";
    default: return "unknown";
    }
}

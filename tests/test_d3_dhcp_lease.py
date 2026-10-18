#!/usr/bin/env python3
"""Synthetic host tests for the D3 pure DHCPv4 lease validator.

Run: python tests/test_d3_dhcp_lease.py
Requires host GCC (or CC). Compiles the production source only, into an
approved temporary directory; no firmware, Wi-Fi device, socket, route, DHCP
client, camera or deployment is touched. The protected AP/M4/USB subnets are
supplied as parameters (env-overridable) rather than hard-coded.
"""
from __future__ import annotations

import ctypes
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "fw" / "d3" / "dhcp_lease.c"
HEADER = ROOT / "fw" / "d3" / "dhcp_lease.h"

# Result codes, kept in lockstep with the header enum.
OK = 0
ARGUMENT = 1
UNSAFE_INPUT = 2
IP_SYNTAX = 3
IP_LEADING_ZERO = 4
IP_RANGE = 5
NETMASK_SYNTAX = 6
NETMASK_CONTIGUITY = 7
PREFIX_BOUNDS = 8
ADDRESS_NETWORK = 9
ADDRESS_BROADCAST = 10
GATEWAY_SYNTAX = 11
GATEWAY_RANGE = 12
GATEWAY_OFFLINK = 13
GATEWAY_NETWORK = 14
GATEWAY_BROADCAST = 15
GATEWAY_EQUALS_LEASE = 16
DNS_COUNT = 17
DNS_SYNTAX = 18
DNS_RANGE = 19
LEASE_SECONDS = 20
SUBNET_SYNTAX = 21
SUBNET_PREFIX = 22
PROTECTED_COUNT = 23
PROTECTED_OVERLAP = 24
PROTECTED_SUBNET = 25
SUBNET_RANGE = 26

MAX_DNS = 3
MAX_PROTECTED = 4
MIN_LEASE = 60
MAX_LEASE = 604800

# Protected networks are parameters: the stock AP and the (runtime-unproven)
# M4/USB service networks. Overridable so a caller supplies its own values.
AP_SUBNET = os.environ.get("C2M_AP_SUBNET", "192.168.1.1/24")
M4_USB_SUBNET = os.environ.get("C2M_M4_USB_SUBNET", "192.168.42.0/24")
USB_SUBNET = os.environ.get("C2M_USB_SUBNET", "10.55.0.0/16")


class Subnet(ctypes.Structure):
    _fields_ = [("network", ctypes.c_uint32), ("netmask", ctypes.c_uint32)]


class Lease(ctypes.Structure):
    _fields_ = [
        ("address", ctypes.c_uint32),
        ("netmask", ctypes.c_uint32),
        ("network", ctypes.c_uint32),
        ("broadcast", ctypes.c_uint32),
        ("prefix", ctypes.c_uint),
        ("has_gateway", ctypes.c_int),
        ("gateway", ctypes.c_uint32),
        ("dns_count", ctypes.c_uint),
        ("dns", ctypes.c_uint32 * 3),
        ("lease_seconds", ctypes.c_uint32),
    ]


def ipv4(text: str) -> int:
    octets = [int(part) for part in text.split(".")]
    assert len(octets) == 4
    return ((octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) |
            octets[3]) & 0xFFFFFFFF


def dotted(value: int) -> str:
    return "%d.%d.%d.%d" % ((value >> 24) & 0xFF, (value >> 16) & 0xFF,
                            (value >> 8) & 0xFF, value & 0xFF)


def prefix_to_netmask(prefix: int) -> str:
    mask = 0 if prefix == 0 else (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return dotted(mask)


def _cstr(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.encode("ascii", "surrogateescape")
    return value


class DhcpLeaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = os.environ.get("CC")
        if compiler:
            cls.cc = [compiler] if Path(compiler).is_file() else shlex.split(compiler)
        else:
            compiler = shutil.which("gcc") or shutil.which("cc")
            if not compiler:
                raise RuntimeError("Host GCC required (install gcc or set CC)")
            cls.cc = [compiler]
        temp_parent = None
        if os.name == "nt":
            approved = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "opencode"
            if approved.is_dir():
                temp_parent = approved
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-dhcp-lease-", dir=temp_parent)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.build = Path(cls.tmp.name)
        cls.flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                     "-pedantic", "-I", str(SOURCE.parent)]
        suffix = ".dll" if os.name == "nt" else ".so"
        cls.library_path = cls.build / ("dhcp_lease" + suffix)
        shared = ["-shared"] + ([] if os.name == "nt" else ["-fPIC"])
        cls.compile(*shared, str(SOURCE), "-o", str(cls.library_path))
        cls.lib = cls.configure(cls.library_path)
        if os.name == "nt":
            cls.addClassCleanup(cls.release_windows_library)

    @classmethod
    def release_windows_library(cls):
        import _ctypes
        _ctypes.FreeLibrary(cls.lib._handle)
        cls.lib = None

    @classmethod
    def configure(cls, path):
        lib = ctypes.CDLL(str(path))
        lib.c2m_dhcp_parse_ipv4.argtypes = [ctypes.c_char_p,
                                            ctypes.POINTER(ctypes.c_uint32)]
        lib.c2m_dhcp_parse_ipv4.restype = ctypes.c_int
        lib.c2m_dhcp_parse_subnet.argtypes = [ctypes.c_char_p,
                                              ctypes.POINTER(Subnet)]
        lib.c2m_dhcp_parse_subnet.restype = ctypes.c_int
        lib.c2m_dhcp_validate_lease.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_char_p), ctypes.c_uint, ctypes.c_uint32,
            ctypes.POINTER(Subnet), ctypes.c_uint, ctypes.POINTER(Lease)]
        lib.c2m_dhcp_validate_lease.restype = ctypes.c_int
        lib.c2m_dhcp_lease_has_router.argtypes = [ctypes.POINTER(Lease)]
        lib.c2m_dhcp_lease_has_router.restype = ctypes.c_int
        lib.c2m_dhcp_result_name.argtypes = [ctypes.c_int]
        lib.c2m_dhcp_result_name.restype = ctypes.c_char_p
        return lib

    @classmethod
    def compile(cls, *args):
        result = subprocess.run(cls.cc + cls.flags + list(args), cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Host compile failed:\n" + result.stdout + result.stderr)

    def parse_ip(self, text, expected=OK):
        out = ctypes.c_uint32(0xA5A5A5A5)
        result = self.lib.c2m_dhcp_parse_ipv4(_cstr(text), ctypes.byref(out))
        self.assertEqual(result, expected, text)
        return out.value

    def parse_subnet(self, cidr, expected=OK):
        out = Subnet()
        ctypes.memset(ctypes.byref(out), 0xA5, ctypes.sizeof(out))
        result = self.lib.c2m_dhcp_parse_subnet(_cstr(cidr), ctypes.byref(out))
        self.assertEqual(result, expected, cidr)
        return out

    def subnets(self, cidrs):
        if not cidrs:
            return None
        array = (Subnet * len(cidrs))()
        for index, entry in enumerate(cidrs):
            if isinstance(entry, Subnet):
                array[index] = entry
            elif isinstance(entry, tuple):
                array[index] = self.raw_subnet(*entry)
            else:
                array[index] = self.parse_subnet(entry)
        return array

    def raw_subnet(self, network, netmask):
        subnet = Subnet()
        subnet.network = network if isinstance(network, int) else ipv4(network)
        subnet.netmask = netmask if isinstance(netmask, int) else ipv4(netmask)
        return subnet

    def validate(self, address="192.168.50.2", netmask="255.255.255.0",
                 gateway=None, dns=(), seconds=3600, protected=(),
                 out_provided=True):
        dns_list = [_cstr(entry) for entry in dns]
        dns_array = ((ctypes.c_char_p * len(dns_list))(*dns_list)
                     if dns_list else None)
        protected_array = self.subnets(list(protected))
        out = Lease()
        ctypes.memset(ctypes.byref(out), 0xA5, ctypes.sizeof(out))
        result = self.lib.c2m_dhcp_validate_lease(
            _cstr(address), _cstr(netmask), _cstr(gateway),
            dns_array, len(dns_list), seconds,
            protected_array, len(protected),
            ctypes.byref(out) if out_provided else None)
        return result, out

    def expect(self, expected, **kwargs):
        result, out = self.validate(**kwargs)
        self.assertEqual(result, expected, self.lib.c2m_dhcp_result_name(result))
        if expected != OK:
            self.assertEqual(bytes(out), bytes(ctypes.sizeof(out)))
        return out

    # ---- happy path and the RFC-ish fixture --------------------------------

    def test_valid_fixture_ap_m4_usb(self):
        out = self.expect(
            OK, address="192.168.50.2", netmask="255.255.255.0",
            gateway="192.168.50.1", dns=("192.168.50.1", "8.8.8.8"),
            seconds=3600, protected=(AP_SUBNET, M4_USB_SUBNET, USB_SUBNET))
        self.assertEqual(out.address, ipv4("192.168.50.2"))
        self.assertEqual(out.netmask, ipv4("255.255.255.0"))
        self.assertEqual(out.network, ipv4("192.168.50.0"))
        self.assertEqual(out.broadcast, ipv4("192.168.50.255"))
        self.assertEqual(out.prefix, 24)
        self.assertEqual(out.has_gateway, 1)
        self.assertEqual(out.gateway, ipv4("192.168.50.1"))
        self.assertEqual(out.dns_count, 2)
        self.assertEqual(list(out.dns)[:out.dns_count],
                         [ipv4("192.168.50.1"), ipv4("8.8.8.8")])
        self.assertEqual(list(out.dns), [ipv4("192.168.50.1"),
                                         ipv4("8.8.8.8"), 0])
        self.assertEqual(out.lease_seconds, 3600)
        self.assertEqual(self.lib.c2m_dhcp_lease_has_router(ctypes.byref(out)), 1)

    def test_zero_router_is_valid_and_never_implies_internet(self):
        for gateway in (None, ""):
            with self.subTest(gateway=gateway):
                out = self.expect(OK, gateway=gateway, protected=(AP_SUBNET,))
                self.assertEqual(out.has_gateway, 0)
                self.assertEqual(out.gateway, 0)
                self.assertEqual(
                    self.lib.c2m_dhcp_lease_has_router(ctypes.byref(out)), 0)
        # The validated structure has no Internet/route/credential field.
        fields = {name for name, _ in Lease._fields_}
        self.assertEqual(fields, {
            "address", "netmask", "network", "broadcast", "prefix",
            "has_gateway", "gateway", "dns_count", "dns", "lease_seconds"})
        self.assertNotIn("internet", fields)

    def test_public_dns_and_no_dns(self):
        out = self.expect(OK, dns=("8.8.8.8", "1.1.1.1", "9.9.9.9"))
        self.assertEqual(out.dns_count, 3)
        out = self.expect(OK, dns=())
        self.assertEqual(out.dns_count, 0)
        self.assertEqual(list(out.dns), [0, 0, 0])

    # ---- canonical dotted-decimal ------------------------------------------

    def test_ip_canonical_parsing(self):
        self.assertEqual(self.parse_ip("0.0.0.1"), 1)
        self.assertEqual(self.parse_ip("255.255.255.255"), 0xFFFFFFFF)
        self.assertEqual(self.parse_ip("192.168.50.2"), ipv4("192.168.50.2"))
        for bad in ("", "192.168.50", "192.168.50.2.3", "192.168.50..2",
                    ".192.168.50.2", "192.168.50.2.", "192.168.50.256",
                    "192.168.50.-1", "192.168.50.a", "1.2.3.4.5"):
            with self.subTest(bad=bad):
                self.parse_ip(bad, IP_SYNTAX)

    def test_leading_zero_is_ambiguous(self):
        for bad in ("192.168.050.2", "192.168.50.02", "010.0.0.1",
                    "00.0.0.0", "192.168.50.00"):
            with self.subTest(bad=bad):
                self.parse_ip(bad, IP_LEADING_ZERO)

    def test_forbidden_ranges(self):
        for bad in ("0.0.0.0", "0.1.2.3", "127.0.0.1", "127.255.255.254",
                    "169.254.1.1", "224.0.0.1", "239.255.255.255",
                    "240.0.0.1", "255.255.255.255"):
            with self.subTest(bad=bad):
                self.assertEqual(self.parse_ip(bad), ipv4(bad))
                # Forbidden as a lease host even before network/broadcast.
                self.expect(IP_RANGE, address=bad, netmask="255.255.255.0")

    # ---- netmask and prefix -------------------------------------------------

    def test_netmask_contiguity_and_prefix_bounds(self):
        good = {"255.255.255.0": 24, "255.255.0.0": 16,
                "255.255.255.252": 30}
        for mask, prefix in good.items():
            with self.subTest(mask=mask):
                out = self.expect(OK, address="192.168.50.2", netmask=mask)
                self.assertEqual(out.prefix, prefix)
        # A /1 is contiguous but its span crosses a forbidden range, so it is
        # rejected by the subnet-range test rather than accepted as before.
        self.expect(SUBNET_RANGE, address="192.168.50.2", netmask="128.0.0.0")
        for mask in ("255.0.255.0", "0.255.0.0", "255.255.0.255"):
            with self.subTest(mask=mask):
                self.expect(NETMASK_CONTIGUITY, netmask=mask)
        for mask in ("0.0.0.0", "255.255.255.254", "255.255.255.255"):
            with self.subTest(mask=mask):
                self.expect(PREFIX_BOUNDS, netmask=mask)
        for mask in ("", "255.255.255", "255.255.255.256", "255.255.255.0.0"):
            with self.subTest(mask=mask):
                self.expect(NETMASK_SYNTAX, netmask=mask)
        self.expect(NETMASK_SYNTAX, netmask="255.255.255.00")

    def test_network_and_broadcast_host_rejected(self):
        self.expect(ADDRESS_NETWORK, address="192.168.50.0")
        self.expect(ADDRESS_BROADCAST, address="192.168.50.255")
        self.expect(ADDRESS_NETWORK, address="10.0.0.0", netmask="255.255.0.0")
        self.expect(ADDRESS_BROADCAST, address="10.0.255.255", netmask="255.255.0.0")

    def test_forbidden_subnet_range_intersection(self):
        # The forbidden test is an interval intersection, not an endpoint
        # check: a /1 whose span crosses 127/8 is rejected even though the host
        # 10.0.0.5 and the low endpoint are individually legal.
        self.expect(SUBNET_RANGE, address="10.0.0.5", netmask="128.0.0.0")
        # Every /1 crosses a forbidden range: the high half covers 224/4+240/4.
        self.expect(SUBNET_RANGE, address="200.1.2.3", netmask="128.0.0.0")
        # A /3 that touches no forbidden range stays valid.
        out = self.expect(OK, address="40.0.0.5", netmask="224.0.0.0")
        self.assertEqual(out.network, ipv4("32.0.0.0"))
        self.assertEqual(out.broadcast, ipv4("63.255.255.255"))
        # Ordinary private/public ranges (including CGNAT) are not over-banned.
        for cidr, address in (("10.0.0.0/8", "10.1.2.3"),
                              ("172.16.0.0/12", "172.16.5.5"),
                              ("192.168.0.0/16", "192.168.50.2"),
                              ("100.64.0.0/10", "100.64.0.1")):
            with self.subTest(cidr=cidr):
                subnet = self.parse_subnet(cidr)
                prefix = bin(subnet.netmask).count("1")
                self.expect(OK, address=address,
                            netmask=prefix_to_netmask(prefix))

    # ---- gateway ------------------------------------------------------------

    def test_gateway_rules(self):
        out = self.expect(OK, gateway="192.168.50.254")
        self.assertEqual(out.gateway, ipv4("192.168.50.254"))
        self.expect(GATEWAY_OFFLINK, gateway="192.168.51.1")
        self.expect(GATEWAY_OFFLINK, gateway="10.0.0.1")
        self.expect(GATEWAY_NETWORK, gateway="192.168.50.0")
        self.expect(GATEWAY_BROADCAST, gateway="192.168.50.255")
        self.expect(GATEWAY_EQUALS_LEASE, gateway="192.168.50.2")
        self.expect(GATEWAY_RANGE, gateway="127.0.0.1")
        self.expect(GATEWAY_RANGE, gateway="224.0.0.1")
        self.expect(GATEWAY_RANGE, gateway="0.0.0.0")
        self.expect(GATEWAY_SYNTAX, gateway="192.168.50.1.1")
        self.expect(GATEWAY_SYNTAX, gateway="192.168.50")
        self.expect(GATEWAY_SYNTAX, gateway="192.168.50.01")

    # ---- DNS ----------------------------------------------------------------

    def test_dns_rules(self):
        self.expect(DNS_COUNT, dns=("8.8.8.8", "8.8.4.4", "1.1.1.1", "9.9.9.9"))
        self.expect(DNS_RANGE, dns=("127.0.0.1",))
        self.expect(DNS_RANGE, dns=("224.0.0.1",))
        self.expect(DNS_RANGE, dns=("169.254.1.1",))
        # A DNS server must not be the lease subnet network or broadcast.
        self.expect(DNS_RANGE, dns=("192.168.50.0",))
        self.expect(DNS_RANGE, dns=("192.168.50.255",))
        # Duplicate servers are explicitly permitted; there is no de-dupe.
        self.expect(OK, dns=("8.8.8.8", "8.8.8.8"))
        self.expect(DNS_SYNTAX, dns=("192.168.50.1.1",))
        self.expect(DNS_SYNTAX, dns=("",))
        self.expect(UNSAFE_INPUT, dns=("192.168.50.2;id",))
        self.expect(OK, dns=("8.8.8.8",))

    # ---- lease time ---------------------------------------------------------

    def test_lease_seconds_bounds(self):
        for seconds in (60, 3600, MAX_LEASE):
            with self.subTest(seconds=seconds):
                out = self.expect(OK, seconds=seconds)
                self.assertEqual(out.lease_seconds, seconds)
        for seconds in (0, 59, MAX_LEASE + 1, 0xFFFFFFFF):
            with self.subTest(seconds=seconds):
                self.expect(LEASE_SECONDS, seconds=seconds)

    # ---- unsafe input -------------------------------------------------------

    def test_unsafe_input_rejected_everywhere(self):
        for junk in ("192.168.1.1\n", "192.168.1.1 ", "\t192.168.1.1",
                     "192.168.1.1;rm -rf /", "$(reboot)", "`id`",
                     "192.168.1.1|cat", "192.168.1.1&x", "192.168.1.1$(x)",
                     "192.168.1.1'x'", '192.168.1.1"x"', "192.168.1.1\\x",
                     "=a"):
            with self.subTest(junk=junk):
                self.parse_ip(junk, UNSAFE_INPUT)
        self.expect(UNSAFE_INPUT, address="192.168.50.2;id")
        self.expect(UNSAFE_INPUT, netmask="255.255.255.0\n")
        self.expect(UNSAFE_INPUT, gateway="192.168.50.1|tee")
        self.expect(UNSAFE_INPUT, dns=("8.8.8.8`x`",))
        self.parse_subnet("192.168.1.0/24;id", UNSAFE_INPUT)

    # ---- protected subnet parsing and overlap ------------------------------

    def test_parse_subnet_normalizes_cidr(self):
        subnet = self.parse_subnet("192.168.1.1/24")
        self.assertEqual(subnet.network, ipv4("192.168.1.0"))
        self.assertEqual(subnet.netmask, ipv4("255.255.255.0"))
        subnet = self.parse_subnet("10.0.0.0/8")
        self.assertEqual(subnet.network, ipv4("10.0.0.0"))
        self.assertEqual(subnet.netmask, ipv4("255.0.0.0"))
        subnet = self.parse_subnet("0.0.0.0/0")
        self.assertEqual(subnet.network, 0)
        self.assertEqual(subnet.netmask, 0)
        subnet = self.parse_subnet("1.2.3.4/32")
        self.assertEqual(subnet.network, ipv4("1.2.3.4"))
        self.assertEqual(subnet.netmask, 0xFFFFFFFF)
        for bad in ("192.168.1", "192.168.1.1", "192.168.1/24",
                    "192.168.1.1/", "192.168.1.1/-1", "garbage",
                    "192.168.01.1/24", "/24", "1.2.3.4/24/24"):
            with self.subTest(bad=bad):
                self.parse_subnet(bad, SUBNET_SYNTAX)
        self.parse_subnet("1.2.3.4/33", SUBNET_PREFIX)
        self.parse_subnet("1.2.3.4/100", SUBNET_PREFIX)

    def test_protected_overlap_and_broad_masks(self):
        # Exact stock AP subnet and a lease inside it.
        self.expect(PROTECTED_OVERLAP, address="192.168.1.2",
                    protected=(AP_SUBNET,))
        # Each supplied M4/USB network is protected dynamically.
        for cidr in (M4_USB_SUBNET, USB_SUBNET):
            with self.subTest(cidr=cidr):
                subnet = self.parse_subnet(cidr)
                prefix = bin(subnet.netmask).count("1")
                host = dotted(subnet.network + 2)
                netmask = prefix_to_netmask(prefix)
                self.expect(PROTECTED_OVERLAP, address=host, netmask=netmask,
                            protected=(cidr,))
        # Broad protected mask containing the lease subnet.
        self.expect(PROTECTED_OVERLAP, address="192.168.50.2",
                    protected=("192.168.0.0/16",))
        self.expect(PROTECTED_OVERLAP, address="10.1.2.3", netmask="255.255.0.0",
                    protected=("10.0.0.0/8",))
        self.expect(PROTECTED_OVERLAP, address="172.16.5.5",
                    protected=("0.0.0.0/0",))
        # Non-overlapping protected subnets are fine.
        self.expect(OK, address="192.168.50.2",
                    protected=("192.168.1.0/24", M4_USB_SUBNET, USB_SUBNET))
        self.expect(OK, address="192.168.50.2",
                    protected=("1.2.3.4/32",))
        # Bounded count: exactly four is allowed, five is rejected.
        four = ("192.168.1.0/24", "192.168.42.0/24", "10.55.0.0/16",
                "172.16.0.0/12")
        self.assertEqual(len(four), MAX_PROTECTED)
        self.expect(OK, protected=four)
        self.expect(PROTECTED_COUNT, protected=four + ("192.168.99.0/24",))

    def test_protected_subnet_normalization_and_contiguity(self):
        # A raw struct with host bits set must be normalized, not trusted: the
        # host-bit form of 192.168.1.0/24 must still block 192.168.1.2/30.
        self.expect(PROTECTED_OVERLAP, address="192.168.1.2",
                    netmask="255.255.255.252",
                    protected=[("192.168.1.128", "255.255.255.0")])
        # Parsed and raw/host-bit forms describe the same protected subnet.
        parsed = self.parse_subnet("192.168.1.1/24")
        raw = self.raw_subnet("192.168.1.128", "255.255.255.0")
        self.assertEqual(parsed.network, raw.network & raw.netmask)
        self.assertEqual(parsed.netmask, raw.netmask)
        for entry in (("192.168.1.128", "255.255.255.0"), parsed):
            with self.subTest(entry=entry):
                self.expect(PROTECTED_OVERLAP, address="192.168.1.2",
                            netmask="255.255.255.252", protected=[entry])
        # A noncontiguous protected mask is a structured input error.
        for raw_mask in ("255.0.255.0", "0.255.0.0", "255.255.0.255"):
            with self.subTest(raw_mask=raw_mask):
                self.expect(PROTECTED_SUBNET,
                            protected=[("192.168.1.0", raw_mask)])
        # A protected /0 is contiguous, allowed, and protects everything.
        self.expect(PROTECTED_OVERLAP, address="192.168.50.2",
                    protected=[("1.2.3.4", "0.0.0.0")])
        self.expect(PROTECTED_OVERLAP, address="192.168.50.2",
                    protected=("0.0.0.0/0",))

    # ---- argument handling --------------------------------------------------

    def test_argument_handling(self):
        out = Lease()
        self.assertEqual(self.lib.c2m_dhcp_validate_lease(
            b"192.168.50.2", b"255.255.255.0", None, None, 0, 3600,
            None, 1, ctypes.byref(out)), ARGUMENT)
        self.assertEqual(self.lib.c2m_dhcp_validate_lease(
            b"192.168.50.2", b"255.255.255.0", None,
            None, 1, 3600, None, 0,
            ctypes.byref(out)), ARGUMENT)
        self.assertEqual(self.lib.c2m_dhcp_parse_ipv4(None, ctypes.byref(
            ctypes.c_uint32())), ARGUMENT)
        self.assertEqual(self.lib.c2m_dhcp_parse_ipv4(b"1.2.3.4", None), ARGUMENT)
        self.assertEqual(self.lib.c2m_dhcp_parse_subnet(None, ctypes.byref(
            Subnet())), ARGUMENT)
        self.assertEqual(self.lib.c2m_dhcp_parse_subnet(b"1.2.3.4/24", None),
                         ARGUMENT)
        self.expect(ARGUMENT, address=None)
        self.expect(ARGUMENT, netmask=None)
        result, _ = self.validate(out_provided=False)
        self.assertEqual(result, ARGUMENT)

    def test_failed_parse_leaves_numeric_out_untouched(self):
        value = ctypes.c_uint32(0xA5A5A5A5)
        self.lib.c2m_dhcp_parse_ipv4(b"bad;id", ctypes.byref(value))
        self.assertEqual(value.value, 0xA5A5A5A5)

    # ---- result naming and purity ------------------------------------------

    def test_result_names_are_fixed_and_input_free(self):
        expected = {
            OK: b"ok", ARGUMENT: b"argument", UNSAFE_INPUT: b"unsafe_input",
            IP_SYNTAX: b"ip_syntax", IP_LEADING_ZERO: b"ip_leading_zero",
            IP_RANGE: b"ip_range", NETMASK_SYNTAX: b"netmask_syntax",
            NETMASK_CONTIGUITY: b"netmask_contiguity",
            PREFIX_BOUNDS: b"prefix_bounds", ADDRESS_NETWORK: b"address_network",
            ADDRESS_BROADCAST: b"address_broadcast",
            GATEWAY_SYNTAX: b"gateway_syntax", GATEWAY_RANGE: b"gateway_range",
            GATEWAY_OFFLINK: b"gateway_offlink",
            GATEWAY_NETWORK: b"gateway_network",
            GATEWAY_BROADCAST: b"gateway_broadcast",
            GATEWAY_EQUALS_LEASE: b"gateway_equals_lease",
            DNS_COUNT: b"dns_count", DNS_SYNTAX: b"dns_syntax",
            DNS_RANGE: b"dns_range", LEASE_SECONDS: b"lease_seconds",
            SUBNET_SYNTAX: b"subnet_syntax", SUBNET_PREFIX: b"subnet_prefix",
            PROTECTED_COUNT: b"protected_count",
            PROTECTED_OVERLAP: b"protected_overlap",
            PROTECTED_SUBNET: b"protected_subnet",
            SUBNET_RANGE: b"subnet_range",
        }
        self.assertEqual(set(expected), set(range(27)))
        for code, name in expected.items():
            with self.subTest(code=code):
                self.assertEqual(self.lib.c2m_dhcp_result_name(code), name)
        self.assertEqual(self.lib.c2m_dhcp_result_name(12345), b"unknown")

    def test_source_is_pure_pure_ascii_and_shell_free(self):
        text = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("#include <stdio.h>", "printf", "fprintf", "snprintf",
                          "puts(", "putchar", "system(", "popen", "exec",
                          "fork(", "socket(", "fopen", "getenv", "malloc",
                          "calloc", "realloc", "abort("):
            self.assertNotIn(forbidden, text, forbidden)
        header = HEADER.read_text(encoding="utf-8")
        self.assertNotIn("stdio.h", header)
        # Fixed literal reason tokens only; no caller data is formatted in.
        self.assertIn('return "protected_overlap";', text)
        self.assertIn('return "protected_subnet";', text)
        self.assertIn('return "subnet_range";', text)
        self.assertTrue(text.isascii())

    def test_validator_emits_no_stdout(self):
        probe = (
            "import ctypes,sys\n"
            "lib=ctypes.CDLL(sys.argv[1])\n"
            "class S(ctypes.Structure):\n"
            "    _fields_=[('network',ctypes.c_uint32),('netmask',ctypes.c_uint32)]\n"
            "class L(ctypes.Structure):\n"
            "    _fields_=[('address',ctypes.c_uint32),('netmask',ctypes.c_uint32),"
            "('network',ctypes.c_uint32),('broadcast',ctypes.c_uint32),"
            "('prefix',ctypes.c_uint),('has_gateway',ctypes.c_int),"
            "('gateway',ctypes.c_uint32),('dns_count',ctypes.c_uint),"
            "('dns',ctypes.c_uint32*3),('lease_seconds',ctypes.c_uint32)]\n"
            "lib.c2m_dhcp_validate_lease.argtypes=[ctypes.c_char_p,ctypes.c_char_p,"
            "ctypes.c_char_p,ctypes.POINTER(ctypes.c_char_p),ctypes.c_uint,"
            "ctypes.c_uint32,ctypes.POINTER(S),ctypes.c_uint,ctypes.POINTER(L)]\n"
            "lib.c2m_dhcp_validate_lease.restype=ctypes.c_int\n"
            "lib.c2m_dhcp_parse_ipv4.argtypes=[ctypes.c_char_p,"
            "ctypes.POINTER(ctypes.c_uint32)]\n"
            "lib.c2m_dhcp_parse_ipv4.restype=ctypes.c_int\n"
            "v=ctypes.c_uint32()\n"
            "lib.c2m_dhcp_parse_ipv4(b'bad;id\\n',ctypes.byref(v))\n"
            "o=L()\n"
            "lib.c2m_dhcp_validate_lease(b'192.168.50.2',b'255.255.255.0',"
            "b'192.168.50.1',None,0,3600,None,0,ctypes.byref(o))\n"
        )
        result = subprocess.run([sys.executable, "-c", probe,
                                 str(self.library_path)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_repeatable_and_deterministic(self):
        first = self.expect(OK, protected=(AP_SUBNET, M4_USB_SUBNET))
        second = self.expect(OK, protected=(AP_SUBNET, M4_USB_SUBNET))
        self.assertEqual(bytes(first), bytes(second))


if __name__ == "__main__":
    unittest.main(verbosity=2)

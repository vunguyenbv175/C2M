#!/usr/bin/env python3
"""CI ELF gate for the minimal ARM binary: assert 32-bit LE ARM EXEC, no execution."""
import struct
import sys
from pathlib import Path

p = Path(sys.argv[1])
d = p.read_bytes()
assert d[:4] == b"\x7fELF", "not ELF"
assert d[4] == 1, f"want EI_CLASS=1 (32-bit), got {d[4]}"
assert d[5] == 1, f"want EI_DATA=1 (LE), got {d[5]}"
etype, machine = struct.unpack_from("<HH", d, 16)
assert etype == 2, f"want ET_EXEC=2, got {hex(etype)}"
assert machine == 0x28, f"want EM_ARM=0x28, got {hex(machine)}"
print(f"ELF-OK: {p} 32-bit LE ARM EXEC ({len(d)} bytes)")

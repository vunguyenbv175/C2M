#!/usr/bin/env python3
"""Static source-level tests for fw/device_minimal/start.S (no toolchain needed).

Locks the glibc-2.30 ARM startup contract into the source so a future edit
cannot silently break it (the CI disassembly step in the arm-dyn job proves
the COMPILED shape; this proves the SOURCE shape on every host run):

  1. outermost frame/link cleared (mov fp,#0 / mov lr,#0);
  2. argc popped, argv taken from sp (pop {a2} / mov a3,sp);
  3. loader rtld_fini PRESERVED: pushed from a1 BEFORE any write to a1
     (precisely: the first `push {a1}` precedes the first `ldr a1`/`mov a1`);
  4. stack order fini/rtld_fini/stack_end (push a3=stack_end, push a1=rtld,
     push a4=NULL-fini, in that order);
  5. 8-byte call-boundary alignment statically accountable: pop(4) + 3x
     push(4) = net +8 from entry, i.e. sp%8 preserved;
  6. .note.GNU-stack present (non-executable stack, no linker warning);
  7. eabi attributes 24/25 (align8) + 6/10/28 (v7/VFPv3-D16/VFP-args), and NO
     Advanced-SIMD attribute directive (no tag 12);
  8. version pins for __libc_start_main/abort in THIS object;
  9. abort fallback after the __libc_start_main call.
Run: python3 fw/device_minimal/test_startup_abi.py
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "start.S"


def main() -> int:
    t = SRC.read_text(encoding="utf-8")
    fails: list[str] = []

    def check(name: str, ok: bool, detail: str = ""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
        if not ok:
            fails.append(name)

    code = [ln.split("//")[0].split("/*")[0]
            for ln in t.splitlines()]
    body = "\n".join(code)

    check("frame.clear", "mov fp, #0" in body and "mov lr, #0" in body)
    check("args.argv", "pop {a2}" in body and "mov a3, sp" in body)
    push_a1 = body.find("push {a1}")
    first_a1_write = min((body.find(p) for p in ("ldr a1", "mov a1")
                          if body.find(p) >= 0), default=10**9)
    check("fini.preserved", 0 <= push_a1 < first_a1_write,
          "(push{a1} must precede any a1 write)")
    check("fini.not_null", "rtld_fini = NULL" not in body and "rtld_fini=NULL" not in body,
          "(loader value preserved, never forced NULL)")
    order = [body.find(f"push {{{r}}}") for r in ("a3", "a1", "a4")]
    check("stack.order", all(o >= 0 for o in order) and order == sorted(order),
          "(stack_end, rtld_fini, fini)")
    pops = len(re.findall(r"^\s*pop\s", body, re.M))
    push_regs = re.findall(r"^\s*push\s\{([^}]*)\}", body, re.M)
    pushed_words = sum(len(r.split(",")) for r in push_regs)
    check("stack.align8", (pushed_words * 4 - pops * 4) % 8 == 0,
          f"(pop {pops} regs, push {pushed_words} regs: net %+d)" % (pushed_words * 4 - pops * 4))
    check("stack.note", '.section .note.GNU-stack,"",%progbits' in body)
    for tag, want in ((24, 1), (25, 1), (6, 10), (10, 4), (28, 1)):
        check(f"attr.{tag}", f".eabi_attribute {tag}, {want}" in body)
    check("attr.no_simd", ".eabi_attribute 12," not in body)
    check("symver.startmain", ".symver __libc_start_main,__libc_start_main@GLIBC_2.4" in body)
    check("symver.abort", ".symver abort,abort@GLIBC_2.4" in body)
    bl_main = body.find("bl __libc_start_main")
    bl_abort = body.find("bl abort")
    check("fallthrough.abort", 0 <= bl_main < bl_abort, "(abort after start_main call)")

    if fails:
        print(f"STARTUP-ABI: FAIL {fails}")
        return 1
    print("startup-abi source: OK (glibc-2.30 ARM contract locked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

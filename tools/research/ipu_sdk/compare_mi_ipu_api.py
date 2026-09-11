"""Diff local MI_IPU dynsym exports against a candidate SDK header/library.

Inputs (all obtainable without running vendor binaries):
  --dynsym  text file with one local symbol per line (the 11 C2M exports), or
            an ELF .so (parsed via `nm -D --defined-only` if available)
  --header  candidate mi_ipu.h (scans MI_IPU_* declarations)
  --lib     candidate libmi_ipu.so (optional; same nm parse, never executed)

Output: MATCH / ADDED (candidate-only) / MISSING (local-only) / SIGNATURE_RISK
(signatures are NOT compared textually unless --strict; risk list is structural:
fields/APIs known to postdate sdk_commit.b03a7d4).

Usage:
  python3 compare_mi_ipu_api.py --dynsym local_dynsym.txt --header mi_ipu.h [--lib libmi_ipu.so]
"""
import argparse
import re
import shutil
import subprocess

LOCAL_11 = ["MI_IPU_CreateDevice", "MI_IPU_DestroyDevice", "MI_IPU_CreateCHN",
            "MI_IPU_DestroyCHN", "MI_IPU_GetInOutTensorDesc", "MI_IPU_GetInputTensors",
            "MI_IPU_PutInputTensors", "MI_IPU_GetOutputTensors", "MI_IPU_PutOutputTensors",
            "MI_IPU_Invoke", "MI_IPU_GetOfflineModeStaticInfo"]
NEWER_RISK = ["MI_IPU_GetInputTensors2", "MI_IPU_PutInputTensors2",
              "MI_IPU_GetOutputTensors2", "MI_IPU_PutOutputTensors2",
              "MI_IPU_Invoke2", "MI_IPU_Invoke2Custom", "MI_IPU_CreateCHNWithUserMem",
              "MI_IPU_DestroyDeviceExt", "MI_IPU_CancelInvoke"]
STRUCT_RISK = ["au32Reserve", "u32VariableGroup", "u32CoreMask", "eBatchMode",
               "eIpuWorkMode", "eLayoutType", "u32BufSize", "u32InputWidthAlignment",
               "MI_IPU_FORMAT_GRAY", "MI_IPU_FORMAT_COMPLEX64"]


def load_names(path):
    txt = open(path, errors="replace").read()
    names = re.findall(r"MI_IPU_[A-Za-z0-9_]+", txt)
    if not names and path.endswith(".so") and shutil.which("nm"):
        try:
            out = subprocess.run(["nm", "-D", "--defined-only", path],
                                 capture_output=True, text=True, timeout=30).stdout
            names = re.findall(r"MI_IPU_[A-Za-z0-9_]+", out)
        except Exception:
            pass
    return sorted(set(names))


def main():
    ap = argparse.ArgumentParser(description="MI_IPU API diff (static only)")
    ap.add_argument("--dynsym", default="", help="local dynsym .txt or .so")
    ap.add_argument("--header", default="", help="candidate mi_ipu.h")
    ap.add_argument("--lib", default="", help="candidate libmi_ipu.so (never executed)")
    args = ap.parse_args()
    local = load_names(args.dynsym) if args.dynsym else list(LOCAL_11)
    local = [n for n in local if n in LOCAL_11 or n.startswith("MI_IPU_")]
    cand = set()
    struct_hits = []
    for src in (args.header, args.lib):
        if src:
            cand |= set(load_names(src))
            if src.endswith(".h"):
                txt = open(src, errors="replace").read()
                struct_hits = sorted({s for s in STRUCT_RISK if s in txt})
    local_s, cand_s = set(local), set(cand) if cand else set(local)
    match = sorted(local_s & cand_s) if cand else sorted(local_s)
    missing = sorted(local_s - cand_s) if cand else []
    added = sorted(cand_s - local_s) if cand else []
    newer = sorted(set(added) & set(NEWER_RISK))
    print("MATCH (%d): %s" % (len(match), match))
    print("MISSING-local-only (%d): %s" % (len(missing), missing))
    print("ADDED-candidate-only (%d): %s" % (len(added), added))
    print("NEWER-API-RISK (must NOT run on C2M b03a7d4): %s" % newer)
    print("SIGNATURE_RISK (postdates 2022-06-06, verify before use): %s" % struct_hits)
    if not cand:
        print("note: no candidate given; local baseline printed (11 expected).")


if __name__ == "__main__":
    main()

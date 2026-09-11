"""Metadata-only fingerprint scanner for a local SGS_IPU_SDK / SGS_IPU_Toolchain drop.

Scans a directory the operator already obtained via legal channels and emits
JSON metadata ONLY (paths, sizes, hashes, tool/version/chip/API/framework strings).
Never copies SDK files, weights, or binaries into the repo. Do NOT point it at
firmware dumps; it is for the host-side SDK tree (e.g. external/sgs_ipu_sdk).

Usage:
  python3 fingerprint_sgs_sdk.py --sdk <dir> [--out fingerprint.json]
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

TOOL_NAMES = ["ConvertTool.py", "SGS_converter.py", "Calibrator.py", "calibrator.py",
              "Compiler.py", "compiler.py", "Simulator.py", "simulator.py",
              "postprocess.py", "concat_net", "show_sdk_info.py", "cfg_env.sh",
              "input_config.ini", "CompilerConfig.txt", "run_docker.sh",
              "dla_simulator", "dla_classify", "dla_detect", "show_img_info",
              "ipu_log", "utilization", "ipu_server", "mi_ipu.h",
              "mi_ipu_datatype.h", "mi_sys.h", "mi_scl.h"]
VERSION_RES = [r"sdk_commit\.[0-9a-f]{5,}", r"project_commit\.[0-9a-f]{5,}",
               r"T_\d+\.\d+\.\d+_\d+", r"build_time\.\d{10,}",
               r"S\d+\.\d+.*verified.*\d{6,}", r"sgs_docker_v[\d.]+",
               r"Netron Setup [\d.]+", r"Python\s*3\.\d+", r"tensorflow.{0,8}1\.\d+"]
CHIP_RES = [r"SSC8838G", r"SSC35\d\w?", r"SSC33\d\w?", r"SSC93\d+\w?", r"SSD2\d+\w?",
            r"Mercury6?", r"Tiramisu", r"Pudding", r"Pcupid", r"Muffin", r"Mochi",
            r"Maruko", r"\bpcupid\b", r"\bCHIP_LIST\b", r"soc_version"]
API_RES = [r"MI_IPU_[A-Za-z0-9_]+", r"MI_SYS_[A-Za-z0-9_]+", r"MI_SCL_[A-Za-z0-9_]+"]
FW_RES = [r"\bonnx\b", r"caffe", r"tflite", r"tensorflow_graphdef",
          r"tensorflow_savemodel", r"keras", r"torch_calibrator"]


def sha256_of(path, limit=8 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
            if h.digest_size and f.tell() > limit:
                h.update(b"[...truncated-for-scan...]")
                break
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sdk", required=True, help="local SDK directory (already obtained legally)")
    ap.add_argument("--out", default="", help="output JSON path (default: stdout)")
    args = ap.parse_args()
    root = Path(args.sdk)
    if not root.is_dir():
        raise SystemExit("not a directory: %s" % root)
    files, tools, versions, chips, apis, fws, reqs = [], {}, set(), set(), set(), set(), {}
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            rel = str(p.relative_to(root))
            files.append({"path": rel, "bytes": sz,
                          "sha256": sha256_of(p) if sz <= (8 << 20) else "LARGE-skipped"})
            if fn in TOOL_NAMES:
                tools.setdefault(fn, []).append(rel)
            if fn in ("requirements.txt", "setup.py", "environment.yml", "Dockerfile"):
                try:
                    reqs[rel] = p.read_text(errors="replace")[:4000]
                except OSError:
                    pass
            if p.suffix.lower() in (".py", ".sh", ".ini", ".txt", ".cfg", ".md", ".html"):
                try:
                    text = p.read_text(errors="replace")[:200000]
                except OSError:
                    continue
                for rx in VERSION_RES:
                    versions.update(re.findall(rx, text, re.I))
                for rx in CHIP_RES:
                    chips.update(re.findall(rx, text))
                for rx in API_RES:
                    apis.update(re.findall(rx, text))
                for rx in FW_RES:
                    fws.update(m.lower() for m in re.findall(rx, text, re.I))
    report = {"sdk_root": str(root), "file_count": len(files), "files": sorted(files, key=lambda d: d["path"])[:5000],
              "tool_hits": tools, "version_strings": sorted(versions)[:200],
              "chip_strings": sorted(set(chips))[:200], "api_names": sorted(apis)[:300],
              "framework_importers": sorted(fws), "dependency_files": reqs,
              "note": "metadata only; no SDK content copied"}
    out = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(out)
    else:
        print(out)


if __name__ == "__main__":
    main()

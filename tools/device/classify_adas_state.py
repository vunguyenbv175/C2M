#!/usr/bin/env python3
"""Classify C2M ADAS runtime state from one read-only baseline capture.

The output is evidence-first. A classification is emitted only when its
preconditions are observable in the capture; otherwise UNKNOWN is preferred.

Classes:
A process_absent
B process_crash_or_restart
C process_alive_input_path_suspect
D process_alive_inference_init_suspect
E inference_likely_alive_output_suppressed
F adas_likely_alive_display_audio_path_suspect
OK no_obvious_failure_in_baseline
UNKNOWN insufficient_evidence
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PORT_SCREEN = 26012
PORT_CARDV = 8080
HEX_SCREEN = f"{PORT_SCREEN:04X}"
HEX_CARDV = f"{PORT_CARDV:04X}"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def all_text(root: Path, max_each: int = 2_000_000) -> str:
    chunks = []
    candidates = [
        root / "dmesg.txt",
        root / "ps.txt",
        root / "ps_w.txt",
        root / "processes.tsv",
        root / "netstat_anp.txt",
        root / "ss_lntup.txt",
        root / "proc_net_unix.txt",
        root / "proc_sysvipc_shm.txt",
        root / "proc_sysvipc_msg.txt",
        root / "ports_of_interest.txt",
        root / "high_value_files.tsv",
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size <= max_each:
            chunks.append(read(p))
    for p in root.glob("proc_*_*/status.txt"):
        if p.stat().st_size <= max_each:
            chunks.append(read(p))
    for p in root.glob("proc_*_*/fd.txt"):
        if p.stat().st_size <= max_each:
            chunks.append(read(p))
    return "\n".join(chunks)


def processes(root: Path) -> list[dict[str, str]]:
    out = []
    for line in read(root / "processes.tsv").splitlines():
        p = line.split("\t", 2)
        if len(p) >= 2:
            out.append({"pid": p[0], "comm": p[1], "cmd": p[2] if len(p) > 2 else ""})
    return out


def process_matches(procs, needle: str):
    n = needle.lower()
    return [p for p in procs if n in (p["comm"] + " " + p["cmd"]).lower()]


def port_present(root: Path, port: int) -> bool:
    h = f"{port:04X}"
    for fn in ["proc_net_tcp.txt", "proc_net_tcp6.txt", "proc_net_udp.txt", "proc_net_udp6.txt"]:
        text = read(root / fn).upper()
        if re.search(rf":[0]*{h}\b", text):
            return True
    text = (read(root / "netstat_anp.txt") + "\n" + read(root / "ss_lntup.txt"))
    return bool(re.search(rf"[:.]?{port}\b", text))


def keyword_hits(text: str, groups: dict[str, list[str]]) -> dict[str, list[str]]:
    low = text.lower()
    result = {}
    for name, words in groups.items():
        found = sorted({w for w in words if w.lower() in low})
        if found:
            result[name] = found
    return result


def status_for_pid(root: Path, pid: str) -> str:
    for d in root.glob(f"proc_{pid}_*"):
        p = d / "status.txt"
        if p.exists():
            return read(p)
    return ""


def classify(root: Path) -> dict[str, Any]:
    procs = processes(root)
    adas = process_matches(procs, "adas")
    cardv = process_matches(procs, "cardv")
    text = all_text(root)

    groups = {
        "crash": ["segfault", "segmentation fault", "sigsegv", "killed process", "core dumped", "assert failed", "abort"],
        "ringbuf_input": ["raw_adas", "ringbuf_vehicle", "ringbuf", "camera reader", "get frame failed", "frame timeout", "no frame"],
        "ipu_inference": ["mi_ipu", "ipucreate", "ipu", "model init", "load model", "cnn", "npu"],
        "calibration": ["calib", "calibration"],
        "license": ["license", "checksn", "bitanswer", "serial number"],
        "screen": ["screenservice", "screen service", "screenwarning", "screenaudio", "websocket", "26012"],
        "audio": ["sound_alert", "audio", "wav"],
        "warning": ["fcw", "ldw", "pcw", "hmw", "warning"],
    }
    hits = keyword_hits(text, groups)

    screen_port = port_present(root, PORT_SCREEN)
    cardv_port = port_present(root, PORT_CARDV)
    raw_hint = bool(hits.get("ringbuf_input"))
    crash_hint = bool(hits.get("crash"))
    ipu_hint = bool(hits.get("ipu_inference"))
    screen_hint = screen_port or bool(hits.get("screen"))

    adas_states = []
    for p in adas:
        s = status_for_pid(root, p["pid"])
        m = re.search(r"^State:\s*(.+)$", s, re.M)
        adas_states.append({"pid": p["pid"], "comm": p["comm"], "cmd": p["cmd"], "state": m.group(1).strip() if m else None})

    evidence = []
    def add(kind, value, weight=0, note=""):
        evidence.append({"kind": kind, "value": value, "weight": weight, "note": note})

    add("adas_process_count", len(adas), 100 if adas else -100)
    add("cardv_process_count", len(cardv), 15 if cardv else -15)
    add("screenservice_port_26012", screen_port, 35 if screen_port else -20)
    add("cardv_port_8080", cardv_port, 10 if cardv_port else 0)
    add("raw_adas_or_ringbuf_text_seen", raw_hint, 10 if raw_hint else 0)
    add("crash_keywords_seen", crash_hint, -50 if crash_hint else 0, str(hits.get("crash", [])))
    add("ipu_or_inference_text_seen", ipu_hint, 10 if ipu_hint else 0)

    # Classification is deliberately conservative. Static baselines do not
    # prove frames are flowing or inference is producing detections.
    if not adas:
        cls = "B" if crash_hint else "A"
        label = "process_crash_or_restart" if crash_hint else "process_absent"
        confidence = "medium" if crash_hint else "high"
        reason = "No ADAS process is present; crash evidence exists." if crash_hint else "No ADAS process is present in processes.tsv."
    elif crash_hint:
        cls = "B"; label = "process_crash_or_restart"; confidence = "medium"
        reason = "ADAS process is present now, but crash-related evidence appears in captured logs; this may indicate a guard/restart loop."
    else:
        # Negative evidence is not enough to distinguish C/D/E/F. Build a
        # bounded candidate set from what *is* observable.
        candidates = []
        if not raw_hint:
            candidates.append("C: input path/ringbuffer must still be verified")
        if not ipu_hint:
            candidates.append("D: IPU/model initialization must still be verified")
        if screen_port:
            candidates.append("E/F less likely to be a missing ScreenService listener, but message flow is unproven")
        else:
            candidates.append("F: display/output path is suspect because port 26012 is not observed")
        cls = "OK" if screen_port and cardv else "UNKNOWN"
        label = "no_obvious_failure_in_baseline" if cls == "OK" else "insufficient_evidence"
        confidence = "low"
        reason = "; ".join(candidates)

    # Stronger F candidate: ADAS exists, cardv exists, no crash, but screen
    # listener is absent. Still call it a candidate, not proof.
    candidates = []
    if adas and cardv and not crash_hint and not screen_port:
        candidates.append({"class": "F", "label": "display_audio_path_suspect", "confidence": "medium", "basis": "ADAS and cardv present but ScreenService port 26012 not observed"})
    if adas and not crash_hint and not raw_hint:
        candidates.append({"class": "C", "label": "input_path_needs_verification", "confidence": "low", "basis": "baseline contains no raw_adas/ringbuf evidence; absence of text is not proof of absent frames"})
    if adas and not crash_hint and not ipu_hint:
        candidates.append({"class": "D", "label": "inference_init_needs_verification", "confidence": "low", "basis": "baseline contains no explicit IPU/model evidence"})

    return {
        "capture": str(root),
        "classification": {"class": cls, "label": label, "confidence": confidence, "reason": reason},
        "candidates": candidates,
        "adas_processes": adas_states,
        "cardv_processes": cardv,
        "ports": {"26012_screenservice": screen_port, "8080_cardv_candidate": cardv_port},
        "keyword_hits": hits,
        "evidence": evidence,
        "limitations": [
            "A single baseline is a snapshot, not a continuous liveness test.",
            "No frame counter is currently sampled, so C vs D cannot be proven from absence of text alone.",
            "Port 26012 proves a listener/socket only, not successful M4 delivery.",
            "Class E requires evidence that inference results exist while warnings are suppressed; the baseline collector alone may not provide that."
        ]
    }


def markdown(r: dict[str, Any]) -> str:
    c = r["classification"]
    out = [
        "# ADAS runtime classification", "",
        f"Capture: `{r['capture']}`", "",
        f"**Result:** `{c['class']} — {c['label']}`  ",
        f"**Confidence:** {c['confidence']}  ",
        f"**Reason:** {c['reason']}", "",
        "## Processes", "",
        f"- ADAS: {len(r['adas_processes'])}",
        f"- cardv: {len(r['cardv_processes'])}",
        f"- ScreenService port 26012 observed: {r['ports']['26012_screenservice']}",
        f"- cardv candidate port 8080 observed: {r['ports']['8080_cardv_candidate']}", "",
    ]
    if r["candidates"]:
        out += ["## Candidate next checks", ""]
        for x in r["candidates"]:
            out.append(f"- `{x['class']}` {x['label']} ({x['confidence']}): {x['basis']}")
        out.append("")
    out += ["## Limitations", ""] + [f"- {x}" for x in r["limitations"]] + [""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--markdown", type=Path)
    args = ap.parse_args()
    result = classify(args.capture)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(markdown(result), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

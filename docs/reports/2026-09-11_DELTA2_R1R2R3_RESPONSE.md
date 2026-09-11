# Báo cáo Delta 2 — đáp ứng DELTA_R1_R9_OWNER_REVIEW (3 findings P0)

Trả lời `docs/reviews/2026-09-11_DELTA_R1_R9_OWNER_REVIEW.md`. Giữ toàn bộ
hướng "không rollback" của review.

## WHAT WAS BUILT

R1-new — evidence verification fail-closed:

```text
tools/ci/verify_evidence.py   TAR SHA gate -> carve -> rootfs/cardv SHA gate
                              -> UBIFS inventories -> adas SHA gate
                              -> regen 4 JSONs -> diff canonical (fail mọi bước)
tools/ci/test_evidence_gate.py  5 induced failures đều RED:
                              missing TAR / bad SHA / truncated image /
                              generator missing-inputs / tampered canonical;
                              happy-path full-chain GREEN.
.github/workflows/firmware-evidence.yml  viết lại, không `|| echo`.
```

R2-new — transmit boundary:

```text
M4Adapter::Transmit re-validate từng message: channel allowlist +
uuid policy + key-shape allowlist + denied sweep (BlockedPolicy).
CHECK tests (chạy cả Release/NDEBUG): 5 bypass negatives
(GPSSpeed/AdasStatus/unknown-UUID/sai channel/smuggle fcw) + 1 positive.
Python parity: replay_guard payload_shape_ok + test.
```

Test thật bắt 1 bug boundary (smuggle `"fcw"` lọt sweep thiếu token) → chuyển
sang shape-allowlist làm lớp chính. Đã sửa + xanh.

R3-new — verdict 3 tầng: `tiers:{presence,routing,runtime}` trên cả 53 rows;
presence CONFIRMED không suy ra routing/runtime. Schema regen + md §5 + memory.

Phụ: smoke test chuyển assert→CHECK (Release không còn vacuous).

## WHAT WAS PROVEN

- Local CI strict + evidence: ALL GREEN (headers/ctest/pytest/evidence-no-drift).
- Verifier 2 chiều: 5 RED + happy-path GREEN.
- C++ bypass negatives BLOCKED, sender 0 calls; positive SendOk 1 call.

## WHAT REMAINS UNKNOWN

- Remote Actions (c2m-ci + firmware-evidencemanual) — owner xác nhận.
- Runtime TSR/units/transport/path như cũ; xref sâu vẫn prior work.

## STOCK COMPATIBILITY IMPACT

Zero: chỉ đọc firmware; boundary fail-CLOSED (chặn transmit, không mở thêm).

## PERFORMANCE IMPACT

Không đáng kể (validate chuỗi ngắn/message; verifier chạy theo nhu cầu).

## RISKS

- Shape-allowlist cứng theo 4 template L2 hiện tại; template mới cần update
  policy + parity test (có chủ ý — fail closed).
- Runner GitHub cần liblzo2-dev (đã ghi trong workflow) hoặc minilzo route.

## NEXT HIGHEST-VALUE TASK

Owner đã chỉ rõ: xong delta này thì chuyển sang **EN-device M4 L0/L1 capture**,
không scaffold thêm. ARM cross-build song song.

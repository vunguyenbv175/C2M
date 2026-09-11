# VI Kernel, Media, and Memory Differential V1

## Verdict

The EN and VI kernel images are demonstrably different, and VI introduces an additional 8 MiB framebuffer reservation. However, the available static evidence does not prove that this change starves ADAS, disrupts the media pipeline, or prevents IPU initialization. The causal effect remains **UNKNOWN** pending runtime allocator, media, and IPU evidence.

## Verified kernel identities

### EN

```text
uImage size: 2,255,135 bytes
SHA-256: c1fa8f7363615f1dc7d91f3308608d336fee6d89f5dcfe48e826bf4a399f5030
payload size: 2,255,071 bytes
payload SHA-256: 4c9b8b1ad13cbe8520c7cb18819c1249d22e7733e967f2427e7a7ea87041b665
timestamp: 2023-07-31T12:08:22+00:00
load address: 0x20008000
entry address: 0x20008000
data CRC: valid
```

### VI

```text
uImage size: 2,255,137 bytes
SHA-256: 8261589e10474885277d59fea0a2ad02e079a5b94661a2f4f8f869be29364314
payload size: 2,255,073 bytes
payload SHA-256: cf9f928dc53bd43dc9253634f86c0a159988907cdb7b537b4cfe16e12810b983
timestamp: 2023-09-20T08:38:27+00:00
load address: 0x20008000
entry address: 0x20008000
data CRC: valid
```

The matching load and entry addresses exclude relocation as an observed difference. The differing payload hashes prove distinct kernel builds, but the two-byte compressed-size delta does not measure semantic code change.

## Bootargs and reserved memory

VI adds:

```text
mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000
```

Proven facts:

- The requested region is 8 MiB.
- It is labeled `fb`.
- Its documented address window is `0x3F000000` through `0x3F800000`.
- The delta is VI-only in the recovered bootarg comparison.

Not proven:

- That the framebuffer region overlaps CMA, MIU, IPU, camera, or ring-buffer allocations.
- That the reservation leaves insufficient memory for ADAS.
- That the reservation is consumed at runtime.
- That it changes physical-contiguous allocation order.
- That it is the direct cause of the activation regression.

All causal memory conclusions are therefore **UNKNOWN**.

## Rootfs media stack

The rootfs comparison contains 528 paths per release, with 526 byte-identical files. The only changed rootfs files are:

```text
bootconfig/bin/cardv
bootconfig/modules/4.9.227/sc7a20.ko
```

This strongly limits rootfs-level media ABI drift. The rootfs contains the same named SigmaStar components, including:

```text
mi_ipu.ko
mi_isp.ko
mi_scl.ko
mi_sensor.ko
mi_sys.ko
mi_vif.ko
libmi_ipu.so
libmi_isp.so
libmi_scl.so
libmi_sensor.so
libmi_sys.so
libmi_vif.so
```

Path and rootfs-content equality does not prove that the changed kernel executes these modules identically.

## Camera and ADAS input path

Recovered startup/config evidence identifies:

```text
front sensor: imx415_MIPI.ko chmap=1 i2c_slave_id=0x34
rear decoder: tp9950_MIPI.ko chmap=2 lane_num=2
ADAS camera input: ringbuf_vehicle
ring-buffer name: raw_adas
configured image size: 1920x1440
configured vehicle frequency: 10 Hz
```

The static architecture is therefore:

```text
sensor / VIF / ISP / SCL
        -> cardv frame producer
        -> raw_adas CRingBuf
        -> ADAS CameraReader / RingbufReader
        -> IPU/model processing
```

The producer contract is analyzed separately in `VI_CARDV_RAW_ADAS_DEEP_DIFF_V1.md`.

## IPU and model boundary

Both ADAS trees contain byte-identical user-space IPU firmware, model images, and relevant SigmaStar user-space libraries. The ADAS executable in both releases retains calls to:

```text
MI_SYS_Init
MI_SCL_CreateDevice
IPUCreateDevice
```

This excludes a missing user-space initialization call or changed model weight as the primary static explanation. It does not prove successful VI kernel-side device creation, firmware loading, contiguous allocation, or inference.

Status: **UNKNOWN** until runtime return codes and kernel logs are captured.

## SC7A20 delta

```text
EN size: 24,196 bytes
EN SHA-256: 2d8121dd245d88684a5ece8e5647dfd04571a3184beca2a01fcac7743bbc797a
VI size: 24,204 bytes
VI SHA-256: 5d020616c2b67909a6bc5db19245bfedaf1301d875ae7c117c4d1888de566d64
vermagic: 4.9.227 SMP preempt mod_unload ARMv7 thumb2 p2v8
```

ADAS defaults include `--use_imu_move=true`, so the module remains relevant to motion and warning behavior. No evidence proves that an SC7A20 probe or data failure prevents ADAS startup. Causality is **UNKNOWN**.

## Kernel config and DTB status

A reliable decompressed kernel configuration or DTB semantic comparison was not recovered in this pass. Direct zlib decompression of the uImage payloads failed because compression type 9 is not zlib. No `dtc`, `binwalk`, ARM `objdump`, or vendor decompressor was available in the inspected environment.

Therefore these remain **UNKNOWN**:

- Exact `CONFIG_*` differences.
- Built-in driver differences.
- DTB node, reserved-memory, interrupt, clock, IOMMU, CMA, and media graph differences.
- Whether the bootarg reservation duplicates or conflicts with DTB reservations.

The failure to decode must not be interpreted as evidence that no DTB/config delta exists.

## Ranked kernel/media hypotheses

1. **UNKNOWN, high priority:** contiguous-memory pressure or changed allocation ordering affects `raw_adas` or IPU buffers.
2. **UNKNOWN, high priority:** changed kernel-side VIF/ISP/SCL/IPU behavior prevents frames or device creation.
3. **UNKNOWN, medium priority:** producer startup ordering changes through VI `cardv` despite unchanged writer helpers.
4. **UNKNOWN, medium-low priority:** SC7A20 behavior suppresses motion-dependent activation or warnings.
5. **DOWNGRADED:** changed user-space media libraries, because the rootfs media stack is otherwise byte-identical.
6. **EXCLUDED AS PRIMARY:** changed model weights, because all six embedded model blobs are byte-identical.

## Required runtime evidence

Collect on both EN and VI without modifying persistent state:

```sh
cat /proc/cmdline
cat /proc/meminfo
cat /proc/iomem
cat /proc/buddyinfo
cat /proc/pagetypeinfo
cat /proc/modules
lsmod
ps
dmesg
ls -l /dev
```

Filter logs for:

```sh
dmesg | grep -Ei 'miu|mmap|reserved|cma|mma|ipu|vif|isp|scl|sensor|imx415|tp9950|ring|alloc|fail|error'
```

Capture the return status and logs around `MI_SYS_Init`, `MI_SCL_CreateDevice`, and `IPUCreateDevice`. Also record whether `cardv` creates `raw_adas`, whether frame counters increase, and whether the consumer receives frames.

## Reproduction

From repository root:

```powershell
python tools\fw\vi_adas_failure_evidence.py
Get-FileHash -Algorithm SHA256 build\carve_en\kernel.es.load0.off_00061000.size_22691f.bin
Get-FileHash -Algorithm SHA256 build\vi_carve\kernel.es.load0.off_00061000.size_226921.bin
```

Canonical hashes and finding status are recorded in:

```text
docs/reverse/EVIDENCE_VI_ADAS_FAILURE.json
```

## Conclusion

The kernel/media/memory boundary is the highest-priority unresolved area because the kernel is different and VI adds a concrete memory reservation while the user-space media stack is nearly unchanged. Nevertheless, no static evidence proves memory starvation, media failure, or IPU failure. The root cause remains **UNKNOWN** until runtime evidence identifies the first failing boundary.
# 09 — EN/VI ADAS Regression Bisect Plan

## Objective

Find the smallest component delta that changes:

```text
ADAS works
```

to:

```text
ADAS does not work
```

without repeatedly full-flashing NAND.

## Before testing

Required:
- preserve full EN working image,
- backup persistent config,
- collect boot/process/log baseline,
- have a tested restore method,
- avoid bootloader/kernel writes during early bisect.

## Stage 1 — classify VI failure

On full VI, determine whether the problem is:

```text
1. adas_service never launches
2. guard launches but adas exits
3. adas stays alive
4. raw_adas/ringbuf input absent
5. IPU init fails
6. calibration/license rejected
7. inference exists but output is absent
8. screen/audio path only is broken
```

Commands/logs should include:

```sh
ps
dmesg
logread 2>/dev/null
cat /proc/meminfo
cat /proc/cmdline
lsmod
ss -lntup
netstat -anp
```

plus all MINIEYE logs.

## Stage 2 — binary A/B on working EN base

Safest high-value test:

```text
EN kernel
EN rootfs/cardv
EN customer libraries/models/config
+
VI adas executable only
```

Do not overwrite the only copy.

Run from a temporary path or make a reversible backup.

Interpretation:

```text
VI adas fails on EN base
=> primary defect is in VI adas executable/overlay or its interpretation of persistent config

VI adas works on EN base
=> defect depends on VI cardv/kernel/modules/integration
```

## Stage 3 — cardv A/B

If VI adas works on EN base, test VI `cardv` with extreme care because it owns media/recording/display.

Preferred first step:
- static function diff,
- log/IPC comparison,
- do not overwrite boot rootfs on first experiment.

If runtime substitution is feasible in RAM, use that.

## Stage 4 — config/license A/B

Use copies of:
- adas_de.flag,
- calib_de.flag,
- produce_de.flag,
- license files.

Do not mutate originals.

Compare behavior and logs using EN vs VI executable.

## Stage 5 — kernel/module boundary

Only after userspace is largely excluded.

Compare:
- raw_adas creation,
- IPU driver behavior,
- SC7A20,
- framebuffer reservation,
- USB/M4.

Avoid flashing U-Boot solely for this test.

## Stage 6 — M4/output isolation

If inference appears alive:

- disconnect M4,
- inspect ScreenService port 26012,
- inspect output messages,
- verify whether ADAS is actually working but invisible.

## Evidence table format

Every experiment:

```text
Test ID
Base firmware
adas binary
cardv binary
kernel
config hash
M4 connected?
process state
frame input state
IPU state
ScreenService state
observed result
logs
conclusion
```

Never rely on “seems to work”.

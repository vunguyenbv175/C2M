# 05 — Camera, Media, Sensor and IMU Path

## Front/rear camera evidence

The `oneed_cust` startup assets indicate:

```text
imx415_MIPI.ko chmap=1 i2c_slave_id=0x34
tp9950_MIPI.ko chmap=2 lane_num=2
```

Working interpretation:

```text
front: Sony IMX415 MIPI
rear:  TP9950 analog-HD decoder -> MIPI
```

Do not replace these drivers in the enhancement project unless necessary.

## ADAS input path

Default ADAS flags:

```text
--camera_input=ringbuf_vehicle
--ringbuf_name=raw_adas
--image_width=1920
--image_height=1440
--vehicle_run_freq=10
```

This implies ADAS does not simply own the physical sensor directly; it consumes a ring-buffered camera path.

That makes `cardv` / shared media plumbing highly relevant.

## Why VI `cardv` is a regression suspect

Models and most ADAS dependencies remain identical, while `cardv` changes.

Coding agent should locate:

```text
raw_adas
ringbuf_vehicle
camera producer
frame format
stride
timestamp
pixel format
frame dimensions
producer startup order
```

in both cardv builds.

A subtle producer-format/timing change could make ADAS appear completely dead while recording continues.

## NPU/IPU

Both ADAS trees contain identical:

```text
ipu_firmware.bin
params/model.img
```

and identical SigmaStar/IPU user-space libraries used by ADAS.

Therefore a changed AI model is not currently the leading explanation for VI failure.

However the kernel itself changes, so low-level IPU driver behavior still needs runtime validation.

## IMU/G-sensor

ADAS defaults include:

```text
--use_imu_move=true
```

and the distribution contains IMU/harsh-warning/drive-state libraries.

The SC7A20 driver changed between EN and VI.

VI also changes the web/config key:

```text
EN: Camera.Menu.GSensorSensitivity
VI: Camera.Menu.GSensor
```

and `CGI_PROCESS.sh` changes the corresponding nvconf write.

This appears intentional, but it is a real semantic config delta.

## Runtime data collection

On EN and VI, capture:

```sh
dmesg
lsmod
cat /proc/meminfo
cat /proc/cmdline
ps
ls -l /dev
```

and ADAS-specific logs.

Record:
- camera producer process,
- ringbuffer creation,
- frame arrival,
- IPU init status,
- SC7A20 probe,
- calibration state,
- ADAS restart loop.

## Failure triage

Classify “ADAS not working” into one of:

```text
A. process never starts
B. process starts then crashes
C. process stays alive but no frames
D. frames arrive but NPU/model init fails
E. inference works but warnings are suppressed
F. ADAS works internally but screen/audio output fails
```

This classification should precede any code replacement.

# 07 — Persistent Config, License and Calibration

## Most important fact

`/customer/minieye/config` is deliberately persistent across vendor full firmware upgrade.

`adas_upgrade.sh` backs it up and restores it.

The customer image itself contains only:

```text
/customer/minieye/config/.gitkeep
```

So production units receive/retain device-specific state outside the generic customer image.

## ADAS required files

`run.sh` requires:

```text
/customer/minieye/config/adas.flag
/customer/minieye/config/calib.flag
```

It base64-decodes them to:

```text
adas_de.flag
calib_de.flag
```

If either required source file is absent, startup exits.

It also checks:

```text
--enable_vehicle=
```

and exits when vehicle is explicitly disabled.

## Runtime flag layering

The lane processes use:

```text
built-in detect.flag
+
adas_de.flag
+
calib_de.flag
```

The main ADAS executable also references:

```text
switch_file=/customer/minieye/config/adas_de.flag
calib_file=/customer/minieye/config/calib_de.flag
produce_file=/customer/minieye/config/produce_de.flag
license_root_path=/customer/minieye/config
```

Therefore per-device provisioning is central to behavior.

## License/integrity

Files/scripts include:

```text
adas_checksn.sh
adas_checkcalib.sh
adas_license_restore.sh
mutualism.checksn.txt
mutualism.restoresn.txt
libadas_license_helper.so
BitAnswer/license-related strings inside ADAS
```

The scripts and helper files compared in the ADAS subtree are mostly identical across EN/VI.

But the VI ADAS executable itself changed, so internal validation logic may have changed.

## Regression interpretation

If the same physical device/config was preserved while switching VI -> EN:

- missing config alone is unlikely,
- a new code path interpreting the same config differently remains plausible,
- a new license rule inside VI remains plausible,
- calibration compatibility remains plausible.

## Must collect from the physical device

Read-only backup:

```sh
mkdir -p /mnt/mmc/c2m_backup/config
cp -a /customer/minieye/config /mnt/mmc/c2m_backup/config/
cp -a /config/cgi_config.bin /mnt/mmc/c2m_backup/
cp -a /config/net_config.bin /mnt/mmc/c2m_backup/
```

Then decode copies, not originals:

```sh
base64 -d adas.flag > adas_de.flag.copy
base64 -d calib.flag > calib_de.flag.copy
```

Record:
- hashes,
- exact flags,
- calibration camera parameters,
- license files,
- feature switches.

Do not publish secrets/device serial/license material in public GitHub.

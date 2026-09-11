# VI Calibration and Persistent-State Path V1

## Verdict

The EN and VI startup and calibration-check scripts are byte-identical. Both require persistent device-specific `adas.flag` and `calib.flag` inputs, decode them into runtime flags, and can suppress startup when vehicle detection is disabled. Whether the VI executable interprets the preserved calibration or feature state incompatibly remains **UNKNOWN** because the physical device configuration was not available.

## Proven persistent-state behavior

The vendor upgrade process preserves:

```text
/customer/minieye/config
/config/cgi_config.bin
/config/net_config.bin
```

The generic customer image contains only a placeholder under the ADAS config directory. Operational calibration, license, and feature state is therefore device-specific rather than supplied as a complete generic default.

## Startup-script identity

The extracted EN and VI `run.sh` files are byte-identical:

```text
size: 1,584 bytes
SHA-256: 796e555a276d849737b8034021e1464a8241ed291a332ef5a61b767d9ab860e4
```

Reproducible extraction reports:

```text
build/run_en.extract.json
build/run_vi.extract.json
```

The script requires:

```text
/customer/minieye/config/adas.flag
/customer/minieye/config/calib.flag
```

If either file is absent, startup exits with status 1. When present, the files are base64-decoded into:

```text
/customer/minieye/config/adas_de.flag
/customer/minieye/config/calib_de.flag
```

The script compares the MD5 of decoded source content against the existing decoded file and replaces the decoded file when they differ.

## Proven activation gate

The startup script searches `adas_de.flag` for:

```text
--enable_vehicle=
```

If the value is exactly `false`, the script exits without launching the ADAS mutualism process. This is a proven activation gate shared by EN and VI.

The identical script excludes a release-specific shell-script regression as the primary cause. It does not exclude different persisted values or different interpretation by the VI executable.

## Runtime flag layering

Recovered configuration references show the stock pipeline combines:

```text
built-in detect.flag
+ adas_de.flag
+ calib_de.flag
```

The main executable also references:

```text
switch_file=/customer/minieye/config/adas_de.flag
calib_file=/customer/minieye/config/calib_de.flag
produce_file=/customer/minieye/config/produce_de.flag
license_root_path=/customer/minieye/config
```

This proves that switch, calibration, production, and license state converge under the same persistent directory.

## Calibration-check script identity

The extracted EN and VI `adas_checkcalib.sh` files are byte-identical:

```text
size: 1,145 bytes
SHA-256: 518f22e98842eb8a6c315d0a29098c885f0d2c942c4690154ddc730034b3d8c4
```

Reproducible extraction reports:

```text
build/checkcalib_en.extract.json
build/checkcalib_vi.extract.json
```

A release-specific change to this script is therefore excluded. Runtime inputs and executable behavior remain open.

## Compatibility assessment

### Proven

- EN and VI use the same startup script.
- EN and VI use the same calibration-check script.
- Both require `adas.flag` and `calib.flag`.
- Both regenerate decoded files when content hashes differ.
- Both suppress startup when `--enable_vehicle=false` is present.
- Vendor upgrade behavior preserves the persistent configuration directory.

### Downgraded

- Missing generic calibration defaults as the sole explanation. The same physical unit later ran EN successfully while persistent state was designed to survive upgrades.
- A changed EN-versus-VI shell gate. The relevant scripts are byte-identical.

### UNKNOWN

- Exact contents and hashes of the device's source and decoded flags.
- Whether base64 decoding succeeded on the VI boot.
- Whether stale decoded files existed before startup.
- Whether VI accepts the same intrinsic and extrinsic calibration ranges as EN.
- Whether camera geometry, horizon, mounting height, pitch, yaw, or vanishing-point values were rejected.
- Whether `produce_de.flag` existed and was compatible.
- Whether license or feature files under the same root changed behavior.
- Whether the VI executable reached calibration initialization or failed earlier at media/IPU startup.

## License and feature-state interaction

Static analysis strongly downgrades a changed BitAnswer implementation because compared login, feature-read, checkout, path, and dispatcher functions are byte-identical. The same code can still produce different results when supplied with different device UUID, custom-info, volume, license, or feature data.

Therefore:

```text
changed license implementation: DOWNGRADED
runtime license or feature-state incompatibility: UNKNOWN
```

No serial number, license secret, or device-specific credential should be committed or published.

## Safe runtime evidence collection

Operate on copies only:

```sh
mkdir -p /mnt/mmc/c2m_backup/config
cp -a /customer/minieye/config /mnt/mmc/c2m_backup/config/
cp -a /config/cgi_config.bin /mnt/mmc/c2m_backup/
cp -a /config/net_config.bin /mnt/mmc/c2m_backup/
```

Generate a private file inventory:

```sh
find /mnt/mmc/c2m_backup/config -type f -exec sha256sum {} \;
```

Decode copies, never originals:

```sh
cd /mnt/mmc/c2m_backup/config/config
base64 -d adas.flag > adas_de.flag.copy
base64 -d calib.flag > calib_de.flag.copy
```

Record, with secrets redacted:

- File presence, size, mode, owner, and SHA-256.
- Base64 decoder exit status.
- `--enable_vehicle` and other non-secret feature switches.
- Image width, height, camera ID, and calibration geometry.
- Calibration parser return codes and logs.
- License login and feature-query status without exposing credentials.
- Whether the process exits before or after media/IPU initialization.

## Failure discrimination

Interpret results as follows:

```text
required file absent or decode failure
  => startup/config failure

--enable_vehicle=false
  => explicit activation suppression

files decode identically but VI rejects calibration
  => executable-to-persistent-state compatibility failure

calibration accepted but no raw_adas frames
  => producer/media/kernel boundary

frames and calibration valid but no IPU initialization
  => kernel/IPU/memory boundary

inference active but no warning/display output
  => feature gate, warning policy, audio, or display boundary
```

## Reproduction

From repository root:

```powershell
python tools\fw\ubifs_extract_file.py build\carve_en\customer.es.load0.off_00c5d000.size_25e7000.bin /minieye/adas/run.sh -o build\run_en.sh --report build\run_en.extract.json
python tools\fw\ubifs_extract_file.py build\vi_carve\customer.es.load0.off_00c5d000.size_25e7000.bin /minieye/adas/run.sh -o build\run_vi.sh --report build\run_vi.extract.json
Get-FileHash -Algorithm SHA256 build\run_en.sh,build\run_vi.sh

python tools\fw\ubifs_extract_file.py build\carve_en\customer.es.load0.off_00c5d000.size_25e7000.bin /minieye/adas/adas_checkcalib.sh -o build\checkcalib_en.sh --report build\checkcalib_en.extract.json
python tools\fw\ubifs_extract_file.py build\vi_carve\customer.es.load0.off_00c5d000.size_25e7000.bin /minieye/adas/adas_checkcalib.sh -o build\checkcalib_vi.sh --report build\checkcalib_vi.extract.json
Get-FileHash -Algorithm SHA256 build\checkcalib_en.sh,build\checkcalib_vi.sh
```

Canonical finding status and input hashes are stored in:

```text
docs/reverse/EVIDENCE_VI_ADAS_FAILURE.json
```

## Conclusion

The static calibration path is unchanged at the shell-script level, but it depends on persistent device-specific inputs. A VI calibration or feature-state incompatibility remains a leading unresolved hypothesis, not a proven cause. The next decisive step is a private, read-only comparison of decoded flags, parser results, and failure ordering on the physical device.
# `tools/wifi/rtl8821cs_profiles` — offline build profiles

Small, self-authored `Makefile` patches used by
`tools/wifi/build_rtl8821cs_lab.sh` to build the pinned public RTL8821CS
driver in two configurations. The **entire driver source is fetched at build
time** from the pinned public URL; only these small patches are committed.

## Pinned source (not committed here)

* `https://github.com/leavs/rtl8821cs` @ `d0336d198c7dc050fd5a14c6ae6ac3c74d7112f2`
* archive SHA-256 `f7f6cdf34260f55bbca7ad0e3ce5959f4f8ee41dead30d1ee52ae1255c85347e`
* `include/rtw_version.h` SHA-256 `aae92ac00973d72e56b7b03023c2aa1184e1e0a53b914e0995be00ca6dc39e53`
* version string `v5.14.2-28-g6011b0372.20220328`
* driver `Makefile` SHA-256 `dbe35f90f5fb7a14c91e595db8cf12249d64493bdb069da0016d92be6e940b5d`

## Profiles

| profile | file | effect |
| --- | --- | --- |
| baseline | `baseline/Makefile.patch` | disable stock RK3188 default (which forces `-DCONFIG_CONCURRENT_MODE` + Android/Rockchip), add minimal `CONFIG_PLATFORM_C2M` (SDIO + cfg80211 only) → `CONFIG_IFACE_NUMBER = 1` |
| concurrent | `concurrent/Makefile.patch` | same, plus `-DCONFIG_CONCURRENT_MODE` → `CONFIG_IFACE_NUMBER = 2`, same-channel (`.num_different_channels = 1`) |

`*/c2m.flags` records the derived `EXTRA_CFLAGS` set (documentation only; the
build derives flags from the patched `Makefile`, not from these files).

The patches are plain unified diffs; the build applies them with
`patch --batch --forward -p1` to a fresh extraction of the pinned archive.
They were verified to apply cleanly (`git apply --check -p1`) against the
pinned source.

## License handling

The patch context lines are a handful of lines quoted from the Realtek
GPLv2 driver `Makefile`. The full file is GPLv2 and is fetched, not
redistributed, here. See the source provenance note
`docs/firmware/RTL8821CS_SOURCE_PROVENANCE_20261018.md` in this repository.

## Not a camera ABI

These profiles only select the *driver-side* macro set. They are **not** the
camera's vendor kernel configuration and produce **no camera-compatible**
module. `NOT_CAMERA_ABI`, `NO_LOAD_EVER`.

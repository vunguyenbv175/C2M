# RTL8821CS source provenance — 2026-10-18

## Result and boundary

An accessible public standalone source archive has now been downloaded and checked with the **same driver version string** as the installed camera module:

```text
v5.14.2-28-g6011b0372.20220328
```

This supersedes the earlier failed neardi-source search as the available research baseline. It **does not** establish that this mirror reproduces the camera's downstream patches, compile configuration, kernel structure layout or binary. No candidate module has been built/loaded on the camera.

## Primary pinned source

- Repository: https://github.com/leavs/rtl8821cs
- Commit: `d0336d198c7dc050fd5a14c6ae6ac3c74d7112f2`
- Archive: https://codeload.github.com/leavs/rtl8821cs/tar.gz/d0336d198c7dc050fd5a14c6ae6ac3c74d7112f2
- Archive SHA-256: `f7f6cdf34260f55bbca7ad0e3ce5959f4f8ee41dead30d1ee52ae1255c85347e`
- `include/rtw_version.h`: `aae92ac00973d72e56b7b03023c2aa1184e1e0a53b914e0995be00ca6dc39e53`
- `include/drv_conf.h`: `997eea79909bbcb520493441e803fe5df97ed36ea8b935610c46e6c8a734efce`
- `include/autoconf.h`: `7470f2b517425fc27955e607b215242ea3796d105d0d1e172102152a139aa6d6`
- `Makefile`: `dbe35f90f5fb7a14c91e595db8cf12249d64493bdb069da0016d92be6e940b5d`

The parent independently rehashed the downloaded archive and extracted version-header bytes in memory and checked the exact version text. No archive source/binary bytes from the camera are redistributed here.

## Additional cross-checks reported by source research

- https://github.com/jack935321350/rtl8821cs at `0af809cdac1d10511d15788755f90979c4445f6b`
  - Archive SHA-256: `e9e3e3a87dfb44731ff139d82c2b2ad26ec3dfd6efcbf55b11924843b2f32cdb`
  - Version/config/autoconf header hashes match the primary pin; downstream source/Makefile differences remain and must not be ignored.
- https://github.com/zouxf/linux-rockchip at `be5f28943310dec69d090a34342797f5b61f7af9`
  - Path: `drivers/net/wireless/rockchip_wlan/rtl8821cs/`
  - Key files were fetched, not the complete kernel tree. Reported version/config-header agreement is corroboration of source lineage, not independent vendor-camera provenance.

These are public mirrors of related source, not three independent attestations of the camera's actual build.

## License and handling

Representative source headers state GPL version2. The source research found GPL notices in many files but no standalone LICENSE file. Review per-file notices before redistribution; do not assume every bundled file has been legally audited from a count of matching notices. Only URL/hash metadata is committed here. Downloaded research artifacts remain outside the repository.

## Explicitly nonmatching or unverified sources

- Inspected `milkv-duo/duo-buildroot-sdk` and `knulli-cfw/rtl8821cs` source versions were5.12.0, not the installed5.14.2; they are context only, not a replacement pin.
- `git.neardi.com/...@808d6627f5cd48c123b7e3114429fd126a9abe43` could not be retrieved/verified in the research environment. Do not cite that commit as confirmed.

## Mercury6 SDK research follow-up

Public material now identifies the Mercury6 SDK family as **TIRAMISU**, with documentation referencing Linux4.9.227 and the GCC9.1.0-2020.07 ARM toolchain. A retrieved public userspace SDK readme at `qanthink/skyipc_tiramisu@afab3dda8beff0c89f10ee4ad1d0eb0152650abd/soc_sdk/readme.txt` explicitly names `tiramisuV012_20220606_usb` and describes copying release headers/libraries from that SDK.

This is a useful lead toward the correct vendor SDK, **not a matching kernel source drop**. Public userspace MI headers/libraries do not determine kernel module structure layout or prove ABI reproducibility. The exact camera vendor kernel configuration and downstream tree remain unavailable in the artifacts obtained so far. Searches that did not find a public mirror cannot prove one does not exist; authenticated code-search channels were not available in part of this research.

Reference URLs:
- https://github.com/qanthink/skyipc_tiramisu/tree/afab3dda8beff0c89f10ee4ad1d0eb0152650abd
- https://wx.comake.online/doc/doc/SigmaStarDocs-SSD268-SIGMASTAR-202305231823/
- https://github.com/linux-chenxing/linux-chenxing.org

No compiler binary was downloaded/executed from an unverified mirror. Do not install a whole IPC image or substitute Infinity6E solely because its public kernel is easier to obtain.

## Engineering next steps

1. Derive a single-interface baseline from the verified public source and compare its selected macros/platform flags with the live driver report.
2. Prepare a separate minimal concurrent-mode profile, preserving baseline features and documenting same-channel limits. This is offline source preparation only.
3. Obtain/validate matching Mercury6 4.9.227 generated headers/config and kernel ABI. Reconstructed generic headers/identical vermagic are insufficient proof of safe loading.
4. Compare candidate metadata with the pinned stock module using `tools/fw/module_abi_report.py`, including exports and actual target attributes; no result from that tool alone authorizes a load.
5. Establish AP-independent recovery before a separately reviewed hardware driver test. No live driver change has occurred in this investigation.

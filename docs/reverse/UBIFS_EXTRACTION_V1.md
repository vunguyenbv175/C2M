# Self-contained UBIFS single-file extraction V1

## Purpose

Make C2M firmware analysis reproducible from the original vendor images without requiring an external `ubi_reader` installation or mounting UBIFS.

Tool: `tools/fw/ubifs_extract_file.py`.

It is read-only: it scans an already-carved raw UBIFS image and reconstructs one regular file.

## Supported stock C2M data paths

The C2M `customer` image uses ordinary UBIFS inode/dentry/data nodes. The extractor selects the highest-sequence-number node for each inode/key/block and supports:

```text
compression 0: none
compression 1: LZO1X through system liblzo2
compression 2: zlib
compression 3: zstd when Python zstandard is installed
```

## Reproduction

After carving the vendor upgrade image, extract the stock ADAS executable from the customer UBIFS payload:

```sh
python3 tools/fw/ubifs_extract_file.py \
  <customer.ubifs> \
  /minieye/adas/adas \
  -o adas \
  --report adas_extract.json
```

## Verified against both vendor builds

### EN known-good

```text
path: /minieye/adas/adas
inode: 136
size: 11,636,008
SHA-256: 0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043
data blocks: 2,841
compression blocks: none 1,701; LZO 1,140
```

### VI regression/donor

```text
path: /minieye/adas/adas
inode: 199
size: 11,653,870
SHA-256: 997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1
data blocks: 2,846
compression blocks: none 1,702; LZO 1,144
```

The reconstructed sizes, hashes and ELF Build IDs match the binaries used in the existing reverse reports.

## Scope / limitations

This is deliberately a small forensic extractor, not a general UBIFS repair/repack implementation. It must not be used to rewrite stock UBIFS.

## Confidence

- **CONFIRMED:** reproduces exact EN/VI `adas` binaries from original vendor customer images.
- **CONFIRMED:** read-only with respect to firmware input.
- **HIGH-CONFIDENCE:** sufficient for the current C2M regular-file extraction workflow.

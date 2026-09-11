#!/usr/bin/env python3
"""Decode the C2M ADAS --m0 encrypted model directory.

Static reverse evidence shows vehicle::GetKey() returns a 32-hex-character
AES-128 key assembled from two embedded 16-char literals. DecryptNum() parses
one 32-char hex block, AES-ECB decrypts 16 bytes, and returns the last four
plaintext bytes as a big-endian uint32.

The 384-hex-character m0 therefore contains 12 encrypted uint32 values, paired
as six (offset, size) records. With --model-txt they are labelled in the stock
model.txt order. This is analysis tooling only; it never modifies firmware.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

DEFAULT_KEY_HEX = "de091ce6cb35733540c86656fa1692e8"


def tail_flags(data: bytes) -> dict[str,str]:
    marker=b"--switch_file="
    start=data.rfind(marker)
    if start < 0:
        raise ValueError("--switch_file marker not found")
    text=data[start:].decode("ascii")
    out={}
    for line in text.splitlines():
        if line.startswith("--") and "=" in line:
            k,v=line[2:].split("=",1); out[k]=v
    return out


def aes_decrypt_blocks(m0_hex: str, key_hex: str) -> list[dict]:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as e:
        raise SystemExit("cryptography is required: pip install cryptography") from e
    if len(m0_hex) % 32:
        raise ValueError("m0 length is not a multiple of one AES block (32 hex chars)")
    key=bytes.fromhex(key_hex)
    if len(key)!=16:
        raise ValueError("expected 16-byte AES-128 key")
    dec=Cipher(algorithms.AES(key),modes.ECB()).decryptor()
    rows=[]
    for i in range(0,len(m0_hex),32):
        ct=bytes.fromhex(m0_hex[i:i+32])
        pt=dec.update(ct)
        rows.append({
            "block": i//32,
            "ciphertext_hex": ct.hex(),
            "plaintext_hex": pt.hex(),
            "value": int.from_bytes(pt[-4:],"big"),
            "value_hex": hex(int.from_bytes(pt[-4:],"big")),
        })
    return rows


def model_names(path: Path|None, n: int) -> list[str]:
    if path is None: return [f"model_{i}" for i in range(n)]
    names=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if line: names.append(line.split()[0])
    if len(names)!=n:
        raise ValueError(f"model.txt has {len(names)} names, expected {n}")
    return names


def report(binary: Path, model_txt: Path|None, key_hex: str):
    data=binary.read_bytes(); flags=tail_flags(data)
    m0=flags.get("m0")
    if not m0: raise ValueError("m0 flag missing")
    blocks=aes_decrypt_blocks(m0,key_hex)
    if len(blocks)%2: raise ValueError("m0 does not contain offset/size pairs")
    names=model_names(model_txt,len(blocks)//2)
    recs=[]
    for i,name in enumerate(names):
        off=blocks[2*i]["value"]; size=blocks[2*i+1]["value"]
        end=off+size
        blob=data[off:end]
        recs.append({
            "index":i,"name":name,
            "offset":off,"offset_hex":hex(off),
            "size":size,"size_hex":hex(size),
            "end":end,"end_hex":hex(end),
            "in_file": end<=len(data),
            "sha256": hashlib.sha256(blob).hexdigest() if end<=len(data) else None,
            "head16_hex": blob[:16].hex() if end<=len(data) else None,
            "tail16_hex": blob[-16:].hex() if end<=len(data) and blob else None,
        })
    return {
        "binary":str(binary),"file_size":len(data),
        "tail_size_from_switch_file":len(data)-data.rfind(b"--switch_file="),
        "m0_hex_length":len(m0),"aes_key_hex":key_hex,
        "blocks":blocks,"records":recs,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("binary",type=Path)
    ap.add_argument("--model-txt",type=Path)
    ap.add_argument("--key-hex",default=DEFAULT_KEY_HEX)
    ap.add_argument("-o","--output",type=Path)
    args=ap.parse_args()
    r=report(args.binary,args.model_txt,args.key_hex)
    s=json.dumps(r,indent=2)
    if args.output: args.output.write_text(s,encoding="utf-8")
    print(s)
if __name__=="__main__": main()

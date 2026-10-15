#!/usr/bin/env python3
"""Narrow pinned Dropbear auth to the server UID, without bypassing checks.

DROPBEAR_SVR_MULTIUSER must stay enabled on a normal Linux kernel. This
small reviewed policy change only REMOVES root's permission to authenticate
as other UIDs; account/shell, key signature, group and privilege checks remain.
Only use on the independently SHA256-pinned Dropbear 2026.94 source.
"""
from pathlib import Path
import argparse

OLD = 'if (!(DROPBEAR_SVR_MULTIUSER && uid == 0) && uid != ses.authstate.pw_uid) {'
NEW = 'if (uid != ses.authstate.pw_uid) { /* C2M_DEBUG_SAME_UID_ONLY */'


def apply(source: Path) -> None:
    target = source / 'src/svr-auth.c'
    if source.is_symlink() or target.is_symlink() or not target.is_file():
        raise ValueError('debug auth patch requires a regular pinned source tree')
    data = target.read_bytes()
    old, new = OLD.encode('ascii'), NEW.encode('ascii')
    if data.count(old) != 1 or new in data:
        raise ValueError('debug auth narrowing context mismatch/already patched')
    target.write_bytes(data.replace(old, new, 1))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    apply(args.source)
    print('DEBUG-AUTH-POLICY: server-UID-only narrowing applied (all other checks preserved)')

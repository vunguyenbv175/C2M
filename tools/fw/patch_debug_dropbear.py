#!/usr/bin/env python3
"""Apply two explicit C2M policies to SHA256-pinned Dropbear 2026.94.

1. Keep MULTIUSER enabled for normal Linux, but restrict login to server UID.
2. Permit only the exact known /tmp ancestor policy used by the supervisor:
   root-owned sticky /tmp, or stock EN /tmp mode0775 uid/gid1001. Every
   private child and authorized_keys file retains upstream permission checks.

No account/shell, key signature, group or privilege checks are bypassed.
The vendor UID1001 trust is inherited from root-run stock firmware, NOT a
hardened security boundary against a hostile local vendor-UID process.
"""
from pathlib import Path
import argparse

OLD = 'if (!(DROPBEAR_SVR_MULTIUSER && uid == 0) && uid != ses.authstate.pw_uid) {'
NEW = 'if (uid != ses.authstate.pw_uid) { /* C2M_DEBUG_SAME_UID_ONLY */'
PERM_OLD = 'if (filestat.st_mode & (S_IWGRP | S_IWOTH)) {'
PERM_NEW = '''if ((filestat.st_mode & (S_IWGRP | S_IWOTH)) &&
        !(strcmp(filename, "/tmp") == 0 && S_ISDIR(filestat.st_mode) &&
          ((filestat.st_uid == 0 && (filestat.st_mode & S_ISVTX)) ||
           (filestat.st_uid == 1001 && filestat.st_gid == 1001 &&
            (filestat.st_mode & 07777) == 0775)))) {
        /* C2M_DEBUG_TMP_ANCESTOR: private children remain checked. */'''
OWNER_OLD = '''if (filestat.st_uid != ses.authstate.pw_uid
\t\t\t&& filestat.st_uid != 0) {'''
OWNER_NEW = '''if (filestat.st_uid != ses.authstate.pw_uid
\t\t\t&& filestat.st_uid != 0 &&
\t\t\t!(strcmp(filename, "/tmp") == 0 && S_ISDIR(filestat.st_mode) &&
\t\t\t  filestat.st_uid == 1001 && filestat.st_gid == 1001 &&
\t\t\t  (filestat.st_mode & 07777) == 0775)) {'''


def apply(source: Path) -> None:
    auth = source / 'src/svr-auth.c'
    perms = source / 'src/svr-authpubkey.c'
    if source.is_symlink() or any(p.is_symlink() or not p.is_file() for p in (auth, perms)):
        raise ValueError('debug auth patch requires a regular pinned source tree')
    auth_data = auth.read_text(encoding='utf-8')
    perm_data = perms.read_text(encoding='utf-8')
    for data, old, new in ((auth_data, OLD, NEW), (perm_data, PERM_OLD, PERM_NEW),
                           (perm_data, OWNER_OLD, OWNER_NEW)):
        if data.count(old) != 1 or new in data:
            raise ValueError('debug restrictive auth context mismatch/already patched')
    # Validate all contexts before writing either upstream source file.
    auth.write_text(auth_data.replace(OLD, NEW, 1), encoding='utf-8', newline='\n')
    perms.write_text(perm_data.replace(PERM_OLD, PERM_NEW, 1).replace(OWNER_OLD, OWNER_NEW, 1),
                     encoding='utf-8', newline='\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    apply(args.source)
    print('DEBUG-AUTH-POLICY: same-UID narrowing and exact /tmp ancestor policy applied')

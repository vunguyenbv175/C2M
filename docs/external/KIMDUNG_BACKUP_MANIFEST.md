# KimDung upstream backup manifest (metadata/reference only)

Date (UTC): 2026-09-11. Local mirrors live OUTSIDE this repo
(`D:\CODE\backups\`); private GitHub mirrors under `vunguyenbv175`.
No upstream source or binary is committed here.

## kimdung/promax

- upstream: `https://github.com/kimdung/promax.git`
- backup date: 2026-09-11T09:42:16Z
- upstream HEAD SHA: `fd581971ac86475763e1ac0380e9f5cb8c0630e6` (`main`)
- branches: 1 (`main`); tags: 0
- LFS: no (`.gitattributes` absent in history, no LFS pointers at HEAD)
- releases/assets: no (`gh release list` empty)
- firmware in git: yes (`firmware/*.bin` tracked directly, preserved in mirror; 489 objects, 59.05 MiB pack)
- backup repo (private): `https://github.com/vunguyenbv175/kimdung-promax-backup` (HEAD verified identical)
- archive SHA256: `988239fee6e3a6dddf632d3ee1c6e22ded29a7b51b080f5d8b2b2f01798e9f4d` (`kimdung-promax-git-mirror.tar.gz`)

## kimdung/promax_xl

- upstream: `https://github.com/kimdung/promax_xl.git`
- backup date: 2026-09-11T09:42:16Z
- upstream HEAD SHA: `f678b2c25b90df0989fa0ae2bf9e954b3de662ac` (`main`)
- branches: 1 (`main`); tags: 0
- LFS: no (`.gitattributes` absent in history, no LFS pointers at HEAD)
- releases/assets: no (`gh release list` empty)
- firmware in git: yes (`firmware/*.bin` tracked directly, preserved in mirror; 556 objects, 61.13 MiB pack)
- backup repo (private): `https://github.com/vunguyenbv175/kimdung-promax-xl-backup` (HEAD verified identical)
- archive SHA256: `937531ac86943f41d5f01da4146eab0a817e2190ca9c65933036ce3c7367788b` (`kimdung-promax-xl-git-mirror.tar.gz`)

## Verification performed per repo

`git clone --mirror`, `git fsck --full` (clean), `git show-ref`,
`git branch -a`, `git tag -l`, `git count-objects -vH`, LFS/`.gitattributes`
check, `gh release list`, `git push --mirror` + `git ls-remote` HEAD match,
`tar -czf` + SHA256. No source edits, no history rewrite, no filtering.

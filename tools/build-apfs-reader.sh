#!/bin/sh
# Optional, local build only. Keep full source/licenses with any distributed binary.
set -eu
: "${FREEQNAP_APFS_SOURCE:?Pinned apfs-fuse checkout with lzfse submodule required}"
: "${FREEQNAP_APFS_OUTPUT:?New build directory required}"
[ ! -e "$FREEQNAP_APFS_OUTPUT" ]
[ "$(git -C "$FREEQNAP_APFS_SOURCE" rev-parse HEAD)" = 66b86bd525e8cb90f9012543be89b1f092b75cf3 ]
[ "$(git -C "$FREEQNAP_APFS_SOURCE/3rdparty/lzfse" rev-parse HEAD)" = e634ca58b4821d9f3d560cdc6df5dec02ffc93fd ]
git -C "$FREEQNAP_APFS_SOURCE" diff --quiet
git -C "$FREEQNAP_APFS_SOURCE" diff --cached --quiet
git -C "$FREEQNAP_APFS_SOURCE/3rdparty/lzfse" diff --quiet
# This small GPL-source adjustment permits a private pipe instead of password argv.
python3 - "$FREEQNAP_APFS_SOURCE/ApfsLib/Util.cpp" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.read_text();needle='bool GetPassword(std::string &pw)\n{'
assert s.count(needle)==1 and 'FREEQNAP_PASSWORD_STDIN' not in s
s=s.replace('#include <stdio.h>','#include <stdio.h>\n#include <cstdlib>')
s=s.replace(needle,needle+'\n\tif (std::getenv("FREEQNAP_PASSWORD_STDIN")) { std::getline(std::cin, pw); return !std::cin.fail(); }')
p.write_text(s)
PY
cmake -S "$FREEQNAP_APFS_SOURCE" -B "$FREEQNAP_APFS_OUTPUT" -DUSE_FUSE3=ON -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build "$FREEQNAP_APFS_OUTPUT" --target apfs-fuse -j2
sha256sum "$FREEQNAP_APFS_OUTPUT/apfs-fuse"
printf 'Private build only: test a software-encrypted APFS fixture before claiming acceptance.\n'

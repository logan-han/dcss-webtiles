#!/usr/bin/env python3
"""Fail if deploy/oci/cloud-init.yaml's inline copies differ from the files they were copied from.

cloud-init only runs when an instance is created, so a copy that has drifted would only show up on a rebuild.

  python tools/check_cloud_init.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

CLOUD_INIT = Path("deploy/oci/cloud-init.yaml")
COPIES = {
    "/opt/dcss/compose.yaml": Path("deploy/oci/compose.yaml"),
    "/opt/dcss/Caddyfile": Path("deploy/oci/Caddyfile"),
    "/opt/dcss/backup.sh": Path("deploy/oci/backup.sh"),
}


def main() -> None:
    files = {f["path"]: f.get("content", "") for f in yaml.safe_load(CLOUD_INIT.read_text())["write_files"]}
    bad = []
    for path, source in COPIES.items():
        if path not in files:
            bad.append(f"{path}: missing from {CLOUD_INIT}")
        elif files[path].rstrip("\n") != source.read_text().rstrip("\n"):
            bad.append(f"{path}: differs from {source}")
    for line in bad:
        print(line)
    print(f"{len(COPIES)} cloud-init copies checked, {len(bad)} out of sync")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

"""Sign a completed local app from the inside out, without uploading it."""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import subprocess
from pathlib import Path

from macos_bundle import ROOT, audit, macho_files


def development_identity() -> str:
    identities = subprocess.check_output(["security", "find-identity", "-v", "-p", "codesigning"], text=True)
    matches = re.findall(r'\b([A-F0-9]{40}) "Apple Development:', identities)
    if len(matches) != 1:
        raise RuntimeError("Development signing requires exactly one available Apple Development identity")
    return matches[0]


def sign(app: Path, identity: str = "-", *, development: bool = False) -> None:
    app = app.resolve()
    if development:
        identity = development_identity()
    resources = app / "Contents/Resources"
    report = audit(app)
    (resources / "BinaryAudit.json").write_text(json.dumps(report, indent=2) + "\n")
    with (app / "Contents/Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    info["LSMinimumSystemVersion"] = report["minimum_macos"]
    with (app / "Contents/Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)
    (resources / "Signing.json").write_text(json.dumps({"kind": "development" if development else "ad-hoc" if identity == "-" else "distribution",
        "hardened_runtime": identity != "-", "notarization": "Requires a separate distribution receipt and stapled ticket"}, indent=2) + "\n")
    common = ["codesign", "--force", "--sign", identity]
    if identity != "-":
        common += ["--options", "runtime", "--timestamp=none" if development else "--timestamp"]
    for binary in macho_files(app):
        arguments = common.copy()
        if identity != "-" and binary.parent.name == "bin" and binary.name.startswith("python3."):
            arguments += ["--entitlements", str(ROOT / "macos/Runtime.entitlements")]
        subprocess.run([*arguments, str(binary)], check=True)
    arguments = [*common, "--identifier", info["CFBundleIdentifier"]]
    if identity != "-":
        arguments += ["--entitlements", str(ROOT / "macos/App.entitlements")]
    subprocess.run([*arguments, str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--identity", default="-")
    parser.add_argument("--development-signing", action="store_true")
    args = parser.parse_args()
    sign(args.app, args.identity, development=args.development_signing)

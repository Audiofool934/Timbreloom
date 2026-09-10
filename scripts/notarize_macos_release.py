"""Submit a reviewed Developer ID DMG only with explicit --submit, then staple and verify it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def readonly_image(dmg: Path):
    temporary = Path(tempfile.mkdtemp(prefix="timbreloom-notary-check-"))
    mount = temporary / "Read Only Volume"
    mount.mkdir()
    try:
        subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(dmg)], check=True)
        yield mount
    finally:
        # Trust scanning can temporarily retain a mounted image after its app exits.
        # Never recursively remove a directory that may still contain a live volume.
        if mount.is_mount():
            for attempt in range(5):
                detached = subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True, text=True)
                if detached.returncode == 0:
                    break
                time.sleep(2)
            else:
                raise RuntimeError(f"Could not detach the validation image at {mount}: {detached.stderr.strip()}")
        if mount.is_mount():
            raise RuntimeError(f"Validation image remains mounted at {mount}")
        mount.rmdir()
        temporary.rmdir()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--keychain-profile", required=True, help="Existing notarytool credential profile; no password is accepted in this script")
    parser.add_argument("--submit", action="store_true", help="Explicitly upload this reviewed DMG to Apple's notary service")
    args = parser.parse_args()
    app, dmg = args.app.resolve(), args.dmg.resolve()
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    details = subprocess.run(["codesign", "-d", "--verbose=4", str(app)], check=True, capture_output=True, text=True).stderr
    if "Authority=Developer ID Application:" not in details or "runtime" not in details:
        parser.error("A Developer ID Application signature with hardened runtime is required")
    subprocess.run(["hdiutil", "verify", str(dmg)], check=True)
    with readonly_image(dmg) as mount:
        contained = mount / app.name
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(contained)], check=True)
        packaged_details = subprocess.run(["codesign", "-d", "--verbose=4", str(contained)], check=True, capture_output=True, text=True).stderr
        if re.search(r"^CDHash=(.+)$", details, re.M).group(1) != re.search(r"^CDHash=(.+)$", packaged_details, re.M).group(1):
            raise RuntimeError("The DMG contains a different app from the reviewed signed bundle")
    if not args.submit:
        print("Local prerequisites passed. Nothing was uploaded; use --submit only for the approved artifact.")
        return
    with dmg.open("rb") as handle:
        submitted_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    response = subprocess.check_output(["xcrun", "notarytool", "submit", str(dmg),
        "--keychain-profile", args.keychain_profile, "--wait", "--output-format", "json"], text=True)
    receipt = json.loads(response)
    receipt["submitted_sha256"] = submitted_hash
    receipt_path = dmg.with_suffix(".notarization.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    subprocess.run(["xcrun", "notarytool", "log", receipt["id"], "--keychain-profile", args.keychain_profile,
                    str(dmg.with_suffix(".notary-log.json"))], check=True)
    if receipt.get("status") != "Accepted":
        raise RuntimeError("Apple did not accept this submission; inspect the saved notarization log")
    subprocess.run(["xcrun", "stapler", "staple", str(dmg)], check=True)
    subprocess.run(["xcrun", "stapler", "validate", str(dmg)], check=True)
    subprocess.run(["spctl", "--assess", "--type", "open", "--context", "context:primary-signature", "--verbose=2", str(dmg)], check=True)
    with dmg.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    dmg.with_suffix(".sha256").write_text(f"{checksum}  {dmg.name}\n")
    receipt.update(stapled=True, gatekeeper_accepted=True, distributed_sha256=checksum)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Notarized and verified: {dmg}")


if __name__ == "__main__":
    main()

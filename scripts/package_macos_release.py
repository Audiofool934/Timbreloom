"""Create and verify a local DMG; notarization is a separate explicit command."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from macos_bundle import clone_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app, output = args.app.resolve(), args.output.resolve()
    if output.exists():
        parser.error("The output already exists; choose a new artifact name")
    with (app / "Contents/Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    manifest = json.loads((app / "Contents/Resources/ReleaseManifest.json").read_text())
    if manifest.get("models_embedded") is not False or (app / "Contents/Resources/backend/models").exists():
        parser.error("Release apps must contain the runtime and download catalog only; model weights stay separate")
    if not all(manifest["runtimes"][name].get("production_only") for name in ("main", "seed-vc")):
        parser.error("Release apps must be assembled from locked production-only environments")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dmg-stage-", dir=output.parent) as temporary:
        stage = Path(temporary)
        shutil.copytree(app, stage / "Timbreloom.app", symlinks=True, copy_function=clone_file)
        (stage / "Applications").symlink_to("/Applications")
        (stage / "安装说明.txt").write_text(
            f"Timbreloom {info['CFBundleShortVersionString']}\n\n"
            f"需要 Apple Silicon 和 macOS {info['LSMinimumSystemVersion']} 或更新版本。\n"
            "将 Timbreloom 拖入 Applications，再从应用程序目录打开。\n"
            "本地运行时已包含在应用中，无需 Python 或 Homebrew。\n"
            "模型单独保存，请在应用的模型管理中按需下载。未选择下载前不会获取模型。\n"
            "模型保存在 ~/Library/Application Support/Timbreloom/models，下载后可离线使用。\n"
            "音色、转录和项目保存在 ~/Library/Application Support/Timbreloom/data。\n"
            "替换应用不会删除资料库。\n")
        subprocess.run(["hdiutil", "create", "-format", "ULFO", "-nospotlight",
            "-volname", "Timbreloom", "-srcfolder", str(stage), str(output)], check=True)
    subprocess.run(["hdiutil", "verify", str(output)], check=True)
    with output.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    output.with_suffix(".sha256").write_text(f"{checksum}  {output.name}\n")
    print(json.dumps({"artifact": str(output), "bytes": output.stat().st_size, "sha256": checksum}, indent=2))


if __name__ == "__main__":
    main()

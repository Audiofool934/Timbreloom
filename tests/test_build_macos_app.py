import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_macos_app as builder


def make_app(path, content, bundle_id=builder.BUNDLE_ID):
    contents = path / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": bundle_id}))
    binary = contents / "Timbreloom"
    binary.write_text(content)
    binary.chmod(0o755)
    (contents / "current").symlink_to("Timbreloom")
    return path


def test_backup_restores_contents_permissions_and_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    old = make_app(tmp_path / "Timbreloom.app", "old")
    staged = make_app(tmp_path / "stage" / "Timbreloom.app", "new")
    subprocess.run(["/usr/bin/xattr", "-w", "com.apple.TextEncoding", "utf-8;134217984",
                    str(old / "Contents/Timbreloom")], check=True)
    builder.replace_build(staged, old)
    assert (old / "Contents/Timbreloom").read_text() == "new"
    backups = list((tmp_path / "build/previous-apps").iterdir())
    assert len(backups) == 1 and backups[0].suffix == ".zip"
    restored = tmp_path / "restored"
    subprocess.run(["/usr/bin/ditto", "-x", "-k", str(backups[0]), str(restored)], check=True)
    binary = restored / "Timbreloom.app/Contents/Timbreloom"
    assert binary.read_text() == "old"
    assert binary.stat().st_mode & 0o777 == 0o755
    assert subprocess.check_output(["/usr/bin/xattr", "-p", "com.apple.TextEncoding", str(binary)]).strip() == b"utf-8;134217984"
    link = binary.with_name("current")
    assert link.is_symlink() and link.readlink() == Path("Timbreloom")


def test_failed_archive_preserves_both_apps(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    old = make_app(tmp_path / "Timbreloom.app", "old")
    staged = make_app(tmp_path / "stage" / "Timbreloom.app", "new")

    def fail(*args):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(builder, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        builder.replace_build(staged, old)
    assert (old / "Contents/Timbreloom").read_text() == "old"
    assert (staged / "Contents/Timbreloom").read_text() == "new"


def test_refuses_to_replace_another_app(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    old = make_app(tmp_path / "Timbreloom.app", "other", bundle_id="other.app")
    staged = make_app(tmp_path / "stage" / "Timbreloom.app", "new")
    with pytest.raises(RuntimeError, match="different app"):
        builder.replace_build(staged, old)
    assert (old / "Contents/Timbreloom").read_text() == "other"
    assert staged.exists()

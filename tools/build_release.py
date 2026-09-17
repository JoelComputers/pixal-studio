"""Build a source ZIP using an explicit allowlist; never includes user data."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOP = ["server.py", "settings.py", "pipeline.py", "doctor.py", "export_graph.py",
       "requirements.txt", "requirements.lock", "package.json", "package-lock.json",
       "config.example.json", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
       "CONTRIBUTING.md", "CHANGELOG.md", ".gitignore", "Start Studio.cmd"]
TREES = {"pixal_pipeline": {".py", ".json"}, "static": {".html", ".css", ".js"},
         "manifests": {".json", ".txt"}, "licenses": {".txt"},
         "tests": {".py", ".json"}, "tools": {".py"}, ".github": {".md", ".yml"}}
THREE = ["LICENSE", "build/three.module.js", "examples/jsm/controls/OrbitControls.js",
         "examples/jsm/loaders/GLTFLoader.js", "examples/jsm/environments/RoomEnvironment.js",
         "examples/jsm/utils/BufferGeometryUtils.js"]


def main():
    contents = {name: (ROOT / name).read_bytes() for name in TOP}
    for directory, suffixes in TREES.items():
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts:
                contents[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    three_root = ROOT / "vendor/three"
    if not three_root.is_dir():
        three_root = ROOT / "node_modules/three"
        package = json.loads((three_root / "package.json").read_text())
        if package["version"] != "0.169.0":
            raise ValueError("Run npm ci: expected Three.js 0.169.0")
    for name in THREE:
        contents["vendor/three/" + name] = (three_root / name).read_bytes()
    contents["RELEASE-FILES.sha256"] = ("\n".join(
        hashlib.sha256(data).hexdigest() + "  " + name
        for name, data in sorted(contents.items())) + "\n").encode()
    target = ROOT / "dist/pixal-studio-0.1.0-source.zip"
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo("pixal-studio/" + name, date_time=(2026, 9, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(digest + "  " + target.name + "\n")
    print(f"Built {target.name}: {len(contents)} files, {target.stat().st_size:,} bytes")
    print("SHA256 " + digest)


if __name__ == "__main__":
    main()

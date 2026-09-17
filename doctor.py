"""Read-only readiness checks. Never submits, cancels, or loads GPU models."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

from pixal_pipeline import build_graph
from settings import load_settings, ROOT

BINDINGS = {"diffusion": ("UNETLoader", "unet_name"),
    "shape_vae": ("VAELoader", "vae_name"), "texture_vae": ("VAELoader", "vae_name"),
    "vision": ("CLIPVisionLoader", "clip_name"),
    "background": ("LoadBackgroundRemovalModel", "bg_removal_name")}


def check_schema(definitions, models):
    errors = []
    for preset in ("preview", "detail"):
        for node in build_graph("input.png", preset, models=models).values():
            kind = node["class_type"]
            if kind not in definitions:
                errors.append("Missing node: " + kind)
                continue
            required = definitions[kind]["input"].get("required", {})
            for key, spec in required.items():
                if key not in node["inputs"]:
                    errors.append(f"Missing required input: {kind}.{key}")
                elif kind != "LoadImage" and isinstance(spec[0], list) and not isinstance(node["inputs"][key], list):
                    if node["inputs"][key] not in spec[0]:
                        errors.append(f"Unsupported value for {kind}.{key}: {node['inputs'][key]}")
    return sorted(set(errors))


def check_models(settings, full_hash=False):
    root = settings.get("models_dir")
    if not root:
        return ["Set models_dir (or PIXAL_MODELS_DIR) to check model files."], []
    manifest = json.loads((ROOT / "manifests/models.json").read_text())
    errors, checked = [], []
    for record in manifest["models"]:
        category = Path(record["path"]).parts[0]
        relative = settings["models"][record["role"]].replace("\\", "/")
        target = (root / category / relative).resolve()
        if not target.is_relative_to(root.resolve()):
            errors.append("Model path escapes models_dir: " + record["role"])
        elif not target.is_file():
            errors.append("Missing model: " + str(target))
        elif target.stat().st_size != record["bytes"]:
            errors.append("Model size mismatch: " + str(target))
        elif full_hash:
            with target.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != record["sha256"]:
                errors.append("Model SHA256 mismatch: " + str(target))
            else:
                checked.append(record["role"] + ": SHA256 verified")
        else:
            checked.append(record["role"] + ": size verified (use --hash-models for integrity)")
    return errors, checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--offline", action="store_true", help="Skip the ComfyUI HTTP readiness check")
    parser.add_argument("--hash-models", action="store_true", help="Read model files on CPU and verify SHA256")
    args = parser.parse_args()
    errors, checks = [], []
    try:
        settings = load_settings(args.config)
        for preset in ("preview", "detail"):
            build_graph("input.png", preset, models=settings["models"])
        checks.append("Both workflow presets constructed without GPU imports")
        if not settings["output_dir"].is_dir():
            errors.append("output_dir must point to the existing ComfyUI output directory")
        vendor = ROOT / "vendor/three"
        if not vendor.exists():
            vendor = ROOT / "node_modules/three"
        for name in ("build/three.module.js", "examples/jsm/loaders/GLTFLoader.js"):
            if not (vendor / name).is_file():
                errors.append("Missing viewer asset: " + name + "; run npm ci")
        failures, model_checks = check_models(settings, args.hash_models)
        errors.extend(failures)
        checks.extend(model_checks)
        if not args.offline:
            with urllib.request.urlopen(settings["comfy_url"] + "/object_info", timeout=30) as response:
                errors.extend(check_schema(json.load(response), settings["models"]))
            checks.append("Queried ComfyUI node signatures; no job submitted")
    except Exception as exc:
        errors.append(str(exc))
    print(json.dumps({"ok": not errors, "checks": checks, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

"""Local configuration. Importing this module never contacts ComfyUI."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
MODEL_DEFAULTS = {
    "diffusion": "pixal3d_int8_convrot.safetensors",
    "shape_vae": "trellis_2_shape_vae_bf16.safetensors",
    "texture_vae": "trellis_2_texture_vae_bf16.safetensors",
    "vision": "dino_v3_L_naf_fp32.safetensors",
    "background": "birefnet.safetensors",
}


def load_settings(config_path=None, environ=None):
    env = os.environ if environ is None else environ
    explicit = config_path or env.get("PIXAL_CONFIG")
    path = Path(explicit).expanduser().resolve() if explicit else ROOT / "config.local.json"
    if explicit and not path.is_file():
        raise ValueError(f"Configuration file not found: {path}")
    values = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    if not isinstance(values, dict):
        raise ValueError("Configuration must be a JSON object.")
    unknown = set(values) - {"comfy_url", "output_dir", "data_dir", "models_dir", "models"}
    if unknown:
        raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
    values["comfy_url"] = env.get("PIXAL_COMFY_URL", values.get("comfy_url", "http://127.0.0.1:8188")).rstrip("/")
    url = urlsplit(values["comfy_url"])
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
        raise ValueError("comfy_url must be an HTTP(S) URL without embedded credentials.")
    for key, variable, default in (("output_dir", "PIXAL_OUTPUT_DIR", "output"),
            ("data_dir", "PIXAL_DATA_DIR", "data"), ("models_dir", "PIXAL_MODELS_DIR", None)):
        raw = env.get(variable, values.get(key, default))
        if raw:
            target = Path(raw).expanduser()
            values[key] = (path.parent / target).resolve() if not target.is_absolute() else target.resolve()
        else:
            values[key] = None
    overrides = values.get("models", {})
    if not isinstance(overrides, dict) or set(overrides) - MODEL_DEFAULTS.keys():
        raise ValueError("models must map known model roles to ComfyUI model filenames.")
    if any(not isinstance(value, str) or not value for value in overrides.values()):
        raise ValueError("Model filenames must be nonempty strings.")
    values["models"] = MODEL_DEFAULTS | overrides
    return values

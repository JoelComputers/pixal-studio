"""Native ComfyUI graphs. The GUI never loads a model or starts a GPU worker."""
import copy
import json
from pathlib import Path

BASE_GRAPH = json.loads(Path(__file__).with_name("base_graph.json").read_text(encoding="utf-8"))

PRESETS = {
    "preview": {"label": "Quick preview", "resolution": 1024, "faces": 300000,
                "texture_size": 0},
    "detail": {"label": "Detailed", "resolution": 1536, "faces": 700000,
               "texture_size": 4096},
}

STAGES = {
    "5": "Loading image", "8": "Removing background", "7": "Framing subject",
    "10": "Reading image details", "31": "Building structure",
    "32": "Decoding structure", "33": "Preparing shape", "35": "Sculpting shape",
    "34": "Adding resolution", "36": "Refining geometry", "37": "Decoding mesh",
    "51": "Cleaning surface", "52": "Optimizing mesh", "53": "Finishing normals",
    "40": "Preparing color", "41": "Generating surface details",
    "42": "Decoding surface details", "62": "Laying out UVs",
    "63": "Baking texture maps", "64": "Applying textures", "54": "Painting mesh",
    "60": "Saving clean mesh", "61": "Saving finished model", "65": "Saving source mesh",
}


def build_graph(image, preset="detail", seed=42, job_id="test", models=None):
    if preset not in PRESETS:
        raise ValueError("Choose Quick preview or Detailed.")
    seed = int(seed)
    if not 0 <= seed <= 2147483647:
        raise ValueError("Seed must be between 0 and 2147483647.")
    settings = PRESETS[preset]
    if not job_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in job_id):
        raise ValueError("job_id must contain only letters, digits, underscore or hyphen.")
    graph = copy.deepcopy(BASE_GRAPH)
    bindings = {"diffusion": ("1", "unet_name"), "shape_vae": ("2", "vae_name"),
                "texture_vae": ("3", "vae_name"), "vision": ("4", "clip_name"),
                "background": ("6", "bg_removal_name")}
    for role, filename in (models or {}).items():
        if role not in bindings or not isinstance(filename, str) or not filename:
            raise ValueError("Invalid model override: " + str(role))
        node, field = bindings[role]
        graph[node]["inputs"][field] = filename
    prefix = f"pixal3d_gui/{job_id}"
    graph["5"]["inputs"]["image"] = image
    graph["34"]["inputs"]["target_resolution"] = settings["resolution"]
    for node, offset in (("31", 14), ("35", 0), ("36", 0), ("41", 1)):
        graph[node]["inputs"]["seed"] = seed + offset
    graph["52"]["inputs"]["target_face_count"] = settings["faces"]
    graph["60"]["inputs"]["filename_prefix"] = prefix + "/clean"
    graph["61"]["inputs"]["filename_prefix"] = prefix + "/model"
    graph["71"] = {"class_type": "SaveImage", "inputs": {
        "images": ["7", 0], "filename_prefix": prefix + "/prepared"}}
    if preset == "detail":
        # Preserve small ridges and original surface position. The old recipe
        # used 20 smoothing passes and vertex colors interpolated across faces.
        graph["51"]["inputs"].update(resolution=1024, smooth_iters=2,
            project_back=0.85, drop_small_components=0.001)
        graph["51"]["inputs"]["sign_mode.qef"] = True
        del graph["54"]
        graph["62"] = {"class_type": "UnwrapMesh", "inputs": {
            "mesh": ["53", 0], "segmenter": "pec", "resolution": 4096,
            "padding": 4, "weld_distance": 0.0002}}
        graph["63"] = {"class_type": "BakeTextureFromVoxel", "inputs": {
            "mesh": ["62", 0], "voxel_colors": ["42", 0],
            "reference_mesh": ["37", 0], "texture_size": 4096}}
        graph["64"] = {"class_type": "ApplyTextureToMesh", "inputs": {
            "mesh": ["62", 0], "base_color": ["63", 0],
            "metallic": ["63", 1], "roughness": ["63", 2]}}
        graph["61"]["inputs"]["mesh"] = ["64", 0]
        graph["65"] = {"class_type": "SaveGLB", "inputs": {
            "mesh": ["37", 0], "filename_prefix": prefix + "/source_mesh"}}
        for node, slot, name in (("66", 0, "base_color"),
                                  ("67", 1, "metallic"), ("68", 2, "roughness")):
            graph[node] = {"class_type": "SaveImage", "inputs": {
                "images": ["63", slot], "filename_prefix": prefix + "/" + name}}
    return graph

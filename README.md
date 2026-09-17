# Pixal Studio

Free, open-source local image-to-3D interface: upload an image, generate a model,
orbit it in your browser, and download a GLB. Uses an existing ComfyUI backend
and joins its normal queue. It does not start a second GPU server.

**Status:** v0.1.0 Developer Preview. Windows generation has been tested. This is
a local application for an existing ComfyUI installation, not yet a standalone
installer or a public multi-user web service.

Download: [v0.1.0 Developer Preview](https://github.com/JoelComputers/pixal-studio/releases/tag/v0.1.0)

Source and issues: [JoelComputers/pixal-studio](https://github.com/JoelComputers/pixal-studio)

## Requirements

- Python 3.12 for the GUI. The GUI has no PyTorch/CUDA dependency.
- A compatible ComfyUI installation running on the same machine (or with its
  output folder mounted locally). Set output_dir to the exact output directory
  used by that server.
- The five model files in manifests/models.json under their specified model
  categories. The manifest has immutable revision URLs, byte counts, and SHA256.
- Native Pixal3D/Trellis2, background-removal, mesh/UV/texture nodes available in
  the backend. `doctor.py` checks both presets against its actual node schema.
- A modern browser with WebGL. The release ZIP bundles the required Three.js
  modules locally; no CDN is used. Git source checkouts need Node/npm to run
  `npm ci` once, or use the release ZIP's vendor assets.

Backend reference: ComfyUI commit
`856a922befab9d94cb66f36a3dce17234d7a6e31`, Python 3.12.10. See
manifests/backend-observed-windows.json for observed dependency versions and
manifests/comfyui-requirements.txt for that revision's upstream requirements.
The observed inventory includes unrelated installed packages; it is evidence,
not a recommended install command or a Linux lockfile. GPU platform packages
must be selected and verified separately. No minimum VRAM or Linux/cloud
compatibility claim is made yet.

## Install the GUI on Windows

Extract the source ZIP and open PowerShell inside its `pixal-studio` folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.local.json
```

Edit `config.local.json` to point output_dir and models_dir to your ComfyUI
folders. Relative paths are resolved relative to the configuration file, not
your terminal's current directory. Forward slashes work in Windows JSON paths.
The model map normally stays empty; use role-to-filename overrides only when
your ComfyUI model names differ. Read THIRD_PARTY_NOTICES.md before obtaining
external weights; they are not included in this release.

Start ComfyUI with its normal launcher, then check readiness:

```powershell
.\.venv\Scripts\python.exe doctor.py --hash-models
.\.venv\Scripts\python.exe server.py
```

Visit http://127.0.0.1:8790 . On subsequent launches, double-click
`Start Studio.cmd`. Closing the server does not cancel work already submitted
to ComfyUI. Reopening restores saved job history.

On other systems the GUI uses the equivalent `python3.12 -m venv .venv` and
`.venv/bin/python` commands. The GUI and pipeline use portable Python, but
end-to-end Linux GPU generation remains unverified until the cloud-worker stage.

## Use

1. Upload a PNG, JPEG, or WebP with one subject fully visible.
2. Choose Quick preview (1024, approximately 300k triangles, vertex color) or
   Detailed (1536, approximately 700k triangles, 4K UV textures).
3. Generate. It waits behind jobs already in the ComfyUI queue.
4. Orbit/zoom the result and download GLB. Detailed also provides clean/source
   meshes, prepared input, and base-color/metallic/roughness maps.

A reference character took 221 seconds for Detailed and produced a 36 MB GLB
on the original machine, excluding queue time. This is one measurement, not a
speed guarantee. Small features, unseen surfaces, identity, and topology can
still need manual work. Models are not promised to be animation-ready.

Cancellation targets only jobs this GUI submitted. Data is local; there are no
accounts or cloud uploads. Keep the server bound to loopback. Authentication,
multi-user isolation, payments, and internet deployment are separate work.

## Configuration and diagnostics

Default settings are in settings.py. A private config.local.json overrides
them; environment variables override that file:

| Variable | Meaning |
| --- | --- |
| PIXAL_CONFIG | Explicit configuration filename; a missing file is an error |
| PIXAL_COMFY_URL | Backend URL (default http://127.0.0.1:8188) |
| PIXAL_OUTPUT_DIR | Existing backend output directory |
| PIXAL_MODELS_DIR | Model root used for local integrity checks |
| PIXAL_DATA_DIR | Job/history/source directory (default data next to config) |

`python doctor.py --offline --hash-models` checks local files without any HTTP
requests. Normal doctor additionally reads `/object_info`; it never submits,
cancels, or loads models on a GPU. File size alone cannot detect all corruption,
so use hash verification after downloading or copying models. For models spread
across multiple roots, check each file against the manifest and configure the
backend's normal model search paths; doctor's local file check uses one root.

`python export_graph.py --image uploaded.png --preset detail --output graph.json`
writes an API-format graph without running it. Graph construction can also be
imported from `pixal_pipeline`; it needs only the Python standard library.

## Tests and release

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/build_release.py
```

The tests include an exact regression comparison to a previously successful
Detailed graph, same-size corruption detection, isolated configuration, and
an HTTP server running from another directory with a fake offline backend.
They never perform GPU generation. The release builder includes only explicit
source/assets directories, produces a deterministic ZIP and SHA256 listing,
and excludes config.local.json, jobs, uploads, models, virtual environments,
logs, and development files outside this project.

The current portable checks establish GUI installation and graph equivalence;
a completely fresh GPU-backend installation is still a separate acceptance
test before claiming one-click setup support.

## License and credits

Application: GPL-3.0-only, see LICENSE. Three.js remains MIT. External models
retain their upstream terms. See THIRD_PARTY_NOTICES.md for attribution and
the DINOv3 provenance question to resolve before distributing weights or
launching paid hosting. This source release does not bundle those weights.

Built on ComfyUI, Tencent Pixal3D, Microsoft TRELLIS.2, Meta DINOv3, BiRefNet,
and Three.js. Contributions welcome; see CONTRIBUTING.md.

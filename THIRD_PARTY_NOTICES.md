# Licensing and provenance

Pixal Studio application code is provided under GPL-3.0-only; see LICENSE.
Copyright (c) 2026 Pixal Studio contributors. This license permits commercial
use and does not require charging for the local application. Third-party code
and model weights retain their own licenses. This project is not affiliated
with or endorsed by Tencent, Microsoft, Meta, or Comfy Org.

| Component | Relationship | Terms / source |
| --- | --- | --- |
| ComfyUI | Separate required backend; native node workflow informed this graph | GPLv3; https://github.com/Comfy-Org/ComfyUI |
| Three.js 0.169.0 | Unmodified viewer modules bundled in source ZIP | MIT; licenses/Three-MIT.txt; https://github.com/mrdoob/three/tree/r169 |
| Pixal3D | External generation weights, not bundled | MIT and upstream NOTICE; licenses/Pixal3D-*; https://github.com/TencentARC/Pixal3D |
| TRELLIS.2 | External VAE/model foundations, not bundled | MIT; licenses/TRELLIS2-MIT.txt; https://github.com/microsoft/TRELLIS.2 |
| DINOv3 | External vision backbone, not bundled | Custom DINOv3 terms; licenses/DINOv3.txt; https://github.com/facebookresearch/dinov3 |
| BiRefNet | External background-removal model, not bundled | Upstream MIT; licenses/BiRefNet-MIT.txt; https://github.com/ZhengPeng7/BiRefNet |
| Pillow | Installed separately by pip | HPND/Pillow terms; https://github.com/python-pillow/Pillow/blob/main/LICENSE |
| aiohttp | Installed separately by pip | Apache-2.0 and notices; https://github.com/aio-libs/aiohttp/blob/master/LICENSE.txt |

The workflow derives from the ComfyUI native Pixal3D/Trellis2 example and the
locally validated v5 correction. No ComfyUI source or model weights are shipped
in the source ZIP. The release contains the Three.js license alongside its code.
The separately installed Python distributions carry their own dependency licenses.

## Model provenance review, 2026-09-17

manifests/models.json pins the Comfy-Org repacks by repository commit and LFS
SHA256. All five hashes matched the working local files. A repack's top-level
MIT model-card label does not remove inherited component obligations.
In particular, the DINO/NAF filename and DINOv3 backend indicate a DINOv3
component, while Pixal3D's upstream NOTICE lists DINOv2. Preserve the stricter
component provenance distinction; do not claim the entire weight set is MIT.
Clarify the exact inherited vision-weight terms before bundling weights or
opening a paid hosted service. This does not prevent shipping this application's
source and requiring users to obtain the external models under their terms.

The native ComfyUI backend is used, not a bundled third-party Trellis wrapper.
No license assumption about nvdiffrast, CUDA redistributables, optional custom
nodes, or a future cloud container is made here. Stage 2 must inventory the
actual Linux container and retain its required notices before distribution.

Copies of upstream model license documents are included for reference; model
downloads are not automatic and no terms are accepted on the user's behalf.

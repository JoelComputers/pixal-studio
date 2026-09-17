import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const $ = id => document.getElementById(id);
let inputFile = null, uploading = false, online = false, jobs = [];
let selectedId = localStorage.getItem('pixal-selected') || null;
let previewURL = null, loadedId = null, loadToken = 0, historySignature = '';
let renderer, scene, camera, controls, model, grid, home, animating = false;
let wire = false, rotation = false;
const terminal = new Set(['completed', 'failed', 'cancelled']);

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
function error(message) { $('form-error').textContent = message; $('form-error').hidden = !message; }
function enableGenerate() { $('generate').disabled = !inputFile || uploading || !online; }
function pick(file) {
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    error('Choose a PNG, JPEG, or WebP image.'); return;
  }
  if (file.size > 25 * 1024 * 1024) { error('Choose an image smaller than 25 MB.'); return; }
  inputFile = file;
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = URL.createObjectURL(file);
  $('image-preview').src = previewURL;
  $('image-preview').hidden = false;
  $('upload-placeholder').hidden = true;
  $('change-image').hidden = false;
  $('dropzone').classList.add('has-image');
  $('model-name').value = file.name.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' ');
  error(''); enableGenerate();
}
$('image-input').addEventListener('change', e => pick(e.target.files[0]));
$('dropzone').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('image-input').click(); }
});
for (const type of ['dragenter', 'dragover']) $('dropzone').addEventListener(type, e => {
  e.preventDefault(); $('dropzone').classList.add('drag-over');
});
for (const type of ['dragleave', 'drop']) $('dropzone').addEventListener(type, e => {
  e.preventDefault(); $('dropzone').classList.remove('drag-over');
  if (type === 'drop') pick(e.dataTransfer.files[0]);
});
document.querySelectorAll('input[name=quality]').forEach(input => input.addEventListener('change', () => {
  document.querySelectorAll('.quality-option').forEach(label => {
    label.classList.toggle('selected', label.querySelector('input').checked);
  });
}));
$('randomize').onclick = () => { $('seed').value = crypto.getRandomValues(new Uint32Array(1))[0] % 2147483647; };
$('generate').onclick = async () => {
  if (!inputFile || uploading || !$('seed').reportValidity()) return;
  uploading = true; enableGenerate(); error('');
  $('generate').firstElementChild.textContent = 'Adding to queue…';
  const params = new URLSearchParams({name: $('model-name').value.trim() || 'Untitled model',
    preset: document.querySelector('input[name=quality]:checked').value, seed: $('seed').value});
  try {
    const job = await api('/api/jobs?' + params, {method: 'POST',
      headers: {'Content-Type': 'application/octet-stream'}, body: inputFile});
    jobs.unshift(job); selectJob(job.id); await refresh();
  } catch (e) { error(e.message); }
  finally { uploading = false; $('generate').firstElementChild.textContent = 'Generate 3D model'; enableGenerate(); }
};
$('cancel-job').onclick = async () => {
  const job = jobs.find(j => j.id === selectedId);
  if (!job || terminal.has(job.status)) return;
  $('cancel-job').disabled = true;
  try { await api(`/api/jobs/${job.id}/cancel`, {method: 'POST'}); await refresh(); }
  catch (e) { error(e.message); }
  finally { $('cancel-job').disabled = false; }
};
function selectJob(id) {
  selectedId = id; localStorage.setItem('pixal-selected', id);
  updateSelected(); renderHistory();
}
function renderHistory() {
  const signature = JSON.stringify(jobs.map(j => [j.id,j.status,j.name])) + selectedId;
  if (signature === historySignature) return;
  historySignature = signature;
  $('history-count').textContent = `${jobs.length} creation${jobs.length === 1 ? '' : 's'}`;
  if (!jobs.length) return;
  $('history-list').replaceChildren();
  for (const job of jobs) {
    const button = document.createElement('button');
    button.className = 'history-item' + (job.id === selectedId ? ' active' : '');
    button.setAttribute('aria-label', `Open ${job.name}, ${job.status}`);
    const img = document.createElement('img'); img.src = `/file/${job.id}/source`; img.alt = ''; img.loading = 'lazy';
    const content = document.createElement('div');
    const title = document.createElement('strong'); title.textContent = job.name;
    const detail = document.createElement('small');
    detail.textContent = `${job.preset === 'detail' ? 'Detailed' : 'Quick preview'} · ${new Date(job.created).toLocaleDateString(undefined,{month:'short',day:'numeric'})}`;
    const state = document.createElement('span'); state.className = 'history-state';
    state.textContent = ({completed:'Ready to explore',running:'Generating…',queued:'In queue',failed:'Needs attention',cancelled:'Cancelled',cancelling:'Cancelling…'})[job.status] || job.status;
    content.append(title,detail,state); button.append(img,content);
    button.onclick = () => selectJob(job.id); $('history-list').append(button);
  }
}
function updateSelected() {
  const job = jobs.find(j => j.id === selectedId);
  if (!job) return;
  $('preview-title').textContent = job.name;
  $('result-badge').textContent = job.preset === 'detail' ? 'DETAILED · 4K' : 'QUICK PREVIEW';
  $('job-status').hidden = job.status === 'completed';
  $('job-state').textContent = job.status;
  $('job-stage').textContent = job.stage || job.status;
  $('cancel-job').hidden = terminal.has(job.status) || job.status === 'cancelling';
  const moving = ['running','cancelling'].includes(job.status);
  const hasSteps = moving && job.steps > 1;
  $('progress-bar').classList.toggle('indeterminate', moving && !hasSteps);
  $('progress-bar').style.width = hasSteps ? `${Math.min(100,100*job.step/job.steps)}%` : '0%';
  $('status-detail').textContent = job.error || (job.status === 'queued'
    ? `${job.ahead ?? 0} job${job.ahead === 1 ? '' : 's'} ahead. Your model will start automatically.`
    : hasSteps ? `Step ${Math.round(job.step)} of ${Math.round(job.steps)} in this stage.`
    : job.status === 'cancelling' ? 'Stopping only this job. Other jobs keep their place.'
    : job.status === 'cancelled' ? 'This job was cancelled. You can generate another variation.'
    : !online ? 'Waiting for ComfyUI to reconnect…' : 'Working locally. You can leave this page open or come back later.');
  const ready = job.status === 'completed' && job.files.model;
  $('result-footer').hidden = !ready; $('extra-downloads').hidden = !ready;
  if (ready) {
    $('download-model').href = `/file/${job.id}/model?download=1`;
    $('result-summary').textContent = `${(job.files.model.bytes/1048576).toFixed(1)} MB · ${job.preset === 'detail' ? 'Textured GLB' : 'Vertex-colored GLB'}${job.duration ? ` · ${Math.round(job.duration)} sec generation` : ''}`;
    const downloads = [['clean','Clean mesh'],['source_mesh','Full-resolution mesh'],
      ['base_color','Base color'],['roughness','Roughness'],['metallic','Metallic'],['prepared','Prepared image']];
    $('extra-downloads').replaceChildren();
    for (const [key,label] of downloads) if (job.files[key]) {
      const a = document.createElement('a'); a.href = `/file/${job.id}/${key}?download=1`; a.textContent = label;
      $('extra-downloads').append(a);
    }
    if (loadedId !== job.id) loadModel(job);
  } else if (loadedId !== null) {
    ++loadToken; loadedId = null; clearModel();
    $('empty-state').hidden = false; $('viewer-tools').hidden = true; $('viewer-hint').hidden = true;
    $('viewer-message').hidden = true;
  }
}
async function refresh() {
  try {
    const [health,list] = await Promise.all([api('/api/status'),api('/api/jobs')]);
    online = health.online; jobs = list.jobs;
    $('connection').className = 'connection ' + (online ? 'online' : 'offline');
    $('connection').lastElementChild.textContent = !online ? 'Start ComfyUI to generate'
      : health.running ? `GPU busy · ${health.waiting} queued` : 'Ready to create';
    if (!jobs.some(j => j.id === selectedId)) selectedId = jobs.find(j => !['cancelled','failed'].includes(j.status))?.id || jobs[0]?.id || null;
    updateSelected(); renderHistory();
  } catch (e) {
    online = false; $('connection').className = 'connection offline';
    $('connection').lastElementChild.textContent = 'Studio disconnected';
  }
  enableGenerate();
}

function initViewer() {
  if (renderer) return;
  const viewport = $('viewport');
  renderer = new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  viewport.prepend(renderer.domElement);
  renderer.domElement.setAttribute('aria-label','Interactive 3D model');
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(36,1,.01,100);
  controls = new OrbitControls(camera,renderer.domElement);
  controls.enableDamping = false; controls.minDistance = .2; controls.maxDistance = 18;
  controls.addEventListener('change',render);
  const room = new RoomEnvironment();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(room,.04).texture;
  room.dispose(); pmrem.dispose();
  scene.add(new THREE.HemisphereLight(0xffffff,0xa4b69a,1.5));
  const key = new THREE.DirectionalLight(0xffffff,2); key.position.set(3,5,4); scene.add(key);
  grid = new THREE.GridHelper(12,24,0xcad3c0,0xe0e6d6);
  grid.material.transparent = true; grid.material.opacity = .45; scene.add(grid);
  new ResizeObserver(() => {
    const {width,height} = viewport.getBoundingClientRect();
    renderer.setSize(width,height); camera.aspect = width/height; camera.updateProjectionMatrix(); render();
  }).observe(viewport);
}
function render() { if (renderer && scene && camera) renderer.render(scene,camera); }
function clearModel() {
  if (!model) return;
  model.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    for (const material of (Array.isArray(o.material) ? o.material : o.material ? [o.material] : [])) {
      for (const value of Object.values(material)) if (value?.isTexture) value.dispose();
      material.dispose();
    }
  });
  scene.remove(model); model = null; render();
}
async function loadModel(job) {
  loadedId = job.id; const token = ++loadToken;
  $('viewer-message').hidden = false; $('viewer-message').textContent = 'Opening your model…';
  $('empty-state').hidden = true;
  try {
    initViewer(); clearModel();
    const gltf = await new GLTFLoader().loadAsync(`/file/${job.id}/model`);
    if (token !== loadToken) {
      gltf.scene.traverse(o => { o.geometry?.dispose(); }); return;
    }
    model = gltf.scene;
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const scale = 2.8/Math.max(size.x,size.y,size.z);
    model.scale.multiplyScalar(scale); model.position.sub(center.multiplyScalar(scale));
    let triangles = 0, vertices = 0;
    model.traverse(o => {
      if (!o.isMesh) return;
      vertices += o.geometry.attributes.position.count;
      triangles += (o.geometry.index?.count || o.geometry.attributes.position.count)/3;
      for (const m of (Array.isArray(o.material) ? o.material : [o.material])) {
        m.wireframe = wire;
        for (const value of Object.values(m)) if (value?.isTexture) value.anisotropy = Math.min(8,renderer.capabilities.getMaxAnisotropy());
      }
    });
    scene.add(model); grid.position.y = -size.y*scale/2-.008;
    const radius = Math.max(size.length()*scale/2,.2);
    const fov = Math.min(THREE.MathUtils.degToRad(camera.fov),2*Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*camera.aspect));
    const distance = radius / Math.sin(fov/2) * 1.08;
    home = new THREE.Vector3(distance*.32,distance*.09,distance*.94);
    resetView();
    $('mesh-stats').textContent = `${Math.round(triangles).toLocaleString()} triangles · ${vertices.toLocaleString()} vertices`;
    $('viewer-tools').hidden = false; $('viewer-hint').hidden = false; $('viewer-message').hidden = true;
    if (rotation) animate();
  } catch (e) {
    $('viewer-message').hidden = false;
    $('viewer-message').textContent = 'The preview could not open. Your GLB download is still available.';
    console.error('Viewer:',e);
  }
}
function resetView() { if (home) { camera.position.copy(home); controls.target.set(0,0,0); controls.update(); render(); } }
function animate() {
  if (animating || !rotation || !model) return;
  animating = true;
  const tick = () => {
    if (!rotation || !model || document.hidden) { animating = false; return; }
    controls.autoRotate = true; controls.autoRotateSpeed = .7; controls.update(); render(); requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
$('reset-view').onclick = resetView;
$('wireframe').onclick = () => {
  wire = !wire; $('wireframe').setAttribute('aria-pressed',String(wire));
  model?.traverse(o => { if (o.isMesh) for (const m of (Array.isArray(o.material) ? o.material : [o.material])) m.wireframe=wire; }); render();
};
$('rotate').onclick = () => {
  rotation = !rotation; $('rotate').setAttribute('aria-pressed',String(rotation));
  if (controls) controls.autoRotate = rotation; animate();
};
document.addEventListener('visibilitychange',() => { if (!document.hidden) { refresh(); animate(); } });
await refresh();
setInterval(refresh,2500);

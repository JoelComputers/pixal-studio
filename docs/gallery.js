// Render on interaction only: no animation loop and no generation backend.
let active = null;
for (const section of document.querySelectorAll('[data-model]')) {
  const viewport = section.querySelector('.viewport');
  const button = section.querySelector('.load');
  const status = section.querySelector('.status');
  button.addEventListener('click', async () => {
    if (active) active();
    button.disabled = true;
    button.textContent = 'Loading…';
    status.textContent = 'Downloading the original GLB…';
    let renderer, controls, observer, scene, environment, disposed = false;
    const release = () => {
      disposed = true;
      observer?.disconnect(); controls?.dispose();
      const textures = new Set();
      scene?.traverse(o => { o.geometry?.dispose();
        for (const m of (Array.isArray(o.material) ? o.material : o.material ? [o.material] : [])) {
          Object.values(m).filter(v => v?.isTexture).forEach(t => textures.add(t)); m.dispose();
        }
      });
      textures.forEach(t => t.dispose()); environment?.dispose();
      renderer?.dispose(); renderer?.forceContextLoss(); renderer?.domElement.remove();
      viewport.querySelector('.poster').hidden = false;
      section.querySelector('.controls').hidden = true;
      button.hidden = false; button.disabled = false; button.textContent = 'Load 3D';
      status.textContent = '';
      if (active === release) active = null;
    };
    active = release;
    try {
      const [THREE, {OrbitControls}, {GLTFLoader}, {RoomEnvironment}] = await Promise.all([
        import('three'), import('three/addons/controls/OrbitControls.js'),
        import('three/addons/loaders/GLTFLoader.js'), import('three/addons/environments/RoomEnvironment.js')]);
      if (disposed) return;
      renderer = new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'});
      renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
      renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.15;
      renderer.domElement.setAttribute('aria-label', 'Drag to rotate the 3D model');
      viewport.prepend(renderer.domElement);
      scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(36,1,.01,100);
      controls = new OrbitControls(camera,renderer.domElement); controls.enablePan = false;
      controls.minDistance = 1.7; controls.maxDistance = 15;
      const render = () => {if (!disposed) renderer.render(scene,camera);};
      controls.addEventListener('change', render);
      const room = new RoomEnvironment(), pmrem = new THREE.PMREMGenerator(renderer);
      environment = pmrem.fromScene(room,.04).texture;
      scene.environment = environment; room.dispose(); pmrem.dispose();
      scene.add(new THREE.HemisphereLight(0xffffff,0xa4b69a,1.5));
      const light = new THREE.DirectionalLight(0xffffff,2); light.position.set(3,5,4); scene.add(light);
      const gltf = await new GLTFLoader().loadAsync(`models/${section.dataset.model}.glb`, event => {
        if (!disposed && event.total) status.textContent = `Loading model: ${Math.round(100*event.loaded/event.total)}%`;
      });
      if (disposed) {
        scene.add(gltf.scene); release(); return;
      }
      const model = gltf.scene, box = new THREE.Box3().setFromObject(model);
      const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
      const scale = 2.8/Math.max(size.x,size.y,size.z);
      model.scale.multiplyScalar(scale); model.position.sub(center.multiplyScalar(scale)); scene.add(model);
      const home = new THREE.Vector3(1.4,.45,5.5);
      const reset = () => {camera.position.copy(home); controls.target.set(0,0,0); controls.update(); render();};
      section.querySelector('.reset').onclick = reset;
      section.querySelector('.left').onclick = () => {camera.position.applyAxisAngle(new THREE.Vector3(0,1,0),Math.PI/8); controls.update();render();};
      section.querySelector('.zoom').onclick = () => {camera.position.multiplyScalar(.85);controls.update();render();};
      observer = new ResizeObserver(() => {const w=viewport.clientWidth,h=viewport.clientHeight;
        renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();render();});
      observer.observe(viewport); reset();
      viewport.querySelector('.poster').hidden = true; button.hidden = true; status.textContent = '';
      section.querySelector('.controls').hidden = false;
      viewport.dataset.loaded = 'true';
    } catch (error) {
      release(); status.textContent = 'Preview unavailable. You can still download the GLB below.';
      console.error('3D viewer:', error);
    }
  });
}

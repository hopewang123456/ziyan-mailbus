/**
 * Mailbus Dashboard — Three.js 背景 / Agent 轨道 / 审批粒子 / Workflow 3D 管道
 * 加载：index.html importmap + type="module"
 */
import * as THREE from 'three';

const REDUCED_MOTION = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
const MOBILE = typeof innerWidth !== 'undefined' && innerWidth < 900;

let _bg = null;
let _orbit = null;
let _wf3d = null;
let _paused = false;

function agentColor(id) {
  const map = (typeof window !== 'undefined' && window.AGENT_COLORS) || {};
  const hex = map[id] || '#38bdf8';
  return new THREE.Color(hex);
}

/** ── 全局星场背景（替换 2D 粒子） ── */
export function initThreeBackground(canvas) {
  if (!canvas || REDUCED_MOTION || MOBILE) return null;
  if (_bg) {
    _bg.destroy();
    _bg = null;
  }
  try {
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: 'low-power' });
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 2000);
    camera.position.z = 400;

    const count = 120;
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(count * 3);
    const vel = [];
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 800;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 600;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 400;
      vel.push({ x: (Math.random() - 0.5) * 0.15, y: (Math.random() - 0.5) * 0.15 });
    }
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const mat = new THREE.PointsMaterial({ color: 0x00d4ff, size: 1.2, transparent: true, opacity: 0.55, sizeAttenuation: true });
    const points = new THREE.Points(geo, mat);
    scene.add(points);

    const lineGeo = new THREE.BufferGeometry();
    const linePos = new Float32Array(count * count * 6);
    lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3));
    const lineMat = new THREE.LineBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.06 });
    const lines = new THREE.LineSegments(lineGeo, lineMat);
    scene.add(lines);

    function resize() {
      const w = innerWidth;
      const h = innerHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
    resize();

    let raf = 0;
    function tick() {
      if (_paused) { raf = requestAnimationFrame(tick); return; }
      const arr = geo.attributes.position.array;
      for (let i = 0; i < count; i++) {
        arr[i * 3] += vel[i].x;
        arr[i * 3 + 1] += vel[i].y;
        if (Math.abs(arr[i * 3]) > 400) vel[i].x *= -1;
        if (Math.abs(arr[i * 3 + 1]) > 300) vel[i].y *= -1;
      }
      geo.attributes.position.needsUpdate = true;

      let li = 0;
      const maxDist = 100;
      for (let i = 0; i < count; i++) {
        for (let j = i + 1; j < count; j++) {
          const dx = arr[i * 3] - arr[j * 3];
          const dy = arr[i * 3 + 1] - arr[j * 3 + 1];
          const dz = arr[i * 3 + 2] - arr[j * 3 + 2];
          if (dx * dx + dy * dy + dz * dz < maxDist * maxDist) {
            linePos[li++] = arr[i * 3]; linePos[li++] = arr[i * 3 + 1]; linePos[li++] = arr[i * 3 + 2];
            linePos[li++] = arr[j * 3]; linePos[li++] = arr[j * 3 + 1]; linePos[li++] = arr[j * 3 + 2];
          }
        }
      }
      lineGeo.setDrawRange(0, li / 3);
      lineGeo.attributes.position.needsUpdate = true;
      points.rotation.y += 0.0003;
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    }
    tick();

    const onResize = () => resize();
    addEventListener('resize', onResize);

    _bg = {
      destroy() {
        cancelAnimationFrame(raf);
        removeEventListener('resize', onResize);
        renderer.dispose();
        geo.dispose();
        mat.dispose();
        lineGeo.dispose();
        lineMat.dispose();
        _bg = null;
      },
    };
    return _bg;
  } catch (e) {
    console.warn('Three.js background unavailable:', e);
    return null;
  }
}

/** ── Agent 环状轨道（#agentOrbitHost） ── */
export function renderAgentOrbit(host, agentsPayload, workloadPayload) {
  if (!host) return;
  destroyAgentOrbit();
  if (REDUCED_MOTION || MOBILE) {
    host.style.display = 'none';
    return;
  }
  host.style.display = 'block';
  const agents = (agentsPayload && agentsPayload.agents) || {};
  const wl = (workloadPayload && workloadPayload.agents) || {};
  const ids = Object.keys(agents);
  if (!ids.length) return;

  const w = host.clientWidth || 640;
  const h = 220;
  host.innerHTML = '';
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  canvas.style.width = '100%';
  canvas.style.height = h + 'px';
  canvas.style.borderRadius = '8px';
  host.appendChild(canvas);

  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setSize(w, h);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, w / h, 1, 1000);
  camera.position.set(0, 80, 180);
  camera.lookAt(0, 0, 0);

  const ringGeo = new THREE.TorusGeometry(70, 0.4, 8, 64);
  const ringMat = new THREE.MeshBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.25 });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  scene.add(ring);

  const nodes = [];
  ids.forEach((id, i) => {
    const angle = (i / ids.length) * Math.PI * 2;
    const r = 70;
    const x = Math.cos(angle) * r;
    const z = Math.sin(angle) * r;
    const load = (wl[id] && wl[id].active_tasks) || 0;
    const size = 3 + Math.min(load, 5) * 0.8;
    const geo = new THREE.SphereGeometry(size, 16, 16);
    const mat = new THREE.MeshPhongMaterial({ color: agentColor(id), emissive: agentColor(id), emissiveIntensity: 0.35 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, Math.sin(i) * 4, z);
    mesh.userData = { id, angle, r, phase: i * 0.7 };
    scene.add(mesh);
    nodes.push(mesh);
  });

  const light = new THREE.DirectionalLight(0xffffff, 0.8);
  light.position.set(50, 100, 50);
  scene.add(light);
  scene.add(new THREE.AmbientLight(0x404060, 0.6));

  let raf = 0;
  const t0 = performance.now();
  function tick(now) {
    if (_paused) { raf = requestAnimationFrame(tick); return; }
    const t = (now - t0) * 0.001;
    nodes.forEach((m) => {
      const a = m.userData.angle + t * 0.08;
      m.position.x = Math.cos(a) * m.userData.r;
      m.position.z = Math.sin(a) * m.userData.r;
      m.position.y = Math.sin(t * 2 + m.userData.phase) * 3;
    });
    ring.rotation.y += 0.002;
    renderer.render(scene, camera);
    raf = requestAnimationFrame(tick);
  }
  tick(t0);

  _orbit = {
    destroy() {
      cancelAnimationFrame(raf);
      renderer.dispose();
      ringGeo.dispose();
      ringMat.dispose();
      nodes.forEach((m) => { m.geometry.dispose(); m.material.dispose(); });
      if (host) host.innerHTML = '';
      _orbit = null;
    },
  };
}

export function destroyAgentOrbit() {
  if (_orbit) _orbit.destroy();
}

/** ── human-queue 批准粒子 burst ── */
export function burstApprovalParticles(container) {
  if (!container || REDUCED_MOTION) return;
  const rect = container.getBoundingClientRect();
  const host = document.createElement('div');
  host.className = 'hq-particle-burst';
  host.style.cssText = 'position:fixed;left:' + rect.left + 'px;top:' + rect.top + 'px;width:' + rect.width + 'px;height:' + rect.height + 'px;pointer-events:none;z-index:200;overflow:hidden;border-radius:8px';
  document.body.appendChild(host);
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(rect.width, 200);
  canvas.height = Math.max(rect.height, 120);
  host.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  const parts = [];
  for (let i = 0; i < 24; i++) {
    parts.push({
      x: canvas.width / 2, y: canvas.height / 2,
      vx: (Math.random() - 0.5) * 6, vy: (Math.random() - 0.5) * 6 - 2,
      life: 1, hue: Math.random() * 60 + 160,
    });
  }
  let frame = 0;
  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let alive = false;
    parts.forEach((p) => {
      if (p.life <= 0) return;
      alive = true;
      p.x += p.vx; p.y += p.vy; p.vy += 0.08; p.life -= 0.025;
      ctx.globalAlpha = p.life;
      ctx.fillStyle = 'hsl(' + p.hue + ',90%,60%)';
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    });
    frame++;
    if (alive && frame < 80) requestAnimationFrame(draw);
    else host.remove();
  }
  draw();
}

/** ── Workflow 3D 管道（phase 节点） ── */
export function renderWorkflowPipeline(host, phases, accentHex) {
  if (!host || !phases || !phases.length) return;
  destroyWorkflowPipeline();
  if (REDUCED_MOTION || MOBILE) {
    host.style.display = 'none';
    return;
  }
  host.style.display = 'block';
  const w = host.clientWidth || 600;
  const h = 140;
  host.innerHTML = '';
  const canvas = document.createElement('canvas');
  canvas.style.width = '100%';
  canvas.style.height = h + 'px';
  host.appendChild(canvas);
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setSize(w, h);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, w / h, 1, 500);
  camera.position.set(0, 40, 120);
  camera.lookAt(0, 0, 0);

  const color = new THREE.Color(accentHex || '#38bdf8');
  const spacing = Math.min(55, (w - 80) / Math.max(phases.length, 1));
  const startX = -((phases.length - 1) * spacing) / 2;
  const tubes = [];

  phases.forEach((p, i) => {
    const x = startX + i * spacing;
    const geo = new THREE.CylinderGeometry(8, 8, 20, 12);
    const mat = new THREE.MeshPhongMaterial({ color, transparent: true, opacity: 0.85, emissive: color, emissiveIntensity: 0.2 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, 0, 0);
    mesh.rotation.z = Math.PI / 2;
    scene.add(mesh);
    tubes.push(mesh);
    if (i < phases.length - 1) {
      const path = new THREE.CatmullRomCurve3([
        new THREE.Vector3(x + 10, 0, 0),
        new THREE.Vector3(x + spacing * 0.5, 8, 0),
        new THREE.Vector3(x + spacing - 10, 0, 0),
      ]);
      const tubeGeo = new THREE.TubeGeometry(path, 8, 1.2, 6, false);
      const tubeMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.4 });
      scene.add(new THREE.Mesh(tubeGeo, tubeMat));
    }
  });

  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const dl = new THREE.DirectionalLight(0xffffff, 0.7);
  dl.position.set(0, 50, 80);
  scene.add(dl);

  let raf = 0;
  const t0 = performance.now();
  function tick(now) {
    if (_paused || !host.isConnected) { raf = requestAnimationFrame(tick); return; }
    const t = (now - t0) * 0.001;
    tubes.forEach((m, i) => {
      m.position.y = Math.sin(t * 2 + i * 0.8) * 4;
      m.rotation.x = t * 0.5 + i;
    });
    renderer.render(scene, camera);
    raf = requestAnimationFrame(tick);
  }
  tick(t0);

  _wf3d = {
    destroy() {
      cancelAnimationFrame(raf);
      renderer.dispose();
      if (host) host.innerHTML = '';
      _wf3d = null;
    },
  };
}

export function destroyWorkflowPipeline() {
  if (_wf3d) _wf3d.destroy();
}

/** Agent 资料卡 — 3D 动态肖像（纹理 + 呼吸/转头） */
let _portrait3d = null;

export function mountAgentPortrait3D(host, opts = {}) {
  if (!host) return null;
  if (_portrait3d) {
    _portrait3d.destroy();
    _portrait3d = null;
  }
  if (REDUCED_MOTION) {
    host.innerHTML = '<img src="' + (opts.textureUrls && opts.textureUrls[0] || '') + '" style="width:100%;height:100%;object-fit:cover;border-radius:14px" alt="">';
    return null;
  }

  const w = host.clientWidth || 340;
  const h = host.clientHeight || 400;
  const accent = opts.accent || '#38bdf8';
  const urls = opts.textureUrls || [];
  const videoUrl = opts.videoUrl || '';
  const staticPortrait = opts.staticPortrait === true;

  try {
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.setSize(w, h);
    renderer.domElement.style.borderRadius = '14px';
    host.innerHTML = '';
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(28, w / h, 0.1, 20);
    camera.position.set(0, 0.05, 2.35);

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 0.85);
    key.position.set(1.2, 1.5, 2);
    scene.add(key);
    const rim = new THREE.PointLight(new THREE.Color(accent), 1.2, 8);
    rim.position.set(-1.5, 0.5, 1.2);
    scene.add(rim);

    const group = new THREE.Group();
    scene.add(group);

    const seg = 48;
    const geo = new THREE.PlaneGeometry(1.15, 1.42, seg, seg);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const bulge = Math.exp(-(x * x * 1.8 + y * y * 1.2)) * 0.22;
      pos.setZ(i, bulge);
    }
    geo.computeVertexNormals();

    let mat;
    if (videoUrl) {
      const vid = document.createElement('video');
      vid.src = videoUrl;
      vid.crossOrigin = 'anonymous';
      vid.loop = true;
      vid.muted = true;
      vid.playsInline = true;
      vid.autoplay = true;
      vid.play().catch(() => {});
      const tex = new THREE.VideoTexture(vid);
      tex.colorSpace = THREE.SRGBColorSpace;
      mat = new THREE.MeshStandardMaterial({
        map: tex, roughness: 0.45, metalness: 0.08, transparent: true,
      });
    } else {
      const loader = new THREE.TextureLoader();
      const tex = loader.load(urls[0] || '', () => {}, undefined, () => {
        if (urls[1]) loader.load(urls[1], (t2) => { mat.map = t2; mat.needsUpdate = true; });
      });
      tex.colorSpace = THREE.SRGBColorSpace;
      mat = new THREE.MeshStandardMaterial({
        map: tex, roughness: 0.38, metalness: 0.12, transparent: true,
      });
    }

    const mesh = new THREE.Mesh(geo, mat);
    group.add(mesh);

    // 前景光晕
    const glowGeo = new THREE.RingGeometry(0.85, 1.05, 64);
    const glowMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(accent), transparent: true, opacity: 0.12, side: THREE.DoubleSide,
    });
    const glow = new THREE.Mesh(glowGeo, glowMat);
    glow.position.z = -0.08;
    group.add(glow);

    let raf = 0;
    const t0 = performance.now();
    function tick(now) {
      if (!host.isConnected) return;
      const t = (now - t0) * 0.001;
      if (!staticPortrait) {
        group.rotation.y = Math.sin(t * 0.55) * 0.28;
        group.rotation.x = Math.sin(t * 0.35) * 0.04 - 0.02;
        const breath = 1 + Math.sin(t * 1.6) * 0.018;
        group.scale.set(breath, breath, breath);
        rim.intensity = 0.9 + Math.sin(t * 2) * 0.25;
      }
      if (mat.map && mat.map.isVideoTexture) mat.map.needsUpdate = true;
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    }
    tick(t0);

    _portrait3d = {
      destroy() {
        cancelAnimationFrame(raf);
        renderer.dispose();
        geo.dispose();
        mat.dispose();
        glowGeo.dispose();
        glowMat.dispose();
        if (host) host.innerHTML = '';
        _portrait3d = null;
      },
    };
    return _portrait3d;
  } catch (e) {
    console.warn('portrait3d:', e);
    host.innerHTML = '<img src="' + (urls[0] || '') + '" style="width:100%;height:100%;object-fit:cover" alt="">';
    return null;
  }
}

export function destroyAgentPortrait3D() {
  if (_portrait3d) _portrait3d.destroy();
}

export function pauseThreeScenes() {
  _paused = true;
}

export function resumeThreeScenes() {
  _paused = false;
}

export function destroyAllThree() {
  if (_bg) _bg.destroy();
  destroyAgentOrbit();
  destroyWorkflowPipeline();
  destroyAgentPortrait3D();
}

if (typeof window !== 'undefined') {
  window.MailbusThree = {
    initThreeBackground,
    renderAgentOrbit,
    destroyAgentOrbit,
    burstApprovalParticles,
    renderWorkflowPipeline,
    destroyWorkflowPipeline,
    mountAgentPortrait3D,
    destroyAgentPortrait3D,
    pauseThreeScenes,
    resumeThreeScenes,
    destroyAllThree,
  };
}

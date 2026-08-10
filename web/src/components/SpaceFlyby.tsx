import { Canvas, useFrame } from "@react-three/fiber";
import { memo, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import {
  playDodgeBlip,
  playFlybyPass,
  playMeteorWhoosh,
  playNebulaBlip,
  unlockCockpitAudio,
} from "../lib/cockpit-audio";

/**
 * 窗外景色（对齐可观测宇宙层次，非暗能量质量比）：
 * 远场：星系 ≫ 星云/星尘 ≫ 点状恒星场
 * 近场：陨石 ≫ 有伴星的恒星系 > 致密残骸（白矮/脉冲/黑洞）
 * 物理示意：质量→引力势阱；密度/表面g→近轨加速；霜线体型；开普勒公转；
 * 恒星默认远距分立（各带行星/陨石带）；密近双星才出现三体纠缠
 * 白洞为理论解，默认不出现；航向仍是前方双子星云
 */

/** 软光晕：平滑衰减 + 微噪声破同心「指纹」环（纯 radialGradient 易出条带） */
function makeGlowTex(stops: [number, string][], size = 256) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  for (const [p, col] of stops) g.addColorStop(p, col);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  // 破环：极低对比噪声打散量化条带
  const img = ctx.getImageData(0, 0, size, size);
  const d = img.data;
  const cx = size / 2;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      if (d[i + 3] < 2) continue;
      const dx = (x - cx) / cx;
      const dy = (y - cx) / cx;
      const r = Math.sqrt(dx * dx + dy * dy);
      // 椭圆扰动，避免正圆 ripples
      const n = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453;
      const nf = (n - Math.floor(n)) * 2 - 1;
      const jitter = 1 + nf * 0.04 * (1 - r);
      d[i] = Math.min(255, d[i] * jitter);
      d[i + 1] = Math.min(255, d[i + 1] * jitter);
      d[i + 2] = Math.min(255, d[i + 2] * jitter);
      d[i + 3] = Math.min(255, d[i + 3] * (0.92 + nf * 0.08));
    }
  }
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.minFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  return tex;
}

/** 超新星光晕：多瓣/丝状/偏心，刻意避免正圆径向光 */
function makeSupernovaTex(size = 256) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  ctx.clearRect(0, 0, size, size);
  const cx = size * (0.42 + Math.random() * 0.16);
  const cy = size * (0.4 + Math.random() * 0.2);

  const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, size * 0.22);
  core.addColorStop(0, "rgba(255,255,255,0.95)");
  core.addColorStop(0.35, "rgba(255,210,140,0.7)");
  core.addColorStop(1, "rgba(255,120,40,0)");
  ctx.fillStyle = core;
  ctx.beginPath();
  ctx.ellipse(cx, cy, size * 0.2, size * 0.12, Math.random() * Math.PI, 0, Math.PI * 2);
  ctx.fill();

  const lobes = 4 + Math.floor(Math.random() * 3);
  for (let i = 0; i < lobes; i++) {
    const ang = (i / lobes) * Math.PI * 2 + Math.random() * 0.5;
    const len = size * (0.22 + Math.random() * 0.28);
    const thick = size * (0.04 + Math.random() * 0.08);
    const ox = cx + Math.cos(ang) * len * 0.35;
    const oy = cy + Math.sin(ang) * len * 0.35;
    const g = ctx.createRadialGradient(ox, oy, 0, ox, oy, len);
    const warm = Math.random() > 0.45;
    g.addColorStop(0, warm ? "rgba(255,200,120,0.55)" : "rgba(180,140,255,0.4)");
    g.addColorStop(0.45, warm ? "rgba(255,100,40,0.22)" : "rgba(100,80,200,0.15)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.ellipse(ox, oy, len, thick, ang, 0, Math.PI * 2);
    ctx.fill();
  }

  for (let i = 0; i < 14; i++) {
    const ang = Math.random() * Math.PI * 2;
    const r0 = size * (0.08 + Math.random() * 0.12);
    const r1 = size * (0.28 + Math.random() * 0.3);
    ctx.strokeStyle = Math.random() > 0.5 ? "rgba(255,180,100,0.22)" : "rgba(160,150,255,0.18)";
    ctx.lineWidth = 1 + Math.random() * 2.5;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(ang) * r0, cy + Math.sin(ang) * r0);
    const bend = ang + (Math.random() - 0.5) * 0.7;
    ctx.quadraticCurveTo(
      cx + Math.cos(bend) * (r0 + r1) * 0.5,
      cy + Math.sin(bend) * (r0 + r1) * 0.5,
      cx + Math.cos(ang + 0.2) * r1,
      cy + Math.sin(ang + 0.2) * r1,
    );
    ctx.stroke();
  }

  const img = ctx.getImageData(0, 0, size, size);
  const d = img.data;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      if (d[i + 3] < 2) continue;
      const n = Math.sin(x * 19.1 + y * 47.3) * 43758.5453;
      const nf = n - Math.floor(n);
      d[i + 3] = Math.min(255, d[i + 3] * (0.75 + nf * 0.45));
    }
  }
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.minFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  return tex;
}

function makePlanetTex(base: string, spot: string, bands = false, size = 256) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  if (bands) {
    // 气巨星条带：高对比，自转一眼可读
    for (let y = 0; y < size; y++) {
      const t = y / size;
      const stripe = Math.sin(t * Math.PI * 14) * 0.5 + 0.5;
      ctx.fillStyle = stripe > 0.55 ? base : spot;
      ctx.fillRect(0, y, size, 1);
    }
    for (let i = 0; i < 8; i++) {
      ctx.fillStyle = spot;
      ctx.globalAlpha = 0.25 + Math.random() * 0.35;
      ctx.beginPath();
      ctx.ellipse(
        Math.random() * size,
        size * (0.25 + Math.random() * 0.5),
        18 + Math.random() * 40,
        4 + Math.random() * 8,
        0,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }
  } else {
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, size, size);
    // 大陆/陨石斑块：提供自转视觉锚点
    for (let i = 0; i < 48; i++) {
      ctx.fillStyle = spot;
      ctx.globalAlpha = 0.2 + Math.random() * 0.45;
      ctx.beginPath();
      ctx.ellipse(
        Math.random() * size,
        Math.random() * size,
        8 + Math.random() * 42,
        4 + Math.random() * 20,
        Math.random() * Math.PI,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }
  }
  ctx.globalAlpha = 1;
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.RepeatWrapping;
  return tex;
}

/** 恒星光球纹理：亮斑/暗带，否则纯色球自转不可见 */
function makeStarSurfaceTex(hot = "#fff6d0", cool = "#ff9a40", size = 128) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = hot;
  ctx.fillRect(0, 0, size, size);
  for (let y = 0; y < size; y++) {
    const t = y / size;
    ctx.globalAlpha = 0.12 + 0.18 * Math.sin(t * Math.PI * 8);
    ctx.fillStyle = cool;
    ctx.fillRect(0, y, size, 1);
  }
  for (let i = 0; i < 28; i++) {
    ctx.globalAlpha = 0.15 + Math.random() * 0.35;
    ctx.fillStyle = Math.random() > 0.45 ? "#ffffff" : cool;
    ctx.beginPath();
    ctx.ellipse(
      Math.random() * size,
      Math.random() * size,
      3 + Math.random() * 14,
      2 + Math.random() * 6,
      Math.random() * Math.PI,
      0,
      Math.PI * 2,
    );
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/**
 * 横贯视场的星河带纹理（平面贴图，不用穹顶 UV——球面会投成「右上灰渍」）。
 * 物理动机：未分辨恒星积分光 + 乘性尘埃消光；灰白、低饱和；无径向指纹色团。
 */
function makeMilkyWayBandTex() {
  const w = 2048;
  const h = 384;
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d")!;
  const img = ctx.createImageData(w, h);
  const data = img.data;

  const hash2 = (ix: number, iy: number) => {
    let n = ix * 374761393 + iy * 668265263;
    n = (n ^ (n >>> 13)) * 1274126177;
    return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
  };
  const valueNoise = (x: number, y: number) => {
    const x0 = Math.floor(x);
    const y0 = Math.floor(y);
    const fx = x - x0;
    const fy = y - y0;
    const ux = fx * fx * (3 - 2 * fx);
    const uy = fy * fy * (3 - 2 * fy);
    const a = hash2(x0, y0);
    const b = hash2(x0 + 1, y0);
    const c0 = hash2(x0, y0 + 1);
    const d = hash2(x0 + 1, y0 + 1);
    return a + (b - a) * ux + (c0 - a) * uy + (a - b - c0 + d) * ux * uy;
  };
  const fbm = (x: number, y: number) => {
    let v = 0;
    let amp = 0.5;
    let f = 1;
    for (let i = 0; i < 4; i++) {
      v += amp * valueNoise(x * f, y * f);
      amp *= 0.5;
      f *= 2.1;
    }
    return v;
  };

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const u = x / w;
      const v = y / h;
      // 河带中线微起伏（跨整幅宽度）
      const mid = 0.5 + 0.06 * Math.sin(u * Math.PI * 2) + 0.03 * Math.sin(u * Math.PI * 5.3);
      const half = 0.22 + 0.06 * Math.sin(u * Math.PI * 3.1 + 0.4);
      const lat = (v - mid) / half;
      const disk = Math.exp(-lat * lat * 2.6);
      if (disk < 0.02) continue;

      const clumps = 0.5 + 0.5 * fbm(u * 10, v * 6);
      // 银心略亮（纹理中段）
      const bulge = 1 + 0.45 * Math.exp(-Math.pow((u - 0.55) * 3.2, 2));
      // 大裂谷：乘性消光切开河带
      const rift =
        Math.exp(-Math.pow((u - 0.42) * 6.5, 2)) * Math.exp(-Math.pow(lat * 0.55, 2)) +
        0.5 * Math.exp(-Math.pow((u - 0.68) * 8, 2)) * Math.exp(-Math.pow(lat * 0.8, 2));
      const dust = Math.max(0, fbm(u * 22, v * 14) - 0.5) * 1.4;
      const transm = Math.max(0.12, 1 - rift * 0.9 - dust * disk * 0.4);
      // 偏暗弥散：不要「喷漆白带」
      const L = disk * clumps * transm * bulge * 0.32;

      const i = (y * w + x) * 4;
      data[i] = 175;
      data[i + 1] = 182;
      data[i + 2] = 198;
      data[i + 3] = Math.min(255, (L * 255) | 0);
    }
  }
  ctx.putImageData(img, 0, 0);
  // 稀疏微星（勿密成砂纸）
  for (let i = 0; i < 1200; i++) {
    const x = Math.random() * w;
    const u = x / w;
    const mid = h * (0.5 + 0.06 * Math.sin(u * Math.PI * 2));
    const y = mid + (Math.random() - 0.5) * h * 0.32;
    ctx.fillStyle = `rgba(220,228,240,${0.12 + Math.random() * 0.28})`;
    ctx.fillRect(x, y, 1, 1);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  return tex;
}

type GalaxyMorph = "spiral" | "elliptical" | "irregular";

function makeGalaxyTex(morph: GalaxyMorph = "spiral") {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const ctx = c.getContext("2d")!;
  ctx.clearRect(0, 0, 256, 256);
  const cx = 128;
  const cy = 128;
  if (morph === "elliptical") {
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, 110);
    g.addColorStop(0, "rgba(255,245,230,0.95)");
    g.addColorStop(0.2, "rgba(255,210,160,0.55)");
    g.addColorStop(0.55, "rgba(120,100,180,0.18)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.ellipse(cx, cy, 110, 70, 0, 0, Math.PI * 2);
    ctx.fill();
  } else if (morph === "irregular") {
    for (let i = 0; i < 7; i++) {
      const g = ctx.createRadialGradient(cx + (Math.random() - 0.5) * 80, cy + (Math.random() - 0.5) * 70, 0, cx, cy, 40 + Math.random() * 40);
      g.addColorStop(0, `rgba(${180 + Math.random() * 75},${160 + Math.random() * 60},${220},0.55)`);
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, 256, 256);
    }
  } else {
    // spiral-ish: bright core + faint arms
    const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, 40);
    core.addColorStop(0, "rgba(255,255,255,0.95)");
    core.addColorStop(0.35, "rgba(255,220,170,0.55)");
    core.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = core;
    ctx.fillRect(0, 0, 256, 256);
    ctx.strokeStyle = "rgba(160,140,255,0.28)";
    ctx.lineWidth = 10;
    for (let arm = 0; arm < 2; arm++) {
      ctx.beginPath();
      for (let a = 0; a < Math.PI * 1.6; a += 0.08) {
        const r = 28 + a * 38;
        const ang = a + arm * Math.PI + 0.4;
        const x = cx + Math.cos(ang) * r;
        const y = cy + Math.sin(ang) * r * 0.55;
        if (a === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    const halo = ctx.createRadialGradient(cx, cy, 50, cx, cy, 120);
    halo.addColorStop(0, "rgba(80,100,200,0.12)");
    halo.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, 256, 256);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeNebulaTex(kind: "emission" | "reflection" | "planetary" | "dark") {
  if (kind === "dark") {
    return makeGlowTex([
      [0, "rgba(8,10,18,0.85)"],
      [0.35, "rgba(12,14,22,0.45)"],
      [0.7, "rgba(5,6,10,0.15)"],
      [1, "rgba(0,0,0,0)"],
    ], 256);
  }
  if (kind === "planetary") {
    const c = document.createElement("canvas");
    c.width = c.height = 256;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, 256, 256);
    const g = ctx.createRadialGradient(128, 128, 20, 128, 128, 110);
    g.addColorStop(0, "rgba(255,255,255,0.9)");
    g.addColorStop(0.18, "rgba(120,220,255,0.55)");
    g.addColorStop(0.4, "rgba(80,160,255,0.0)");
    g.addColorStop(0.55, "rgba(180,80,255,0.35)");
    g.addColorStop(0.75, "rgba(40,100,200,0.12)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 256, 256);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }
  if (kind === "reflection") {
    return makeGlowTex([
      [0, "rgba(200,220,255,0.55)"],
      [0.3, "rgba(120,160,255,0.22)"],
      [0.65, "rgba(60,80,160,0.08)"],
      [1, "rgba(0,0,0,0)"],
    ], 256);
  }
  // emission HII-like — 多层色团，避免单一光晕显得假
  {
    const c = document.createElement("canvas");
    c.width = c.height = 256;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, 256, 256);
    const blobs: [number, number, number, string, string][] = [
      [110, 120, 90, "rgba(255,140,180,0.55)", "rgba(255,60,100,0.0)"],
      [160, 100, 70, "rgba(80,200,255,0.4)", "rgba(40,80,180,0.0)"],
      [90, 160, 75, "rgba(180,100,255,0.35)", "rgba(60,20,120,0.0)"],
      [140, 150, 55, "rgba(255,200,120,0.28)", "rgba(120,40,20,0.0)"],
    ];
    for (const [x, y, r, a, b] of blobs) {
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, a);
      g.addColorStop(1, b);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, 256, 256);
    }
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }
}

/** 河带白雾里的远星闪烁（大气/衍射级 scintillation，非近景霓虹） */
function MilkyWayTwinkles() {
  const ref = useRef<THREE.Points>(null);
  const { geom, mat } = useMemo(() => {
    const count = 900;
    const pos = new Float32Array(count * 3);
    const col = new Float32Array(count * 3);
    const size = new Float32Array(count);
    const phase = new Float32Array(count);
    const speed = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      // 与主河带同局部坐标：宽 × 薄 × 微纵深
      const x = (Math.random() - 0.5) * 380;
      const envelope = Math.exp(-Math.pow(x / 200, 2) * 0.15); // 两端略稀
      const y = (Math.random() - 0.5) * 42 * (0.55 + 0.45 * Math.random()) * envelope;
      const z = (Math.random() - 0.5) * 6;
      pos[i * 3] = x;
      pos[i * 3 + 1] = y;
      pos[i * 3 + 2] = z;
      // 冷白为主，偶有微暖（K 型）
      const warm = Math.random() < 0.18 ? 1 : 0;
      const b = 0.55 + Math.random() * 0.45;
      col[i * 3] = (warm ? 1 : 0.82) * b;
      col[i * 3 + 1] = (warm ? 0.92 : 0.9) * b;
      col[i * 3 + 2] = (warm ? 0.78 : 1) * b;
      const roll = Math.random();
      size[i] =
        roll < 0.78 ? 0.9 + Math.random() * 1.4 : roll < 0.95 ? 2.2 + Math.random() * 1.8 : 4 + Math.random() * 2.5;
      phase[i] = Math.random() * Math.PI * 2;
      // 慢闪：约 0.15–0.55 Hz 量级，勿霓虹频闪
      speed[i] = 0.18 + Math.random() * 0.4;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    g.setAttribute("size", new THREE.BufferAttribute(size, 1));
    g.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
    g.setAttribute("aSpeed", new THREE.BufferAttribute(speed, 1));
    const m = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      depthTest: false,
      fog: false,
      blending: THREE.AdditiveBlending,
      vertexColors: true,
      uniforms: {
        uTime: { value: 0 },
        uPixelRatio: { value: Math.min(window.devicePixelRatio, 2) },
      },
      vertexShader: `
        attribute float size;
        attribute float aPhase;
        attribute float aSpeed;
        varying vec3 vColor;
        varying float vTwinkle;
        uniform float uTime;
        uniform float uPixelRatio;
        void main() {
          vColor = color;
          // 慢起伏 + 偶发弱尖峰（尖峰也降频）
          float s = 0.5 + 0.5 * sin(uTime * aSpeed + aPhase);
          float spike = pow(0.5 + 0.5 * sin(uTime * aSpeed * 1.35 + aPhase * 1.1), 8.0);
          vTwinkle = 0.4 + 0.45 * s + 0.22 * spike;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * uPixelRatio * vTwinkle * (180.0 / max(40.0, -mv.z));
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        varying float vTwinkle;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          float a = smoothstep(0.5, 0.0, d);
          gl_FragColor = vec4(vColor, a * vTwinkle * 0.85);
        }
      `,
    });
    return { geom: g, mat: m };
  }, []);
  useFrame((state) => {
    mat.uniforms.uTime.value = state.clock.elapsedTime;
  });
  return <points ref={ref} geometry={geom} material={mat} renderOrder={-9} />;
}

/**
 * 正对相机的超宽河带：两端伸出视锥，斜贯整屏舷窗。
 * （球面贴图在当前机位会缩成右上角灰渍，用户反馈「没有星河」）
 */
function DistantMilkyWay() {
  const group = useRef<THREE.Group>(null);
  const tex = useMemo(() => makeMilkyWayBandTex(), []);
  useFrame(() => {
    if (!group.current) return;
    group.current.position.x = 2 + Math.sin(performance.now() * 0.00002) * 2;
  });
  // 相机 lookAt(3.2,1.5,-54)；平面在双子后方，两端伸出视锥
  return (
    <group ref={group} position={[2, 1.5, -88]} rotation={[0, 0, -0.48]} renderOrder={-10}>
      <mesh scale={[420, 110, 1]} renderOrder={-11}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial
          map={tex}
          transparent
          depthWrite={false}
          depthTest={false}
          fog={false}
          blending={THREE.AdditiveBlending}
          opacity={0.22}
          side={THREE.DoubleSide}
          toneMapped={false}
        />
      </mesh>
      <mesh scale={[400, 58, 1]} renderOrder={-10}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial
          map={tex}
          transparent
          depthWrite={false}
          depthTest={false}
          fog={false}
          blending={THREE.AdditiveBlending}
          opacity={0.62}
          side={THREE.DoubleSide}
          toneMapped={false}
        />
      </mesh>
      <MilkyWayTwinkles />
    </group>
  );
}

/** 远处河外星系：深场主体，近乎静止（可观测宇宙中星系远多于近景行星） */
function _DistantGalaxies() {
  const group = useRef<THREE.Group>(null);
  const texSpiral = useMemo(() => makeGalaxyTex("spiral"), []);
  const texEllip = useMemo(() => makeGalaxyTex("elliptical"), []);
  const texIrr = useMemo(() => makeGalaxyTex("irregular"), []);
  const items = useMemo(
    () =>
      Array.from({ length: 18 }, (_, i) => {
        const roll = Math.random();
        const morph: GalaxyMorph = roll < 0.55 ? "spiral" : roll < 0.85 ? "elliptical" : "irregular";
        // 绝大多数深场；极少中远场，避免满屏「星系刷屏」
        const mid = i < 4;
        return {
          key: i,
          morph,
          x: (Math.random() - 0.5) * (mid ? 70 : 100),
          y: (Math.random() - 0.5) * (mid ? 36 : 52),
          z: mid ? -85 - Math.random() * 30 : -120 - Math.random() * 80,
          s: mid
            ? 1.8 + Math.random() * (morph === "elliptical" ? 2.2 : 3.2)
            : 0.9 + Math.random() * (morph === "elliptical" ? 2.2 : 3.2),
          aspect: morph === "elliptical" ? 0.55 + Math.random() * 0.25 : 0.42 + Math.random() * 0.35,
          rot: Math.random() * Math.PI,
          opacity: mid ? 0.28 + Math.random() * 0.22 : 0.12 + Math.random() * 0.2,
        };
      }),
    [],
  );
  useFrame((_, dt) => {
    if (group.current) group.current.rotation.y += dt * 0.0015;
  });
  return (
    <group ref={group}>
      {items.map((it) => (
        <sprite
          key={it.key}
          position={[it.x, it.y, it.z]}
          scale={[it.s, it.s * it.aspect, 1]}
          rotation={[0, 0, it.rot]}
        >
          <spriteMaterial
            map={it.morph === "spiral" ? texSpiral : it.morph === "elliptical" ? texEllip : texIrr}
            transparent
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            opacity={it.opacity}
          />
        </sprite>
      ))}
    </group>
  );
}

function StarField() {
  const ref = useRef<THREE.Points>(null);
  const { geom, mat } = useMemo(() => {
    const count = 5200;
    const pos = new Float32Array(count * 3);
    const col = new Float32Array(count * 3);
    const size = new Float32Array(count);
    const palette = [
      [0.7, 0.82, 1],
      [1, 0.96, 0.88],
      [1, 0.72, 0.4],
      [0.5, 0.7, 1],
      [1, 0.5, 0.5],
    ];
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 110;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 65;
      pos[i * 3 + 2] = -Math.random() * 150 - 4;
      const p = palette[(Math.random() * palette.length) | 0];
      const bright = 0.5 + Math.random() * 0.5;
      col[i * 3] = p[0] * bright;
      col[i * 3 + 1] = p[1] * bright;
      col[i * 3 + 2] = p[2] * bright;
      const roll = Math.random();
      size[i] =
        roll < 0.84
          ? 0.035 + Math.random() * 0.05
          : roll < 0.96
            ? 0.1 + Math.random() * 0.1
            : 0.26 + Math.random() * 0.22;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    g.setAttribute("size", new THREE.BufferAttribute(size, 1));
    const m = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexColors: true,
      uniforms: { uPixelRatio: { value: Math.min(window.devicePixelRatio, 2) } },
      vertexShader: `
        attribute float size;
        varying vec3 vColor;
        uniform float uPixelRatio;
        void main() {
          vColor = color;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * uPixelRatio * (300.0 / -mv.z);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          float a = smoothstep(0.5, 0.0, d);
          gl_FragColor = vec4(vColor, a * 0.95);
        }
      `,
    });
    return { geom: g, mat: m };
  }, []);

  useFrame((_, dt) => {
    if (!ref.current) return;
    ref.current.position.z += dt * 4.2;
    if (ref.current.position.z > 50) ref.current.position.z = 0;
  });

  return <points ref={ref} geometry={geom} material={mat} />;
}

function TwinNebula() {
  const g = useRef<THREE.Group>(null);
  const flareA = useRef<THREE.Sprite>(null);
  const flareB = useRef<THREE.Sprite>(null);
  const lightA = useRef<THREE.PointLight>(null);
  const lightB = useRef<THREE.PointLight>(null);
  // 色标加密，减轻 radial 量化环
  const texCyan = useMemo(
    () =>
      makeGlowTex([
        [0, "rgba(255,255,255,0.9)"],
        [0.08, "rgba(160,235,255,0.7)"],
        [0.18, "rgba(80,210,255,0.48)"],
        [0.32, "rgba(20,160,240,0.28)"],
        [0.5, "rgba(30,100,200,0.12)"],
        [0.72, "rgba(20,60,140,0.04)"],
        [1, "rgba(0,0,0,0)"],
      ], 384),
    [],
  );
  const texViolet = useMemo(
    () =>
      makeGlowTex([
        [0, "rgba(255,240,255,0.9)"],
        [0.08, "rgba(230,150,255,0.68)"],
        [0.2, "rgba(180,80,255,0.42)"],
        [0.38, "rgba(200,60,160,0.22)"],
        [0.55, "rgba(160,40,100,0.1)"],
        [0.75, "rgba(80,20,60,0.03)"],
        [1, "rgba(0,0,0,0)"],
      ], 384),
    [],
  );
  const texDust = useMemo(
    () =>
      makeGlowTex([
        [0, "rgba(255,170,100,0.28)"],
        [0.25, "rgba(200,80,90,0.14)"],
        [0.55, "rgba(120,40,60,0.05)"],
        [1, "rgba(0,0,0,0)"],
      ], 256),
    [],
  );

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (g.current) {
      g.current.position.z = -54 + Math.sin(t * 0.05) * 1.2;
      g.current.rotation.z = Math.sin(t * 0.035) * 0.035;
    }
    const pulseA =
      0.55 + 0.45 * Math.pow(0.5 + 0.5 * Math.sin(t * 2.1), 3) * (0.7 + 0.3 * Math.sin(t * 7.3));
    const pulseB =
      0.5 + 0.5 * Math.pow(0.5 + 0.5 * Math.sin(t * 1.7 + 1.2), 3) * (0.65 + 0.35 * Math.sin(t * 5.8));
    if (flareA.current) {
      flareA.current.scale.setScalar(15 + pulseA * 7);
      (flareA.current.material as THREE.SpriteMaterial).opacity = 0.35 + pulseA * 0.55;
    }
    if (flareB.current) {
      flareB.current.scale.setScalar(13 + pulseB * 8);
      (flareB.current.material as THREE.SpriteMaterial).opacity = 0.3 + pulseB * 0.6;
    }
    if (lightA.current) lightA.current.intensity = 4 + pulseA * 14;
    if (lightB.current) lightB.current.intensity = 3.5 + pulseB * 16;
  });

  return (
    <group ref={g} position={[3.5, 2.2, -54]}>
      <sprite position={[0.5, -0.8, -3]} scale={[28, 16, 1]}>
        <spriteMaterial map={texDust} transparent depthWrite={false} blending={THREE.AdditiveBlending} opacity={0.55} />
      </sprite>
      <sprite ref={flareA} position={[-3.2, 0.8, 0]}>
        <spriteMaterial map={texCyan} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
      </sprite>
      <sprite ref={flareB} position={[3.6, -0.6, 1]}>
        <spriteMaterial map={texViolet} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
      </sprite>
      <pointLight ref={lightA} position={[-3, 0.8, 2]} color="#4de0ff" distance={55} />
      <pointLight ref={lightB} position={[3.5, -0.5, 2]} color="#c060ff" distance={55} />
    </group>
  );
}

function resetFar(obj: THREE.Object3D, spread = 20) {
  obj.position.z = -55 - Math.random() * 40;
  obj.position.x = (Math.random() - 0.5) * spread;
  obj.position.y = (Math.random() - 0.5) * 10;
}

const NEAR_SLOTS = new Set<string>();

function placeNearby(
  spreadX: number,
  spreadY: number,
  zBase: number,
  zJitter: number,
): [number, number, number] {
  for (let i = 0; i < 24; i++) {
    const x = (Math.random() - 0.5) * spreadX;
    const y = (Math.random() - 0.5) * spreadY;
    const z = zBase - Math.random() * zJitter;
    const key = `${Math.round(x * 2)}_${Math.round(y * 2)}_${Math.round(z / 6)}`;
    if (!NEAR_SLOTS.has(key)) {
      NEAR_SLOTS.add(key);
      if (NEAR_SLOTS.size > 180) NEAR_SLOTS.clear();
      return [x, y, z];
    }
  }
  return [(Math.random() - 0.5) * spreadX, (Math.random() - 0.5) * spreadY, zBase - Math.random() * zJitter];
}

type Spectral = "M" | "K" | "G" | "F" | "A";

/** 主序近似：质量决定引力势阱；密度/表面 g 决定近轨「拉得紧」的观感 */
type StarPhys = {
  color: string;
  glow: [number, string][];
  /** 视觉半径（M 矮星小而密） */
  radius: number;
  /** ~太阳质量 */
  mass: number;
  /** 相对平均密度（M/白矮高 → 近区轨道更紧更快） */
  density: number;
  /** 表面引力指数（∝ M/R² 的示意） */
  surfaceG: number;
};

function starPhys(spectral: Spectral): StarPhys {
  const table: Record<Spectral, StarPhys> = {
    // 红矮星：小、密、表面 g 高 → 紧凑多行星系（类 TRAPPIST）
    M: {
      color: "#ff6644",
      glow: [
        [0, "rgba(255,200,180,1)"],
        [0.2, "rgba(255,80,40,0.7)"],
        [0.55, "rgba(180,20,10,0.2)"],
        [1, "rgba(0,0,0,0)"],
      ],
      radius: 0.28,
      mass: 0.35,
      density: 2.8,
      surfaceG: 2.4,
    },
    K: {
      color: "#ffb060",
      glow: [
        [0, "rgba(255,220,160,1)"],
        [0.18, "rgba(255,140,60,0.65)"],
        [0.5, "rgba(200,80,20,0.18)"],
        [1, "rgba(0,0,0,0)"],
      ],
      radius: 0.4,
      mass: 0.7,
      density: 1.6,
      surfaceG: 1.5,
    },
    G: {
      color: "#fff2d0",
      glow: [
        [0, "rgba(255,255,255,1)"],
        [0.12, "rgba(255,240,200,0.85)"],
        [0.4, "rgba(255,170,80,0.3)"],
        [1, "rgba(0,0,0,0)"],
      ],
      radius: 0.55,
      mass: 1.0,
      density: 1.0,
      surfaceG: 1.0,
    },
    F: {
      color: "#f0f4ff",
      glow: [
        [0, "rgba(255,255,255,1)"],
        [0.15, "rgba(220,230,255,0.75)"],
        [0.45, "rgba(160,180,255,0.22)"],
        [1, "rgba(0,0,0,0)"],
      ],
      radius: 0.68,
      mass: 1.35,
      density: 0.75,
      surfaceG: 0.85,
    },
    A: {
      color: "#e8f0ff",
      glow: [
        [0, "rgba(255,255,255,1)"],
        [0.15, "rgba(200,220,255,0.75)"],
        [0.5, "rgba(120,160,255,0.2)"],
        [1, "rgba(0,0,0,0)"],
      ],
      radius: 0.82,
      mass: 2.0,
      density: 0.45,
      surfaceG: 0.7,
    },
  };
  return table[spectral];
}

function pickSpectral(): Spectral {
  const r = Math.random();
  if (r < 0.72) return "M";
  if (r < 0.87) return "K";
  if (r < 0.95) return "G";
  return r < 0.975 ? "F" : "A";
}

/** 恒星最小间距格子——同屏不宜「恒星挤成一团」 */
const STAR_SLOTS = new Set<string>();
function placeStarFar(delay: number): [number, number, number] {
  for (let i = 0; i < 32; i++) {
    const x = (Math.random() - 0.5) * 22;
    const y = (Math.random() - 0.5) * 10;
    const z = -40 - delay * 14 - Math.random() * 36;
    const key = `${Math.round(x / 4)}_${Math.round(y / 4)}_${Math.round(z / 14)}`;
    if (!STAR_SLOTS.has(key)) {
      STAR_SLOTS.add(key);
      if (STAR_SLOTS.size > 48) STAR_SLOTS.clear();
      return [x, y, z];
    }
  }
  return [(Math.random() - 0.5) * 22, (Math.random() - 0.5) * 10, -50 - delay * 14];
}

type BodyKind = "rocky" | "superEarth" | "ice" | "gas" | "dwarf";

type SystemMoon = { a: number; r: number; speed: number; phase: number };

type SystemPlanet = {
  a: number;
  e: number;
  r: number;
  kind: BodyKind;
  spin: number;
  phase: number;
  incline: number;
  tilt: number;
  moons: SystemMoon[];
};

function buildMoons(kind: BodyKind, planetR: number): SystemMoon[] {
  // 气巨/冰巨多卫星；岩质也可有（类地月）；矮行星偶见
  const n =
    kind === "gas"
      ? 2 + (Math.random() > 0.45 ? 1 : 0)
      : kind === "ice"
        ? 1 + (Math.random() > 0.4 ? 1 : 0)
        : kind === "dwarf"
          ? Math.random() > 0.65
            ? 1
            : 0
          : Math.random() > 0.28
            ? 1
            : 0;
  return Array.from({ length: n }, (_, i) => ({
    a: planetR * (2.1 + i * 0.9 + Math.random() * 0.55),
    r: planetR * (0.14 + Math.random() * 0.1) * (1 - i * 0.12),
    speed: 2.6 - i * 0.45 + Math.random() * 0.9,
    phase: Math.random() * Math.PI * 2,
  }));
}

/** 按质量/密度/霜线生成伴星：几乎每颗恒星都有行星或陨石带 */
function buildCompanions(phys: StarPhys): {
  planets: SystemPlanet[];
  beltInner: number;
  beltOuter: number;
  beltCount: number;
} {
  const frost = 2.2 * Math.sqrt(phys.mass); // 霜线随光度/质量外推的示意
  // 致密矮星：Roche/潮汐允许更近；高 surfaceG → 内区塞满
  const aMin = 0.55 * phys.radius * (2.2 / Math.max(0.8, phys.density));
  const planets: SystemPlanet[] = [];
  const nPlanets =
    phys.mass < 0.5 ? 4 + Math.floor(Math.random() * 2) : 3 + Math.floor(Math.random() * 2);

  for (let i = 0; i < nPlanets; i++) {
    const t = (i + 1) / (nPlanets + 0.5);
    // 紧凑系：高密度把轨道径向压缩
    const a = aMin + t * (3.8 + phys.mass * 2.2) * (1.15 / Math.sqrt(phys.density));
    let kind: BodyKind;
    let r: number;
    if (a < frost * 0.55) {
      kind = Math.random() > 0.55 ? "rocky" : "superEarth";
      r = kind === "superEarth" ? 0.14 + Math.random() * 0.06 : 0.08 + Math.random() * 0.05;
    } else if (a < frost) {
      kind = Math.random() > 0.4 ? "rocky" : "dwarf";
      r = kind === "dwarf" ? 0.06 + Math.random() * 0.04 : 0.1 + Math.random() * 0.06;
    } else if (a < frost * 1.55) {
      kind = Math.random() > 0.35 ? "gas" : "ice";
      r = kind === "gas" ? 0.38 + Math.random() * 0.18 : 0.26 + Math.random() * 0.1;
    } else {
      kind = Math.random() > 0.5 ? "ice" : "dwarf";
      r = kind === "ice" ? 0.22 + Math.random() * 0.1 : 0.07 + Math.random() * 0.04;
    }
    // 近星体必须更小（Roche / 潮汐）
    r *= 0.55 + 0.55 * Math.min(1, a / (frost * 0.9));
    planets.push({
      a,
      e: 0.03 + Math.random() * 0.1,
      r,
      kind,
      spin:
        kind === "gas"
          ? 2.0 + Math.random() * 1.2
          : kind === "dwarf"
            ? 0.4 + Math.random() * 0.4
            : 0.8 + Math.random() * 1.0,
      phase: Math.random() * Math.PI * 2,
      incline: (Math.random() - 0.5) * 0.22,
      tilt: 0.1 + Math.random() * 0.5,
      moons: buildMoons(kind, r),
    });
  }

  const beltInner = frost * 0.85;
  const beltOuter = frost * 1.15;
  const beltCount = 28 + Math.floor(phys.density * 18);
  return { planets, beltInner, beltOuter, beltCount };
}

/**
 * 有引力主机的恒星系：质量→开普勒常数；密度/表面g→近轨加速；必有行星或陨石带。
 */
function StarSystem({
  delay = 0,
  spectral = pickSpectral(),
}: {
  delay?: number;
  spectral?: Spectral;
}) {
  const root = useRef<THREE.Group>(null);
  const star = useRef<THREE.Mesh>(null);
  const carriers = useRef<(THREE.Group | null)[]>([]);
  const spinners = useRef<(THREE.Mesh | null)[]>([]);
  const moonMeshes = useRef<(THREE.Mesh | null)[][]>([]);
  const moonPhases = useRef<number[][]>([]);
  const beltRef = useRef<THREE.Points>(null);
  const whooshed = useRef(false);
  const pos = useMemo(() => placeStarFar(delay), [delay]);

  const phys = useMemo(() => starPhys(spectral), [spectral]);
  const seed = useMemo(() => {
    const companions = buildCompanions(phys);
    moonPhases.current = companions.planets.map((p) => p.moons.map((m) => m.phase));
    moonMeshes.current = companions.planets.map((p) => p.moons.map(() => null));
    // n = orbitK / a^{1.5}；orbitK ∝ √M，再乘表面 g 让致密矮星近轨更「咬」
    const orbitK = (0.95 + Math.random() * 0.25) * Math.sqrt(phys.mass) * (0.75 + 0.35 * phys.surfaceG);
    return {
      speed: 2.2 + Math.random() * 1.8,
      starSpin: 0.25 + phys.density * 0.2 + Math.random() * 0.25,
      scale: 0.48 + Math.random() * 0.22,
      orbitK,
      systemTilt: (Math.random() - 0.5) * 0.35,
      ...companions,
    };
  }, [phys]);

  const starGlow = useMemo(() => makeGlowTex(phys.glow, 128), [phys.glow]);
  const starSurf = useMemo(() => makeStarSurfaceTex(phys.color, "#ff8040"), [phys.color]);
  const textures = useMemo(
    () => ({
      rocky: makePlanetTex("#6a6058", "#c4a882"),
      superEarth: makePlanetTex("#4a6a58", "#a8c090"),
      ice: makePlanetTex("#7a9bb8", "#e8f4ff"),
      gas: makePlanetTex("#c49a4a", "#5a2e12", true),
      dwarf: makePlanetTex("#8a7a68", "#4a4038"),
      moon: makePlanetTex("#a8b0bc", "#5c646e"),
    }),
    [],
  );

  const beltGeom = useMemo(() => {
    const n = seed.beltCount;
    const posArr = new Float32Array(n * 3);
    const phase = new Float32Array(n);
    const rad = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      phase[i] = Math.random() * Math.PI * 2;
      rad[i] = seed.beltInner + Math.random() * (seed.beltOuter - seed.beltInner);
      posArr[i * 3] = Math.cos(phase[i]) * rad[i];
      posArr[i * 3 + 1] = (Math.random() - 0.5) * 0.15;
      posArr[i * 3 + 2] = Math.sin(phase[i]) * rad[i];
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(posArr, 3));
    g.setAttribute("phase", new THREE.BufferAttribute(phase, 1));
    g.setAttribute("rad", new THREE.BufferAttribute(rad, 1));
    return g;
  }, [seed.beltCount, seed.beltInner, seed.beltOuter]);

  useFrame((state, dt) => {
    if (!root.current || !star.current) return;
    root.current.position.z += dt * seed.speed;
    star.current.rotation.y += dt * seed.starSpin;

    if (!whooshed.current && root.current.position.z > 0.5) {
      whooshed.current = true;
      playFlybyPass("star");
    }

    const t0 = state.clock.elapsedTime;
    seed.planets.forEach((p, i) => {
      const carrier = carriers.current[i];
      const spinner = spinners.current[i];
      if (!carrier || !spinner) return;
      // 开普勒 + 近区表面 g 加权（致密矮星内轨更快）
      const nearBoost = 1 + phys.surfaceG * 0.2 * Math.exp(-p.a * 0.35);
      const n = (seed.orbitK * nearBoost) / Math.pow(p.a, 1.5);
      const theta = t0 * n + p.phase;
      const r = (p.a * (1 - p.e * p.e)) / (1 + p.e * Math.cos(theta));
      carrier.position.set(
        Math.cos(theta) * r,
        Math.sin(theta) * r * Math.sin(p.incline),
        Math.sin(theta) * r * Math.cos(p.incline),
      );
      spinner.rotation.y += dt * p.spin;

      p.moons.forEach((m, j) => {
        const moon = moonMeshes.current[i]?.[j];
        if (!moon) return;
        if (!moonPhases.current[i]) moonPhases.current[i] = [];
        moonPhases.current[i][j] = (moonPhases.current[i][j] ?? m.phase) + dt * m.speed;
        const mt = moonPhases.current[i][j];
        moon.position.set(Math.cos(mt) * m.a, Math.sin(mt) * m.a * 0.18, Math.sin(mt) * m.a);
        moon.rotation.y = mt + Math.PI;
      });
    });

    // 陨石带：同一引力阱内开普勒扫掠
    if (beltRef.current) {
      const posAttr = beltRef.current.geometry.getAttribute("position") as THREE.BufferAttribute;
      const phaseAttr = beltRef.current.geometry.getAttribute("phase") as THREE.BufferAttribute;
      const radAttr = beltRef.current.geometry.getAttribute("rad") as THREE.BufferAttribute;
      const midA = 0.5 * (seed.beltInner + seed.beltOuter);
      const nBelt = (seed.orbitK * 0.85) / Math.pow(midA, 1.5);
      for (let i = 0; i < phaseAttr.count; i++) {
        const ph = (phaseAttr.array as Float32Array)[i] + dt * nBelt * (0.9 + (i % 5) * 0.03);
        (phaseAttr.array as Float32Array)[i] = ph;
        const rr = (radAttr.array as Float32Array)[i];
        posAttr.setXYZ(i, Math.cos(ph) * rr, Math.sin(ph * 2.1) * 0.08, Math.sin(ph) * rr);
      }
      phaseAttr.needsUpdate = true;
      posAttr.needsUpdate = true;
    }

    if (root.current.position.z > 12) {
      root.current.position.set(...placeStarFar(delay + Math.random()));
      whooshed.current = false;
    }
  });

  const lightIntensity = 1.4 + phys.mass * 1.2;

  return (
    <group ref={root} position={pos} scale={seed.scale} rotation={[seed.systemTilt * 0.5, 0, seed.systemTilt]}>
      <sprite scale={[5 + phys.radius * 4, 5 + phys.radius * 4, 1]}>
        <spriteMaterial map={starGlow} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
      </sprite>
      <mesh ref={star}>
        <sphereGeometry args={[phys.radius, 24, 24]} />
        <meshBasicMaterial map={starSurf} color={phys.color} />
      </mesh>
      <pointLight color={phys.color} intensity={lightIntensity} distance={10 + phys.mass * 8} />

      {/* 小行星带：只有实体碎屑，不画轨道示意环 */}
      <points ref={beltRef} geometry={beltGeom}>
        <pointsMaterial color="#a89880" size={0.045} sizeAttenuation transparent opacity={0.75} depthWrite={false} />
      </points>

      {seed.planets.map((p, i) => (
        <group
          key={`p-${i}`}
          ref={(el) => {
            carriers.current[i] = el;
          }}
        >
          <group rotation={[p.tilt, 0.15, 0]}>
            <mesh
              ref={(el) => {
                spinners.current[i] = el;
              }}
              scale={p.kind === "gas" ? [1.15, 0.78, 1.12] : [1, 1, 1]}
            >
              <sphereGeometry args={[p.r, p.kind === "gas" ? 28 : 14, p.kind === "gas" ? 28 : 14]} />
              <meshStandardMaterial
                map={textures[p.kind]}
                roughness={p.kind === "gas" ? 0.62 : 0.9}
                metalness={p.kind === "ice" ? 0.1 : 0.03}
              />
            </mesh>
            {p.kind === "gas" && (
              <mesh rotation={[Math.PI / 2.05, 0, 0]}>
                <torusGeometry args={[p.r * 1.7, 0.028, 8, 48]} />
                <meshStandardMaterial color="#d2b48c" transparent opacity={0.55} roughness={0.85} />
              </mesh>
            )}
          </group>
          {p.moons.map((m, j) => (
            <mesh
              key={`moon-${i}-${j}`}
              ref={(el) => {
                if (!moonMeshes.current[i]) moonMeshes.current[i] = [];
                moonMeshes.current[i][j] = el;
              }}
            >
              <sphereGeometry args={[m.r, 10, 10]} />
              <meshStandardMaterial map={textures.moon} roughness={1} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}

/** 独立掠过的行星（已弃用：有行星必随恒星系；仅保留导出以免实验引用炸掉） */
function _PlanetBody({
  kind,
  delay = 0,
  withMoon = false,
}: {
  kind: "rocky" | "ice" | "gas";
  delay?: number;
  withMoon?: boolean;
}) {
  const root = useRef<THREE.Group>(null);
  const planet = useRef<THREE.Mesh>(null);
  const moon = useRef<THREE.Mesh>(null);
  const ring = useRef<THREE.Mesh>(null);
  const whooshed = useRef(false);
  const moonPhase = useRef(Math.random() * Math.PI * 2);
  const seed = useMemo(() => {
    // 气巨星因自转常呈扁椭；岩/冰更近球
    const oblong = kind === "gas" || Math.random() > 0.55;
    return {
      speed: 4.2 + Math.random() * 5.5,
      // 自转：气巨星更快（木星式），岩质中等
      spin: kind === "gas" ? 1.8 + Math.random() * 1.4 : 0.7 + Math.random() * 1.1,
      moonSpeed: 1.35 + Math.random() * 1.6,
      moonA: 2.05 + Math.random() * 0.55,
      // 轴倾：让赤道带扫过视线，自转更明显
      axialTilt: 0.25 + Math.random() * 0.55,
      orbitIncline: (Math.random() - 0.5) * 0.45,
      scale: kind === "gas" ? 0.55 + Math.random() * 0.55 : 0.22 + Math.random() * 0.36,
      vx: (Math.random() - 0.5) * 0.28,
      sx: oblong ? 1.12 + Math.random() * 0.35 : 1,
      sy: oblong ? 0.72 + Math.random() * 0.2 : 1,
      sz: oblong ? 1.08 + Math.random() * 0.2 : 1,
      pos: [
        (Math.random() - 0.5) * 16,
        (Math.random() - 0.5) * 8,
        -28 - delay * 6 - Math.random() * 35,
      ] as [number, number, number],
    };
  }, [kind, delay]);
  const tex = useMemo(() => {
    if (kind === "ice") return makePlanetTex("#7a9bb8", "#d8f0ff");
    if (kind === "gas") return makePlanetTex("#c49a4a", "#6b3a18", true);
    return makePlanetTex("#6a6058", "#3a322c");
  }, [kind]);
  const moonTex = useMemo(() => makePlanetTex("#9aa3b0", "#5a6068"), []);

  useFrame((_, dt) => {
    if (!root.current || !planet.current) return;
    root.current.position.z += dt * seed.speed;
    root.current.position.x += dt * seed.vx;
    // 绕自转轴旋转（轴倾在父 group 上）
    planet.current.rotation.y += dt * seed.spin;
    if (ring.current) ring.current.rotation.z += dt * seed.spin * 0.15;
    if (!whooshed.current && root.current.position.z > 0.5) {
      whooshed.current = true;
      playFlybyPass("planet");
    }
    if (moon.current) {
      moonPhase.current += dt * seed.moonSpeed;
      const t = moonPhase.current;
      const a = seed.moonA;
      // 倾斜轨道面：公转扫出可见弧线
      moon.current.position.set(
        Math.cos(t) * a,
        Math.sin(t) * a * Math.sin(seed.orbitIncline),
        Math.sin(t) * a * Math.cos(seed.orbitIncline),
      );
      // 潮汐锁定：同一面朝向母星
      moon.current.rotation.y = t + Math.PI;
    }
    if (root.current.position.z > 12) {
      resetFar(root.current);
      whooshed.current = false;
    }
  });

  return (
    <group ref={root} position={seed.pos} scale={seed.scale}>
      <group rotation={[seed.axialTilt, 0.2, 0]}>
        <mesh ref={planet} scale={[seed.sx, seed.sy, seed.sz]}>
          <sphereGeometry args={[1, kind === "gas" ? 32 : 20, kind === "gas" ? 32 : 20]} />
          <meshStandardMaterial
            map={tex}
            roughness={kind === "gas" ? 0.65 : 0.92}
            metalness={kind === "ice" ? 0.12 : 0.04}
          />
        </mesh>
        {kind === "gas" && (
          <mesh ref={ring} rotation={[Math.PI / 2.05, 0, 0]} scale={[seed.sx, 1, seed.sz]}>
            <torusGeometry args={[1.65, 0.05, 8, 64]} />
            <meshStandardMaterial color="#d2b48c" transparent opacity={0.6} roughness={0.85} />
          </mesh>
        )}
      </group>
      {withMoon && (
        <mesh ref={moon} scale={[0.95, 0.88, 1]}>
          <sphereGeometry args={[0.24, 14, 14]} />
          <meshStandardMaterial map={moonTex} roughness={1} />
        </mesh>
      )}
    </group>
  );
}

function MeteorBody({ delay = 0 }: { delay?: number }) {
  const g = useRef<THREE.Group>(null);
  const rock = useRef<THREE.Mesh>(null);
  const pos = useMemo(() => placeNearby(22, 10, -20 - delay * 2.2, 40), [delay]);
  const whooshed = useRef(false);
  const seed = useMemo(
    () => ({
      speed: 14 + Math.random() * 16,
      spin: 2 + Math.random() * 4,
      scale: 0.05 + Math.random() * 0.16,
      vx: (Math.random() - 0.5) * 1.2,
      vy: (Math.random() - 0.5) * 0.8,
      sx: 0.7 + Math.random() * 0.9,
      sy: 0.5 + Math.random() * 0.8,
      sz: 0.8 + Math.random() * 0.7,
    }),
    [],
  );
  useFrame((_, dt) => {
    if (!g.current || !rock.current) return;
    g.current.position.z += dt * seed.speed;
    g.current.position.x += dt * seed.vx;
    g.current.position.y += dt * seed.vy;
    rock.current.rotation.x += dt * seed.spin;
    rock.current.rotation.y += dt * seed.spin * 1.3;
    rock.current.rotation.z += dt * seed.spin * 0.7;
    if (!whooshed.current && g.current.position.z > 0.8) {
      whooshed.current = true;
      playMeteorWhoosh();
    }
    if (g.current.position.z > 14) {
      resetFar(g.current, 24);
      whooshed.current = false;
    }
  });
  return (
    <group ref={g} position={pos} scale={seed.scale}>
      <mesh ref={rock} scale={[seed.sx, seed.sy, seed.sz]}>
        <dodecahedronGeometry args={[1, 0]} />
        <meshStandardMaterial color="#5a534c" roughness={1} flatShading />
      </mesh>
      <mesh position={[0, 0, -2.2]} scale={[0.35, 0.35, 2.8]}>
        <coneGeometry args={[0.5, 1, 6]} />
        <meshBasicMaterial color="#ffaa66" transparent opacity={0.35} blending={THREE.AdditiveBlending} />
      </mesh>
    </group>
  );
}

function BlackHole({ delay = 0 }: { delay?: number }) {
  const g = useRef<THREE.Group>(null);
  const disk = useRef<THREE.Mesh>(null);
  const seed = useMemo(
    () => ({
      // 极慢、偏远：一生航程里几乎只擦肩一次
      speed: 1.1 + Math.random() * 0.9,
      spin: 1.2 + Math.random() * 1.5,
      scale: 0.28 + Math.random() * 0.22,
      pos: [8 + Math.random() * 6, -2 + Math.random() * 4, -95 - delay * 30] as [number, number, number],
    }),
    [delay],
  );
  const glow = useMemo(
    () =>
      makeGlowTex([
        [0, "rgba(0,0,0,1)"],
        [0.2, "rgba(20,10,30,0.9)"],
        [0.45, "rgba(255,140,60,0.45)"],
        [0.7, "rgba(120,60,255,0.15)"],
        [1, "rgba(0,0,0,0)"],
      ]),
    [],
  );
  useFrame((_, dt) => {
    if (!g.current || !disk.current) return;
    g.current.position.z += dt * seed.speed;
    disk.current.rotation.z += dt * seed.spin;
    // 飞过后丢到极远处，长时间不再出现
    if (g.current.position.z > 8) {
      g.current.position.set((Math.random() - 0.5) * 20, (Math.random() - 0.5) * 10, -180 - Math.random() * 80);
    }
  });
  return (
    <group ref={g} position={seed.pos} scale={seed.scale}>
      <sprite scale={[8, 8, 1]}>
        <spriteMaterial map={glow} transparent depthWrite={false} blending={THREE.AdditiveBlending} opacity={0.85} />
      </sprite>
      <mesh>
        <sphereGeometry args={[0.55, 24, 24]} />
        <meshBasicMaterial color="#000000" />
      </mesh>
      <mesh ref={disk} rotation={[Math.PI / 2.2, 0.2, 0]} scale={[1.4, 1, 0.55]}>
        <torusGeometry args={[1.35, 0.18, 10, 48]} />
        <meshBasicMaterial color="#ff9944" transparent opacity={0.75} blending={THREE.AdditiveBlending} />
      </mesh>
    </group>
  );
}

/** 棕矮星：失败恒星，质量介于巨星与恒星之间，可带紧凑伴星 */
function BrownDwarfBody({ delay = 0 }: { delay?: number }) {
  const root = useRef<THREE.Group>(null);
  const core = useRef<THREE.Mesh>(null);
  const moon = useRef<THREE.Mesh>(null);
  const phase = useRef(Math.random() * Math.PI * 2);
  const pos = useMemo(() => placeStarFar(delay + 0.7), [delay]);
  const seed = useMemo(
    () => ({
      speed: 2.6 + Math.random() * 1.6,
      spin: 0.9 + Math.random() * 0.6,
      // 密度高 → 表面 g 强 → 伴星贴得很近、转得快
      mass: 0.05,
      density: 3.5,
      moonA: 0.95,
      moonSpeed: 2.8,
      scale: 0.55 + Math.random() * 0.2,
    }),
    [],
  );
  const glow = useMemo(
    () =>
      makeGlowTex(
        [
          [0, "rgba(255,180,120,0.9)"],
          [0.25, "rgba(180,60,40,0.45)"],
          [0.6, "rgba(80,20,30,0.12)"],
          [1, "rgba(0,0,0,0)"],
        ],
        96,
      ),
    [],
  );
  const tex = useMemo(() => makePlanetTex("#6a3020", "#c06030", true), []);
  useFrame((_, dt) => {
    if (!root.current || !core.current) return;
    root.current.position.z += dt * seed.speed;
    core.current.rotation.y += dt * seed.spin;
    if (moon.current) {
      phase.current += dt * seed.moonSpeed * Math.sqrt(seed.density);
      const t = phase.current;
      moon.current.position.set(Math.cos(t) * seed.moonA, Math.sin(t) * 0.12, Math.sin(t) * seed.moonA);
      moon.current.rotation.y = t + Math.PI;
    }
    if (root.current.position.z > 12) root.current.position.set(...placeStarFar(delay));
  });
  return (
    <group ref={root} position={pos} scale={seed.scale}>
      <sprite scale={[3.2, 3.2, 1]}>
        <spriteMaterial map={glow} transparent depthWrite={false} blending={THREE.AdditiveBlending} opacity={0.7} />
      </sprite>
      <mesh ref={core}>
        <sphereGeometry args={[0.42, 18, 18]} />
        <meshStandardMaterial map={tex} emissive="#401008" emissiveIntensity={0.35} roughness={0.8} />
      </mesh>
      <mesh ref={moon}>
        <sphereGeometry args={[0.1, 10, 10]} />
        <meshStandardMaterial color="#8a7060" roughness={1} />
      </mesh>
      <pointLight color="#ff8040" intensity={0.9} distance={6} />
    </group>
  );
}

/** 白矮星：极端致密，引力阱深，残骸盘贴身高速公转 */
function WhiteDwarfBody({ delay = 0 }: { delay?: number }) {
  const root = useRef<THREE.Group>(null);
  const core = useRef<THREE.Mesh>(null);
  const debris = useRef<THREE.Points>(null);
  const pos = useMemo(() => placeStarFar(delay + 1.5), [delay]);
  const seed = useMemo(
    () => ({
      speed: 2.0 + Math.random() * 1.2,
      spin: 1.8 + Math.random() * 1.2,
      mass: 0.6,
      scale: 0.4 + Math.random() * 0.15,
      diskA: 0.85,
    }),
    [],
  );
  const glow = useMemo(
    () =>
      makeGlowTex(
        [
          [0, "rgba(220,235,255,1)"],
          [0.2, "rgba(160,190,255,0.55)"],
          [0.55, "rgba(80,120,255,0.15)"],
          [1, "rgba(0,0,0,0)"],
        ],
        96,
      ),
    [],
  );
  const geom = useMemo(() => {
    const n = 48;
    const arr = new Float32Array(n * 3);
    const ph = new Float32Array(n);
    const rad = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      ph[i] = Math.random() * Math.PI * 2;
      rad[i] = 0.55 + Math.random() * 0.55;
      arr[i * 3] = Math.cos(ph[i]) * rad[i];
      arr[i * 3 + 1] = (Math.random() - 0.5) * 0.06;
      arr[i * 3 + 2] = Math.sin(ph[i]) * rad[i];
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(arr, 3));
    g.setAttribute("phase", new THREE.BufferAttribute(ph, 1));
    g.setAttribute("rad", new THREE.BufferAttribute(rad, 1));
    return g;
  }, []);
  useFrame((_, dt) => {
    if (!root.current || !core.current) return;
    root.current.position.z += dt * seed.speed;
    core.current.rotation.y += dt * seed.spin;
    if (debris.current) {
      const posAttr = debris.current.geometry.getAttribute("position") as THREE.BufferAttribute;
      const phaseAttr = debris.current.geometry.getAttribute("phase") as THREE.BufferAttribute;
      const radAttr = debris.current.geometry.getAttribute("rad") as THREE.BufferAttribute;
      const n = 4.5 * Math.sqrt(seed.mass);
      for (let i = 0; i < phaseAttr.count; i++) {
        const ph =
          (phaseAttr.array as Float32Array)[i] +
          (dt * n) / Math.pow((radAttr.array as Float32Array)[i], 1.5);
        (phaseAttr.array as Float32Array)[i] = ph;
        const rr = (radAttr.array as Float32Array)[i];
        posAttr.setXYZ(i, Math.cos(ph) * rr, Math.sin(ph * 3) * 0.04, Math.sin(ph) * rr);
      }
      phaseAttr.needsUpdate = true;
      posAttr.needsUpdate = true;
    }
    if (root.current.position.z > 12) root.current.position.set(...placeStarFar(delay));
  });
  return (
    <group ref={root} position={pos} scale={seed.scale}>
      <sprite scale={[2.4, 2.4, 1]}>
        <spriteMaterial map={glow} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
      </sprite>
      <mesh ref={core}>
        <sphereGeometry args={[0.12, 16, 16]} />
        <meshBasicMaterial color="#e8f0ff" />
      </mesh>
      <points ref={debris} geometry={geom}>
        <pointsMaterial color="#c0d0e8" size={0.035} sizeAttenuation transparent opacity={0.85} depthWrite={false} />
      </points>
      <mesh rotation={[Math.PI / 2.1, 0, 0]}>
        <torusGeometry args={[seed.diskA, 0.08, 6, 48]} />
        <meshBasicMaterial color="#a0b8d8" transparent opacity={0.2} depthWrite={false} />
      </mesh>
      <pointLight color="#c0d8ff" intensity={2.2} distance={7} />
    </group>
  );
}

/**
 * 密近双星 + 一颗行星：三体纠缠（极稀；默认舰队不刷）
 */
function _BinaryThreeBody({ delay = 0 }: { delay?: number }) {
  const root = useRef<THREE.Group>(null);
  const starA = useRef<THREE.Mesh>(null);
  const starB = useRef<THREE.Mesh>(null);
  const planet = useRef<THREE.Mesh>(null);
  const pos = useMemo(() => placeStarFar(delay + 2.2), [delay]);
  const dyn = useRef({
    binaryPhase: Math.random() * Math.PI * 2,
    px: 2.8,
    py: 0.2,
    pz: 0,
    vx: 0,
    vy: 0.15,
    vz: 1.1,
  });
  const trailBuf = useRef<number[]>([]);
  const seed = useMemo(
    () => ({
      speed: 1.8 + Math.random() * 1.0,
      sep: 1.35 + Math.random() * 0.4,
      mA: 0.9,
      mB: 0.75,
      scale: 0.55 + Math.random() * 0.2,
      G: 2.8,
    }),
    [],
  );
  const glowA = useMemo(
    () =>
      makeGlowTex(
        [
          [0, "rgba(255,240,200,1)"],
          [0.4, "rgba(255,160,60,0.25)"],
          [1, "rgba(0,0,0,0)"],
        ],
        64,
      ),
    [],
  );
  const glowB = useMemo(
    () =>
      makeGlowTex(
        [
          [0, "rgba(255,180,160,1)"],
          [0.4, "rgba(255,80,40,0.25)"],
          [1, "rgba(0,0,0,0)"],
        ],
        64,
      ),
    [],
  );
  const ptex = useMemo(() => makePlanetTex("#6a7060", "#c0b090"), []);
  const trailLine = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(120 * 3), 3));
    const mat = new THREE.LineBasicMaterial({
      color: "#88c0ff",
      transparent: true,
      opacity: 0.45,
      depthWrite: false,
    });
    return new THREE.Line(g, mat);
  }, []);

  useFrame((_, dt) => {
    if (!root.current || !starA.current || !starB.current || !planet.current) return;
    root.current.position.z += dt * seed.speed;
    const s = dyn.current;
    const step = Math.min(dt, 0.05);
    s.binaryPhase += step * 1.35 * Math.sqrt((seed.mA + seed.mB) / seed.sep);
    const qA = seed.mB / (seed.mA + seed.mB);
    const qB = seed.mA / (seed.mA + seed.mB);
    const ax = Math.cos(s.binaryPhase) * seed.sep * qA;
    const az = Math.sin(s.binaryPhase) * seed.sep * qA;
    const bx = -Math.cos(s.binaryPhase) * seed.sep * qB;
    const bz = -Math.sin(s.binaryPhase) * seed.sep * qB;
    starA.current.position.set(ax, 0, az);
    starB.current.position.set(bx, 0, bz);
    starA.current.rotation.y += step * 0.8;
    starB.current.rotation.y += step * 1.1;

    const soft = 0.2;
    const pull = (mx: number, mz: number, mass: number) => {
      const dx = mx - s.px;
      const dy = 0 - s.py;
      const dz = mz - s.pz;
      const d2 = dx * dx + dy * dy + dz * dz + soft;
      const inv = mass / (d2 * Math.sqrt(d2));
      return [dx * inv, dy * inv, dz * inv] as const;
    };
    const [ax1, ay1, az1] = pull(ax, az, seed.mA);
    const [ax2, ay2, az2] = pull(bx, bz, seed.mB);
    s.vx += seed.G * (ax1 + ax2) * step;
    s.vy += seed.G * (ay1 + ay2) * step;
    s.vz += seed.G * (az1 + az2) * step;
    s.vx *= 0.999;
    s.vy *= 0.999;
    s.vz *= 0.999;
    s.px += s.vx * step;
    s.py += s.vy * step;
    s.pz += s.vz * step;
    const dist = Math.hypot(s.px, s.py, s.pz);
    if (dist > 6.5 || dist < 0.35) {
      s.px = 2.6 + Math.random() * 0.4;
      s.py = (Math.random() - 0.5) * 0.3;
      s.pz = 0;
      s.vx = 0;
      s.vy = 0.1;
      s.vz = 0.95 + Math.random() * 0.2;
      trailBuf.current = [];
    }
    planet.current.position.set(s.px, s.py, s.pz);
    planet.current.rotation.y += step * 1.4;

    trailBuf.current.push(s.px, s.py, s.pz);
    if (trailBuf.current.length > 360) trailBuf.current.splice(0, trailBuf.current.length - 360);
    const attr = trailLine.geometry.getAttribute("position") as THREE.BufferAttribute;
    const src = trailBuf.current;
    const n = Math.min(120, Math.floor(src.length / 3));
    for (let i = 0; i < 120; i++) {
      const j = Math.max(0, n - 120 + i);
      if (j * 3 + 2 < src.length) attr.setXYZ(i, src[j * 3], src[j * 3 + 1], src[j * 3 + 2]);
    }
    attr.needsUpdate = true;
    trailLine.geometry.setDrawRange(0, n);

    if (root.current.position.z > 12) root.current.position.set(...placeStarFar(delay));
  });

  return (
    <group ref={root} position={pos} scale={seed.scale}>
      <mesh ref={starA}>
        <sphereGeometry args={[0.32, 16, 16]} />
        <meshBasicMaterial color="#ffe6a0" />
      </mesh>
      <mesh ref={starB}>
        <sphereGeometry args={[0.26, 16, 16]} />
        <meshBasicMaterial color="#ff8866" />
      </mesh>
      <sprite scale={[3.5, 3.5, 1]}>
        <spriteMaterial map={glowA} transparent depthWrite={false} blending={THREE.AdditiveBlending} opacity={0.4} />
      </sprite>
      <sprite scale={[2.4, 2.4, 1]}>
        <spriteMaterial map={glowB} transparent depthWrite={false} blending={THREE.AdditiveBlending} opacity={0.45} />
      </sprite>
      <mesh ref={planet}>
        <sphereGeometry args={[0.14, 12, 12]} />
        <meshStandardMaterial map={ptex} roughness={0.85} />
      </mesh>
      <primitive object={trailLine} />
      <pointLight color="#ffcc88" intensity={1.6} distance={10} />
    </group>
  );
}

/** 流浪矮行星：无主恒星，缓慢自转（偶见） */
function RogueDwarfPlanet({ delay = 0 }: { delay?: number }) {
  const root = useRef<THREE.Group>(null);
  const body = useRef<THREE.Mesh>(null);
  const seed = useMemo(
    () => ({
      speed: 3.2 + Math.random() * 2.5,
      spin: 0.35 + Math.random() * 0.4,
      scale: 0.18 + Math.random() * 0.12,
      vx: (Math.random() - 0.5) * 0.2,
      pos: [
        (Math.random() - 0.5) * 16,
        (Math.random() - 0.5) * 8,
        -40 - delay * 10,
      ] as [number, number, number],
    }),
    [delay],
  );
  const tex = useMemo(() => makePlanetTex("#7a6a58", "#3a3228"), []);
  useFrame((_, dt) => {
    if (!root.current || !body.current) return;
    root.current.position.z += dt * seed.speed;
    root.current.position.x += dt * seed.vx;
    body.current.rotation.y += dt * seed.spin;
    if (root.current.position.z > 12) resetFar(root.current, 18);
  });
  return (
    <group ref={root} position={seed.pos} scale={seed.scale}>
      <mesh ref={body} rotation={[0.4, 0, 0.1]}>
        <sphereGeometry args={[1, 14, 14]} />
        <meshStandardMaterial map={tex} roughness={0.95} />
      </mesh>
    </group>
  );
}

/**
 * 远处背景星云：发射/反射/行星状/暗星云；横向缓缓移出画面
 */
function _DistantDriftingNebula({
  delay = 0,
  kind = "emission",
}: {
  delay?: number;
  kind?: "emission" | "reflection" | "planetary" | "dark";
}) {
  const ref = useRef<THREE.Sprite>(null);
  const tex = useMemo(() => makeNebulaTex(kind), [kind]);
  const seed = useMemo(() => {
    const dir = Math.random() > 0.5 ? 1 : -1;
    return {
      vx: dir * (0.22 + Math.random() * 0.45),
      vy: (Math.random() - 0.5) * 0.1,
      vz: 0.03 + Math.random() * 0.08,
      sx: kind === "planetary" ? 6 + Math.random() * 6 : 12 + Math.random() * 16,
      sy: kind === "planetary" ? 6 + Math.random() * 6 : 7 + Math.random() * 11,
      rot: (Math.random() - 0.5) * 0.5,
      spin: (Math.random() - 0.5) * 0.03,
      opacity: kind === "dark" ? 0.55 + Math.random() * 0.25 : 0.42 + Math.random() * 0.32,
      pos: [
        (Math.random() > 0.5 ? 1 : -1) * (18 + Math.random() * 40),
        (Math.random() - 0.5) * 18,
        -78 - delay * 5 - Math.random() * 30,
      ] as [number, number, number],
    };
  }, [kind, delay]);

  const respawn = () => {
    if (!ref.current) return;
    const fromLeft = seed.vx > 0;
    ref.current.position.set(
      fromLeft ? -58 - Math.random() * 18 : 58 + Math.random() * 18,
      (Math.random() - 0.5) * 20,
      -72 - Math.random() * 40 - delay * 4,
    );
  };

  useFrame((_, dt) => {
    if (!ref.current) return;
    ref.current.position.x += dt * seed.vx;
    ref.current.position.y += dt * seed.vy;
    ref.current.position.z += dt * seed.vz;
    ref.current.material.rotation += dt * seed.spin;
    if (Math.abs(ref.current.position.x) > 75) respawn();
  });

  return (
    <sprite
      ref={ref}
      position={seed.pos}
      scale={[seed.sx, seed.sy, 1]}
      rotation={[0, 0, seed.rot]}
    >
      <spriteMaterial
        map={tex}
        transparent
        depthWrite={false}
        blending={kind === "dark" ? THREE.NormalBlending : THREE.AdditiveBlending}
        opacity={seed.opacity}
      />
    </sprite>
  );
}

/** 彗星：近场偶见，长尾巴，少于陨石 */
function CometBody({ delay = 0 }: { delay?: number }) {
  const g = useRef<THREE.Group>(null);
  const seed = useMemo(
    () => ({
      speed: 9 + Math.random() * 8,
      scale: 0.35 + Math.random() * 0.35,
      vx: (Math.random() - 0.5) * 0.6,
      vy: (Math.random() - 0.5) * 0.4,
      pos: [
        (Math.random() - 0.5) * 18,
        (Math.random() - 0.5) * 9,
        -35 - delay * 8 - Math.random() * 30,
      ] as [number, number, number],
    }),
    [delay],
  );
  const glow = useMemo(
    () =>
      makeGlowTex([
        [0, "rgba(220,240,255,0.9)"],
        [0.25, "rgba(160,210,255,0.4)"],
        [1, "rgba(0,0,0,0)"],
      ], 128),
    [],
  );
  useFrame((_, dt) => {
    if (!g.current) return;
    g.current.position.z += dt * seed.speed;
    g.current.position.x += dt * seed.vx;
    g.current.position.y += dt * seed.vy;
    if (g.current.position.z > 14) resetFar(g.current, 20);
  });
  return (
    <group ref={g} position={seed.pos} scale={seed.scale}>
      <sprite scale={[2.2, 2.2, 1]}>
        <spriteMaterial map={glow} transparent depthWrite={false} blending={THREE.AdditiveBlending} opacity={0.8} />
      </sprite>
      <mesh>
        <sphereGeometry args={[0.22, 12, 12]} />
        <meshStandardMaterial color="#d8e8ff" roughness={0.7} emissive="#88aacc" emissiveIntensity={0.35} />
      </mesh>
      <mesh position={[0, 0, -3.5]} rotation={[Math.PI / 2, 0, 0]} scale={[0.35, 5.5, 0.35]}>
        <coneGeometry args={[0.5, 1, 8]} />
        <meshBasicMaterial color="#a8d0ff" transparent opacity={0.28} blending={THREE.AdditiveBlending} />
      </mesh>
      <mesh position={[0.4, 0.15, -2.8]} rotation={[Math.PI / 2, 0.1, 0.2]} scale={[0.2, 4.2, 0.2]}>
        <coneGeometry args={[0.5, 1, 6]} />
        <meshBasicMaterial color="#ffd0a0" transparent opacity={0.18} blending={THREE.AdditiveBlending} />
      </mesh>
    </group>
  );
}

/** 脉冲星/中子星：极稀，闪烁 */
function PulsarBody({ delay = 0 }: { delay?: number }) {
  const g = useRef<THREE.Group>(null);
  const beam = useRef<THREE.Group>(null);
  const seed = useMemo(
    () => ({
      speed: 4 + Math.random() * 3,
      scale: 0.25 + Math.random() * 0.15,
      pos: [
        (Math.random() - 0.5) * 12,
        (Math.random() - 0.5) * 6,
        -50 - delay * 20,
      ] as [number, number, number],
    }),
    [delay],
  );
  useFrame((state, dt) => {
    if (!g.current || !beam.current) return;
    g.current.position.z += dt * seed.speed;
    beam.current.rotation.z += dt * 8;
    const flash = 0.35 + 0.65 * Math.pow(0.5 + 0.5 * Math.sin(state.clock.elapsedTime * 14), 8);
    g.current.scale.setScalar(seed.scale * (0.85 + flash * 0.25));
    if (g.current.position.z > 10) resetFar(g.current, 16);
  });
  return (
    <group ref={g} position={seed.pos} scale={seed.scale}>
      <mesh>
        <sphereGeometry args={[0.18, 12, 12]} />
        <meshBasicMaterial color="#c8e0ff" />
      </mesh>
      <group ref={beam}>
        <mesh scale={[0.08, 3.2, 0.08]}>
          <boxGeometry />
          <meshBasicMaterial color="#88ccff" transparent opacity={0.55} blending={THREE.AdditiveBlending} />
        </mesh>
      </group>
      <pointLight color="#a0d0ff" intensity={1.6} distance={8} />
    </group>
  );
}

function CelestialFleet() {
  // 稀有度：陨石 ≫ 彗星 ≫ 恒星系（行星只作为恒星伴星）≫ 流浪矮行星 ≫ 致密残骸
  // 禁止「无主行星」掠过：有行星必有宿主恒星
  return (
    <>
      {Array.from({ length: 96 }, (_, i) => (
        <MeteorBody key={`m${i}`} delay={i * 0.12} />
      ))}
      {Array.from({ length: 4 }, (_, i) => (
        <CometBody key={`c${i}`} delay={i * 2.8} />
      ))}
      {/* 可分辨恒星系：行星/卫星只出现在系内 */}
      <StarSystem delay={0} spectral="M" />
      <StarSystem delay={5.5} spectral="G" />
      {/* 极稀：无恒星的流浪矮行星（星际抛射体，不是普通行星） */}
      <RogueDwarfPlanet delay={4} />
      <BrownDwarfBody delay={4.2} />
      <WhiteDwarfBody delay={8} />
      <PulsarBody delay={6} />
      <BlackHole delay={0} />
    </>
  );
}

function DriftCamera() {
  const lastDodge = useRef(0);
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    state.camera.position.x = Math.sin(t * 0.055) * 0.38;
    state.camera.position.y = Math.cos(t * 0.04) * 0.2;
    state.camera.lookAt(3.2, 1.5, -54);
    if (t - lastDodge.current > 4.5 + Math.random() * 3) {
      lastDodge.current = t;
      playDodgeBlip();
    }
  });
  return null;
}

/** 超新星：远场不规则光斑（非正圆），闪光 → 膨胀 → 余晖 */
function SupernovaBurst({ slot = 0 }: { slot?: number }) {
  const root = useRef<THREE.Group>(null);
  const shell = useRef<THREE.Mesh>(null);
  const glow = useRef<THREE.Sprite>(null);
  const glow2 = useRef<THREE.Sprite>(null);
  const st = useRef({
    mode: "wait" as "wait" | "flash" | "expand" | "fade",
    age: 0,
    wait: 18 + slot * 28 + Math.random() * 40,
    peakX: 0,
    placed: false,
    sx: 1.35 + Math.random() * 0.9,
    sy: 0.55 + Math.random() * 0.45,
    rot: (Math.random() - 0.5) * 1.4,
    shellSx: 1.4 + Math.random() * 0.8,
    shellSy: 0.5 + Math.random() * 0.4,
    shellSz: 0.7 + Math.random() * 0.5,
  });
  const tex = useMemo(() => makeSupernovaTex(192), []);
  const tex2 = useMemo(() => makeSupernovaTex(160), []);

  const setGlowScale = (base: number) => {
    const s = st.current;
    if (glow.current) {
      glow.current.scale.set(base * s.sx, base * s.sy, 1);
      glow.current.material.rotation = s.rot;
    }
    if (glow2.current) {
      glow2.current.scale.set(base * s.sy * 0.85, base * s.sx * 0.7, 1);
      glow2.current.material.rotation = s.rot + 0.9;
    }
  };

  const respawn = () => {
    if (!root.current) return;
    const side = Math.random() > 0.5 ? 1 : -1;
    root.current.position.set(
      side * (18 + Math.random() * 28),
      (Math.random() - 0.5) * 16,
      -150 - Math.random() * 90,
    );
    st.current.mode = "wait";
    st.current.age = 0;
    st.current.wait = 22 + Math.random() * 55;
    st.current.peakX = 0;
    st.current.sx = 1.35 + Math.random() * 0.9;
    st.current.sy = 0.55 + Math.random() * 0.45;
    st.current.rot = (Math.random() - 0.5) * 1.4;
    st.current.shellSx = 1.4 + Math.random() * 0.8;
    st.current.shellSy = 0.5 + Math.random() * 0.4;
    st.current.shellSz = 0.7 + Math.random() * 0.5;
    if (shell.current) shell.current.scale.set(0.01, 0.01, 0.01);
    setGlowScale(0.01);
    if (glow.current) (glow.current.material as THREE.SpriteMaterial).opacity = 0;
    if (glow2.current) (glow2.current.material as THREE.SpriteMaterial).opacity = 0;
  };

  useFrame((_, dt) => {
    if (!root.current) return;
    if (!st.current.placed) {
      st.current.placed = true;
      respawn();
    }

    const s = st.current;
    s.age += dt;
    const mat = glow.current?.material as THREE.SpriteMaterial | undefined;
    const mat2 = glow2.current?.material as THREE.SpriteMaterial | undefined;

    if (s.mode === "wait") {
      if (s.age >= s.wait) {
        s.mode = "flash";
        s.age = 0;
      }
      return;
    }

    if (s.mode === "flash") {
      const u = Math.min(1, s.age / 0.28);
      const peak = 3.8 + u * 4.8;
      s.peakX = peak;
      setGlowScale(peak);
      if (mat) mat.opacity = 0.4 + u * 0.45;
      if (mat2) mat2.opacity = 0.25 + u * 0.3;
      if (shell.current) {
        const t = 0.06 + u * 0.12;
        shell.current.scale.set(t * s.shellSx, t * s.shellSy, t * s.shellSz);
      }
      if (s.age > 0.28) {
        s.mode = "expand";
        s.age = 0;
      }
      return;
    }

    if (s.mode === "expand") {
      const u = Math.min(1, s.age / 3.4);
      const sc = 0.2 + u * 2.8;
      if (shell.current) {
        shell.current.scale.set(sc * s.shellSx, sc * s.shellSy, sc * s.shellSz);
        shell.current.rotation.z = s.rot + u * 0.35;
        (shell.current.material as THREE.MeshBasicMaterial).opacity = 0.32 * (1 - u * 0.75);
      }
      setGlowScale(s.peakX * (1.05 + u * 1.35));
      if (mat) mat.opacity = 0.55 * (1 - u * 0.55);
      if (mat2) mat2.opacity = 0.35 * (1 - u * 0.65);
      if (s.age > 3.4) {
        s.mode = "fade";
        s.age = 0;
      }
      return;
    }

    {
      const u = Math.min(1, s.age / 4.8);
      if (shell.current) {
        const sc = 3.0 + u * 2.0;
        shell.current.scale.set(sc * s.shellSx, sc * s.shellSy, sc * s.shellSz);
        (shell.current.material as THREE.MeshBasicMaterial).opacity = 0.07 * (1 - u);
      }
      setGlowScale(s.peakX * (2.0 + u * 1.5));
      if (mat) mat.opacity = 0.2 * (1 - u);
      if (mat2) mat2.opacity = 0.12 * (1 - u);
      if (s.age > 4.8) respawn();
    }
  });

  return (
    <group ref={root}>
      <sprite ref={glow} scale={[0.01, 0.01, 1]}>
        <spriteMaterial map={tex} transparent depthWrite={false} blending={THREE.AdditiveBlending} opacity={0} />
      </sprite>
      <sprite ref={glow2} scale={[0.01, 0.01, 1]} position={[0.4, -0.2, 0]}>
        <spriteMaterial map={tex2} transparent depthWrite={false} blending={THREE.AdditiveBlending} opacity={0} />
      </sprite>
      <mesh ref={shell} scale={[0.01, 0.01, 0.01]}>
        <sphereGeometry args={[1, 16, 12]} />
        <meshBasicMaterial
          color="#ffb070"
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          side={THREE.BackSide}
        />
      </mesh>
    </group>
  );
}

/** 缓慢：缓慢漂移的尘埃帘（当前 LivingSky 未启用，观感怪异） */
function _CosmicDustRibbons() {
  const group = useRef<THREE.Group>(null);
  const sheets = useMemo(
    () =>
      Array.from({ length: 5 }, (_, i) => ({
        kind: (["emission", "reflection", "dark", "emission", "planetary"] as const)[i],
        x: (Math.random() - 0.5) * 50,
        y: (Math.random() - 0.5) * 22,
        z: -48 - i * 12 - Math.random() * 20,
        sx: 14 + Math.random() * 18,
        sy: 6 + Math.random() * 10,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.08,
        spin: (Math.random() - 0.5) * 0.04,
        rot: (Math.random() - 0.5) * 0.8,
        opacity: 0.28 + Math.random() * 0.28,
      })),
    [],
  );
  const texes = useMemo(
    () => ({
      emission: makeNebulaTex("emission"),
      reflection: makeNebulaTex("reflection"),
      planetary: makeNebulaTex("planetary"),
      dark: makeNebulaTex("dark"),
    }),
    [],
  );
  const refs = useRef<(THREE.Sprite | null)[]>([]);

  useFrame((_, dt) => {
    sheets.forEach((sh, i) => {
      const sp = refs.current[i];
      if (!sp) return;
      sp.position.x += dt * sh.vx;
      sp.position.y += dt * sh.vy;
      sp.material.rotation += dt * sh.spin;
      if (Math.abs(sp.position.x) > 70) {
        sp.position.x = -Math.sign(sp.position.x) * 65;
        sp.position.y = (Math.random() - 0.5) * 20;
      }
    });
    if (group.current) group.current.rotation.z = Math.sin(performance.now() * 0.00003) * 0.04;
  });

  return (
    <group ref={group}>
      {sheets.map((sh, i) => (
        <sprite
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          position={[sh.x, sh.y, sh.z]}
          scale={[sh.sx, sh.sy, 1]}
          rotation={[0, 0, sh.rot]}
        >
          <spriteMaterial
            map={texes[sh.kind]}
            transparent
            depthWrite={false}
            blending={sh.kind === "dark" ? THREE.NormalBlending : THREE.AdditiveBlending}
            opacity={sh.opacity}
          />
        </sprite>
      ))}
    </group>
  );
}

/** 远场：仅偶发远处超新星（去掉线框感螺旋星系贴图） */
function LivingSky() {
  return <SupernovaBurst slot={0} />;
}

const FLYBY_CAMERA = { position: [0, 0, 5] as [number, number, number], fov: 58, near: 0.1, far: 280 };
const FLYBY_DPR: [number, number] = [1, 1.75];
const FLYBY_GL = { antialias: true, alpha: false, powerPreference: "high-performance" as const };

type Props = {
  className?: string;
};

function FlybyAmbience() {
  useEffect(() => {
    const id = window.setInterval(() => {
      if (Math.random() < 0.55) playNebulaBlip();
    }, 2800 + Math.random() * 2200);
    return () => window.clearInterval(id);
  }, []);
  return null;
}

/** 单例根渲染的场景本体：无 props，避免驾驶舱 setState 传入新 props */
export function SpaceFlybyScene() {
  useEffect(() => {
    const unlock = () => unlockCockpitAudio();
    window.addEventListener("pointerdown", unlock, { once: true });
    return () => window.removeEventListener("pointerdown", unlock);
  }, []);

  return (
    <>
      <FlybyAmbience />
      <Canvas
        camera={FLYBY_CAMERA}
        dpr={FLYBY_DPR}
        gl={FLYBY_GL}
        frameloop="always"
        resize={{ scroll: false, debounce: { resize: 0, scroll: 0 } }}
      >
        <color attach="background" args={["#010308"]} />
        <fog attach="fog" args={["#010308", 100, 260]} />
        <ambientLight intensity={0.22} />
        <directionalLight position={[6, 8, 5]} intensity={0.4} color="#cfe0ff" />
        <DriftCamera />
        <DistantMilkyWay />
        <StarField />
        <LivingSky />
        <TwinNebula />
        <CelestialFleet />
      </Canvas>
    </>
  );
}

/** @deprecated 驾驶舱请用 SpaceFlybyHost；保留具名导出以免旧引用炸掉 */
export const SpaceFlyby = memo(function SpaceFlyby({ className = "" }: Props) {
  return (
    <div className={`cp-space-flyby ${className}`} aria-hidden>
      <SpaceFlybyScene />
    </div>
  );
});

// Kept for scene experiments; exported so tsc noUnusedLocals stays clean.
export {
  _DistantGalaxies as DistantGalaxies,
  _DistantDriftingNebula as DistantDriftingNebula,
  _CosmicDustRibbons as CosmicDustRibbons,
  _BinaryThreeBody as BinaryThreeBody,
  _PlanetBody as PlanetBody,
};

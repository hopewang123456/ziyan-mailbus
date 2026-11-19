/** 楼外环境：草坪、干道、红绿灯、围栏、树木、行人、行驶车辆。仅整楼视图显示，聚焦楼层时隐藏。 */

import { useLayoutEffect, useRef } from "react";

type Axis = "x" | "y";
type TreeVariant = "round" | "tall" | "wide" | "pine";
type CarKind = "sedan" | "suv" | "van" | "truck";

interface TreeSpec {
  x: number;
  y: number;
  scale: number;
  variant: TreeVariant;
  /** 叶色分组，避免整片树林一个颜色 */
  tone: number;
}

interface CarSpec {
  axis: Axis;
  at: number;
  rev: boolean;
  /** 场景单位 / 秒，明显高于行人的步行速度。 */
  speed: number;
  start: number;
  tone: string;
  kind: CarKind;
}

interface WalkerSpec {
  axis: "x" | "y";
  at: number;
  rev: boolean;
  dur: number;
  delay: number;
  shirt: string;
  hair: string;
}

/** 围栏范围与立柱间距，南侧留出大门。 */
const FENCE = { x0: -150, y0: -150, x1: 1550, y1: 1050, step: 116, gateFrom: 545, gateTo: 855 };

/** 叶色：四种绿，配合树的形态随机分布。 */
const TREE_TONES = [
  { a: "#c2dfa8", b: "#7fae77", c: "#6b9a64" },
  { a: "#b2d49a", b: "#6f9f6b", c: "#5c8a5c" },
  { a: "#cde3b3", b: "#8cb87e", c: "#76a36c" },
  { a: "#a9cf9b", b: "#6b9566", c: "#547d52" },
];

/** 园区树木：四种形态交替，位置铺满整片草坪。 */
const TREES: TreeSpec[] = [
  { x: -260, y: -420, scale: 2.7, variant: "round", tone: 0 },
  { x: 120, y: -416, scale: 3.1, variant: "tall", tone: 2 },
  { x: 470, y: -424, scale: 2.5, variant: "wide", tone: 1 },
  { x: 830, y: -416, scale: 3.0, variant: "pine", tone: 3 },
  { x: 1180, y: -424, scale: 2.6, variant: "round", tone: 2 },
  { x: 1520, y: -416, scale: 3.2, variant: "tall", tone: 0 },
  { x: -420, y: 300, scale: 2.8, variant: "wide", tone: 3 },
  { x: -416, y: 760, scale: 3.0, variant: "round", tone: 1 },
  { x: 1786, y: 260, scale: 2.9, variant: "pine", tone: 0 },
  { x: 1792, y: 720, scale: 2.7, variant: "round", tone: 2 },
  { x: 236, y: 1290, scale: 3.0, variant: "tall", tone: 1 },
  { x: 968, y: 1284, scale: 2.6, variant: "wide", tone: 0 },
  { x: 1306, y: 1294, scale: 3.1, variant: "round", tone: 3 },
  { x: 1726, y: 1270, scale: 2.8, variant: "pine", tone: 2 },
  { x: -620, y: -520, scale: 3.4, variant: "tall", tone: 3 },
  { x: -260, y: -560, scale: 3.0, variant: "round", tone: 1 },
  { x: 320, y: -580, scale: 3.2, variant: "wide", tone: 2 },
  { x: 980, y: -600, scale: 3.1, variant: "pine", tone: 0 },
  { x: 1500, y: -560, scale: 3.3, variant: "round", tone: 3 },
  { x: 2100, y: -540, scale: 3.0, variant: "tall", tone: 1 },
  { x: -700, y: 1420, scale: 3.2, variant: "wide", tone: 0 },
  { x: -180, y: 1480, scale: 3.4, variant: "pine", tone: 2 },
  { x: 600, y: 1500, scale: 3.1, variant: "round", tone: 1 },
  { x: 1300, y: 1470, scale: 3.3, variant: "tall", tone: 3 },
  { x: 2000, y: 1500, scale: 3.0, variant: "wide", tone: 2 },
  { x: -1500, y: -900, scale: 3.4, variant: "round", tone: 0 },
  { x: -920, y: 300, scale: 3.1, variant: "pine", tone: 1 },
  { x: 2520, y: 180, scale: 3.2, variant: "tall", tone: 2 },
  { x: 2820, y: 1320, scale: 3.4, variant: "wide", tone: 3 },
  { x: -1220, y: 1660, scale: 3.1, variant: "round", tone: 2 },
  { x: 420, y: 1760, scale: 3.2, variant: "pine", tone: 0 },
  { x: 1820, y: 1760, scale: 3.0, variant: "tall", tone: 1 },
  { x: 2920, y: -720, scale: 3.5, variant: "round", tone: 3 },
  { x: -1560, y: 820, scale: 3.0, variant: "wide", tone: 1 },
  { x: 2460, y: -1020, scale: 3.2, variant: "pine", tone: 2 },
];

/** 主干道双向车道：车辆约 240–285 单位/秒，明显快于行人。 */
const CARS: CarSpec[] = [
  { axis: "x", at: -316, rev: false, speed: 250, start: -900, tone: "#E9A08C", kind: "sedan" },
  { axis: "x", at: -258, rev: true, speed: 280, start: 900, tone: "#9DBBD1", kind: "suv" },
  { axis: "x", at: 1246, rev: true, speed: 240, start: 2200, tone: "#F0C98A", kind: "truck" },
  { axis: "x", at: 1198, rev: false, speed: 265, start: 300, tone: "#B7CDA8", kind: "van" },
  { axis: "y", at: -316, rev: false, speed: 255, start: -800, tone: "#D8B6C8", kind: "sedan" },
  { axis: "y", at: -258, rev: true, speed: 275, start: 1000, tone: "#A8C4D6", kind: "truck" },
  { axis: "y", at: 1746, rev: true, speed: 245, start: 1800, tone: "#E7B58A", kind: "suv" },
  { axis: "y", at: 1698, rev: false, speed: 260, start: 300, tone: "#CBD3A6", kind: "van" },
];

/** 行人约 28–35 单位/秒，保持从容的步行节奏。 */
const WALKERS: WalkerSpec[] = [
  { axis: "x", at: -239, rev: false, dur: 108, delay: -8, shirt: "#e98f72", hair: "#6b4a33" },
  { axis: "x", at: -222, rev: true, dur: 122, delay: -29, shirt: "#7fa8c9", hair: "#4d3826" },
  { axis: "x", at: 1109, rev: true, dur: 116, delay: -32, shirt: "#8fbf9a", hair: "#3f2f24" },
  { axis: "x", at: 1126, rev: false, dur: 104, delay: -47, shirt: "#e3b36a", hair: "#7d5638" },
  { axis: "y", at: -239, rev: true, dur: 112, delay: -20, shirt: "#b79bd1", hair: "#3f2f24" },
  { axis: "y", at: -222, rev: false, dur: 128, delay: -51, shirt: "#8bbfc2", hair: "#6b4a33" },
  { axis: "y", at: 1683, rev: false, dur: 124, delay: -44, shirt: "#d98ca6", hair: "#4d3826" },
  { axis: "y", at: 1700, rev: true, dur: 118, delay: -12, shirt: "#9aa6d6", hair: "#7d5638" },
];

const LAMPS: Array<{ x: number; y: number }> = [
  { x: -150, y: -150 },
  { x: 1550, y: -150 },
  { x: -150, y: 1050 },
  { x: 1550, y: 1050 },
  { x: 520, y: 1050 },
  { x: 880, y: 1050 },
];

/** 四条道路的中心交点，斑马线、停止线与信号灯共用同一套坐标。 */
const JUNCTIONS = [
  { x: -282, y: -282 },
  { x: 1722, y: -282 },
  { x: -282, y: 1222 },
  { x: 1722, y: 1222 },
];

/** 四个来车方向各一盏灯，灯面朝向对应来车；背面只露出深色灯壳。 */
const TRAFFIC_LIGHTS: Array<{ x: number; y: number; axis: Axis; yaw: number }> = JUNCTIONS.flatMap(({ x, y }) => [
  { x: x - 104, y: y - 104, axis: "x", yaw: 90 },
  { x: x + 104, y: y + 104, axis: "x", yaw: -90 },
  { x: x - 104, y: y + 104, axis: "y", yaw: 180 },
  { x: x + 104, y: y - 104, axis: "y", yaw: 0 },
]);

/** 车身中心停在停止线后的位置；前后各留出一个车长余量。 */
const STOP_POSITIONS = {
  x: {
    forward: JUNCTIONS.map(({ x }) => x - 162),
    reverse: JUNCTIONS.map(({ x }) => x + 162),
  },
  y: {
    forward: JUNCTIONS.map(({ y }) => y - 162),
    reverse: JUNCTIONS.map(({ y }) => y + 162),
  },
};

const ROUTE_BOUNDS = {
  x: { min: -1500, max: 2700 },
  y: { min: -1300, max: 2300 },
};

/** 围栏立柱：四条边均匀布点，南侧大门处跳过。 */
function fencePosts() {
  const { x0, y0, x1, y1, step, gateFrom, gateTo } = FENCE;
  const posts: Array<{ x: number; y: number; key: string }> = [];
  for (let x = x0; x <= x1; x += step) {
    posts.push({ x, y: y0, key: `n-${x}` });
    if (x <= gateFrom || x >= gateTo) posts.push({ x, y: y1, key: `s-${x}` });
  }
  for (let y = y0 + step; y < y1; y += step) {
    posts.push({ x: x0, y, key: `w-${y}` });
    posts.push({ x: x1, y, key: `e-${y}` });
  }
  return posts;
}

const POSTS = fencePosts();

function Fence() {
  const { x0, y0, x1, y1, gateFrom, gateTo } = FENCE;
  const rails: Array<{ key: string; style: React.CSSProperties }> = [
    { key: "north", style: { left: x0, top: y0 - 4, width: x1 - x0, height: 9 } },
    { key: "south-a", style: { left: x0, top: y1 - 4, width: gateFrom - x0, height: 9 } },
    { key: "south-b", style: { left: gateTo, top: y1 - 4, width: x1 - gateTo, height: 9 } },
    { key: "west", style: { left: x0 - 4, top: y0, width: 9, height: y1 - y0 } },
    { key: "east", style: { left: x1 - 4, top: y0, width: 9, height: y1 - y0 } },
  ];

  return (
    <div className="fence">
      {rails.map((rail) => (
        <span key={rail.key} className="fence-rail" style={rail.style} />
      ))}
      {rails.map((rail) => (
        <span
          key={`low-${rail.key}`}
          className="fence-rail low"
          style={rail.style}
        />
      ))}
      {POSTS.map((post) => (
        <span key={post.key} className="fence-post" style={{ left: post.x, top: post.y }} />
      ))}
    </div>
  );
}

function RoadMarkings({ x, y }: { x: number; y: number }) {
  return (
    <>
      {/* 四个方向的斑马线 */}
      <span className="crosswalk crosswalk-ns" style={{ left: x - 105, top: y - 48 }} />
      <span className="crosswalk crosswalk-ns" style={{ left: x + 61, top: y - 48 }} />
      <span className="crosswalk crosswalk-ew" style={{ left: x - 48, top: y - 105 }} />
      <span className="crosswalk crosswalk-ew" style={{ left: x - 48, top: y + 61 }} />
      {/* 每个方向只在来车一侧设置停止线 */}
      <span className="stop-line" style={{ left: x - 114, top: y - 46, width: 8, height: 44 }} />
      <span className="stop-line" style={{ left: x + 106, top: y + 2, width: 8, height: 44 }} />
      <span className="stop-line" style={{ left: x - 46, top: y - 114, width: 44, height: 8 }} />
      <span className="stop-line" style={{ left: x + 2, top: y + 106, width: 44, height: 8 }} />
    </>
  );
}

function TrafficLight({ x, y, axis, yaw }: { x: number; y: number; axis: Axis; yaw: number }) {
  /** 横向先绿 7 秒，纵向错相 8 秒；黄灯期间车辆准备停车。 */
  const delay = axis === "x" ? "0s" : "-8s";
  return (
    <div
      className="traffic-light"
      data-axis={axis}
      style={{ left: x, top: y, "--tl-yaw": `${yaw}deg` } as React.CSSProperties}
    >
      <span className="tl-shadow" />
      <span className="tl-base" />
      <span className="tl-stand">
        <span className="tl-pole" />
        <span className="tl-head">
          <span className="tl-visor v-red" />
          <span className="tl-visor v-yellow" />
          <span className="tl-visor v-green" />
          <i className="tl-lamp red" style={{ animationDelay: delay }} />
          <i className="tl-lamp yellow" style={{ animationDelay: delay }} />
          <i className="tl-lamp green" style={{ animationDelay: delay }} />
        </span>
      </span>
    </div>
  );
}

function Tree({ tree }: { tree: TreeSpec }) {
  const tone = TREE_TONES[tree.tone];
  return (
    <div
      className={`tree v-${tree.variant}`}
      style={{
        left: tree.x,
        top: tree.y,
        transform: `translateZ(-60px) scale3d(${tree.scale}, ${tree.scale}, ${tree.scale})`,
        "--leaf-a": tone.a,
        "--leaf-b": tone.b,
        "--leaf-c": tone.c,
      } as React.CSSProperties}
    >
      <span className="tree-shadow" />
      <span className="tree-stand">
        <span className="tree-trunk" />
        {tree.variant !== "pine" && (
          <>
            <span className="tree-branch bl-u" />
            <span className="tree-branch bl-l" />
            <span className="tree-branch br-u" />
            <span className="tree-branch br-l" />
          </>
        )}
        {tree.variant === "pine" ? (
          <span className="pine-crown">
            <i className="pine-tier p1" />
            <i className="pine-tier p2" />
            <i className="pine-tier p3" />
            <i className="pine-tier p4" />
          </span>
        ) : (
          <span className="tree-leaves">
            <i className="tree-leaf l1" />
            <i className="tree-leaf l2" />
            <i className="tree-leaf l3" />
            <i className="tree-leaf l4" />
            <i className="tree-leaf l5" />
            <i className="tree-leaf l6" />
            <i className="tree-leaf l7" />
            <i className="tree-leaf l8" />
            <i className="tree-leaf l9" />
            <i className="tree-leaf l10" />
          </span>
        )}
      </span>
    </div>
  );
}

function Car({ car }: { car: CarSpec }) {
  const rot = car.axis === "x" ? (car.rev ? 180 : 0) : car.rev ? 90 : -90;
  return (
    <div
      className="lane"
      style={{
        left: car.axis === "y" ? car.at : 0,
        top: car.axis === "x" ? car.at : 0,
      }}
    >
      <div className="car-drive" data-axis={car.axis}>
        <div
          className={`car k-${car.kind}`}
          style={{ background: car.tone, transform: `rotateZ(${rot}deg) translateZ(12px)` }}
        >
          <span className="car-cab" />
          <span className="car-roof" />
          <span className="car-glass front" />
          <span className="car-glass back" />
          <span className="car-wheel w1" />
          <span className="car-wheel w2" />
          <span className="car-wheel w3" />
          <span className="car-wheel w4" />
          <span className="car-light front" />
          <span className="car-light back" />
        </div>
      </div>
    </div>
  );
}

function Walker({ walker }: { walker: WalkerSpec }) {
  const walk =
    walker.axis === "x" ? (walker.rev ? "walk-x-rev" : "walk-x") : walker.rev ? "walk-y-rev" : "walk-y";
  return (
    <div
      className="lane"
      style={{
        left: walker.axis === "y" ? walker.at : 0,
        top: walker.axis === "x" ? walker.at : 0,
      }}
    >
      <div
        className={`walker ${walk}`}
        style={{ animationDuration: `${walker.dur}s`, animationDelay: `${walker.delay}s` }}
      >
        <span className="walker-shadow" />
        <span
          className="walker-figure"
          style={{ "--shirt": walker.shirt, "--hair": walker.hair } as React.CSSProperties}
        >
          <i className="walker-arm left" />
          <i className="walker-leg left" />
          <i className="walker-leg right" />
          <i className="walker-body" />
          <i className="walker-arm right" />
          <i className="walker-neck" />
          <i className="walker-head">
            <i className="walker-face" />
          </i>
        </span>
      </div>
    </div>
  );
}

/** 整楼园区场景：仅在 overview 状态挂载；聚焦楼层时整个卸载以释放 DOM 和 RAF。 */
export function SiteScene({ visible = true }: { visible?: boolean }) {
  const siteRef = useRef<HTMLDivElement>(null);

  /** 直接更新 8 辆车的 transform，避免每帧触发 React 重渲染。 */
  useLayoutEffect(() => {
    if (!visible) return; // focused 时虽然组件不渲染，但为安全起见再检查一次
    const root = siteRef.current;
    if (!root) return;
    const nodes = Array.from(root.querySelectorAll<HTMLElement>(".car-drive"));
    const positions = CARS.map((car) => car.start);

    nodes.forEach((node, i) => {
      const car = CARS[i];
      node.style.transform =
        car.axis === "x" ? `translate3d(${positions[i]}px, 0, 0)` : `translate3d(0, ${positions[i]}px, 0)`;
    });

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const startedAt = performance.now();
    let previous = startedAt;
    let frame = 0;

    const tick = (now: number) => {
      const dt = Math.min((now - previous) / 1000, 0.05);
      previous = now;
      const phase = ((now - startedAt) / 1000) % 16;

      CARS.forEach((car, i) => {
        const green = car.axis === "x" ? phase < 7 : phase >= 8 && phase < 15;
        const direction = car.rev ? -1 : 1;
        const bounds = ROUTE_BOUNDS[car.axis];
        const current = positions[i];
        let next = current + direction * car.speed * dt;

        if (!car.rev && next > bounds.max) next = bounds.min + (next - bounds.max);
        if (car.rev && next < bounds.min) next = bounds.max - (bounds.min - next);

        /* 红灯或黄灯时只截停在最近的停止线前；已经进入路口的车继续驶离。 */
        if (!green) {
          const stops = STOP_POSITIONS[car.axis][car.rev ? "reverse" : "forward"];
          for (const stop of stops) {
            if ((!car.rev && current <= stop && next >= stop) || (car.rev && current >= stop && next <= stop)) {
              next = stop;
              break;
            }
          }
        }

        positions[i] = next;
        nodes[i].style.transform =
          car.axis === "x" ? `translate3d(${next}px, 0, 0)` : `translate3d(0, ${next}px, 0)`;
      });

      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [visible]); // visible 变化时重跑/清理

  if (!visible) return null;

  return (
    <div className="site" ref={siteRef}>
      <div className="ground">
        <div className="avenue-h" style={{ top: -330 }} />
        <div className="avenue-h" style={{ top: 1174 }} />
        <div className="avenue-v" style={{ left: -330 }} />
        <div className="avenue-v" style={{ left: 1674 }} />
        {JUNCTIONS.map((junction, i) => (
          <RoadMarkings key={`junction-${i}`} {...junction} />
        ))}
        <div className="sidewalk" style={{ left: -240, top: -256, width: 1860, height: 34 }} />
        <div className="sidewalk" style={{ left: -240, top: 1092, width: 1860, height: 34 }} />
        <div className="sidewalk" style={{ left: -240, top: -256, width: 34, height: 1420 }} />
        <div className="sidewalk" style={{ left: 1666, top: -256, width: 34, height: 1420 }} />
        <div className="walk-path" />
        <div className="plaza" />
      </div>

      <Fence />

      {TRAFFIC_LIGHTS.map((light, i) => (
        <TrafficLight key={`tl-${i}`} {...light} />
      ))}

      {TREES.map((tree, i) => (
        <Tree key={`tree-${i}`} tree={tree} />
      ))}

      {LAMPS.map((lamp, i) => (
        <div key={`lamp-${i}`} className="lamp" style={{ left: lamp.x, top: lamp.y }}>
          <span className="lamp-pole" />
          <span className="lamp-head" />
          <span className="lamp-glow" />
        </div>
      ))}

      {WALKERS.map((walker, i) => (
        <Walker key={`walker-${i}`} walker={walker} />
      ))}

      {CARS.map((car, i) => (
        <Car key={`car-${i}`} car={car} />
      ))}
    </div>
  );
}

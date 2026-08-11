import { Canvas, ThreeEvent, useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import type { Group, Mesh } from "three";

function OrbitCore({ selected }: { selected: boolean }) {
  const ref = useRef<Mesh>(null);
  useFrame((_, delta) => {
    if (!ref.current) return;
    ref.current.rotation.y += delta * (selected ? 1.2 : 0.75);
    ref.current.rotation.x += delta * 0.28;
  });
  return (
    <mesh ref={ref}>
      <icosahedronGeometry args={[1.15, 1]} />
      <meshStandardMaterial
        color={selected ? "#7ef0ff" : "#3de0ff"}
        wireframe
        emissive="#124858"
        emissiveIntensity={selected ? 0.9 : 0.55}
      />
    </mesh>
  );
}

function Ring({ speed = 0.4, scale = 1.9 }: { speed?: number; scale?: number }) {
  const ref = useRef<Mesh>(null);
  useFrame((_, delta) => {
    if (ref.current) ref.current.rotation.z -= delta * speed;
  });
  return (
    <mesh ref={ref} rotation={[Math.PI / 2.35, 0.15, 0]} scale={scale}>
      <torusGeometry args={[1, 0.025, 10, 80]} />
      <meshStandardMaterial color="#f0a020" emissive="#f0a020" emissiveIntensity={0.4} />
    </mesh>
  );
}

const COLORS = ["#00d4ff", "#8b5cf6", "#3ecf8e", "#e8a045", "#7ef0ff", "#c4a0ff", "#6dffb0"];

function buildFleet(ids?: string[]) {
  const list = ids && ids.length ? ids.slice(0, 16) : ["lingyun", "lingzhao", "xiaoqi", "dali"];
  const n = list.length;
  return list.map((id, i) => {
    const angle = (i / Math.max(n, 1)) * Math.PI * 2;
    const r = 1.6 + (i % 3) * 0.35;
    return {
      id,
      label: id,
      color: COLORS[i % COLORS.length],
      pos: [Math.cos(angle) * r, Math.sin(angle * 0.7) * 0.9, Math.sin(angle) * r * 0.35] as [
        number,
        number,
        number,
      ],
    };
  });
}

function FleetNode({
  id,
  label,
  color,
  position,
  active,
  onSelect,
}: {
  id: string;
  label: string;
  color: string;
  position: readonly [number, number, number];
  active: boolean;
  onSelect: (id: string) => void;
}) {
  const g = useRef<Group>(null);
  useFrame((state) => {
    if (!g.current) return;
    g.current.position.y = position[1] + Math.sin(state.clock.elapsedTime * 1.4 + position[0]) * 0.08;
  });
  return (
    <group
      ref={g}
      position={[position[0], position[1], position[2]]}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation();
        onSelect(id);
      }}
      onPointerOver={() => {
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        document.body.style.cursor = "auto";
      }}
    >
      <mesh>
        <octahedronGeometry args={[active ? 0.26 : 0.18, 0]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={active ? 1.1 : 0.45}
          wireframe={!active}
        />
      </mesh>
      <mesh position={[0, 0.38, 0]}>
        <planeGeometry args={[Math.min(label.length, 10) * 0.055 + 0.12, 0.14]} />
        <meshBasicMaterial color="#060910" transparent opacity={0.65} />
      </mesh>
    </group>
  );
}

type SceneProps = {
  interactive?: boolean;
  onSelect?: (id: string) => void;
  selectedId?: string;
  fleetIds?: string[];
};

/** Wave8 R3F shell — rings + core; fleet nodes from live agent ids when provided. */
export function StarfieldScene({ interactive = false, onSelect, selectedId, fleetIds }: SceneProps) {
  const [localSel, setLocalSel] = useState(fleetIds?.[0] || "lingyun");
  const sel = selectedId ?? localSel;
  const pick = (id: string) => {
    setLocalSel(id);
    onSelect?.(id);
    window.parent?.postMessage({ type: "mailbus/agent-select", agent: id }, "*");
  };
  const nodes = useMemo(() => buildFleet(fleetIds), [fleetIds]);

  return (
    <div className="hud-panel relative h-56 w-full overflow-hidden md:h-80">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-abyss via-transparent to-cyan-signal/5" />
      <Canvas camera={{ position: [0, 0.55, 4.4], fov: 40 }}>
        <color attach="background" args={["#05080f"]} />
        <ambientLight intensity={0.3} />
        <pointLight position={[5, 3, 6]} intensity={1.35} color="#3de0ff" />
        <pointLight position={[-4, -2, -3]} intensity={0.55} color="#f0a020" />
        <OrbitCore selected={interactive && !!sel} />
        <Ring speed={0.35} scale={1.85} />
        <Ring speed={-0.22} scale={2.25} />
        {interactive &&
          nodes.map((n) => (
            <FleetNode
              key={n.id}
              id={n.id}
              label={n.label}
              color={n.color}
              position={n.pos}
              active={sel === n.id}
              onSelect={pick}
            />
          ))}
      </Canvas>
      <p className="pointer-events-none absolute bottom-3 left-3 font-display text-[10px] tracking-[0.25em] text-cyan-signal/80">
        R3F · {interactive ? "FLEET" : "LIVE"}
      </p>
      {interactive && (
        <p className="pointer-events-none absolute bottom-3 right-3 font-mono text-[10px] text-amber-signal">
          sel:{sel}
        </p>
      )}
    </div>
  );
}


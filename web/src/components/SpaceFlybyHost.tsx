import { createRoot, type Root } from "react-dom/client";
import { useLayoutEffect, useRef } from "react";
import { SpaceFlybyScene } from "./SpaceFlyby";

/**
 * 驾驶舱 hover 会频繁 setState。若 SpaceFlyby 落在同一 React 树里，
 * 即便 memo，仍可能因父级协调 / 合成层变化导致 Canvas 重建 → 宇宙「换片」。
 * 这里用模块级单例 createRoot：场景只挂载一次，宿主只负责把 DOM 节点挂回槽位。
 */

let flybyNode: HTMLDivElement | null = null;
let flybyRoot: Root | null = null;
let parkNode: HTMLDivElement | null = null;

function ensurePark() {
  if (parkNode || typeof document === "undefined") return parkNode;
  parkNode = document.createElement("div");
  parkNode.id = "cp-space-park";
  parkNode.setAttribute("aria-hidden", "true");
  // 保持全视口尺寸，避免 canvas 缩成 0 触发 WebGL context loss
  parkNode.style.cssText =
    "position:fixed;inset:0;visibility:hidden;pointer-events:none;z-index:-1;overflow:hidden;";
  document.body.appendChild(parkNode);
  return parkNode;
}

function ensureFlybyNode() {
  if (flybyNode) return flybyNode;
  flybyNode = document.createElement("div");
  flybyNode.className = "cp-space-flyby";
  flybyNode.setAttribute("aria-hidden", "true");
  flybyNode.style.cssText = "position:absolute;inset:0;pointer-events:none;";
  flybyRoot = createRoot(flybyNode);
  flybyRoot.render(<SpaceFlybyScene />);
  return flybyNode;
}

/** 槽位组件：可安全随 Cockpit 重渲染；不卸载 WebGL 场景 */
export function SpaceFlybyHost() {
  const slotRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const slot = slotRef.current;
    if (!slot) return;
    const node = ensureFlybyNode();
    node.style.visibility = "visible";
    if (node.parentElement !== slot) slot.appendChild(node);
    return () => {
      const park = ensurePark();
      if (park && node.parentElement === slot) {
        node.style.visibility = "hidden";
        park.appendChild(node);
      }
    };
  }, []);

  return <div ref={slotRef} className="cp-space-slot" aria-hidden />;
}

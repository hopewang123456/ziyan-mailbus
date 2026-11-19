/** 大楼外壳：detail=false 时只渲染南立面 + 屋顶（省 DOM），detail=true 渲染 3 面完整窗墙。 */

interface BuildingShellProps {
  /** 外壳总高（含屋顶），由楼层数换算。 */
  height: number;
  /** 是否渲染东西侧窗墙（peek/focused 时需要完整体量）。 */
  detail: boolean;
}

/** 南立面窗格：7 排 × 10 列，夜间分亮/微亮/关灯三档，避免整面一样亮。 */
const WINDOWS = Array.from({ length: 70 }, (_, i) => {
  const row = Math.floor(i / 10);
  const col = i % 10;
  const level = (row * 7 + col * 3) % 7;
  return {
    left: `${5 + col * 9.3}%`,
    top: `${9 + row * 11.6}%`,
    tone: level === 0 ? "off" : level <= 3 ? "soft" : "lit",
  };
});

function FacadeWindows() {
  return (
    <>
      {WINDOWS.map((win, i) => (
        <span
          key={`win-${i}`}
          className={`facade-win${win.tone === "off" ? "" : ` is-${win.tone}`}`}
          style={{ left: win.left, top: win.top }}
        />
      ))}
    </>
  );
}

export function BuildingShell({ height, detail }: BuildingShellProps) {
  return (
    <div className="shell">
      {/* 屋顶：停机坪、设备间、空调机组 */}
      <div className="shell-roof" style={{ transform: `translateZ(${height}px)` }}>
        <span className="roof-pad" />
        <span className="roof-shed" />
        <span className="roof-unit u1" />
        <span className="roof-unit u2" />
      </div>

      {/* 南立面（面向广场）：始终渲染，幕墙窗格、楼体招牌、首层入口 */}
      <div className="shell-wall shell-wall-s" style={{ height }}>
        <span className="facade-skin" />
        <FacadeWindows />
        <span className="facade-sign">ZIYAN</span>
        <span className="facade-entry" />
      </div>

      {/* 西立面：detail 模式下才渲染窗格，概览只保留墙皮做体量 */}
      <div className="shell-wall shell-wall-w" style={{ width: height, left: -height }}>
        <span className="facade-skin" />
        {detail && <FacadeWindows />}
      </div>

      {/* 东立面：同西立面 */}
      <div className="shell-wall shell-wall-e" style={{ width: height }}>
        <span className="facade-skin" />
        {detail && <FacadeWindows />}
      </div>
    </div>
  );
}

import type { SeatAgent } from "./types";

const TASK_STATE_LABEL: Record<string, string> = {
  created: "待派发",
  dispatched: "已派发",
  running: "执行中",
  review: "评审中",
  blocked: "阻塞",
  done: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const STATUS_LABEL: Record<string, string> = {
  online: "在线",
  busy: "忙碌",
  offline: "离线",
};

/**
 * 悬停信息卡：头像 + 姓名 / 岗位 / Agent / 在忙什么。
 * 动画与箭头由 twin.css 的 .person-card 驱动，这里只组织内容。
 */
export function PersonHoverCard({ agent }: { agent: SeatAgent }) {
  const busy = Boolean(agent.task_id || agent.task);
  const stateLabel = agent.task_state
    ? TASK_STATE_LABEL[agent.task_state] ?? agent.task_state
    : null;
  const total = agent.progress_total ?? 0;
  const done = agent.progress_done ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;

  return (
    <span className="person-card" aria-hidden>
      <span className="pc-glow" />
      <span className="pc-head">
        <span className="pc-avatar">{agent.display_name.slice(0, 1)}</span>
        <span className="pc-ident">
          <strong>{agent.display_name}</strong>
          <em>
            {agent.position || "岗位未设置"}
            {agent.team ? ` · ${agent.team}` : ""}
          </em>
        </span>
        <span className={`pc-status is-${agent.status}`}>
          {STATUS_LABEL[agent.status] ?? agent.status}
        </span>
      </span>

      <span className="pc-divider" />

      <span className="pc-agent">
        <i className="pc-agent-dot" />
        {agent.agent_name || "未绑定 Agent"}
        {agent.agent_framework ? (
          <span className="pc-framework">{agent.agent_framework}</span>
        ) : null}
      </span>

      {busy ? (
        <span className="pc-task">
          <span className="pc-task-name">{agent.task || "未命名任务"}</span>
          {total > 0 ? (
            <span className="pc-bar">
              <i style={{ width: `${pct}%` }} />
              <b>
                {done}/{total}
              </b>
            </span>
          ) : null}
          {agent.current_node || stateLabel ? (
            <span className="pc-task-meta">
              {agent.current_node ?? ""}
              {stateLabel ? ` · ${stateLabel}` : ""}
            </span>
          ) : null}
        </span>
      ) : (
        <span className="pc-idle">
          <i />
          当前空闲，可以走动
        </span>
      )}

      <span className="pc-arrow" />
    </span>
  );
}

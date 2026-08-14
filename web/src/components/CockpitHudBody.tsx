import { useState, type ReactNode } from "react";
import { HudCardGrid } from "./HudCardGrid";
import { HudL3Modal } from "./HudL3Modal";
import { AgentOrbitPanel } from "./AgentOrbitPanel";
import { TasksPage } from "../pages/TasksPage";
import { AuditPage } from "../pages/AuditPage";
import { HumanGatePage } from "../pages/HumanGatePage";
import { ConfigPage } from "../pages/ConfigPage";
import { IntegrationsPage } from "../pages/IntegrationsPage";
import { ClinicPage } from "../pages/ClinicPage";
import { InboxPage } from "../pages/InboxPage";
import { CommandBriefPage } from "../pages/CommandBriefPage";
import { ApiListPage } from "../pages/thin/ApiListPage";
import { WorkflowBoardPage } from "../pages/thin/WorkflowBoardPage";
import { t, type I18nKey } from "../lib/i18n";

export type HudPanelId =
  | "home"
  | "tasks"
  | "agents"
  | "llm"
  | "integrations"
  | "bus"
  | "clinic"
  | "other"
  | "gear";

function CardLauncher({
  cards,
  render,
  surface = "form",
}: {
  cards: { id: string; titleKey: I18nKey; blurb?: string }[];
  render: (id: string) => ReactNode;
  surface?: "fleet" | "form";
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const title = cards.find((c) => c.id === openId)?.titleKey;
  return (
    <>
      <HudCardGrid
        surface={surface}
        cards={cards.map((c) => ({ id: c.id, title: t(c.titleKey), blurb: c.blurb }))}
        onOpen={setOpenId}
      />
      <HudL3Modal title={title ? t(title) : ""} open={!!openId} onClose={() => setOpenId(null)}>
        {openId ? render(openId) : null}
      </HudL3Modal>
    </>
  );
}

function WorkCards() {
  return (
    <CardLauncher
      surface="form"
      cards={[
        { id: "tasks", titleKey: "tasks", blurb: "FSM / 工单" },
        { id: "audit", titleKey: "audit", blurb: "统计与异常" },
        { id: "human", titleKey: "human", blurb: "队列 + Reviews" },
      ]}
      render={(id) => {
        if (id === "tasks") return <TasksPage />;
        if (id === "audit") return <AuditPage />;
        return <HumanGatePage />;
      }}
    />
  );
}

function OtherCards() {
  return (
    <CardLauncher
      cards={[
        { id: "intake", titleKey: "intake", blurb: "商前 · 需求入口" },
        { id: "workflows", titleKey: "workflows", blurb: "工作流定义" },
        { id: "content", titleKey: "content", blurb: "任务内容 · 最近40条" },
        { id: "pipeline", titleKey: "pipeline", blurb: "人机队列" },
        { id: "inbox", titleKey: "inbox", blurb: "Agent 信箱" },
        { id: "bulletin", titleKey: "bulletin", blurb: "公告板" },
        { id: "stats", titleKey: "stats", blurb: "审核统计" },
        { id: "patrol", titleKey: "patrol", blurb: "巡检报告" },
        { id: "alerts", titleKey: "alerts", blurb: "告警日志" },
      ]}
      render={(id) => {
        switch (id) {
          case "intake":
            return <ApiListPage title={t("intake")} path="/api/intake" listKey="intakes" />;
          case "workflows":
            return <WorkflowBoardPage />;
          case "content":
            return <ApiListPage title={t("content")} path="/api/tasks?limit=40" listKey="tasks" />;
          case "pipeline":
            return <ApiListPage title={t("pipeline")} path="/api/human-queue?status=pending" listKey="items" />;
          case "inbox":
            return <InboxPage />;
          case "bulletin":
            return <ApiListPage title={t("bulletin")} path="/api/bulletin" listKey="bulletins" variant="mail" />;
          case "stats":
            return <ApiListPage title={t("stats")} path="/api/tasks/audit/stats" variant="stats" />;
          case "patrol":
            return <ApiListPage title={t("patrol")} path="/api/patrol-reports" variant="mail" />;
          case "alerts":
            return <ApiListPage title={t("alerts")} path="/api/alerts" listKey="alerts" variant="mail" />;
          default:
            return null;
        }
      }}
    />
  );
}

export function CockpitHudBody({ panel }: { panel: HudPanelId }) {
  // Do not useMemo JSX — keeps panel mounts predictable when switching hotspots.
  let body: ReactNode = null;
  switch (panel) {
    case "home":
      body = <CommandBriefPage />;
      break;
    case "tasks":
      body = <WorkCards />;
      break;
    case "agents":
      body = <AgentOrbitPanel />;
      break;
    case "llm":
      body = <ConfigPage variant="llm" />;
      break;
    case "integrations":
      body = <IntegrationsPage />;
      break;
    case "bus":
      body = <ConfigPage variant="bus" />;
      break;
    case "clinic":
      body = <ClinicPage />;
      break;
    case "other":
      body = <OtherCards />;
      break;
    case "gear":
      body = <ConfigPage variant="gear" />;
      break;
    default:
      body = null;
  }

  return <div className="cp-hud-panel-root">{body}</div>;
}

import { useMemo, useRef, useState } from "react";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import { Dialog, ConfirmDialog } from "../../components/console/ConsoleDialog";
import {
  useScreens,
  usePairs,
  useMessages,
  useLayout,
} from "../../lib/collab/hooks";
import {
  upsertScreen,
  publishScreen,
  focusScreen,
  deleteScreen,
  endPair,
  sendMessage,
  assignSeat,
  publicScreenConfig,
  type UpsertScreenBody,
} from "../../lib/collab/api";
import {
  PLAY_STATE_LABEL,
  PAIR_STATE_LABEL,
  DELIVERY_STATUS_LABEL,
  MESSAGE_KIND_LABEL,
  timeText,
  type ScreenRow,
} from "../../lib/collab/view";
import { useEmployees } from "../../lib/org/hooks";
import type { components } from "../../lib/contracts";

/**
 * 协同大屏管理端（F5）：屏幕列表 / 结对管理 / 协同消息 三 Tab + 可视化布局编辑器。
 * 所有数据读取走 collab/hooks.ts；所有写操作走 collab/api.ts；不直接 fetch。
 * 权限由 props.can(capability) 控制，典型需要 console_admin / message_send。
 */

type Tab = "screens" | "pairs" | "messages";

const TABS: Array<{ key: Tab; label: string }> = [
  { key: "screens", label: "屏幕列表" },
  { key: "pairs", label: "结对管理" },
  { key: "messages", label: "协同消息" },
];

type ConfigTheme = NonNullable<components["schemas"]["ScreenConfigIn"]["theme"]>;
type ConfigLayoutType = NonNullable<components["schemas"]["ScreenConfigIn"]["layout_type"]>;
type ConfigResolution = NonNullable<components["schemas"]["ScreenConfigIn"]["resolution"]>;
type ScreenConfigIn = components["schemas"]["ScreenConfigIn"];

const DEFAULT_CONFIG_KEY = "auto|office|1920x1080";
const THEMES: ConfigTheme[] = ["auto", "dark", "light"];
const LAYOUT_TYPES: ConfigLayoutType[] = ["office", "grid", "custom"];
const RESOLUTIONS: ConfigResolution[] = ["1920x1080", "3840x2160"];

/** 公开配置接口返回的是宽泛的 string，这里按允许值收窄。 */
function pick<T extends string>(allowed: readonly T[], value: string, fallback: T): T {
  return allowed.find((item) => item === value) ?? fallback;
}

export function ConsoleCollabPage({ can }: { can: (capability: string) => boolean }) {
  const [tab, setTab] = useState<Tab>("screens");

  // === 域层读取 ===
  const {
    items: screens,
    loading: screensLoading,
    error: screensError,
    refresh: refreshScreens,
  } = useScreens({ limit: 200, offset: 0 });

  const {
    items: pairs,
    loading: pairsLoading,
    error: pairsError,
    refresh: refreshPairs,
  } = usePairs({ limit: 200 });

  const [pairFilterId, setPairFilterId] = useState<string>("");
  const {
    items: messages,
    loading: messagesLoading,
    error: messagesError,
    refresh: refreshMessages,
  } = useMessages({ pair_id: pairFilterId || null, limit: 200 });

  const {
    data: layout,
    loading: layoutLoading,
    error: layoutError,
    refresh: refreshLayout,
  } = useLayout();

  const { items: employees } = useEmployees({ limit: 500 });

  // === 状态 ===
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorScreen, setEditorScreen] = useState<ScreenRow | null>(null);
  const [editorName, setEditorName] = useState("");
  const [editorPlayState, setEditorPlayState] = useState<"playing" | "paused">("playing");
  const [editorTheme, setEditorTheme] = useState<ConfigTheme>("auto");
  const [editorLayoutType, setEditorLayoutType] = useState<ConfigLayoutType>("office");
  const [editorResolution, setEditorResolution] = useState<ConfigResolution>("1920x1080");
  /** 打开对话框时主题/布局/分辨率的组合值，用来判断用户是否改过配置。 */
  const [editorConfigKey, setEditorConfigKey] = useState(DEFAULT_CONFIG_KEY);
  const [editorConfigLoading, setEditorConfigLoading] = useState(false);
  const editorScreenIdRef = useRef<string | null>(null);

  const [layoutEditorOpen, setLayoutEditorOpen] = useState(false);
  const [layoutEditorScreen, setLayoutEditorScreen] = useState<ScreenRow | null>(null);

  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ScreenRow | null>(null);

  const [publishConfirmOpen, setPublishConfirmOpen] = useState(false);
  const [publishTarget, setPublishTarget] = useState<ScreenRow | null>(null);

  const [focusFloor, setFocusFloor] = useState("");

  const [messageBody, setMessageBody] = useState("");
  const [messageKind, setMessageKind] = useState("note");

  const [busy, setBusy] = useState(false);
  const [globalErr, setGlobalErr] = useState("");
  const [globalMsg, setGlobalMsg] = useState("");

  const canAdmin = can("console_admin");
  const canSend = can("message_send");
  const canFocus = can("console_admin");

  const employeeMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const e of employees) m.set(e.id, e.displayName);
    return m;
  }, [employees]);

  // === 事件 ===

  const showError = (err: string) => {
    setGlobalErr(err);
    setGlobalMsg("");
  };
  const showMsg = (msg: string) => {
    setGlobalMsg(msg);
    setGlobalErr("");
  };

  const openCreateScreen = () => {
    if (!canAdmin) return;
    setEditorScreen(null);
    setEditorName("");
    setEditorPlayState("playing");
    setEditorTheme("auto");
    setEditorLayoutType("office");
    setEditorResolution("1920x1080");
    setEditorConfigKey(DEFAULT_CONFIG_KEY);
    setEditorConfigLoading(false);
    editorScreenIdRef.current = null;
    setGlobalErr("");
    setGlobalMsg("");
    setEditorOpen(true);
  };

  const openEditScreen = (row: ScreenRow) => {
    if (!canAdmin) return;
    editorScreenIdRef.current = row.id;
    setEditorScreen(row);
    setEditorName(row.name);
    setEditorPlayState(row.play_state === "paused" ? "paused" : "playing");
    setEditorTheme("auto");
    setEditorLayoutType("office");
    setEditorResolution("1920x1080");
    setEditorConfigKey(DEFAULT_CONFIG_KEY);
    setEditorOpen(true);
    // 管理端没有读取草稿配置的接口，只能用已发布配置回填；返回时已切到别的屏幕则忽略。
    setEditorConfigLoading(true);
    void publicScreenConfig(row.id).then((result) => {
      if (editorScreenIdRef.current !== row.id) return;
      setEditorConfigLoading(false);
      if (!result.ok || !result.data.published) return;
      const { theme, layout_type: layoutType, resolution } = result.data;
      setEditorTheme(pick(THEMES, theme, "auto"));
      setEditorLayoutType(pick(LAYOUT_TYPES, layoutType, "office"));
      setEditorResolution(pick(RESOLUTIONS, resolution, "1920x1080"));
      setEditorConfigKey(`${theme}|${layoutType}|${resolution}`);
    });
  };

  const submitEditor = async () => {
    if (!canAdmin) return;
    if (!editorName.trim()) {
      showError("屏幕名称不能为空");
      return;
    }
    setBusy(true);
    setGlobalErr("");
    setGlobalMsg("");
    const config: ScreenConfigIn = {
      layout_type: editorLayoutType,
      theme: editorTheme,
      resolution: editorResolution,
    };
    // 编辑已有屏幕且主题/布局/分辨率都没动时不提交 config，避免用默认值覆盖草稿。
    const configUntouched =
      editorScreen !== null &&
      `${editorTheme}|${editorLayoutType}|${editorResolution}` === editorConfigKey;
    const body: UpsertScreenBody = {
      id: editorScreen?.id,
      name: editorName.trim(),
      play_state: editorPlayState,
      config: configUntouched ? undefined : config,
    };
    const result = await upsertScreen(body);
    setBusy(false);
    if (!result.ok) {
      showError(result.error);
      return;
    }
    setEditorOpen(false);
    showMsg(editorScreen ? `已保存 ${editorName} 的草稿` : `已创建大屏 ${editorName}`);
    await refreshScreens();
  };

  const openPublishConfirm = (row: ScreenRow) => {
    if (!canAdmin) return;
    if (!row.has_draft && row.is_published) {
      showMsg(`${row.name} 没有可发布的草稿`);
      return;
    }
    setPublishTarget(row);
    setPublishConfirmOpen(true);
  };

  const submitPublish = async () => {
    if (!publishTarget) return;
    setBusy(true);
    setGlobalErr("");
    setGlobalMsg("");
    const result = await publishScreen(publishTarget.id, publishTarget.config_version);
    setBusy(false);
    setPublishConfirmOpen(false);
    if (!result.ok) {
      showError(result.error);
      return;
    }
    showMsg(`${publishTarget.name} 已发布（v${result.data?.config_version ?? publishTarget.config_version}）`);
    setPublishTarget(null);
    await refreshScreens();
  };

  const openDeleteConfirm = (row: ScreenRow) => {
    if (!canAdmin) return;
    setDeleteTarget(row);
    setDeleteConfirmOpen(true);
  };

  const submitDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    setGlobalErr("");
    setGlobalMsg("");
    const result = await deleteScreen(deleteTarget.id);
    setBusy(false);
    setDeleteConfirmOpen(false);
    if (!result.ok) {
      showError(result.error);
      return;
    }
    showMsg(`已删除 ${deleteTarget.name}`);
    setDeleteTarget(null);
    await refreshScreens();
  };

  const submitFocus = async (row: ScreenRow) => {
    if (!canFocus) return;
    if (!focusFloor) {
      showError("请先选择目标楼层");
      return;
    }
    setBusy(true);
    setGlobalErr("");
    setGlobalMsg("");
    const result = await focusScreen(row.id, {
      floor_id: focusFloor,
      seat_id: null,
    });
    setBusy(false);
    if (!result.ok) {
      showError(result.error);
      return;
    }
    showMsg(`已让 ${row.name} 聚焦 ${focusFloor}`);
  };

  const submitEndPair = async (pairId: string) => {
    setBusy(true);
    setGlobalErr("");
    setGlobalMsg("");
    const result = await endPair(pairId);
    setBusy(false);
    if (!result.ok) {
      showError(result.error);
      return;
    }
    showMsg("结对已结束");
    await refreshPairs();
  };

  const submitSendMessage = async () => {
    if (!canSend) return;
    if (!messageBody.trim()) {
      showError("消息内容不能为空");
      return;
    }
    const pairId = pairFilterId;
    if (!pairId) {
      showError("协同消息必须选择结对或指定 pair_id");
      return;
    }
    setBusy(true);
    setGlobalErr("");
    setGlobalMsg("");
    const result = await sendMessage({
      pair_id: pairId,
      body: messageBody.trim(),
      kind: messageKind,
      channel: "file_bus",
    });
    setBusy(false);
    if (!result.ok) {
      showError(result.error);
      return;
    }
    setMessageBody("");
    showMsg("协同消息已发送");
    await refreshMessages();
  };

  // === 布局编辑器 ===
  const [seatAssignments, setSeatAssignments] = useState<Record<string, { employee_id?: string | null }>>({});
  const openLayoutEditor = (row: ScreenRow) => {
    if (!canAdmin) return;
    setLayoutEditorScreen(row);
    setSeatAssignments({});
    void refreshLayout();
    setLayoutEditorOpen(true);
  };
  const applySeatAssignment = (seatId: string, employeeId: string) => {
    setSeatAssignments((prev) => ({
      ...prev,
      [seatId]: { employee_id: employeeId || null },
    }));
  };
  const submitLayout = async () => {
    if (!layoutEditorScreen) return;
    setBusy(true);
    setGlobalErr("");
    setGlobalMsg("");
    let failed = 0;
    for (const [seatId, payload] of Object.entries(seatAssignments)) {
      const result = await assignSeat(seatId, {
        employee_id: payload.employee_id ?? null,
      });
      if (!result.ok) failed += 1;
    }
    // 同步保存屏幕草稿（即便没有 seat 变更，也把 layout 引用写入 config）
    const screenResult = await upsertScreen({
      id: layoutEditorScreen.id,
      name: layoutEditorScreen.name,
    });
    setBusy(false);
    if (!screenResult.ok) {
      showError(screenResult.error);
      return;
    }
    if (failed > 0) showMsg(`布局已保存，但有 ${failed} 个座位分配失败`);
    else showMsg(`布局已保存`);
    setLayoutEditorOpen(false);
    await refreshScreens();
    await refreshLayout();
  };

  const seatsFlat = useMemo(() => {
    if (!layout) return [];
    const all: Array<{
      floor_id: string;
      level: number;
      floor_name: string;
      room_id: string;
      room_name: string;
      seat_id: string;
      x: number;
      y: number;
      employee_id?: string | null;
    }> = [];
    for (const floor of layout.floors ?? []) {
      for (const room of floor.rooms ?? []) {
        for (const seat of room.seats ?? []) {
          all.push({
            floor_id: floor.floor_id,
            level: floor.level,
            floor_name: floor.name,
            room_id: room.room_id,
            room_name: room.name,
            seat_id: seat.seat_id,
            x: seat.x,
            y: seat.y,
            employee_id: (seat.agent as Record<string, unknown> | undefined)?.display_name
              ? (seat.agent as Record<string, unknown>).display_name as unknown as string
              : null,
          });
        }
      }
    }
    return all;
  }, [layout]);

  const tabErrors = [screensError, pairsError, messagesError, layoutError].filter(Boolean);

  return (
    <>
      <ConsolePageHeader
        title="协同大屏管理"
        description="协同管理 · 大屏遥控 · 结对协同消息 · 屏幕注册 / 草稿发布 / 聚焦遥控"
        actions={
          canAdmin ? (
            <button
              type="button"
              className="hud-btn text-xs"
              onClick={openCreateScreen}
            >
              + 新建大屏
            </button>
          ) : null
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`rounded border px-2.5 py-1 text-xs ${
              tab === item.key
                ? "border-mint/50 bg-mint/10 text-mint"
                : "border-rail text-mute hover:text-frost"
            }`}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
        <label className="ml-auto text-[11px] text-mute">
          聚焦楼层
          <select
            className="ml-1 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={focusFloor}
            onChange={(event) => setFocusFloor(event.target.value)}
          >
            <option value="">选择楼层</option>
            {(layout?.floors ?? []).map((f) => (
              <option key={f.floor_id} value={f.floor_id}>
                {f.level}F · {f.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {globalErr && <p className="mb-3 text-xs text-flare">{globalErr}</p>}
      {globalMsg && <p className="mb-3 text-xs text-mint">{globalMsg}</p>}
      {tabErrors.length > 0 && !globalErr && (
        <p className="mb-3 text-xs text-amber-signal">{tabErrors.join("；")}</p>
      )}

      {tab === "screens" && (
        <ConsoleSection title={`屏幕列表（${screens.length}）`}>
          <ConsoleTable
            rows={screens}
            rowKey={(row) => row.id}
            loading={screensLoading}
            empty="尚无登记大屏"
            columns={[
              {
                key: "name",
                header: "名称",
                render: (row) => (
                  <span>
                    {row.name}
                    <span className="ml-2 font-mono text-[10px] text-mute">{row.id}</span>
                  </span>
                ),
              },
              { key: "source", header: "来源", render: (row) => <ConsoleTag>{row.source}</ConsoleTag> },
              {
                key: "online",
                header: "状态",
                render: (row) => (
                  <ConsoleTag tone={row.online ? "ok" : "default"}>
                    {row.online ? "在线" : "离线"}
                  </ConsoleTag>
                ),
              },
              { key: "seen", header: "最后心跳", render: (row) => timeText(row.last_seen_at) },
              {
                key: "config",
                header: "配置版本",
                render: (row) => (
                  <span className="font-mono text-[11px]">
                    {row.config_version}
                    {row.published_config_version !== null && (
                      <span className="text-mute"> / 发布 {row.published_config_version}</span>
                    )}
                  </span>
                ),
              },
              {
                key: "draft",
                header: "草稿",
                render: (row) =>
                  row.has_draft ? (
                    <ConsoleTag tone="warn">草稿</ConsoleTag>
                  ) : row.is_published ? (
                    <ConsoleTag tone="ok">已发布</ConsoleTag>
                  ) : (
                    <ConsoleTag>未发布</ConsoleTag>
                  ),
              },
              {
                key: "play",
                header: "Play",
                render: (row) => <ConsoleTag>{PLAY_STATE_LABEL[row.play_state] ?? row.play_state}</ConsoleTag>,
              },
              {
                key: "actions",
                header: "操作",
                render: (row) => (
                  <span className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      disabled={!canAdmin}
                      className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                      onClick={() => openEditScreen(row)}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      disabled={!canAdmin}
                      className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                      onClick={() => openLayoutEditor(row)}
                    >
                      布局
                    </button>
                    <button
                      type="button"
                      disabled={!canAdmin || row.has_draft === false}
                      className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-mint disabled:opacity-40"
                      onClick={() => openPublishConfirm(row)}
                    >
                      发布
                    </button>
                    <button
                      type="button"
                      disabled={!canFocus || !focusFloor}
                      className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                      onClick={() => void submitFocus(row)}
                    >
                      聚焦
                    </button>
                    <button
                      type="button"
                      disabled={!canAdmin}
                      className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-flare disabled:opacity-40"
                      onClick={() => openDeleteConfirm(row)}
                    >
                      删除
                    </button>
                  </span>
                ),
              },
            ]}
          />
        </ConsoleSection>
      )}

      {tab === "pairs" && (
        <ConsoleSection title={`结对管理（${pairs.length}）`}>
          <ConsoleTable
            rows={pairs}
            rowKey={(row) => row.id}
            loading={pairsLoading}
            empty="暂无结对"
            columns={[
              { key: "id", header: "pair_id", render: (row) => <span className="font-mono text-[11px]">{row.id}</span> },
              { key: "initiator", header: "发起方", render: (row) => employeeMap.get(row.initiator_id) ?? row.initiator_id },
              { key: "partner", header: "对方", render: (row) => employeeMap.get(row.partner_id) ?? row.partner_id },
              {
                key: "state",
                header: "状态",
                render: (row) => (
                  <ConsoleTag tone={row.active ? "ok" : "default"}>
                    {PAIR_STATE_LABEL[row.state] ?? row.state}
                  </ConsoleTag>
                ),
              },
              { key: "created", header: "开始", render: (row) => timeText(row.created_at) },
              { key: "ended", header: "结束", render: (row) => timeText(row.ended_at) },
              {
                key: "actions",
                header: "操作",
                render: (row) =>
                  row.active ? (
                    <button
                      type="button"
                      className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-flare"
                      disabled={busy}
                      onClick={() => void submitEndPair(row.id)}
                    >
                      结束
                    </button>
                  ) : null,
              },
            ]}
          />
        </ConsoleSection>
      )}

      {tab === "messages" && (
        <>
          <ConsoleSection
            title="协同消息"
            actions={
              <div className="flex items-center gap-2">
                <label className="text-[11px] text-mute">
                  筛选
                  <select
                    className="ml-1 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                    value={pairFilterId}
                    onChange={(event) => setPairFilterId(event.target.value)}
                  >
                    <option value="">全部结对</option>
                    {pairs.map((p) => (
                      <option key={p.id} value={p.id}>
                        {employeeMap.get(p.initiator_id) ?? p.initiator_id}
                        {" ⇄ "}
                        {employeeMap.get(p.partner_id) ?? p.partner_id}
                        {" · "}
                        {p.id.slice(-8)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            }
          >
            <ConsoleTable
              rows={messages}
              rowKey={(row) => row.id}
              loading={messagesLoading}
              empty="暂无协同消息"
              columns={[
                { key: "time", header: "时间", render: (row) => timeText(row.created_at) },
                { key: "sender", header: "发送方", render: (row) => employeeMap.get(row.sender_id) ?? row.sender_id },
                {
                  key: "recipient",
                  header: "接收方",
                  render: (row) => row.recipient_id ? (employeeMap.get(row.recipient_id) ?? row.recipient_id) : "—",
                },
                {
                  key: "kind",
                  header: "类型",
                  render: (row) => <ConsoleTag>{MESSAGE_KIND_LABEL[row.kind] ?? row.kind}</ConsoleTag>,
                },
                {
                  key: "body",
                  header: "内容",
                  render: (row) => <span className="text-frost/85">{row.body}</span>,
                },
                {
                  key: "status",
                  header: "投递",
                  render: (row) => (
                    <ConsoleTag
                      tone={
                        row.delivery_status === "failed"
                          ? "danger"
                          : row.delivery_status === "pending" || row.delivery_status === "queued"
                            ? "warn"
                            : "ok"
                      }
                    >
                      {DELIVERY_STATUS_LABEL[row.delivery_status ?? ""] ?? row.delivery_status ?? "—"}
                    </ConsoleTag>
                  ),
                },
              ]}
            />
          </ConsoleSection>

          <ConsoleSection title="发送协同消息">
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-[11px] text-mute">
                所属结对
                <select
                  className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                  value={pairFilterId}
                  onChange={(event) => setPairFilterId(event.target.value)}
                >
                  <option value="">选择结对</option>
                  {pairs.map((p) => (
                    <option key={p.id} value={p.id}>
                      {employeeMap.get(p.initiator_id) ?? p.initiator_id}
                      {" ⇄ "}
                      {employeeMap.get(p.partner_id) ?? p.partner_id}
                      {" · "}
                      {p.id.slice(-8)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-[11px] text-mute">
                类型
                <select
                  className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                  value={messageKind}
                  onChange={(event) => setMessageKind(event.target.value)}
                >
                  {Object.entries(MESSAGE_KIND_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </label>
              <label className="flex-1 text-[11px] text-mute">
                内容
                <input
                  className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                  value={messageBody}
                  maxLength={500}
                  disabled={!canSend}
                  placeholder="例如：请协助对接会议室"
                  onChange={(event) => setMessageBody(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="hud-btn text-xs disabled:opacity-40"
                disabled={!canSend || !pairFilterId || !messageBody.trim() || busy}
                onClick={() => void submitSendMessage()}
              >
                发送
              </button>
            </div>
            {!canSend && (
              <p className="mt-2 text-[11px] text-amber-signal">发送消息需要 message_send。</p>
            )}
          </ConsoleSection>
        </>
      )}

      {/* 新建 / 编辑屏幕对话框 */}
      <Dialog
        open={editorOpen}
        title={editorScreen ? `编辑大屏：${editorScreen.name}` : "新建大屏"}
        description={editorScreen ? `当前配置版本 v${editorScreen.config_version}` : "填写基础信息，保存后生成一条草稿"}
        onClose={() => setEditorOpen(false)}
        footer={
          <>
            <button
              type="button"
              className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
              onClick={() => setEditorOpen(false)}
              disabled={busy}
            >
              取消
            </button>
            <button
              type="button"
              className="rounded px-3 py-1.5 text-xs bg-mint text-abyss hover:opacity-90 disabled:opacity-40"
              onClick={() => void submitEditor()}
              disabled={busy || !editorName.trim()}
            >
              {busy ? "保存中…" : "保存草稿"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <label className="block text-[11px] text-mute">
            大屏名称
            <input
              className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
              value={editorName}
              placeholder="例如：一层前台大屏"
              onChange={(event) => setEditorName(event.target.value)}
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-[11px] text-mute">
              Play 状态
              <select
                className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={editorPlayState}
                onChange={(event) => setEditorPlayState(event.target.value as any)}
              >
                <option value="playing">播放中</option>
                <option value="paused">暂停</option>
              </select>
            </label>
            <label className="block text-[11px] text-mute">
              主题
              <select
                className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={editorTheme}
                disabled={editorConfigLoading}
                onChange={(event) => setEditorTheme(event.target.value as ConfigTheme)}
              >
                <option value="auto">跟随系统</option>
                <option value="dark">深色</option>
                <option value="light">浅色</option>
              </select>
            </label>
            <label className="block text-[11px] text-mute">
              布局类型
              <select
                className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={editorLayoutType}
                disabled={editorConfigLoading}
                onChange={(event) => setEditorLayoutType(event.target.value as ConfigLayoutType)}
              >
                <option value="office">办公室</option>
                <option value="grid">网格</option>
                <option value="custom">自定义</option>
              </select>
            </label>
            <label className="block text-[11px] text-mute">
              分辨率
              <select
                className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={editorResolution}
                disabled={editorConfigLoading}
                onChange={(event) => setEditorResolution(event.target.value as ConfigResolution)}
              >
                <option value="1920x1080">1920 × 1080</option>
                <option value="3840x2160">3840 × 2160</option>
              </select>
            </label>
          </div>
          <p className="text-[11px] text-mute">
            主题与 Play 状态在公开孪生大屏生效；布局类型决定渲染方式。保存后需点击「发布」才会在 /twin 端看到。
          </p>
        </div>
      </Dialog>

      {/* 发布确认 */}
      <ConfirmDialog
        open={publishConfirmOpen}
        title={`发布草稿：${publishTarget?.name ?? ""}`}
        description={
          publishTarget
            ? `将 v${publishTarget.config_version} 的草稿配置提升为发布版本；之前的发布版本为 ${publishTarget.published_config_version ?? "从未发布"}。`
            : null
        }
        busy={busy}
        onConfirm={() => void submitPublish()}
        onCancel={() => {
          setPublishConfirmOpen(false);
          setPublishTarget(null);
        }}
      />

      {/* 删除确认 */}
      <ConfirmDialog
        open={deleteConfirmOpen}
        danger
        title={`删除大屏：${deleteTarget?.name ?? ""}`}
        description={
          deleteTarget
            ? `屏幕 ${deleteTarget.id} 的登记、心跳与所有公开会话会立即断开；草稿配置也会一并移除。`
            : null
        }
        busy={busy}
        confirmLabel="删除"
        onConfirm={() => void submitDelete()}
        onCancel={() => {
          setDeleteConfirmOpen(false);
          setDeleteTarget(null);
        }}
      />

      {/* 布局编辑器 */}
      <Dialog
        open={layoutEditorOpen}
        title={`布局编辑器：${layoutEditorScreen?.name ?? ""}`}
        description="Canvas 显示公开布局的 Seat 网格，每个 seat 可分配员工。保存时 PUT /api/seats/{id}/assign + PATCH 屏幕草稿。"
        onClose={() => {
          if (!busy) setLayoutEditorOpen(false);
        }}
        width={960}
        footer={
          <>
            <button
              type="button"
              className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
              onClick={() => setLayoutEditorOpen(false)}
              disabled={busy}
            >
              取消
            </button>
            <button
              type="button"
              className="rounded px-3 py-1.5 text-xs bg-mint text-abyss hover:opacity-90 disabled:opacity-40"
              onClick={() => void submitLayout()}
              disabled={busy || seatsFlat.length === 0}
            >
              {busy ? "保存中…" : `保存布局（${Object.keys(seatAssignments).length} 处变更）`}
            </button>
          </>
        }
      >
        {layoutLoading ? (
          <p className="text-xs text-mute">加载公开布局中…</p>
        ) : layoutError ? (
          <p className="text-xs text-flare">{layoutError}</p>
        ) : !layout ? (
          <p className="text-xs text-mute">暂无公开布局数据</p>
        ) : (
          <div className="max-h-[520px] overflow-auto rounded border border-rail bg-abyss/40 p-3">
            {layout.floors.map((floor) => (
              <div key={floor.floor_id} className="mb-4 last:mb-0">
                <p className="mb-2 text-[11px] uppercase tracking-wider text-mute">
                  {floor.level}F · {floor.name}
                </p>
                {floor.rooms.map((room) => (
                  <div key={room.room_id} className="mb-2 rounded border border-rail/50 bg-hull/30 p-2">
                    <p className="mb-1 text-[11px] text-frost/80">
                      {room.name} · {room.seats.length} seat
                    </p>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                      {room.seats.map((seat) => {
                        const assignment = seatAssignments[seat.seat_id];
                        const currentEmployeeId =
                          assignment?.employee_id ??
                          (typeof (seat.agent as Record<string, unknown> | undefined)?.display_name === "string"
                            ? (seat.agent as Record<string, unknown>)["employee_id"] as unknown as string
                            : "");
                        return (
                          <div
                            key={seat.seat_id}
                            className="rounded border border-rail bg-hull/60 p-2"
                          >
                            <p className="mb-1 font-mono text-[10px] text-mute">{seat.seat_id}</p>
                            <label className="block text-[11px] text-mute">
                              员工
                              <select
                                className="mt-1 block w-full rounded border border-rail bg-abyss/50 px-1.5 py-1 text-xs text-frost"
                                value={assignment !== undefined
                                  ? (assignment.employee_id ?? "")
                                  : currentEmployeeId ?? ""}
                                onChange={(event) => applySeatAssignment(seat.seat_id, event.target.value)}
                              >
                                <option value="">（空位）</option>
                                {employees.map((e) => (
                                  <option key={e.id} value={e.id}>
                                    {e.displayName}
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </Dialog>
    </>
  );
}

const KEY = "mailbus.lang";

export type Lang = "zh" | "en";

const dict = {
  zh: {
    home: "指挥摘要",
    tasks: "任务",
    audit: "审计",
    human: "人机",
    agents: "智能体员工",
    llm: "智能体",
    agent: "智能体",
    integrations: "集成",
    bus: "总线",
    clinic: "诊所",
    other: "其它",
    cruise: "巡航",
    close: "关闭",
    intake: "商前",
    workflows: "Workflow",
    content: "内容",
    pipeline: "流水线",
    inbox: "Inbox",
    bulletin: "公告",
    stats: "统计",
    patrol: "巡检",
    alerts: "告警",
    reviews: "Reviews",
    avatarPending: "头像齐套中",
    avatarPendingHint: "需 13 人静态肖像 + 同源动态图全部过目后启用智能体员工",
    lang: "语言",
    mute: "静音",
    charge: "蓄力",
    editTip: "拖动热点调整位置；右下角缩放",
    gear: "齿轮",
    legacyUi: "旧壳",
    cockpitUi: "舰桥",
    booting: "舰桥启动中…",
    exitCalibrate: "退出校准",
    saveHotspots: "保存热点",
    resetHotspots: "重置热点",
    copyJson: "复制 JSON",
    popupBlocked: "（弹窗被拦截）",
    avatarChecking: "头像检查中…",
    rosterLoading: "名册加载中…",
    rosterEmpty: "名册为空",
    rosterSyncHint: "正在同步头像与名册",
    rosterRetryHint: "可点击刷新重试",
    refresh: "刷新",
    orbitFilterAll: "全部",
    orbitEmpty: "暂无匹配的智能体员工",
  },
  en: {
    home: "Command",
    tasks: "Tasks",
    audit: "Audit",
    human: "Human",
    agents: "Crew",
    llm: "Agent",
    agent: "Agent",
    integrations: "Integrations",
    bus: "Bus",
    clinic: "Clinic",
    other: "More",
    cruise: "Cruise",
    close: "Close",
    intake: "Intake",
    workflows: "Workflows",
    content: "Content",
    pipeline: "Pipeline",
    inbox: "Inbox",
    bulletin: "Bulletin",
    stats: "Stats",
    patrol: "Patrol",
    alerts: "Alerts",
    reviews: "Reviews",
    avatarPending: "Avatars pending",
    avatarPendingHint: "Orbit unlocks after 13 static+animated pairs pass review",
    lang: "Language",
    mute: "Mute",
    charge: "Charge",
    editTip: "Drag hotspots; resize from corner",
    gear: "Gear",
    legacyUi: "Legacy",
    cockpitUi: "Cockpit",
    booting: "Booting…",
    exitCalibrate: "Exit calibrate",
    saveHotspots: "Save hotspots",
    resetHotspots: "Reset hotspots",
    copyJson: "Copy JSON",
    popupBlocked: " (popup blocked)",
    avatarChecking: "Checking avatars…",
    rosterLoading: "Loading roster…",
    rosterEmpty: "Roster empty",
    rosterSyncHint: "Syncing avatars & roster",
    rosterRetryHint: "Retry with refresh",
    refresh: "Refresh",
    orbitFilterAll: "All",
    orbitEmpty: "No matching crew",
  },
} as const;

export type I18nKey = keyof (typeof dict)["zh"];

export function getLang(): Lang {
  const v = localStorage.getItem(KEY);
  return v === "en" ? "en" : "zh";
}

export function setLang(lang: Lang) {
  localStorage.setItem(KEY, lang);
}

export function t(key: I18nKey, lang: Lang = getLang()): string {
  return dict[lang][key] || dict.zh[key] || key;
}

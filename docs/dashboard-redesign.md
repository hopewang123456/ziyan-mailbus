# mailbus Dashboard 重设计 v2 — AI 科技感方案

> 设计方向：冷色调 · AI 未来感 · 炫光动效 · 产品级质感

---

## 整体视觉感受

参考方向：
- **Vercel 仪表盘** — 干净、深色、数据驱动
- **Blade Runner 2049 界面** — 冷蓝紫光晕、全息感
- **钢铁侠 Jarvis 界面** — 蓝色发光线条、动态数据流

第一眼印象：**这不是 demo，这是在太空站监控 AI 舰队。**

---

## 1+. 宇宙元素设计

### 背景点缀

- 背景中加入微弱的**星系粒子**（CSS 动画小圆点随机分布，缓慢旋转）
- 页面角落加上**星座连线**（SVG 线条，透明度极低，不影响阅读）
- 页面底部有一个微弱的**银河光带**（横向渐变条，类似 `radial-gradient` 模拟银河）

### 导航栏

- 顶部左侧用一个小行星图标 + "mailbus" 文字
- 选中的导航项可以加一个微弱的**轨道环动画**（绕着图标转的虚线圆环）

### 加载动画

- 用旋转的**星云脉冲环**代替普通 spinner
- 空态页显示一颗暗淡的**孤独星球** + "暂无数据"

### 卡片装饰

- Agent 卡片右上角加一个微弱的**星座符号**（每个 agent 不同星座？或统一用六芒星）
- 数据指标卡的数字下方有一条**星轨线**（横向渐变细线）

### 宇宙飞船元素

- **导航栏 Logo**：用一个小型宇宙飞船/卫星图标（SVG），取代纯文字 Logo
- **加载动画**：飞船在星空中飞行的轨迹线（细线从右向左划过），代替传统 spinner
- **空态页**：显示一艘停在星空中的小飞船 + "航行中，暂无数据"
- **底部状态栏**：左侧放一个飞船图标，右侧显示"系统运行中 · 第 X 天"

```svg
<!-- 飞船 SVG 图标 — 简洁线条风格 -->
<svg viewBox="0 0 24 24" width="20" height="20">
  <path d="M12 2L3 20h18L12 2z" fill="none" stroke="currentColor" stroke-width="1.5"/>
  <circle cx="12" cy="14" r="2" fill="none" stroke="currentColor" stroke-width="1.5"/>
</svg>
```

### 赛博元素

- **字体微调**：数值和状态标签使用类似赛博风格的等宽字体（JetBrains Mono 已符合）
- **边框发光**：成功/失败状态标签使用**霓虹灯管效果**（text-shadow 多层发光）
- **扫描线**：Agent 详情弹窗背景加极淡的 CRT 扫描线纹理（可选，通过 CSS repeating-linear-gradient）
- **矩阵数字雨**：loading 时在背景显示极淡的绿色数字雨效果（仅限 loading 态，非常克制）

```css
/* 霓虹灯管文字效果 — 用在状态标签上 */
.neon-cyan {
  color: var(--accent-cyan);
  text-shadow:
    0 0 4px rgba(0, 212, 255, 0.4),
    0 0 12px rgba(0, 212, 255, 0.2),
    0 0 24px rgba(0, 212, 255, 0.1);
}

.neon-green {
  color: var(--accent-green);
  text-shadow:
    0 0 4px rgba(16, 185, 129, 0.4),
    0 0 12px rgba(16, 185, 129, 0.2);
}

.neon-red {
  color: var(--accent-red);
  text-shadow:
    0 0 4px rgba(239, 68, 68, 0.4),
    0 0 12px rgba(239, 68, 68, 0.2);
}
```

```css
/* CRT 扫描线 — 仅在弹窗背景使用，极淡 */
.crt-overlay {
  background-image: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0, 0, 0, 0.03) 2px,
    rgba(0, 0, 0, 0.03) 4px
  );
}
```

### 机器人元素

- **Agent 头像**：每个 agent 的图标从 emoji 改为简洁的**机器人头像 SVG**（不同颜色代表不同角色）
- **mailbus 自身 Logo**：用一个机器人头部 + 天线 + 发光眼睛的图标
- **错误提示**：在错误信息旁加一个🤖表情或机器人 SVG 图标，弱化错误带来的负面情绪

```svg
<!-- 机器人头部 SVG — 简洁风格 -->
<svg viewBox="0 0 24 24" width="18" height="18">
  <rect x="4" y="6" width="16" height="12" rx="3" fill="none" stroke="currentColor" stroke-width="1.5"/>
  <circle cx="9" cy="12" r="1.5" fill="currentColor"/>
  <circle cx="15" cy="12" r="1.5" fill="currentColor"/>
  <rect x="7" y="3" width="2" height="4" rx="1" fill="none" stroke="currentColor" stroke-width="1"/>
  <rect x="15" y="3" width="2" height="4" rx="1" fill="none" stroke="currentColor" stroke-width="1"/>
  <line x1="10" y1="16" x2="14" y2="16" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
</svg>
```

### 未来世界元素

- **全息投影效果**：弹窗和重要数据卡片加极淡的**全息网格线**（CSS 网格背景，透明度 0.03），模拟全息投影界面
- **数据流动线**：总览页的数据指标卡之间加微弱的**流动光线条**连接（CSS 动画虚线流动），模拟数据在太空中传输
- **脉冲扫描环**：Agent 在线状态图标用**脉冲扩散环动画**（类似雷达扫描），不在线时静止
- **浮空数据标签**：鼠标 hover 数据指标卡时，数值上方出现一个**浮空的标签**（向上飘 + 淡入），模拟 AR 数据叠加
- **能量护盾边框**：重要弹窗（如确认上线、警告）的边框使用**动态流光效果**（渐变背景 + background-position 动画）

```css
/* 全息投影网格 — 弹窗背景 */
.hologrid {
  background-image: 
    linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
}

/* 数据流动线 — 连接卡片 */
.data-flow {
  position: absolute;
  height: 1px;
  background: linear-gradient(90deg, 
    transparent, 
    rgba(0, 212, 255, 0.15), 
    transparent);
  animation: dataPulse 2s ease-in-out infinite;
}

@keyframes dataPulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.8; }
}

/* 脉冲扫描环 — 在线状态 */
.pulse-ring {
  position: relative;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-green);
}

.pulse-ring::before {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1px solid rgba(16, 185, 129, 0.3);
  animation: pulseExpand 2s ease-out infinite;
}

@keyframes pulseExpand {
  0% { transform: scale(1); opacity: 0.8; }
  100% { transform: scale(2.5); opacity: 0; }
}

/* 能量护盾流光边框 */
.energy-shield {
  position: relative;
  border: 1px solid transparent;
  background-clip: padding-box;
}

.energy-shield::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  padding: 1px;
  background: linear-gradient(
    90deg, 
    rgba(0, 212, 255, 0.2), 
    rgba(139, 92, 246, 0.2), 
    rgba(0, 212, 255, 0.2)
  );
  -webkit-mask: 
    linear-gradient(#fff 0 0) content-box, 
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  background-size: 200% 100%;
  animation: shieldFlow 3s linear infinite;
}

@keyframes shieldFlow {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

### AR 数据叠加效果

```css
/* 浮空数据标签 — hover 时出现 */
.data-label-float {
  opacity: 0;
  transform: translateY(8px);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.card:hover .data-label-float {
  opacity: 1;
  transform: translateY(0);
}
```

### 注意事项

- 未来世界元素只用在**关键交互点**（弹窗、hover、状态切换），不是全屏滥用
- 所有动效控制在 0.2~0.3 秒，流畅不拖沓
- 全息网格、数据流动线、能量护盾等**默认透明度不高于 0.05**，hover/激活时提高到 0.15
- **性能意识**：动效优先使用 CSS（GPU 加速），避免 JS 频繁操作 DOM

### 注意事项

- **所有宇宙元素必须非常克制** — 透明度控制在 0.03~0.15 之间
- 赛博元素只在关键状态标签上使用（不滥用霓虹灯管效果）
- 扫描线和数字雨默认关闭，只在弹窗/loading 时可选启用
- 机器人和飞船用**简洁线条 SVG**，不要复杂插画，保持现代感
- 三层叠加：**星系背景（底）→ 鼠标炫光（中）→ 毛玻璃卡片（顶）**，效果深邃高级不刺眼

---

## 1. 配色系统（冷色调）

```css
/* 主背景 — 深邃星空 */
--bg-deep:        #050510    /* 极深蓝黑 — 主背景 */
--bg-surface:     #0a0a1a    /* 深空蓝 — 表面层 */
--bg-card:        #0f172a    /* 卡片背景（半透明） */
--bg-card-hover:  #1a1a3e    /* 卡片 hover — 带紫调 */

/* 文字 */
--text-primary:   #e0e6f0    /* 主文字 — 冷白 */
--text-secondary: #8892b0    /* 辅助文字 — 灰蓝 */
--text-muted:     #4a5578    /* 弱化文字 */

/* 科技感强调色 */
--accent-cyan:    #00d4ff    /* 亮青 — 主要交互色 */
--accent-blue:    #3b82f6    /* 蓝 — 信息/链接 */
--accent-purple:  #8b5cf6    /* 紫 — 审计/特殊 */
--accent-green:   #10b981    /* 绿 — 成功 */
--accent-red:     #ef4444    /* 红 — 失败 */
--accent-gold:    #f59e0b    /* 金 — 告警 */

/* 发光色 */
--glow-cyan:      rgba(0, 212, 255, 0.15)
--glow-purple:    rgba(139, 92, 246, 0.12)
--glow-blue:      rgba(59, 130, 246, 0.1)

/* 边框 */
--border:         rgba(51, 65, 85, 0.3)
--border-active:  rgba(0, 212, 255, 0.5)
```

---

## 2. 背景（关键！）

**不使用纯色或简单渐变。** 用多层背景叠加实现深邃感：

```css
body {
  background: #050510;
}

body::before {
  content: '';
  position: fixed; inset: 0;
  z-index: 0;
  pointer-events: none;
  
  /* 第一层：深空渐变 */
  background: 
    radial-gradient(ellipse 100% 60% at 50% 0%, 
      rgba(0, 100, 200, 0.08) 0%, transparent 60%),
    radial-gradient(ellipse 80% 50% at 80% 100%, 
      rgba(100, 0, 200, 0.06) 0%, transparent 50%),
    radial-gradient(ellipse 60% 40% at 20% 80%, 
      rgba(0, 200, 255, 0.04) 0%, transparent 40%);
}
```

这会产生一种**深邃的 AI 空间感**——类似星际穿越里的五维空间那种深蓝紫渐变。

---

## 3. 炫光动效（鼠标跟随）

**核心炫技点：** 鼠标移动时，背景有一个柔和的光晕跟随，类似 Javis 界面。

```css
/* 炫光跟随层 — 通过 JS 更新 transform */
.glow-follow {
  position: fixed;
  width: 600px;
  height: 600px;
  border-radius: 50%;
  background: radial-gradient(circle, 
    rgba(0, 150, 255, 0.06) 0%, 
    rgba(100, 0, 255, 0.03) 40%, 
    transparent 70%);
  pointer-events: none;
  z-index: 0;
  transform: translate(-50%, -50%);
  transition: transform 0.1s ease-out;
}
```

```javascript
// JS — 鼠标移动时更新炫光位置
document.addEventListener('mousemove', (e) => {
  const glow = document.querySelector('.glow-follow');
  if (glow) {
    glow.style.left = e.clientX + 'px';
    glow.style.top = e.clientY + 'px';
  }
});
```

效果：鼠标移到哪里，哪里就有淡淡的蓝紫光晕跟随，科技感拉满。

---

## 4. 导航栏

**左侧固定导航 + 顶部状态条**

```
┌──────────────────────────────────────────────────┐
│  ◉  ziyan-mailbus                     🔔 3  ⚙️ │  ← 顶栏
├──────────┬───────────────────────────────────────┤
│          │                                       │
│  ⬡ 状态  │                                       │
│  ⬡ Agent│                                       │
│  ⬡ 消息  │         主体内容区域                   │
│  ⬡ 审计  │         毛玻璃卡片                     │
│  ⬡ 公告  │         冷蓝光晕边框                   │
│  ⬡ 健康  │                                       │
│  ⬡ 告警  │                                       │
│          │                                       │
│ ──────── │                                       │
│ ⚡ 系统   │                                       │
│    运行中 │                                       │
└──────────┴───────────────────────────────────────┘
```

左侧导航宽度：220px。每个导航项：
- hover 时左侧有青色发光边框（2px, box-shadow 发光）
- 选中项有背景色变化 + 发光边框常亮
- 图标用简洁的 SVG 线条图标（类似 Vercel 风格），不是 emoji

---

## 5. 卡片样式

```css
.card {
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(51, 65, 85, 0.3);
  border-radius: 12px;
  padding: 16px;
  
  /* 多层阴影 */
  box-shadow: 
    0 4px 24px rgba(0, 0, 0, 0.2),
    0 1px 0 rgba(255, 255, 255, 0.03) inset;
  
  /* 上浮效果 */
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.card:hover {
  border-color: rgba(0, 212, 255, 0.3);
  box-shadow: 
    0 8px 40px rgba(0, 0, 0, 0.3),
    0 0 20px rgba(0, 212, 255, 0.05);
  transform: translateY(-2px);
}
```

---

## 6. 数据指标卡（总览页）

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  📨          │  │  ✅          │  │  ⏳          │  │  ⚡          │
│  消息总数     │  │  已完成      │  │  处理中      │  │  系统负载     │
│  1,284       │  │  1,142       │  │  37          │  │  23%         │
│  ↑ 12% 本周  │  │  ↑ 8%       │  │  ↓ 3%       │  │  ● 正常      │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

数字使用 `font-mono`（等宽字体），大号显示。
趋势箭头用青色（↑）或红色（↓）。
卡片背景颜色与指标类型关联：消息=蓝、成功=绿、待处理=金、负载=紫。

---

## 7. 按钮样式

```css
.btn {
  background: rgba(30, 41, 59, 0.8);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(51, 65, 85, 0.4);
  border-radius: 8px;
  padding: 8px 16px;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

.btn:hover {
  border-color: rgba(0, 212, 255, 0.4);
  box-shadow: 0 0 16px rgba(0, 212, 255, 0.1);
  transform: translateY(-1px);
}

.btn:active {
  transform: translateY(0);
}

/* 主要操作按钮（青色） */
.btn-primary {
  background: rgba(0, 212, 255, 0.15);
  border-color: rgba(0, 212, 255, 0.3);
  color: var(--accent-cyan);
}

.btn-primary:hover {
  background: rgba(0, 212, 255, 0.25);
  border-color: rgba(0, 212, 255, 0.5);
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.2);
}
```

---

## 8. 弹窗（Modal）

```css
.modal {
  background: rgba(5, 5, 16, 0.8);
  backdrop-filter: blur(8px);
}

.modal-inner {
  background: rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(51, 65, 85, 0.4);
  border-radius: 16px;
  box-shadow: 
    0 24px 80px rgba(0, 0, 0, 0.5),
    0 0 40px rgba(0, 212, 255, 0.05);
}
```

---

## 9. 加载 / 空态 / 错误态

| 状态 | 设计 |
|------|------|
| 加载中 | 青色脉冲环（类似 iOS 加载） |
| 空态 | 中间显示图标 + 灰色提示文字 |
| 错误 | 红色边框卡片 + 重试按钮 |
| Toast | 从右上滑入，青色左边框 |

---

## 10. 实施顺序

1. CSS 变量 + 背景（炫光渐变）
2. 鼠标跟随炫光动效
3. 导航栏改装（左侧）
4. 卡片样式（毛玻璃）
5. 按钮样式统一
6. 数据指标卡（总览页）
7. 弹窗/Toast 样式统一
8. 动效收尾

---

## 11. 验收标准

□ 打开 dashboard，第一眼感觉是"这起码是个正经产品"
□ 背景有深邃的蓝紫渐变，不是纯色
□ 鼠标移动时有炫光跟随
□ 卡片是毛玻璃效果，hover 有发光边框
□ 导航在左侧，选中项有青色发光
□ 按钮 hover 有发光效果
□ 所有原有功能正常
□ 配色统一使用冷色调设计系统 token

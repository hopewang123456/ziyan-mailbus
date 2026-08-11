# Cockpit (Vite + React + Tailwind)

星舰驾驶舱 SPA。`npm run build` 产出 `dist/`，由 mailbus API `_serve_static` 优先挂在 `/`；旧 docs HUD 走 `/legacy`。

```bash
cd web
npm install
npm run dev    # :5173，代理 /api → :9814
npm run build  # → web/dist
```

设计：星系/舰桥 HUD（cyan + amber on void），品牌 **ziyan-mailbus** 为首屏英雄信号。HashRouter，免改后端深链。

#!/usr/bin/env node
/**
 * 代理 codexapp：将 projectless「New Chat」重定向到 agent 工作区，避免丢失人设。
 * 须转发 WebSocket（/codex-api/ws），否则浏览器经 9240/9241 打开 UI 后对话会 Failed to fetch。
 */
import http from "node:http";
import net from "node:net";

const projectDir = (process.env.CODEX_PROJECT_DIR || "").trim();
const internalPort = (process.env.CODEX_UI_INTERNAL_PORT || "17681").trim();
const listenPort = (process.env.CODEX_UI_PORT || "7681").trim();

if (!projectDir) {
  console.error("[codex-ui-proxy] CODEX_PROJECT_DIR is required");
  process.exit(1);
}

function proxyRequest(req, res) {
  const headers = { ...req.headers, host: `127.0.0.1:${internalPort}` };
  const upstream = http.request(
    {
      hostname: "127.0.0.1",
      port: Number(internalPort),
      path: req.url,
      method: req.method,
      headers,
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode ?? 502, upstreamRes.headers);
      upstreamRes.pipe(res);
    },
  );
  upstream.on("error", (err) => {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: String(err.message || err) }));
  });
  req.pipe(upstream);
}

function proxyWebSocketUpgrade(req, clientSocket, head) {
  const path = req.url || "";
  if (!path.startsWith("/codex-api/ws")) {
    clientSocket.destroy();
    return;
  }
  const upstream = net.connect(
    { port: Number(internalPort), host: "127.0.0.1" },
    () => {
      const lines = [`${req.method} ${path} HTTP/1.1`];
      for (const [key, value] of Object.entries(req.headers)) {
        if (value === undefined) continue;
        if (Array.isArray(value)) {
          for (const v of value) lines.push(`${key}: ${v}`);
        } else {
          lines.push(`${key}: ${value}`);
        }
      }
      // 上游 codexapp 只监听 loopback，Host 须对齐 internalPort
      const hostIdx = lines.findIndex((l) => l.toLowerCase().startsWith("host:"));
      const hostLine = `Host: 127.0.0.1:${internalPort}`;
      if (hostIdx >= 0) lines[hostIdx] = hostLine;
      else lines.push(hostLine);
      upstream.write(`${lines.join("\r\n")}\r\n\r\n`);
      if (head.length) upstream.write(head);
      upstream.pipe(clientSocket);
      clientSocket.pipe(upstream);
    },
  );
  const destroyBoth = () => {
    upstream.destroy();
    clientSocket.destroy();
  };
  upstream.on("error", destroyBoth);
  clientSocket.on("error", destroyBoth);
}

const server = http.createServer((req, res) => {
  if (req.method === "POST" && req.url === "/codex-api/projectless-thread-cwd") {
    const body = JSON.stringify({
      data: {
        cwd: projectDir,
        outputDirectory: projectDir,
        workspaceRoot: projectDir,
      },
    });
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(body);
    return;
  }
  proxyRequest(req, res);
});

server.on("upgrade", proxyWebSocketUpgrade);

server.listen(Number(listenPort), "0.0.0.0", () => {
  console.error(
    `[codex-ui-proxy] :${listenPort} -> :${internalPort} project=${projectDir}`,
  );
});

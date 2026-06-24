#!/usr/bin/env node

// src/cli/index.ts
import { createServer as createServer2 } from "http";
import { chmodSync as chmodSync2, createWriteStream, existsSync as existsSync7, mkdirSync as mkdirSync2 } from "fs";
import { readFile as readFile5, stat as stat7, writeFile as writeFile6 } from "fs/promises";
import { homedir as homedir7, networkInterfaces } from "os";
import { isAbsolute as isAbsolute4, join as join10, resolve as resolve3 } from "path";
import { spawn as spawn5 } from "child_process";
import { createInterface as createInterface2 } from "readline/promises";
import { fileURLToPath as fileURLToPath2 } from "url";
import { dirname as dirname6 } from "path";
import { get as httpsGet } from "https";
import { Command } from "commander";
import qrcode from "qrcode-terminal";

// src/commandResolution.ts
import { spawnSync } from "child_process";
import { existsSync } from "fs";
import { homedir } from "os";
import { delimiter, join } from "path";
function uniqueStrings(values) {
  const unique = [];
  for (const value of values) {
    const normalized = value?.trim();
    if (!normalized || unique.includes(normalized)) continue;
    unique.push(normalized);
  }
  return unique;
}
function isPathLike(command) {
  return command.includes("/") || command.includes("\\") || /^[a-zA-Z]:/.test(command);
}
function isRunnableCommand(command, args = []) {
  if (isPathLike(command) && !existsSync(command)) {
    return false;
  }
  return canRunCommand(command, args);
}
function getWindowsAppDataNpmPrefix() {
  const appData = process.env.APPDATA?.trim();
  return appData ? join(appData, "npm") : null;
}
function getPotentialNpmPrefixes() {
  return uniqueStrings([
    process.env.npm_config_prefix,
    process.env.PREFIX,
    getUserNpmPrefix(),
    process.platform === "win32" ? getWindowsAppDataNpmPrefix() : null
  ]);
}
function getPotentialCodexPackageDirs(prefix) {
  const dirs = [join(prefix, "node_modules", "@openai", "codex")];
  if (process.platform !== "win32") {
    dirs.push(join(prefix, "lib", "node_modules", "@openai", "codex"));
  }
  return dirs;
}
function getPotentialCodexExecutables(prefix) {
  return getPotentialCodexPackageDirs(prefix).map((packageDir) => process.platform === "win32" ? join(
    packageDir,
    "node_modules",
    "@openai",
    "codex-win32-x64",
    "vendor",
    "x86_64-pc-windows-msvc",
    "codex",
    "codex.exe"
  ) : join(packageDir, "bin", "codex"));
}
function getPotentialRipgrepExecutables(prefix) {
  return getPotentialCodexPackageDirs(prefix).map((packageDir) => process.platform === "win32" ? join(
    packageDir,
    "node_modules",
    "@openai",
    "codex-win32-x64",
    "vendor",
    "x86_64-pc-windows-msvc",
    "path",
    "rg.exe"
  ) : join(packageDir, "bin", "rg"));
}
function canRunCommand(command, args = []) {
  const result = spawnSync(command, args, {
    stdio: "ignore",
    windowsHide: true
  });
  return !result.error && result.status === 0;
}
function getUserNpmPrefix() {
  return join(homedir(), ".npm-global");
}
function getNpmGlobalBinDir(prefix) {
  return process.platform === "win32" ? prefix : join(prefix, "bin");
}
function prependPathEntry(existingPath, entry) {
  const normalizedEntry = entry.trim();
  if (!normalizedEntry) return existingPath;
  const parts = existingPath.split(delimiter).map((value) => value.trim()).filter(Boolean);
  if (parts.includes(normalizedEntry)) {
    return existingPath;
  }
  return existingPath ? `${normalizedEntry}${delimiter}${existingPath}` : normalizedEntry;
}
function resolveCodexCommand() {
  const explicit = process.env.CODEXUI_CODEX_COMMAND?.trim();
  const packageCandidates = getPotentialNpmPrefixes().flatMap(getPotentialCodexExecutables);
  const fallbackCandidates = process.platform === "win32" ? [...packageCandidates, "codex"] : ["codex", ...packageCandidates];
  for (const candidate of uniqueStrings([explicit, ...fallbackCandidates])) {
    if (isRunnableCommand(candidate, ["--version"])) {
      return candidate;
    }
  }
  return null;
}
function resolveRipgrepCommand() {
  const explicit = process.env.CODEXUI_RG_COMMAND?.trim();
  const packageCandidates = getPotentialNpmPrefixes().flatMap(getPotentialRipgrepExecutables);
  const fallbackCandidates = process.platform === "win32" ? [...packageCandidates, "rg"] : ["rg", ...packageCandidates];
  for (const candidate of uniqueStrings([explicit, ...fallbackCandidates])) {
    if (isRunnableCommand(candidate, ["--version"])) {
      return candidate;
    }
  }
  return null;
}

// src/server/appServerRuntimeConfig.ts
var SANDBOX_MODES = /* @__PURE__ */ new Set([
  "read-only",
  "workspace-write",
  "danger-full-access"
]);
var APPROVAL_POLICIES = /* @__PURE__ */ new Set([
  "untrusted",
  "on-failure",
  "on-request",
  "never"
]);
var DEFAULT_RUNTIME_CONFIG = {
  sandboxMode: "danger-full-access",
  approvalPolicy: "never",
  memories: true
};
function normalizeRuntimeValue(value) {
  return value?.trim().toLowerCase() ?? "";
}
function readSandboxModeFromEnv() {
  const candidate = normalizeRuntimeValue(process.env.CODEXUI_SANDBOX_MODE);
  if (SANDBOX_MODES.has(candidate)) {
    return candidate;
  }
  return DEFAULT_RUNTIME_CONFIG.sandboxMode;
}
function readApprovalPolicyFromEnv() {
  const candidate = normalizeRuntimeValue(process.env.CODEXUI_APPROVAL_POLICY);
  if (APPROVAL_POLICIES.has(candidate)) {
    return candidate;
  }
  return DEFAULT_RUNTIME_CONFIG.approvalPolicy;
}
function readMemoriesFromEnv() {
  const candidate = normalizeRuntimeValue(process.env.CODEXUI_MEMORIES);
  if (candidate === "false" || candidate === "0" || candidate === "no") {
    return false;
  }
  if (candidate === "true" || candidate === "1" || candidate === "yes") {
    return true;
  }
  return DEFAULT_RUNTIME_CONFIG.memories;
}
function resolveAppServerRuntimeConfig() {
  return {
    sandboxMode: readSandboxModeFromEnv(),
    approvalPolicy: readApprovalPolicyFromEnv(),
    memories: readMemoriesFromEnv()
  };
}
function buildAppServerArgs() {
  const config = resolveAppServerRuntimeConfig();
  return [
    "app-server",
    "-c",
    `approval_policy="${config.approvalPolicy}"`,
    "-c",
    `sandbox_mode="${config.sandboxMode}"`,
    "-c",
    `features.memories=${config.memories ? "true" : "false"}`
  ];
}
function parseSandboxMode(value) {
  const candidate = value.trim().toLowerCase();
  return SANDBOX_MODES.has(candidate) ? candidate : null;
}
function parseApprovalPolicy(value) {
  const candidate = value.trim().toLowerCase();
  return APPROVAL_POLICIES.has(candidate) ? candidate : null;
}

// src/server/httpServer.ts
import { fileURLToPath } from "url";
import { dirname as dirname5, extname as extname3, isAbsolute as isAbsolute3, join as join9 } from "path";
import { existsSync as existsSync6 } from "fs";
import { writeFile as writeFile5, stat as stat6 } from "fs/promises";
import express from "express";

// src/server/codexAppServerBridge.ts
import { spawn as spawn4, spawnSync as spawnSync4 } from "child_process";
import { createHash as createHash2, randomBytes } from "crypto";
import { mkdtemp as mkdtemp3, readFile as readFile3, readdir as readdir2, rename, rm as rm4, mkdir as mkdir4, stat as stat4, lstat as lstat2 } from "fs/promises";
import { createReadStream as createReadStream2, existsSync as existsSync4, readFileSync as readFileSync2 } from "fs";
import { request as httpRequest2 } from "http";
import { request as httpsRequest2 } from "https";
import { homedir as homedir5 } from "os";
import { tmpdir as tmpdir4 } from "os";
import { basename as basename4, dirname as dirname2, isAbsolute as isAbsolute2, join as join6, resolve as resolve2 } from "path";
import { createInterface } from "readline";
import { writeFile as writeFile4 } from "fs/promises";

// src/server/accountRoutes.ts
import { spawn } from "child_process";
import { createHash } from "crypto";
import { mkdtemp, mkdir, readFile, rm, stat, writeFile } from "fs/promises";
import { homedir as homedir2, tmpdir } from "os";
import { join as join2 } from "path";

// src/server/rateLimitDecodeRecovery.ts
function asRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function readString(value) {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}
function readBoolean(value) {
  return typeof value === "boolean" ? value : null;
}
function readNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function getErrorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}
function parseJsonObjectAt(text, startIndex) {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = startIndex; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }
    if (char === '"') {
      inString = true;
      continue;
    }
    if (char === "{") {
      depth += 1;
      continue;
    }
    if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return JSON.parse(text.slice(startIndex, index + 1));
      }
    }
  }
  return null;
}
function extractResponseBodyFromDecodeError(error) {
  const message = getErrorMessage(error);
  if (!message.includes("unknown variant") || !message.includes("plan_type") || !message.includes("body=")) {
    return null;
  }
  const bodyMarkerIndex = message.indexOf("body=");
  const bodyStartIndex = message.indexOf("{", bodyMarkerIndex);
  if (bodyStartIndex < 0) return null;
  try {
    return asRecord(parseJsonObjectAt(message, bodyStartIndex));
  } catch {
    return null;
  }
}
function normalizeWindow(value) {
  const record = asRecord(value);
  if (!record) return null;
  const usedPercent = readNumber(record.used_percent);
  if (usedPercent === null) return null;
  const limitWindowSeconds = readNumber(record.limit_window_seconds);
  const windowMinutes = limitWindowSeconds === null ? null : Math.round(limitWindowSeconds / 60);
  return {
    usedPercent,
    windowDurationMins: windowMinutes,
    windowMinutes,
    resetsAt: readNumber(record.reset_at)
  };
}
function normalizeCredits(value) {
  const record = asRecord(value);
  if (!record) return null;
  const hasCredits = readBoolean(record.has_credits);
  const unlimited = readBoolean(record.unlimited);
  if (hasCredits === null || unlimited === null) return null;
  return {
    hasCredits,
    unlimited,
    balance: readString(record.balance)
  };
}
function buildSnapshot(limitId, limitName, rateLimit, planType, credits) {
  const record = asRecord(rateLimit);
  if (!record) return null;
  const primary = normalizeWindow(record.primary_window);
  const secondary = normalizeWindow(record.secondary_window);
  const normalizedCredits = normalizeCredits(credits);
  if (!primary && !secondary && !normalizedCredits) return null;
  return {
    limitId,
    limitName,
    primary,
    secondary,
    credits: normalizedCredits,
    planType
  };
}
function recoverRateLimitsFromPlanTypeDecodeError(error) {
  const body = extractResponseBodyFromDecodeError(error);
  if (!body) return null;
  const planType = readString(body.plan_type);
  const primarySnapshot = buildSnapshot("codex", null, body.rate_limit, planType, body.credits);
  if (!primarySnapshot) return null;
  const rateLimitsByLimitId = {
    codex: primarySnapshot
  };
  const additionalRateLimits = Array.isArray(body.additional_rate_limits) ? body.additional_rate_limits : [];
  for (const entry of additionalRateLimits) {
    const entryRecord = asRecord(entry);
    if (!entryRecord) continue;
    const limitId = readString(entryRecord.metered_feature) ?? readString(entryRecord.limit_name);
    if (!limitId) continue;
    const snapshot = buildSnapshot(
      limitId,
      readString(entryRecord.limit_name),
      entryRecord.rate_limit,
      planType,
      null
    );
    if (snapshot) {
      rateLimitsByLimitId[limitId] = snapshot;
    }
  }
  return {
    rateLimits: primarySnapshot,
    rateLimitsByLimitId
  };
}
async function callRpcWithRateLimitDecodeRecovery(appServer, method, params) {
  try {
    return await appServer.rpc(method, params ?? null);
  } catch (error) {
    if (method === "account/rateLimits/read") {
      const recovered = recoverRateLimitsFromPlanTypeDecodeError(error);
      if (recovered) return recovered;
    }
    throw error;
  }
}

// src/server/accountRoutes.ts
var ACCOUNT_QUOTA_REFRESH_TTL_MS = 5 * 60 * 1e3;
var ACCOUNT_QUOTA_LOADING_STALE_MS = 2 * 60 * 1e3;
var ACCOUNT_INSPECTION_TIMEOUT_MS = 25 * 1e3;
var LOGIN_URL_TIMEOUT_MS = 15 * 1e3;
var LOGIN_CALLBACK_TIMEOUT_MS = 20 * 1e3;
var LOGIN_AUTH_FILE_TIMEOUT_MS = 10 * 1e3;
var backgroundRefreshPromise = null;
var activeLogin = null;
function asRecord2(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function readString2(value) {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}
function readNumber2(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function readBoolean2(value) {
  return typeof value === "boolean" ? value : null;
}
function normalizeAccountUnavailableReason(value) {
  return value === "payment_required" ? value : null;
}
function setJson(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}
async function readJsonBody(req) {
  const rawBody = await new Promise((resolve4, reject) => {
    let body = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => {
      body += chunk;
    });
    req.on("end", () => resolve4(body));
    req.on("error", reject);
  });
  return asRecord2(rawBody.length > 0 ? JSON.parse(rawBody) : {});
}
function getErrorMessage2(payload, fallback) {
  if (payload instanceof Error && payload.message.trim().length > 0) {
    return payload.message;
  }
  const record = asRecord2(payload);
  const error = record?.error;
  if (typeof error === "string" && error.trim().length > 0) {
    return error.trim();
  }
  if (typeof record?.message === "string" && record.message.trim().length > 0) {
    return record.message.trim();
  }
  return fallback;
}
function isPaymentRequiredErrorMessage(value) {
  if (!value) return false;
  const normalized = value.toLowerCase();
  return normalized.includes("payment required") || /\b402\b/.test(normalized);
}
function detectAccountUnavailableReason(error) {
  return isPaymentRequiredErrorMessage(getErrorMessage2(error, "")) ? "payment_required" : null;
}
function getCodexHomeDir() {
  const codexHome = process.env.CODEX_HOME?.trim();
  return codexHome && codexHome.length > 0 ? codexHome : join2(homedir2(), ".codex");
}
function getActiveAuthPath() {
  return join2(getCodexHomeDir(), "auth.json");
}
function getAccountsStatePath() {
  return join2(getCodexHomeDir(), "accounts.json");
}
function getAccountsSnapshotRoot() {
  return join2(getCodexHomeDir(), "accounts");
}
function toStorageId(accountId) {
  return createHash("sha256").update(accountId).digest("hex");
}
function normalizeRateLimitWindow(value) {
  const record = asRecord2(value);
  if (!record) return null;
  const usedPercent = readNumber2(record.usedPercent ?? record.used_percent);
  if (usedPercent === null) return null;
  return {
    usedPercent,
    windowMinutes: readNumber2(record.windowDurationMins ?? record.window_minutes),
    resetsAt: readNumber2(record.resetsAt ?? record.resets_at)
  };
}
function normalizeCreditsSnapshot(value) {
  const record = asRecord2(value);
  if (!record) return null;
  const hasCredits = readBoolean2(record.hasCredits ?? record.has_credits);
  const unlimited = readBoolean2(record.unlimited);
  if (hasCredits === null || unlimited === null) return null;
  return {
    hasCredits,
    unlimited,
    balance: readString2(record.balance)
  };
}
function normalizeRateLimitSnapshot(value) {
  const record = asRecord2(value);
  if (!record) return null;
  const primary = normalizeRateLimitWindow(record.primary);
  const secondary = normalizeRateLimitWindow(record.secondary);
  const credits = normalizeCreditsSnapshot(record.credits);
  if (!primary && !secondary && !credits) return null;
  return {
    limitId: readString2(record.limitId ?? record.limit_id),
    limitName: readString2(record.limitName ?? record.limit_name),
    primary,
    secondary,
    credits,
    planType: readString2(record.planType ?? record.plan_type)
  };
}
function pickCodexRateLimitSnapshot(payload) {
  const record = asRecord2(payload);
  if (!record) return null;
  const rateLimitsByLimitId = asRecord2(record.rateLimitsByLimitId ?? record.rate_limits_by_limit_id);
  const codexBucket = normalizeRateLimitSnapshot(rateLimitsByLimitId?.codex);
  if (codexBucket) return codexBucket;
  return normalizeRateLimitSnapshot(record.rateLimits ?? record.rate_limits);
}
function normalizeStoredAccountEntry(value) {
  const record = asRecord2(value);
  const accountId = readString2(record?.accountId);
  const storageId = readString2(record?.storageId);
  const lastRefreshedAtIso = readString2(record?.lastRefreshedAtIso);
  const quotaStatusRaw = readString2(record?.quotaStatus);
  const quotaStatus = quotaStatusRaw === "loading" || quotaStatusRaw === "ready" || quotaStatusRaw === "error" ? quotaStatusRaw : "idle";
  if (!accountId || !storageId || !lastRefreshedAtIso) return null;
  return {
    accountId,
    storageId,
    authMode: readString2(record?.authMode),
    email: readString2(record?.email),
    planType: readString2(record?.planType),
    lastRefreshedAtIso,
    lastActivatedAtIso: readString2(record?.lastActivatedAtIso),
    quotaSnapshot: normalizeRateLimitSnapshot(record?.quotaSnapshot),
    quotaUpdatedAtIso: readString2(record?.quotaUpdatedAtIso),
    quotaStatus,
    quotaError: readString2(record?.quotaError),
    unavailableReason: normalizeAccountUnavailableReason(record?.unavailableReason) ?? (isPaymentRequiredErrorMessage(readString2(record?.quotaError)) ? "payment_required" : null)
  };
}
async function readStoredAccountsState() {
  try {
    const raw = await readFile(getAccountsStatePath(), "utf8");
    const parsed = asRecord2(JSON.parse(raw));
    const activeAccountId = readString2(parsed?.activeAccountId);
    const rawAccounts = Array.isArray(parsed?.accounts) ? parsed.accounts : [];
    const accounts = rawAccounts.map((entry) => normalizeStoredAccountEntry(entry)).filter((entry) => entry !== null);
    return { activeAccountId, accounts };
  } catch {
    return { activeAccountId: null, accounts: [] };
  }
}
async function writeStoredAccountsState(state) {
  await writeFile(getAccountsStatePath(), JSON.stringify(state, null, 2), { encoding: "utf8", mode: 384 });
}
function withUpsertedAccount(state, nextEntry) {
  const rest = state.accounts.filter((entry) => entry.accountId !== nextEntry.accountId);
  return {
    activeAccountId: state.activeAccountId,
    accounts: [nextEntry, ...rest]
  };
}
function sortAccounts(accounts, activeAccountId) {
  return [...accounts].sort((left, right) => {
    const leftActive = left.accountId === activeAccountId ? 1 : 0;
    const rightActive = right.accountId === activeAccountId ? 1 : 0;
    if (leftActive !== rightActive) return rightActive - leftActive;
    return right.lastRefreshedAtIso.localeCompare(left.lastRefreshedAtIso);
  });
}
function toPublicAccountEntry(entry, activeAccountId) {
  return {
    ...entry,
    isActive: entry.accountId === activeAccountId
  };
}
function decodeBase64UrlJson(input) {
  try {
    const normalized = input.replace(/-/g, "+").replace(/_/g, "/");
    const padding = normalized.length % 4 === 0 ? "" : "=".repeat(4 - normalized.length % 4);
    const raw = Buffer.from(`${normalized}${padding}`, "base64").toString("utf8");
    const parsed = JSON.parse(raw);
    return asRecord2(parsed);
  } catch {
    return null;
  }
}
function extractTokenMetadata(accessToken) {
  if (!accessToken || typeof accessToken !== "string") {
    return { email: null, planType: null };
  }
  const parts = accessToken.split(".");
  if (parts.length < 2) {
    return { email: null, planType: null };
  }
  const payload = decodeBase64UrlJson(parts[1] ?? "");
  const profile = asRecord2(payload?.["https://api.openai.com/profile"]);
  const auth = asRecord2(payload?.["https://api.openai.com/auth"]);
  return {
    email: typeof profile?.email === "string" && profile.email.trim().length > 0 ? profile.email.trim() : null,
    planType: typeof auth?.chatgpt_plan_type === "string" && auth.chatgpt_plan_type.trim().length > 0 ? auth.chatgpt_plan_type.trim() : null
  };
}
async function readAuthFileFromPath(path) {
  const raw = await readFile(path, "utf8");
  const parsed = JSON.parse(raw);
  const accountId = parsed.tokens?.account_id?.trim() ?? "";
  if (!accountId) {
    throw new Error("missing_account_id");
  }
  return {
    raw,
    parsed,
    accountId,
    authMode: typeof parsed.auth_mode === "string" && parsed.auth_mode.trim().length > 0 ? parsed.auth_mode.trim() : null,
    metadata: extractTokenMetadata(parsed.tokens?.access_token)
  };
}
function getSnapshotPath(storageId) {
  return join2(getAccountsSnapshotRoot(), storageId, "auth.json");
}
async function writeSnapshot(storageId, raw) {
  const dir = join2(getAccountsSnapshotRoot(), storageId);
  await mkdir(dir, { recursive: true, mode: 448 });
  await writeFile(getSnapshotPath(storageId), raw, { encoding: "utf8", mode: 384 });
}
async function removeSnapshot(storageId) {
  await rm(join2(getAccountsSnapshotRoot(), storageId), { recursive: true, force: true });
}
async function readRuntimeAccountMetadata(appServer) {
  const payload = asRecord2(await appServer.rpc("account/read", { refreshToken: false }));
  const account = asRecord2(payload?.account);
  return {
    email: typeof account?.email === "string" && account.email.trim().length > 0 ? account.email.trim() : null,
    planType: typeof account?.planType === "string" && account.planType.trim().length > 0 ? account.planType.trim() : null
  };
}
async function validateSwitchedAccount(appServer) {
  const metadata = await readRuntimeAccountMetadata(appServer);
  const quotaPayload = await callRpcWithRateLimitDecodeRecovery(appServer, "account/rateLimits/read", null);
  return {
    metadata,
    quotaSnapshot: pickCodexRateLimitSnapshot(quotaPayload)
  };
}
async function restoreActiveAuth(raw) {
  const path = getActiveAuthPath();
  if (raw === null) {
    await rm(path, { force: true });
    return;
  }
  await writeFile(path, raw, { encoding: "utf8", mode: 384 });
}
async function fileExists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}
async function withTemporaryCodexAppServer(authRaw, run) {
  const tempCodexHome = await mkdtemp(join2(tmpdir(), "codexui-account-"));
  const authPath = join2(tempCodexHome, "auth.json");
  await writeFile(authPath, authRaw, { encoding: "utf8", mode: 384 });
  const proc = spawn("codex", buildAppServerArgs(), {
    env: { ...process.env, CODEX_HOME: tempCodexHome },
    stdio: ["pipe", "pipe", "pipe"]
  });
  let disposed = false;
  let initialized = false;
  let initializePromise = null;
  let readBuffer = "";
  let nextId = 1;
  const pending = /* @__PURE__ */ new Map();
  const rejectAllPending = (error) => {
    for (const request of pending.values()) {
      request.reject(error);
    }
    pending.clear();
  };
  proc.stdout.setEncoding("utf8");
  proc.stdout.on("data", (chunk) => {
    readBuffer += chunk;
    let lineEnd = readBuffer.indexOf("\n");
    while (lineEnd !== -1) {
      const line = readBuffer.slice(0, lineEnd).trim();
      readBuffer = readBuffer.slice(lineEnd + 1);
      if (line.length > 0) {
        try {
          const message = JSON.parse(line);
          if (typeof message.id === "number" && pending.has(message.id)) {
            const current = pending.get(message.id);
            pending.delete(message.id);
            if (!current) {
              lineEnd = readBuffer.indexOf("\n");
              continue;
            }
            if (message.error?.message) {
              current.reject(new Error(message.error.message));
            } else {
              current.resolve(message.result);
            }
          }
        } catch {
        }
      }
      lineEnd = readBuffer.indexOf("\n");
    }
  });
  proc.stderr.setEncoding("utf8");
  proc.stderr.on("data", () => {
  });
  proc.on("error", (error) => {
    rejectAllPending(error instanceof Error ? error : new Error("codex app-server failed to start"));
  });
  proc.on("exit", () => {
    if (disposed) return;
    rejectAllPending(new Error("codex app-server exited unexpectedly"));
  });
  const sendLine = (payload) => {
    proc.stdin.write(`${JSON.stringify(payload)}
`);
  };
  const call = async (method, params) => {
    const id = nextId++;
    return await new Promise((resolve4, reject) => {
      pending.set(id, { resolve: resolve4, reject });
      sendLine({
        jsonrpc: "2.0",
        id,
        method,
        params
      });
    });
  };
  const ensureInitialized = async () => {
    if (initialized) return;
    if (initializePromise) {
      await initializePromise;
      return;
    }
    initializePromise = call("initialize", {
      clientInfo: {
        name: "codexui-account-refresh",
        version: "0.1.0"
      },
      capabilities: {
        experimentalApi: true
      }
    }).then(() => {
      sendLine({
        jsonrpc: "2.0",
        method: "initialized"
      });
      initialized = true;
    }).finally(() => {
      initializePromise = null;
    });
    await initializePromise;
  };
  const dispose = async () => {
    if (disposed) return;
    disposed = true;
    rejectAllPending(new Error("codex app-server stopped"));
    try {
      proc.stdin.end();
    } catch {
    }
    try {
      proc.kill("SIGTERM");
    } catch {
    }
    await rm(tempCodexHome, { recursive: true, force: true });
  };
  try {
    await ensureInitialized();
    return await run(call);
  } finally {
    await dispose();
  }
}
async function inspectStoredAccount(entry) {
  const snapshotPath = getSnapshotPath(entry.storageId);
  const authRaw = await readFile(snapshotPath, "utf8");
  return await withTemporaryCodexAppServer(authRaw, async (rpc) => {
    const accountPayload = asRecord2(await rpc("account/read", { refreshToken: false }));
    const account = asRecord2(accountPayload?.account);
    const quotaPayload = await callRpcWithRateLimitDecodeRecovery({ rpc }, "account/rateLimits/read", null);
    return {
      metadata: {
        email: typeof account?.email === "string" && account.email.trim().length > 0 ? account.email.trim() : entry.email,
        planType: typeof account?.planType === "string" && account.planType.trim().length > 0 ? account.planType.trim() : entry.planType
      },
      quotaSnapshot: pickCodexRateLimitSnapshot(quotaPayload)
    };
  });
}
async function inspectStoredAccountWithTimeout(entry) {
  let timeoutHandle = null;
  try {
    return await Promise.race([
      inspectStoredAccount(entry),
      new Promise((_, reject) => {
        timeoutHandle = setTimeout(() => {
          reject(new Error(`Account quota inspection timed out after ${ACCOUNT_INSPECTION_TIMEOUT_MS}ms`));
        }, ACCOUNT_INSPECTION_TIMEOUT_MS);
        timeoutHandle.unref?.();
      })
    ]);
  } finally {
    if (timeoutHandle) clearTimeout(timeoutHandle);
  }
}
function shouldRefreshAccountQuota(entry) {
  if (entry.quotaStatus === "loading") {
    const updatedAtMs2 = entry.quotaUpdatedAtIso ? Date.parse(entry.quotaUpdatedAtIso) : Number.NaN;
    if (!Number.isFinite(updatedAtMs2)) return true;
    return Date.now() - updatedAtMs2 >= ACCOUNT_QUOTA_LOADING_STALE_MS;
  }
  if (!entry.quotaUpdatedAtIso) return true;
  const updatedAtMs = Date.parse(entry.quotaUpdatedAtIso);
  if (!Number.isFinite(updatedAtMs)) return true;
  return Date.now() - updatedAtMs >= ACCOUNT_QUOTA_REFRESH_TTL_MS;
}
async function replaceStoredAccount(nextEntry, activeAccountId) {
  const state = await readStoredAccountsState();
  const nextState = withUpsertedAccount({
    activeAccountId,
    accounts: state.accounts
  }, nextEntry);
  await writeStoredAccountsState({
    activeAccountId,
    accounts: nextState.accounts
  });
}
async function pickReplacementActiveAccount(accounts) {
  const sorted = sortAccounts(accounts, null);
  for (const entry of sorted) {
    if (entry.unavailableReason === "payment_required") continue;
    if (await fileExists(getSnapshotPath(entry.storageId))) {
      return entry;
    }
  }
  return null;
}
async function refreshAccountsInBackground(accountIds, activeAccountId) {
  for (const accountId of accountIds) {
    const state = await readStoredAccountsState();
    const entry = state.accounts.find((item) => item.accountId === accountId);
    if (!entry) continue;
    try {
      const inspected = await inspectStoredAccountWithTimeout(entry);
      await replaceStoredAccount({
        ...entry,
        email: inspected.metadata.email ?? entry.email,
        planType: inspected.metadata.planType ?? entry.planType,
        quotaSnapshot: inspected.quotaSnapshot ?? entry.quotaSnapshot,
        quotaUpdatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
        quotaStatus: "ready",
        quotaError: null,
        unavailableReason: null
      }, activeAccountId);
    } catch (error) {
      await replaceStoredAccount({
        ...entry,
        quotaUpdatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
        quotaStatus: "error",
        quotaError: getErrorMessage2(error, "Failed to refresh account quota"),
        unavailableReason: detectAccountUnavailableReason(error)
      }, activeAccountId);
    }
  }
}
async function scheduleAccountsBackgroundRefresh(options = {}) {
  const state = await readStoredAccountsState();
  if (state.accounts.length === 0) return state;
  if (backgroundRefreshPromise) return state;
  const allowedIds = options.accountIds ? new Set(options.accountIds) : null;
  const candidates = state.accounts.filter((entry) => !allowedIds || allowedIds.has(entry.accountId)).filter((entry) => options.force === true || shouldRefreshAccountQuota(entry)).sort((left, right) => {
    const prioritize = options.prioritizeAccountId ?? "";
    const leftPriority = left.accountId === prioritize ? 1 : 0;
    const rightPriority = right.accountId === prioritize ? 1 : 0;
    if (leftPriority !== rightPriority) return rightPriority - leftPriority;
    return 0;
  });
  if (candidates.length === 0) return state;
  const candidateIds = new Set(candidates.map((entry) => entry.accountId));
  const markedState = {
    activeAccountId: state.activeAccountId,
    accounts: state.accounts.map((entry) => candidateIds.has(entry.accountId) ? {
      ...entry,
      quotaStatus: "loading",
      quotaError: null
    } : entry)
  };
  await writeStoredAccountsState(markedState);
  backgroundRefreshPromise = refreshAccountsInBackground(
    candidates.map((entry) => entry.accountId),
    markedState.activeAccountId
  ).finally(() => {
    backgroundRefreshPromise = null;
  });
  return markedState;
}
async function importAccountFromAuthPath(path) {
  const imported = await readAuthFileFromPath(path);
  const storageId = toStorageId(imported.accountId);
  await writeSnapshot(storageId, imported.raw);
  const state = await readStoredAccountsState();
  const existing = state.accounts.find((entry) => entry.accountId === imported.accountId) ?? null;
  const nextEntry = {
    accountId: imported.accountId,
    storageId,
    authMode: imported.authMode,
    email: imported.metadata.email ?? existing?.email ?? null,
    planType: imported.metadata.planType ?? existing?.planType ?? null,
    lastRefreshedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
    lastActivatedAtIso: existing?.lastActivatedAtIso ?? null,
    quotaSnapshot: existing?.quotaSnapshot ?? null,
    quotaUpdatedAtIso: existing?.quotaUpdatedAtIso ?? null,
    quotaStatus: existing?.quotaStatus ?? "idle",
    quotaError: existing?.quotaError ?? null,
    unavailableReason: existing?.unavailableReason ?? null
  };
  const nextState = withUpsertedAccount(state, nextEntry);
  await writeStoredAccountsState(nextState);
  return {
    activeAccountId: nextState.activeAccountId,
    importedAccountId: imported.accountId,
    accounts: sortAccounts(nextState.accounts, nextState.activeAccountId).map((entry) => toPublicAccountEntry(entry, nextState.activeAccountId))
  };
}
function extractLoginUrl(output) {
  const match = output.match(/https:\/\/auth\.openai\.com\/oauth\/authorize\?\S+/u);
  return match?.[0] ?? null;
}
function isLocalCallbackUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    if (parsed.protocol !== "http:") return false;
    return parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1" || parsed.hostname === "[::1]" || parsed.hostname === "::1";
  } catch {
    return false;
  }
}
async function waitForLoginUrl() {
  if (activeLogin?.loginUrl) return activeLogin.loginUrl;
  return await new Promise((resolve4, reject) => {
    const startedAt = Date.now();
    const timer = setInterval(() => {
      if (!activeLogin) {
        clearInterval(timer);
        reject(new Error("Login process is not running."));
        return;
      }
      if (activeLogin.loginUrl) {
        clearInterval(timer);
        resolve4(activeLogin.loginUrl);
        return;
      }
      if (activeLogin.exited) {
        clearInterval(timer);
        reject(new Error(activeLogin.output.trim() || "codex login exited before returning a login URL."));
        return;
      }
      if (Date.now() - startedAt > LOGIN_URL_TIMEOUT_MS) {
        clearInterval(timer);
        reject(new Error("Timed out waiting for codex login URL."));
      }
    }, 100);
  });
}
async function startCodexLogin() {
  if (activeLogin && !activeLogin.exited) {
    return await waitForLoginUrl();
  }
  const proc = spawn("codex", ["login"], {
    env: process.env,
    stdio: ["pipe", "pipe", "pipe"]
  });
  proc.stdin.end();
  activeLogin = {
    proc,
    loginUrl: null,
    output: "",
    exited: false,
    exitCode: null,
    exitSignal: null,
    exitPromise: new Promise((resolve4) => {
      proc.once("exit", (code, signal) => {
        if (activeLogin?.proc === proc) {
          activeLogin.exited = true;
          activeLogin.exitCode = code;
          activeLogin.exitSignal = signal;
        }
        resolve4();
      });
    })
  };
  const appendOutput = (chunk) => {
    if (!activeLogin || activeLogin.proc !== proc) return;
    activeLogin.output += chunk.toString();
    activeLogin.loginUrl = activeLogin.loginUrl ?? extractLoginUrl(activeLogin.output);
  };
  proc.stdout.on("data", appendOutput);
  proc.stderr.on("data", appendOutput);
  proc.once("error", (error) => {
    if (!activeLogin || activeLogin.proc !== proc) return;
    activeLogin.exited = true;
    activeLogin.output += error.message;
  });
  try {
    return await waitForLoginUrl();
  } catch (error) {
    if (activeLogin?.proc === proc && !activeLogin.exited) {
      proc.kill("SIGTERM");
    }
    activeLogin = null;
    throw error;
  }
}
async function curlLoginCallback(callbackUrl) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), LOGIN_CALLBACK_TIMEOUT_MS);
  try {
    const response = await fetch(callbackUrl, {
      redirect: "manual",
      signal: controller.signal
    });
    if (response.status >= 400) {
      throw new Error(`Login callback returned HTTP ${response.status}.`);
    }
  } finally {
    clearTimeout(timer);
  }
}
async function getActiveAuthMtimeMs() {
  try {
    return (await stat(getActiveAuthPath())).mtimeMs;
  } catch {
    return null;
  }
}
async function waitForAuthFileUpdate(previousMtimeMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt <= LOGIN_AUTH_FILE_TIMEOUT_MS) {
    const nextMtimeMs = await getActiveAuthMtimeMs();
    if (nextMtimeMs !== null && (previousMtimeMs === null || nextMtimeMs > previousMtimeMs)) {
      return;
    }
    await new Promise((resolve4) => setTimeout(resolve4, 250));
  }
}
function stopActiveLogin() {
  if (!activeLogin) return;
  if (!activeLogin.exited) {
    activeLogin.proc.kill("SIGTERM");
  }
  activeLogin = null;
}
async function handleAccountRoutes(req, res, url, context) {
  const { appServer } = context;
  if (req.method === "GET" && url.pathname === "/codex-api/accounts") {
    const state = await scheduleAccountsBackgroundRefresh();
    setJson(res, 200, {
      data: {
        activeAccountId: state.activeAccountId,
        accounts: sortAccounts(state.accounts, state.activeAccountId).map((entry) => toPublicAccountEntry(entry, state.activeAccountId))
      }
    });
    return true;
  }
  if (req.method === "GET" && url.pathname === "/codex-api/accounts/active") {
    const state = await readStoredAccountsState();
    const active = state.activeAccountId ? state.accounts.find((entry) => entry.accountId === state.activeAccountId) ?? null : null;
    setJson(res, 200, {
      data: active ? toPublicAccountEntry(active, state.activeAccountId) : null
    });
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/accounts/refresh") {
    try {
      const imported = await importAccountFromAuthPath(getActiveAuthPath());
      try {
        appServer.dispose();
        const inspection = await validateSwitchedAccount(appServer);
        const state = await readStoredAccountsState();
        const importedAccountId = imported.importedAccountId;
        const target = state.accounts.find((entry) => entry.accountId === importedAccountId) ?? null;
        if (!target) {
          throw new Error("account_not_found");
        }
        const nextEntry = {
          ...target,
          email: inspection.metadata.email ?? target.email,
          planType: inspection.metadata.planType ?? target.planType,
          lastActivatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
          quotaSnapshot: inspection.quotaSnapshot ?? target.quotaSnapshot,
          quotaUpdatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
          quotaStatus: "ready",
          quotaError: null,
          unavailableReason: null
        };
        const nextState = withUpsertedAccount({
          activeAccountId: importedAccountId,
          accounts: state.accounts
        }, nextEntry);
        await writeStoredAccountsState({
          activeAccountId: importedAccountId,
          accounts: nextState.accounts
        });
        const backgroundState = await scheduleAccountsBackgroundRefresh({
          force: true,
          prioritizeAccountId: importedAccountId,
          accountIds: nextState.accounts.filter((entry) => entry.accountId !== importedAccountId).map((entry) => entry.accountId)
        });
        setJson(res, 200, {
          data: {
            activeAccountId: importedAccountId,
            importedAccountId,
            accounts: sortAccounts(backgroundState.accounts, importedAccountId).map((entry) => toPublicAccountEntry(entry, importedAccountId))
          }
        });
      } catch (error) {
        setJson(res, 502, {
          error: "account_refresh_failed",
          message: getErrorMessage2(error, "Failed to refresh account")
        });
      }
    } catch (error) {
      const message = getErrorMessage2(error, "Failed to refresh account");
      if (message === "missing_account_id") {
        setJson(res, 400, { error: "missing_account_id", message: "Current auth.json is missing tokens.account_id." });
        return true;
      }
      setJson(res, 400, { error: "invalid_auth_json", message: "Failed to parse the current auth.json file." });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/accounts/login/start") {
    try {
      const loginUrl = await startCodexLogin();
      setJson(res, 200, {
        ok: true,
        data: {
          loginUrl
        }
      });
    } catch (error) {
      setJson(res, 500, {
        error: "account_login_start_failed",
        message: getErrorMessage2(error, "Failed to start codex login")
      });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/accounts/login/complete") {
    try {
      const payload = await readJsonBody(req);
      const callbackUrl = typeof payload?.callbackUrl === "string" ? payload.callbackUrl.trim() : "";
      if (!callbackUrl) {
        setJson(res, 400, { error: "missing_callback_url", message: "Paste the localhost callback URL from the browser." });
        return true;
      }
      if (!isLocalCallbackUrl(callbackUrl)) {
        setJson(res, 400, { error: "invalid_callback_url", message: "The callback URL must use http://localhost or http://127.0.0.1." });
        return true;
      }
      if (!activeLogin || activeLogin.exited) {
        setJson(res, 409, { error: "login_not_running", message: "Start Codex login before submitting the callback URL." });
        return true;
      }
      const previousAuthMtimeMs = await getActiveAuthMtimeMs();
      await curlLoginCallback(callbackUrl);
      await waitForAuthFileUpdate(previousAuthMtimeMs);
      const imported = await importAccountFromAuthPath(getActiveAuthPath());
      stopActiveLogin();
      appServer.dispose();
      const inspection = await validateSwitchedAccount(appServer);
      const state = await readStoredAccountsState();
      const importedAccountId = imported.importedAccountId;
      const target = state.accounts.find((entry) => entry.accountId === importedAccountId) ?? null;
      if (!target) {
        throw new Error("account_not_found");
      }
      const nextEntry = {
        ...target,
        email: inspection.metadata.email ?? target.email,
        planType: inspection.metadata.planType ?? target.planType,
        lastActivatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
        quotaSnapshot: inspection.quotaSnapshot ?? target.quotaSnapshot,
        quotaUpdatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
        quotaStatus: "ready",
        quotaError: null,
        unavailableReason: null
      };
      const nextState = withUpsertedAccount({
        activeAccountId: importedAccountId,
        accounts: state.accounts
      }, nextEntry);
      await writeStoredAccountsState({
        activeAccountId: importedAccountId,
        accounts: nextState.accounts
      });
      const backgroundState = await scheduleAccountsBackgroundRefresh({
        force: true,
        prioritizeAccountId: importedAccountId,
        accountIds: nextState.accounts.filter((entry) => entry.accountId !== importedAccountId).map((entry) => entry.accountId)
      });
      setJson(res, 200, {
        ok: true,
        data: {
          activeAccountId: importedAccountId,
          importedAccountId,
          accounts: sortAccounts(backgroundState.accounts, importedAccountId).map((entry) => toPublicAccountEntry(entry, importedAccountId))
        }
      });
    } catch (error) {
      setJson(res, 500, {
        error: "account_login_complete_failed",
        message: getErrorMessage2(error, "Failed to complete Codex login")
      });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/accounts/switch") {
    try {
      if (appServer.listPendingServerRequests().length > 0) {
        setJson(res, 409, {
          error: "account_switch_blocked",
          message: "Finish pending approval requests before switching accounts."
        });
        return true;
      }
      const payload = await readJsonBody(req);
      const accountId = typeof payload?.accountId === "string" ? payload.accountId.trim() : "";
      if (!accountId) {
        setJson(res, 400, { error: "account_not_found", message: "Missing accountId." });
        return true;
      }
      const state = await readStoredAccountsState();
      const target = state.accounts.find((entry) => entry.accountId === accountId) ?? null;
      if (!target) {
        setJson(res, 404, { error: "account_not_found", message: "The requested account was not found." });
        return true;
      }
      const snapshotPath = getSnapshotPath(target.storageId);
      if (!await fileExists(snapshotPath)) {
        setJson(res, 404, { error: "account_not_found", message: "The requested account snapshot is missing." });
        return true;
      }
      let previousRaw = null;
      try {
        previousRaw = await readFile(getActiveAuthPath(), "utf8");
      } catch {
        previousRaw = null;
      }
      const targetRaw = await readFile(snapshotPath, "utf8");
      await writeFile(getActiveAuthPath(), targetRaw, { encoding: "utf8", mode: 384 });
      try {
        appServer.dispose();
        const inspection = await validateSwitchedAccount(appServer);
        const nextEntry = {
          ...target,
          email: inspection.metadata.email ?? target.email,
          planType: inspection.metadata.planType ?? target.planType,
          lastActivatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
          quotaSnapshot: inspection.quotaSnapshot ?? target.quotaSnapshot,
          quotaUpdatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
          quotaStatus: "ready",
          quotaError: null,
          unavailableReason: null
        };
        const nextState = withUpsertedAccount({
          activeAccountId: accountId,
          accounts: state.accounts
        }, nextEntry);
        await writeStoredAccountsState({
          activeAccountId: accountId,
          accounts: nextState.accounts
        });
        void scheduleAccountsBackgroundRefresh({
          force: true,
          prioritizeAccountId: accountId,
          accountIds: nextState.accounts.filter((entry) => entry.accountId !== accountId).map((entry) => entry.accountId)
        });
        setJson(res, 200, {
          ok: true,
          data: {
            activeAccountId: accountId,
            account: toPublicAccountEntry(nextEntry, accountId)
          }
        });
      } catch (error) {
        await restoreActiveAuth(previousRaw);
        appServer.dispose();
        await replaceStoredAccount({
          ...target,
          quotaUpdatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
          quotaStatus: "error",
          quotaError: getErrorMessage2(error, "Failed to switch account"),
          unavailableReason: detectAccountUnavailableReason(error)
        }, state.activeAccountId);
        setJson(res, 502, {
          error: "account_switch_failed",
          message: getErrorMessage2(error, "Failed to switch account")
        });
      }
    } catch (error) {
      setJson(res, 400, {
        error: "invalid_auth_json",
        message: getErrorMessage2(error, "Failed to switch account")
      });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/accounts/remove") {
    try {
      const payload = await readJsonBody(req);
      const accountId = typeof payload?.accountId === "string" ? payload.accountId.trim() : "";
      if (!accountId) {
        setJson(res, 400, { error: "account_not_found", message: "Missing accountId." });
        return true;
      }
      const state = await readStoredAccountsState();
      const target = state.accounts.find((entry) => entry.accountId === accountId) ?? null;
      if (!target) {
        setJson(res, 404, { error: "account_not_found", message: "The requested account was not found." });
        return true;
      }
      const remainingAccounts = state.accounts.filter((entry) => entry.accountId !== accountId);
      if (state.activeAccountId !== accountId) {
        await removeSnapshot(target.storageId);
        await writeStoredAccountsState({
          activeAccountId: state.activeAccountId,
          accounts: remainingAccounts
        });
        setJson(res, 200, {
          ok: true,
          data: {
            activeAccountId: state.activeAccountId,
            accounts: sortAccounts(remainingAccounts, state.activeAccountId).map((entry) => toPublicAccountEntry(entry, state.activeAccountId))
          }
        });
        return true;
      }
      if (appServer.listPendingServerRequests().length > 0) {
        setJson(res, 409, {
          error: "account_remove_blocked",
          message: "Finish pending approval requests before removing the active account."
        });
        return true;
      }
      let previousRaw = null;
      try {
        previousRaw = await readFile(getActiveAuthPath(), "utf8");
      } catch {
        previousRaw = null;
      }
      const replacement = await pickReplacementActiveAccount(remainingAccounts);
      if (!replacement) {
        await restoreActiveAuth(null);
        appServer.dispose();
        await removeSnapshot(target.storageId);
        await writeStoredAccountsState({
          activeAccountId: null,
          accounts: remainingAccounts
        });
        void scheduleAccountsBackgroundRefresh({
          force: true,
          accountIds: remainingAccounts.map((entry) => entry.accountId)
        });
        setJson(res, 200, {
          ok: true,
          data: {
            activeAccountId: null,
            accounts: sortAccounts(remainingAccounts, null).map((entry) => toPublicAccountEntry(entry, null))
          }
        });
        return true;
      }
      const replacementSnapshotPath = getSnapshotPath(replacement.storageId);
      if (!await fileExists(replacementSnapshotPath)) {
        setJson(res, 404, {
          error: "account_not_found",
          message: "The replacement account snapshot is missing."
        });
        return true;
      }
      const replacementRaw = await readFile(replacementSnapshotPath, "utf8");
      await writeFile(getActiveAuthPath(), replacementRaw, { encoding: "utf8", mode: 384 });
      try {
        appServer.dispose();
        const inspection = await validateSwitchedAccount(appServer);
        const activatedReplacement = {
          ...replacement,
          email: inspection.metadata.email ?? replacement.email,
          planType: inspection.metadata.planType ?? replacement.planType,
          lastActivatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
          quotaSnapshot: inspection.quotaSnapshot ?? replacement.quotaSnapshot,
          quotaUpdatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
          quotaStatus: "ready",
          quotaError: null,
          unavailableReason: null
        };
        const nextAccounts = remainingAccounts.map((entry) => entry.accountId === activatedReplacement.accountId ? activatedReplacement : entry);
        await removeSnapshot(target.storageId);
        await writeStoredAccountsState({
          activeAccountId: activatedReplacement.accountId,
          accounts: nextAccounts
        });
        void scheduleAccountsBackgroundRefresh({
          force: true,
          prioritizeAccountId: activatedReplacement.accountId,
          accountIds: nextAccounts.filter((entry) => entry.accountId !== activatedReplacement.accountId).map((entry) => entry.accountId)
        });
        setJson(res, 200, {
          ok: true,
          data: {
            activeAccountId: activatedReplacement.accountId,
            accounts: sortAccounts(nextAccounts, activatedReplacement.accountId).map((entry) => toPublicAccountEntry(entry, activatedReplacement.accountId))
          }
        });
      } catch (error) {
        await restoreActiveAuth(previousRaw);
        appServer.dispose();
        await replaceStoredAccount({
          ...replacement,
          quotaUpdatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
          quotaStatus: "error",
          quotaError: getErrorMessage2(error, "Failed to switch account"),
          unavailableReason: detectAccountUnavailableReason(error)
        }, state.activeAccountId);
        setJson(res, 502, {
          error: "account_remove_failed",
          message: getErrorMessage2(error, "Failed to remove account")
        });
      }
    } catch (error) {
      setJson(res, 400, {
        error: "invalid_auth_json",
        message: getErrorMessage2(error, "Failed to remove account")
      });
    }
    return true;
  }
  return false;
}

// src/server/reviewGit.ts
import { spawn as spawn2 } from "child_process";
import { createReadStream } from "fs";
import { mkdir as mkdir2, rm as rm2, stat as stat2, writeFile as writeFile2 } from "fs/promises";
import { tmpdir as tmpdir2 } from "os";
import { isAbsolute, join as join3, resolve } from "path";
function getNodeErrorCode(error) {
  return typeof error === "object" && error && "code" in error ? String(error.code) : "";
}
function normalizeBaseBranchDisplayName(value) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.startsWith("origin/") ? trimmed.slice("origin/".length) : trimmed;
}
function asRecord3(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function readString3(value) {
  return typeof value === "string" ? value.trim() : "";
}
function getErrorMessage3(payload, fallback) {
  if (payload instanceof Error && payload.message.trim().length > 0) {
    return payload.message;
  }
  const record = asRecord3(payload);
  if (!record) return fallback;
  const direct = readString3(record.error);
  if (direct) return direct;
  const nested = asRecord3(record.error);
  const nestedMessage = readString3(nested?.message);
  if (nestedMessage) return nestedMessage;
  return fallback;
}
function setJson2(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}
async function runCommandResult(command, args, options = {}) {
  return await new Promise((resolve4, reject) => {
    const proc = spawn2(command, args, {
      cwd: options.cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", reject);
    proc.on("close", (code) => {
      resolve4({
        code: code ?? 1,
        stdout: stdout.trim(),
        stderr: stderr.trim()
      });
    });
  });
}
async function runCommand(command, args, options = {}) {
  const result = await runCommandResult(command, args, options);
  if (result.code === 0) return;
  const details = [result.stderr, result.stdout].filter(Boolean).join("\n");
  const suffix = details ? `: ${details}` : "";
  throw new Error(`Command failed (${command} ${args.join(" ")})${suffix}`);
}
async function runCommandCapture(command, args, options = {}) {
  const result = await runCommandResult(command, args, options);
  if (result.code === 0) return result.stdout;
  const details = [result.stderr, result.stdout].filter(Boolean).join("\n");
  const suffix = details ? `: ${details}` : "";
  throw new Error(`Command failed (${command} ${args.join(" ")})${suffix}`);
}
async function runCommandCaptureRaw(command, args, options = {}) {
  return await new Promise((resolve4, reject) => {
    const proc = spawn2(command, args, {
      cwd: options.cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code === 0) {
        resolve4(stdout);
        return;
      }
      const details = [stderr.trim(), stdout.trim()].filter(Boolean).join("\n");
      const suffix = details ? `: ${details}` : "";
      reject(new Error(`Command failed (${command} ${args.join(" ")})${suffix}`));
    });
  });
}
function isNotGitRepositoryError(error) {
  const message = getErrorMessage3(error, "").toLowerCase();
  return message.includes("not a git repository") || message.includes("fatal: not a git repository");
}
function isMissingHeadError(error) {
  const message = getErrorMessage3(error, "").toLowerCase();
  return message.includes("ambiguous argument 'head'") || message.includes("bad revision 'head'") || message.includes("unknown revision or path not in the working tree") || message.includes("not a valid object name 'head'") || message.includes("not a valid object name: head");
}
function normalizeInputCwd(value) {
  return isAbsolute(value) ? value : resolve(value);
}
async function ensureDirectory(cwd) {
  const info = await stat2(cwd);
  if (!info.isDirectory()) {
    throw new Error("cwd is not a directory");
  }
}
async function resolveGitRoot(cwd) {
  try {
    return await runCommandCapture("git", ["rev-parse", "--show-toplevel"], { cwd });
  } catch (error) {
    if (isNotGitRepositoryError(error)) {
      return null;
    }
    throw error;
  }
}
async function gitRefExists(repoRoot, ref) {
  const result = await runCommandResult("git", ["rev-parse", "--verify", "--quiet", ref], { cwd: repoRoot });
  return result.code === 0;
}
async function detectBaseBranch(repoRoot) {
  const originHead = await runCommandResult("git", ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], { cwd: repoRoot });
  const originHeadRef = originHead.code === 0 ? originHead.stdout : "";
  if (originHeadRef.startsWith("origin/")) {
    return {
      displayName: originHeadRef.slice("origin/".length),
      gitRef: originHeadRef
    };
  }
  for (const candidate of ["main", "master"]) {
    if (await gitRefExists(repoRoot, candidate)) {
      return { displayName: candidate, gitRef: candidate };
    }
    const remoteCandidate = `origin/${candidate}`;
    if (await gitRefExists(repoRoot, remoteCandidate)) {
      return { displayName: candidate, gitRef: remoteCandidate };
    }
  }
  return null;
}
async function listBaseBranchOptions(repoRoot) {
  const result = await runCommandResult(
    "git",
    ["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin"],
    { cwd: repoRoot }
  );
  if (result.code !== 0) {
    return [];
  }
  const options = [];
  for (const line of result.stdout.split(/\r?\n/u)) {
    const normalized = normalizeBaseBranchDisplayName(line);
    if (!normalized || normalized === "HEAD" || normalized.endsWith("/HEAD")) continue;
    if (!options.includes(normalized)) {
      options.push(normalized);
    }
  }
  for (const fallback of ["main", "master"]) {
    if (!options.includes(fallback)) {
      options.push(fallback);
    }
  }
  return options;
}
async function resolveBaseBranch(repoRoot, requestedBaseBranch = "") {
  const normalizedRequested = normalizeBaseBranchDisplayName(requestedBaseBranch);
  if (normalizedRequested) {
    for (const candidate of [normalizedRequested, `origin/${normalizedRequested}`]) {
      if (await gitRefExists(repoRoot, candidate)) {
        return {
          displayName: normalizedRequested,
          gitRef: candidate
        };
      }
    }
  }
  return await detectBaseBranch(repoRoot);
}
async function detectHeadBranch(repoRoot) {
  const result = await runCommandResult("git", ["symbolic-ref", "--quiet", "--short", "HEAD"], { cwd: repoRoot });
  return result.code === 0 && result.stdout !== "HEAD" ? result.stdout : null;
}
function splitGitPathList(raw) {
  return raw.split("\0").filter((entry) => entry.length > 0);
}
function isSafeGitRelativePath(filePath) {
  return Boolean(filePath) && !isAbsolute(filePath) && !filePath.split("/").includes("..");
}
async function listUntrackedPaths(repoRoot) {
  const output = await runCommandCaptureRaw("git", ["ls-files", "--others", "--exclude-standard", "-z"], { cwd: repoRoot });
  return splitGitPathList(output).filter(isSafeGitRelativePath);
}
async function diffUntrackedFile(repoRoot, path) {
  const result = await runCommandResult(
    "git",
    ["diff", "--no-index", "--no-ext-diff", "--patch", "--", "/dev/null", path],
    { cwd: repoRoot }
  );
  if (result.code !== 0 && result.code !== 1) {
    const details = [result.stderr, result.stdout].filter(Boolean).join("\n");
    const suffix = details ? `: ${details}` : "";
    throw new Error(`Command failed (git diff --no-index -- /dev/null ${path})${suffix}`);
  }
  return result.stdout;
}
function parseNumstatSummary(output) {
  let fileCount = 0;
  let addedLineCount = 0;
  let removedLineCount = 0;
  for (const line of output.split(/\r?\n/u)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const [addedRaw, removedRaw] = trimmed.split(/\s+/u);
    if (addedRaw === void 0 || removedRaw === void 0) continue;
    fileCount += 1;
    const added = Number(addedRaw);
    const removed = Number(removedRaw);
    if (Number.isFinite(added)) addedLineCount += added;
    if (Number.isFinite(removed)) removedLineCount += removed;
  }
  return { fileCount, addedLineCount, removedLineCount };
}
function addReviewSummary(left, right) {
  return {
    fileCount: left.fileCount + right.fileCount,
    addedLineCount: left.addedLineCount + right.addedLineCount,
    removedLineCount: left.removedLineCount + right.removedLineCount
  };
}
async function summarizeUntrackedFile(repoRoot, path) {
  const absolutePath = join3(repoRoot, ...path.split("/"));
  let info;
  try {
    info = await stat2(absolutePath);
  } catch (error) {
    const code = getNodeErrorCode(error);
    if (code === "ENOENT" || code === "ENOTDIR") {
      return { fileCount: 0, addedLineCount: 0, removedLineCount: 0 };
    }
    if (code === "EACCES" || code === "EPERM") {
      return { fileCount: 1, addedLineCount: 0, removedLineCount: 0 };
    }
    throw error;
  }
  if (!info.isFile()) {
    return { fileCount: 0, addedLineCount: 0, removedLineCount: 0 };
  }
  const addedLineCount = await new Promise((resolve4, reject) => {
    const stream = createReadStream(absolutePath);
    let lineCount = 0;
    let sawAnyByte = false;
    let lastByteWasNewline = false;
    stream.on("data", (chunk) => {
      if (typeof chunk === "string") chunk = Buffer.from(chunk);
      sawAnyByte = true;
      for (const byte of chunk) {
        if (byte === 10) lineCount += 1;
      }
      lastByteWasNewline = chunk[chunk.length - 1] === 10;
    });
    stream.on("error", (error) => {
      const code = getNodeErrorCode(error);
      if (code === "ENOENT" || code === "ENOTDIR") {
        resolve4(0);
        return;
      }
      if (code === "EACCES" || code === "EPERM") {
        resolve4(0);
        return;
      }
      reject(error);
    });
    stream.on("end", () => {
      resolve4(sawAnyByte && !lastByteWasNewline ? lineCount + 1 : lineCount);
    });
  });
  return { fileCount: 1, addedLineCount, removedLineCount: 0 };
}
async function buildWorkspaceDiffSummary(repoRoot, workspaceView) {
  if (workspaceView === "staged") {
    try {
      const output = await runCommandCapture("git", ["diff", "--cached", "--no-ext-diff", "--find-renames", "--numstat"], { cwd: repoRoot });
      return parseNumstatSummary(output);
    } catch (error) {
      if (isMissingHeadError(error)) {
        return { fileCount: 0, addedLineCount: 0, removedLineCount: 0 };
      }
      throw error;
    }
  }
  let summary = { fileCount: 0, addedLineCount: 0, removedLineCount: 0 };
  try {
    const output = await runCommandCapture("git", ["diff", "--no-ext-diff", "--find-renames", "--numstat"], { cwd: repoRoot });
    summary = addReviewSummary(summary, parseNumstatSummary(output));
  } catch (error) {
    if (!isMissingHeadError(error)) {
      throw error;
    }
  }
  for (const path of await listUntrackedPaths(repoRoot)) {
    summary = addReviewSummary(summary, await summarizeUntrackedFile(repoRoot, path));
  }
  return summary;
}
async function buildWorkspaceDiff(repoRoot, workspaceView) {
  if (workspaceView === "staged") {
    try {
      return await runCommandCapture("git", ["diff", "--cached", "--no-ext-diff", "--find-renames", "--patch"], { cwd: repoRoot });
    } catch (error) {
      if (isMissingHeadError(error)) {
        return "";
      }
      throw error;
    }
  }
  let trackedDiff = "";
  try {
    trackedDiff = await runCommandCapture("git", ["diff", "--no-ext-diff", "--find-renames", "--patch"], { cwd: repoRoot });
  } catch (error) {
    if (!isMissingHeadError(error)) {
      throw error;
    }
  }
  const untrackedDiffs = await Promise.all(
    (await listUntrackedPaths(repoRoot)).map(async (path) => await diffUntrackedFile(repoRoot, path))
  );
  return [trackedDiff, ...untrackedDiffs].map((chunk) => chunk.trim()).filter(Boolean).join("\n");
}
async function buildBaseBranchDiff(repoRoot, baseBranch) {
  const mergeBaseResult = await runCommandResult("git", ["merge-base", "HEAD", baseBranch.gitRef], { cwd: repoRoot });
  if (mergeBaseResult.code !== 0 || !mergeBaseResult.stdout) {
    return { diffText: "", mergeBaseSha: null };
  }
  const diffText = await runCommandCapture(
    "git",
    ["diff", "--no-ext-diff", "--find-renames", "--patch", mergeBaseResult.stdout, "HEAD"],
    { cwd: repoRoot }
  );
  return {
    diffText,
    mergeBaseSha: mergeBaseResult.stdout
  };
}
async function buildCommitDiff(repoRoot, commitSha) {
  const resolvedSha = await runCommandCapture("git", ["rev-parse", "--verify", `${commitSha}^{commit}`], { cwd: repoRoot });
  const diffText = await runCommandCapture(
    "git",
    ["diff-tree", "--root", "-r", "--no-commit-id", "--no-ext-diff", "--find-renames", "--patch", resolvedSha],
    { cwd: repoRoot }
  );
  return { diffText, commitSha: resolvedSha };
}
function normalizeDiffPath(value) {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "/dev/null") return null;
  if (trimmed.startsWith("a/") || trimmed.startsWith("b/")) {
    return trimmed.slice(2);
  }
  return trimmed;
}
function filePathFromDiffHeader(line, side) {
  const prefix = side === "old" ? "--- " : "+++ ";
  if (!line.startsWith(prefix)) return null;
  return normalizeDiffPath(line.slice(prefix.length));
}
function parseDiffGitLine(line) {
  const match = line.match(/^diff --git a\/(.+?) b\/(.+)$/u);
  if (!match) return { oldPath: null, newPath: null };
  return {
    oldPath: normalizeDiffPath(`a/${match[1]}`),
    newPath: normalizeDiffPath(`b/${match[2]}`)
  };
}
function buildReviewDiffLines(fileId, hunkId, lines) {
  const output = [];
  let addedLineCount = 0;
  let removedLineCount = 0;
  let oldLine = null;
  let newLine = null;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    if (index === 0) {
      const match = line.match(/^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@/u);
      if (match) {
        oldLine = Number(match[1]);
        newLine = Number(match[3]);
      }
      output.push({
        key: `${fileId}:${hunkId}:header`,
        kind: "hunk",
        text: line,
        oldLine: null,
        newLine: null
      });
      continue;
    }
    if (line.startsWith("+") && !line.startsWith("+++")) {
      output.push({
        key: `${fileId}:${hunkId}:add:${index}`,
        kind: "add",
        text: line.slice(1),
        oldLine: null,
        newLine
      });
      addedLineCount += 1;
      newLine = newLine === null ? null : newLine + 1;
      continue;
    }
    if (line.startsWith("-") && !line.startsWith("---")) {
      output.push({
        key: `${fileId}:${hunkId}:remove:${index}`,
        kind: "remove",
        text: line.slice(1),
        oldLine,
        newLine: null
      });
      removedLineCount += 1;
      oldLine = oldLine === null ? null : oldLine + 1;
      continue;
    }
    if (line.startsWith("\\")) {
      output.push({
        key: `${fileId}:${hunkId}:meta:${index}`,
        kind: "meta",
        text: line,
        oldLine: null,
        newLine: null
      });
      continue;
    }
    output.push({
      key: `${fileId}:${hunkId}:context:${index}`,
      kind: "context",
      text: line.startsWith(" ") ? line.slice(1) : line,
      oldLine,
      newLine
    });
    oldLine = oldLine === null ? null : oldLine + 1;
    newLine = newLine === null ? null : newLine + 1;
  }
  return { addedLineCount, removedLineCount, lines: output };
}
function parseDiffBlocks(diffText) {
  const normalized = diffText.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];
  const blocks = [];
  let current = [];
  for (const line of normalized.split("\n")) {
    if (line.startsWith("diff --git ")) {
      if (current.length > 0) {
        blocks.push(current);
      }
      current = [line];
      continue;
    }
    if (current.length > 0) {
      current.push(line);
    }
  }
  if (current.length > 0) {
    blocks.push(current);
  }
  return blocks;
}
function serializePatch(lines) {
  if (lines.length === 0) return "";
  return `${lines.join("\n")}
`;
}
function parseReviewSnapshotFile(repoRoot, blockLines, fileIndex) {
  if (blockLines.length === 0) return null;
  let oldPath = null;
  let newPath = null;
  let renameFrom = null;
  let renameTo = null;
  let operation = "update";
  const firstHunkIndex = blockLines.findIndex((line) => line.startsWith("@@ "));
  const headerLines = firstHunkIndex >= 0 ? blockLines.slice(0, firstHunkIndex) : [...blockLines];
  for (const line of headerLines) {
    if (line.startsWith("diff --git ")) {
      const parsed = parseDiffGitLine(line);
      oldPath = parsed.oldPath ?? oldPath;
      newPath = parsed.newPath ?? newPath;
      continue;
    }
    if (line.startsWith("rename from ")) {
      renameFrom = normalizeDiffPath(line.slice("rename from ".length));
      operation = "rename";
      continue;
    }
    if (line.startsWith("rename to ")) {
      renameTo = normalizeDiffPath(line.slice("rename to ".length));
      operation = "rename";
      continue;
    }
    if (line.startsWith("new file mode ")) {
      operation = "add";
      continue;
    }
    if (line.startsWith("deleted file mode ")) {
      operation = "delete";
      continue;
    }
    const headerOldPath = filePathFromDiffHeader(line, "old");
    if (headerOldPath !== null) {
      oldPath = headerOldPath;
      continue;
    }
    const headerNewPath = filePathFromDiffHeader(line, "new");
    if (headerNewPath !== null) {
      newPath = headerNewPath;
    }
  }
  const previousPath = renameFrom ?? oldPath;
  const resolvedPath = renameTo ?? newPath ?? oldPath;
  if (!resolvedPath) return null;
  if (operation === "update") {
    if (!previousPath) {
      operation = "add";
    } else if (!newPath) {
      operation = "delete";
    }
  }
  const hunks = [];
  if (firstHunkIndex >= 0) {
    let currentHunk = [];
    let hunkCounter = 0;
    const flushHunk = () => {
      if (currentHunk.length === 0) return;
      const header = currentHunk[0] ?? "";
      const match = header.match(/^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@/u);
      const hunkId = `review-hunk:${fileIndex}:${hunkCounter}`;
      const rendered = buildReviewDiffLines(`review-file:${fileIndex}`, hunkId, currentHunk);
      hunks.push({
        id: hunkId,
        header,
        patch: serializePatch([...headerLines, ...currentHunk]),
        addedLineCount: rendered.addedLineCount,
        removedLineCount: rendered.removedLineCount,
        oldStart: match ? Number(match[1]) : null,
        oldLineCount: match ? Number(match[2] ?? "1") : 0,
        newStart: match ? Number(match[3]) : null,
        newLineCount: match ? Number(match[4] ?? "1") : 0,
        lines: rendered.lines
      });
      currentHunk = [];
      hunkCounter += 1;
    };
    for (let index = firstHunkIndex; index < blockLines.length; index += 1) {
      const line = blockLines[index] ?? "";
      if (line.startsWith("@@ ")) {
        flushHunk();
        currentHunk = [line];
        continue;
      }
      if (currentHunk.length > 0) {
        currentHunk.push(line);
      }
    }
    flushHunk();
  }
  const addedLineCount = hunks.reduce((sum, hunk) => sum + hunk.addedLineCount, 0);
  const removedLineCount = hunks.reduce((sum, hunk) => sum + hunk.removedLineCount, 0);
  return {
    id: `review-file:${fileIndex}`,
    path: resolvedPath,
    absolutePath: join3(repoRoot, resolvedPath),
    previousPath: previousPath && previousPath !== resolvedPath ? previousPath : null,
    previousAbsolutePath: previousPath && previousPath !== resolvedPath ? join3(repoRoot, previousPath) : null,
    operation,
    addedLineCount,
    removedLineCount,
    diff: serializePatch(blockLines),
    hunks
  };
}
function parseReviewSnapshotFiles(repoRoot, diffText) {
  return parseDiffBlocks(diffText).map((block, index) => parseReviewSnapshotFile(repoRoot, block, index)).filter((entry) => entry !== null);
}
async function buildReviewSnapshot(cwd, scope, workspaceView, requestedBaseBranch = "", requestedCommitSha = "") {
  const normalizedCwd = normalizeInputCwd(cwd);
  await ensureDirectory(normalizedCwd);
  const gitRoot = await resolveGitRoot(normalizedCwd);
  if (!gitRoot) {
    return {
      cwd: normalizedCwd,
      gitRoot: null,
      isGitRepo: false,
      scope,
      workspaceView,
      baseBranch: null,
      baseBranchOptions: [],
      commitSha: null,
      headBranch: null,
      mergeBaseSha: null,
      generatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
      summary: {
        fileCount: 0,
        addedLineCount: 0,
        removedLineCount: 0
      },
      files: []
    };
  }
  const [baseBranch, baseBranchOptions, headBranch] = await Promise.all([
    resolveBaseBranch(gitRoot, requestedBaseBranch),
    listBaseBranchOptions(gitRoot),
    detectHeadBranch(gitRoot)
  ]);
  let diffText = "";
  let mergeBaseSha = null;
  let commitSha = null;
  if (scope === "commit") {
    if (!requestedCommitSha.trim()) {
      throw new Error("Missing commit");
    }
    const commitDiff = await buildCommitDiff(gitRoot, requestedCommitSha.trim());
    diffText = commitDiff.diffText;
    commitSha = commitDiff.commitSha;
  } else if (scope === "baseBranch") {
    if (baseBranch) {
      const baseDiff = await buildBaseBranchDiff(gitRoot, baseBranch);
      diffText = baseDiff.diffText;
      mergeBaseSha = baseDiff.mergeBaseSha;
    }
  } else {
    diffText = await buildWorkspaceDiff(gitRoot, workspaceView);
  }
  const files = parseReviewSnapshotFiles(gitRoot, diffText);
  return {
    cwd: normalizedCwd,
    gitRoot,
    isGitRepo: true,
    scope,
    workspaceView,
    baseBranch: baseBranch?.displayName ?? null,
    baseBranchOptions,
    commitSha,
    headBranch,
    mergeBaseSha,
    generatedAtIso: (/* @__PURE__ */ new Date()).toISOString(),
    summary: {
      fileCount: files.length,
      addedLineCount: files.reduce((sum, file) => sum + file.addedLineCount, 0),
      removedLineCount: files.reduce((sum, file) => sum + file.removedLineCount, 0)
    },
    files
  };
}
async function buildReviewSummary(cwd, workspaceView) {
  const normalizedCwd = normalizeInputCwd(cwd);
  await ensureDirectory(normalizedCwd);
  const gitRoot = await resolveGitRoot(normalizedCwd);
  if (!gitRoot) {
    return { fileCount: 0, addedLineCount: 0, removedLineCount: 0 };
  }
  return await buildWorkspaceDiffSummary(gitRoot, workspaceView);
}
async function writePatchFile(patch) {
  const dir = await mkdir2(join3(tmpdir2(), "codexui-review-patches"), { recursive: true }).then(() => join3(tmpdir2(), "codexui-review-patches"));
  const filePath = join3(dir, `${Date.now()}-${Math.random().toString(16).slice(2)}.patch`);
  const normalizedPatch = patch.endsWith("\n") ? patch : `${patch}
`;
  await writeFile2(filePath, normalizedPatch, "utf8");
  return filePath;
}
async function applyPatchAction(repoRoot, action, workspaceView, patch) {
  const patchPath = await writePatchFile(patch);
  try {
    if (workspaceView === "unstaged" && action === "stage") {
      await runCommand("git", ["apply", "--cached", "--recount", patchPath], { cwd: repoRoot });
      return;
    }
    if (workspaceView === "unstaged" && action === "revert") {
      await runCommand("git", ["apply", "-R", "--recount", patchPath], { cwd: repoRoot });
      return;
    }
    if (workspaceView === "staged" && action === "unstage") {
      await runCommand("git", ["apply", "--cached", "-R", "--recount", patchPath], { cwd: repoRoot });
      return;
    }
    throw new Error("Unsupported patch action for this view");
  } finally {
    await rm2(patchPath, { force: true });
  }
}
async function applyAllAction(repoRoot, action, workspaceView) {
  if (workspaceView === "unstaged" && action === "stage") {
    await runCommand("git", ["add", "-A"], { cwd: repoRoot });
    return;
  }
  if (workspaceView === "unstaged" && action === "revert") {
    try {
      await runCommand("git", ["restore", "--worktree", "--source=HEAD", "--", "."], { cwd: repoRoot });
    } catch (error) {
      if (!isMissingHeadError(error)) {
        throw error;
      }
    }
    await runCommand("git", ["clean", "-fd", "--", "."], { cwd: repoRoot });
    return;
  }
  if (workspaceView === "staged" && action === "unstage") {
    await runCommand("git", ["restore", "--staged", "--", "."], { cwd: repoRoot });
    return;
  }
  throw new Error("Unsupported bulk action for this view");
}
async function initializeGitRepository(cwd) {
  const normalizedCwd = normalizeInputCwd(cwd);
  await ensureDirectory(normalizedCwd);
  await runCommand("git", ["init"], { cwd: normalizedCwd });
}
async function applyReviewAction(payload) {
  const record = asRecord3(payload);
  if (!record) {
    throw new Error("Invalid body: expected object");
  }
  const cwd = readString3(record.cwd);
  const scope = record.scope === "baseBranch" ? "baseBranch" : record.scope === "commit" ? "commit" : "workspace";
  const workspaceView = record.workspaceView === "staged" ? "staged" : "unstaged";
  const action = readString3(record.action);
  const level = readString3(record.level);
  const patch = typeof record.patch === "string" ? record.patch : "";
  if (!cwd) {
    throw new Error("Missing cwd");
  }
  if (scope !== "workspace") {
    throw new Error("Review actions are only available for workspace changes");
  }
  if (action !== "stage" && action !== "unstage" && action !== "revert") {
    throw new Error("Invalid review action");
  }
  if (level !== "all" && level !== "file" && level !== "hunk") {
    throw new Error("Invalid review action level");
  }
  const normalizedCwd = normalizeInputCwd(cwd);
  await ensureDirectory(normalizedCwd);
  const repoRoot = await resolveGitRoot(normalizedCwd);
  if (!repoRoot) {
    throw new Error("Not a Git repository");
  }
  if (level === "all") {
    await applyAllAction(repoRoot, action, workspaceView);
  } else {
    if (!patch.trim()) {
      throw new Error("Missing patch payload");
    }
    await applyPatchAction(repoRoot, action, workspaceView, patch);
  }
  return await buildReviewSnapshot(normalizedCwd, scope, workspaceView);
}
async function handleReviewRoutes(req, res, url, context) {
  if (req.method === "GET" && url.pathname === "/codex-api/review/summary") {
    const cwd = url.searchParams.get("cwd")?.trim() ?? "";
    const workspaceView = url.searchParams.get("workspaceView") === "staged" ? "staged" : "unstaged";
    if (!cwd) {
      setJson2(res, 400, { error: "Missing cwd" });
      return true;
    }
    try {
      setJson2(res, 200, {
        data: await buildReviewSummary(cwd, workspaceView)
      });
    } catch (error) {
      setJson2(res, 500, { error: getErrorMessage3(error, "Failed to load review summary") });
    }
    return true;
  }
  if (req.method === "GET" && url.pathname === "/codex-api/review/snapshot") {
    const cwd = url.searchParams.get("cwd")?.trim() ?? "";
    const scope = url.searchParams.get("scope") === "baseBranch" ? "baseBranch" : url.searchParams.get("scope") === "commit" ? "commit" : "workspace";
    const workspaceView = url.searchParams.get("workspaceView") === "staged" ? "staged" : "unstaged";
    const baseBranch = url.searchParams.get("baseBranch")?.trim() ?? "";
    const commitSha = url.searchParams.get("commitSha")?.trim() ?? "";
    if (!cwd) {
      setJson2(res, 400, { error: "Missing cwd" });
      return true;
    }
    try {
      setJson2(res, 200, {
        data: await buildReviewSnapshot(cwd, scope, workspaceView, baseBranch, commitSha)
      });
    } catch (error) {
      setJson2(res, 500, { error: getErrorMessage3(error, "Failed to load review snapshot") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/review/action") {
    try {
      const payload = await context.readJsonBody(req);
      setJson2(res, 200, {
        data: await applyReviewAction(payload)
      });
    } catch (error) {
      setJson2(res, 500, { error: getErrorMessage3(error, "Failed to apply review action") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/review/git/init") {
    const payload = asRecord3(await context.readJsonBody(req));
    const cwd = readString3(payload?.cwd);
    if (!cwd) {
      setJson2(res, 400, { error: "Missing cwd" });
      return true;
    }
    try {
      await initializeGitRepository(cwd);
      setJson2(res, 200, { ok: true });
    } catch (error) {
      setJson2(res, 500, { error: getErrorMessage3(error, "Failed to initialize Git") });
    }
    return true;
  }
  return false;
}

// src/server/skillsRoutes.ts
import { spawn as spawn3 } from "child_process";
import { mkdtemp as mkdtemp2, readFile as readFile2, readdir, rm as rm3, mkdir as mkdir3, stat as stat3, lstat, readlink, symlink } from "fs/promises";
import { existsSync as existsSync2 } from "fs";
import { homedir as homedir3, tmpdir as tmpdir3 } from "os";
import { join as join4 } from "path";
import { writeFile as writeFile3 } from "fs/promises";

// src/utils/commandInvocation.ts
import { spawnSync as spawnSync2 } from "child_process";
import { basename, extname } from "path";
var WINDOWS_CMD_NAMES = /* @__PURE__ */ new Set(["codex", "npm", "npx"]);
function quoteCmdExeArg(value) {
  const normalized = value.replace(/"/g, '""');
  if (!/[\s"]/u.test(normalized)) {
    return normalized;
  }
  return `"${normalized}"`;
}
function needsCmdExeWrapper(command) {
  if (process.platform !== "win32") {
    return false;
  }
  const lowerCommand = command.toLowerCase();
  const baseName = basename(lowerCommand);
  if (/\.(cmd|bat)$/i.test(baseName)) {
    return true;
  }
  if (extname(baseName)) {
    return false;
  }
  return WINDOWS_CMD_NAMES.has(baseName);
}
function getSpawnInvocation(command, args = []) {
  if (needsCmdExeWrapper(command)) {
    return {
      command: "cmd.exe",
      args: ["/d", "/s", "/c", [quoteCmdExeArg(command), ...args.map((arg) => quoteCmdExeArg(arg))].join(" ")]
    };
  }
  return { command, args };
}
function spawnSyncCommand(command, args = [], options = {}) {
  const invocation = getSpawnInvocation(command, args);
  return spawnSync2(invocation.command, invocation.args, options);
}

// src/server/skillsRoutes.ts
function asRecord4(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function getErrorMessage4(payload, fallback) {
  if (payload instanceof Error && payload.message.trim().length > 0) {
    return payload.message;
  }
  const record = asRecord4(payload);
  if (!record) return fallback;
  const error = record.error;
  if (typeof error === "string" && error.length > 0) return error;
  const nestedError = asRecord4(error);
  if (nestedError && typeof nestedError.message === "string" && nestedError.message.length > 0) {
    return nestedError.message;
  }
  return fallback;
}
function setJson3(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}
function getCodexHomeDir2() {
  const codexHome = process.env.CODEX_HOME?.trim();
  return codexHome && codexHome.length > 0 ? codexHome : join4(homedir3(), ".codex");
}
function splitAbsolutePath(pathValue) {
  return pathValue.split("/").filter(Boolean);
}
function buildAbsolutePath(parts) {
  return `/${parts.join("/")}`;
}
function normalizeSkillMarkdownPath(skillPath) {
  if (!skillPath) return "";
  return skillPath.endsWith("/SKILL.md") ? skillPath : `${skillPath}/SKILL.md`;
}
function deriveSkillPathInfo(skillPath, knownPaths = /* @__PURE__ */ new Set()) {
  const normalizedPath = normalizeSkillMarkdownPath(skillPath);
  const parts = splitAbsolutePath(normalizedPath);
  if (parts.length < 2) return null;
  const pluginSkillsIndex = parts.lastIndexOf("skills");
  if (pluginSkillsIndex >= 2) {
    const pluginName = parts[pluginSkillsIndex - 2] ?? "";
    if (pluginName) {
      const rootSkillPath = buildAbsolutePath([...parts.slice(0, pluginSkillsIndex + 1), pluginName, "SKILL.md"]);
      if (knownPaths.has(rootSkillPath)) {
        return {
          normalizedPath,
          rootSkillPath,
          rootSkillName: pluginName,
          installDir: buildAbsolutePath(parts.slice(0, pluginSkillsIndex + 1)),
          isNestedSkill: normalizedPath !== rootSkillPath
        };
      }
    }
  }
  const firstSkillsIndex = parts.indexOf("skills");
  if (firstSkillsIndex < 0 || firstSkillsIndex + 1 >= parts.length - 1) return null;
  const rootSkillName = parts[firstSkillsIndex + 1] ?? "";
  if (!rootSkillName) return null;
  const rootParts = parts.slice(0, firstSkillsIndex + 2);
  const installDirParts = parts.slice(0, firstSkillsIndex + 1);
  return {
    normalizedPath,
    rootSkillPath: buildAbsolutePath([...rootParts, "SKILL.md"]),
    rootSkillName,
    installDir: buildAbsolutePath(installDirParts),
    isNestedSkill: normalizedPath !== buildAbsolutePath([...rootParts, "SKILL.md"])
  };
}
function getSkillsInstallDir() {
  return join4(getCodexHomeDir2(), "skills");
}
function getSharedSkillsInstallDir() {
  return join4(getSkillsInstallDir(), "shared_skills");
}
var DEFAULT_COMMAND_TIMEOUT_MS = 12e4;
var SKILL_SEARCH_METADATA_LIMIT = 20;
var SKILL_SEARCH_METADATA_CONCURRENCY = 4;
async function runCommand2(command, args, options = {}) {
  const timeout = options.timeoutMs ?? DEFAULT_COMMAND_TIMEOUT_MS;
  await new Promise((resolve4, reject) => {
    const invocation = getSpawnInvocation(command, args);
    const proc = spawn3(invocation.command, invocation.args, {
      cwd: options.cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let settled = false;
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      proc.kill("SIGKILL");
      reject(new Error(`Command timed out after ${timeout}ms (${command} ${args.join(" ")})`));
    }, timeout);
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(err);
    });
    proc.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (code === 0) {
        resolve4();
        return;
      }
      const details = [stderr.trim(), stdout.trim()].filter(Boolean).join("\n");
      const suffix = details.length > 0 ? `: ${details}` : "";
      reject(new Error(`Command failed (${command} ${args.join(" ")})${suffix}`));
    });
  });
}
async function runCommandWithOutput(command, args, options = {}) {
  const timeout = options.timeoutMs ?? DEFAULT_COMMAND_TIMEOUT_MS;
  return await new Promise((resolve4, reject) => {
    const invocation = getSpawnInvocation(command, args);
    const proc = spawn3(invocation.command, invocation.args, {
      cwd: options.cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let settled = false;
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      proc.kill("SIGKILL");
      reject(new Error(`Command timed out after ${timeout}ms (${command} ${args.join(" ")})`));
    }, timeout);
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(err);
    });
    proc.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (code === 0) {
        resolve4(stdout.trim());
        return;
      }
      const details = [stderr.trim(), stdout.trim()].filter(Boolean).join("\n");
      const suffix = details.length > 0 ? `: ${details}` : "";
      reject(new Error(`Command failed (${command} ${args.join(" ")})${suffix}`));
    });
  });
}
function withTimeout(promise, ms, label) {
  return new Promise((resolve4, reject) => {
    const timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
    promise.then(
      (val) => {
        clearTimeout(timer);
        resolve4(val);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      }
    );
  });
}
async function detectUserSkillsDir(appServer) {
  try {
    const result = await appServer.rpc("skills/list", {});
    for (const entry of result.data ?? []) {
      for (const skill of entry.skills ?? []) {
        if (skill.scope !== "user" || !skill.path) continue;
        const skillInfo = deriveSkillPathInfo(skill.path);
        if (!skillInfo) continue;
        return skillInfo.installDir;
      }
    }
  } catch {
  }
  return getSkillsInstallDir();
}
async function ensureInstalledSkillIsValid(appServer, skillPath) {
  const result = await appServer.rpc("skills/list", { forceReload: true });
  const normalized = skillPath.endsWith("/SKILL.md") ? skillPath : `${skillPath}/SKILL.md`;
  for (const entry of result.data ?? []) {
    for (const error of entry.errors ?? []) {
      if (error.path === normalized) {
        throw new Error(error.message || "Installed skill is invalid");
      }
    }
  }
}
async function runGitFetchWithRefLockRetry(repoDir, args = ["fetch", "origin"]) {
  try {
    await runCommand2("git", args, { cwd: repoDir });
  } catch (error) {
    const message = getErrorMessage4(error, "");
    if (!message.includes("cannot lock ref 'refs/remotes/origin/")) throw error;
    const branchMatch = message.match(/refs\/remotes\/origin\/([^\s':]+)/);
    if (!branchMatch?.[1]) throw error;
    const refPath = join4(repoDir, ".git", "refs", "remotes", "origin", branchMatch[1]);
    try {
      await rm3(refPath, { force: true });
    } catch {
    }
    await runCommand2("git", args, { cwd: repoDir });
  }
}
async function buildLocalHubEntry(info) {
  let description = "";
  if (info.path) {
    try {
      description = extractSkillDescriptionFromMarkdown(await readFile2(info.path, "utf8"));
    } catch {
    }
  }
  return {
    name: info.name,
    owner: "local",
    description,
    displayName: "",
    publishedAt: 0,
    avatarUrl: "",
    url: "",
    installed: true,
    path: info.path,
    enabled: info.enabled
  };
}
function stripAnsi(value) {
  return value.replace(/\x1B\[[0-?]*[ -/]*[@-~]/gu, "");
}
function parseNpxSkillsFindOutput(output, installedMap) {
  const lines = stripAnsi(output).split(/\r?\n/u).map((line) => line.trim()).filter(Boolean);
  const results = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const match = line.match(/^(.+?@[^@\s]+)\s+([\d.]+[KMB]?)\s+installs$/iu);
    if (!match) continue;
    const source = match[1]?.trim() ?? "";
    const installs = match[2]?.trim() ?? "";
    const atIndex = source.lastIndexOf("@");
    if (atIndex <= 0 || atIndex >= source.length - 1) continue;
    const owner = source.slice(0, atIndex);
    const name = source.slice(atIndex + 1);
    let url = "";
    const next = lines[index + 1] ?? "";
    const urlMatch = next.match(/(?:^└\s*)?(https?:\/\/\S+)$/u);
    if (urlMatch?.[1]) {
      url = urlMatch[1];
      index += 1;
    }
    const installedInfo = installedMap.get(name);
    results.push({
      name,
      owner,
      displayName: name,
      description: installs ? `${installs} installs` : "",
      installCountLabel: installs ? `${installs} installs` : "",
      publishedAt: 0,
      avatarUrl: "",
      url,
      installed: Boolean(installedInfo),
      source,
      path: installedInfo?.path,
      enabled: installedInfo?.enabled
    });
  }
  return results;
}
function parseGithubSkillSource(source) {
  const atIndex = source.lastIndexOf("@");
  if (atIndex <= 0 || atIndex >= source.length - 1) return null;
  const ownerRepo = source.slice(0, atIndex).trim();
  const skillName = source.slice(atIndex + 1).trim();
  const ownerRepoParts = ownerRepo.split("/").filter(Boolean);
  if (ownerRepoParts.length !== 2 || skillName.length === 0) return null;
  if (ownerRepoParts.some((part) => part.includes(":") || part.includes(" "))) return null;
  return { ownerRepo, skillName };
}
function getGithubOwnerAvatarUrl(source) {
  const parsed = parseGithubSkillSource(source);
  if (!parsed) return "";
  const owner = parsed.ownerRepo.split("/")[0] ?? "";
  return owner ? `https://github.com/${encodeURIComponent(owner)}.png?size=64` : "";
}
function buildGithubSkillRawCandidates(source) {
  const parsed = parseGithubSkillSource(source);
  if (!parsed) return [];
  const ownerRepo = parsed.ownerRepo.split("/").map(encodeURIComponent).join("/");
  const skillName = encodeURIComponent(parsed.skillName);
  const branches = ["main", "master"];
  const paths = [
    `skills/${skillName}/SKILL.md`,
    `${skillName}/SKILL.md`,
    "SKILL.md"
  ];
  return branches.flatMap((branch) => paths.map((path) => `https://raw.githubusercontent.com/${ownerRepo}/${branch}/${path}`));
}
async function fetchTextWithTimeout(url, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, {
      headers: { "User-Agent": "codex-web-local" },
      signal: controller.signal
    });
    if (!resp.ok) return "";
    return await resp.text();
  } finally {
    clearTimeout(timeout);
  }
}
function resolveSkillIconUrl(icon, markdownUrl) {
  const value = icon.trim().replace(/^['"]|['"]$/gu, "");
  if (!value) return "";
  if (/^https?:\/\//iu.test(value)) return value;
  try {
    return new URL(value, markdownUrl).toString();
  } catch {
    return "";
  }
}
async function fetchGithubSkillMetadata(source) {
  for (const candidate of buildGithubSkillRawCandidates(source)) {
    try {
      const markdown = await fetchTextWithTimeout(candidate, 4e3);
      if (!markdown) continue;
      const description = extractSkillDescriptionFromMarkdown(markdown);
      const icon = extractSkillFrontmatterField(markdown, "icon");
      const avatarUrl = icon ? resolveSkillIconUrl(icon, candidate) : getGithubOwnerAvatarUrl(source);
      if (description || avatarUrl) return { description, avatarUrl };
    } catch {
    }
  }
  return { avatarUrl: getGithubOwnerAvatarUrl(source) };
}
async function mapWithConcurrency(items, concurrency, mapper) {
  const results = new Array(items.length);
  let nextIndex = 0;
  const workerCount = Math.max(1, Math.min(concurrency, items.length));
  await Promise.all(Array.from({ length: workerCount }, async () => {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      results[index] = await mapper(items[index], index);
    }
  }));
  return results;
}
async function enrichSkillSearchDescriptions(results) {
  const enrichedHead = await mapWithConcurrency(
    results.slice(0, SKILL_SEARCH_METADATA_LIMIT),
    SKILL_SEARCH_METADATA_CONCURRENCY,
    async (result) => {
      if (!result.source) return result;
      const metadata = await fetchGithubSkillMetadata(result.source);
      return {
        ...result,
        description: metadata.description || result.description,
        avatarUrl: metadata.avatarUrl || result.avatarUrl
      };
    }
  );
  return [...enrichedHead, ...results.slice(SKILL_SEARCH_METADATA_LIMIT)];
}
function groupRpcSkillRecords(skills) {
  const normalizedPathSet = new Set(
    skills.map((skill) => normalizeSkillMarkdownPath(typeof skill.path === "string" ? skill.path : "")).filter(Boolean)
  );
  const grouped = /* @__PURE__ */ new Map();
  for (const skill of skills) {
    const rawPath = typeof skill.path === "string" ? skill.path : "";
    const pathInfo = rawPath ? deriveSkillPathInfo(rawPath, normalizedPathSet) : null;
    const groupingKey = pathInfo && pathInfo.isNestedSkill && normalizedPathSet.has(pathInfo.rootSkillPath) ? pathInfo.rootSkillPath : pathInfo?.normalizedPath || rawPath || `${skill.scope ?? ""}:${skill.name ?? ""}`;
    const existing = grouped.get(groupingKey);
    const isRootEntry = pathInfo?.normalizedPath === groupingKey;
    const groupedName = pathInfo && groupingKey === pathInfo.rootSkillPath ? pathInfo.rootSkillName : skill.name;
    if (!existing) {
      grouped.set(groupingKey, {
        preferred: isRootEntry ? {
          ...skill,
          name: groupedName,
          path: groupingKey
        } : {
          ...skill,
          name: groupedName,
          path: groupingKey
        },
        hasRoot: isRootEntry,
        anyEnabled: skill.enabled !== false
      });
      continue;
    }
    existing.anyEnabled = existing.anyEnabled || skill.enabled !== false;
    if (!existing.hasRoot && isRootEntry) {
      existing.preferred = {
        ...skill,
        name: groupedName,
        path: groupingKey
      };
      existing.hasRoot = true;
      continue;
    }
    if (!existing.preferred.description && skill.description) {
      existing.preferred = { ...existing.preferred, description: skill.description };
    }
    if (!existing.preferred.shortDescription && skill.shortDescription) {
      existing.preferred = { ...existing.preferred, shortDescription: skill.shortDescription };
    }
  }
  return Array.from(grouped.values()).map(({ preferred, anyEnabled }) => ({
    ...preferred,
    enabled: preferred.enabled ?? anyEnabled
  }));
}
var GITHUB_DEVICE_CLIENT_ID = "Iv1.b507a08c87ecfe98";
var DEFAULT_SKILLS_SYNC_REPO_NAME = "codexskills";
var SKILLS_SYNC_MANIFEST_PATH = "installed-skills.json";
var SYNC_UPSTREAM_SKILLS_OWNER = "OpenClawAndroid";
var SYNC_UPSTREAM_SKILLS_REPO = "skills";
var PRIVATE_SYNC_BRANCH = "main";
var PUBLIC_UPSTREAM_BRANCH_ANDROID = "android";
var PUBLIC_UPSTREAM_BRANCH_DEFAULT = "main";
var startupSkillsSyncInitialized = false;
var startupSyncStatus = {
  inProgress: false,
  mode: "idle",
  branch: PRIVATE_SYNC_BRANCH,
  lastAction: "not-started",
  lastRunAtIso: "",
  lastSuccessAtIso: "",
  lastError: ""
};
async function scanInstalledSkillsFromDir(skillsDir) {
  const map = /* @__PURE__ */ new Map();
  try {
    const entries = await readdir(skillsDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
      const skillMd = join4(skillsDir, entry.name, "SKILL.md");
      try {
        await stat3(skillMd);
        map.set(entry.name, { name: entry.name, path: skillMd, enabled: true });
      } catch {
      }
    }
  } catch {
  }
  return map;
}
async function scanInstalledSkillsFromDisk() {
  return await scanInstalledSkillsFromDir(getSkillsInstallDir());
}
async function collectInstalledSkillsMap(appServer) {
  const installedMap = await scanInstalledSkillsFromDisk();
  try {
    const result = await appServer.rpc("skills/list", {});
    for (const entry of result.data ?? []) {
      for (const skill of groupRpcSkillRecords(entry.skills ?? [])) {
        if (skill.name) {
          installedMap.set(skill.name, { name: skill.name, path: skill.path ?? "", enabled: skill.enabled !== false });
        }
      }
    }
  } catch {
  }
  return installedMap;
}
function extractSkillFrontmatterField(markdown, fieldName) {
  const lines = markdown.split(/\r?\n/);
  if (lines[0]?.trim() !== "---") return "";
  const frontmatter = [];
  for (let index = 1; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    if (line.trim() === "---") break;
    frontmatter.push(line);
  }
  const escapedFieldName = fieldName.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const fieldPattern = new RegExp(`^${escapedFieldName}\\s*:`, "iu");
  const valuePattern = new RegExp(`^${escapedFieldName}\\s*:\\s*`, "iu");
  const fieldLine = frontmatter.find((line) => fieldPattern.test(line.trim()));
  if (!fieldLine) return "";
  return fieldLine.replace(valuePattern, "").replace(/^['"]|['"]$/gu, "").trim();
}
function extractSkillDescriptionFromMarkdown(markdown) {
  const frontmatterDescription = extractSkillFrontmatterField(markdown, "description");
  if (frontmatterDescription) return frontmatterDescription;
  const lines = markdown.split(/\r?\n/);
  let inCodeFence = false;
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line.startsWith("```")) {
      inCodeFence = !inCodeFence;
      continue;
    }
    if (inCodeFence || line.length === 0) continue;
    if (line.startsWith("#")) continue;
    if (line.startsWith(">")) continue;
    if (line.startsWith("- ") || line.startsWith("* ")) continue;
    return line;
  }
  return "";
}
function getSkillsSyncStatePath() {
  return join4(getCodexHomeDir2(), "skills-sync.json");
}
async function readSkillsSyncState() {
  try {
    const raw = await readFile2(getSkillsSyncStatePath(), "utf8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}
async function writeSkillsSyncState(state) {
  await writeFile3(getSkillsSyncStatePath(), JSON.stringify(state), "utf8");
}
async function getGithubJson(url, token, method = "GET", body) {
  const resp = await fetch(url, {
    method,
    headers: {
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "codex-web-local"
    },
    body: body ? JSON.stringify(body) : void 0
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`GitHub API ${method} ${url} failed (${resp.status}): ${text}`);
  }
  return await resp.json();
}
async function startGithubDeviceLogin() {
  const resp = await fetch("https://github.com/login/device/code", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": "codex-web-local"
    },
    body: new URLSearchParams({
      client_id: GITHUB_DEVICE_CLIENT_ID,
      scope: "repo read:user"
    })
  });
  if (!resp.ok) {
    throw new Error(`GitHub device flow init failed (${resp.status})`);
  }
  return await resp.json();
}
async function completeGithubDeviceLogin(deviceCode) {
  const resp = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": "codex-web-local"
    },
    body: new URLSearchParams({
      client_id: GITHUB_DEVICE_CLIENT_ID,
      device_code: deviceCode,
      grant_type: "urn:ietf:params:oauth:grant-type:device_code"
    })
  });
  if (!resp.ok) {
    throw new Error(`GitHub token exchange failed (${resp.status})`);
  }
  const payload = await resp.json();
  if (!payload.access_token) return { token: null, error: payload.error || "unknown_error" };
  return { token: payload.access_token, error: null };
}
function isAndroidLikeRuntime() {
  if (process.platform === "android") return true;
  if (existsSync2("/data/data/com.termux")) return true;
  if (process.env.TERMUX_VERSION) return true;
  const prefix = process.env.PREFIX?.toLowerCase() ?? "";
  if (prefix.includes("/com.termux/")) return true;
  const proot = process.env.PROOT_TMP_DIR?.toLowerCase() ?? "";
  return proot.length > 0;
}
function getPreferredPublicUpstreamBranch() {
  return isAndroidLikeRuntime() ? PUBLIC_UPSTREAM_BRANCH_ANDROID : PUBLIC_UPSTREAM_BRANCH_DEFAULT;
}
function isUpstreamSkillsRepo(repoOwner, repoName) {
  return repoOwner.toLowerCase() === SYNC_UPSTREAM_SKILLS_OWNER.toLowerCase() && repoName.toLowerCase() === SYNC_UPSTREAM_SKILLS_REPO.toLowerCase();
}
async function resolveGithubUsername(token) {
  const user = await getGithubJson("https://api.github.com/user", token);
  return user.login;
}
async function ensurePrivateForkFromUpstream(token, username, repoName) {
  const repoUrl = `https://api.github.com/repos/${username}/${repoName}`;
  let created = false;
  const existing = await fetch(repoUrl, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "codex-web-local"
    }
  });
  if (existing.ok) {
    const details = await existing.json();
    if (details.private === true) return;
    await getGithubJson(repoUrl, token, "PATCH", { private: true });
    return;
  }
  if (existing.status !== 404) {
    throw new Error(`Failed to check personal repo existence (${existing.status})`);
  }
  await getGithubJson(
    "https://api.github.com/user/repos",
    token,
    "POST",
    { name: repoName, private: true, auto_init: false, description: "Codex skills private mirror sync" }
  );
  created = true;
  let ready = false;
  for (let i = 0; i < 20; i++) {
    const check = await fetch(repoUrl, {
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "codex-web-local"
      }
    });
    if (check.ok) {
      ready = true;
      break;
    }
    await new Promise((resolve4) => setTimeout(resolve4, 1e3));
  }
  if (!ready) throw new Error("Private mirror repo was created but is not available yet");
  if (!created) return;
  const tmp = await mkdtemp2(join4(tmpdir3(), "codex-skills-seed-"));
  try {
    const upstreamUrl = `https://github.com/${SYNC_UPSTREAM_SKILLS_OWNER}/${SYNC_UPSTREAM_SKILLS_REPO}.git`;
    const branch = PRIVATE_SYNC_BRANCH;
    try {
      await runCommand2("git", ["clone", "--depth", "1", "--single-branch", "--branch", branch, upstreamUrl, tmp]);
    } catch {
      await runCommand2("git", ["clone", "--depth", "1", upstreamUrl, tmp]);
    }
    const privateRemote = toGitHubTokenRemote(username, repoName, token);
    await runCommand2("git", ["remote", "set-url", "origin", privateRemote], { cwd: tmp });
    try {
      await runCommand2("git", ["checkout", "-B", branch], { cwd: tmp });
    } catch {
    }
    await runCommand2("git", ["push", "-u", "origin", `HEAD:${branch}`], { cwd: tmp });
  } finally {
    await rm3(tmp, { recursive: true, force: true });
  }
}
async function readRemoteSkillsManifest(token, repoOwner, repoName) {
  const url = `https://api.github.com/repos/${repoOwner}/${repoName}/contents/${SKILLS_SYNC_MANIFEST_PATH}`;
  const resp = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "codex-web-local"
    }
  });
  if (resp.status === 404) return [];
  if (!resp.ok) throw new Error(`Failed to read remote manifest (${resp.status})`);
  const payload = await resp.json();
  const content = payload.content ? Buffer.from(payload.content.replace(/\n/g, ""), "base64").toString("utf8") : "[]";
  const parsed = JSON.parse(content);
  if (!Array.isArray(parsed)) return [];
  const skills = [];
  for (const row of parsed) {
    const item = asRecord4(row);
    const owner = typeof item?.owner === "string" ? item.owner : "";
    const name = typeof item?.name === "string" ? item.name : "";
    if (!name) continue;
    skills.push({ ...owner ? { owner } : {}, name, enabled: item?.enabled !== false });
  }
  return skills;
}
async function writeRemoteSkillsManifest(token, repoOwner, repoName, skills) {
  const url = `https://api.github.com/repos/${repoOwner}/${repoName}/contents/${SKILLS_SYNC_MANIFEST_PATH}`;
  let sha = "";
  const nextContent = JSON.stringify(skills, null, 2);
  const existing = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "codex-web-local"
    }
  });
  if (existing.ok) {
    const payload = await existing.json();
    sha = payload.sha ?? "";
    const currentContent = payload.content ? Buffer.from(payload.content.replace(/\n/g, ""), "base64").toString("utf8") : "";
    if (currentContent === nextContent) return false;
  }
  const content = Buffer.from(nextContent, "utf8").toString("base64");
  await getGithubJson(url, token, "PUT", {
    message: "Update synced skills manifest",
    content,
    ...sha ? { sha } : {}
  });
  return true;
}
function toGitHubTokenRemote(repoOwner, repoName, token) {
  return `https://x-access-token:${encodeURIComponent(token)}@github.com/${repoOwner}/${repoName}.git`;
}
async function ensureSkillsWorkingTreeRepo(repoUrl, branch, options = {}) {
  const localDir = options.localDir ?? getSkillsInstallDir();
  await mkdir3(localDir, { recursive: true });
  const gitDir = join4(localDir, ".git");
  let hasGitDir = false;
  try {
    const gitDirStat = await lstat(gitDir);
    hasGitDir = gitDirStat.isDirectory() || gitDirStat.isFile();
  } catch {
    hasGitDir = false;
  }
  if (!hasGitDir) {
    await runCommand2("git", ["init"], { cwd: localDir });
    await runCommand2("git", ["config", "user.email", "skills-sync@local"], { cwd: localDir });
    await runCommand2("git", ["config", "user.name", "Skills Sync"], { cwd: localDir });
    await runCommand2("git", ["add", "-A"], { cwd: localDir });
    try {
      await runCommand2("git", ["commit", "-m", "Local skills snapshot before sync"], { cwd: localDir });
    } catch {
    }
    await runCommand2("git", ["branch", "-M", branch], { cwd: localDir });
    try {
      await runCommand2("git", ["remote", "add", "origin", repoUrl], { cwd: localDir });
    } catch {
      await runCommand2("git", ["remote", "set-url", "origin", repoUrl], { cwd: localDir });
    }
    await runGitFetchWithRefLockRetry(localDir);
    if (options.overwriteLocalFiles) {
      await runCommand2("git", ["reset", "--hard"], { cwd: localDir });
      await runCommand2("git", ["clean", "-fd"], { cwd: localDir });
      await runCommand2("git", ["checkout", "-B", branch, `origin/${branch}`], { cwd: localDir });
      await runCommand2("git", ["reset", "--hard", `origin/${branch}`], { cwd: localDir });
      await runCommand2("git", ["clean", "-fd"], { cwd: localDir });
      return localDir;
    }
    try {
      await runCommand2("git", ["merge", "--allow-unrelated-histories", "--no-edit", `origin/${branch}`], { cwd: localDir });
    } catch {
    }
    return localDir;
  }
  await runCommand2("git", ["remote", "set-url", "origin", repoUrl], { cwd: localDir });
  await runGitFetchWithRefLockRetry(localDir);
  if (options.overwriteLocalFiles) {
    try {
      await runCommand2("git", ["reset", "--hard"], { cwd: localDir });
    } catch {
    }
    await runCommand2("git", ["clean", "-fd"], { cwd: localDir });
    await runCommand2("git", ["checkout", "-B", branch, `origin/${branch}`], { cwd: localDir });
    await runCommand2("git", ["reset", "--hard", `origin/${branch}`], { cwd: localDir });
    await runCommand2("git", ["clean", "-fd"], { cwd: localDir });
    return localDir;
  }
  const hasLocalChangesBeforeSync = await hasLocalUncommittedChanges(localDir);
  const localMtimesBeforeSync = hasLocalChangesBeforeSync ? await snapshotFileMtimes(localDir) : /* @__PURE__ */ new Map();
  await resolveMergeConflictsByNewerCommit(localDir, branch, localMtimesBeforeSync);
  try {
    await runCommand2("git", ["checkout", branch], { cwd: localDir });
  } catch {
    await resolveMergeConflictsByNewerCommit(localDir, branch, localMtimesBeforeSync);
    await runCommand2("git", ["checkout", "-B", branch], { cwd: localDir });
  }
  await resolveMergeConflictsByNewerCommit(localDir, branch, localMtimesBeforeSync);
  const hasLocalChangesBeforePull = await hasLocalUncommittedChanges(localDir);
  const localMtimesBeforePull = hasLocalChangesBeforePull ? await snapshotFileMtimes(localDir) : /* @__PURE__ */ new Map();
  let createdAutostash = false;
  try {
    const stashOutput = await runCommandWithOutput("git", ["stash", "push", "--include-untracked", "-m", "codex-skills-autostash"], { cwd: localDir });
    createdAutostash = !stashOutput.includes("No local changes to save");
  } catch {
  }
  let pulledMtimes = /* @__PURE__ */ new Map();
  await runGitFetchWithRefLockRetry(localDir, ["fetch", "origin", branch]);
  await runCommand2("git", ["reset", "--hard", `origin/${branch}`], { cwd: localDir });
  pulledMtimes = await snapshotFileMtimes(localDir);
  if (createdAutostash) {
    try {
      await runCommand2("git", ["stash", "pop"], { cwd: localDir });
    } catch {
      await resolveStashPopConflictsByFileTime(localDir, localMtimesBeforePull, pulledMtimes);
    }
  }
  return localDir;
}
async function resolveMergeConflictsByNewerCommit(repoDir, branch, localMtimesBeforeSync = /* @__PURE__ */ new Map()) {
  for (let i = 0; i < 20; i++) {
    const unmerged = (await runCommandWithOutput("git", ["diff", "--name-only", "--diff-filter=U"], { cwd: repoDir })).split(/\r?\n/).map((row) => row.trim()).filter(Boolean);
    if (unmerged.length === 0) return;
    for (const path of unmerged) {
      const localMtimeMs = localMtimesBeforeSync.get(path) ?? 0;
      const localMtimeSec = Math.floor(localMtimeMs / 1e3);
      const remoteCommitTime = await getCommitTime(repoDir, `origin/${branch}`, path);
      if (remoteCommitTime > localMtimeSec) {
        await checkoutConflictSideWithFallback(repoDir, path, "--theirs");
      } else {
        await checkoutConflictSideWithFallback(repoDir, path, "--ours");
      }
      await runCommand2("git", ["add", "--", path], { cwd: repoDir });
    }
    const rebaseHead = await readOptionalGitRef(repoDir, "REBASE_HEAD");
    if (rebaseHead) {
      try {
        await runCommand2("git", ["rebase", "--continue"], { cwd: repoDir });
        continue;
      } catch {
        continue;
      }
    }
    const mergeHead = await readOptionalGitRef(repoDir, "MERGE_HEAD");
    if (mergeHead) {
      await runCommand2("git", ["commit", "-m", "Auto-resolve skills merge by mtime policy"], { cwd: repoDir });
      continue;
    }
  }
  throw new Error("Auto-resolve exceeded retry limit while reconciling sync conflicts");
}
async function readOptionalGitRef(repoDir, ref) {
  try {
    return (await runCommandWithOutput("git", ["rev-parse", "-q", "--verify", ref], { cwd: repoDir })).trim();
  } catch {
    return "";
  }
}
async function listUnmergedStages(repoDir, path) {
  const raw = (await runCommandWithOutput("git", ["ls-files", "-u", "--", path], { cwd: repoDir })).trim();
  const stages = /* @__PURE__ */ new Set();
  if (!raw) return stages;
  for (const line of raw.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    const stage = Number.parseInt(parts[2] ?? "", 10);
    if (Number.isInteger(stage)) stages.add(stage);
  }
  return stages;
}
async function checkoutConflictSideWithFallback(repoDir, path, preferredSide) {
  const stages = await listUnmergedStages(repoDir, path);
  const hasOurs = stages.has(2);
  const hasTheirs = stages.has(3);
  if (!hasOurs && !hasTheirs) return;
  if (preferredSide === "--ours") {
    if (hasOurs) {
      await runCommand2("git", ["checkout", "--ours", "--", path], { cwd: repoDir });
      return;
    }
    await runCommand2("git", ["checkout", "--theirs", "--", path], { cwd: repoDir });
    return;
  }
  if (hasTheirs) {
    await runCommand2("git", ["checkout", "--theirs", "--", path], { cwd: repoDir });
    return;
  }
  await runCommand2("git", ["checkout", "--ours", "--", path], { cwd: repoDir });
}
async function getCommitTime(repoDir, ref, path) {
  try {
    const output = (await runCommandWithOutput("git", ["log", "-1", "--format=%ct", ref, "--", path], { cwd: repoDir })).trim();
    return output ? Number.parseInt(output, 10) : 0;
  } catch {
    return 0;
  }
}
async function resolveStashPopConflictsByFileTime(repoDir, localMtimesBeforePull, pulledMtimes) {
  const unmerged = (await runCommandWithOutput("git", ["diff", "--name-only", "--diff-filter=U"], { cwd: repoDir })).split(/\r?\n/).map((row) => row.trim()).filter(Boolean);
  if (unmerged.length === 0) return;
  for (const path of unmerged) {
    const localMtime = localMtimesBeforePull.get(path) ?? 0;
    const pulledMtime = pulledMtimes.get(path) ?? 0;
    const side = localMtime >= pulledMtime ? "--theirs" : "--ours";
    await checkoutConflictSideWithFallback(repoDir, path, side);
    await runCommand2("git", ["add", "--", path], { cwd: repoDir });
  }
  const mergeHead = await readOptionalGitRef(repoDir, "MERGE_HEAD");
  if (mergeHead) {
    await runCommand2("git", ["commit", "-m", "Auto-resolve stash-pop conflicts by file time"], { cwd: repoDir });
  }
}
async function snapshotFileMtimes(dir) {
  const mtimes = /* @__PURE__ */ new Map();
  await walkFileMtimes(dir, dir, mtimes);
  return mtimes;
}
async function hasLocalUncommittedChanges(repoDir) {
  const status = (await runCommandWithOutput("git", ["status", "--porcelain"], { cwd: repoDir })).trim();
  return status.length > 0;
}
async function hasCommittableWorkingTreeChanges(repoDir) {
  try {
    await runCommand2("git", ["diff", "--quiet", "--exit-code", "--ignore-submodules=dirty"], { cwd: repoDir });
    await runCommand2("git", ["diff", "--cached", "--quiet", "--exit-code", "--ignore-submodules=dirty"], { cwd: repoDir });
  } catch {
    return true;
  }
  const untracked = (await runCommandWithOutput("git", ["ls-files", "--others", "--exclude-standard"], { cwd: repoDir })).trim();
  return untracked.length > 0;
}
async function walkFileMtimes(rootDir, currentDir, out) {
  let entries;
  try {
    entries = await readdir(currentDir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const entryName = String(entry.name);
    if (entryName === ".git") continue;
    const absolutePath = join4(currentDir, entryName);
    const relativePath = absolutePath.slice(rootDir.length + 1);
    if (entry.isDirectory()) {
      await walkFileMtimes(rootDir, absolutePath, out);
      continue;
    }
    if (!entry.isFile()) continue;
    try {
      const info = await stat3(absolutePath);
      out.set(relativePath, info.mtimeMs);
    } catch {
    }
  }
}
async function syncInstalledSkillsFolderToRepo(token, repoOwner, repoName, _installedMap) {
  async function hasTrackedLocalFileChanges(repoDir2, filePath) {
    const diffHead = (await runCommandWithOutput("git", ["diff", "--name-only", "HEAD", "--", filePath], { cwd: repoDir2 })).trim();
    if (diffHead.length > 0) return true;
    const diffCached = (await runCommandWithOutput("git", ["diff", "--cached", "--name-only", "--", filePath], { cwd: repoDir2 })).trim();
    return diffCached.length > 0;
  }
  async function restoreProtectedFilesFromOrigin(repoDir2, branch2) {
    const protectedFiles = ["AGENTS.md"];
    for (const filePath of protectedFiles) {
      const hasLocalEdits = await hasTrackedLocalFileChanges(repoDir2, filePath);
      if (hasLocalEdits) continue;
      try {
        await runCommand2("git", ["cat-file", "-e", `origin/${branch2}:${filePath}`], { cwd: repoDir2 });
      } catch {
        continue;
      }
      await runCommand2("git", ["checkout", `origin/${branch2}`, "--", filePath], { cwd: repoDir2 });
    }
    try {
      await runCommand2("git", ["cat-file", "-e", `origin/${branch2}:shared_skills`], { cwd: repoDir2 });
      await runCommand2("git", ["checkout", `origin/${branch2}`, "--", "shared_skills"], { cwd: repoDir2 });
    } catch {
    }
  }
  function isNonFastForwardPushError(error) {
    const text = getErrorMessage4(error, "").toLowerCase();
    return text.includes("non-fast-forward") || text.includes("fetch first") || text.includes("rejected") && text.includes("push");
  }
  async function pushWithNonFastForwardRetry(repoDir2, branch2) {
    const maxAttempts = 3;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const hasLocalChangesBeforeReconcile = await hasLocalUncommittedChanges(repoDir2);
      const localMtimesBeforeReconcile = hasLocalChangesBeforeReconcile ? await snapshotFileMtimes(repoDir2) : /* @__PURE__ */ new Map();
      await runGitFetchWithRefLockRetry(repoDir2);
      try {
        await runCommand2("git", ["rebase", `origin/${branch2}`], { cwd: repoDir2 });
      } catch {
        try {
          await runCommand2("git", ["rebase", "--abort"], { cwd: repoDir2 });
        } catch {
        }
        try {
          await runCommand2("git", ["pull", "--rebase", "--autostash", "origin", branch2], { cwd: repoDir2 });
        } catch {
          await resolveMergeConflictsByNewerCommit(repoDir2, branch2, localMtimesBeforeReconcile);
          await runCommand2("git", ["pull", "--rebase", "--autostash", "origin", branch2], { cwd: repoDir2 });
        }
      }
      try {
        await runCommand2("git", ["push", "--no-recurse-submodules", "origin", `HEAD:${branch2}`], { cwd: repoDir2 });
        const state = await readSkillsSyncState();
        const pushedHead = await runCommandWithOutput("git", ["rev-parse", "HEAD"], { cwd: repoDir2 });
        await writeSkillsSyncState({
          ...state,
          lastPushCommitSha: pushedHead.trim(),
          lastSyncAttemptCount: attempt,
          lastSyncError: "",
          lastSyncAtIso: (/* @__PURE__ */ new Date()).toISOString()
        });
        return;
      } catch (error) {
        if (!isNonFastForwardPushError(error) || attempt >= maxAttempts) {
          const state = await readSkillsSyncState();
          await writeSkillsSyncState({
            ...state,
            lastSyncAttemptCount: attempt,
            lastSyncError: getErrorMessage4(error, "push failed"),
            lastSyncAtIso: (/* @__PURE__ */ new Date()).toISOString()
          });
          throw error;
        }
      }
    }
    throw new Error("Failed to push after non-fast-forward retries");
  }
  const remoteUrl = toGitHubTokenRemote(repoOwner, repoName, token);
  const branch = PRIVATE_SYNC_BRANCH;
  const repoDir = await ensureSkillsWorkingTreeRepo(remoteUrl, branch);
  void _installedMap;
  await runCommand2("git", ["config", "user.email", "skills-sync@local"], { cwd: repoDir });
  await runCommand2("git", ["config", "user.name", "Skills Sync"], { cwd: repoDir });
  await restoreProtectedFilesFromOrigin(repoDir, branch);
  await runCommand2("git", ["add", "."], { cwd: repoDir });
  try {
    await runCommand2("git", ["diff", "--cached", "--quiet", "--exit-code"], { cwd: repoDir });
    return;
  } catch {
  }
  await runCommand2("git", ["commit", "-m", "Sync installed skills folder and manifest"], { cwd: repoDir });
  await pushWithNonFastForwardRetry(repoDir, branch);
}
async function pullInstalledSkillsFolderFromRepo(token, repoOwner, repoName) {
  const remoteUrl = toGitHubTokenRemote(repoOwner, repoName, token);
  const isUpstream = isUpstreamSkillsRepo(repoOwner, repoName);
  const branch = isUpstream ? PUBLIC_UPSTREAM_BRANCH_ANDROID : PRIVATE_SYNC_BRANCH;
  return await ensureSkillsWorkingTreeRepo(remoteUrl, branch, {
    ...isUpstream ? { localDir: getSharedSkillsInstallDir() } : {},
    overwriteLocalFiles: isUpstream
  });
}
async function bootstrapSkillsFromUpstreamIntoLocal() {
  const repoUrl = `https://github.com/${SYNC_UPSTREAM_SKILLS_OWNER}/${SYNC_UPSTREAM_SKILLS_REPO}.git`;
  return await ensureSkillsWorkingTreeRepo(repoUrl, PUBLIC_UPSTREAM_BRANCH_ANDROID, {
    localDir: getSharedSkillsInstallDir(),
    overwriteLocalFiles: true
  });
}
async function collectLocalSyncedSkills(appServer) {
  const state = await readSkillsSyncState();
  const owners = { ...state.installedOwners ?? {} };
  const skills = await appServer.rpc("skills/list", {});
  const seen = /* @__PURE__ */ new Set();
  const synced = [];
  let ownersChanged = false;
  for (const entry of skills.data ?? []) {
    for (const skill of groupRpcSkillRecords(entry.skills ?? [])) {
      const name = typeof skill.name === "string" ? skill.name : "";
      if (!name || skill.scope !== "user" || seen.has(name)) continue;
      seen.add(name);
      const owner = owners[name] ?? "";
      synced.push({ ...owner ? { owner } : {}, name, enabled: skill.enabled !== false });
    }
  }
  if (ownersChanged) {
    await writeSkillsSyncState({ ...state, installedOwners: owners });
  }
  synced.sort((a, b) => `${a.owner ?? ""}/${a.name}`.localeCompare(`${b.owner ?? ""}/${b.name}`));
  return synced;
}
async function autoPushSyncedSkills(appServer) {
  const state = await readSkillsSyncState();
  if (!state.githubToken || !state.repoOwner || !state.repoName) return;
  if (isUpstreamSkillsRepo(state.repoOwner, state.repoName)) {
    throw new Error("Refusing to push to upstream skills repository");
  }
  const repoDir = getSkillsInstallDir();
  await runCommand2("git", ["fetch", "origin", PRIVATE_SYNC_BRANCH], { cwd: repoDir });
  const head = (await runCommandWithOutput("git", ["rev-parse", "HEAD"], { cwd: repoDir })).trim();
  const originHead = (await runCommandWithOutput("git", ["rev-parse", `origin/${PRIVATE_SYNC_BRANCH}`], { cwd: repoDir })).trim();
  const hasCommittableChanges = await hasCommittableWorkingTreeChanges(repoDir);
  if (!hasCommittableChanges && head === originHead) return;
  const local = await collectLocalSyncedSkills(appServer);
  const installedMap = await scanInstalledSkillsFromDisk();
  await writeRemoteSkillsManifest(state.githubToken, state.repoOwner, state.repoName, local);
  await syncInstalledSkillsFolderToRepo(state.githubToken, state.repoOwner, state.repoName, installedMap);
}
async function ensureCodexAgentsSymlinkToSkillsAgents() {
  const codexHomeDir = getCodexHomeDir2();
  const skillsAgentsPath = join4(codexHomeDir, "skills", "AGENTS.md");
  const codexAgentsPath = join4(codexHomeDir, "AGENTS.md");
  await mkdir3(join4(codexHomeDir, "skills"), { recursive: true });
  let copiedFromCodex = false;
  try {
    const codexAgentsStat = await lstat(codexAgentsPath);
    if (codexAgentsStat.isFile() || codexAgentsStat.isSymbolicLink()) {
      const content = await readFile2(codexAgentsPath, "utf8");
      await writeFile3(skillsAgentsPath, content, "utf8");
      copiedFromCodex = true;
    } else {
      await rm3(codexAgentsPath, { force: true, recursive: true });
    }
  } catch {
  }
  if (!copiedFromCodex) {
    try {
      const skillsAgentsStat = await stat3(skillsAgentsPath);
      if (!skillsAgentsStat.isFile()) {
        await rm3(skillsAgentsPath, { force: true, recursive: true });
        await writeFile3(skillsAgentsPath, "", "utf8");
      }
    } catch {
      await writeFile3(skillsAgentsPath, "", "utf8");
    }
  }
  const relativeTarget = join4("skills", "AGENTS.md");
  try {
    const current = await lstat(codexAgentsPath);
    if (current.isSymbolicLink()) {
      const existingTarget = await readlink(codexAgentsPath);
      if (existingTarget === relativeTarget) return;
    }
    await rm3(codexAgentsPath, { force: true, recursive: true });
  } catch {
  }
  await symlink(relativeTarget, codexAgentsPath);
}
async function runSkillsSyncStartup(appServer) {
  if (startupSyncStatus.inProgress) return;
  startupSyncStatus.inProgress = true;
  startupSyncStatus.lastRunAtIso = (/* @__PURE__ */ new Date()).toISOString();
  startupSyncStatus.lastError = "";
  startupSyncStatus.branch = PRIVATE_SYNC_BRANCH;
  try {
    const state = await readSkillsSyncState();
    if (!state.githubToken) {
      await ensureCodexAgentsSymlinkToSkillsAgents();
      if (!isAndroidLikeRuntime()) {
        startupSyncStatus.mode = "idle";
        startupSyncStatus.lastAction = "skip-upstream-non-android";
        startupSyncStatus.lastSuccessAtIso = (/* @__PURE__ */ new Date()).toISOString();
        return;
      }
      startupSyncStatus.mode = "unauthenticated-bootstrap";
      startupSyncStatus.branch = getPreferredPublicUpstreamBranch();
      startupSyncStatus.lastAction = "pull-upstream";
      await bootstrapSkillsFromUpstreamIntoLocal();
      try {
        await appServer.rpc("skills/list", { forceReload: true });
      } catch {
      }
      startupSyncStatus.lastSuccessAtIso = (/* @__PURE__ */ new Date()).toISOString();
      startupSyncStatus.lastAction = "pull-upstream-complete";
      return;
    }
    startupSyncStatus.mode = "authenticated-fork-sync";
    startupSyncStatus.branch = PRIVATE_SYNC_BRANCH;
    startupSyncStatus.lastAction = "ensure-private-fork";
    const username = state.githubUsername || await resolveGithubUsername(state.githubToken);
    const repoName = DEFAULT_SKILLS_SYNC_REPO_NAME;
    await ensurePrivateForkFromUpstream(state.githubToken, username, repoName);
    await writeSkillsSyncState({ ...state, githubUsername: username, repoOwner: username, repoName });
    startupSyncStatus.lastAction = "pull-private-fork";
    await pullInstalledSkillsFolderFromRepo(state.githubToken, username, repoName);
    try {
      await appServer.rpc("skills/list", { forceReload: true });
    } catch {
    }
    startupSyncStatus.lastAction = "push-private-fork";
    await autoPushSyncedSkills(appServer);
    startupSyncStatus.lastSuccessAtIso = (/* @__PURE__ */ new Date()).toISOString();
    startupSyncStatus.lastAction = "startup-sync-complete";
  } catch (error) {
    startupSyncStatus.lastError = getErrorMessage4(error, "startup-sync-failed");
    startupSyncStatus.lastAction = "startup-sync-failed";
  } finally {
    startupSyncStatus.inProgress = false;
  }
}
async function initializeSkillsSyncOnStartup(appServer) {
  if (startupSkillsSyncInitialized) return;
  startupSkillsSyncInitialized = true;
  await runSkillsSyncStartup(appServer);
}
async function finalizeGithubLoginAndSync(token, username, appServer) {
  const repoName = DEFAULT_SKILLS_SYNC_REPO_NAME;
  await ensurePrivateForkFromUpstream(token, username, repoName);
  const current = await readSkillsSyncState();
  await writeSkillsSyncState({ ...current, githubToken: token, githubUsername: username, repoOwner: username, repoName });
  await pullInstalledSkillsFolderFromRepo(token, username, repoName);
  try {
    await appServer.rpc("skills/list", { forceReload: true });
  } catch {
  }
  await autoPushSyncedSkills(appServer);
}
async function handleSkillsRoutes(req, res, url, context) {
  const { appServer, readJsonBody: readJsonBody3 } = context;
  if (req.method === "GET" && url.pathname === "/codex-api/skills-hub") {
    try {
      const installedMap = await collectInstalledSkillsMap(appServer);
      const installed = await Promise.all([...installedMap.values()].map((info) => buildLocalHubEntry(info)));
      installed.sort((a, b) => a.name.localeCompare(b.name));
      setJson3(res, 200, { installed });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to fetch skills hub") });
    }
    return true;
  }
  if (req.method === "GET" && url.pathname === "/codex-api/skills-hub/search") {
    try {
      const query = (url.searchParams.get("q") || "").trim();
      if (query.length < 2) {
        setJson3(res, 200, { results: [] });
        return true;
      }
      const installedMap = await collectInstalledSkillsMap(appServer);
      const output = await runCommandWithOutput("npx", ["--yes", "skills", "find", query], { timeoutMs: 6e4 });
      const results = await enrichSkillSearchDescriptions(parseNpxSkillsFindOutput(output, installedMap));
      setJson3(res, 200, { results });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to search skills") });
    }
    return true;
  }
  if (req.method === "GET" && url.pathname === "/codex-api/skills-sync/status") {
    const state = await readSkillsSyncState();
    setJson3(res, 200, {
      data: {
        loggedIn: Boolean(state.githubToken),
        githubUsername: state.githubUsername ?? "",
        repoOwner: state.repoOwner ?? "",
        repoName: state.repoName ?? "",
        configured: Boolean(state.githubToken && state.repoOwner && state.repoName),
        telemetry: {
          lastPullCommitSha: state.lastPullCommitSha ?? "",
          lastPushCommitSha: state.lastPushCommitSha ?? "",
          lastSyncAttemptCount: state.lastSyncAttemptCount ?? 0,
          lastSyncError: state.lastSyncError ?? "",
          lastSyncAtIso: state.lastSyncAtIso ?? ""
        },
        startup: {
          inProgress: startupSyncStatus.inProgress,
          mode: startupSyncStatus.mode,
          branch: startupSyncStatus.branch,
          lastAction: startupSyncStatus.lastAction,
          lastRunAtIso: startupSyncStatus.lastRunAtIso,
          lastSuccessAtIso: startupSyncStatus.lastSuccessAtIso,
          lastError: startupSyncStatus.lastError
        }
      }
    });
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/skills-sync/github/start-login") {
    try {
      const started = await startGithubDeviceLogin();
      setJson3(res, 200, { data: started });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to start GitHub login") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/skills-sync/github/token-login") {
    try {
      const payload = asRecord4(await readJsonBody3(req));
      const token = typeof payload?.token === "string" ? payload.token.trim() : "";
      if (!token) {
        setJson3(res, 400, { error: "Missing GitHub token" });
        return true;
      }
      const username = await resolveGithubUsername(token);
      await finalizeGithubLoginAndSync(token, username, appServer);
      setJson3(res, 200, { ok: true, data: { githubUsername: username } });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to login with GitHub token") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/skills-sync/github/logout") {
    try {
      const state = await readSkillsSyncState();
      await writeSkillsSyncState({
        ...state,
        githubToken: void 0,
        githubUsername: void 0,
        repoOwner: void 0,
        repoName: void 0
      });
      setJson3(res, 200, { ok: true });
    } catch (error) {
      setJson3(res, 500, { error: getErrorMessage4(error, "Failed to logout GitHub") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/skills-sync/github/complete-login") {
    try {
      const payload = asRecord4(await readJsonBody3(req));
      const deviceCode = typeof payload?.deviceCode === "string" ? payload.deviceCode : "";
      if (!deviceCode) {
        setJson3(res, 400, { error: "Missing deviceCode" });
        return true;
      }
      const result = await completeGithubDeviceLogin(deviceCode);
      if (!result.token) {
        setJson3(res, 200, { ok: false, pending: result.error === "authorization_pending", error: result.error || "login_failed" });
        return true;
      }
      const token = result.token;
      const username = await resolveGithubUsername(token);
      await finalizeGithubLoginAndSync(token, username, appServer);
      setJson3(res, 200, { ok: true, data: { githubUsername: username } });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to complete GitHub login") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/skills-sync/push") {
    try {
      const state = await readSkillsSyncState();
      if (!state.githubToken || !state.repoOwner || !state.repoName) {
        setJson3(res, 400, { error: "Skills sync is not configured yet" });
        return true;
      }
      if (isUpstreamSkillsRepo(state.repoOwner, state.repoName)) {
        setJson3(res, 400, { error: "Refusing to push to upstream repository" });
        return true;
      }
      const local = await collectLocalSyncedSkills(appServer);
      const installedMap = await collectInstalledSkillsMap(appServer);
      await writeRemoteSkillsManifest(state.githubToken, state.repoOwner, state.repoName, local);
      await syncInstalledSkillsFolderToRepo(state.githubToken, state.repoOwner, state.repoName, installedMap);
      setJson3(res, 200, { ok: true, data: { synced: local.length } });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to push synced skills") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/skills-sync/startup-sync") {
    try {
      await runSkillsSyncStartup(appServer);
      setJson3(res, 200, { ok: true });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to run startup sync") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/skills-sync/pull") {
    try {
      const state = await readSkillsSyncState();
      if (!state.githubToken || !state.repoOwner || !state.repoName) {
        const repoDir = await bootstrapSkillsFromUpstreamIntoLocal();
        const localSkills2 = await scanInstalledSkillsFromDir(repoDir);
        try {
          await appServer.rpc("skills/list", { forceReload: true });
        } catch {
        }
        setJson3(res, 200, { ok: true, data: { synced: localSkills2.size, source: "upstream" } });
        return true;
      }
      if (isUpstreamSkillsRepo(state.repoOwner, state.repoName)) {
        const repoDir = await pullInstalledSkillsFolderFromRepo(state.githubToken, state.repoOwner, state.repoName);
        const localSkills2 = await scanInstalledSkillsFromDir(repoDir);
        const pulledHead2 = await runCommandWithOutput("git", ["rev-parse", "HEAD"], { cwd: repoDir }).catch(() => "");
        await writeSkillsSyncState({
          ...state,
          lastPullCommitSha: pulledHead2.trim(),
          lastSyncAttemptCount: 1,
          lastSyncError: "",
          lastSyncAtIso: (/* @__PURE__ */ new Date()).toISOString()
        });
        try {
          await appServer.rpc("skills/list", { forceReload: true });
        } catch {
        }
        setJson3(res, 200, { ok: true, data: { synced: localSkills2.size, source: "upstream" } });
        return true;
      }
      const remote = await readRemoteSkillsManifest(state.githubToken, state.repoOwner, state.repoName);
      const localDir = await detectUserSkillsDir(appServer);
      await pullInstalledSkillsFolderFromRepo(state.githubToken, state.repoOwner, state.repoName);
      const localSkills = await scanInstalledSkillsFromDisk();
      const missingAfterPull = [];
      for (const skill of remote) {
        const owner = skill.owner || "";
        if (!owner) continue;
        if (!localSkills.has(skill.name)) {
          missingAfterPull.push(`${owner}/${skill.name}`);
          continue;
        }
        const skillPath = join4(localDir, skill.name);
        await appServer.rpc("skills/config/write", { path: skillPath, enabled: skill.enabled });
      }
      if (missingAfterPull.length > 0) {
        throw new Error(`Missing skill folders after pull: ${missingAfterPull.join(", ")}`);
      }
      const remoteNames = new Set(remote.map((row) => row.name));
      for (const [name, localInfo] of localSkills.entries()) {
        if (!remoteNames.has(name)) {
          await rm3(localInfo.path.replace(/\/SKILL\.md$/, ""), { recursive: true, force: true });
        }
      }
      const nextOwners = {};
      for (const item of remote) {
        const owner = item.owner || "";
        if (owner) nextOwners[item.name] = owner;
      }
      const pulledHead = await runCommandWithOutput("git", ["rev-parse", "HEAD"], { cwd: getSkillsInstallDir() }).catch(() => "");
      await writeSkillsSyncState({
        ...state,
        installedOwners: nextOwners,
        lastPullCommitSha: pulledHead.trim(),
        lastSyncAttemptCount: 1,
        lastSyncError: "",
        lastSyncAtIso: (/* @__PURE__ */ new Date()).toISOString()
      });
      try {
        await appServer.rpc("skills/list", { forceReload: true });
      } catch {
      }
      setJson3(res, 200, { ok: true, data: { synced: remote.length } });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to pull synced skills") });
    }
    return true;
  }
  if (req.method === "GET" && url.pathname === "/codex-api/skills-hub/readme") {
    try {
      const owner = url.searchParams.get("owner") || "";
      const name = url.searchParams.get("name") || "";
      const installed = url.searchParams.get("installed") === "true";
      const skillPath = url.searchParams.get("path") || "";
      if (!owner || !name) {
        setJson3(res, 400, { error: "Missing owner or name" });
        return true;
      }
      if (installed) {
        const installedMap = await scanInstalledSkillsFromDisk();
        const installedInfo = installedMap.get(name);
        const localSkillPath = installedInfo?.path || (skillPath ? skillPath.endsWith("/SKILL.md") ? skillPath : `${skillPath}/SKILL.md` : "");
        if (localSkillPath) {
          const content = await readFile2(localSkillPath, "utf8");
          const description = extractSkillDescriptionFromMarkdown(content);
          setJson3(res, 200, { content, description, source: "local" });
          return true;
        }
      }
      setJson3(res, 404, { error: "Only installed local skills are available in Skills Hub." });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to fetch SKILL.md") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/skills-hub/install") {
    try {
      const payload = asRecord4(await readJsonBody3(req));
      const source = typeof payload?.source === "string" ? payload.source.trim() : "";
      const owner = typeof payload?.owner === "string" ? payload.owner.trim() : "";
      const name = typeof payload?.name === "string" ? payload.name.trim() : "";
      const installSource = source || (owner && name ? `${owner}@${name}` : "");
      if (!installSource || !/^[A-Za-z0-9._/-]+@[A-Za-z0-9._-]+$/u.test(installSource)) {
        setJson3(res, 400, { error: "Missing or invalid skill source" });
        return true;
      }
      await runCommand2("npx", ["--yes", "skills", "add", installSource, "--yes", "--global"], { timeoutMs: 12e4 });
      try {
        await withTimeout(appServer.rpc("skills/list", { forceReload: true }), 1e4, "skills/list reload");
      } catch {
      }
      const installedMap = await collectInstalledSkillsMap(appServer);
      const installed = installedMap.get(name || installSource.slice(installSource.lastIndexOf("@") + 1));
      if (!installed?.path) {
        throw new Error(`Skill install completed but ${installSource} was not found in local installed skills`);
      }
      await ensureInstalledSkillIsValid(appServer, installed.path);
      autoPushSyncedSkills(appServer).catch(() => {
      });
      setJson3(res, 200, { ok: true, path: installed.path });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to install skill") });
    }
    return true;
  }
  if (req.method === "POST" && url.pathname === "/codex-api/skills-hub/uninstall") {
    try {
      const payload = asRecord4(await readJsonBody3(req));
      const name = typeof payload?.name === "string" ? payload.name : "";
      const path = typeof payload?.path === "string" ? payload.path : "";
      const normalizedPath = path.endsWith("/SKILL.md") ? path.slice(0, -"/SKILL.md".length) : path;
      const target = normalizedPath || (name ? join4(getSkillsInstallDir(), name) : "");
      if (!target) {
        setJson3(res, 400, { error: "Missing name or path" });
        return true;
      }
      await rm3(target, { recursive: true, force: true });
      if (name) {
        const syncState = await readSkillsSyncState();
        const nextOwners = { ...syncState.installedOwners ?? {} };
        delete nextOwners[name];
        await writeSkillsSyncState({ ...syncState, installedOwners: nextOwners });
      }
      autoPushSyncedSkills(appServer).catch(() => {
      });
      try {
        await withTimeout(appServer.rpc("skills/list", { forceReload: true }), 1e4, "skills/list reload");
      } catch {
      }
      setJson3(res, 200, { ok: true, deletedPath: target });
    } catch (error) {
      setJson3(res, 502, { error: getErrorMessage4(error, "Failed to uninstall skill") });
    }
    return true;
  }
  return false;
}

// src/server/telegramThreadBridge.ts
import { basename as basename2 } from "path";
var TELEGRAM_MESSAGE_MAX_LENGTH = 3500;
var TELEGRAM_BOT_COMMANDS = [
  { command: "start", description: "Show quick start and thread picker" },
  { command: "threads", description: "List recent threads to connect" },
  { command: "newthread", description: "Create and connect a new thread" },
  { command: "thread", description: "Connect existing thread: /thread <id>" },
  { command: "current", description: "Show currently connected thread" },
  { command: "history", description: "Show recent history for current thread" },
  { command: "status", description: "Show bridge and mapping status" },
  { command: "whoami", description: "Show your Telegram IDs" },
  { command: "help", description: "Show available commands" }
];
function asRecord5(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function getErrorMessage5(payload, fallback) {
  if (payload instanceof Error && payload.message.trim().length > 0) {
    return payload.message;
  }
  const record = asRecord5(payload);
  if (!record) return fallback;
  const error = record.error;
  if (typeof error === "string" && error.length > 0) return error;
  const nestedError = asRecord5(error);
  if (nestedError && typeof nestedError.message === "string" && nestedError.message.length > 0) {
    return nestedError.message;
  }
  return fallback;
}
function normalizeTelegramAllowlist(values) {
  const rawValues = Array.isArray(values) ? values : [];
  const allowAllUsers = rawValues.some((value) => typeof value === "string" && value.trim() === "*");
  const allowedUserIds = Array.from(new Set(rawValues.map((value) => {
    if (typeof value === "number" && Number.isFinite(value)) {
      return Math.trunc(value);
    }
    if (typeof value === "string" && value.trim().length > 0) {
      const normalized = value.trim().replace(/^(telegram|tg):/i, "").trim();
      if (/^-?\d+$/.test(normalized)) {
        return Number.parseInt(normalized, 10);
      }
    }
    return Number.NaN;
  }).filter((value) => Number.isFinite(value)))).slice(0, 100);
  return { allowAllUsers, allowedUserIds };
}
function escapeHtml(value) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function renderMarkdownInlineToTelegramHtml(value) {
  let rendered = escapeHtml(value);
  rendered = rendered.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>');
  rendered = rendered.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  rendered = rendered.replace(/\*\*([^*\n][^*\n]*?)\*\*/g, "<b>$1</b>");
  rendered = rendered.replace(/__([^_\n][^_\n]*?)__/g, "<b>$1</b>");
  rendered = rendered.replace(/\*([^*\n][^*\n]*?)\*/g, "<i>$1</i>");
  rendered = rendered.replace(/_([^_\n][^_\n]*?)_/g, "<i>$1</i>");
  rendered = rendered.replace(/^(#{1,6})\s+(.+)$/gm, (_match, _hashes, content) => `<b>${content}</b>`);
  return rendered;
}
function renderMarkdownToTelegramHtml(markdown) {
  const normalized = markdown.replace(/\r\n/g, "\n");
  const fencedCodeRegex = /```([a-zA-Z0-9_-]+)?\n([\s\S]*?)```/g;
  let cursor = 0;
  const parts = [];
  let match = fencedCodeRegex.exec(normalized);
  while (match) {
    const [fullMatch, lang, code] = match;
    const matchIndex = match.index;
    const before = normalized.slice(cursor, matchIndex);
    if (before) {
      parts.push(renderMarkdownInlineToTelegramHtml(before));
    }
    const escapedCode = escapeHtml((code ?? "").replace(/\n+$/g, ""));
    const escapedLang = typeof lang === "string" ? escapeHtml(lang) : "";
    if (escapedLang) {
      parts.push(`<pre><code class="language-${escapedLang}">${escapedCode}</code></pre>`);
    } else {
      parts.push(`<pre>${escapedCode}</pre>`);
    }
    cursor = matchIndex + fullMatch.length;
    match = fencedCodeRegex.exec(normalized);
  }
  const tail = normalized.slice(cursor);
  if (tail) {
    parts.push(renderMarkdownInlineToTelegramHtml(tail));
  }
  return parts.join("");
}
function splitTelegramText(text, maxLength = TELEGRAM_MESSAGE_MAX_LENGTH) {
  const normalized = text.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];
  if (normalized.length <= maxLength) return [normalized];
  const chunks = [];
  let remaining = normalized;
  while (remaining.length > maxLength) {
    let splitIndex = remaining.lastIndexOf("\n\n", maxLength);
    if (splitIndex < Math.floor(maxLength * 0.5)) {
      splitIndex = remaining.lastIndexOf("\n", maxLength);
    }
    if (splitIndex < Math.floor(maxLength * 0.5)) {
      splitIndex = remaining.lastIndexOf(" ", maxLength);
    }
    if (splitIndex <= 0) {
      splitIndex = maxLength;
    }
    const chunk = remaining.slice(0, splitIndex).trim();
    if (chunk) chunks.push(chunk);
    remaining = remaining.slice(splitIndex).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}
var TelegramThreadBridge = class {
  constructor(appServer, options = {}) {
    this.allowAllUsers = false;
    this.allowedUserIds = /* @__PURE__ */ new Set();
    this.threadIdByChatId = /* @__PURE__ */ new Map();
    this.chatIdsByThreadId = /* @__PURE__ */ new Map();
    this.lastForwardedTurnByThreadId = /* @__PURE__ */ new Map();
    this.active = false;
    this.pollingTask = null;
    this.nextUpdateOffset = 0;
    this.lastError = "";
    this.appServer = appServer;
    this.token = process.env.TELEGRAM_BOT_TOKEN?.trim() ?? "";
    this.defaultCwd = process.env.TELEGRAM_DEFAULT_CWD?.trim() ?? process.cwd();
    this.configureAllowedUserIds(
      (process.env.TELEGRAM_ALLOWED_USER_IDS ?? "").split(",").map((value) => value.trim()).filter(Boolean)
    );
    this.onChatSeen = options.onChatSeen;
  }
  start() {
    if (!this.token || this.active) return;
    this.active = true;
    void this.syncBotCommands().catch(() => {
    });
    void this.notifyOnlineForKnownChats().catch(() => {
    });
    this.pollingTask = this.pollLoop();
    this.appServer.onNotification((notification) => {
      void this.handleNotification(notification).catch(() => {
      });
    });
  }
  stop() {
    this.active = false;
  }
  async pollLoop() {
    while (this.active) {
      try {
        const updates = await this.getUpdates();
        this.lastError = "";
        for (const update of updates) {
          const updateId = typeof update.update_id === "number" ? update.update_id : -1;
          if (updateId >= 0) {
            this.nextUpdateOffset = Math.max(this.nextUpdateOffset, updateId + 1);
          }
          await this.handleIncomingUpdate(update);
        }
      } catch (error) {
        this.lastError = getErrorMessage5(error, "Telegram polling failed");
        await new Promise((resolve4) => setTimeout(resolve4, 1500));
      }
    }
  }
  async getUpdates() {
    if (!this.token) {
      throw new Error("Telegram bot token is not configured");
    }
    const response = await fetch(this.apiUrl("getUpdates"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        timeout: 45,
        offset: this.nextUpdateOffset,
        allowed_updates: ["message", "callback_query"]
      })
    });
    const payload = asRecord5(await response.json());
    const result = Array.isArray(payload?.result) ? payload.result : [];
    return result;
  }
  apiUrl(method) {
    return `https://api.telegram.org/bot${this.token}/${method}`;
  }
  configureToken(token) {
    const normalizedToken = token.trim();
    if (!normalizedToken) {
      throw new Error("Telegram bot token is required");
    }
    this.token = normalizedToken;
    void this.syncBotCommands().catch(() => {
    });
  }
  getStatus() {
    return {
      configured: this.token.length > 0,
      active: this.active,
      mappedChats: this.threadIdByChatId.size,
      mappedThreads: this.chatIdsByThreadId.size,
      allowedUsers: this.allowedUserIds.size,
      allowAllUsers: this.allowAllUsers,
      lastError: this.lastError
    };
  }
  configureAllowedUserIds(allowedUserIds) {
    const normalized = normalizeTelegramAllowlist(allowedUserIds);
    this.allowAllUsers = normalized.allowAllUsers;
    this.allowedUserIds = new Set(normalized.allowedUserIds);
  }
  connectThread(threadId, chatId, token) {
    const normalizedThreadId = threadId.trim();
    if (!normalizedThreadId) {
      throw new Error("threadId is required");
    }
    if (!Number.isFinite(chatId)) {
      throw new Error("chatId must be a number");
    }
    if (typeof token === "string" && token.trim().length > 0) {
      this.configureToken(token);
    }
    if (!this.token) {
      throw new Error("Telegram bot token is not configured");
    }
    this.bindChatToThread(chatId, normalizedThreadId);
    this.markChatSeen(chatId);
    this.start();
    void this.sendOnlineMessage(chatId).catch(() => {
    });
  }
  markChatSeen(chatId) {
    if (!Number.isFinite(chatId)) return;
    this.onChatSeen?.(Math.trunc(chatId));
  }
  async sendTelegramMessage(chatId, text, options = {}) {
    const chunks = splitTelegramText(text);
    if (chunks.length === 0) return;
    for (let index = 0; index < chunks.length; index += 1) {
      const chunk = chunks[index];
      const replyMarkup = index === 0 ? options.replyMarkup : void 0;
      const htmlChunk = renderMarkdownToTelegramHtml(chunk);
      try {
        await this.sendMessageRequest(chatId, htmlChunk, { replyMarkup, parseMode: "HTML" });
      } catch {
        await this.sendMessageRequest(chatId, chunk, { replyMarkup });
      }
    }
  }
  async sendMessageRequest(chatId, text, options = {}) {
    const payload = { chat_id: chatId, text };
    if (options.replyMarkup) {
      payload.reply_markup = options.replyMarkup;
    }
    if (options.parseMode) {
      payload.parse_mode = options.parseMode;
    }
    await this.callTelegramApi("sendMessage", payload);
  }
  async syncBotCommands() {
    if (!this.token) return;
    await this.callTelegramApi("setMyCommands", {
      commands: TELEGRAM_BOT_COMMANDS
    });
  }
  async callTelegramApi(method, payload) {
    const response = await fetch(this.apiUrl(method), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const parsed = asRecord5(await response.json());
    const ok = parsed?.ok === true;
    if (!response.ok || !ok) {
      const description = typeof parsed?.description === "string" ? parsed.description : "";
      const statusPart = `${String(response.status)} ${response.statusText}`.trim();
      throw new Error(description || statusPart || `Telegram API ${method} failed`);
    }
    return parsed ?? {};
  }
  async sendOnlineMessage(chatId) {
    await this.sendTelegramMessage(chatId, "Codex thread bridge went online.");
  }
  async notifyOnlineForKnownChats() {
    const knownChatIds = Array.from(this.threadIdByChatId.keys());
    for (const chatId of knownChatIds) {
      await this.sendOnlineMessage(chatId);
    }
  }
  async handleIncomingUpdate(update) {
    if (update.callback_query) {
      await this.handleCallbackQuery(update.callback_query);
      return;
    }
    const message = update.message;
    const chatId = message?.chat?.id;
    const senderId = message?.from?.id;
    const text = message?.text?.trim();
    if (typeof chatId !== "number" || !text) return;
    if (!this.isAllowedSender(senderId)) {
      await this.sendTelegramMessage(chatId, this.unauthorizedMessage(senderId));
      return;
    }
    this.markChatSeen(chatId);
    if (text === "/start") {
      await this.sendTelegramMessage(chatId, this.helpMessage());
      await this.sendThreadPicker(chatId);
      return;
    }
    if (text === "/threads") {
      await this.sendThreadPicker(chatId);
      return;
    }
    if (text === "/newthread") {
      const threadId2 = await this.createThreadForChat(chatId);
      await this.sendTelegramMessage(chatId, `Mapped to new thread: ${threadId2}`);
      return;
    }
    const threadCommand = text.match(/^\/thread\s+(\S+)$/);
    if (threadCommand) {
      const threadId2 = threadCommand[1];
      this.bindChatToThread(chatId, threadId2);
      await this.sendTelegramMessage(chatId, `Mapped to thread: ${threadId2}`);
      return;
    }
    if (text === "/current") {
      const threadId2 = this.threadIdByChatId.get(chatId);
      await this.sendTelegramMessage(chatId, threadId2 ? `Current thread: \`${threadId2}\`` : "No thread is connected for this chat yet. Use /threads, /newthread, or /thread <id>.");
      return;
    }
    if (text === "/history") {
      const threadId2 = this.threadIdByChatId.get(chatId);
      if (!threadId2) {
        await this.sendTelegramMessage(chatId, "No thread is connected for this chat yet. Use /threads or /newthread first.");
        return;
      }
      const history = await this.readThreadHistorySummary(threadId2);
      await this.sendTelegramMessage(chatId, history);
      return;
    }
    if (text === "/status") {
      const status = this.getStatus();
      const mappedThreadId = this.threadIdByChatId.get(chatId) ?? "none";
      await this.sendTelegramMessage(
        chatId,
        [
          "**Bridge status**",
          `configured: ${String(status.configured)}`,
          `active: ${String(status.active)}`,
          `mapped chats: ${String(status.mappedChats)}`,
          `mapped threads: ${String(status.mappedThreads)}`,
          `allowed users: ${String(status.allowedUsers)}`,
          `allow all users: ${String(status.allowAllUsers)}`,
          `chat ${String(chatId)} thread: \`${mappedThreadId}\``,
          status.lastError ? `last error: ${status.lastError}` : ""
        ].filter(Boolean).join("\n")
      );
      return;
    }
    if (text === "/whoami") {
      const normalizedSenderId = typeof senderId === "number" && Number.isFinite(senderId) ? String(Math.trunc(senderId)) : "unknown";
      const normalizedChatId = String(Math.trunc(chatId));
      await this.sendTelegramMessage(
        chatId,
        [
          "**Identity**",
          `telegram user id: \`${normalizedSenderId}\``,
          `chat id: \`${normalizedChatId}\``,
          `authorized: ${String(this.isAllowedSender(senderId))}`,
          this.allowAllUsers ? "allowlist mode: `*`" : "allowlist mode: explicit ids"
        ].join("\n")
      );
      return;
    }
    if (text === "/help") {
      await this.sendTelegramMessage(chatId, this.helpMessage());
      return;
    }
    const threadId = await this.ensureThreadForChat(chatId);
    try {
      await this.appServer.rpc("turn/start", {
        threadId,
        input: [{ type: "text", text }]
      });
    } catch (error) {
      const message2 = getErrorMessage5(error, "Failed to forward message to thread");
      await this.sendTelegramMessage(chatId, `Forward failed: ${message2}`);
    }
  }
  async handleCallbackQuery(callbackQuery) {
    const callbackId = typeof callbackQuery.id === "string" ? callbackQuery.id : "";
    const data = typeof callbackQuery.data === "string" ? callbackQuery.data : "";
    const chatId = callbackQuery.message?.chat?.id;
    const senderId = callbackQuery.from?.id;
    if (!this.isAllowedSender(senderId)) {
      if (callbackId) {
        await this.answerCallbackQuery(callbackId, this.unauthorizedCallbackMessage(senderId));
      }
      if (typeof chatId === "number") {
        await this.sendTelegramMessage(chatId, this.unauthorizedMessage(senderId));
      }
      return;
    }
    if (typeof chatId === "number") {
      this.markChatSeen(chatId);
    }
    if (!callbackId) return;
    if (!data.startsWith("thread:") || typeof chatId !== "number") {
      await this.answerCallbackQuery(callbackId, "Invalid selection");
      return;
    }
    const threadId = data.slice("thread:".length).trim();
    if (!threadId) {
      await this.answerCallbackQuery(callbackId, "Invalid thread id");
      return;
    }
    this.bindChatToThread(chatId, threadId);
    await this.answerCallbackQuery(callbackId, "Thread connected");
    await this.sendTelegramMessage(chatId, `Connected to thread: ${threadId}`);
    const history = await this.readThreadHistorySummary(threadId);
    if (history) {
      await this.sendTelegramMessage(chatId, history);
    }
  }
  isAllowedSender(senderId) {
    if (this.allowAllUsers) {
      return typeof senderId === "number" && Number.isFinite(senderId);
    }
    return typeof senderId === "number" && Number.isFinite(senderId) && this.allowedUserIds.has(Math.trunc(senderId));
  }
  unauthorizedMessage(senderId) {
    const normalizedSenderId = typeof senderId === "number" && Number.isFinite(senderId) ? String(Math.trunc(senderId)) : "unknown";
    return `Unauthorized sender.

Your Telegram user ID: ${normalizedSenderId}
Add this ID to the bot allowlist before using the bridge.`;
  }
  unauthorizedCallbackMessage(senderId) {
    if (typeof senderId === "number" && Number.isFinite(senderId)) {
      return `Unauthorized: ${String(Math.trunc(senderId))}`;
    }
    return "Unauthorized sender";
  }
  helpMessage() {
    const rows = TELEGRAM_BOT_COMMANDS.map((command) => `/${command.command} - ${command.description}`);
    return ["**Available commands**", ...rows].join("\n");
  }
  async answerCallbackQuery(callbackQueryId, text) {
    await this.callTelegramApi("answerCallbackQuery", {
      callback_query_id: callbackQueryId,
      text
    });
  }
  async sendThreadPicker(chatId) {
    const threads = await this.listRecentThreads();
    if (threads.length === 0) {
      await this.sendTelegramMessage(chatId, "No threads found. Send /newthread to create one.");
      return;
    }
    const inlineKeyboard = threads.map((thread) => [
      {
        text: thread.title,
        callback_data: `thread:${thread.id}`
      }
    ]);
    await this.sendTelegramMessage(chatId, "Select a thread to connect:", {
      replyMarkup: { inline_keyboard: inlineKeyboard }
    });
  }
  async listRecentThreads() {
    const payload = asRecord5(await this.appServer.rpc("thread/list", {
      archived: false,
      limit: 20,
      sortKey: "updated_at",
      modelProviders: []
    }));
    const rows = Array.isArray(payload?.data) ? payload.data : [];
    const threads = [];
    for (const row of rows) {
      const record = asRecord5(row);
      const id = typeof record?.id === "string" ? record.id.trim() : "";
      if (!id) continue;
      const name = typeof record?.name === "string" ? record.name.trim() : "";
      const preview = typeof record?.preview === "string" ? record.preview.trim() : "";
      const cwd = typeof record?.cwd === "string" ? record.cwd.trim() : "";
      const projectName = cwd ? basename2(cwd) : "project";
      const threadTitle = (name || preview || id).replace(/\s+/g, " ").trim();
      const title = `${projectName}/${threadTitle}`.slice(0, 64);
      threads.push({ id, title });
    }
    return threads;
  }
  async createThreadForChat(chatId) {
    const response = asRecord5(await this.appServer.rpc("thread/start", { cwd: this.defaultCwd }));
    const thread = asRecord5(response?.thread);
    const threadId = typeof thread?.id === "string" ? thread.id : "";
    if (!threadId) {
      throw new Error("thread/start did not return thread id");
    }
    this.bindChatToThread(chatId, threadId);
    return threadId;
  }
  async ensureThreadForChat(chatId) {
    const existing = this.threadIdByChatId.get(chatId);
    if (existing) return existing;
    return this.createThreadForChat(chatId);
  }
  bindChatToThread(chatId, threadId) {
    const previousThreadId = this.threadIdByChatId.get(chatId);
    if (previousThreadId && previousThreadId !== threadId) {
      const previousSet = this.chatIdsByThreadId.get(previousThreadId);
      previousSet?.delete(chatId);
      if (previousSet && previousSet.size === 0) {
        this.chatIdsByThreadId.delete(previousThreadId);
      }
    }
    this.threadIdByChatId.set(chatId, threadId);
    const chatIds = this.chatIdsByThreadId.get(threadId) ?? /* @__PURE__ */ new Set();
    chatIds.add(chatId);
    this.chatIdsByThreadId.set(threadId, chatIds);
  }
  extractThreadId(notification) {
    const params = asRecord5(notification.params);
    if (!params) return "";
    const directThreadId = typeof params.threadId === "string" ? params.threadId : "";
    if (directThreadId) return directThreadId;
    const turn = asRecord5(params.turn);
    const turnThreadId = typeof turn?.threadId === "string" ? turn.threadId : "";
    return turnThreadId;
  }
  extractTurnId(notification) {
    const params = asRecord5(notification.params);
    if (!params) return "";
    const directTurnId = typeof params.turnId === "string" ? params.turnId : "";
    if (directTurnId) return directTurnId;
    const turn = asRecord5(params.turn);
    const turnId = typeof turn?.id === "string" ? turn.id : "";
    return turnId;
  }
  async handleNotification(notification) {
    if (notification.method !== "turn/completed") return;
    const threadId = this.extractThreadId(notification);
    if (!threadId) return;
    const chatIds = this.chatIdsByThreadId.get(threadId);
    if (!chatIds || chatIds.size === 0) return;
    const turnId = this.extractTurnId(notification);
    const lastForwardedTurnId = this.lastForwardedTurnByThreadId.get(threadId);
    if (turnId && lastForwardedTurnId === turnId) return;
    const assistantReply = await this.readLatestAssistantMessage(threadId);
    if (!assistantReply) return;
    for (const chatId of chatIds) {
      await this.sendTelegramMessage(chatId, assistantReply);
    }
    if (turnId) {
      this.lastForwardedTurnByThreadId.set(threadId, turnId);
    }
  }
  async readLatestAssistantMessage(threadId) {
    const response = asRecord5(await this.appServer.rpc("thread/read", { threadId, includeTurns: true }));
    const thread = asRecord5(response?.thread);
    const turns = Array.isArray(thread?.turns) ? thread.turns : [];
    for (let turnIndex = turns.length - 1; turnIndex >= 0; turnIndex -= 1) {
      const turn = asRecord5(turns[turnIndex]);
      const items = Array.isArray(turn?.items) ? turn.items : [];
      for (let itemIndex = items.length - 1; itemIndex >= 0; itemIndex -= 1) {
        const item = asRecord5(items[itemIndex]);
        if (item?.type === "agentMessage") {
          const text = typeof item.text === "string" ? item.text.trim() : "";
          if (text) return text;
        }
      }
    }
    return "";
  }
  async readThreadHistorySummary(threadId) {
    const response = asRecord5(await this.appServer.rpc("thread/read", { threadId, includeTurns: true }));
    const thread = asRecord5(response?.thread);
    const turns = Array.isArray(thread?.turns) ? thread.turns : [];
    const historyRows = [];
    for (const turn of turns) {
      const turnRecord = asRecord5(turn);
      const items = Array.isArray(turnRecord?.items) ? turnRecord.items : [];
      for (const item of items) {
        const itemRecord = asRecord5(item);
        const type = typeof itemRecord?.type === "string" ? itemRecord.type : "";
        if (type === "userMessage") {
          const content = Array.isArray(itemRecord?.content) ? itemRecord.content : [];
          for (const block of content) {
            const blockRecord = asRecord5(block);
            if (blockRecord?.type === "text" && typeof blockRecord.text === "string" && blockRecord.text.trim()) {
              historyRows.push(`User: ${blockRecord.text.trim()}`);
            }
          }
        }
        if (type === "agentMessage" && typeof itemRecord?.text === "string" && itemRecord.text.trim()) {
          historyRows.push(`Assistant: ${itemRecord.text.trim()}`);
        }
      }
    }
    if (historyRows.length === 0) {
      return "Thread has no message history yet.";
    }
    const tail = historyRows.slice(-12).join("\n\n");
    const maxLen = 3800;
    const summary = tail.length > maxLen ? tail.slice(tail.length - maxLen) : tail;
    return `Recent history:

${summary}`;
  }
};

// src/server/freeMode.ts
var ENCRYPTED_KEYS = [
  "FhkYWwEZE0MYBhAGUEADDBYFBEoDBxIHVUpUVRIMVUYDAkEHVRYNAxABUUAEAUMDV0pUDEQAU0ZTDEQCVERQVkoBVhAEBBBXAQ==",
  "FhkYWwEZE0MYVkIGUkNUUkpVXUsBBUUAVEYHUEIMBhQCVxZWBBcHVkoNUENRAxAMA0MHARBXBkVUAUVQXBAFAUVXVxFWBUtWBw==",
  "FhkYWwEZE0MYVhFWAUJUUBEMURMHAUoEAUcABRAEURRXARBRU0ZUBBFVB0YAAUNVVUYBDBBSABRUAhdVXUUBUhANV0IMBBABBA==",
  "FhkYWwEZE0MYUBIDABMBVkMHURcGDRVSXRMFBUUCBBQBVhUBUBEGDBAAVkpTVUoGUBYMBhJXB0ANABUEARBQB0RRXUBRBUNQBw==",
  "FhkYWwEZE0MYVhcFBhMFARJXVBMADRdWVxYHBkQNA0cBBEsGVEBRAkYCXEFXURBXABZQDEZSXBQHAkJSAUABVxIMA0NWAEcMUA==",
  "FhkYWwEZE0MYAEQAXEZQURUGARFRBkRWVENWDUYFBkQHBEJWU0dQUkdWBhZXARYMAERXURcBUUQNDUAGAEoEB0ABV0NTUkQDBw==",
  "FhkYWwEZE0MYABdRURBXVkYDURZWUUIAUEcMBEcMUUpXVxEGVhEMBktVXBBWAEFQBBBRVhECUEQEBkFQUUpRVRUMV0dRA0QGUw==",
  "FhkYWwEZE0MYVUMCUUIHAUFRVksFVhYMARRRBBIAVBMBDEFVAxMAAUpRXUsEBkMHVhAHBUdSVxECABJSVRdRBkMEURANAEdXVA==",
  "FhkYWwEZE0MYUkEFVEVUBEoMVkINDUFQUENQAkBSAEVQVhcEAEsDBxVWUkBWAkRSA0ANV0FVBkYMVxcBXUQEUEQCARYDDEpWXA==",
  "FhkYWwEZE0MYDBcCXBANBRdVU0YEAEsMAUoNUkoMUBYDABcHVEBQBkRVUxdWBUUAAURUVxUGB0oDVxIHABRUAhJRAEUDUkECXQ==",
  "FhkYWwEZE0MYVhUHVBEBURFQA0EBVRcNUUZXAhVXVkpQAEUHBhNTDUQMXRAGA0JQA0BRBRUHVRQMURVWXUoBVxcEBEYEAEACUQ==",
  "FhkYWwEZE0MYA0UCB0ZTABUNBhRTAUYAUENQUEANBEMCARdQBkRRBRYDUhdWVhACXBcGBhIDVBFRBRJQUREGDRAAUhQHUhUBAA==",
  "FhkYWwEZE0MYAUsMARACBBYGVxQHARVQVxRRBRcNUkAFUUQCXBEAUkcBXEMBBEYCXRENBUsBVRYABUJXU0FUAEYBUUpWABEGUw==",
  "FhkYWwEZE0MYAEdSUBcNAUoFUERUAkcFAEQAB0IBUxcFDUIMBEpQVktWUxdUB0MBXUEBBhIMXRQEUBFQXEMFAEBQXUEMVkoBUQ==",
  "FhkYWwEZE0MYDBYNUUVUA0ECUREMVhUEBkoCVxJSXEtRUENQVxAMBBcMAxACVkVVBEEDUEYDAURWA0oDXUYAAEEEVxQABUANVg==",
  "FhkYWwEZE0MYVhcHBhcFV0EBUEdWVxdSU0sMABFSUEIHA0EAU0dWBkcFXEZRBENXAUEDV0AFUkEABBAEXBdXAhZRBEAAUUBSVg==",
  "FhkYWwEZE0MYV0MHAxYBDUsHB0oFVRJWAUoABEQGAUEHDRdRUBQHBREFUkpQVUYHVkVTDBcDXUYHBkJXUhENVUIAVUtTDRcMVA==",
  "FhkYWwEZE0MYBxVXBEsAUkYBA0EEAUIGBkRQA0MNABZRVkcHA0JTUEdWUkNRBBUEXUFUB0oFB0QGDBdWUUsEV0NXBBQBVRUEVg==",
  "FhkYWwEZE0MYVxcCVBYHAEsNVBEADEENUkMAUhFWXBNUVxdWBxNWURYAVEEAUUdSURAHDUsAUkEABBJSVRZQV0YNVRBRDUVSBw==",
  "FhkYWwEZE0MYAEQEV0YGVxcMVkRQUEsGUEBRUEADAEYEV0NRBBRWBUpXV0oMA0NRXBBRAkAMXUZWURBSXEZRB0EEVBQNVxYBXQ==",
  "FhkYWwEZE0MYA0IBUhADUERXB0MNB0MHVUtUDRUNBEpXVkEGUBMABkZVUENUAkBVXRAEDEAHBkJWABAEURNWDEcEABQCVUdVVA==",
  "FhkYWwEZE0MYUhcEBBYCAUFSXUAEAEEBV0sDDRAFV0YDV0NVBENXB0QNVxdUAkYMXUQGA0tRV0tWVUoDAxcGUUVVVUQHDBEDBA==",
  "FhkYWwEZE0MYA0QBBEIAB0INXUtTBxYFVBFXABJSBkYEAxIAVEAGVkZSB0tQUEoHBkcGBBUHVENWAUNRUEYCAhJSXRcNUEQGUA==",
  "FhkYWwEZE0MYUBJQUEIFUkBXARBUBUIDAxBQVhJVVkUMVhEDAEYNVxEGBhRUVkJWURYDAUAAAUUMARVRBhYAUkAEUkUEAhYCVg==",
  "FhkYWwEZE0MYVUYGVBcEDEAFVhACVkFWXBFTAxAMUUpQURENARYBVhABAEINAEQCAUECDEsCBEUBVxBXBxRUVxdQBBRXVkcCUA==",
  "FhkYWwEZE0MYV0YMVxBTVUNQBERRURVSUxQGUUVWB0MGVUMHV0cHUkMEAEMDDUMCVEcGVkNVB0oDURdVAUFQBkIAURYDBhAHAA==",
  "FhkYWwEZE0MYUhYCXEsNVUAEURFXBkcHABFQBxcFUENWVkpVAxZWAhEBAxMBBkRRVUtQDEZWXEoBBxUNVkYBBhJQUBBQUUoDBw==",
  "FhkYWwEZE0MYB0YGXUIGDRIHVRZQVUJSV0UNB0oNAxQADRUMVUcEBhdQV0AHDUZXAEtQVkVQUhBRBUBSUEQCVkRSBEUDUkQEVQ==",
  "FhkYWwEZE0MYB0MGAUEADERVV0RXDUJSUUMAUEdRAUMCBxZSBktQDUMEBkIBBkIDAEMNURdRXUoFB0RWVEZRDUFXAEJTVRVWVg==",
  "FhkYWwEZE0MYAkQDAxcFBEpXVEIEDUJSB0tXBhVXUkIDAEEMBBBXDUdRVRcNBURVAxZXUUENARYNBkMAUBBTDUsGVUFWDEcAVQ==",
  "FhkYWwEZE0MYDRFQVUsCBRIMXBEFBEYEBEMBAUAMVkoCDUoABEcNV0YMU0pWABJXURcAAEIEUBcGVxcGUhZWBUIAVUQCUkVVAA==",
  "FhkYWwEZE0MYUhcDVURUDBBSVkVWAEYCBkoMUEVVU0cEAxcFVhcDVUEBAEpXUhIAXEUNBUQBAxYGUhFXVUUHBBUAVkpRURAAVQ==",
  "FhkYWwEZE0MYUEtVV0BQV0tXB0dXVkNRVRRQBUADABFTURYDVBdXUEFSXEpXB0dQVBQEA0oAVUpTBEYEVBMNDEMDU0BUBUINUg==",
  "FhkYWwEZE0MYUEpQBxZTBkFXXEZWAkEEBxEHB0RXVktQUEMDARRRABEFAUIABEAMARRRDUACBBAMUEMMUxcEUUEEAEoAURBQBg==",
  "FhkYWwEZE0MYUEINARRQAhcCUEJRUBIFBEIHBkJQB0tWVhINXRBUUBdVBkcMBUZVUxNTAUsMU0cFAEtSXUJXDRJSBkVUAUoBVA==",
  "FhkYWwEZE0MYUEBWAUtXBxEHUhNTBRZVB0UEB0MDA0sCBEAABkNUAUQCBxYAAEVQUEYDVkoDVxAFVUFVVUcMAUECBkoGUUsCUA==",
  "FhkYWwEZE0MYBBUBUEFTBUIDAxAGBUcFARBWBRJXUUJTAkUGURQBUUUEB0EFBBBVVURQBEEAUBMAVhINVUEBVUcMA0sNVUNQVg==",
  "FhkYWwEZE0MYDUMDA0MNA0oAV0BQUEEFBEUBAkpQXBAMBUsCVRZXVkIAXBMEAktXBhYABkcAUhMAUhYBA0BTAURVURMBA0ACXA==",
  "FhkYWwEZE0MYUhdXUUMDAEQNBhZTAEdWXUYHBxEHXUQCDBYCBkEBBEIDAEBQBkEAUkUBBREMUEUNAEUMBENUBhZXVkVQV0NWBw==",
  "FhkYWwEZE0MYUBdVU0VXVkpQUkEEBkFSVhZRDEQMXBdQA0QDXUIHUEtWBEABAERXBEoMAxEDUxYMDUVRXUJTUBcFBhQCVkcAVQ==",
  "FhkYWwEZE0MYDRcBUBYCUEpRABQNVRcHBkQABkZXUkBWURFVU0sMBxINURQMAREHUUcHAUYDB0QBAUNVVUAAARUGUEoAABYGXA==",
  "FhkYWwEZE0MYAhUCUktQV0oEBxcCVUoCB0pTAUJQXUJTARYAXUsNDRUDUkVQARIHUUJUBEMEVxMFBhEAUUUCBRIAXBMBVUAHAA==",
  "FhkYWwEZE0MYARcCAUMDVxFQBEZXUEcCAEYDVksNVUpQB0MEB0EEAhVWXRcEUUBQXEoGA0BSAEVWBhdXVUACUUZSUEZXBUZRVg==",
  "FhkYWwEZE0MYA0oBUhEHABYCBkcMUUcGXRdUDRZXVBZTARUHVkQGV0UAAUoDBxJRVRQBA0oFAUEGBERSVhMGBEBWBEpRAUMGVg==",
  "FhkYWwEZE0MYVhANVBFXDEoAXEoMBhYMUxMNUEECVEoMAkQFVxANVRcFABdRDRVWXUACBBYHVURUUBACXUNUV0IMAUcCAUIHBw==",
  "FhkYWwEZE0MYUEUCB0UNDBEFVhQGBhJSBkYHBEMNBhAGUkAFA0AMBUAGUEYDAUZQVUdWUhcHUEcAUhEFB0FQV0VQAUtXBEcDBw==",
  "FhkYWwEZE0MYAUNSURNTBRANUkRWVxYHXEYMAUYBB0cCBksCAEUHUkVSVUdRURIEBxADBhECVxNRUEcFUxQMUEMMA0MFBEENBA==",
  "FhkYWwEZE0MYBxBWVkZQAkENVhYNBBUDXBADAUANUkBRVkICBEtRVxEEAEFUDUIDUkNXAxEDAUcHARIAVEJTA0oNVkANB0EGXA==",
  "FhkYWwEZE0MYV0IGAREGUhZVUEFXVkJVVUECDBcFARcNUhZQXBEFAkMBU0sDUEIFBhcCV0cCXUBTVRADV0YEA0ZQUxACUUsEXA==",
  "FhkYWwEZE0MYVUoNVUNQURVQUREDAxJSB0AAAkMCABQDAUMGVBYABBJWBxADBENRVEsAVxcAAEdTARUDBBEFUhZSUEQDDRcAXA==",
  "FhkYWwEZE0MYBhdRVUQBVhcGBhENV0QEAEIGVxcBUxQNUUcAVxZWBEEEVUBTARYGAUFUAUUHBEQEDUsDVEJXDEQNU0sCV0YMAA==",
  "FhkYWwEZE0MYVktRAENWAkEBXUsGUUEDUkMHB0FXB0cCAhEHARZUBxJWB0IDBERRUkUAAxYDUkYBUkYDV0QDVUcHVxAGA0INVA==",
  "FhkYWwEZE0MYBkIAVBABVUINV0NTVxYGAUYFVUMBUxYMURAGBksAVUJVBkoHUUQMA0cMAUdQVkUGBUpSAEZTVRANUBYEUEQBVA==",
  "FhkYWwEZE0MYDEMDA0oCVURRUBZWUkANUEQBAkBSXBBRB0BSVBYGVkAFVRAGDEYDVkMEDBBSBkQHV0JRA0JUBRcFXURTDRZRUw==",
  "FhkYWwEZE0MYUBJSVEUNUhcGBkYGAhYDUEcAUEsEBxdUUBZSXEcGDEINXEoDBxcFUkdWBEBRVxYNDUYAUBMBVkcCUBcHUUsAXA==",
  "FhkYWwEZE0MYA0QNUEtWAUMEAEoBUEoAAREDVRYHVkoEV0ZQBEEEUkEAAUIEAUcCVhEHUBUDB0FRVktVVEFXARIHA0NWBUpXBg==",
  "FhkYWwEZE0MYV0oCAxFXV0YMUxFQAUAAUEVWA0cEB0pUUBAFXUIHDRdQAEQAUkMGU0AEVxEDBBEBAhBRV0QEAxVWU0NQBxECBw==",
  "FhkYWwEZE0MYUkoCBBMEUkYDBhYFB0IFVkQMVUpSBksMUUcFUxEEDRZVVkUADEoCVhcHUkEHUxACUUJXBBdTVUQDAEFRBxUGAw==",
  "FhkYWwEZE0MYV0BXBEUCURUNXUYABUpQURYBBUYFVENXBhYCXRBWDUsHA0NRB0oGUREHDRYGUxMBAksEUkINVkNVBEIBAxdWUA==",
  "FhkYWwEZE0MYBEoCA0MNDEUAXUNUAxYHXBRRURACUEFQBxYDB0dUBksDA0QFVksMAxQFAEZRAxNTA0cMVUENVxEEAUFRBUAHBA==",
  "FhkYWwEZE0MYB0ENVkAABxEFXEZQAUYHBhMFBBJQBkMCUUZRBERTAkBRBhADVxYEXEADB0RSUUtRUREBXRdXBkAGBEUNBEQCUg==",
  "FhkYWwEZE0MYVhFVXBAFDBYFBkFTAhIGB0ZRBEJVXURTBBFWBxNUVkBXBEMMBkIHURcDAksAVEMEV0dSUhdXBBJWUkJWAxBRVg==",
  "FhkYWwEZE0MYBRFRXUoBBUcGBhZUAUBVABYEVkICVkNXDUcMABYFVxdXU0sEBkcFXEYBURUFVUYFABJSA0dTABdRVBRQVRENVg==",
  "FhkYWwEZE0MYV0VQVhEHVkVVAEFQAhcHBEMMUUANVxNUBUJWVRcEVUoEBBcDUkcNBkoCUUVVVBcDVRZQBBBUVRYNXBZWBUMAAQ==",
  "FhkYWwEZE0MYAhIHARYBVxIABhYBVxVWUkVXV0ICXUUADBZQAUYBBEUBUEsFBRcFARcGUEtVXEoGABYAUkEGDEBRVUMBB0IFXQ==",
  "FhkYWwEZE0MYBBUCXEEFBEJVVxZQBEICUxFRBUUNBksHBhFXUUANVhUCV0EMB0QDVURWDBFSVkYDAxYAABdXBhIEUEQMBEUCUg==",
  "FhkYWwEZE0MYDUsDBEoNAEECURBTAUJXUEpWVUdSBEAMDRBVUkYAUUoDAxFTDEpVVxEHAUYNVUMGVkYAA0cBBRJWBBAHUUIMVw==",
  "FhkYWwEZE0MYUUUFXUBTUEYHUkoHBBIFBEpRV0NWVRcBAktWBkADBxAMVUZUBhJSBEAEB0MDVkpTABUMUUVUUEABUkJUVkIHAA=="
];
var DECRYPT_KEY = "er54s4";
function xorDecrypt(b64, secret) {
  const buf = Buffer.from(b64, "base64");
  const keyBuf = Buffer.from(secret, "utf8");
  const out = Buffer.alloc(buf.length);
  for (let i = 0; i < buf.length; i++) {
    out[i] = buf[i] ^ keyBuf[i % keyBuf.length];
  }
  return out.toString("utf8");
}
function getRandomFreeKey() {
  if (ENCRYPTED_KEYS.length === 0) return null;
  const idx = Math.floor(Math.random() * ENCRYPTED_KEYS.length);
  return xorDecrypt(ENCRYPTED_KEYS[idx], DECRYPT_KEY);
}
function getFreeKeyCount() {
  return ENCRYPTED_KEYS.length;
}
var FREE_MODE_BASE_URL = "https://openrouter.ai/api/v1";
var FREE_MODE_RUNTIME_PROVIDER_ID = "openrouter_free";
var FALLBACK_FREE_MODELS = [
  "openrouter/free",
  "google/gemma-4-26b-a4b-it:free",
  "google/gemma-3-27b-it:free",
  "meta-llama/llama-3.3-70b-instruct:free",
  "qwen/qwen3-coder:free"
];
var cachedFreeModels = null;
var cacheTimestamp = 0;
var CACHE_TTL_MS = 10 * 60 * 1e3;
var freeModelsRefreshPromise = null;
async function fetchFreeModelsFromOpenRouter() {
  try {
    const resp = await fetch("https://openrouter.ai/api/v1/models");
    if (!resp.ok) return cachedFreeModels ?? FALLBACK_FREE_MODELS;
    const json = await resp.json();
    const ids = json.data.filter((m) => m.id.endsWith(":free") || m.id === "openrouter/free").map((m) => m.id);
    if (ids.length === 0) return cachedFreeModels ?? FALLBACK_FREE_MODELS;
    const sorted = ["openrouter/free", ...ids.filter((id) => id !== "openrouter/free")];
    cachedFreeModels = sorted;
    cacheTimestamp = Date.now();
    return sorted;
  } catch {
    return cachedFreeModels ?? FALLBACK_FREE_MODELS;
  }
}
async function getFreeModels() {
  if (cachedFreeModels && Date.now() - cacheTimestamp < CACHE_TTL_MS) {
    return cachedFreeModels;
  }
  return fetchFreeModelsFromOpenRouter();
}
function getCachedFreeModels() {
  return cachedFreeModels ?? FALLBACK_FREE_MODELS;
}
function refreshFreeModelsInBackground() {
  if (cachedFreeModels && Date.now() - cacheTimestamp < CACHE_TTL_MS) return;
  if (freeModelsRefreshPromise) return;
  freeModelsRefreshPromise = fetchFreeModelsFromOpenRouter().finally(() => {
    freeModelsRefreshPromise = null;
  });
}
var FREE_MODE_DEFAULT_MODEL = "openrouter/free";
var FREE_MODE_STATE_FILE = "webui-custom-providers.json";
var OPENCODE_ZEN_PROVIDER_ID = "opencode-zen";
var CUSTOM_RUNTIME_PROVIDER_ID = "custom_endpoint";
var OPENCODE_ZEN_RUNTIME_PROVIDER_ID = "opencode_zen";
var OPENCODE_ZEN_BASE_URL = "https://opencode.ai/zen/v1";
var OPENCODE_ZEN_DEFAULT_MODEL = "big-pickle";
function createDefaultOpenCodeZenFreeModeState() {
  return {
    enabled: true,
    apiKey: null,
    model: OPENCODE_ZEN_DEFAULT_MODEL,
    customKey: false,
    provider: "opencode-zen",
    wireApi: "responses",
    providerKeys: {}
  };
}
function shouldCreateDefaultFreeModeStateForMissingAuth(current, hasUsableCodexAuth2) {
  return current == null && !hasUsableCodexAuth2;
}
function shouldSuppressCommunityFreeModeForCodexAuth(current, hasUsableCodexAuth2) {
  if (!hasUsableCodexAuth2 || !current?.enabled) return false;
  if (current.provider === "custom") return false;
  if (current.customKey === true) return false;
  if (current.provider === "opencode-zen" && current.apiKey?.trim()) return false;
  return current.provider === "openrouter" || current.provider === "opencode-zen" || !current.provider;
}
function shouldMarkOpenRouterKeyAsCustom(current, explicitApiKey) {
  if (explicitApiKey.trim().length > 0) return true;
  return current?.provider === "openrouter" && current.customKey === true;
}
function getFreeModeEnvVars(state) {
  if (!state.enabled) return {};
  if (state.provider === "opencode-zen" && state.apiKey) {
    return { OPENCODE_ZEN_API_KEY: state.apiKey };
  }
  if (state.provider === "custom" && state.customBaseUrl && state.apiKey) {
    return { CUSTOM_ENDPOINT_API_KEY: state.apiKey };
  }
  return {};
}
function filterOpenCodeZenModelsForAuthState(modelIds, apiKey) {
  if (apiKey?.trim()) return modelIds;
  return modelIds.filter((id) => id === OPENCODE_ZEN_DEFAULT_MODEL || id.endsWith("-free"));
}
function getOpenCodeZenProviderConfigArgs(serverPort) {
  const providerConfigKey = `model_providers.${OPENCODE_ZEN_RUNTIME_PROVIDER_ID}`;
  const baseUrl = serverPort ? `http://127.0.0.1:${serverPort}/codex-api/zen-proxy/v1` : OPENCODE_ZEN_BASE_URL;
  const authArgs = serverPort ? ["-c", `${providerConfigKey}.experimental_bearer_token="zen-proxy-token"`] : ["-c", `${providerConfigKey}.env_key="OPENCODE_ZEN_API_KEY"`];
  return [
    "-c",
    `${providerConfigKey}.name="OpenCode Zen"`,
    "-c",
    `${providerConfigKey}.base_url="${baseUrl}"`,
    "-c",
    `${providerConfigKey}.wire_api="responses"`,
    ...authArgs
  ];
}
function getProviderCompatibilityConfigArgs(serverPort) {
  return getOpenCodeZenProviderConfigArgs(serverPort);
}
function getFreeModeConfigArgs(state, serverPort) {
  if (!state.enabled) return [];
  if (state.provider === "opencode-zen") {
    const model = state.model?.trim() || OPENCODE_ZEN_DEFAULT_MODEL;
    return [
      "-c",
      `model="${model}"`,
      "-c",
      `model_provider="${OPENCODE_ZEN_RUNTIME_PROVIDER_ID}"`,
      ...getOpenCodeZenProviderConfigArgs(serverPort)
    ];
  }
  if (state.provider === "custom" && state.customBaseUrl) {
    const providerConfigKey2 = `model_providers.${CUSTOM_RUNTIME_PROVIDER_ID}`;
    const baseUrl2 = serverPort ? `http://127.0.0.1:${serverPort}/codex-api/custom-proxy/v1` : state.customBaseUrl;
    const wireApi = serverPort ? "responses" : state.wireApi || "responses";
    const authArgs = serverPort ? ["-c", `${providerConfigKey2}.experimental_bearer_token="custom-proxy-token"`] : ["-c", `${providerConfigKey2}.env_key="CUSTOM_ENDPOINT_API_KEY"`];
    const modelArgs = state.model?.trim() ? ["-c", `model="${state.model.trim()}"`] : [];
    return [
      ...modelArgs,
      "-c",
      `model_provider="${CUSTOM_RUNTIME_PROVIDER_ID}"`,
      "-c",
      `${providerConfigKey2}.name="Custom Endpoint"`,
      "-c",
      `${providerConfigKey2}.base_url="${baseUrl2}"`,
      "-c",
      `${providerConfigKey2}.wire_api="${wireApi}"`,
      ...authArgs
    ];
  }
  if (!state.apiKey) return [];
  const providerConfigKey = `model_providers.${FREE_MODE_RUNTIME_PROVIDER_ID}`;
  const baseUrl = serverPort ? `http://127.0.0.1:${serverPort}/codex-api/openrouter-proxy/v1` : FREE_MODE_BASE_URL;
  const bearerToken = serverPort ? "openrouter-proxy-token" : state.apiKey;
  return [
    "-c",
    `model="${state.model}"`,
    "-c",
    `model_provider="${FREE_MODE_RUNTIME_PROVIDER_ID}"`,
    "-c",
    `${providerConfigKey}.name="OpenRouter Free"`,
    "-c",
    `${providerConfigKey}.base_url="${baseUrl}"`,
    "-c",
    `${providerConfigKey}.wire_api="responses"`,
    "-c",
    `${providerConfigKey}.experimental_bearer_token="${bearerToken}"`
  ];
}

// src/server/unifiedResponsesProxy.ts
import { request as httpRequest } from "http";
import { request as httpsRequest } from "https";
function readRequestBody(req) {
  return new Promise((resolve4, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve4(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}
function safeStringifyUnknown(value) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value ?? "");
  } catch {
    return String(value ?? "");
  }
}
function appendAssistantText(messages, text, reasoningContent) {
  const trimmedText = text.trim();
  const trimmedReasoningContent = reasoningContent?.trim() ?? "";
  if (!trimmedText && !trimmedReasoningContent) return;
  const lastMessage = messages[messages.length - 1];
  if (lastMessage?.role === "assistant" && Array.isArray(lastMessage.tool_calls)) {
    lastMessage.content = lastMessage.content ? `${lastMessage.content}
${trimmedText}` : trimmedText;
    if (trimmedReasoningContent) {
      lastMessage.reasoning_content = lastMessage.reasoning_content ? `${lastMessage.reasoning_content}
${trimmedReasoningContent}` : trimmedReasoningContent;
    }
    return;
  }
  messages.push({
    role: "assistant",
    content: trimmedText,
    ...trimmedReasoningContent ? { reasoning_content: trimmedReasoningContent } : {}
  });
}
function appendAssistantToolCall(messages, toolCall, reasoningContent) {
  const trimmedReasoningContent = reasoningContent?.trim() ?? "";
  const lastMessage = messages[messages.length - 1];
  if (lastMessage?.role === "assistant" && !lastMessage.tool_call_id) {
    lastMessage.tool_calls = [...lastMessage.tool_calls ?? [], toolCall];
    if (trimmedReasoningContent) {
      lastMessage.reasoning_content = lastMessage.reasoning_content ? `${lastMessage.reasoning_content}
${trimmedReasoningContent}` : trimmedReasoningContent;
    }
    return;
  }
  messages.push({
    role: "assistant",
    content: "",
    tool_calls: [toolCall],
    ...trimmedReasoningContent ? { reasoning_content: trimmedReasoningContent } : {}
  });
}
function extractTextParts(value) {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return "";
  return value.map((part) => part && typeof part === "object" && typeof part.text === "string" ? part.text : "").filter((part) => part.length > 0).join("\n");
}
function responsesInputToMessages(input, instructions) {
  const messages = [];
  let pendingReasoningContent = "";
  if (instructions) {
    messages.push({ role: "system", content: instructions });
  }
  if (typeof input === "string") {
    messages.push({ role: "user", content: input });
    return messages;
  }
  for (const item of input) {
    if (!item || typeof item !== "object") continue;
    if (item.type === "reasoning") {
      const content = extractTextParts(item.content);
      const summary = extractTextParts(item.summary);
      const text = content || summary;
      if (text) {
        const lastMessage = messages[messages.length - 1];
        if (lastMessage?.role === "assistant") {
          lastMessage.reasoning_content = lastMessage.reasoning_content ? `${lastMessage.reasoning_content}
${text}` : text;
        } else {
          pendingReasoningContent = pendingReasoningContent ? `${pendingReasoningContent}
${text}` : text;
        }
      }
      continue;
    }
    if (item.type === "message" && item.role) {
      const content = item.content;
      const text = typeof content === "string" ? content : Array.isArray(content) ? content.map((part) => typeof part?.text === "string" ? part.text : "").filter((part) => part.length > 0).join("\n") : typeof item.text === "string" ? item.text : "";
      const role = item.role === "developer" ? "system" : item.role;
      if (role === "assistant") {
        appendAssistantText(messages, text, pendingReasoningContent);
        pendingReasoningContent = "";
      } else {
        messages.push({ role, content: text });
      }
      continue;
    }
    if ((item.type === "function_call_output" || item.type === "computer_call_output") && item.call_id) {
      messages.push({
        role: "tool",
        tool_call_id: item.call_id,
        content: safeStringifyUnknown(item.output)
      });
      continue;
    }
    if (item.type === "function_call" && item.call_id && item.name) {
      appendAssistantToolCall(messages, {
        id: item.call_id,
        type: "function",
        function: {
          name: item.name,
          arguments: typeof item.arguments === "string" ? item.arguments : "{}"
        }
      }, pendingReasoningContent);
      pendingReasoningContent = "";
    }
  }
  return messages;
}
function responsesToolsToChatTools(tools) {
  if (!Array.isArray(tools)) return void 0;
  const mapped = tools.map((tool) => {
    if (!tool || typeof tool !== "object" || Array.isArray(tool)) return null;
    const row = tool;
    if (row.type !== "function") return null;
    const name = typeof row.name === "string" ? row.name : "";
    if (!name) return null;
    const description = typeof row.description === "string" ? row.description : void 0;
    return {
      type: "function",
      function: {
        name,
        ...description ? { description } : {},
        ...row.parameters !== void 0 ? { parameters: row.parameters } : {}
      }
    };
  }).filter((row) => Boolean(row));
  return mapped.length > 0 ? mapped : void 0;
}
function responsesToolChoiceToChatToolChoice(toolChoice) {
  if (typeof toolChoice === "string") return toolChoice;
  if (!toolChoice || typeof toolChoice !== "object" || Array.isArray(toolChoice)) return void 0;
  const row = toolChoice;
  if (row.type !== "function") return void 0;
  const name = typeof row.name === "string" ? row.name : row.function && typeof row.function === "object" && typeof row.function.name === "string" ? String(row.function.name) : "";
  if (!name) return void 0;
  return { type: "function", function: { name } };
}
function chatCompletionToResponsesFormat(chatResponse, model) {
  const choices = chatResponse.choices ?? [];
  const output = [];
  for (const choice of choices) {
    const message = choice.message;
    if (!message) continue;
    if (Array.isArray(message.tool_calls)) {
      for (const toolCall of message.tool_calls) {
        if (!toolCall || toolCall.type !== "function") continue;
        const callId = typeof toolCall.id === "string" && toolCall.id ? toolCall.id : `call_${Date.now()}`;
        const name = typeof toolCall.function?.name === "string" ? toolCall.function.name : "";
        if (!name) continue;
        output.push({
          type: "function_call",
          name,
          call_id: callId,
          arguments: typeof toolCall.function?.arguments === "string" ? toolCall.function.arguments : "{}",
          status: "completed"
        });
      }
    }
    if (message.content) {
      output.push({
        type: "message",
        role: "assistant",
        content: [{ type: "output_text", text: message.content }],
        status: "completed"
      });
    }
    if (message.reasoning_content) {
      output.push({
        type: "reasoning",
        id: `rs_${Date.now()}`,
        summary: [],
        content: [{ type: "reasoning_text", text: message.reasoning_content }]
      });
    }
  }
  const usage = chatResponse.usage;
  return {
    id: chatResponse.id ?? `resp_${Date.now()}`,
    object: "response",
    created_at: chatResponse.created ?? Math.floor(Date.now() / 1e3),
    status: "completed",
    model,
    output,
    usage: usage ? {
      input_tokens: usage.prompt_tokens ?? 0,
      output_tokens: usage.completion_tokens ?? 0,
      total_tokens: usage.total_tokens ?? 0
    } : void 0
  };
}
function forwardStreamingTextResponse(upstreamRes, res, model) {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive"
  });
  let buffer = "";
  const contentParts = [];
  const reasoningParts = [];
  let responseId = `resp_${Date.now()}`;
  res.write(`data: {"type":"response.created","response":{"id":"${responseId}","object":"response","status":"in_progress","model":"${model}","output":[]}}

`);
  res.write('data: {"type":"response.output_item.added","output_index":0,"item":{"type":"message","role":"assistant","content":[],"status":"in_progress"}}\n\n');
  res.write('data: {"type":"response.content_part.added","output_index":0,"content_index":0,"part":{"type":"output_text","text":""}}\n\n');
  upstreamRes.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") continue;
      try {
        const parsed = JSON.parse(data);
        if (parsed.id) responseId = `resp_${parsed.id}`;
        const delta = parsed.choices?.[0]?.delta;
        if (delta?.reasoning_content) {
          reasoningParts.push(delta.reasoning_content);
        }
        if (delta?.content) {
          contentParts.push(delta.content);
          const escaped = JSON.stringify(delta.content).slice(1, -1);
          res.write(`data: {"type":"response.output_text.delta","output_index":0,"content_index":0,"delta":"${escaped}"}

`);
        }
      } catch {
      }
    }
  });
  upstreamRes.on("end", () => {
    const fullText = contentParts.join("");
    const fullReasoningText = reasoningParts.join("");
    const escapedFull = JSON.stringify(fullText).slice(1, -1);
    const messageItem = { type: "message", role: "assistant", content: [{ type: "output_text", text: fullText }], status: "completed" };
    const output = [messageItem];
    if (fullReasoningText) {
      output.push({
        type: "reasoning",
        id: `rs_${Date.now()}`,
        summary: [],
        content: [{ type: "reasoning_text", text: fullReasoningText }]
      });
    }
    res.write(`data: {"type":"response.output_text.done","output_index":0,"content_index":0,"text":"${escapedFull}"}

`);
    res.write(`data: {"type":"response.content_part.done","output_index":0,"content_index":0,"part":{"type":"output_text","text":"${escapedFull}"}}

`);
    res.write(`data: {"type":"response.output_item.done","output_index":0,"item":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"${escapedFull}"}],"status":"completed"}}

`);
    if (fullReasoningText) {
      const reasoningIndex = output.length - 1;
      const reasoningItem = output[reasoningIndex];
      res.write(`data: ${JSON.stringify({ type: "response.output_item.added", output_index: reasoningIndex, item: reasoningItem })}

`);
      res.write(`data: ${JSON.stringify({ type: "response.output_item.done", output_index: reasoningIndex, item: reasoningItem })}

`);
    }
    res.write(`data: ${JSON.stringify({ type: "response.completed", response: { id: responseId, object: "response", status: "completed", model, output } })}

`);
    res.end();
  });
  upstreamRes.on("error", () => {
    if (!res.writableEnded) res.end();
  });
}
function sendSyntheticStreamingCompletion(res, response) {
  const responseId = typeof response.id === "string" && response.id ? response.id : `resp_${Date.now()}`;
  const model = typeof response.model === "string" ? response.model : "";
  const output = Array.isArray(response.output) ? response.output : [];
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive"
  });
  const createdPayload = {
    type: "response.created",
    response: {
      id: responseId,
      object: "response",
      status: "in_progress",
      model,
      output: []
    }
  };
  const completedPayload = {
    type: "response.completed",
    response: {
      id: responseId,
      object: "response",
      status: "completed",
      model,
      output,
      usage: response.usage
    }
  };
  res.write(`data: ${JSON.stringify(createdPayload)}

`);
  output.forEach((item, index) => {
    res.write(`data: ${JSON.stringify({ type: "response.output_item.added", output_index: index, item })}

`);
    res.write(`data: ${JSON.stringify({ type: "response.output_item.done", output_index: index, item })}

`);
  });
  res.write(`data: ${JSON.stringify(completedPayload)}

`);
  res.end();
}
function copyProxyHeaders(upstreamHeaders) {
  const headers = {};
  for (const [key, value] of Object.entries(upstreamHeaders)) {
    if (!value) continue;
    const lower = key.toLowerCase();
    if (lower === "transfer-encoding" || lower === "content-length" || lower === "connection") continue;
    headers[key] = Array.isArray(value) ? value.join(", ") : value;
  }
  return headers;
}
function hasToolOutputsInInput(input) {
  if (!Array.isArray(input)) return false;
  return input.some((item) => item?.type === "function_call_output" || item?.type === "computer_call_output");
}
function handleUnifiedResponsesProxyRequest(req, res, options) {
  void (async () => {
    try {
      if (options.requireBearerToken !== false && !options.bearerToken) {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: { message: options.missingKeyMessage } }));
        return;
      }
      const rawBody = await readRequestBody(req);
      const parsedBody = JSON.parse(rawBody.toString());
      const hasTools = Array.isArray(parsedBody.tools) && parsedBody.tools.length > 0;
      const hasToolOutputs = hasToolOutputsInInput(parsedBody.input);
      const useResponsesFallback = options.allowToolFallbackToResponses && (hasTools || hasToolOutputs);
      const useChatCompletions = options.wireApi === "chat" && !useResponsesFallback;
      const useChatPayload = useChatCompletions || options.responsesPayloadFormat === "chat";
      const isStreaming = parsedBody.stream === true;
      const effectiveStreaming = useChatPayload && isStreaming && !(hasTools || hasToolOutputs);
      let payload = "";
      let upstreamUrl;
      if (useChatPayload) {
        const chatReq = {
          model: parsedBody.model,
          messages: responsesInputToMessages(parsedBody.input, parsedBody.instructions),
          stream: effectiveStreaming
        };
        if (parsedBody.temperature != null) chatReq.temperature = parsedBody.temperature;
        if (parsedBody.top_p != null) chatReq.top_p = parsedBody.top_p;
        if (parsedBody.max_output_tokens != null) chatReq.max_tokens = parsedBody.max_output_tokens;
        const chatTools = responsesToolsToChatTools(parsedBody.tools);
        const chatToolChoice = responsesToolChoiceToChatToolChoice(parsedBody.tool_choice);
        if (chatTools) chatReq.tools = chatTools;
        if (chatToolChoice) chatReq.tool_choice = chatToolChoice;
        payload = JSON.stringify(chatReq);
        upstreamUrl = new URL(options.chatCompletionsEndpoint);
      } else {
        const requestBody = parsedBody && typeof parsedBody === "object" && !Array.isArray(parsedBody) ? { ...parsedBody } : {};
        const sanitized = options.sanitizeResponsesRequest ? options.sanitizeResponsesRequest(requestBody) : requestBody;
        payload = JSON.stringify(sanitized);
        upstreamUrl = new URL(options.responsesEndpoint);
      }
      const requestFn = upstreamUrl.protocol === "http:" ? httpRequest : httpsRequest;
      const proxyReq = requestFn({
        hostname: upstreamUrl.hostname,
        port: upstreamUrl.port || (upstreamUrl.protocol === "http:" ? 80 : 443),
        path: upstreamUrl.pathname,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
          ...options.bearerToken ? { "Authorization": `Bearer ${options.bearerToken}` } : {}
        }
      }, (upstreamRes) => {
        const status = upstreamRes.statusCode ?? 502;
        if (useChatPayload && effectiveStreaming && status >= 200 && status < 300) {
          forwardStreamingTextResponse(upstreamRes, res, parsedBody.model);
          return;
        }
        const chunks = [];
        upstreamRes.on("data", (chunk) => chunks.push(chunk));
        upstreamRes.on("end", () => {
          const rawResponseBody = Buffer.concat(chunks).toString();
          if (!useChatPayload) {
            res.writeHead(status, copyProxyHeaders(upstreamRes.headers));
            res.end(rawResponseBody);
            return;
          }
          try {
            const upstreamPayload = JSON.parse(rawResponseBody);
            if (upstreamPayload.error || status >= 400) {
              if (process.env.CODEXUI_PROXY_DEBUG === "1") {
                console.warn("[unified-responses-proxy]", JSON.stringify({
                  status,
                  upstreamUrl: upstreamUrl.toString(),
                  request: JSON.parse(payload),
                  response: upstreamPayload
                }));
              }
              res.writeHead(status, { "Content-Type": "application/json" });
              res.end(JSON.stringify(upstreamPayload));
              return;
            }
            const translated = chatCompletionToResponsesFormat(upstreamPayload, parsedBody.model);
            if (isStreaming) {
              sendSyntheticStreamingCompletion(res, translated);
            } else {
              res.writeHead(200, { "Content-Type": "application/json" });
              res.end(JSON.stringify(translated));
            }
          } catch {
            const detail = rawResponseBody.slice(0, 500).trim();
            res.writeHead(status >= 400 ? status : 502, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ error: { message: detail || "Bad gateway: failed to parse upstream response" } }));
          }
        });
      });
      proxyReq.on("error", (error) => {
        if (!res.headersSent) {
          res.writeHead(502, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: { message: `Proxy error: ${error.message}` } }));
        }
      });
      proxyReq.write(payload);
      proxyReq.end();
    } catch (error) {
      if (!res.headersSent) {
        const message = error instanceof Error ? error.message : "Unknown error";
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: { message } }));
      }
    }
  })();
}

// src/server/openRouterProxy.ts
var OPENROUTER_RESPONSES_ENDPOINT = "https://openrouter.ai/api/v1/responses";
var OPENROUTER_CHAT_COMPLETIONS_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions";
var OPENROUTER_ALLOWED_TOOL_TYPES = /* @__PURE__ */ new Set([
  "function",
  "openrouter:datetime",
  "openrouter:image_generation",
  "openrouter:experimental__search_models",
  "openrouter:web_search"
]);
function sanitizeOpenRouterResponsesRequest(payload) {
  const requestBody = { ...payload };
  const rawTools = Array.isArray(requestBody.tools) ? requestBody.tools : null;
  if (!rawTools) return requestBody;
  const sanitizedTools = rawTools.filter((tool) => {
    if (!tool || typeof tool !== "object" || Array.isArray(tool)) return false;
    const type = typeof tool.type === "string" ? String(tool.type) : "";
    return OPENROUTER_ALLOWED_TOOL_TYPES.has(type);
  });
  if (sanitizedTools.length === 0) {
    delete requestBody.tools;
    delete requestBody.tool_choice;
    return requestBody;
  }
  requestBody.tools = sanitizedTools;
  return requestBody;
}
function handleOpenRouterProxyRequest(req, res, bearerToken, wireApi) {
  handleUnifiedResponsesProxyRequest(req, res, {
    bearerToken,
    wireApi,
    responsesEndpoint: OPENROUTER_RESPONSES_ENDPOINT,
    chatCompletionsEndpoint: OPENROUTER_CHAT_COMPLETIONS_ENDPOINT,
    missingKeyMessage: "Missing OpenRouter API key",
    allowToolFallbackToResponses: true,
    sanitizeResponsesRequest: sanitizeOpenRouterResponsesRequest
  });
}

// src/server/zenProxy.ts
var ZEN_RESPONSES_ENDPOINT = "https://opencode.ai/zen/v1/responses";
var ZEN_CHAT_COMPLETIONS_ENDPOINT = "https://opencode.ai/zen/v1/chat/completions";
function handleZenProxyRequest(req, res, bearerToken, wireApi) {
  handleUnifiedResponsesProxyRequest(req, res, {
    bearerToken,
    wireApi,
    responsesEndpoint: ZEN_RESPONSES_ENDPOINT,
    chatCompletionsEndpoint: ZEN_CHAT_COMPLETIONS_ENDPOINT,
    missingKeyMessage: "Missing OpenCode Zen API key",
    requireBearerToken: false,
    allowToolFallbackToResponses: false,
    responsesPayloadFormat: "chat"
  });
}

// src/server/customEndpointProxy.ts
function joinEndpoint(baseUrl, path) {
  return `${baseUrl.replace(/\/+$/u, "")}${path}`;
}
function handleCustomEndpointProxyRequest(req, res, options) {
  handleUnifiedResponsesProxyRequest(req, res, {
    bearerToken: options.bearerToken,
    wireApi: options.wireApi,
    responsesEndpoint: joinEndpoint(options.baseUrl, "/responses"),
    chatCompletionsEndpoint: joinEndpoint(options.baseUrl, "/chat/completions"),
    missingKeyMessage: "Missing custom endpoint API key",
    allowToolFallbackToResponses: false
  });
}

// src/server/terminalManager.ts
import { chmodSync, existsSync as existsSync3, lstatSync, readFileSync, realpathSync, rmSync, writeFileSync } from "fs";
import { randomUUID } from "crypto";
import { createRequire } from "module";
import { basename as basename3, dirname, join as join5 } from "path";
import { homedir as homedir4 } from "os";
import { spawnSync as spawnSync3 } from "child_process";
var TERMINAL_BUFFER_LIMIT = 16 * 1024;
var DEFAULT_COLS = 80;
var DEFAULT_ROWS = 24;
var TERMINAL_NAME = "xterm-256color";
var require2 = createRequire(import.meta.url);
var ThreadTerminalManager = class {
  constructor(options = {}) {
    this.sessions = /* @__PURE__ */ new Map();
    this.activeSessionIdByThreadId = /* @__PURE__ */ new Map();
    this.listeners = /* @__PURE__ */ new Set();
    const terminalSpawn = loadOptionalTerminalSpawn(options.spawn);
    this.spawn = terminalSpawn.spawn;
    this.unavailableReason = terminalSpawn.reason;
    this.exists = options.exists ?? existsSync3;
    this.homeDir = options.homeDir ?? homedir4;
    this.cwd = options.cwd ?? process.cwd;
    this.platform = options.platform ?? process.platform;
    this.shell = options.shell ?? null;
    this.ensureSpawnHelperExecutable = options.ensureSpawnHelperExecutable ?? ensureNodePtyPrebuiltExecutable;
  }
  subscribe(listener) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }
  getAvailability() {
    return {
      available: this.spawn !== null,
      reason: this.unavailableReason
    };
  }
  attach(params) {
    this.requireAvailable();
    const threadId = params.threadId.trim();
    if (!threadId) {
      throw new Error("Missing threadId");
    }
    const requestedSessionId = params.sessionId?.trim() || "";
    const existingSessionId = params.newSession ? "" : requestedSessionId || this.activeSessionIdByThreadId.get(threadId) || "";
    const existing = existingSessionId ? this.sessions.get(existingSessionId) : null;
    if (existing) {
      this.activeSessionIdByThreadId.set(threadId, existing.id);
      this.resize(existing.id, params.cols, params.rows);
      const nextCwd = this.resolveCwd(params.cwd);
      if (nextCwd !== existing.cwd) {
        existing.cwd = nextCwd;
        existing.pty.write(`cd ${shellQuote(nextCwd)}\r`);
      }
      this.emitInit(existing);
      this.emitAttached(existing);
      return this.toSnapshot(existing);
    }
    const session = this.createSession({
      threadId,
      cwd: params.cwd,
      sessionId: requestedSessionId || randomUUID(),
      cols: params.cols,
      rows: params.rows
    });
    this.sessions.set(session.id, session);
    this.activeSessionIdByThreadId.set(threadId, session.id);
    this.emitAttached(session);
    return this.toSnapshot(session);
  }
  write(sessionId, data) {
    this.requireAvailable();
    const session = this.requireSession(sessionId);
    session.pty.write(data);
  }
  resize(sessionId, cols, rows) {
    const session = this.sessions.get(sessionId);
    if (!session) return;
    const nextCols = normalizeDimension(cols, DEFAULT_COLS);
    const nextRows = normalizeDimension(rows, DEFAULT_ROWS);
    session.pty.resize(nextCols, nextRows);
  }
  close(sessionId) {
    const session = this.sessions.get(sessionId);
    if (!session) return;
    this.sessions.delete(session.id);
    if (this.activeSessionIdByThreadId.get(session.threadId) === session.id) {
      this.activeSessionIdByThreadId.delete(session.threadId);
    }
    session.pty.kill();
    this.emit({
      method: "terminal-exit",
      params: {
        sessionId: session.id,
        threadId: session.threadId,
        code: null,
        signal: null
      }
    });
  }
  getSnapshotForThread(threadId) {
    const sessionId = this.activeSessionIdByThreadId.get(threadId.trim());
    if (!sessionId) return null;
    const session = this.sessions.get(sessionId);
    return session ? this.toSnapshot(session) : null;
  }
  dispose() {
    for (const sessionId of Array.from(this.sessions.keys())) {
      this.close(sessionId);
    }
    this.listeners.clear();
  }
  createSession(params) {
    const cwd = this.resolveCwd(params.cwd);
    const shell = this.resolveShell();
    const env = {
      ...process.env,
      TERM: TERMINAL_NAME
    };
    normalizeLocaleEnv(env, this.platform);
    delete env.TERMINFO;
    delete env.TERMINFO_DIRS;
    this.ensureSpawnHelperExecutable();
    if (!this.spawn) {
      throw new Error(this.unavailableReason || "Integrated terminal is unavailable on this host");
    }
    const pty = this.spawn(shell, [], {
      name: TERMINAL_NAME,
      cols: normalizeDimension(params.cols, DEFAULT_COLS),
      rows: normalizeDimension(params.rows, DEFAULT_ROWS),
      cwd,
      env
    });
    const session = {
      id: params.sessionId,
      threadId: params.threadId,
      cwd,
      shell: basename3(shell),
      pty,
      buffer: "",
      truncated: false
    };
    pty.onData((data) => {
      this.appendOutput(session, data);
    });
    pty.onExit(({ exitCode, signal }) => {
      if (this.sessions.get(session.id) === session) {
        this.sessions.delete(session.id);
      }
      if (this.activeSessionIdByThreadId.get(session.threadId) === session.id) {
        this.activeSessionIdByThreadId.delete(session.threadId);
      }
      this.emit({
        method: "terminal-exit",
        params: {
          sessionId: session.id,
          threadId: session.threadId,
          code: exitCode,
          signal: signal == null ? null : String(signal)
        }
      });
    });
    return session;
  }
  appendOutput(session, data) {
    const next = `${session.buffer}${data}`;
    if (next.length > TERMINAL_BUFFER_LIMIT) {
      session.buffer = next.slice(-TERMINAL_BUFFER_LIMIT);
      session.truncated = true;
    } else {
      session.buffer = next;
    }
    this.emit({
      method: "terminal-data",
      params: {
        sessionId: session.id,
        threadId: session.threadId,
        data
      }
    });
  }
  emitInit(session) {
    if (!session.buffer) return;
    this.emit({
      method: "terminal-init-log",
      params: {
        sessionId: session.id,
        threadId: session.threadId,
        log: session.buffer,
        truncated: session.truncated
      }
    });
  }
  emitAttached(session) {
    this.emit({
      method: "terminal-attached",
      params: {
        sessionId: session.id,
        threadId: session.threadId,
        cwd: session.cwd,
        shell: session.shell
      }
    });
  }
  emit(notification) {
    for (const listener of this.listeners) {
      listener(notification);
    }
  }
  requireSession(sessionId) {
    const session = this.sessions.get(sessionId.trim());
    if (!session) {
      throw new Error("Terminal session missing");
    }
    return session;
  }
  requireAvailable() {
    if (this.spawn) return;
    throw new Error(this.unavailableReason || "Integrated terminal is unavailable on this host");
  }
  resolveShell() {
    if (this.shell) return this.shell;
    if (this.platform === "win32") {
      return process.env.COMSPEC || "cmd.exe";
    }
    return process.env.SHELL || "/bin/zsh";
  }
  resolveCwd(value) {
    const cwd = value.trim();
    if (cwd && this.exists(cwd)) {
      return cwd;
    }
    const home = this.homeDir();
    if (home && this.exists(home)) {
      return home;
    }
    return this.cwd();
  }
  toSnapshot(session) {
    return {
      id: session.id,
      threadId: session.threadId,
      cwd: session.cwd,
      shell: session.shell,
      buffer: session.buffer,
      truncated: session.truncated
    };
  }
};
function loadOptionalTerminalSpawn(spawn6) {
  if (spawn6) {
    return { spawn: spawn6, reason: null };
  }
  if (spawn6 === null) {
    return { spawn: null, reason: "Integrated terminal is unavailable on this host" };
  }
  try {
    return { spawn: loadTerminalSpawn(), reason: null };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const suffix = message.includes("Cannot find module") ? "Native PTY support is not installed." : sanitizeUnavailableReason(message);
    return {
      spawn: null,
      reason: `Integrated terminal is unavailable on this host. ${suffix}`
    };
  }
}
function sanitizeUnavailableReason(message) {
  const firstLine = message.split("\n")[0]?.trim() || "";
  return firstLine ? firstLine : "Native PTY support could not be loaded.";
}
function normalizeDimension(value, fallback) {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(1, Math.min(500, Math.trunc(parsed)));
}
function loadTerminalSpawn() {
  repairNativePtyBuild("node-pty");
  if (resolveNodePtyPrebuiltPath()) {
    try {
      const terminal2 = require2("node-pty-prebuilt-multiarch");
      return terminal2.spawn;
    } catch {
    }
  }
  const terminal = require2("node-pty");
  return terminal.spawn;
}
function repairNativePtyBuild(packageName) {
  try {
    const packageJson = require2.resolve(`${packageName}/package.json`);
    const packageRoot = dirname(packageJson);
    const buildDir = join5(packageRoot, "build");
    const makefile = join5(buildDir, "Makefile");
    const binary = join5(buildDir, "Release", "pty.node");
    if (!existsSync3(makefile)) return;
    if (!isBrokenSymlink(binary)) return;
    const source = readFileSync(makefile, "utf8");
    const patched = source.replace(
      /^cmd_copy = ln -f "\$<" "\$@" 2>\/dev\/null \|\| \(rm -rf "\$@" && cp -af "\$<" "\$@"\)$/m,
      'cmd_copy = rm -rf "$@" && cp -af "$<" "$@"'
    );
    if (patched !== source) {
      writeFileSync(makefile, patched);
    }
    rmSync(binary, { force: true });
    spawnSync3("make", ["BUILDTYPE=Release", "-C", buildDir], { stdio: "ignore" });
  } catch {
  }
}
function isBrokenSymlink(path) {
  try {
    if (!lstatSync(path).isSymbolicLink()) return false;
    try {
      return !existsSync3(realpathSync(path));
    } catch {
      return true;
    }
  } catch {
    return false;
  }
}
function resolveNodePtyPrebuiltPath() {
  try {
    const packageJson = require2.resolve("node-pty-prebuilt-multiarch/package.json");
    const packageRoot = dirname(packageJson);
    const builtPath = join5(packageRoot, "build", "Release", "pty.node");
    if (existsSync3(builtPath)) {
      return builtPath;
    }
    const runtime = Object.prototype.hasOwnProperty.call(process.versions, "electron") ? "electron" : "node";
    const libc = process.platform === "linux" && existsSync3("/etc/alpine-release") ? ".musl" : "";
    const binaryName = `${runtime}.abi${process.versions.modules}${libc}.node`;
    const binaryPath = join5(packageRoot, "prebuilds", `${process.platform}-${process.arch}`, binaryName);
    return existsSync3(binaryPath) ? binaryPath : null;
  } catch {
    return null;
  }
}
function ensureNodePtyPrebuiltExecutable() {
  if (process.platform !== "darwin" && process.platform !== "linux") return;
  ensurePackageSpawnHelperExecutable("node-pty");
  ensurePackageSpawnHelperExecutable("node-pty-prebuilt-multiarch");
}
function ensurePackageSpawnHelperExecutable(packageName) {
  try {
    const packageRoot = dirname(require2.resolve(`${packageName}/package.json`));
    const helperPath = join5(packageRoot, "prebuilds", `${process.platform}-${process.arch}`, "spawn-helper");
    if (existsSync3(helperPath)) {
      chmodSync(helperPath, 493);
    }
  } catch {
  }
}
function normalizeLocaleEnv(env, platform) {
  const locale = platform === "darwin" ? "en_US.UTF-8" : "C.UTF-8";
  env.LANG = locale;
  env.LC_ALL = locale;
  env.LC_CTYPE = locale;
}
function shellQuote(value) {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

// src/pathUtils.ts
function stripWindowsDevicePathPrefix(value) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("\\\\?\\UNC\\")) {
    return `\\\\${trimmed.slice("\\\\?\\UNC\\".length)}`;
  }
  if (trimmed.startsWith("\\\\?\\")) {
    return trimmed.slice("\\\\?\\".length);
  }
  return trimmed;
}
function normalizePathForUi(value) {
  return stripWindowsDevicePathPrefix(value);
}
function isWindowsLikePath(value) {
  return /^[a-z]:[\\/]/iu.test(value) || value.startsWith("\\\\");
}
function isAbsoluteLikePath(value) {
  const normalized = normalizePathForUi(value);
  return normalized.startsWith("/") || isWindowsLikePath(normalized);
}

// src/server/codexAppServerBridge.ts
var COMPOSIO_CONNECTORS_PAGE_LIMIT_MAX = 1e3;
var PROVIDER_MODELS_FETCH_TIMEOUT_MS = 5e3;
var THREAD_RESPONSE_TURN_LIMIT = 10;
var THREAD_TURN_PAGE_READ_CACHE_TTL_MS = 3e4;
var THREAD_METHODS_WITH_TURNS = /* @__PURE__ */ new Set(["thread/read", "thread/resume", "thread/fork", "thread/rollback"]);
var THREAD_METHODS_WITH_THREAD_SNAPSHOT = /* @__PURE__ */ new Set([...THREAD_METHODS_WITH_TURNS, "thread/start"]);
var THREAD_SEARCH_FULL_TEXT_THREAD_LIMIT = 100;
var PROJECTLESS_THREAD_DIRECTORY_MAX_ATTEMPTS = 100;
var PROJECTLESS_THREAD_READABLE_DIRECTORY_ATTEMPTS = 20;
var PROJECTLESS_THREAD_SLUG_MAX_LENGTH = 80;
var API_PERF_LOGGING_ENV_KEY = "CODEXUI_API_PERF_LOGGING";
var API_PERF_MS_THRESHOLD_ENV_KEY = "CODEXUI_API_PERF_MS_THRESHOLD";
var API_PERF_BODY_MB_THRESHOLD_ENV_KEY = "CODEXUI_API_PERF_BODY_MB_THRESHOLD";
var DEFAULT_API_PERF_MS_THRESHOLD = 300;
var DEFAULT_API_PERF_BODY_MB_THRESHOLD = 1;
var MB_DIVISOR = 1024 * 1024;
var COMPOSIO_USER_DATA_PATH = join6(homedir5(), ".composio", "user_data.json");
var SESSION_SKILL_INPUT_CACHE_LIMIT = 64;
var sessionSkillInputCache = /* @__PURE__ */ new Map();
function parseSessionSkillText(value) {
  const trimmed = value.trim();
  if (!trimmed.startsWith("<skill>")) return null;
  const name = trimmed.match(/<name>\s*([\s\S]*?)\s*<\/name>/u)?.[1]?.trim() ?? "";
  const path = trimmed.match(/<path>\s*([\s\S]*?)\s*<\/path>/u)?.[1]?.trim() ?? "";
  if (!name || !path) return null;
  return { name, path };
}
function buildSessionSkillInputsByTurn(sessionLogRaw) {
  let currentTurnId = "";
  const skillsByTurnId = /* @__PURE__ */ new Map();
  for (const line of sessionLogRaw.split("\n")) {
    if (!line.trim()) continue;
    let row = null;
    try {
      row = JSON.parse(line);
    } catch {
      continue;
    }
    if (row.type === "turn_context") {
      const payloadRecord2 = asRecord6(row.payload);
      currentTurnId = readNonEmptyString(payloadRecord2?.turn_id) || currentTurnId;
      continue;
    }
    if (row.type === "event_msg") {
      const payloadRecord2 = asRecord6(row.payload);
      if (payloadRecord2?.type === "task_started") {
        currentTurnId = readNonEmptyString(payloadRecord2.turn_id) || currentTurnId;
      }
      continue;
    }
    if (row.type !== "response_item" || !currentTurnId) continue;
    const payloadRecord = asRecord6(row.payload);
    if (payloadRecord?.type !== "message" || payloadRecord.role !== "user") continue;
    const content = Array.isArray(payloadRecord.content) ? payloadRecord.content : [];
    for (const contentItem of content) {
      const contentRecord = asRecord6(contentItem);
      if (contentRecord?.type !== "input_text" || typeof contentRecord.text !== "string") continue;
      const skill = parseSessionSkillText(contentRecord.text);
      if (!skill) continue;
      const existing = skillsByTurnId.get(currentTurnId) ?? [];
      if (!existing.some((item) => item.path === skill.path)) {
        existing.push(skill);
        skillsByTurnId.set(currentTurnId, existing);
      }
    }
  }
  return skillsByTurnId;
}
async function readCachedSessionSkillInputsByTurn(sessionPath) {
  const sessionStat = await stat4(sessionPath);
  const cached = sessionSkillInputCache.get(sessionPath);
  if (cached && cached.size === sessionStat.size && cached.mtimeMs === sessionStat.mtimeMs) {
    return cached.skillsByTurnId;
  }
  const sessionLogRaw = await readFile3(sessionPath, "utf8");
  const skillsByTurnId = buildSessionSkillInputsByTurn(sessionLogRaw);
  sessionSkillInputCache.set(sessionPath, {
    size: sessionStat.size,
    mtimeMs: sessionStat.mtimeMs,
    skillsByTurnId
  });
  if (sessionSkillInputCache.size > SESSION_SKILL_INPUT_CACHE_LIMIT) {
    const oldestKey = sessionSkillInputCache.keys().next().value;
    if (oldestKey) sessionSkillInputCache.delete(oldestKey);
  }
  return skillsByTurnId;
}
function mergeSessionSkillInputsIntoTurnsFromMap(turns, skillsByTurnId) {
  const turnIds = /* @__PURE__ */ new Set();
  for (const turn of turns) {
    const turnRecord = asRecord6(turn);
    const turnId = readNonEmptyString(turnRecord?.id);
    if (turnId) turnIds.add(turnId);
  }
  if (turnIds.size === 0) return turns;
  if (skillsByTurnId.size === 0) return turns;
  let changed = false;
  const nextTurns = turns.map((turn) => {
    const turnRecord = asRecord6(turn);
    const turnId = readNonEmptyString(turnRecord?.id);
    const skills = turnId ? skillsByTurnId.get(turnId) : void 0;
    const items = Array.isArray(turnRecord?.items) ? turnRecord.items : null;
    if (!turnRecord || !skills || skills.length === 0 || !items) return turn;
    let targetUserMessageIndex = -1;
    for (let index = items.length - 1; index >= 0; index -= 1) {
      const itemRecord = asRecord6(items[index]);
      if (itemRecord?.type === "userMessage" && Array.isArray(itemRecord.content)) {
        targetUserMessageIndex = index;
        break;
      }
    }
    if (targetUserMessageIndex < 0) return turn;
    let addedToMessage = false;
    const nextItems = items.map((item, index) => {
      const itemRecord = asRecord6(item);
      const content = Array.isArray(itemRecord?.content) ? itemRecord.content : null;
      if (index !== targetUserMessageIndex || itemRecord?.type !== "userMessage" || !content) return item;
      const existingSkillPaths = new Set(
        content.flatMap((contentItem) => {
          const contentRecord = asRecord6(contentItem);
          const path = typeof contentRecord?.path === "string" ? contentRecord.path.trim() : "";
          return contentRecord?.type === "skill" && path ? [path] : [];
        })
      );
      const missingSkills = skills.filter((skill) => !existingSkillPaths.has(skill.path));
      if (missingSkills.length === 0) return item;
      addedToMessage = true;
      changed = true;
      return {
        ...itemRecord,
        content: [
          ...content,
          ...missingSkills.map((skill) => ({ type: "skill", name: skill.name, path: skill.path }))
        ]
      };
    });
    return addedToMessage ? { ...turnRecord, items: nextItems } : turn;
  });
  return changed ? nextTurns : turns;
}
async function mergeSessionSkillInputsIntoThreadResult(result) {
  const record = asRecord6(result);
  const thread = asRecord6(record?.thread);
  const turns = Array.isArray(thread?.turns) ? thread.turns : null;
  const sessionPath = readNonEmptyString(thread?.path);
  if (!record || !thread || !turns || turns.length === 0 || !sessionPath || !isAbsolute2(sessionPath)) {
    return result;
  }
  try {
    const skillsByTurnId = await readCachedSessionSkillInputsByTurn(sessionPath);
    const mergedTurns = mergeSessionSkillInputsIntoTurnsFromMap(turns, skillsByTurnId);
    if (mergedTurns === turns) return result;
    return {
      ...record,
      thread: {
        ...thread,
        turns: mergedTurns
      }
    };
  } catch {
    return result;
  }
}
function readEnvValueFromFile(filePath, key) {
  try {
    const content = readFileSync2(filePath, "utf8");
    const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const match = content.match(new RegExp(`^\\s*${escapedKey}\\s*=\\s*(.+)\\s*$`, "m"));
    if (!match) return null;
    const rawValue = match[1]?.trim() ?? "";
    if (!rawValue) return null;
    if (rawValue.startsWith('"') && rawValue.endsWith('"') || rawValue.startsWith("'") && rawValue.endsWith("'")) {
      return rawValue.slice(1, -1).trim();
    }
    return rawValue;
  } catch {
    return null;
  }
}
function parseBooleanEnvFlag(value) {
  if (!value) return null;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return null;
}
function resolveApiPerfLoggingEnabled() {
  const explicitValue = parseBooleanEnvFlag(process.env[API_PERF_LOGGING_ENV_KEY]);
  if (explicitValue !== null) return explicitValue;
  const fromEnvLocal = parseBooleanEnvFlag(readEnvValueFromFile(".env.local", API_PERF_LOGGING_ENV_KEY));
  if (fromEnvLocal !== null) return fromEnvLocal;
  const fromEnv = parseBooleanEnvFlag(readEnvValueFromFile(".env", API_PERF_LOGGING_ENV_KEY));
  if (fromEnv !== null) return fromEnv;
  return false;
}
var API_PERF_LOGGING_ENABLED = resolveApiPerfLoggingEnabled();
function parseNumberEnvFlag(value) {
  if (!value) return null;
  const parsed = Number.parseFloat(value.trim());
  if (!Number.isFinite(parsed)) return null;
  return parsed;
}
function resolveNumericEnvConfig(envKey, fallback) {
  const fromProcess = parseNumberEnvFlag(process.env[envKey]);
  if (fromProcess !== null) return fromProcess;
  const fromEnvLocal = parseNumberEnvFlag(readEnvValueFromFile(".env.local", envKey));
  if (fromEnvLocal !== null) return fromEnvLocal;
  const fromEnv = parseNumberEnvFlag(readEnvValueFromFile(".env", envKey));
  if (fromEnv !== null) return fromEnv;
  return fallback;
}
var API_PERF_MS_THRESHOLD = resolveNumericEnvConfig(API_PERF_MS_THRESHOLD_ENV_KEY, DEFAULT_API_PERF_MS_THRESHOLD);
var API_PERF_BODY_MB_THRESHOLD = resolveNumericEnvConfig(API_PERF_BODY_MB_THRESHOLD_ENV_KEY, DEFAULT_API_PERF_BODY_MB_THRESHOLD);
function getChunkByteLength(chunk, encoding) {
  if (typeof chunk === "string") {
    return Buffer.byteLength(chunk, encoding);
  }
  if (chunk instanceof Uint8Array) {
    return chunk.byteLength;
  }
  if (ArrayBuffer.isView(chunk)) {
    return chunk.byteLength;
  }
  if (chunk instanceof ArrayBuffer) {
    return chunk.byteLength;
  }
  return 0;
}
function asRecord6(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function isInlineDataUrl(value) {
  return /^data:/iu.test(value.trim());
}
function inferImageMimeTypeFromBytes(bytes) {
  if (bytes.length >= 8 && bytes[0] === 137 && bytes[1] === 80 && bytes[2] === 78 && bytes[3] === 71 && bytes[4] === 13 && bytes[5] === 10 && bytes[6] === 26 && bytes[7] === 10) {
    return "image/png";
  }
  if (bytes.length >= 3 && bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255) {
    return "image/jpeg";
  }
  if (bytes.length >= 12 && bytes[0] === 82 && bytes[1] === 73 && bytes[2] === 70 && bytes[3] === 70 && bytes[8] === 87 && bytes[9] === 69 && bytes[10] === 66 && bytes[11] === 80) {
    return "image/webp";
  }
  if (bytes.length >= 6 && bytes[0] === 71 && bytes[1] === 73 && bytes[2] === 70 && bytes[3] === 56 && (bytes[4] === 55 || bytes[4] === 57) && bytes[5] === 97) {
    return "image/gif";
  }
  return null;
}
function inferImageMimeTypeFromBase64(value) {
  const compact = value.trim().replace(/\s+/gu, "");
  if (compact.length < 32 || !/^[A-Za-z0-9+/]+={0,2}$/u.test(compact)) return null;
  try {
    return inferImageMimeTypeFromBytes(Buffer.from(compact.slice(0, 64), "base64"));
  } catch {
    return null;
  }
}
function normalizeBase64ImageDataUrl(value, mimeType) {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (isInlineDataUrl(trimmed)) {
    return /^data:image\//iu.test(trimmed) ? trimmed : null;
  }
  const compact = trimmed.replace(/\s+/gu, "");
  const inferredMimeType = inferImageMimeTypeFromBase64(compact);
  if (!inferredMimeType) return null;
  const normalizedMimeType = mimeType.trim().toLowerCase();
  const finalMimeType = normalizedMimeType.startsWith("image/") && normalizedMimeType !== "image/*" ? normalizedMimeType : inferredMimeType;
  return `data:${finalMimeType};base64,${compact}`;
}
function extensionFromMimeType(mimeType) {
  const normalized = mimeType.trim().toLowerCase();
  if (normalized === "image/png") return ".png";
  if (normalized === "image/jpeg") return ".jpg";
  if (normalized === "image/webp") return ".webp";
  if (normalized === "image/gif") return ".gif";
  if (normalized === "image/svg+xml") return ".svg";
  if (normalized === "application/pdf") return ".pdf";
  return "";
}
function asNonEmptyString(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}
function toAttachmentLinkTarget(block, fallback) {
  const candidate = asNonEmptyString(block.path) ?? asNonEmptyString(block.file_path) ?? asNonEmptyString(block.filename) ?? asNonEmptyString(block.file_id) ?? fallback;
  if (candidate.startsWith("file://")) return candidate;
  if (candidate.startsWith("/")) return `file://${candidate}`;
  return `attachment://${candidate}`;
}
async function persistInlineDataUrlToLocalFile(dataUrl, baseName) {
  const trimmed = dataUrl.trim();
  const match = /^data:([^;,]*)(;base64)?,(.*)$/isu.exec(trimmed);
  if (!match) return null;
  const mimeType = (match[1] ?? "").trim().toLowerCase();
  const encodedPayload = match[3] ?? "";
  let bytes;
  try {
    bytes = match[2] ? Buffer.from(encodedPayload, "base64") : Buffer.from(decodeURIComponent(encodedPayload), "utf8");
  } catch {
    return null;
  }
  if (bytes.length === 0) return null;
  const hash = createHash2("sha1").update(bytes).digest("hex");
  const ext = extensionFromMimeType(mimeType);
  const mediaDir = join6(tmpdir4(), "codex-web-inline-media");
  await mkdir4(mediaDir, { recursive: true });
  const fileName = `${baseName}-${hash}${ext}`;
  const filePath = join6(mediaDir, fileName);
  try {
    await stat4(filePath);
  } catch {
    await writeFile4(filePath, bytes);
  }
  return filePath;
}
function toLocalImageProxyUrl(path) {
  return `/codex-local-image?path=${encodeURIComponent(path)}`;
}
var INLINE_IMAGE_FIELD_NAMES = /* @__PURE__ */ new Set([
  "b64_json",
  "image",
  "image_url",
  "images",
  "result",
  "url"
]);
function isPotentialInlineImageField(fieldName) {
  return typeof fieldName === "string" && INLINE_IMAGE_FIELD_NAMES.has(fieldName);
}
async function sanitizeInlineImageString(value, context) {
  if (!isPotentialInlineImageField(context.fieldName)) {
    return { value, changed: false };
  }
  const dataUrl = normalizeBase64ImageDataUrl(value, "image/*");
  if (!dataUrl) return { value, changed: false };
  const localUrl = await persistInlineDataUrlToLocalFile(
    dataUrl,
    `inline-image-${context.turnId}-${context.itemId}-${context.fieldName}-${String(context.blockIndex)}`
  );
  if (!localUrl) return { value, changed: false };
  return { value: toLocalImageProxyUrl(localUrl), changed: true };
}
async function sanitizeInlineUserContentBlock(block, context) {
  const record = asRecord6(block);
  if (!record) return block;
  const type = asNonEmptyString(record.type) ?? "";
  const imageUrl = asNonEmptyString(record.url) ?? asNonEmptyString(record.image_url);
  if (imageUrl && isInlineDataUrl(imageUrl)) {
    const localUrl = await persistInlineDataUrlToLocalFile(imageUrl, `inline-image-${context.turnId}-${context.itemId}-${String(context.blockIndex)}`);
    if (localUrl) {
      const nextRecord = { ...record };
      if (typeof record.url === "string") {
        nextRecord.url = toLocalImageProxyUrl(localUrl);
      }
      if (typeof record.image_url === "string") {
        nextRecord.image_url = toLocalImageProxyUrl(localUrl);
      }
      return {
        ...nextRecord,
        type: "image"
      };
    }
    const target = toAttachmentLinkTarget(record, `inline-image/${context.turnId}/${context.itemId}/${String(context.blockIndex)}`);
    return {
      type: "text",
      text: `Image attachment: ${target}`
    };
  }
  if (type === "imageGeneration" || type === "image_generation") {
    const rawResult = asNonEmptyString(record.result) ?? asNonEmptyString(record.b64_json) ?? asNonEmptyString(record.image);
    const mimeType = asNonEmptyString(record.mime_type) ?? asNonEmptyString(record.mimeType) ?? "image/png";
    const dataUrl = rawResult ? normalizeBase64ImageDataUrl(rawResult, mimeType) : null;
    if (dataUrl) {
      const localUrl = await persistInlineDataUrlToLocalFile(dataUrl, `generated-image-${context.turnId}-${context.itemId}`);
      if (localUrl) {
        return {
          ...record,
          type: "imageView",
          path: localUrl
        };
      }
    }
  }
  const inlineFileData = asNonEmptyString(record.file_data) ?? asNonEmptyString(record.data) ?? asNonEmptyString(record.base64);
  if ((type.includes("file") || type === "input_file" || type === "file") && inlineFileData) {
    const mimeType = asNonEmptyString(record.mime_type) ?? "application/octet-stream";
    const fileDataUrl = `data:${mimeType};base64,${inlineFileData}`;
    const localUrl = await persistInlineDataUrlToLocalFile(fileDataUrl, `inline-file-${context.turnId}-${context.itemId}-${String(context.blockIndex)}`);
    if (localUrl) {
      return {
        type: "text",
        text: `File attachment: ${localUrl}`
      };
    }
    const target = toAttachmentLinkTarget(record, `inline-file/${context.turnId}/${context.itemId}/${String(context.blockIndex)}`);
    return {
      type: "text",
      text: `File attachment: ${target}`
    };
  }
  return block;
}
async function sanitizeInlinePayloadDeep(value, context) {
  const maybeBlock = await sanitizeInlineUserContentBlock(value, context);
  if (maybeBlock !== value) {
    return { value: maybeBlock, changed: true };
  }
  if (typeof value === "string") {
    return sanitizeInlineImageString(value, context);
  }
  if (Array.isArray(value)) {
    let changed2 = false;
    const nextArray = [];
    for (let index = 0; index < value.length; index += 1) {
      const nested = await sanitizeInlinePayloadDeep(value[index], {
        turnId: context.turnId,
        itemId: context.itemId,
        blockIndex: index,
        fieldName: context.fieldName
      });
      if (nested.changed) changed2 = true;
      nextArray.push(nested.value);
    }
    return changed2 ? { value: nextArray, changed: true } : { value, changed: false };
  }
  const record = asRecord6(value);
  if (!record) return { value, changed: false };
  let changed = false;
  const nextRecord = {};
  for (const [key, nestedValue] of Object.entries(record)) {
    const nested = await sanitizeInlinePayloadDeep(nestedValue, {
      turnId: context.turnId,
      itemId: context.itemId,
      blockIndex: context.blockIndex,
      fieldName: key
    });
    if (nested.changed) changed = true;
    nextRecord[key] = nested.value;
  }
  return changed ? { value: nextRecord, changed: true } : { value, changed: false };
}
async function sanitizeThreadTurnsInlinePayloads(method, result) {
  if (!THREAD_METHODS_WITH_TURNS.has(method)) return result;
  const record = asRecord6(result);
  const thread = asRecord6(record?.thread);
  const turns = Array.isArray(thread?.turns) ? thread.turns : null;
  if (!record || !thread || !turns || turns.length === 0) return result;
  let changed = false;
  const nextTurns = [];
  for (let turnIndex = 0; turnIndex < turns.length; turnIndex += 1) {
    const turn = turns[turnIndex];
    const turnRecord = asRecord6(turn);
    const turnId = asNonEmptyString(turnRecord?.id) ?? "turn";
    const items = Array.isArray(turnRecord?.items) ? turnRecord.items : null;
    if (!turnRecord || !items) {
      nextTurns.push(turn);
      continue;
    }
    let itemChanged = false;
    const nextItems = [];
    for (let itemIndex = 0; itemIndex < items.length; itemIndex += 1) {
      const item = items[itemIndex];
      const itemRecord = asRecord6(item);
      const itemId = asNonEmptyString(itemRecord?.id) ?? "item";
      if (!itemRecord) {
        nextItems.push(item);
        continue;
      }
      const sanitizedItem = await sanitizeInlinePayloadDeep(item, {
        turnId,
        itemId,
        blockIndex: itemIndex + turnIndex
      });
      if (!sanitizedItem.changed) {
        nextItems.push(item);
        continue;
      }
      itemChanged = true;
      nextItems.push(sanitizedItem.value);
    }
    if (!itemChanged) {
      nextTurns.push(turn);
      continue;
    }
    changed = true;
    nextTurns.push({
      ...turnRecord,
      items: nextItems
    });
  }
  if (!changed) return result;
  return {
    ...record,
    thread: {
      ...thread,
      turns: nextTurns
    }
  };
}
function trimThreadTurnsInRpcResult(method, result) {
  if (!THREAD_METHODS_WITH_TURNS.has(method)) return result;
  const record = asRecord6(result);
  const thread = asRecord6(record?.thread);
  const turns = Array.isArray(thread?.turns) ? thread.turns : null;
  if (!record || !thread || !turns || turns.length <= THREAD_RESPONSE_TURN_LIMIT) return result;
  const startTurnIndex = Math.max(0, turns.length - THREAD_RESPONSE_TURN_LIMIT);
  return {
    ...record,
    threadTurnStartIndex: startTurnIndex,
    thread: {
      ...thread,
      turns: turns.slice(startTurnIndex)
    }
  };
}
function getErrorMessage6(payload, fallback) {
  if (payload instanceof Error && payload.message.trim().length > 0) {
    return payload.message;
  }
  const record = asRecord6(payload);
  if (!record) return fallback;
  if (typeof record.message === "string" && record.message.length > 0) return record.message;
  const error = record.error;
  if (typeof error === "string" && error.length > 0) return error;
  const nestedError = asRecord6(error);
  if (nestedError && typeof nestedError.message === "string" && nestedError.message.length > 0) {
    return nestedError.message;
  }
  return fallback;
}
function isUnauthenticatedRateLimitError(error) {
  const message = getErrorMessage6(error, "").toLowerCase();
  return message.includes("authentication required") && message.includes("rate limits");
}
function isEmptyThreadReadError(error) {
  const message = getErrorMessage6(error, "").toLowerCase();
  return message.includes("failed to read thread") && message.includes("rollout") && message.includes("is empty");
}
function isThreadMaterializationPendingError(error) {
  const message = getErrorMessage6(error, "").toLowerCase();
  return message.includes("not materialized yet") && message.includes("includeturns is unavailable before first user message");
}
function isThreadNotFoundError(error) {
  const message = getErrorMessage6(error, "").toLowerCase();
  return message.includes("thread not found") || message.includes("no rollout found for thread id");
}
function readStreamTurnId(params) {
  const directTurnId = readNonEmptyString(params.turnId) || readNonEmptyString(params.turn_id);
  if (directTurnId) return directTurnId;
  const turn = asRecord6(params.turn);
  return readNonEmptyString(turn?.id);
}
function readStreamTurnErrorMessage(frame) {
  const params = asRecord6(frame.params);
  if (!params) return null;
  const turnId = readStreamTurnId(params);
  if (!turnId) return null;
  if (frame.method === "turn/completed") {
    const turn = asRecord6(params.turn);
    if (turn?.status !== "failed") return null;
    const message = getErrorMessage6(turn.error, "");
    return message ? { turnId, message } : null;
  }
  if (frame.method === "error" && params.willRetry !== true) {
    const message = getErrorMessage6(params.error, "") || readNonEmptyString(params.message);
    return message ? { turnId, message } : null;
  }
  return null;
}
function mergeStreamTurnErrorsIntoThreadResult(appServer, result) {
  const record = asRecord6(result);
  const thread = asRecord6(record?.thread);
  const threadId = readNonEmptyString(thread?.id);
  const turns = Array.isArray(thread?.turns) ? thread.turns : null;
  if (!record || !thread || !threadId || !turns || turns.length === 0) return result;
  const errorsByTurnId = /* @__PURE__ */ new Map();
  for (const frame of appServer.getStreamEvents(threadId, STREAM_EVENT_BUFFER_LIMIT)) {
    const error = readStreamTurnErrorMessage(frame);
    if (error) errorsByTurnId.set(error.turnId, error.message);
  }
  if (errorsByTurnId.size === 0) return result;
  let changed = false;
  const mergedTurns = turns.map((turn) => {
    const turnRecord = asRecord6(turn);
    const turnId = readNonEmptyString(turnRecord?.id);
    const message = turnId ? errorsByTurnId.get(turnId) : "";
    if (!turnRecord || !turnId || !message) return turn;
    const existingErrorMessage = getErrorMessage6(turnRecord.error, "");
    if (turnRecord.status === "failed" && existingErrorMessage) return turn;
    changed = true;
    return {
      ...turnRecord,
      status: "failed",
      error: {
        message,
        codexErrorInfo: null,
        additionalDetails: null
      }
    };
  });
  if (!changed) return result;
  return {
    ...record,
    thread: {
      ...thread,
      turns: mergedTurns
    }
  };
}
var warnedCodexAuthReadFailures = /* @__PURE__ */ new Set();
function getErrorCode(error) {
  return typeof error === "object" && error !== null && "code" in error ? String(error.code ?? "") : null;
}
function getCodexAuthReadErrorMessage(error) {
  return error instanceof Error && error.message.trim().length > 0 ? error.message : String(error);
}
function warnCodexAuthReadFailure(authPath, error) {
  const message = getCodexAuthReadErrorMessage(error);
  const warningKey = `${authPath}:${message}`;
  if (warnedCodexAuthReadFailures.has(warningKey)) return;
  warnedCodexAuthReadFailures.add(warningKey);
  console.warn("[codex-auth] Unable to read Codex auth state", { path: authPath, error: message });
}
async function hasUsableCodexAuth() {
  const authPath = getCodexAuthPath();
  try {
    const raw = await readFile3(authPath, "utf8");
    const auth = JSON.parse(raw);
    return Boolean(auth.tokens?.access_token?.trim() || auth.tokens?.refresh_token?.trim());
  } catch (error) {
    if (getErrorCode(error) !== "ENOENT") {
      warnCodexAuthReadFailure(authPath, error);
    }
    return false;
  }
}
function setJson4(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}
function logProviderModelDiscoveryWarning(message, details) {
  console.warn("[codex-provider-models]", message, details);
}
function isTimeoutError(payload) {
  return payload instanceof Error && (payload.name === "AbortError" || payload.name === "TimeoutError");
}
function formatProjectlessDateSegment(date = /* @__PURE__ */ new Date()) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}
function buildProjectlessPromptSlug(prompt) {
  const slug = prompt?.toLowerCase().match(/[a-z0-9]+/g)?.slice(0, 6).join("-").slice(0, PROJECTLESS_THREAD_SLUG_MAX_LENGTH);
  return slug && slug.length > 0 ? slug : "new-chat";
}
function buildProjectlessUniqueSuffix() {
  return `${Date.now().toString(36)}-${randomBytes(4).toString("hex")}`;
}
function buildProjectlessFolderName(slug, index, uniqueSuffix = buildProjectlessUniqueSuffix()) {
  if (index === 0) return slug;
  if (index < PROJECTLESS_THREAD_READABLE_DIRECTORY_ATTEMPTS) return `${slug}-${index + 1}`;
  const suffix = `-${uniqueSuffix}`;
  const maxSlugLength = Math.max(1, PROJECTLESS_THREAD_SLUG_MAX_LENGTH - suffix.length);
  return `${slug.slice(0, maxSlugLength)}${suffix}`;
}
async function ensureRealDirectory(path, label) {
  const info = await lstat2(path);
  if (info.isSymbolicLink() || !info.isDirectory()) {
    throw new Error(`${label} must be a real directory`);
  }
}
async function createProjectlessThreadDirectory(prompt) {
  const workspaceRoot = join6(homedir5(), "Documents", "Codex");
  await mkdir4(workspaceRoot, { recursive: true });
  await ensureRealDirectory(workspaceRoot, "Projectless workspace root");
  const dateDir = join6(workspaceRoot, formatProjectlessDateSegment());
  await mkdir4(dateDir, { recursive: true });
  await ensureRealDirectory(dateDir, "Projectless thread date directory");
  const slug = buildProjectlessPromptSlug(prompt);
  for (let index = 0; index < PROJECTLESS_THREAD_DIRECTORY_MAX_ATTEMPTS; index += 1) {
    const folderName = buildProjectlessFolderName(slug, index);
    const cwd = join6(dateDir, folderName);
    try {
      await mkdir4(cwd, { recursive: false });
      return { cwd, outputDirectory: cwd, workspaceRoot };
    } catch {
      try {
        await stat4(cwd);
      } catch {
        throw new Error("Failed to create new chat folder");
      }
    }
  }
  throw new Error("Unable to create a unique new chat folder");
}
function normalizeGithubCloneUrl(rawUrl) {
  const trimmedUrl = rawUrl.trim();
  if (!trimmedUrl) throw new Error("Missing GitHub repository URL");
  const sshMatch = trimmedUrl.match(/^git@github\.com:([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?$/u);
  if (sshMatch) {
    const repoName2 = sshMatch[2];
    return { url: `git@github.com:${sshMatch[1]}/${repoName2}.git`, repoName: repoName2 };
  }
  let parsed;
  try {
    parsed = new URL(trimmedUrl);
  } catch {
    throw new Error("Enter a valid GitHub repository URL");
  }
  if (parsed.hostname.toLowerCase() !== "github.com") {
    throw new Error("Only github.com repository URLs are supported");
  }
  const segments = parsed.pathname.split("/").filter(Boolean);
  if (segments.length < 2) {
    throw new Error("Enter a GitHub repository URL with owner and repository name");
  }
  const owner = segments[0];
  const repoName = segments[1].replace(/\.git$/iu, "");
  if (!/^[A-Za-z0-9_.-]+$/u.test(owner) || !/^[A-Za-z0-9_.-]+$/u.test(repoName)) {
    throw new Error("GitHub repository owner or name contains unsupported characters");
  }
  return { url: `https://github.com/${owner}/${repoName}.git`, repoName };
}
async function cloneGithubRepositoryIntoBase(rawUrl, rawBasePath) {
  const basePath = rawBasePath.trim();
  if (!basePath) throw new Error("Missing clone destination folder");
  const normalizedBasePath = isAbsolute2(basePath) ? basePath : resolve2(basePath);
  await ensureRealDirectory(normalizedBasePath, "Clone destination folder");
  const { url, repoName } = normalizeGithubCloneUrl(rawUrl);
  const targetPath = join6(normalizedBasePath, repoName);
  try {
    await stat4(targetPath);
    throw new Error(`Destination already exists: ${targetPath}`);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  try {
    await runCommand3("git", ["clone", url, targetPath], { cwd: normalizedBasePath, timeoutMs: 5 * 6e4 });
  } catch (error) {
    await rm4(targetPath, { recursive: true, force: true }).catch(() => void 0);
    throw error;
  }
  await persistWorkspaceRoot(targetPath, "");
  return targetPath;
}
function normalizeHeaderValue(value) {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}
function normalizeQueryParams(value) {
  const params = new URLSearchParams();
  const record = asRecord6(value);
  if (!record) return params;
  for (const [key, rawValue] of Object.entries(record)) {
    const normalized = normalizeHeaderValue(rawValue);
    if (!normalized) continue;
    params.set(key, normalized);
  }
  return params;
}
function buildProviderModelsUrl(baseUrl, queryParams) {
  const url = new URL(baseUrl);
  url.pathname = url.pathname.endsWith("/") ? `${url.pathname}models` : `${url.pathname}/models`;
  const extraParams = normalizeQueryParams(queryParams);
  for (const [key, value] of extraParams.entries()) {
    url.searchParams.set(key, value);
  }
  return url;
}
function normalizeProviderModelsData(payload) {
  const record = asRecord6(payload);
  const rows = Array.isArray(record?.data) ? record.data : null;
  if (!rows) {
    throw new Error("provider /models payload is missing a data array");
  }
  const ids = [];
  for (const row of rows) {
    const entry = asRecord6(row);
    const candidate = readNonEmptyString(entry?.id);
    if (!candidate || ids.includes(candidate)) continue;
    ids.push(candidate);
  }
  return ids;
}
async function fetchCustomEndpointDefaultModel(baseUrl, apiKey) {
  const normalizedBaseUrl = baseUrl.trim();
  if (!normalizedBaseUrl) return "";
  try {
    const modelsUrl = buildProviderModelsUrl(normalizedBaseUrl, null);
    const headers = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
    const response = await fetch(modelsUrl, { headers, signal: AbortSignal.timeout(PROVIDER_MODELS_FETCH_TIMEOUT_MS) });
    if (!response.ok) return "";
    const payload = await response.json();
    const modelIds = normalizeProviderModelsData(payload);
    return modelIds[0] ?? "";
  } catch {
    return "";
  }
}
async function fetchOpenCodeZenModelIds(apiKey) {
  const headers = {};
  if (apiKey && apiKey !== "dummy") {
    headers.Authorization = `Bearer ${apiKey}`;
  }
  const response = await fetch("https://opencode.ai/zen/v1/models", {
    headers,
    signal: AbortSignal.timeout(PROVIDER_MODELS_FETCH_TIMEOUT_MS)
  });
  if (!response.ok) return [];
  return normalizeProviderModelsData(await response.json());
}
function sortOpenCodeZenModelIds(modelIds) {
  const freeIds = modelIds.filter((id) => id.endsWith("-free") || id === OPENCODE_ZEN_DEFAULT_MODEL);
  const paidIds = modelIds.filter((id) => !id.endsWith("-free") && id !== OPENCODE_ZEN_DEFAULT_MODEL);
  return [...freeIds, ...paidIds];
}
async function readProviderBackedModelIds(appServer) {
  const configPayload = asRecord6(await appServer.rpc("config/read", {}));
  const config = asRecord6(configPayload?.config);
  const providerId = readNonEmptyString(config?.model_provider);
  if (!providerId) {
    return { data: [], providerId: "", source: "provider" };
  }
  const providers = asRecord6(config?.model_providers);
  const provider = asRecord6(providers?.[providerId]);
  if (!provider) {
    logProviderModelDiscoveryWarning("configured provider is missing from model_providers", { providerId });
    return { data: [], providerId, source: "provider" };
  }
  const wireApi = readNonEmptyString(provider.wire_api);
  if (wireApi !== "responses") {
    return { data: [], providerId, source: "provider" };
  }
  const baseUrl = readNonEmptyString(provider.base_url);
  if (!baseUrl) {
    logProviderModelDiscoveryWarning("responses provider is missing base_url", { providerId });
    return { data: [], providerId, source: "provider" };
  }
  const headers = new Headers();
  const configuredHeaders = asRecord6(provider.http_headers);
  if (configuredHeaders) {
    for (const [key, rawValue] of Object.entries(configuredHeaders)) {
      const normalized = normalizeHeaderValue(rawValue);
      if (!normalized) continue;
      headers.set(key, normalized);
    }
  }
  const bearerToken = readNonEmptyString(provider.experimental_bearer_token);
  if (bearerToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${bearerToken}`);
  }
  const envKey = readNonEmptyString(provider.env_key);
  const envHttpHeaders = asRecord6(provider.env_http_headers);
  if (envKey || envHttpHeaders) {
    logProviderModelDiscoveryWarning("provider discovery skipped env-backed auth/header expansion", {
      providerId,
      hasEnvKey: Boolean(envKey),
      hasEnvHttpHeaders: Boolean(envHttpHeaders)
    });
  }
  let requestUrl;
  try {
    requestUrl = buildProviderModelsUrl(baseUrl, provider.query_params);
  } catch (error) {
    logProviderModelDiscoveryWarning("provider /models URL was invalid", {
      providerId,
      error: getErrorMessage6(error, "invalid url")
    });
    return { data: [], providerId, source: "provider" };
  }
  let response;
  try {
    response = await fetch(requestUrl, {
      method: "GET",
      headers,
      signal: AbortSignal.timeout(PROVIDER_MODELS_FETCH_TIMEOUT_MS)
    });
  } catch (error) {
    logProviderModelDiscoveryWarning("provider /models request failed", {
      providerId,
      error: isTimeoutError(error) ? `request timed out after ${PROVIDER_MODELS_FETCH_TIMEOUT_MS}ms` : getErrorMessage6(error, "network error")
    });
    return { data: [], providerId, source: "provider" };
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    logProviderModelDiscoveryWarning("provider /models response was not valid JSON", {
      providerId,
      status: response.status,
      error: getErrorMessage6(error, "invalid json")
    });
    return { data: [], providerId, source: "provider" };
  }
  if (!response.ok) {
    logProviderModelDiscoveryWarning("provider /models request returned non-2xx", {
      providerId,
      status: response.status,
      statusText: response.statusText
    });
    return { data: [], providerId, source: "provider" };
  }
  try {
    return {
      data: normalizeProviderModelsData(payload),
      providerId,
      source: "provider"
    };
  } catch (error) {
    logProviderModelDiscoveryWarning("provider /models payload was invalid", {
      providerId,
      error: getErrorMessage6(error, "invalid payload")
    });
    return { data: [], providerId, source: "provider" };
  }
}
async function readProviderModelIdsForProvider(appServer, providerId) {
  const normalizedProviderId = providerId.trim().toLowerCase().replace(/_/g, "-");
  if (!normalizedProviderId || normalizedProviderId === "codex" || normalizedProviderId === "openai") {
    return { data: [], providerId: "", source: "provider" };
  }
  const fmState = ensureDefaultFreeModeStateForMissingAuthSync(join6(getCodexHomeDir3(), FREE_MODE_STATE_FILE));
  if (normalizedProviderId === "opencode-zen") {
    try {
      const modelIds = filterOpenCodeZenModelsForAuthState(
        sortOpenCodeZenModelIds(await fetchOpenCodeZenModelIds(fmState?.provider === "opencode-zen" ? fmState.apiKey : null)),
        fmState?.provider === "opencode-zen" ? fmState.apiKey : null
      );
      if (modelIds.length > 0) {
        return { data: modelIds, providerId: "opencode-zen", source: "provider" };
      }
    } catch {
    }
    return {
      data: ["big-pickle", "minimax-m2.5-free", "nemotron-3-super-free", "trinity-large-preview-free"],
      providerId: "opencode-zen",
      source: "provider"
    };
  }
  if (normalizedProviderId === "openrouter-free" || normalizedProviderId === "openrouter") {
    return {
      data: await getFreeModels(),
      providerId: "openrouter-free",
      source: "provider"
    };
  }
  return readProviderBackedModelIds(appServer);
}
function extractThreadMessageText(threadReadPayload) {
  const payload = asRecord6(threadReadPayload);
  const thread = asRecord6(payload?.thread);
  const turns = Array.isArray(thread?.turns) ? thread.turns : [];
  const parts = [];
  for (const turn of turns) {
    const turnRecord = asRecord6(turn);
    const items = Array.isArray(turnRecord?.items) ? turnRecord.items : [];
    for (const item of items) {
      const itemRecord = asRecord6(item);
      const type = typeof itemRecord?.type === "string" ? itemRecord.type : "";
      if (type === "agentMessage" && typeof itemRecord?.text === "string" && itemRecord.text.trim().length > 0) {
        parts.push(itemRecord.text.trim());
        continue;
      }
      if (type === "userMessage") {
        const content = Array.isArray(itemRecord?.content) ? itemRecord.content : [];
        for (const block of content) {
          const blockRecord = asRecord6(block);
          if (blockRecord?.type === "text" && typeof blockRecord.text === "string" && blockRecord.text.trim().length > 0) {
            parts.push(blockRecord.text.trim());
          }
        }
        continue;
      }
      if (type === "commandExecution") {
        const command = typeof itemRecord?.command === "string" ? itemRecord.command.trim() : "";
        const output = typeof itemRecord?.aggregatedOutput === "string" ? itemRecord.aggregatedOutput.trim() : "";
        if (command) parts.push(command);
        if (output) parts.push(output);
      }
    }
  }
  return parts.join("\n").trim();
}
function readNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0 ? value : "";
}
function readThreadArchiveFallbackName(threadReadResult) {
  const record = asRecord6(threadReadResult);
  const thread = asRecord6(record?.thread);
  return readNonEmptyString(thread?.name) || readNonEmptyString(thread?.title) || readNonEmptyString(thread?.preview) || "Untitled thread";
}
function isArchivedThreadReadResult(threadReadResult) {
  const record = asRecord6(threadReadResult);
  const thread = asRecord6(record?.thread);
  const sessionPath = readNonEmptyString(thread?.path);
  return sessionPath.split(/[\\/]+/u).includes("archived_sessions");
}
async function callRpcWithArchiveRecovery(appServer, method, params) {
  try {
    return await callRpcWithRateLimitDecodeRecovery(appServer, method, params);
  } catch (error) {
    const paramsRecord = asRecord6(params);
    const threadId = readNonEmptyString(paramsRecord?.threadId);
    if (method === "turn/start" && threadId && isThreadNotFoundError(error)) {
      await appServer.rpc("thread/resume", { threadId });
      return appServer.rpc(method, params ?? null);
    }
    if (method !== "thread/archive") {
      throw error;
    }
    const errorMessage = getErrorMessage6(error, "");
    if (!threadId || !errorMessage.includes("no rollout found")) {
      throw error;
    }
    let threadReadResult = null;
    try {
      threadReadResult = await appServer.rpc("thread/read", {
        threadId,
        includeTurns: false
      });
      if (isArchivedThreadReadResult(threadReadResult)) {
        return null;
      }
    } catch {
    }
    await appServer.rpc("thread/name/set", {
      threadId,
      name: readThreadArchiveFallbackName(threadReadResult)
    });
    return appServer.rpc(method, params ?? null);
  }
}
async function listTerminalQuickCommands(cwd) {
  const normalizedCwd = isAbsolute2(cwd) ? cwd : resolve2(cwd);
  const info = await stat4(normalizedCwd);
  if (!info.isDirectory()) {
    throw new Error("Terminal cwd is not a directory");
  }
  const commands = [];
  const seen = /* @__PURE__ */ new Set();
  const addCommand = (command) => {
    if (!command.value || seen.has(command.value)) return;
    seen.add(command.value);
    commands.push(command);
  };
  await addPackageJsonCommands(normalizedCwd, addCommand);
  await addMakefileCommands(normalizedCwd, addCommand);
  await addRootScriptCommands(normalizedCwd, addCommand);
  await addScriptsDirectoryCommands(normalizedCwd, addCommand);
  return commands;
}
async function addPackageJsonCommands(cwd, addCommand) {
  try {
    const raw = await readFile3(join6(cwd, "package.json"), "utf8");
    const parsed = JSON.parse(raw);
    const record = asRecord6(parsed);
    const scripts = asRecord6(record?.scripts);
    if (!scripts) return;
    const packageManager = resolvePackageManager(cwd);
    for (const scriptName of Object.keys(scripts)) {
      if (typeof scripts[scriptName] !== "string") continue;
      const value = formatPackageScriptCommand(packageManager, scriptName);
      addCommand({
        label: value,
        value,
        source: "package"
      });
    }
  } catch {
  }
}
async function addMakefileCommands(cwd, addCommand) {
  const makefilePath = existsSync4(join6(cwd, "Makefile")) ? join6(cwd, "Makefile") : existsSync4(join6(cwd, "makefile")) ? join6(cwd, "makefile") : "";
  if (!makefilePath) return;
  try {
    const raw = await readFile3(makefilePath, "utf8");
    for (const line of raw.split(/\r?\n/)) {
      const match = /^([A-Za-z0-9_.@%/+~-][A-Za-z0-9_.@%/+~-]*)\s*:(?![=])/.exec(line);
      if (!match) continue;
      const target = match[1];
      if (!target || target.startsWith(".")) continue;
      const value = `make ${quoteShellTokenIfNeeded(target)}`;
      addCommand({
        label: value,
        value,
        source: "make"
      });
    }
  } catch {
  }
}
async function addRootScriptCommands(cwd, addCommand) {
  await addScriptFileCommands(cwd, ".", addCommand);
}
async function addScriptsDirectoryCommands(cwd, addCommand) {
  await addScriptFileCommands(join6(cwd, "scripts"), "./scripts", addCommand);
}
async function addScriptFileCommands(directory, commandPrefix, addCommand) {
  try {
    const entries = await readdir2(directory, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isFile()) continue;
      if (!entry.name.endsWith(".sh") && !entry.name.endsWith(".cmd")) continue;
      const value = `${commandPrefix}/${quoteShellTokenIfNeeded(entry.name)}`;
      addCommand({
        label: value,
        value,
        source: "script"
      });
    }
  } catch {
  }
}
function resolvePackageManager(cwd) {
  if (existsSync4(join6(cwd, "pnpm-lock.yaml"))) return "pnpm";
  if (existsSync4(join6(cwd, "yarn.lock"))) return "yarn";
  if (existsSync4(join6(cwd, "bun.lock")) || existsSync4(join6(cwd, "bun.lockb"))) return "bun";
  return "npm";
}
function formatPackageScriptCommand(packageManager, scriptName) {
  const quoted = quoteShellTokenIfNeeded(scriptName);
  if (packageManager === "npm") return `npm run ${quoted}`;
  if (packageManager === "pnpm") return `pnpm run ${quoted}`;
  if (packageManager === "bun") return `bun run ${quoted}`;
  return `yarn ${quoted}`;
}
function quoteShellTokenIfNeeded(value) {
  return /^[A-Za-z0-9_./:@-]+$/.test(value) ? value : `'${value.replace(/'/g, `'\\''`)}'`;
}
function readBoolean3(value) {
  return value === true;
}
function readNumber3(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
function buildComposioInvocation(args) {
  const overrideCommand = process.env.CODEXUI_COMPOSIO_COMMAND?.trim();
  if (overrideCommand) {
    const invocation = getSpawnInvocation(overrideCommand, args);
    return {
      command: invocation.command,
      args: invocation.args,
      displayCommand: `${overrideCommand} ${args.map(quoteShellTokenIfNeeded).join(" ")}`.trim()
    };
  }
  return buildInstalledComposioInvocation(args);
}
function buildInstalledComposioInvocation(args) {
  const candidates = [
    join6(homedir5(), ".composio", "composio"),
    "composio"
  ];
  for (const candidate of candidates) {
    if ((candidate.includes("/") || candidate.includes("\\")) && !existsSync4(candidate)) continue;
    const invocation = getSpawnInvocation(candidate, args);
    return {
      command: invocation.command,
      args: invocation.args,
      displayCommand: `${candidate} ${args.map(quoteShellTokenIfNeeded).join(" ")}`.trim()
    };
  }
  return null;
}
function probeComposioInvocation(invocation) {
  const probe = spawnSync4(invocation.command, invocation.args, {
    encoding: "utf8",
    env: process.env,
    windowsHide: true
  });
  const output = `${probe.stdout ?? ""}${probe.stderr ?? ""}`.trim();
  return {
    available: !probe.error && probe.status === 0,
    cliVersion: probe.status === 0 ? (probe.stdout ?? "").trim() : "",
    output
  };
}
function resolveComposioInvocation(args) {
  const invocation = buildComposioInvocation(args);
  const versionInvocation = buildComposioInvocation(["--version"]);
  if (invocation && versionInvocation && probeComposioInvocation(versionInvocation).available) return invocation;
  return null;
}
function parseComposioJson(stdout, fallback) {
  const trimmed = stdout.trim();
  if (!trimmed) {
    throw new Error(fallback);
  }
  return JSON.parse(trimmed);
}
async function runComposioJson(args, fallback) {
  const invocation = resolveComposioInvocation(args);
  if (!invocation) {
    throw new Error("Composio CLI is not installed");
  }
  const child = spawn4(invocation.command, invocation.args, {
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  const exitCode = await new Promise((resolveExit, reject) => {
    child.once("error", reject);
    child.once("close", (code) => resolveExit(code ?? 0));
  });
  if (exitCode !== 0) {
    throw new Error(stderr.trim() || stdout.trim() || fallback);
  }
  try {
    return parseComposioJson(stdout, fallback);
  } catch (error) {
    const details = stderr.trim() || stdout.trim();
    throw new Error(details || getErrorMessage6(error, fallback));
  }
}
async function readComposioUserData() {
  try {
    const raw = await readFile3(COMPOSIO_USER_DATA_PATH, "utf8");
    const payload = asRecord6(JSON.parse(raw));
    if (!payload) return null;
    return {
      apiKey: readNonEmptyString(payload.api_key),
      baseUrl: readNonEmptyString(payload.base_url),
      webUrl: readNonEmptyString(payload.web_url),
      orgId: readNonEmptyString(payload.org_id),
      testUserId: readNonEmptyString(payload.test_user_id)
    };
  } catch {
    return null;
  }
}
function normalizeComposioConnection(value) {
  const record = asRecord6(value);
  if (!record) return null;
  const authConfig = asRecord6(record.auth_config);
  return {
    id: readNonEmptyString(record.id),
    wordId: readNonEmptyString(record.word_id),
    alias: readNonEmptyString(record.alias),
    status: readNonEmptyString(record.status),
    authScheme: readNonEmptyString(record.authScheme || authConfig?.auth_scheme),
    createdAt: readNonEmptyString(record.created_at),
    updatedAt: readNonEmptyString(record.updated_at),
    isComposioManaged: readBoolean3(authConfig?.is_composio_managed),
    isDisabled: readBoolean3(record.is_disabled)
  };
}
function normalizeComposioToolkit(value, connectionsBySlug) {
  const record = asRecord6(value);
  if (!record) return null;
  const slug = readNonEmptyString(record.slug);
  if (!slug) return null;
  const connectionRows = connectionsBySlug.get(slug) ?? [];
  return {
    slug,
    name: readNonEmptyString(record.name),
    description: readNonEmptyString(record.description),
    logoUrl: readNonEmptyString(record.logo || record.meta && asRecord6(record.meta)?.logo),
    latestVersion: readNonEmptyString(record.latest_version || record.latestVersion),
    toolsCount: readNumber3(record.tools_count),
    triggersCount: readNumber3(record.triggers_count),
    isNoAuth: readBoolean3(record.is_no_auth),
    enabled: record.enabled !== false,
    authModes: Array.isArray(record.auth_modes) ? record.auth_modes.map(readNonEmptyString).filter(Boolean) : [],
    activeCount: connectionRows.filter((row) => row.status === "ACTIVE" && !row.isDisabled).length,
    totalConnections: connectionRows.length,
    connectionStatuses: [...new Set(connectionRows.map((row) => row.status).filter(Boolean))]
  };
}
function normalizeComposioTool(value) {
  const record = asRecord6(value);
  if (!record) return null;
  const slug = readNonEmptyString(record.slug);
  if (!slug) return null;
  return {
    slug,
    name: readNonEmptyString(record.name),
    description: readNonEmptyString(record.description)
  };
}
async function readComposioConnectionsBySlug() {
  const payload = asRecord6(await runComposioJson(["connections", "list"], "Failed to list Composio connections"));
  const bySlug = /* @__PURE__ */ new Map();
  for (const [slug, rawRows] of Object.entries(payload ?? {})) {
    if (!Array.isArray(rawRows)) continue;
    const rows = rawRows.map(normalizeComposioConnection).filter((row) => row !== null);
    bySlug.set(slug, rows);
  }
  return bySlug;
}
async function readComposioStatus() {
  const versionInvocation = buildComposioInvocation(["--version"]);
  const probe = versionInvocation ? probeComposioInvocation(versionInvocation) : { available: false, cliVersion: "", output: "" };
  const available = probe.available;
  const cliVersion = probe.cliVersion;
  const userData = await readComposioUserData();
  if (!available) {
    return {
      available: false,
      authenticated: false,
      cliVersion,
      email: "",
      defaultOrgName: "",
      defaultOrgId: userData?.orgId ?? "",
      webUrl: userData?.webUrl ?? "",
      baseUrl: userData?.baseUrl ?? "",
      testUserId: userData?.testUserId ?? ""
    };
  }
  try {
    const payload = asRecord6(await runComposioJson(["whoami"], "Failed to read Composio account status"));
    return {
      available: true,
      authenticated: true,
      cliVersion,
      email: readNonEmptyString(payload?.email),
      defaultOrgName: readNonEmptyString(payload?.default_org_name),
      defaultOrgId: readNonEmptyString(payload?.default_org_id) || userData?.orgId || "",
      webUrl: userData?.webUrl || "https://dashboard.composio.dev/",
      baseUrl: userData?.baseUrl || "https://backend.composio.dev",
      testUserId: readNonEmptyString(payload?.test_user_id) || userData?.testUserId || ""
    };
  } catch {
    return {
      available: true,
      authenticated: false,
      cliVersion,
      email: "",
      defaultOrgName: "",
      defaultOrgId: userData?.orgId ?? "",
      webUrl: userData?.webUrl || "https://dashboard.composio.dev/",
      baseUrl: userData?.baseUrl || "https://backend.composio.dev",
      testUserId: userData?.testUserId ?? ""
    };
  }
}
async function listComposioConnectors(query, cursor = null, limit = 50) {
  const args = ["dev", "toolkits", "list", "--limit", String(COMPOSIO_CONNECTORS_PAGE_LIMIT_MAX)];
  const trimmedQuery = query.trim();
  if (trimmedQuery) {
    args.push("--query", trimmedQuery);
  }
  const [payload, connectionsBySlug] = await Promise.all([
    runComposioJson(args, "Failed to list Composio toolkits"),
    readComposioConnectionsBySlug()
  ]);
  const allRows = payload.map((item) => normalizeComposioToolkit(item, connectionsBySlug)).filter((row) => row !== null);
  const safeLimit = Number.isFinite(limit) ? Math.max(1, Math.min(COMPOSIO_CONNECTORS_PAGE_LIMIT_MAX, Math.floor(limit))) : 50;
  const safeCursor = parseComposioCursor(cursor, allRows.length);
  return {
    data: allRows.slice(safeCursor, safeCursor + safeLimit),
    nextCursor: safeCursor + safeLimit < allRows.length ? String(safeCursor + safeLimit) : null,
    total: allRows.length
  };
}
function parseComposioCursor(cursor, maxLength) {
  const trimmed = cursor?.trim() ?? "";
  const parsed = Number.parseInt(trimmed, 10);
  if (!Number.isFinite(parsed) || Number.isNaN(parsed) || parsed <= 0) return 0;
  if (parsed >= maxLength) return maxLength;
  return parsed;
}
function parseComposioLimit(rawLimit) {
  const parsed = Number.parseInt((rawLimit ?? "").trim(), 10);
  if (!Number.isFinite(parsed) || Number.isNaN(parsed) || parsed <= 0) return 50;
  return Math.max(1, Math.min(COMPOSIO_CONNECTORS_PAGE_LIMIT_MAX, parsed));
}
async function readComposioConnectorDetail(slug) {
  const normalizedSlug = slug.trim();
  if (!normalizedSlug) {
    throw new Error("Missing Composio connector slug");
  }
  const [infoPayload, toolsPayload, connectionsPayload, userData] = await Promise.all([
    runComposioJson(["dev", "toolkits", "info", normalizedSlug], `Failed to load Composio toolkit ${normalizedSlug}`),
    runComposioJson(["tools", "list", normalizedSlug, "--limit", "10"], `Failed to list tools for ${normalizedSlug}`),
    runComposioJson(["link", normalizedSlug, "--list"], `Failed to list connections for ${normalizedSlug}`),
    readComposioUserData()
  ]);
  const connections = Array.isArray(connectionsPayload.items) ? connectionsPayload.items.map(normalizeComposioConnection).filter((row) => row !== null) : [];
  const connector = normalizeComposioToolkit(infoPayload, /* @__PURE__ */ new Map([[normalizedSlug, connections]]));
  if (!connector) {
    throw new Error(`Unknown Composio connector: ${normalizedSlug}`);
  }
  return {
    connector,
    connections,
    tools: Array.isArray(toolsPayload) ? toolsPayload.map(normalizeComposioTool).filter((row) => row !== null) : [],
    dashboardUrl: userData?.webUrl || "https://dashboard.composio.dev/"
  };
}
async function startComposioLink(slug) {
  const normalizedSlug = slug.trim();
  if (!normalizedSlug) {
    throw new Error("Missing Composio connector slug");
  }
  const payload = asRecord6(await runComposioJson(["link", normalizedSlug, "--no-wait"], `Failed to start Composio link for ${normalizedSlug}`));
  return {
    status: readNonEmptyString(payload?.status),
    message: readNonEmptyString(payload?.message),
    connectedAccountId: readNonEmptyString(payload?.connected_account_id),
    redirectUrl: readNonEmptyString(payload?.redirect_url),
    toolkit: readNonEmptyString(payload?.toolkit),
    projectType: readNonEmptyString(payload?.project_type)
  };
}
async function startComposioLogin() {
  const invocation = resolveComposioInvocation(["login", "--no-browser", "-y"]);
  if (!invocation) {
    throw new Error("Composio CLI is not installed");
  }
  const proc = spawn4(invocation.command, invocation.args, {
    cwd: process.cwd(),
    env: process.env,
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true
  });
  proc.unref();
  let stdout = "";
  let stderr = "";
  proc.stdout.setEncoding("utf8");
  proc.stderr.setEncoding("utf8");
  proc.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  const loginUrl = await new Promise((resolveLoginUrl, reject) => {
    const timeout = setTimeout(() => {
      proc.kill("SIGTERM");
      reject(new Error(stderr.trim() || stdout.trim() || "Timed out waiting for Composio CLI login URL"));
    }, 1e4);
    const finish = (url) => {
      clearTimeout(timeout);
      proc.stdout.destroy();
      proc.stderr.destroy();
      resolveLoginUrl(url);
    };
    proc.once("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    proc.once("close", (code) => {
      clearTimeout(timeout);
      reject(new Error(stderr.trim() || stdout.trim() || `Composio CLI login exited with code ${code ?? 0}`));
    });
    proc.stdout.on("data", (chunk) => {
      stdout += chunk;
      const url = stdout.match(/https?:\/\/\S+/)?.[0] ?? "";
      if (url) finish(url);
    });
  });
  const cliKey = loginUrl ? new URL(loginUrl).searchParams.get("cliKey") ?? "" : "";
  return {
    status: "started",
    message: "Composio CLI login URL created",
    loginUrl,
    cliKey,
    expiresAt: ""
  };
}
async function installComposioCli() {
  const command = "bash";
  const installScriptUrl = "https://composio.dev/install";
  const args = ["-lc", `curl -fsSL ${installScriptUrl} | bash`];
  const invocation = getSpawnInvocation(command, args);
  const env = {
    ...process.env,
    COMPOSIO_INSTALL_DIR: process.env.COMPOSIO_INSTALL_DIR?.trim() || join6(homedir5(), ".composio")
  };
  const result = spawnSync4(invocation.command, invocation.args, {
    encoding: "utf8",
    env,
    windowsHide: true
  });
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
  if (result.error || result.status !== 0) {
    throw new Error(output || result.error?.message || "Failed to install Composio CLI");
  }
  return {
    ok: true,
    command: `curl -fsSL ${installScriptUrl} | bash`,
    output
  };
}
function countRecoveredContentLines(value) {
  if (!value) return 0;
  const normalized = value.replace(/\r\n/g, "\n");
  const trimmed = normalized.endsWith("\n") ? normalized.slice(0, -1) : normalized;
  if (!trimmed) return 0;
  return trimmed.split("\n").length;
}
function countRecoveredPatchLines(value) {
  let addedLineCount = 0;
  let removedLineCount = 0;
  for (const line of value.replace(/\r\n/g, "\n").split("\n")) {
    if (!line) continue;
    if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) continue;
    if (line.startsWith("+")) {
      addedLineCount += 1;
      continue;
    }
    if (line.startsWith("-")) {
      removedLineCount += 1;
    }
  }
  return { addedLineCount, removedLineCount };
}
function mergeRecoveredDiff(first, second) {
  if (!first) return second;
  if (!second || first === second) return first;
  return `${first}
${second}`.trim();
}
function mergeRecoveredFileChange(first, second) {
  const operation = first.operation === "add" || second.operation === "add" ? "add" : first.operation === "delete" || second.operation === "delete" ? "delete" : "update";
  return {
    path: second.path || first.path,
    operation,
    movedToPath: second.movedToPath ?? first.movedToPath ?? null,
    diff: mergeRecoveredDiff(first.diff, second.diff),
    addedLineCount: first.addedLineCount + second.addedLineCount,
    removedLineCount: first.removedLineCount + second.removedLineCount
  };
}
function isApplyPatchSectionBoundary(value) {
  return value.startsWith("*** Update File: ") || value.startsWith("*** Add File: ") || value.startsWith("*** Delete File: ") || value === "*** End Patch";
}
function parseApplyPatchInput(input) {
  const normalized = input.replace(/\r\n/g, "\n");
  const lines = normalized.split("\n");
  const changes = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    if (line.startsWith("*** Add File: ")) {
      const path = line.slice("*** Add File: ".length).trim();
      const contentLines = [];
      for (index += 1; index < lines.length; index += 1) {
        const nextLine = lines[index] ?? "";
        if (isApplyPatchSectionBoundary(nextLine)) {
          index -= 1;
          break;
        }
        contentLines.push(nextLine.startsWith("+") ? nextLine.slice(1) : nextLine);
      }
      const diff = contentLines.join("\n").trimEnd();
      if (path) {
        changes.push({
          path,
          operation: "add",
          movedToPath: null,
          diff,
          addedLineCount: countRecoveredContentLines(diff),
          removedLineCount: 0
        });
      }
      continue;
    }
    if (line.startsWith("*** Delete File: ")) {
      const path = line.slice("*** Delete File: ".length).trim();
      if (path) {
        changes.push({
          path,
          operation: "delete",
          movedToPath: null,
          diff: "",
          addedLineCount: 0,
          removedLineCount: 0
        });
      }
      continue;
    }
    if (line.startsWith("*** Update File: ")) {
      const path = line.slice("*** Update File: ".length).trim();
      let movedToPath = null;
      const diffLines = [];
      for (index += 1; index < lines.length; index += 1) {
        const nextLine = lines[index] ?? "";
        if (nextLine.startsWith("*** Move to: ")) {
          const moved = nextLine.slice("*** Move to: ".length).trim();
          movedToPath = moved || null;
          continue;
        }
        if (isApplyPatchSectionBoundary(nextLine)) {
          index -= 1;
          break;
        }
        diffLines.push(nextLine);
      }
      const diff = diffLines.join("\n").trimEnd();
      const counts = countRecoveredPatchLines(diff);
      if (path) {
        changes.push({
          path,
          operation: "update",
          movedToPath,
          diff,
          ...counts
        });
      }
    }
  }
  return changes;
}
function buildSessionFileChangeFallback(threadReadPayload, sessionLogRaw) {
  const payload = asRecord6(threadReadPayload);
  const thread = asRecord6(payload?.thread);
  const turns = Array.isArray(thread?.turns) ? thread.turns : [];
  const turnIndexById = /* @__PURE__ */ new Map();
  for (let turnIndex = 0; turnIndex < turns.length; turnIndex += 1) {
    const turnRecord = asRecord6(turns[turnIndex]);
    const turnId = readNonEmptyString(turnRecord?.id);
    if (turnId) {
      turnIndexById.set(turnId, turnIndex);
    }
  }
  const collectedByTurnId = /* @__PURE__ */ new Map();
  let currentTurnId = "";
  for (const line of sessionLogRaw.split("\n")) {
    if (!line.trim()) continue;
    let row = null;
    try {
      row = JSON.parse(line);
    } catch {
      continue;
    }
    if (row.type === "turn_context") {
      const payloadRecord2 = asRecord6(row.payload);
      currentTurnId = readNonEmptyString(payloadRecord2?.turn_id) || currentTurnId;
      continue;
    }
    if (row.type !== "response_item" || !currentTurnId || !turnIndexById.has(currentTurnId)) {
      continue;
    }
    const payloadRecord = asRecord6(row.payload);
    if (payloadRecord?.type !== "custom_tool_call" || payloadRecord.name !== "apply_patch" || payloadRecord.status !== "completed") {
      continue;
    }
    const input = readNonEmptyString(payloadRecord.input);
    if (!input) continue;
    const parsedChanges = parseApplyPatchInput(input);
    if (parsedChanges.length === 0) continue;
    const previous = collectedByTurnId.get(currentTurnId) ?? [];
    previous.push(...parsedChanges);
    collectedByTurnId.set(currentTurnId, previous);
  }
  const recovered = [];
  for (const [turnId, fileChanges] of collectedByTurnId.entries()) {
    const turnIndex = turnIndexById.get(turnId);
    if (typeof turnIndex !== "number" || fileChanges.length === 0) continue;
    const mergedByPath = /* @__PURE__ */ new Map();
    for (const fileChange of fileChanges) {
      const key = `${fileChange.path}\0${fileChange.movedToPath ?? ""}`;
      const previous = mergedByPath.get(key);
      mergedByPath.set(key, previous ? mergeRecoveredFileChange(previous, fileChange) : { ...fileChange });
    }
    recovered.push({
      turnId,
      turnIndex,
      fileChanges: Array.from(mergedByPath.values())
    });
  }
  return recovered.sort((first, second) => first.turnIndex - second.turnIndex);
}
function parseExecCommandOutput(output) {
  let exitCode = null;
  let wallTime = null;
  const outputLines = [];
  let pastHeader = false;
  for (const line of output.split("\n")) {
    if (!pastHeader) {
      const exitMatch = line.match(/^Process exited with code (\d+)/);
      if (exitMatch) {
        exitCode = Number.parseInt(exitMatch[1], 10);
        continue;
      }
      const wallMatch = line.match(/^Wall time:\s+([\d.]+)\s+seconds/);
      if (wallMatch) {
        wallTime = Math.round(Number.parseFloat(wallMatch[1]) * 1e3);
        continue;
      }
      if (line.startsWith("Command:") || line.startsWith("Chunk ID:") || line.startsWith("Original token count:")) {
        continue;
      }
      if (line === "Output:") {
        pastHeader = true;
        continue;
      }
    }
    outputLines.push(line);
  }
  return { exitCode, wallTime, cleanOutput: outputLines.join("\n").trimEnd() };
}
function buildSessionItemOrder(sessionLogRaw, turnIds) {
  let currentTurnId = "";
  const orderByTurnId = /* @__PURE__ */ new Map();
  const callIdToCommand = /* @__PURE__ */ new Map();
  for (const line of sessionLogRaw.split("\n")) {
    if (!line.trim()) continue;
    let row = null;
    try {
      row = JSON.parse(line);
    } catch {
      continue;
    }
    if (row.type === "turn_context") {
      const p = asRecord6(row.payload);
      currentTurnId = readNonEmptyString(p?.turn_id) || currentTurnId;
      continue;
    }
    if (row.type === "event_msg") {
      const p = asRecord6(row.payload);
      if (p?.type === "task_started") {
        currentTurnId = readNonEmptyString(p.turn_id) || currentTurnId;
      }
      continue;
    }
    if (row.type !== "response_item" || !currentTurnId || !turnIds.has(currentTurnId)) continue;
    const payload = asRecord6(row.payload);
    if (!payload) continue;
    let slots = orderByTurnId.get(currentTurnId);
    if (!slots) {
      slots = [];
      orderByTurnId.set(currentTurnId, slots);
    }
    if (payload.type === "message" && payload.role === "assistant") {
      slots.push({ type: "agentMessage" });
      continue;
    }
    if (payload.type === "function_call" && payload.name === "exec_command") {
      const callId = readNonEmptyString(payload.call_id);
      if (!callId) continue;
      let cmd = "";
      try {
        const args = JSON.parse(payload.arguments);
        cmd = typeof args.cmd === "string" ? args.cmd : "";
      } catch {
      }
      const command = {
        id: `session-cmd-${callId}`,
        type: "commandExecution",
        command: cmd,
        cwd: null,
        status: "completed",
        aggregatedOutput: "",
        exitCode: null,
        durationMs: null
      };
      callIdToCommand.set(callId, command);
      slots.push({ type: "commandExecution", command });
      continue;
    }
    if (payload.type === "function_call_output") {
      const callId = readNonEmptyString(payload.call_id);
      if (!callId) continue;
      const existing = callIdToCommand.get(callId);
      if (!existing) continue;
      const rawOutput = typeof payload.output === "string" ? payload.output : "";
      const parsed = parseExecCommandOutput(rawOutput);
      existing.aggregatedOutput = parsed.cleanOutput;
      existing.exitCode = parsed.exitCode;
      existing.durationMs = parsed.wallTime;
      existing.status = parsed.exitCode === 0 || parsed.exitCode === null ? "completed" : "failed";
    }
    if (payload.type === "custom_tool_call" && payload.name === "apply_patch" && payload.status === "completed") {
      const input = typeof payload.input === "string" ? payload.input : "";
      const callId = readNonEmptyString(payload.call_id);
      if (!input || !callId) continue;
      const parsedChanges = parseApplyPatchInput(input);
      if (parsedChanges.length === 0) continue;
      const fcItem = {
        id: `session-fc-${callId}`,
        type: "fileChange",
        status: "completed",
        changes: parsedChanges.map((fc) => ({
          ...fc,
          kind: { type: fc.operation, ...fc.movedToPath ? { move_path: fc.movedToPath } : {} }
        }))
      };
      slots.push({ type: "fileChange", fileChange: fcItem });
    }
  }
  return orderByTurnId;
}
function extractFilePathsFromCommand(cmd, cwd) {
  const paths = [];
  const absPathPattern = /(?:^|\s|>>|>|<)(\/?(?:Users|home|tmp|var|etc|root)\/[^\s;|&><"']+)/g;
  let match;
  while ((match = absPathPattern.exec(cmd)) !== null) {
    const p = match[1]?.trim();
    if (p && !p.endsWith("/") && !p.startsWith("-")) paths.push(p);
  }
  const redirectPattern = /(?:>>?|cat\s*>\s*)([^\s;|&><"']+)/g;
  while ((match = redirectPattern.exec(cmd)) !== null) {
    const p = match[1]?.trim();
    if (p && !p.startsWith("-") && !p.startsWith("/dev/")) {
      paths.push(isAbsolute2(p) ? p : join6(cwd, p));
    }
  }
  return [...new Set(paths)];
}
function collectFileChangesForTurns(sessionLogRaw, turnIdsToRevert, cwd) {
  let currentTurnId = "";
  const infoByTurnId = /* @__PURE__ */ new Map();
  for (const line of sessionLogRaw.split("\n")) {
    if (!line.trim()) continue;
    let row = null;
    try {
      row = JSON.parse(line);
    } catch {
      continue;
    }
    if (row.type === "turn_context") {
      const p = asRecord6(row.payload);
      currentTurnId = readNonEmptyString(p?.turn_id) || currentTurnId;
      continue;
    }
    if (row.type === "event_msg") {
      const p = asRecord6(row.payload);
      if (p?.type === "task_started") {
        currentTurnId = readNonEmptyString(p.turn_id) || currentTurnId;
      }
      continue;
    }
    if (row.type !== "response_item" || !currentTurnId || !turnIdsToRevert.has(currentTurnId)) continue;
    const payload = asRecord6(row.payload);
    if (!payload) continue;
    let info = infoByTurnId.get(currentTurnId);
    if (!info) {
      info = { patchInputs: [], commandFilePaths: [] };
      infoByTurnId.set(currentTurnId, info);
    }
    if (payload.type === "custom_tool_call" && payload.name === "apply_patch" && payload.status === "completed") {
      const input = typeof payload.input === "string" ? payload.input : "";
      const callId = readNonEmptyString(payload.call_id);
      if (input && callId) {
        info.patchInputs.push({ callId, input });
      }
    }
    if (payload.type === "function_call" && payload.name === "exec_command") {
      let cmd = "";
      try {
        const args = JSON.parse(payload.arguments);
        cmd = typeof args.cmd === "string" ? args.cmd : "";
      } catch {
      }
      if (cmd) {
        const extracted = extractFilePathsFromCommand(cmd, cwd);
        for (const p of extracted) {
          if (!info.commandFilePaths.includes(p)) info.commandFilePaths.push(p);
        }
      }
    }
  }
  return infoByTurnId;
}
function reverseV4aDiff(fileContent, diffText) {
  const fileLines = fileContent.split("\n");
  const rawDiffLines = diffText.split("\n");
  while (rawDiffLines.length > 0 && rawDiffLines[rawDiffLines.length - 1]?.trim() === "") rawDiffLines.pop();
  const diffLines = rawDiffLines;
  const result = [...fileLines];
  const hunks = [];
  let currentHunk = null;
  for (const dl of diffLines) {
    if (dl.startsWith("@@")) {
      if (currentHunk) hunks.push(currentHunk);
      currentHunk = [];
      continue;
    }
    if (!currentHunk) continue;
    if (dl.startsWith("+")) {
      currentHunk.push({ type: "add", text: dl.slice(1) });
    } else if (dl.startsWith("-")) {
      currentHunk.push({ type: "remove", text: dl.slice(1) });
    } else if (dl.startsWith(" ")) {
      currentHunk.push({ type: "context", text: dl.slice(1) });
    } else {
      currentHunk.push({ type: "context", text: dl });
    }
  }
  if (currentHunk) hunks.push(currentHunk);
  for (let hi = hunks.length - 1; hi >= 0; hi--) {
    const hunk = hunks[hi];
    const expectedSequence = hunk.filter((e) => e.type === "context" || e.type === "add").map((e) => e.text);
    if (expectedSequence.length === 0) continue;
    let seqStart = -1;
    outer: for (let ri = result.length - expectedSequence.length; ri >= 0; ri--) {
      for (let si = 0; si < expectedSequence.length; si++) {
        if (result[ri + si] !== expectedSequence[si]) continue outer;
      }
      seqStart = ri;
      break;
    }
    if (seqStart < 0) return null;
    const newLines = [];
    let seqIdx = 0;
    for (const entry of hunk) {
      if (entry.type === "context") {
        newLines.push(result[seqStart + seqIdx]);
        seqIdx++;
      } else if (entry.type === "add") {
        seqIdx++;
      } else if (entry.type === "remove") {
        newLines.push(entry.text);
      }
    }
    result.splice(seqStart, expectedSequence.length, ...newLines);
  }
  return result.join("\n");
}
async function revertTurnFileChanges(cwd, turnInfos) {
  if (turnInfos.size === 0) return { reverted: 0, errors: [] };
  let reverted = 0;
  const errors = [];
  const allEntries = [...turnInfos.values()];
  const allPatchInputs = allEntries.flatMap((info) => info.patchInputs).reverse();
  const allCommandPaths = new Set(allEntries.flatMap((info) => info.commandFilePaths));
  let isGitRepo = false;
  let gitRoot = "";
  try {
    gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd });
    isGitRepo = !!gitRoot;
  } catch {
  }
  const trackedFiles = /* @__PURE__ */ new Set();
  if (isGitRepo) {
    try {
      const tracked = await runCommandCapture2("git", ["ls-files", "--full-name"], { cwd: gitRoot });
      for (const f of tracked.split("\n")) {
        if (f.trim()) trackedFiles.add(join6(gitRoot, f.trim()));
      }
    } catch {
    }
  }
  const patchRevertedPaths = /* @__PURE__ */ new Set();
  for (const patch of allPatchInputs) {
    const changes = parseApplyPatchInput(patch.input);
    for (let ci = changes.length - 1; ci >= 0; ci--) {
      const change = changes[ci];
      const filePath = isAbsolute2(change.path) ? change.path : join6(cwd, change.path);
      try {
        if (change.operation === "add") {
          const fileStat = await stat4(filePath).catch(() => null);
          if (fileStat) {
            await rm4(filePath, { force: true });
            reverted++;
            patchRevertedPaths.add(filePath);
          }
        } else if (change.operation === "update" && change.diff) {
          let reversed = false;
          try {
            const currentContent = await readFile3(filePath, "utf8");
            const newContent = reverseV4aDiff(currentContent, change.diff);
            if (newContent !== null && newContent !== currentContent) {
              const { writeFile: writeFile7 } = await import("fs/promises");
              await writeFile7(filePath, newContent);
              reverted++;
              patchRevertedPaths.add(filePath);
              reversed = true;
            }
          } catch {
          }
          if (!reversed) {
            const isTracked = trackedFiles.has(filePath);
            if (isTracked && isGitRepo) {
              const relativePath = filePath.startsWith(gitRoot + "/") ? filePath.slice(gitRoot.length + 1) : filePath;
              try {
                await runCommand3("git", ["checkout", "HEAD", "--", relativePath], { cwd: gitRoot });
                reverted++;
                patchRevertedPaths.add(filePath);
              } catch {
                errors.push(`Could not revert: ${filePath}`);
              }
            } else {
              errors.push(`Could not reverse patch for untracked file: ${filePath}`);
            }
          }
        } else if (change.operation === "delete") {
          const isTracked = trackedFiles.has(filePath);
          if (isTracked && isGitRepo) {
            const relativePath = filePath.startsWith(gitRoot + "/") ? filePath.slice(gitRoot.length + 1) : filePath;
            try {
              await runCommand3("git", ["checkout", "HEAD", "--", relativePath], { cwd: gitRoot });
              reverted++;
              patchRevertedPaths.add(filePath);
            } catch {
              errors.push(`Could not restore deleted file: ${filePath}`);
            }
          }
        }
      } catch (err) {
        errors.push(`Failed to revert patch for ${filePath}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
  }
  for (const filePath of allCommandPaths) {
    if (patchRevertedPaths.has(filePath)) continue;
    const isTracked = trackedFiles.has(filePath);
    if (isTracked && isGitRepo) {
      const relativePath = filePath.startsWith(gitRoot + "/") ? filePath.slice(gitRoot.length + 1) : filePath;
      try {
        await runCommand3("git", ["checkout", "HEAD", "--", relativePath], { cwd: gitRoot });
        reverted++;
      } catch {
        errors.push(`Could not restore command-modified file: ${filePath}`);
      }
    }
  }
  return { reverted, errors };
}
function mergeSessionCommandsIntoTurns(turns, sessionLogRaw) {
  const turnIds = /* @__PURE__ */ new Set();
  for (const turn of turns) {
    const turnRecord = asRecord6(turn);
    const turnId = readNonEmptyString(turnRecord?.id);
    if (turnId) turnIds.add(turnId);
  }
  if (turnIds.size === 0) return turns;
  const orderByTurnId = buildSessionItemOrder(sessionLogRaw, turnIds);
  if (orderByTurnId.size === 0) return turns;
  return turns.map((turn) => {
    const turnRecord = asRecord6(turn);
    if (!turnRecord) return turn;
    const turnId = readNonEmptyString(turnRecord.id);
    if (!turnId) return turn;
    const slots = orderByTurnId.get(turnId);
    if (!slots || slots.length === 0) return turn;
    const existingItems = Array.isArray(turnRecord.items) ? turnRecord.items : [];
    const alreadyHasRecoveredItems = existingItems.some((it) => it.type === "commandExecution" || it.type === "fileChange");
    if (alreadyHasRecoveredItems) return turn;
    const agentMessages = existingItems.filter((it) => it.type === "agentMessage");
    const nonAgentNonUserItems = existingItems.filter((it) => it.type !== "agentMessage" && it.type !== "userMessage");
    const userMessages = existingItems.filter((it) => it.type === "userMessage");
    let agentIdx = 0;
    const interleaved = [...userMessages];
    for (const slot of slots) {
      if (slot.type === "agentMessage") {
        if (agentIdx < agentMessages.length) {
          interleaved.push(agentMessages[agentIdx]);
          agentIdx++;
        }
      } else if (slot.type === "commandExecution" && slot.command) {
        interleaved.push(slot.command);
      } else if (slot.type === "fileChange" && slot.fileChange) {
        interleaved.push(slot.fileChange);
      }
    }
    while (agentIdx < agentMessages.length) {
      interleaved.push(agentMessages[agentIdx]);
      agentIdx++;
    }
    interleaved.push(...nonAgentNonUserItems);
    return {
      ...turnRecord,
      items: interleaved
    };
  });
}
function isExactPhraseMatch(query, doc) {
  const q = query.trim().toLowerCase();
  if (!q) return false;
  return doc.title.toLowerCase().includes(q) || doc.preview.toLowerCase().includes(q) || doc.messageText.toLowerCase().includes(q);
}
function scoreFileCandidate(path, query) {
  if (!query) return 0;
  const lowerPath = path.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const baseName = lowerPath.slice(lowerPath.lastIndexOf("/") + 1);
  if (baseName === lowerQuery) return 0;
  if (baseName.startsWith(lowerQuery)) return 1;
  if (baseName.includes(lowerQuery)) return 2;
  if (lowerPath.includes(`/${lowerQuery}`)) return 3;
  if (lowerPath.includes(lowerQuery)) return 4;
  return 10;
}
async function listFilesWithRipgrep(cwd) {
  return await new Promise((resolve4, reject) => {
    const ripgrepCommand = resolveRipgrepCommand();
    if (!ripgrepCommand) {
      reject(new Error("ripgrep (rg) is not available"));
      return;
    }
    const proc = spawn4(ripgrepCommand, ["--files", "--hidden", "-g", "!.git", "-g", "!node_modules"], {
      cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code === 0) {
        const rows = stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        resolve4(rows);
        return;
      }
      const details = [stderr.trim(), stdout.trim()].filter(Boolean).join("\n");
      reject(new Error(details || "rg --files failed"));
    });
  });
}
function getCodexHomeDir3() {
  const codexHome = process.env.CODEX_HOME?.trim();
  return codexHome && codexHome.length > 0 ? codexHome : join6(homedir5(), ".codex");
}
function getPromptsDir() {
  return join6(getCodexHomeDir3(), "prompts");
}
function promptNameToFileName(name) {
  const trimmed = name.trim();
  const withoutExtension = trimmed.replace(/\.md$/i, "");
  const sanitized = withoutExtension.replace(/[\/\\:*?"<>|]/g, " ").replace(/\s+/g, " ").trim();
  return `${sanitized || "prompt"}.md`;
}
function buildPromptDescription(content) {
  const firstNonEmptyLine = content.split(/\r?\n/).map((line) => line.trim()).find(Boolean) ?? "";
  return firstNonEmptyLine.slice(0, 120);
}
async function listComposerPrompts() {
  const promptsDir = getPromptsDir();
  try {
    const entries = await readdir2(promptsDir, { withFileTypes: true });
    const prompts = await Promise.all(entries.filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".md")).map(async (entry) => {
      const promptPath = join6(promptsDir, entry.name);
      const content = await readFile3(promptPath, "utf8");
      return {
        name: entry.name.replace(/\.md$/i, ""),
        path: promptPath,
        content,
        description: buildPromptDescription(content)
      };
    }));
    return prompts.sort((a, b) => a.name.localeCompare(b.name));
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
}
async function createComposerPromptFile(name, content) {
  const trimmedName = name.trim();
  if (!trimmedName) throw new Error("Prompt name is required");
  const trimmedContent = content.trim();
  if (!trimmedContent) throw new Error("Prompt content is required");
  const promptsDir = getPromptsDir();
  await mkdir4(promptsDir, { recursive: true });
  const baseFileName = promptNameToFileName(trimmedName);
  let targetPath = join6(promptsDir, baseFileName);
  let suffix = 2;
  while (existsSync4(targetPath)) {
    const nextFileName = `${baseFileName.replace(/\.md$/i, "")}-${suffix}.md`;
    targetPath = join6(promptsDir, nextFileName);
    suffix += 1;
  }
  await writeFile4(targetPath, `${trimmedContent}
`, "utf8");
  return {
    name: basename4(targetPath).replace(/\.md$/i, ""),
    path: targetPath,
    content: `${trimmedContent}
`,
    description: buildPromptDescription(trimmedContent)
  };
}
async function removeComposerPromptFile(promptPath) {
  const resolvedPath = resolve2(promptPath);
  const promptsDir = resolve2(getPromptsDir());
  const relative = resolvedPath.startsWith(`${promptsDir}/`) ? resolvedPath.slice(promptsDir.length + 1) : "";
  if (!relative || relative.includes("..") || !resolvedPath.toLowerCase().endsWith(".md")) {
    throw new Error("Invalid prompt path");
  }
  try {
    await rm4(resolvedPath, { force: false });
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}
async function runCommand3(command, args, options = {}) {
  await new Promise((resolve4, reject) => {
    const proc = spawn4(command, args, {
      cwd: options.cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let closed = false;
    const timeout = typeof options.timeoutMs === "number" && Number.isFinite(options.timeoutMs) && options.timeoutMs > 0 ? setTimeout(() => {
      timedOut = true;
      proc.kill("SIGTERM");
      setTimeout(() => {
        if (!closed) proc.kill("SIGKILL");
      }, 5e3).unref();
    }, options.timeoutMs) : null;
    timeout?.unref();
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", (error) => {
      if (timeout) clearTimeout(timeout);
      reject(error);
    });
    proc.on("close", (code) => {
      closed = true;
      if (timeout) clearTimeout(timeout);
      if (timedOut) {
        reject(new Error(`Command timed out after ${options.timeoutMs}ms (${command} ${args.join(" ")})`));
        return;
      }
      if (code === 0) {
        resolve4();
        return;
      }
      const details = [stderr.trim(), stdout.trim()].filter(Boolean).join("\n");
      const suffix = details.length > 0 ? `: ${details}` : "";
      reject(new Error(`Command failed (${command} ${args.join(" ")})${suffix}`));
    });
  });
}
function isMissingHeadError2(error) {
  const message = getErrorMessage6(error, "").toLowerCase();
  return message.includes("not a valid object name: 'head'") || message.includes("not a valid object name: head") || message.includes("invalid reference: head");
}
function isNotGitRepositoryError2(error) {
  const message = getErrorMessage6(error, "").toLowerCase();
  return message.includes("not a git repository") || message.includes("fatal: not a git repository");
}
async function ensureRepoHasInitialCommit(repoRoot) {
  const agentsPath = join6(repoRoot, "AGENTS.md");
  try {
    await stat4(agentsPath);
  } catch {
    await writeFile4(agentsPath, "", "utf8");
  }
  await runCommand3("git", ["add", "AGENTS.md"], { cwd: repoRoot });
  await runCommand3(
    "git",
    ["-c", "user.name=Codex", "-c", "user.email=codex@local", "commit", "-m", "Initialize repository for worktree support"],
    { cwd: repoRoot }
  );
}
async function runCommandCapture2(command, args, options = {}) {
  return (await runCommandCaptureRaw2(command, args, options)).trim();
}
async function runCommandCaptureRaw2(command, args, options = {}) {
  return await new Promise((resolve4, reject) => {
    const proc = spawn4(command, args, {
      cwd: options.cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code === 0) {
        resolve4(stdout);
        return;
      }
      const details = [stderr.trim(), stdout.trim()].filter(Boolean).join("\n");
      const suffix = details.length > 0 ? `: ${details}` : "";
      reject(new Error(`Command failed (${command} ${args.join(" ")})${suffix}`));
    });
  });
}
function normalizeBranchRefName(value) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("refs/heads/")) return trimmed.slice("refs/heads/".length);
  if (trimmed.startsWith("refs/remotes/")) return trimmed.slice("refs/remotes/".length);
  return trimmed;
}
function toHeaderGitResetHistoryRef(branchName, commitSha) {
  return `refs/codex/header-git-reset-history/${branchName}/${commitSha}`;
}
var HEADER_GIT_RESET_HISTORY_REF_LIMIT = 25;
var HEADER_GIT_UNTRACKED_BACKUP_DIR = ".codex/untracked-backups";
async function assertLocalGitBranch(repoRoot, branchName) {
  await runCommandCapture2("git", ["show-ref", "--verify", `refs/heads/${branchName}`], { cwd: repoRoot });
}
function splitGitPathList2(raw) {
  return raw.split("\0").filter((entry) => entry.length > 0);
}
function isSafeGitRelativePath2(filePath) {
  return Boolean(filePath) && !isAbsolute2(filePath) && !filePath.split("/").includes("..");
}
function resolveGitRelativePath(repoRoot, filePath) {
  return join6(repoRoot, ...filePath.split("/"));
}
function gitPathsConflict(left, right) {
  return left === right || left.startsWith(`${right}/`) || right.startsWith(`${left}/`);
}
async function removeEmptyGitRelativeParents(repoRoot, filePath) {
  let current = dirname2(resolveGitRelativePath(repoRoot, filePath));
  while (current !== repoRoot && current.startsWith(`${repoRoot}/`)) {
    try {
      await rm4(current, { recursive: false });
    } catch {
      return;
    }
    current = dirname2(current);
  }
}
async function rollbackPreservedUntrackedFiles(entries) {
  for (const entry of entries.slice().reverse()) {
    try {
      if (existsSync4(entry.backupPath) && !existsSync4(entry.sourcePath)) {
        await mkdir4(dirname2(entry.sourcePath), { recursive: true });
        await rename(entry.backupPath, entry.sourcePath);
      }
    } catch {
    }
  }
}
async function preserveUntrackedFilesForGitTarget(repoRoot, targetRef) {
  const [untrackedRaw, targetTreeRaw] = await Promise.all([
    runCommandCaptureRaw2("git", ["ls-files", "--others", "--exclude-standard", "-z"], { cwd: repoRoot }),
    runCommandCaptureRaw2("git", ["ls-tree", "-r", "--name-only", "-z", `${targetRef}^{tree}`], { cwd: repoRoot })
  ]);
  const targetPaths = splitGitPathList2(targetTreeRaw);
  const conflictingUntrackedPaths = splitGitPathList2(untrackedRaw).filter((filePath) => isSafeGitRelativePath2(filePath) && targetPaths.some((targetPath) => gitPathsConflict(filePath, targetPath)));
  if (conflictingUntrackedPaths.length === 0) return [];
  const backupRoot = join6(repoRoot, HEADER_GIT_UNTRACKED_BACKUP_DIR, (/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-"));
  const movedFiles = [];
  for (const filePath of conflictingUntrackedPaths) {
    const sourcePath = resolveGitRelativePath(repoRoot, filePath);
    const backupPath = join6(backupRoot, ...filePath.split("/"));
    await mkdir4(dirname2(backupPath), { recursive: true });
    await rename(sourcePath, backupPath);
    movedFiles.push({ filePath, sourcePath, backupPath });
    await removeEmptyGitRelativeParents(repoRoot, filePath);
  }
  return movedFiles;
}
async function withPreservedUntrackedFilesForGitTarget(repoRoot, targetRef, operation) {
  const movedFiles = await preserveUntrackedFilesForGitTarget(repoRoot, targetRef);
  try {
    await operation();
  } catch (error) {
    await rollbackPreservedUntrackedFiles(movedFiles);
    throw error;
  }
}
async function checkoutGitBranchWithWorktreeRecovery(repoRoot, branchName) {
  await withPreservedUntrackedFilesForGitTarget(repoRoot, branchName, async () => {
    try {
      await runCommand3("git", ["checkout", branchName], { cwd: repoRoot });
    } catch (checkoutError) {
      const blockingWorktreePath = extractBranchLockedWorktreePath(checkoutError, branchName);
      if (!blockingWorktreePath) {
        throw checkoutError;
      }
      await runCommand3("git", ["checkout", "--detach"], { cwd: blockingWorktreePath });
      await runCommand3("git", ["checkout", branchName], { cwd: repoRoot });
    }
  });
}
async function pruneHeaderGitResetHistoryRefs(repoRoot, branchName) {
  const resetHistoryRefPrefix = `refs/codex/header-git-reset-history/${branchName}/`;
  const refsRaw = await runCommandCapture2(
    "git",
    ["for-each-ref", "--sort=-creatordate", "--format=%(refname)", resetHistoryRefPrefix],
    { cwd: repoRoot }
  ).catch(() => "");
  const refs = refsRaw.split("\n").map((entry) => entry.trim()).filter(Boolean);
  const staleRefs = refs.slice(HEADER_GIT_RESET_HISTORY_REF_LIMIT);
  for (const refName of staleRefs) {
    await runCommand3("git", ["update-ref", "-d", refName], { cwd: repoRoot });
  }
}
async function readGitHeaderState(cwd) {
  const gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd });
  const currentBranchRaw = await runCommandCapture2("git", ["branch", "--show-current"], { cwd: gitRoot });
  const currentBranch = currentBranchRaw.trim() || null;
  const headShaRaw = await runCommandCapture2("git", ["rev-parse", "--short=12", "HEAD"], { cwd: gitRoot });
  const headCommitRaw = await runCommandCapture2("git", ["show", "-s", "--date=short", "--format=%cd%x09%s", "HEAD"], { cwd: gitRoot });
  const [headDate = "", ...headSubjectParts] = headCommitRaw.split("	");
  const statusRaw = await runCommandCapture2("git", ["status", "--porcelain"], { cwd: gitRoot });
  return {
    currentBranch,
    headSha: headShaRaw.trim() || null,
    headSubject: headSubjectParts.join("	").trim() || null,
    headDate: headDate.trim() || null,
    detached: !currentBranch,
    dirty: statusRaw.trim().length > 0,
    gitRoot
  };
}
async function assertNoTrackedGitChanges(repoRoot) {
  const statusRaw = await runCommandCapture2("git", ["status", "--porcelain"], { cwd: repoRoot });
  const trackedChanges = statusRaw.split("\n").map((line) => line.trimEnd()).filter((line) => line && !line.startsWith("?? "));
  if (trackedChanges.length > 0) {
    throw new Error("Cannot switch branches or reset with tracked uncommitted changes. Commit, stash, or discard tracked changes first. Untracked files are allowed unless Git would overwrite them.");
  }
}
function extractBranchLockedWorktreePath(error, branchName) {
  const message = getErrorMessage6(error, "");
  if (!message || !branchName) return "";
  const escapedBranch = branchName.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const pattern = new RegExp(`'${escapedBranch}' is already checked out at '([^']+)'`, "u");
  const match = pattern.exec(message);
  return match?.[1]?.trim() ?? "";
}
function toPermanentWorktreeBranchNameDraft(worktreeName) {
  const sanitized = worktreeName.trim().replace(/[^A-Za-z0-9._-]+/gu, "-").replace(/\.+/gu, ".").replace(/-+/gu, "-").replace(/^[.-]+|[.-]+$/gu, "");
  return sanitized || "worktree";
}
async function isValidGitBranchName(gitRoot, branchName) {
  try {
    await runCommand3("git", ["check-ref-format", "--branch", branchName], { cwd: gitRoot });
    return true;
  } catch {
    return false;
  }
}
async function doesLocalGitBranchExist(gitRoot, branchName) {
  try {
    await runCommand3("git", ["show-ref", "--verify", "--quiet", `refs/heads/${branchName}`], { cwd: gitRoot });
    return true;
  } catch {
    return false;
  }
}
async function allocatePermanentWorktreeBranchName(gitRoot, worktreeName) {
  const base = toPermanentWorktreeBranchNameDraft(worktreeName);
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const candidate = attempt === 0 ? base : `${base}-${attempt + 1}`;
    if (!await isValidGitBranchName(gitRoot, candidate)) continue;
    if (!await doesLocalGitBranchExist(gitRoot, candidate)) return candidate;
  }
  throw new Error("Failed to allocate a unique branch name for worktree");
}
function normalizeStringArray(value) {
  if (!Array.isArray(value)) return [];
  const normalized = [];
  for (const item of value) {
    if (typeof item === "string" && item.length > 0 && !normalized.includes(item)) {
      normalized.push(item);
    }
  }
  return normalized;
}
function normalizeStringRecord(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const next = {};
  for (const [key, item] of Object.entries(value)) {
    if (typeof key === "string" && key.length > 0 && typeof item === "string") {
      next[key] = item;
    }
  }
  return next;
}
function normalizeRemoteProjects(value) {
  if (!Array.isArray(value)) return [];
  const next = [];
  const seen = /* @__PURE__ */ new Set();
  for (const item of value) {
    const record = asRecord6(item);
    if (!record) continue;
    const id = typeof record.id === "string" ? record.id.trim() : "";
    if (!id || seen.has(id)) continue;
    seen.add(id);
    next.push({
      id,
      hostId: typeof record.hostId === "string" ? record.hostId.trim() : "",
      remotePath: typeof record.remotePath === "string" ? record.remotePath.trim() : "",
      label: typeof record.label === "string" ? record.label.trim() : ""
    });
  }
  return next;
}
function getCodexAuthPath() {
  return join6(getCodexHomeDir3(), "auth.json");
}
var CODEX_CHATGPT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann";
var DEFAULT_CODEX_REFRESH_TOKEN_URL = "https://auth.openai.com/oauth/token";
function decodeBase64UrlJson2(value) {
  try {
    const padded = `${value}${"=".repeat((4 - value.length % 4) % 4)}`;
    const decoded = Buffer.from(padded.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8");
    const parsed = JSON.parse(decoded);
    return asRecord6(parsed);
  } catch {
    return null;
  }
}
function decodeJwtPayload(token) {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length < 2) return null;
  return decodeBase64UrlJson2(parts[1] ?? "");
}
function extractChatgptTokenMetadata(accessToken) {
  const payload = decodeJwtPayload(accessToken);
  const auth = asRecord6(payload?.["https://api.openai.com/auth"]);
  return {
    chatgptAccountId: readNonEmptyString(auth?.chatgpt_account_id) || null,
    chatgptPlanType: readNonEmptyString(auth?.chatgpt_plan_type) || null
  };
}
function readTokenErrorMessage(payload, fallback) {
  const record = asRecord6(payload);
  const message = readNonEmptyString(record?.message);
  if (message) return message;
  const error = record?.error;
  if (typeof error === "string" && error.trim().length > 0) return error.trim();
  const nestedError = asRecord6(error);
  return readNonEmptyString(nestedError?.message) || readNonEmptyString(nestedError?.error_description) || readNonEmptyString(record?.error_description) || fallback;
}
function readTokenResponseString(payload, ...keys) {
  if (!payload) return null;
  for (const key of keys) {
    const value = readNonEmptyString(payload[key]);
    if (value) return value;
  }
  return null;
}
async function refreshChatgptAuthTokensForExternalAuth(params = {}) {
  const authPath = getCodexAuthPath();
  const raw = await readFile3(authPath, "utf8");
  const auth = JSON.parse(raw);
  const currentRefreshToken = auth.tokens?.refresh_token?.trim() ?? "";
  if (!currentRefreshToken) {
    throw new Error("No ChatGPT refresh token is available. Please sign in again.");
  }
  const refreshUrl = process.env.CODEX_REFRESH_TOKEN_URL_OVERRIDE?.trim() || DEFAULT_CODEX_REFRESH_TOKEN_URL;
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: currentRefreshToken,
    client_id: CODEX_CHATGPT_CLIENT_ID
  });
  const response = await fetch(refreshUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: body.toString(),
    signal: AbortSignal.timeout(25e3)
  });
  const text = await response.text();
  let payload = null;
  try {
    payload = asRecord6(JSON.parse(text));
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(readTokenErrorMessage(payload, `ChatGPT token refresh failed with HTTP ${String(response.status)}`));
  }
  const accessToken = readTokenResponseString(payload, "access_token", "accessToken");
  if (!accessToken) {
    throw new Error("ChatGPT token refresh response did not include an access token.");
  }
  const nextRefreshToken = readTokenResponseString(payload, "refresh_token", "refreshToken") ?? currentRefreshToken;
  const nextIdToken = readTokenResponseString(payload, "id_token", "idToken") ?? auth.tokens?.id_token;
  const metadata = extractChatgptTokenMetadata(accessToken);
  const chatgptAccountId = metadata.chatgptAccountId || readTokenResponseString(payload, "chatgpt_account_id", "chatgptAccountId") || readNonEmptyString(params.previousAccountId) || readNonEmptyString(auth.tokens?.account_id);
  if (!chatgptAccountId) {
    throw new Error("ChatGPT token refresh response did not include account metadata.");
  }
  const nextAuth = {
    ...auth,
    auth_mode: auth.auth_mode || "chatgpt",
    last_refresh: Date.now(),
    tokens: {
      ...auth.tokens,
      access_token: accessToken,
      refresh_token: nextRefreshToken,
      account_id: chatgptAccountId,
      ...nextIdToken ? { id_token: nextIdToken } : {}
    }
  };
  await writeFile4(authPath, JSON.stringify(nextAuth, null, 2), { encoding: "utf8", mode: 384 });
  return {
    accessToken,
    chatgptAccountId,
    chatgptPlanType: metadata.chatgptPlanType
  };
}
async function readCodexAuth() {
  try {
    const raw = await readFile3(getCodexAuthPath(), "utf8");
    const auth = JSON.parse(raw);
    const token = auth.tokens?.access_token;
    if (!token) return null;
    return { accessToken: token, accountId: auth.tokens?.account_id ?? void 0 };
  } catch {
    return null;
  }
}
function hasUsableCodexAuthSync() {
  try {
    const raw = readFileSync2(getCodexAuthPath(), "utf8");
    const auth = JSON.parse(raw);
    return Boolean(auth.tokens?.access_token?.trim());
  } catch {
    return false;
  }
}
function readFreeModeStateSync(statePath) {
  try {
    return JSON.parse(readFileSync2(statePath, "utf8"));
  } catch {
    return null;
  }
}
async function writeFreeModeStateFile(statePath, state) {
  await mkdir4(dirname2(statePath), { recursive: true });
  await writeFile4(statePath, JSON.stringify(state), { encoding: "utf8", mode: 384 });
}
function ensureDefaultFreeModeStateForMissingAuthSync(statePath) {
  const current = readFreeModeStateSync(statePath);
  const hasUsableCodexAuth2 = hasUsableCodexAuthSync();
  if (shouldSuppressCommunityFreeModeForCodexAuth(current, hasUsableCodexAuth2)) {
    return null;
  }
  if (!shouldCreateDefaultFreeModeStateForMissingAuth(current, hasUsableCodexAuth2)) {
    return current;
  }
  return createDefaultOpenCodeZenFreeModeState();
}
function isLoopbackRemoteAddress(remoteAddress) {
  if (!remoteAddress) return false;
  const normalized = remoteAddress.startsWith("::ffff:") ? remoteAddress.slice("::ffff:".length) : remoteAddress;
  return normalized === "127.0.0.1" || normalized === "::1";
}
function getCodexGlobalStatePath() {
  return join6(getCodexHomeDir3(), ".codex-global-state.json");
}
function getTelegramBridgeConfigPath() {
  return join6(getCodexHomeDir3(), "telegram-bridge.json");
}
function getCodexSessionIndexPath() {
  return join6(getCodexHomeDir3(), "session_index.jsonl");
}
function getCodexAutomationsDir() {
  return join6(getCodexHomeDir3(), "automations");
}
function readTomlString(value) {
  const trimmed = value.trim();
  if (trimmed.startsWith('"') && trimmed.endsWith('"') || trimmed.startsWith("'") && trimmed.endsWith("'")) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed.slice(1, -1);
    }
  }
  return trimmed;
}
function serializeTomlString(value) {
  return JSON.stringify(value);
}
function parseTomlStringArray(value) {
  const trimmed = value.trim();
  if (!trimmed.startsWith("[") || !trimmed.endsWith("]")) return [];
  const values = [];
  let index = 1;
  const endIndex = trimmed.length - 1;
  while (index < endIndex) {
    while (index < endIndex && /[\s,]/u.test(trimmed[index] ?? "")) index += 1;
    if (index >= endIndex) break;
    const quote = trimmed[index];
    if (quote !== '"' && quote !== "'") return [];
    const start = index;
    index += 1;
    let valueText = "";
    if (quote === "'") {
      const closeIndex = trimmed.indexOf("'", index);
      if (closeIndex < 0 || closeIndex > endIndex) return [];
      valueText = trimmed.slice(index, closeIndex);
      index = closeIndex + 1;
    } else {
      let escaped = false;
      while (index < endIndex) {
        const char = trimmed[index] ?? "";
        if (escaped) {
          escaped = false;
        } else if (char === "\\") {
          escaped = true;
        } else if (char === '"') {
          break;
        }
        index += 1;
      }
      if (index >= endIndex || trimmed[index] !== '"') return [];
      try {
        valueText = JSON.parse(trimmed.slice(start, index + 1));
      } catch {
        return [];
      }
      index += 1;
    }
    if (valueText.trim().length > 0) values.push(valueText);
    while (index < endIndex && /\s/u.test(trimmed[index] ?? "")) index += 1;
    if (index < endIndex && trimmed[index] !== ",") return [];
  }
  return values;
}
function serializeTomlStringArray(values) {
  return `[${values.map((value) => serializeTomlString(value)).join(", ")}]`;
}
function parseAutomationToml(raw) {
  const values = {};
  const extraTomlLines = [];
  const knownKeys = /* @__PURE__ */ new Set([
    "version",
    "id",
    "kind",
    "name",
    "prompt",
    "status",
    "rrule",
    "target_thread_id",
    "cwds",
    "created_at",
    "updated_at"
  ]);
  let isInsideExtraTable = false;
  for (const line of raw.split(/\r?\n/u)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      isInsideExtraTable = true;
      extraTomlLines.push(trimmed);
      continue;
    }
    if (isInsideExtraTable) {
      extraTomlLines.push(trimmed);
      continue;
    }
    if (!trimmed.includes("=")) {
      extraTomlLines.push(trimmed);
      continue;
    }
    const separatorIndex = trimmed.indexOf("=");
    const key = trimmed.slice(0, separatorIndex).trim();
    const value = trimmed.slice(separatorIndex + 1).trim();
    if (!key) continue;
    if (knownKeys.has(key)) {
      values[key] = value;
    } else {
      extraTomlLines.push(trimmed);
    }
  }
  const id = readTomlString(values.id ?? "");
  const kindValue = readTomlString(values.kind ?? (values.cwds ? "cron" : "heartbeat"));
  const name = readTomlString(values.name ?? "");
  const prompt = readTomlString(values.prompt ?? "");
  const rrule = readTomlString(values.rrule ?? "");
  const statusValue = readTomlString(values.status ?? "ACTIVE");
  const targetThreadId = readTomlString(values.target_thread_id ?? "") || null;
  const cwds = parseTomlStringArray(values.cwds ?? "");
  const createdAtMs = Number.parseInt(values.created_at ?? "", 10);
  const updatedAtMs = Number.parseInt(values.updated_at ?? "", 10);
  if (!id || !name || !prompt || !rrule) return null;
  if (kindValue !== "heartbeat" && kindValue !== "cron") return null;
  if (statusValue !== "ACTIVE" && statusValue !== "PAUSED") return null;
  return {
    id,
    kind: kindValue,
    name,
    prompt,
    rrule,
    status: statusValue,
    targetThreadId,
    cwds,
    extraTomlLines,
    createdAtMs: Number.isFinite(createdAtMs) ? createdAtMs : null,
    updatedAtMs: Number.isFinite(updatedAtMs) ? updatedAtMs : null,
    nextRunAtMs: null
  };
}
function serializeAutomationToml(record) {
  const lines = [
    "version = 1",
    `id = ${serializeTomlString(record.id)}`,
    `kind = ${serializeTomlString(record.kind)}`,
    `name = ${serializeTomlString(record.name)}`,
    `prompt = ${serializeTomlString(record.prompt)}`,
    `status = ${serializeTomlString(record.status)}`,
    `rrule = ${serializeTomlString(record.rrule)}`
  ];
  if (record.targetThreadId) {
    lines.push(`target_thread_id = ${serializeTomlString(record.targetThreadId)}`);
  }
  if (record.cwds.length > 0) {
    lines.push(`cwds = ${serializeTomlStringArray(record.cwds)}`);
  }
  lines.push(
    `created_at = ${String(record.createdAtMs ?? Date.now())}`,
    `updated_at = ${String(record.updatedAtMs ?? Date.now())}`
  );
  lines.push(...record.extraTomlLines);
  return `${lines.join("\n")}
`;
}
function toAutomationApiRecord(record) {
  const { extraTomlLines: _extraTomlLines, ...apiRecord } = record;
  return apiRecord;
}
function toAutomationApiMap(automationsByTarget) {
  return Object.fromEntries(
    Object.entries(automationsByTarget).map(([target, automations]) => [
      target,
      automations.map(toAutomationApiRecord)
    ])
  );
}
function toAutomationApiData(automation) {
  if (Array.isArray(automation)) return automation.map(toAutomationApiRecord);
  return automation ? toAutomationApiRecord(automation) : null;
}
function slugifyAutomationId(threadId, name) {
  const preferred = name.trim().toLowerCase().replace(/[^a-z0-9]+/gu, "-").replace(/^-+|-+$/gu, "");
  if (preferred) return preferred.slice(0, 48);
  const fallback = threadId.trim().toLowerCase().replace(/[^a-z0-9]+/gu, "-").replace(/^-+|-+$/gu, "");
  return `heartbeat-${fallback.slice(0, 24) || randomBytes(4).toString("hex")}`;
}
async function readAutomationRecordFromFile(filePath) {
  try {
    return parseAutomationToml(await readFile3(filePath, "utf8"));
  } catch {
    return null;
  }
}
async function listThreadHeartbeatAutomations() {
  const automationRoot = getCodexAutomationsDir();
  const next = {};
  let entries;
  try {
    entries = await readdir2(automationRoot, { withFileTypes: true });
  } catch {
    return next;
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const automation = await readAutomationRecordFromFile(join6(automationRoot, entry.name, "automation.toml"));
    if (!automation || automation.kind !== "heartbeat" || !automation.targetThreadId) continue;
    next[automation.targetThreadId] = [...next[automation.targetThreadId] ?? [], automation];
  }
  for (const automations of Object.values(next)) {
    automations.sort((first, second) => {
      const firstCreatedAt = first.createdAtMs ?? 0;
      const secondCreatedAt = second.createdAtMs ?? 0;
      if (firstCreatedAt !== secondCreatedAt) return firstCreatedAt - secondCreatedAt;
      return first.id.localeCompare(second.id);
    });
  }
  return next;
}
async function readThreadHeartbeatAutomations(threadId) {
  const all = await listThreadHeartbeatAutomations();
  return all[threadId] ?? [];
}
async function readThreadHeartbeatAutomation(threadId, automationId = "") {
  const automations = await readThreadHeartbeatAutomations(threadId);
  if (automationId) return automations.find((automation) => automation.id === automationId) ?? null;
  return automations[0] ?? null;
}
function resolveUniqueAutomationId(existingIds, threadId, name) {
  const baseId = slugifyAutomationId(threadId, name);
  if (!existingIds.has(baseId)) return baseId;
  for (let index = 2; index < 1e3; index += 1) {
    const candidate = `${baseId}-${index}`;
    if (!existingIds.has(candidate)) return candidate;
  }
  return `${baseId}-${randomBytes(4).toString("hex")}`;
}
async function writeThreadHeartbeatAutomation(input) {
  const threadId = input.threadId.trim();
  const name = input.name.trim();
  const prompt = input.prompt.trim();
  const rrule = input.rrule.trim();
  if (!threadId || !name || !prompt || !rrule) {
    throw new Error("threadId, name, prompt, and rrule are required");
  }
  const automationRoot = getCodexAutomationsDir();
  await mkdir4(automationRoot, { recursive: true });
  const existing = input.id ? await readThreadHeartbeatAutomation(threadId, input.id.trim()) : null;
  const entries = await readdir2(automationRoot, { withFileTypes: true }).catch(() => []);
  const existingIds = new Set(entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name));
  const id = existing?.id ?? resolveUniqueAutomationId(existingIds, threadId, name);
  const automationDir = join6(automationRoot, id);
  const now = Date.now();
  const record = {
    id,
    kind: "heartbeat",
    name,
    prompt,
    rrule,
    status: input.status,
    targetThreadId: threadId,
    cwds: [],
    extraTomlLines: existing?.extraTomlLines ?? [],
    createdAtMs: existing?.createdAtMs ?? now,
    updatedAtMs: now,
    nextRunAtMs: null
  };
  await mkdir4(automationDir, { recursive: true });
  await writeFile4(join6(automationDir, "automation.toml"), serializeAutomationToml(record), "utf8");
  const memoryPath = join6(automationDir, "memory.md");
  try {
    await stat4(memoryPath);
  } catch {
    await writeFile4(memoryPath, "", "utf8");
  }
  return record;
}
async function deleteThreadHeartbeatAutomation(threadId, automationId = "") {
  const normalizedThreadId = threadId.trim();
  const normalizedAutomationId = automationId.trim();
  if (normalizedAutomationId) {
    const automation = await readThreadHeartbeatAutomation(normalizedThreadId, normalizedAutomationId);
    if (!automation) return false;
    await rm4(join6(getCodexAutomationsDir(), automation.id), { recursive: true, force: true });
    return true;
  }
  const automations = await readThreadHeartbeatAutomations(normalizedThreadId);
  if (automations.length === 0) return false;
  await Promise.all(automations.map((automation) => rm4(join6(getCodexAutomationsDir(), automation.id), { recursive: true, force: true })));
  return true;
}
async function listProjectCronAutomations() {
  const automationRoot = getCodexAutomationsDir();
  const next = {};
  let entries;
  try {
    entries = await readdir2(automationRoot, { withFileTypes: true });
  } catch {
    return next;
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const automation = await readAutomationRecordFromFile(join6(automationRoot, entry.name, "automation.toml"));
    if (!automation || automation.kind !== "cron" || automation.cwds.length === 0) continue;
    for (const cwd of automation.cwds) {
      next[cwd] = [...next[cwd] ?? [], automation];
    }
  }
  for (const automations of Object.values(next)) {
    automations.sort((first, second) => {
      const firstCreatedAt = first.createdAtMs ?? 0;
      const secondCreatedAt = second.createdAtMs ?? 0;
      if (firstCreatedAt !== secondCreatedAt) return firstCreatedAt - secondCreatedAt;
      return first.id.localeCompare(second.id);
    });
  }
  return next;
}
async function readProjectCronAutomations(projectName) {
  const all = await listProjectCronAutomations();
  return all[projectName] ?? [];
}
async function readProjectCronAutomation(projectName, automationId = "") {
  const automations = await readProjectCronAutomations(projectName);
  if (automationId) return automations.find((automation) => automation.id === automationId) ?? null;
  return automations[0] ?? null;
}
async function writeProjectCronAutomation(input) {
  const projectName = input.projectName.trim();
  const name = input.name.trim();
  const prompt = input.prompt.trim();
  const rrule = input.rrule.trim();
  if (!projectName || !name || !prompt || !rrule) {
    throw new Error("projectName, name, prompt, and rrule are required");
  }
  if (!isAbsoluteLikePath(projectName)) {
    throw new Error("Project automation cwd must be an absolute path");
  }
  const automationRoot = getCodexAutomationsDir();
  await mkdir4(automationRoot, { recursive: true });
  const existing = input.id ? await readProjectCronAutomation(projectName, input.id.trim()) : null;
  const entries = await readdir2(automationRoot, { withFileTypes: true }).catch(() => []);
  const existingIds = new Set(entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name));
  const id = existing?.id ?? resolveUniqueAutomationId(existingIds, projectName, name);
  const automationDir = join6(automationRoot, id);
  const now = Date.now();
  const record = {
    id,
    kind: "cron",
    name,
    prompt,
    rrule,
    status: input.status,
    targetThreadId: null,
    cwds: Array.from(/* @__PURE__ */ new Set([...existing?.cwds ?? [], projectName])),
    extraTomlLines: existing?.extraTomlLines ?? [],
    createdAtMs: existing?.createdAtMs ?? now,
    updatedAtMs: now,
    nextRunAtMs: null
  };
  await mkdir4(automationDir, { recursive: true });
  await writeFile4(join6(automationDir, "automation.toml"), serializeAutomationToml(record), "utf8");
  const memoryPath = join6(automationDir, "memory.md");
  try {
    await stat4(memoryPath);
  } catch {
    await writeFile4(memoryPath, "", "utf8");
  }
  return record;
}
async function deleteProjectCronAutomation(projectName, automationId = "") {
  const normalizedProjectName = projectName.trim();
  const normalizedAutomationId = automationId.trim();
  if (!normalizedProjectName || !isAbsoluteLikePath(normalizedProjectName)) return false;
  if (normalizedAutomationId) {
    const automation = await readProjectCronAutomation(normalizedProjectName, normalizedAutomationId);
    if (!automation) return false;
    const remainingCwds = automation.cwds.filter((cwd) => cwd !== normalizedProjectName);
    if (remainingCwds.length > 0) {
      const record = { ...automation, cwds: remainingCwds, updatedAtMs: Date.now() };
      await writeFile4(join6(getCodexAutomationsDir(), automation.id, "automation.toml"), serializeAutomationToml(record), "utf8");
    } else {
      await rm4(join6(getCodexAutomationsDir(), automation.id), { recursive: true, force: true });
    }
    return true;
  }
  const automations = await readProjectCronAutomations(normalizedProjectName);
  if (automations.length === 0) return false;
  await Promise.all(automations.map(async (automation) => {
    const remainingCwds = automation.cwds.filter((cwd) => cwd !== normalizedProjectName);
    if (remainingCwds.length > 0) {
      const record = { ...automation, cwds: remainingCwds, updatedAtMs: Date.now() };
      await writeFile4(join6(getCodexAutomationsDir(), automation.id, "automation.toml"), serializeAutomationToml(record), "utf8");
      return;
    }
    await rm4(join6(getCodexAutomationsDir(), automation.id), { recursive: true, force: true });
  }));
  return true;
}
var MAX_THREAD_TITLES = 500;
var EMPTY_THREAD_TITLE_CACHE = { titles: {}, order: [] };
var PINNED_THREAD_IDS_KEY = "pinned-thread-ids";
var sessionIndexThreadTitleCacheState = {
  fileSignature: null,
  cache: EMPTY_THREAD_TITLE_CACHE
};
function normalizeThreadTitleCache(value) {
  const record = asRecord6(value);
  if (!record) return EMPTY_THREAD_TITLE_CACHE;
  const rawTitles = asRecord6(record.titles);
  const titles = {};
  if (rawTitles) {
    for (const [k, v] of Object.entries(rawTitles)) {
      if (typeof v === "string" && v.length > 0) titles[k] = v;
    }
  }
  const order = normalizeStringArray(record.order);
  return { titles, order };
}
function normalizePinnedThreadIds(value) {
  return normalizeStringArray(value);
}
function updateThreadTitleCache(cache, id, title) {
  const titles = { ...cache.titles, [id]: title };
  const order = [id, ...cache.order.filter((o) => o !== id)];
  while (order.length > MAX_THREAD_TITLES) {
    const removed = order.pop();
    if (removed) delete titles[removed];
  }
  return { titles, order };
}
function removeFromThreadTitleCache(cache, id) {
  const { [id]: _, ...titles } = cache.titles;
  return { titles, order: cache.order.filter((o) => o !== id) };
}
function normalizeSessionIndexThreadTitle(value) {
  const record = asRecord6(value);
  if (!record) return null;
  const id = typeof record.id === "string" ? record.id.trim() : "";
  const title = typeof record.thread_name === "string" ? record.thread_name.trim() : "";
  const updatedAtIso = typeof record.updated_at === "string" ? record.updated_at.trim() : "";
  const updatedAtMs = updatedAtIso ? Date.parse(updatedAtIso) : Number.NaN;
  if (!id || !title) return null;
  return {
    id,
    title,
    updatedAtMs: Number.isFinite(updatedAtMs) ? updatedAtMs : 0
  };
}
function trimThreadTitleCache(cache) {
  const titles = { ...cache.titles };
  const order = cache.order.filter((id) => {
    if (!titles[id]) return false;
    return true;
  }).slice(0, MAX_THREAD_TITLES);
  for (const id of Object.keys(titles)) {
    if (!order.includes(id)) {
      delete titles[id];
    }
  }
  return { titles, order };
}
function mergeThreadTitleCaches(base, overlay) {
  const titles = { ...base.titles, ...overlay.titles };
  const order = [];
  for (const id of [...overlay.order, ...base.order]) {
    if (!titles[id] || order.includes(id)) continue;
    order.push(id);
  }
  for (const id of Object.keys(titles)) {
    if (!order.includes(id)) {
      order.push(id);
    }
  }
  return trimThreadTitleCache({ titles, order });
}
async function readThreadTitleCache() {
  const statePath = getCodexGlobalStatePath();
  try {
    const raw = await readFile3(statePath, "utf8");
    const payload = asRecord6(JSON.parse(raw)) ?? {};
    return normalizeThreadTitleCache(payload["thread-titles"]);
  } catch {
    return EMPTY_THREAD_TITLE_CACHE;
  }
}
async function writeThreadTitleCache(cache) {
  const statePath = getCodexGlobalStatePath();
  let payload = {};
  try {
    const raw = await readFile3(statePath, "utf8");
    payload = asRecord6(JSON.parse(raw)) ?? {};
  } catch {
    payload = {};
  }
  payload["thread-titles"] = cache;
  await writeFile4(statePath, JSON.stringify(payload), "utf8");
}
async function readPinnedThreadIds() {
  const statePath = getCodexGlobalStatePath();
  try {
    const raw = await readFile3(statePath, "utf8");
    const payload = asRecord6(JSON.parse(raw)) ?? {};
    return normalizePinnedThreadIds(payload[PINNED_THREAD_IDS_KEY]);
  } catch {
    return [];
  }
}
async function writePinnedThreadIds(threadIds) {
  const statePath = getCodexGlobalStatePath();
  let payload = {};
  try {
    const raw = await readFile3(statePath, "utf8");
    payload = asRecord6(JSON.parse(raw)) ?? {};
  } catch {
    payload = {};
  }
  payload[PINNED_THREAD_IDS_KEY] = normalizePinnedThreadIds(threadIds);
  await writeFile4(statePath, JSON.stringify(payload), "utf8");
}
var FIRST_LAUNCH_PLUGINS_CARD_DISMISSED_KEY = "first-launch-plugins-card-dismissed";
var THREAD_QUEUE_STATE_KEY = "thread-queue-state";
function normalizeStoredQueuedMessage(value) {
  const record = asRecord6(value);
  if (!record) return null;
  const id = typeof record.id === "string" ? record.id.trim() : "";
  if (!id) return null;
  const normalizeNamedPathItems = (items) => {
    if (!Array.isArray(items)) return [];
    return items.flatMap((item) => {
      const itemRecord = asRecord6(item);
      if (!itemRecord) return [];
      const name = typeof itemRecord.name === "string" ? itemRecord.name.trim() : "";
      const path = typeof itemRecord.path === "string" ? itemRecord.path.trim() : "";
      return name && path ? [{ name, path }] : [];
    });
  };
  const normalizeFileAttachments = (items) => {
    if (!Array.isArray(items)) return [];
    return items.flatMap((item) => {
      const itemRecord = asRecord6(item);
      if (!itemRecord) return [];
      const label = typeof itemRecord.label === "string" ? itemRecord.label.trim() : "";
      const path = typeof itemRecord.path === "string" ? itemRecord.path.trim() : "";
      const fsPath = typeof itemRecord.fsPath === "string" ? itemRecord.fsPath.trim() : "";
      return label && path && fsPath ? [{ label, path, fsPath }] : [];
    });
  };
  return {
    id,
    text: typeof record.text === "string" ? record.text : "",
    imageUrls: normalizeStringArray(record.imageUrls),
    skills: normalizeNamedPathItems(record.skills),
    fileAttachments: normalizeFileAttachments(record.fileAttachments),
    collaborationMode: record.collaborationMode === "plan" ? "plan" : "default"
  };
}
function normalizeThreadQueueState(value) {
  const record = asRecord6(value);
  if (!record) return {};
  const state = {};
  for (const [threadId, rawMessages] of Object.entries(record)) {
    const normalizedThreadId = threadId.trim();
    if (!normalizedThreadId || !Array.isArray(rawMessages)) continue;
    const messages = rawMessages.flatMap((item) => {
      const message = normalizeStoredQueuedMessage(item);
      return message ? [message] : [];
    });
    if (messages.length > 0) {
      state[normalizedThreadId] = messages;
    }
  }
  return state;
}
var threadQueueMutationChain = Promise.resolve();
async function readThreadQueueState() {
  const statePath = getCodexGlobalStatePath();
  try {
    const raw = await readFile3(statePath, "utf8");
    const payload = asRecord6(JSON.parse(raw)) ?? {};
    return normalizeThreadQueueState(payload[THREAD_QUEUE_STATE_KEY]);
  } catch {
    return {};
  }
}
async function writeThreadQueueStateUnlocked(nextState) {
  const statePath = getCodexGlobalStatePath();
  let payload = {};
  try {
    const raw = await readFile3(statePath, "utf8");
    payload = asRecord6(JSON.parse(raw)) ?? {};
  } catch {
    payload = {};
  }
  const normalized = normalizeThreadQueueState(nextState);
  if (Object.keys(normalized).length > 0) {
    payload[THREAD_QUEUE_STATE_KEY] = normalized;
  } else {
    delete payload[THREAD_QUEUE_STATE_KEY];
  }
  await writeFile4(statePath, JSON.stringify(payload), "utf8");
}
async function withThreadQueueStateUpdate(update) {
  const run = threadQueueMutationChain.then(async () => {
    const currentState = await readThreadQueueState();
    const { nextState, result } = await update(currentState);
    await writeThreadQueueStateUnlocked(nextState);
    return result;
  });
  threadQueueMutationChain = run.catch(() => {
  });
  return run;
}
async function writeThreadQueueState(nextState) {
  await withThreadQueueStateUpdate(() => ({
    nextState: normalizeThreadQueueState(nextState),
    result: void 0
  }));
}
async function appendThreadQueuedMessage(threadId, message) {
  const normalizedThreadId = threadId.trim();
  if (!normalizedThreadId) throw new Error("threadId is required");
  await withThreadQueueStateUpdate((state) => ({
    nextState: {
      ...state,
      [normalizedThreadId]: [...state[normalizedThreadId] ?? [], message]
    },
    result: void 0
  }));
}
function normalizeReasoningEffort(value) {
  const allowed = ["none", "minimal", "low", "medium", "high", "xhigh"];
  return typeof value === "string" && allowed.includes(value) ? value : "";
}
function normalizeCollaborationModeReasoningEffort(value) {
  return value && value.length > 0 ? value : null;
}
function extractLocalImagePathFromUrl(value) {
  if (!value) return null;
  try {
    const parsed = new URL(value, "http://localhost");
    if (parsed.pathname !== "/codex-local-image") return null;
    const path = parsed.searchParams.get("path")?.trim() ?? "";
    return path.length > 0 ? path : null;
  } catch {
    return null;
  }
}
function buildTextWithAttachments(prompt, files) {
  if (files.length === 0) return prompt;
  let prefix = "# Files mentioned by the user:\n";
  for (const f of files) {
    prefix += `
## ${f.label}: ${f.path}
`;
  }
  return `${prefix}
## My request for Codex:

${prompt}
`;
}
function escapeHeartbeatXmlText(value) {
  return value.replace(/&/gu, "&amp;").replace(/</gu, "&lt;").replace(/>/gu, "&gt;");
}
function buildHeartbeatQueuedMessage(automation) {
  return {
    id: `automation-${automation.id}-${Date.now()}-${randomBytes(3).toString("hex")}`,
    text: `<heartbeat>
<automation_id>${escapeHeartbeatXmlText(automation.id)}</automation_id>
<current_time_iso>${(/* @__PURE__ */ new Date()).toISOString()}</current_time_iso>
<instructions>
${escapeHeartbeatXmlText(automation.prompt)}
</instructions>
</heartbeat>`,
    imageUrls: [],
    skills: [],
    fileAttachments: [],
    collaborationMode: "default"
  };
}
function fileNameFromPath(pathValue) {
  const normalized = pathValue.replace(/\\/g, "/");
  const segments = normalized.split("/").filter(Boolean);
  return segments.at(-1) ?? normalized;
}
function extractThreadIdFromNotificationParams(params) {
  const record = asRecord6(params);
  if (!record) return "";
  const threadId = (typeof record.threadId === "string" ? record.threadId : "") || (typeof record.thread_id === "string" ? record.thread_id : "") || (typeof record.conversationId === "string" ? record.conversationId : "") || (typeof record.conversation_id === "string" ? record.conversation_id : "");
  if (threadId) return threadId;
  const thread = asRecord6(record.thread);
  if (thread && typeof thread.id === "string") return thread.id;
  const turn = asRecord6(record.turn);
  if (turn) {
    const turnThreadId = (typeof turn.threadId === "string" ? turn.threadId : "") || (typeof turn.thread_id === "string" ? turn.thread_id : "");
    if (turnThreadId) return turnThreadId;
  }
  return "";
}
function isTurnCompletedNotification(notification) {
  return notification.method === "turn/completed";
}
async function readFirstLaunchPluginsCardDismissed() {
  const statePath = getCodexGlobalStatePath();
  try {
    const raw = await readFile3(statePath, "utf8");
    const payload = asRecord6(JSON.parse(raw)) ?? {};
    return payload[FIRST_LAUNCH_PLUGINS_CARD_DISMISSED_KEY] === true;
  } catch {
    return false;
  }
}
async function writeFirstLaunchPluginsCardDismissed(dismissed) {
  const statePath = getCodexGlobalStatePath();
  let payload = {};
  try {
    const raw = await readFile3(statePath, "utf8");
    payload = asRecord6(JSON.parse(raw)) ?? {};
  } catch {
    payload = {};
  }
  payload[FIRST_LAUNCH_PLUGINS_CARD_DISMISSED_KEY] = dismissed === true;
  await writeFile4(statePath, JSON.stringify(payload), "utf8");
}
function getSessionIndexFileSignature(stats) {
  return `${String(stats.mtimeMs)}:${String(stats.size)}`;
}
async function parseThreadTitlesFromSessionIndex(sessionIndexPath) {
  const latestById = /* @__PURE__ */ new Map();
  const input = createReadStream2(sessionIndexPath, { encoding: "utf8" });
  const lines = createInterface({
    input,
    crlfDelay: Infinity
  });
  try {
    for await (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const entry = normalizeSessionIndexThreadTitle(JSON.parse(trimmed));
        if (!entry) continue;
        const previous = latestById.get(entry.id);
        if (!previous || entry.updatedAtMs >= previous.updatedAtMs) {
          latestById.set(entry.id, entry);
        }
      } catch {
      }
    }
  } finally {
    lines.close();
    input.close();
  }
  const entries = Array.from(latestById.values()).sort((first, second) => second.updatedAtMs - first.updatedAtMs);
  const titles = {};
  const order = [];
  for (const entry of entries) {
    titles[entry.id] = entry.title;
    order.push(entry.id);
  }
  return trimThreadTitleCache({ titles, order });
}
async function readThreadTitlesFromSessionIndex() {
  const sessionIndexPath = getCodexSessionIndexPath();
  try {
    const stats = await stat4(sessionIndexPath);
    const fileSignature = getSessionIndexFileSignature(stats);
    if (sessionIndexThreadTitleCacheState.fileSignature === fileSignature) {
      return sessionIndexThreadTitleCacheState.cache;
    }
    const cache = await parseThreadTitlesFromSessionIndex(sessionIndexPath);
    sessionIndexThreadTitleCacheState = { fileSignature, cache };
    return cache;
  } catch {
    sessionIndexThreadTitleCacheState = {
      fileSignature: "missing",
      cache: EMPTY_THREAD_TITLE_CACHE
    };
    return sessionIndexThreadTitleCacheState.cache;
  }
}
async function readMergedThreadTitleCache() {
  const [sessionIndexCache, persistedCache] = await Promise.all([
    readThreadTitlesFromSessionIndex(),
    readThreadTitleCache()
  ]);
  return mergeThreadTitleCaches(persistedCache, sessionIndexCache);
}
async function readWorkspaceRootsState() {
  const statePath = getCodexGlobalStatePath();
  let payload = {};
  try {
    const raw = await readFile3(statePath, "utf8");
    const parsed = JSON.parse(raw);
    payload = asRecord6(parsed) ?? {};
  } catch {
    payload = {};
  }
  return {
    order: normalizeStringArray(payload["electron-saved-workspace-roots"]),
    labels: normalizeStringRecord(payload["electron-workspace-root-labels"]),
    active: normalizeStringArray(payload["active-workspace-roots"]),
    projectOrder: normalizeStringArray(payload["project-order"]),
    remoteProjects: normalizeRemoteProjects(payload["remote-projects"])
  };
}
async function writeWorkspaceRootsState(nextState) {
  const statePath = getCodexGlobalStatePath();
  let payload = {};
  try {
    const raw = await readFile3(statePath, "utf8");
    payload = asRecord6(JSON.parse(raw)) ?? {};
  } catch {
    payload = {};
  }
  payload["electron-saved-workspace-roots"] = normalizeStringArray(nextState.order);
  payload["electron-workspace-root-labels"] = normalizeStringRecord(nextState.labels);
  payload["active-workspace-roots"] = normalizeStringArray(nextState.active);
  payload["project-order"] = normalizeStringArray(nextState.projectOrder);
  await writeFile4(statePath, JSON.stringify(payload), "utf8");
}
var workspaceRootsMutation = Promise.resolve();
function queueWorkspaceRootsMutation(mutation) {
  const run = workspaceRootsMutation.catch(() => void 0).then(mutation);
  workspaceRootsMutation = run.then(
    () => void 0,
    () => void 0
  );
  return run;
}
function prependUniqueString(value, items) {
  return [value, ...items.filter((item) => item !== value)];
}
async function updateWorkspaceRootsState(updater) {
  await queueWorkspaceRootsMutation(async () => {
    const existingState = await readWorkspaceRootsState();
    await writeWorkspaceRootsState(updater(existingState));
  });
}
async function persistWorkspaceRoot(workspaceRoot, label = "") {
  const normalizedRoot = workspaceRoot.trim();
  if (!normalizedRoot) return;
  await updateWorkspaceRootsState((existingState) => {
    const nextLabels = { ...existingState.labels };
    const trimmedLabel = label.trim();
    if (trimmedLabel.length > 0) {
      nextLabels[normalizedRoot] = trimmedLabel;
    }
    return {
      order: prependUniqueString(normalizedRoot, existingState.order),
      labels: nextLabels,
      active: prependUniqueString(normalizedRoot, existingState.active),
      projectOrder: prependUniqueString(normalizedRoot, existingState.projectOrder),
      remoteProjects: existingState.remoteProjects
    };
  });
}
async function rollbackCreatedWorktree(gitRoot, worktreeCwd, cleanupDirectory, branchName) {
  try {
    await runCommand3("git", ["worktree", "remove", "--force", worktreeCwd], { cwd: gitRoot });
  } catch {
    await rm4(worktreeCwd, { recursive: true, force: true }).catch(() => void 0);
  }
  if (cleanupDirectory && cleanupDirectory !== worktreeCwd) {
    await rm4(cleanupDirectory, { recursive: true, force: true }).catch(() => void 0);
  }
  if (branchName) {
    await runCommand3("git", ["branch", "-D", branchName], { cwd: gitRoot }).catch(() => void 0);
  }
}
function normalizeTelegramBridgeConfig(value) {
  const record = asRecord6(value);
  if (!record) return { botToken: "", chatIds: [], allowedUserIds: [] };
  const botToken = typeof record.botToken === "string" ? record.botToken.trim() : "";
  const rawChatIds = Array.isArray(record.chatIds) ? record.chatIds : [];
  const chatIds = Array.from(new Set(rawChatIds.filter((value2) => typeof value2 === "number" && Number.isFinite(value2)).map((value2) => Math.trunc(value2)))).slice(0, 50);
  const rawAllowedUserIds = Array.isArray(record.allowedUserIds) ? record.allowedUserIds : [];
  const allowAllUsers = rawAllowedUserIds.some((value2) => typeof value2 === "string" && value2.trim() === "*");
  const normalizedAllowedUserIds = Array.from(new Set(rawAllowedUserIds.map((value2) => {
    if (typeof value2 === "number" && Number.isFinite(value2)) return Math.trunc(value2);
    if (typeof value2 === "string") {
      const normalized = value2.trim().replace(/^(telegram|tg):/i, "").trim();
      if (/^-?\d+$/.test(normalized)) {
        return Number.parseInt(normalized, 10);
      }
    }
    return Number.NaN;
  }).filter((value2) => Number.isFinite(value2)))).slice(0, 100);
  const allowedUserIds = allowAllUsers ? ["*", ...normalizedAllowedUserIds] : normalizedAllowedUserIds;
  return { botToken, chatIds, allowedUserIds };
}
async function readTelegramBridgeConfig() {
  const telegramConfigPath = getTelegramBridgeConfigPath();
  try {
    const raw = await readFile3(telegramConfigPath, "utf8");
    const payload = asRecord6(JSON.parse(raw)) ?? {};
    return normalizeTelegramBridgeConfig(payload);
  } catch {
    return { botToken: "", chatIds: [], allowedUserIds: [] };
  }
}
async function writeTelegramBridgeConfig(nextState) {
  const normalized = normalizeTelegramBridgeConfig(nextState);
  const telegramConfigPath = getTelegramBridgeConfigPath();
  await writeFile4(telegramConfigPath, JSON.stringify({
    botToken: normalized.botToken,
    chatIds: normalized.chatIds,
    allowedUserIds: normalized.allowedUserIds
  }), "utf8");
}
var telegramBridgeConfigMutation = Promise.resolve();
function rememberTelegramChatId(chatId) {
  const normalizedChatId = Math.trunc(chatId);
  if (!Number.isFinite(normalizedChatId)) return Promise.resolve();
  telegramBridgeConfigMutation = telegramBridgeConfigMutation.then(async () => {
    const current = await readTelegramBridgeConfig();
    if (current.chatIds.includes(normalizedChatId)) return;
    const next = {
      ...current,
      chatIds: [normalizedChatId, ...current.chatIds].slice(0, 50)
    };
    await writeTelegramBridgeConfig(next);
  });
  return telegramBridgeConfigMutation;
}
async function readJsonBody2(req) {
  const raw = await readRawBody(req);
  if (raw.length === 0) return null;
  const text = raw.toString("utf8").trim();
  if (text.length === 0) return null;
  return JSON.parse(text);
}
async function readRawBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }
  return Buffer.concat(chunks);
}
function bufferIndexOf(buf, needle, start = 0) {
  for (let i = start; i <= buf.length - needle.length; i++) {
    let match = true;
    for (let j = 0; j < needle.length; j++) {
      if (buf[i + j] !== needle[j]) {
        match = false;
        break;
      }
    }
    if (match) return i;
  }
  return -1;
}
function handleFileUpload(req, res) {
  const chunks = [];
  req.on("data", (chunk) => chunks.push(chunk));
  req.on("end", async () => {
    try {
      const body = Buffer.concat(chunks);
      const contentType = req.headers["content-type"] ?? "";
      const boundaryMatch = contentType.match(/boundary=(.+)/i);
      if (!boundaryMatch) {
        setJson4(res, 400, { error: "Missing multipart boundary" });
        return;
      }
      const boundary = boundaryMatch[1];
      const boundaryBuf = Buffer.from(`--${boundary}`);
      const parts = [];
      let searchStart = 0;
      while (searchStart < body.length) {
        const idx = body.indexOf(boundaryBuf, searchStart);
        if (idx < 0) break;
        if (searchStart > 0) parts.push(body.subarray(searchStart, idx));
        searchStart = idx + boundaryBuf.length;
        if (body[searchStart] === 13 && body[searchStart + 1] === 10) searchStart += 2;
      }
      let fileName = "uploaded-file";
      let fileData = null;
      const headerSep = Buffer.from("\r\n\r\n");
      for (const part of parts) {
        const headerEnd = bufferIndexOf(part, headerSep);
        if (headerEnd < 0) continue;
        const headers = part.subarray(0, headerEnd).toString("utf8");
        const fnMatch = headers.match(/filename="([^"]+)"/i);
        if (!fnMatch) continue;
        fileName = fnMatch[1].replace(/[/\\]/g, "_");
        let end = part.length;
        if (end >= 2 && part[end - 2] === 13 && part[end - 1] === 10) end -= 2;
        fileData = part.subarray(headerEnd + 4, end);
        break;
      }
      if (!fileData) {
        setJson4(res, 400, { error: "No file in request" });
        return;
      }
      const uploadDir = join6(tmpdir4(), "codex-web-uploads");
      await mkdir4(uploadDir, { recursive: true });
      const destDir = await mkdtemp3(join6(uploadDir, "f-"));
      const destPath = join6(destDir, fileName);
      await writeFile4(destPath, fileData);
      setJson4(res, 200, { path: destPath });
    } catch (err) {
      setJson4(res, 500, { error: getErrorMessage6(err, "Upload failed") });
    }
  });
  req.on("error", (err) => {
    setJson4(res, 500, { error: getErrorMessage6(err, "Upload stream error") });
  });
}
function httpPost(url, headers, body) {
  const doRequest = url.startsWith("http://") ? httpRequest2 : httpsRequest2;
  return new Promise((resolve4, reject) => {
    const req = doRequest(url, { method: "POST", headers }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve4({ status: res.statusCode ?? 500, body: Buffer.concat(chunks).toString("utf8") }));
      res.on("error", reject);
    });
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}
var curlImpersonateAvailable = null;
function curlImpersonatePost(url, headers, body) {
  return new Promise((resolve4, reject) => {
    const args = ["-s", "-w", "\n%{http_code}", "-X", "POST", url];
    for (const [k, v] of Object.entries(headers)) {
      if (k.toLowerCase() === "content-length") continue;
      args.push("-H", `${k}: ${String(v)}`);
    }
    args.push("--data-binary", "@-");
    const proc = spawn4("curl-impersonate-chrome", args, {
      env: { ...process.env, CURL_IMPERSONATE: "chrome116" },
      stdio: ["pipe", "pipe", "pipe"]
    });
    const chunks = [];
    proc.stdout.on("data", (c) => chunks.push(c));
    proc.on("error", (e) => {
      curlImpersonateAvailable = false;
      reject(e);
    });
    proc.on("close", (code) => {
      const raw = Buffer.concat(chunks).toString("utf8");
      const lastNewline = raw.lastIndexOf("\n");
      const statusStr = lastNewline >= 0 ? raw.slice(lastNewline + 1).trim() : "";
      const responseBody = lastNewline >= 0 ? raw.slice(0, lastNewline) : raw;
      const status = parseInt(statusStr, 10) || (code === 0 ? 200 : 500);
      curlImpersonateAvailable = true;
      resolve4({ status, body: responseBody });
    });
    proc.stdin.write(body);
    proc.stdin.end();
  });
}
async function proxyTranscribe(body, contentType, authToken, accountId) {
  const chatgptHeaders = {
    "Content-Type": contentType,
    "Content-Length": body.length,
    Authorization: `Bearer ${authToken}`,
    originator: "Codex Desktop",
    "User-Agent": `Codex Desktop/0.1.0 (${process.platform}; ${process.arch})`
  };
  if (accountId) chatgptHeaders["ChatGPT-Account-Id"] = accountId;
  const postFn = curlImpersonateAvailable !== false ? curlImpersonatePost : httpPost;
  let result;
  try {
    result = await postFn("https://chatgpt.com/backend-api/transcribe", chatgptHeaders, body);
  } catch {
    result = await httpPost("https://chatgpt.com/backend-api/transcribe", chatgptHeaders, body);
  }
  if (result.status === 403 && result.body.includes("cf_chl")) {
    if (curlImpersonateAvailable !== false && postFn !== curlImpersonatePost) {
      try {
        const ciResult = await curlImpersonatePost("https://chatgpt.com/backend-api/transcribe", chatgptHeaders, body);
        if (ciResult.status !== 403) return ciResult;
      } catch {
      }
    }
    return { status: 503, body: JSON.stringify({ error: "Transcription blocked by Cloudflare. Install curl-impersonate-chrome." }) };
  }
  return result;
}
function parseConnectorLogoUrl(rawUrl) {
  const trimmed = rawUrl.trim();
  if (!trimmed.startsWith("connectors://")) return null;
  const rest = trimmed.slice("connectors://".length);
  const connectorId = (rest.split(/[/?#]/u)[0] ?? "").trim();
  if (!connectorId) return null;
  const query = rest.includes("?") ? rest.slice(rest.indexOf("?") + 1).split("#")[0] ?? "" : "";
  const theme = new URLSearchParams(query).get("theme")?.toLowerCase() === "dark" ? "dark" : "light";
  return { connectorId, theme };
}
async function fetchConnectorLogo(rawUrl) {
  const parsed = parseConnectorLogoUrl(rawUrl);
  if (!parsed) throw new Error("Unsupported connector logo URL");
  const auth = await readCodexAuth();
  if (!auth) throw new Error("No auth token available for connector logo");
  const endpoint = `https://chatgpt.com/backend-api/aip/connectors/${encodeURIComponent(parsed.connectorId)}/logo?theme=${parsed.theme}`;
  const response = await fetch(endpoint, {
    headers: {
      Authorization: `Bearer ${auth.accessToken}`,
      originator: "Codex Desktop",
      "User-Agent": `Codex Desktop/0.1.0 (${process.platform}; ${process.arch})`,
      ...auth.accountId ? { "ChatGPT-Account-Id": auth.accountId } : {}
    },
    signal: AbortSignal.timeout(1e4)
  });
  if (!response.ok) throw new Error(`Connector logo fetch failed (${response.status})`);
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = asRecord6(await response.json());
    const body = asRecord6(payload?.body);
    const base64 = readNonEmptyString(body?.base64);
    const nestedContentType = readNonEmptyString(body?.contentType) ?? readNonEmptyString(body?.content_type);
    if (!base64 || !nestedContentType) throw new Error("Connector logo response was missing image data");
    return { contentType: nestedContentType, body: Buffer.from(base64, "base64") };
  }
  return {
    contentType: contentType || "image/png",
    body: Buffer.from(await response.arrayBuffer())
  };
}
var STREAM_EVENT_BUFFER_LIMIT = 400;
var MERGEABLE_ITEM_TYPES = /* @__PURE__ */ new Set([
  "commandExecution",
  "fileChange"
]);
var AppServerProcess = class {
  constructor() {
    this.process = null;
    this.initialized = false;
    this.initializePromise = null;
    this.readBuffer = "";
    this.nextId = 1;
    this.stopping = false;
    this.pending = /* @__PURE__ */ new Map();
    this.notificationListeners = /* @__PURE__ */ new Set();
    this.pendingServerRequests = /* @__PURE__ */ new Map();
    this.streamEventsByThreadId = /* @__PURE__ */ new Map();
    this.lastThreadReadSnapshotByThreadId = /* @__PURE__ */ new Map();
    this.threadTurnPageReadCacheByThreadId = /* @__PURE__ */ new Map();
    this.threadTurnPageReadPromiseByThreadId = /* @__PURE__ */ new Map();
    this.capturedItemsByThreadId = /* @__PURE__ */ new Map();
    this.liveStateCache = /* @__PURE__ */ new Map();
    this.chatgptAuthRefreshPromise = null;
    this.activeConfigSignature = "";
  }
  getCodexCommand() {
    const codexCommand = resolveCodexCommand();
    if (!codexCommand) {
      throw new Error("Codex CLI is not available. Install @openai/codex or set CODEXUI_CODEX_COMMAND.");
    }
    return codexCommand;
  }
  buildAppServerConfig() {
    const args = buildAppServerArgs();
    let extraEnv = {};
    const serverPort = parseInt(process.env.CODEXUI_SERVER_PORT ?? "", 10) || void 0;
    args.push(...getProviderCompatibilityConfigArgs(serverPort));
    const statePath = join6(getCodexHomeDir3(), FREE_MODE_STATE_FILE);
    try {
      const state = ensureDefaultFreeModeStateForMissingAuthSync(statePath);
      if (state) {
        args.push(...getFreeModeConfigArgs(state, serverPort));
        extraEnv = getFreeModeEnvVars(state);
      }
    } catch {
    }
    return { args, env: extraEnv };
  }
  getAppServerConfigSignature(config) {
    return JSON.stringify({
      args: config.args,
      env: Object.keys(config.env).sort().map((key) => [key, config.env[key]])
    });
  }
  disposeIfConfigChanged() {
    if (!this.process) return;
    const config = this.buildAppServerConfig();
    const nextSignature = this.getAppServerConfigSignature(config);
    if (this.activeConfigSignature === nextSignature) return;
    this.dispose();
  }
  start() {
    if (this.process) return;
    this.stopping = false;
    const config = this.buildAppServerConfig();
    this.activeConfigSignature = this.getAppServerConfigSignature(config);
    const invocation = getSpawnInvocation(this.getCodexCommand(), config.args);
    const spawnEnv = Object.keys(config.env).length > 0 ? { ...process.env, ...config.env } : void 0;
    const proc = spawn4(invocation.command, invocation.args, { stdio: ["pipe", "pipe", "pipe"], ...spawnEnv ? { env: spawnEnv } : {} });
    this.process = proc;
    proc.stdout.setEncoding("utf8");
    proc.stdout.on("data", (chunk) => {
      this.readBuffer += chunk;
      let lineEnd = this.readBuffer.indexOf("\n");
      while (lineEnd !== -1) {
        const line = this.readBuffer.slice(0, lineEnd).trim();
        this.readBuffer = this.readBuffer.slice(lineEnd + 1);
        if (line.length > 0) {
          this.handleLine(line);
        }
        lineEnd = this.readBuffer.indexOf("\n");
      }
    });
    proc.stderr.setEncoding("utf8");
    proc.stderr.on("data", () => {
    });
    proc.on("exit", () => {
      if (this.process !== proc) {
        return;
      }
      const failure = new Error(this.stopping ? "codex app-server stopped" : "codex app-server exited unexpectedly");
      for (const request of this.pending.values()) {
        request.reject(failure);
      }
      this.pending.clear();
      this.pendingServerRequests.clear();
      this.process = null;
      this.initialized = false;
      this.initializePromise = null;
      this.readBuffer = "";
    });
  }
  sendLine(payload) {
    if (!this.process) {
      throw new Error("codex app-server is not running");
    }
    this.process.stdin.write(`${JSON.stringify(payload)}
`);
  }
  handleLine(line) {
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      return;
    }
    if (typeof message.id === "number" && this.pending.has(message.id)) {
      const pendingRequest = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (!pendingRequest) return;
      if (message.error) {
        pendingRequest.reject(new Error(message.error.message));
      } else {
        pendingRequest.resolve(message.result);
      }
      return;
    }
    if (typeof message.method === "string" && typeof message.id !== "number") {
      this.emitNotification({
        method: message.method,
        params: message.params ?? null
      });
      return;
    }
    if (typeof message.id === "number" && typeof message.method === "string") {
      this.handleServerRequest(message.id, message.method, message.params ?? null);
    }
  }
  emitNotification(notification) {
    this.recordStreamEvent(notification);
    this.captureItemFromNotification(notification);
    const nThreadId = this.extractThreadIdFromParams(notification.params);
    if (nThreadId) {
      this.invalidateLiveStateCache(nThreadId);
      this.threadTurnPageReadCacheByThreadId.delete(nThreadId);
    }
    for (const listener of this.notificationListeners) {
      listener(notification);
    }
  }
  extractThreadIdFromParams(params) {
    const record = asRecord6(params);
    if (!record) return "";
    const threadId = (typeof record.threadId === "string" ? record.threadId : "") || (typeof record.thread_id === "string" ? record.thread_id : "") || (typeof record.conversationId === "string" ? record.conversationId : "") || (typeof record.conversation_id === "string" ? record.conversation_id : "");
    if (threadId) return threadId;
    const thread = asRecord6(record.thread);
    if (thread && typeof thread.id === "string") return thread.id;
    const turn = asRecord6(record.turn);
    if (turn) {
      const turnThreadId = (typeof turn.threadId === "string" ? turn.threadId : "") || (typeof turn.thread_id === "string" ? turn.thread_id : "");
      if (turnThreadId) return turnThreadId;
    }
    return "";
  }
  recordStreamEvent(notification) {
    const threadId = this.extractThreadIdFromParams(notification.params);
    if (!threadId) return;
    const frame = {
      method: notification.method,
      params: notification.params,
      atIso: (/* @__PURE__ */ new Date()).toISOString()
    };
    let buffer = this.streamEventsByThreadId.get(threadId);
    if (!buffer) {
      buffer = [];
      this.streamEventsByThreadId.set(threadId, buffer);
    }
    buffer.push(frame);
    if (buffer.length > STREAM_EVENT_BUFFER_LIMIT) {
      buffer.splice(0, buffer.length - STREAM_EVENT_BUFFER_LIMIT);
    }
  }
  getStreamEvents(threadId, limit) {
    const buffer = this.streamEventsByThreadId.get(threadId);
    if (!buffer || buffer.length === 0) return [];
    return buffer.slice(-limit);
  }
  storeThreadReadSnapshot(threadId, snapshot) {
    this.lastThreadReadSnapshotByThreadId.set(threadId, snapshot);
    this.threadTurnPageReadCacheByThreadId.delete(threadId);
  }
  getLastThreadReadSnapshot(threadId) {
    return this.lastThreadReadSnapshotByThreadId.get(threadId) ?? null;
  }
  async readThreadForTurnPage(threadId) {
    const now = Date.now();
    const cached = this.threadTurnPageReadCacheByThreadId.get(threadId);
    if (cached && cached.expiresAt > now) return cached.result;
    if (cached) this.threadTurnPageReadCacheByThreadId.delete(threadId);
    const pending = this.threadTurnPageReadPromiseByThreadId.get(threadId);
    if (pending) return pending;
    const promise = this.rpc("thread/read", {
      threadId,
      includeTurns: true
    }).then((result) => {
      this.threadTurnPageReadCacheByThreadId.set(threadId, {
        result,
        expiresAt: Date.now() + THREAD_TURN_PAGE_READ_CACHE_TTL_MS
      });
      return result;
    }).finally(() => {
      this.threadTurnPageReadPromiseByThreadId.delete(threadId);
    });
    this.threadTurnPageReadPromiseByThreadId.set(threadId, promise);
    return promise;
  }
  cacheLiveState(threadId, data, turnCount, sessionSize) {
    this.liveStateCache.set(threadId, { data, turnCount, sessionSize });
  }
  getCachedLiveState(threadId, turnCount, sessionSize) {
    const cached = this.liveStateCache.get(threadId);
    if (!cached) return null;
    if (cached.turnCount !== turnCount || cached.sessionSize !== sessionSize) return null;
    return cached.data;
  }
  invalidateLiveStateCache(threadId) {
    this.liveStateCache.delete(threadId);
  }
  captureItemFromNotification(notification) {
    if (notification.method !== "item/started" && notification.method !== "item/completed") return;
    const params = asRecord6(notification.params);
    if (!params) return;
    const item = asRecord6(params.item);
    if (!item) return;
    const itemType = typeof item.type === "string" ? item.type : "";
    if (!MERGEABLE_ITEM_TYPES.has(itemType)) return;
    const itemId = typeof item.id === "string" ? item.id : "";
    if (!itemId) return;
    const threadId = this.extractThreadIdFromParams(params);
    if (!threadId) return;
    const turnId = (typeof params.turnId === "string" ? params.turnId : "") || (typeof params.turn_id === "string" ? params.turn_id : "");
    if (!turnId) return;
    let threadItems = this.capturedItemsByThreadId.get(threadId);
    if (!threadItems) {
      threadItems = /* @__PURE__ */ new Map();
      this.capturedItemsByThreadId.set(threadId, threadItems);
    }
    const isCompleted = notification.method === "item/completed";
    const existing = threadItems.get(itemId);
    if (existing && existing.completed && !isCompleted) return;
    threadItems.set(itemId, {
      id: itemId,
      type: itemType,
      turnId,
      data: item,
      completed: isCompleted
    });
  }
  mergeItemsIntoTurns(threadId, turns) {
    const capturedMap = this.capturedItemsByThreadId.get(threadId);
    if (!capturedMap || capturedMap.size === 0) return turns;
    const itemsByTurnId = /* @__PURE__ */ new Map();
    for (const captured of capturedMap.values()) {
      let group = itemsByTurnId.get(captured.turnId);
      if (!group) {
        group = [];
        itemsByTurnId.set(captured.turnId, group);
      }
      group.push(captured);
    }
    return turns.map((turn) => {
      const turnRecord = asRecord6(turn);
      if (!turnRecord) return turn;
      const turnId = typeof turnRecord.id === "string" ? turnRecord.id : "";
      if (!turnId) return turn;
      const captured = itemsByTurnId.get(turnId);
      if (!captured || captured.length === 0) return turn;
      const existingItems = Array.isArray(turnRecord.items) ? turnRecord.items : [];
      const existingIds = new Set(existingItems.map((it) => typeof it.id === "string" ? it.id : "").filter(Boolean));
      const newItems = captured.filter((c) => !existingIds.has(c.id)).map((c) => c.data);
      if (newItems.length === 0) return turn;
      return {
        ...turnRecord,
        items: [...existingItems, ...newItems]
      };
    });
  }
  sendServerRequestReply(requestId, reply) {
    if (reply.error) {
      this.sendLine({
        jsonrpc: "2.0",
        id: requestId,
        error: reply.error
      });
      return;
    }
    this.sendLine({
      jsonrpc: "2.0",
      id: requestId,
      result: reply.result ?? {}
    });
  }
  resolvePendingServerRequest(requestId, reply) {
    const pendingRequest = this.pendingServerRequests.get(requestId);
    if (!pendingRequest) {
      throw new Error(`No pending server request found for id ${String(requestId)}`);
    }
    this.pendingServerRequests.delete(requestId);
    this.sendServerRequestReply(requestId, reply);
    const requestParams = asRecord6(pendingRequest.params);
    const threadId = typeof requestParams?.threadId === "string" && requestParams.threadId.length > 0 ? requestParams.threadId : "";
    this.emitNotification({
      method: "server/request/resolved",
      params: {
        id: requestId,
        method: pendingRequest.method,
        threadId,
        mode: "manual",
        resolvedAtIso: (/* @__PURE__ */ new Date()).toISOString()
      }
    });
  }
  async refreshChatgptAuthTokens(params) {
    if (!this.chatgptAuthRefreshPromise) {
      this.chatgptAuthRefreshPromise = refreshChatgptAuthTokensForExternalAuth(params).finally(() => {
        this.chatgptAuthRefreshPromise = null;
      });
    }
    return await this.chatgptAuthRefreshPromise;
  }
  async handleChatgptAuthTokensRefreshRequest(requestId, params) {
    const requestParams = asRecord6(params);
    const previousAccountId = readNonEmptyString(requestParams?.previousAccountId ?? requestParams?.previous_account_id);
    try {
      const result = await this.refreshChatgptAuthTokens({
        reason: readNonEmptyString(requestParams?.reason) || void 0,
        previousAccountId: previousAccountId || void 0
      });
      this.sendServerRequestReply(requestId, { result });
      this.emitNotification({
        method: "server/request/resolved",
        params: {
          id: requestId,
          method: "account/chatgptAuthTokens/refresh",
          mode: "automatic",
          resolvedAtIso: (/* @__PURE__ */ new Date()).toISOString()
        }
      });
    } catch (error) {
      this.sendServerRequestReply(requestId, {
        error: {
          code: -32001,
          message: getErrorMessage6(error, "Failed to refresh ChatGPT auth tokens")
        }
      });
    }
  }
  handleServerRequest(requestId, method, params) {
    if (method === "account/chatgptAuthTokens/refresh") {
      void this.handleChatgptAuthTokensRefreshRequest(requestId, params);
      return;
    }
    const pendingRequest = {
      id: requestId,
      method,
      params,
      receivedAtIso: (/* @__PURE__ */ new Date()).toISOString()
    };
    this.pendingServerRequests.set(requestId, pendingRequest);
    this.emitNotification({
      method: "server/request",
      params: pendingRequest
    });
  }
  async call(method, params) {
    this.start();
    const id = this.nextId++;
    return new Promise((resolve4, reject) => {
      this.pending.set(id, { resolve: resolve4, reject });
      this.sendLine({
        jsonrpc: "2.0",
        id,
        method,
        params
      });
    });
  }
  async ensureInitialized() {
    if (this.initialized) return;
    if (this.initializePromise) {
      await this.initializePromise;
      return;
    }
    this.initializePromise = this.call("initialize", {
      clientInfo: {
        name: "codex-web-local",
        version: "0.1.0"
      },
      capabilities: {
        experimentalApi: true
      }
    }).then(() => {
      this.sendLine({
        jsonrpc: "2.0",
        method: "initialized"
      });
      this.initialized = true;
    }).finally(() => {
      this.initializePromise = null;
    });
    await this.initializePromise;
  }
  async rpc(method, params) {
    this.disposeIfConfigChanged();
    await this.ensureInitialized();
    return this.call(method, params);
  }
  onNotification(listener) {
    this.notificationListeners.add(listener);
    return () => {
      this.notificationListeners.delete(listener);
    };
  }
  async respondToServerRequest(payload) {
    await this.ensureInitialized();
    const body = asRecord6(payload);
    if (!body) {
      throw new Error("Invalid response payload: expected object");
    }
    const id = body.id;
    if (typeof id !== "number" || !Number.isInteger(id)) {
      throw new Error('Invalid response payload: "id" must be an integer');
    }
    const rawError = asRecord6(body.error);
    if (rawError) {
      const message = typeof rawError.message === "string" && rawError.message.trim().length > 0 ? rawError.message.trim() : "Server request rejected by client";
      const code = typeof rawError.code === "number" && Number.isFinite(rawError.code) ? Math.trunc(rawError.code) : -32e3;
      this.resolvePendingServerRequest(id, { error: { code, message } });
      return;
    }
    if (!("result" in body)) {
      throw new Error('Invalid response payload: expected "result" or "error"');
    }
    this.resolvePendingServerRequest(id, { result: body.result });
  }
  listPendingServerRequests() {
    return Array.from(this.pendingServerRequests.values());
  }
  dispose() {
    if (!this.process) return;
    const proc = this.process;
    this.stopping = true;
    this.process = null;
    this.initialized = false;
    this.initializePromise = null;
    this.activeConfigSignature = "";
    this.readBuffer = "";
    const failure = new Error("codex app-server stopped");
    for (const request of this.pending.values()) {
      request.reject(failure);
    }
    this.pending.clear();
    this.pendingServerRequests.clear();
    try {
      proc.stdin.end();
    } catch {
    }
    try {
      proc.kill("SIGTERM");
    } catch {
    }
    const forceKillTimer = setTimeout(() => {
      if (!proc.killed) {
        try {
          proc.kill("SIGKILL");
        } catch {
        }
      }
    }, 1500);
    forceKillTimer.unref();
  }
};
var BackendQueueProcessor = class {
  constructor(appServer) {
    this.appServer = appServer;
    this.processingThreadIds = /* @__PURE__ */ new Set();
    this.queueDrainTimersByThreadId = /* @__PURE__ */ new Map();
    this.queueDrainDueAtByThreadId = /* @__PURE__ */ new Map();
    this.unsubscribe = appServer.onNotification((notification) => {
      if (!isTurnCompletedNotification(notification)) return;
      const threadId = extractThreadIdFromNotificationParams(notification.params);
      if (!threadId) return;
      void this.processThreadQueue(threadId);
    });
    void this.scheduleAllQueuedThreads(1e3);
  }
  dispose() {
    this.unsubscribe();
    for (const timer of this.queueDrainTimersByThreadId.values()) {
      clearTimeout(timer);
    }
    this.queueDrainTimersByThreadId.clear();
    this.queueDrainDueAtByThreadId.clear();
    this.processingThreadIds.clear();
  }
  async scheduleAllQueuedThreads(delayMs = 0) {
    try {
      const state = await readThreadQueueState();
      for (const threadId of Object.keys(state)) {
        this.scheduleThreadQueueDrain(threadId, delayMs);
      }
    } catch {
    }
  }
  scheduleThreadQueueDrain(threadId, delayMs = 5e3) {
    if (!threadId) return;
    const normalizedDelayMs = Math.max(0, delayMs);
    const nextDueAt = Date.now() + normalizedDelayMs;
    const existingDueAt = this.queueDrainDueAtByThreadId.get(threadId);
    const existingTimer = this.queueDrainTimersByThreadId.get(threadId);
    if (existingTimer) {
      if (existingDueAt !== void 0 && existingDueAt <= nextDueAt) return;
      clearTimeout(existingTimer);
      this.queueDrainTimersByThreadId.delete(threadId);
      this.queueDrainDueAtByThreadId.delete(threadId);
    }
    const timer = setTimeout(() => {
      this.queueDrainTimersByThreadId.delete(threadId);
      this.queueDrainDueAtByThreadId.delete(threadId);
      void this.processThreadQueue(threadId);
    }, normalizedDelayMs);
    timer.unref?.();
    this.queueDrainTimersByThreadId.set(threadId, timer);
    this.queueDrainDueAtByThreadId.set(threadId, nextDueAt);
  }
  async processThreadQueue(threadId) {
    if (this.processingThreadIds.has(threadId)) return;
    this.processingThreadIds.add(threadId);
    try {
      const canStart = await this.canStartQueuedTurn(threadId);
      if (!canStart) {
        if (await this.hasQueuedTurns(threadId)) {
          this.scheduleThreadQueueDrain(threadId);
        }
        return;
      }
      const next = await this.popNextQueuedTurn(threadId);
      if (!next) return;
      try {
        await this.startQueuedTurn(next);
        if (await this.hasQueuedTurns(threadId)) {
          this.scheduleThreadQueueDrain(threadId);
        }
      } catch {
        await this.restoreQueuedTurn(next);
        this.scheduleThreadQueueDrain(threadId);
      }
    } catch {
      this.scheduleThreadQueueDrain(threadId);
    } finally {
      this.processingThreadIds.delete(threadId);
    }
  }
  async hasQueuedTurns(threadId) {
    const state = await readThreadQueueState();
    const queue = state[threadId];
    return Array.isArray(queue) && queue.length > 0;
  }
  async canStartQueuedTurn(threadId) {
    const response = asRecord6(await this.appServer.rpc("thread/read", { threadId, includeTurns: true }));
    const thread = asRecord6(response?.thread);
    if (!thread) return false;
    const status = asRecord6(thread.status);
    const statusType = readNonEmptyString(status?.type);
    if (statusType === "inProgress" || statusType === "running" || statusType === "active") return false;
    const turns = Array.isArray(thread.turns) ? thread.turns : [];
    return !turns.some((turn) => readNonEmptyString(asRecord6(turn)?.status) === "inProgress");
  }
  async popNextQueuedTurn(threadId) {
    return withThreadQueueStateUpdate((state) => {
      const queue = state[threadId];
      if (!queue || queue.length === 0) {
        return { nextState: state, result: null };
      }
      const [message, ...rest] = queue;
      const nextState = { ...state };
      if (rest.length > 0) {
        nextState[threadId] = rest;
      } else {
        delete nextState[threadId];
      }
      return { nextState, result: { threadId, message } };
    });
  }
  async restoreQueuedTurn(turn) {
    await withThreadQueueStateUpdate((state) => {
      const queue = state[turn.threadId] ?? [];
      return {
        nextState: {
          ...state,
          [turn.threadId]: [turn.message, ...queue]
        },
        result: void 0
      };
    });
  }
  async resolveCollaborationModeSettings(mode) {
    let currentConfig = null;
    try {
      const configPayload = asRecord6(await this.appServer.rpc("config/read", {}));
      currentConfig = asRecord6(configPayload?.config);
    } catch {
      currentConfig = null;
    }
    const configuredModel = readNonEmptyString(currentConfig?.model);
    if (configuredModel) {
      return {
        model: configuredModel,
        reasoningEffort: normalizeCollaborationModeReasoningEffort(normalizeReasoningEffort(currentConfig?.model_reasoning_effort))
      };
    }
    try {
      const modelsPayload = asRecord6(await this.appServer.rpc("model/list", {}));
      const models = Array.isArray(modelsPayload?.data) ? modelsPayload.data : [];
      for (const row of models) {
        const record = asRecord6(row);
        const candidate = readNonEmptyString(record?.id) || readNonEmptyString(record?.model);
        if (candidate) {
          return {
            model: candidate,
            reasoningEffort: normalizeCollaborationModeReasoningEffort(normalizeReasoningEffort(currentConfig?.model_reasoning_effort))
          };
        }
      }
    } catch {
    }
    throw new Error(`${mode === "plan" ? "Plan" : "Default"} mode requires an available model.`);
  }
  async buildQueuedTurnParams(turn) {
    const localImageAttachments = [];
    for (const imageUrl of turn.message.imageUrls) {
      const localImagePath = extractLocalImagePathFromUrl(imageUrl.trim());
      if (!localImagePath) continue;
      localImageAttachments.push({
        label: fileNameFromPath(localImagePath),
        path: localImagePath,
        fsPath: localImagePath
      });
    }
    const allFileAttachments = [...turn.message.fileAttachments, ...localImageAttachments];
    const dedupedFileAttachments = allFileAttachments.filter((entry, index) => allFileAttachments.findIndex((candidate) => candidate.fsPath === entry.fsPath) === index);
    const input = [{
      type: "text",
      text: buildTextWithAttachments(turn.message.text, dedupedFileAttachments)
    }];
    for (const imageUrl of turn.message.imageUrls) {
      const normalizedUrl = imageUrl.trim();
      if (!normalizedUrl) continue;
      const localImagePath = extractLocalImagePathFromUrl(normalizedUrl);
      if (localImagePath) {
        input.push({ type: "localImage", path: localImagePath });
      } else {
        input.push({ type: "image", url: normalizedUrl, image_url: normalizedUrl });
      }
    }
    for (const skill of turn.message.skills) {
      input.push({ type: "skill", name: skill.name, path: skill.path });
    }
    const params = {
      threadId: turn.threadId,
      input
    };
    if (dedupedFileAttachments.length > 0) {
      params.attachments = dedupedFileAttachments.map((f) => ({ label: f.label, path: f.path, fsPath: f.fsPath }));
    }
    try {
      const settings = await this.resolveCollaborationModeSettings(turn.message.collaborationMode);
      params.collaborationMode = {
        mode: turn.message.collaborationMode,
        settings: {
          model: settings.model,
          reasoning_effort: settings.reasoningEffort,
          developer_instructions: null
        }
      };
    } catch {
    }
    return params;
  }
  async startQueuedTurn(turn) {
    await this.appServer.rpc("thread/resume", { threadId: turn.threadId });
    await this.appServer.rpc("turn/start", await this.buildQueuedTurnParams(turn));
  }
};
var MethodCatalog = class {
  constructor() {
    this.methodCache = null;
    this.notificationCache = null;
  }
  async runGenerateSchemaCommand(outDir) {
    await new Promise((resolve4, reject) => {
      const codexCommand = resolveCodexCommand();
      if (!codexCommand) {
        reject(new Error("Codex CLI is not available. Install @openai/codex or set CODEXUI_CODEX_COMMAND."));
        return;
      }
      const invocation = getSpawnInvocation(codexCommand, ["app-server", "generate-json-schema", "--out", outDir]);
      const process2 = spawn4(invocation.command, invocation.args, {
        stdio: ["ignore", "ignore", "pipe"]
      });
      let stderr = "";
      process2.stderr.setEncoding("utf8");
      process2.stderr.on("data", (chunk) => {
        stderr += chunk;
      });
      process2.on("error", reject);
      process2.on("exit", (code) => {
        if (code === 0) {
          resolve4();
          return;
        }
        reject(new Error(stderr.trim() || `generate-json-schema exited with code ${String(code)}`));
      });
    });
  }
  extractMethodsFromClientRequest(payload) {
    const root = asRecord6(payload);
    const oneOf = Array.isArray(root?.oneOf) ? root.oneOf : [];
    const methods = /* @__PURE__ */ new Set();
    for (const entry of oneOf) {
      const row = asRecord6(entry);
      const properties = asRecord6(row?.properties);
      const methodDef = asRecord6(properties?.method);
      const methodEnum = Array.isArray(methodDef?.enum) ? methodDef.enum : [];
      for (const item of methodEnum) {
        if (typeof item === "string" && item.length > 0) {
          methods.add(item);
        }
      }
    }
    return Array.from(methods).sort((a, b) => a.localeCompare(b));
  }
  extractMethodsFromServerNotification(payload) {
    const root = asRecord6(payload);
    const oneOf = Array.isArray(root?.oneOf) ? root.oneOf : [];
    const methods = /* @__PURE__ */ new Set();
    for (const entry of oneOf) {
      const row = asRecord6(entry);
      const properties = asRecord6(row?.properties);
      const methodDef = asRecord6(properties?.method);
      const methodEnum = Array.isArray(methodDef?.enum) ? methodDef.enum : [];
      for (const item of methodEnum) {
        if (typeof item === "string" && item.length > 0) {
          methods.add(item);
        }
      }
    }
    return Array.from(methods).sort((a, b) => a.localeCompare(b));
  }
  async listMethods() {
    if (this.methodCache) {
      return this.methodCache;
    }
    const outDir = await mkdtemp3(join6(tmpdir4(), "codex-web-local-schema-"));
    await this.runGenerateSchemaCommand(outDir);
    const clientRequestPath = join6(outDir, "ClientRequest.json");
    const raw = await readFile3(clientRequestPath, "utf8");
    const parsed = JSON.parse(raw);
    const methods = this.extractMethodsFromClientRequest(parsed);
    this.methodCache = methods;
    return methods;
  }
  async listNotificationMethods() {
    if (this.notificationCache) {
      return this.notificationCache;
    }
    const outDir = await mkdtemp3(join6(tmpdir4(), "codex-web-local-schema-"));
    await this.runGenerateSchemaCommand(outDir);
    const serverNotificationPath = join6(outDir, "ServerNotification.json");
    const raw = await readFile3(serverNotificationPath, "utf8");
    const parsed = JSON.parse(raw);
    const methods = this.extractMethodsFromServerNotification(parsed);
    this.notificationCache = methods;
    return methods;
  }
};
var SHARED_BRIDGE_KEY = "__codexRemoteSharedBridge__";
var SHARED_BRIDGE_VERSION = "experimental-api-v2";
function getSharedBridgeState() {
  const globalScope = globalThis;
  const existing = globalScope[SHARED_BRIDGE_KEY];
  if (existing) {
    if (existing.version === SHARED_BRIDGE_VERSION && existing.terminalManager) {
      return existing;
    }
    existing.appServer.dispose();
    existing.backendQueueProcessor?.dispose();
    existing.terminalManager?.dispose();
  }
  const appServer = new AppServerProcess();
  const terminalManager = new ThreadTerminalManager();
  const backendQueueProcessor = new BackendQueueProcessor(appServer);
  const created = {
    version: SHARED_BRIDGE_VERSION,
    appServer,
    terminalManager,
    methodCatalog: new MethodCatalog(),
    backendQueueProcessor,
    telegramBridge: new TelegramThreadBridge(appServer, {
      onChatSeen: (chatId) => {
        void rememberTelegramChatId(chatId).catch(() => {
        });
      }
    })
  };
  globalScope[SHARED_BRIDGE_KEY] = created;
  return created;
}
async function loadAllThreadsForSearch(appServer) {
  const threads = [];
  let cursor = null;
  do {
    const response = asRecord6(await appServer.rpc("thread/list", {
      archived: false,
      limit: 100,
      sortKey: "updated_at",
      modelProviders: [],
      cursor
    }));
    const data = Array.isArray(response?.data) ? response.data : [];
    for (const row of data) {
      const record = asRecord6(row);
      const id = typeof record?.id === "string" ? record.id : "";
      if (!id) continue;
      const title = typeof record?.name === "string" && record.name.trim().length > 0 ? record.name.trim() : typeof record?.preview === "string" && record.preview.trim().length > 0 ? record.preview.trim() : "Untitled thread";
      const preview = typeof record?.preview === "string" ? record.preview : "";
      threads.push({ id, title, preview });
    }
    cursor = typeof response?.nextCursor === "string" && response.nextCursor.length > 0 ? response.nextCursor : null;
  } while (cursor);
  const docs = threads.map((thread) => {
    const searchableText = [thread.title, thread.preview].filter(Boolean).join("\n");
    return {
      id: thread.id,
      title: thread.title,
      preview: thread.preview,
      messageText: "",
      searchableText
    };
  });
  const docsById = new Map(docs.map((doc) => [doc.id, doc]));
  const fullTextThreads = threads.slice(0, THREAD_SEARCH_FULL_TEXT_THREAD_LIMIT);
  const concurrency = 4;
  for (let offset = 0; offset < fullTextThreads.length; offset += concurrency) {
    const batch = fullTextThreads.slice(offset, offset + concurrency);
    const loaded = await Promise.all(batch.map(async (thread) => {
      try {
        const readResponse = await appServer.rpc("thread/read", {
          threadId: thread.id,
          includeTurns: true
        });
        const messageText = extractThreadMessageText(readResponse);
        const searchableText = [thread.title, thread.preview, messageText].filter(Boolean).join("\n");
        return [thread.id, {
          id: thread.id,
          title: thread.title,
          preview: thread.preview,
          messageText,
          searchableText
        }];
      } catch {
        return null;
      }
    }));
    for (const row of loaded) {
      if (!row) continue;
      docsById.set(row[0], row[1]);
    }
  }
  return Array.from(docsById.values());
}
async function buildThreadSearchIndex(appServer) {
  const docs = await loadAllThreadsForSearch(appServer);
  const docsById = new Map(docs.map((doc) => [doc.id, doc]));
  return { docsById };
}
function createCodexBridgeMiddleware() {
  const { appServer, terminalManager, methodCatalog, telegramBridge, backendQueueProcessor } = getSharedBridgeState();
  let threadSearchIndex = null;
  let threadSearchIndexPromise = null;
  async function getThreadSearchIndex() {
    if (threadSearchIndex) return threadSearchIndex;
    if (!threadSearchIndexPromise) {
      threadSearchIndexPromise = buildThreadSearchIndex(appServer).then((index) => {
        threadSearchIndex = index;
        return index;
      }).finally(() => {
        threadSearchIndexPromise = null;
      });
    }
    return threadSearchIndexPromise;
  }
  void initializeSkillsSyncOnStartup(appServer);
  void readTelegramBridgeConfig().then((config) => {
    if (!config.botToken) return;
    telegramBridge.configureToken(config.botToken);
    telegramBridge.configureAllowedUserIds(config.allowedUserIds);
    telegramBridge.start();
  }).catch(() => {
  });
  const middleware = async (req, res, next) => {
    const requestStartNs = process.hrtime.bigint();
    const rawUrl = req.url ?? "";
    const parsedRequestUrl = rawUrl ? new URL(rawUrl, "http://localhost") : null;
    const requestPath = parsedRequestUrl?.pathname ?? "";
    const requestMethod = req.method ?? "UNKNOWN";
    const rawContentLength = Array.isArray(req.headers["content-length"]) ? req.headers["content-length"][0] : req.headers["content-length"];
    const parsedContentLength = rawContentLength ? Number.parseInt(rawContentLength, 10) : NaN;
    let requestBodyBytes = Number.isFinite(parsedContentLength) && parsedContentLength >= 0 ? parsedContentLength : null;
    let responseBodyBytes = 0;
    let rpcMethod = null;
    const originalWrite = res.write.bind(res);
    const originalEnd = res.end.bind(res);
    res.write = ((chunk, encoding, cb) => {
      const resolvedEncoding = typeof encoding === "string" ? encoding : void 0;
      responseBodyBytes += getChunkByteLength(chunk, resolvedEncoding);
      return originalWrite(chunk, encoding, cb);
    });
    res.end = ((chunk, encoding, cb) => {
      const resolvedEncoding = typeof encoding === "string" ? encoding : void 0;
      responseBodyBytes += getChunkByteLength(chunk, resolvedEncoding);
      return originalEnd(chunk, encoding, cb);
    });
    let didLog = false;
    const logApiRequestDuration = () => {
      if (!API_PERF_LOGGING_ENABLED || didLog || !requestPath.startsWith("/codex-api/")) return;
      const durationMs = Number((process.hrtime.bigint() - requestStartNs) / 1000000n);
      const requestBytes = requestBodyBytes ?? 0;
      const bodyMbValue = (requestBytes + responseBodyBytes) / MB_DIVISOR;
      const shouldLog = durationMs > API_PERF_MS_THRESHOLD || bodyMbValue > API_PERF_BODY_MB_THRESHOLD;
      if (!shouldLog) return;
      didLog = true;
      const rpcPart = rpcMethod ? `, rpcMethod=${rpcMethod}` : "";
      console.info(`[codex-api-perf] ${requestMethod} ${requestPath} -> ${res.statusCode} (${durationMs}ms, bodyMB=${bodyMbValue.toFixed(1)}${rpcPart})`);
    };
    res.once("finish", logApiRequestDuration);
    res.once("close", logApiRequestDuration);
    try {
      if (!req.url) {
        next();
        return;
      }
      const url = new URL(req.url, "http://localhost");
      if (url.pathname === "/codex-api/zen-proxy/v1/responses" && req.method === "POST") {
        if (!isLoopbackRemoteAddress(req.socket.remoteAddress)) {
          setJson4(res, 403, { error: "Zen proxy is only available from localhost" });
          return;
        }
        const statePath = join6(getCodexHomeDir3(), FREE_MODE_STATE_FILE);
        let bearerToken = "";
        let wireApi = "responses";
        try {
          const state = ensureDefaultFreeModeStateForMissingAuthSync(statePath);
          bearerToken = state?.apiKey ?? "";
          if (state) {
            wireApi = state.wireApi === "responses" ? "responses" : "chat";
          }
        } catch {
        }
        handleZenProxyRequest(req, res, bearerToken, wireApi);
        return;
      }
      if (url.pathname === "/codex-api/openrouter-proxy/v1/responses" && req.method === "POST") {
        const statePath = join6(getCodexHomeDir3(), FREE_MODE_STATE_FILE);
        let bearerToken = "";
        let wireApi = "responses";
        try {
          const state = ensureDefaultFreeModeStateForMissingAuthSync(statePath);
          bearerToken = state?.apiKey ?? "";
          wireApi = state?.wireApi === "chat" ? "chat" : "responses";
        } catch {
        }
        handleOpenRouterProxyRequest(req, res, bearerToken, wireApi);
        return;
      }
      if (url.pathname === "/codex-api/custom-proxy/v1/responses" && req.method === "POST") {
        const statePath = join6(getCodexHomeDir3(), FREE_MODE_STATE_FILE);
        let bearerToken = "";
        let wireApi = "responses";
        let baseUrl = "";
        try {
          const state = ensureDefaultFreeModeStateForMissingAuthSync(statePath);
          bearerToken = state?.apiKey ?? "";
          wireApi = state?.wireApi === "chat" ? "chat" : "responses";
          baseUrl = state?.customBaseUrl ?? "";
        } catch {
        }
        handleCustomEndpointProxyRequest(req, res, { baseUrl, bearerToken, wireApi });
        return;
      }
      if (url.pathname.startsWith("/codex-api/free-mode")) {
        let readFreeModeState2 = function() {
          return ensureDefaultFreeModeStateForMissingAuthSync(statePath) ?? { enabled: false, apiKey: null, model: FREE_MODE_DEFAULT_MODEL };
        };
        var readFreeModeState = readFreeModeState2;
        const statePath = join6(getCodexHomeDir3(), FREE_MODE_STATE_FILE);
        if (req.method === "POST" && url.pathname === "/codex-api/free-mode") {
          try {
            const body = await readJsonBody2(req);
            const enable = Boolean(body?.enable);
            if (enable) {
              const apiKey = getRandomFreeKey();
              if (!apiKey) {
                setJson4(res, 500, { error: "No free keys available" });
                return;
              }
              const prev = readFreeModeState2();
              const prevKeys = prev.providerKeys ?? {};
              if (prev.provider && prev.apiKey) {
                prevKeys[prev.provider] = prev.apiKey;
              }
              const state = {
                enabled: true,
                apiKey,
                model: FREE_MODE_DEFAULT_MODEL,
                provider: "openrouter",
                wireApi: prev.wireApi === "chat" ? "chat" : "responses",
                providerKeys: prevKeys
              };
              await writeFreeModeStateFile(statePath, state);
              appServer.dispose();
              const freeModels = await getFreeModels();
              setJson4(res, 200, {
                ok: true,
                enabled: true,
                model: FREE_MODE_DEFAULT_MODEL,
                keyCount: getFreeKeyCount(),
                models: freeModels
              });
            } else {
              const prev = readFreeModeState2();
              const prevKeys = prev.providerKeys ?? {};
              if (prev.provider && prev.apiKey) {
                prevKeys[prev.provider] = prev.apiKey;
              }
              const state = {
                enabled: false,
                apiKey: null,
                model: FREE_MODE_DEFAULT_MODEL,
                wireApi: prev.wireApi === "chat" ? "chat" : "responses",
                providerKeys: prevKeys
              };
              await writeFreeModeStateFile(statePath, state);
              appServer.dispose();
              setJson4(res, 200, { ok: true, enabled: false });
            }
          } catch (error) {
            setJson4(res, 500, { error: getErrorMessage6(error, "Failed to toggle free mode") });
          }
          return;
        }
        if (req.method === "GET" && url.pathname === "/codex-api/free-mode/status") {
          try {
            const state = readFreeModeState2();
            const maskedKey = state.apiKey && state.customKey ? state.apiKey.substring(0, 12) + "..." + state.apiKey.substring(state.apiKey.length - 4) : null;
            let models = getCachedFreeModels();
            let currentModel = state.enabled ? state.model : null;
            let wireApi = state.wireApi ?? null;
            if (state.provider === OPENCODE_ZEN_PROVIDER_ID) {
              currentModel = state.enabled ? state.model?.trim() || OPENCODE_ZEN_DEFAULT_MODEL : null;
              try {
                const zenModels = filterOpenCodeZenModelsForAuthState(
                  sortOpenCodeZenModelIds(await fetchOpenCodeZenModelIds(state.apiKey)),
                  state.apiKey
                );
                if (zenModels.length > 0) {
                  models = zenModels;
                } else {
                  models = [
                    OPENCODE_ZEN_DEFAULT_MODEL,
                    "minimax-m2.5-free",
                    "nemotron-3-super-free",
                    "trinity-large-preview-free"
                  ];
                }
              } catch {
                models = [
                  OPENCODE_ZEN_DEFAULT_MODEL,
                  "minimax-m2.5-free",
                  "nemotron-3-super-free",
                  "trinity-large-preview-free"
                ];
              }
              wireApi = "responses";
            } else {
              refreshFreeModelsInBackground();
            }
            setJson4(res, 200, {
              enabled: state.enabled,
              hasCodexAuth: hasUsableCodexAuthSync(),
              keyCount: getFreeKeyCount(),
              models,
              currentModel,
              customKey: Boolean(state.customKey),
              maskedKey,
              provider: state.provider ?? "openrouter",
              customBaseUrl: state.customBaseUrl ?? null,
              wireApi
            });
          } catch (error) {
            setJson4(res, 500, { error: getErrorMessage6(error, "Failed to read free mode status") });
          }
          return;
        }
        if (req.method === "POST" && url.pathname === "/codex-api/free-mode/rotate-key") {
          try {
            const apiKey = getRandomFreeKey();
            if (!apiKey) {
              setJson4(res, 500, { error: "No free keys available" });
              return;
            }
            const current = readFreeModeState2();
            const state = { ...current, apiKey, customKey: false };
            await writeFreeModeStateFile(statePath, state);
            appServer.dispose();
            setJson4(res, 200, { ok: true });
          } catch (error) {
            setJson4(res, 500, { error: getErrorMessage6(error, "Failed to rotate key") });
          }
          return;
        }
        if (req.method === "POST" && url.pathname === "/codex-api/free-mode/custom-key") {
          try {
            const body = await readJsonBody2(req);
            const key = typeof body?.key === "string" ? body.key.trim() : "";
            const current = readFreeModeState2();
            if (key.length > 0) {
              const state = {
                ...current,
                enabled: true,
                apiKey: key,
                customKey: true,
                provider: "openrouter",
                wireApi: current.wireApi === "chat" ? "chat" : "responses"
              };
              await writeFreeModeStateFile(statePath, state);
              appServer.dispose();
              setJson4(res, 200, { ok: true, customKey: true });
            } else {
              const communityKey = getRandomFreeKey();
              const state = {
                ...current,
                apiKey: communityKey,
                customKey: false,
                provider: "openrouter",
                wireApi: current.wireApi === "chat" ? "chat" : "responses"
              };
              await writeFreeModeStateFile(statePath, state);
              appServer.dispose();
              setJson4(res, 200, { ok: true, customKey: false });
            }
          } catch (error) {
            setJson4(res, 500, { error: getErrorMessage6(error, "Failed to set custom key") });
          }
          return;
        }
        if (req.method === "POST" && url.pathname === "/codex-api/free-mode/custom-provider") {
          try {
            const body = await readJsonBody2(req);
            const baseUrl = typeof body?.baseUrl === "string" ? body.baseUrl.trim() : "";
            const apiKey = typeof body?.apiKey === "string" ? body.apiKey.trim() : "";
            const wireApi = body?.wireApi === "chat" ? "chat" : "responses";
            const providerType = body?.provider === "opencode-zen" ? "opencode-zen" : body?.provider === "openrouter" ? "openrouter" : "custom";
            if (providerType === "custom" && !baseUrl) {
              setJson4(res, 400, { error: "baseUrl is required" });
              return;
            }
            const current = readFreeModeState2();
            const prevKeys = current.providerKeys ?? {};
            if (current.provider && current.apiKey) {
              prevKeys[current.provider] = current.apiKey;
            }
            const resolvedKey = apiKey || prevKeys[providerType] || "";
            if (resolvedKey) {
              prevKeys[providerType] = resolvedKey;
            }
            const currentModel = (current.model ?? "").trim();
            const resolvedModel = providerType === "openrouter" ? currentModel.includes("/") ? currentModel : FREE_MODE_DEFAULT_MODEL : providerType === "custom" ? await fetchCustomEndpointDefaultModel(baseUrl, resolvedKey) : OPENCODE_ZEN_DEFAULT_MODEL;
            const state = {
              enabled: true,
              apiKey: resolvedKey,
              model: resolvedModel,
              customKey: providerType === "openrouter" ? shouldMarkOpenRouterKeyAsCustom(current, apiKey) : true,
              provider: providerType,
              customBaseUrl: providerType === "custom" ? baseUrl : void 0,
              wireApi,
              providerKeys: prevKeys
            };
            await writeFreeModeStateFile(statePath, state);
            appServer.dispose();
            setJson4(res, 200, { ok: true });
          } catch (error) {
            setJson4(res, 500, { error: getErrorMessage6(error, "Failed to set custom provider") });
          }
          return;
        }
        next();
        return;
      }
      if (await handleAccountRoutes(req, res, url, { appServer })) {
        return;
      }
      if (await handleSkillsRoutes(req, res, url, { appServer, readJsonBody: readJsonBody2 })) {
        return;
      }
      if (await handleReviewRoutes(req, res, url, { readJsonBody: readJsonBody2 })) {
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-terminal/status") {
        setJson4(res, 200, terminalManager.getAvailability());
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-terminal/quick-commands") {
        const cwd = url.searchParams.get("cwd")?.trim() ?? "";
        if (!cwd) {
          setJson4(res, 400, { error: "Missing cwd" });
          return;
        }
        try {
          setJson4(res, 200, { commands: await listTerminalQuickCommands(cwd) });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to load terminal quick commands") });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/thread-terminal/attach") {
        const availability = terminalManager.getAvailability();
        if (!availability.available) {
          setJson4(res, 503, { error: availability.reason || "Integrated terminal is unavailable on this host" });
          return;
        }
        const body = asRecord6(await readJsonBody2(req));
        const threadId = readNonEmptyString(body?.threadId);
        const cwd = readNonEmptyString(body?.cwd);
        if (!threadId || !cwd) {
          setJson4(res, 400, { error: "Missing threadId or cwd" });
          return;
        }
        const session = terminalManager.attach({
          threadId,
          cwd,
          sessionId: readNonEmptyString(body?.sessionId) || void 0,
          cols: typeof body?.cols === "number" ? body.cols : void 0,
          rows: typeof body?.rows === "number" ? body.rows : void 0,
          newSession: body?.newSession === true
        });
        setJson4(res, 200, { session });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/thread-terminal/input") {
        const availability = terminalManager.getAvailability();
        if (!availability.available) {
          setJson4(res, 503, { error: availability.reason || "Integrated terminal is unavailable on this host" });
          return;
        }
        const body = asRecord6(await readJsonBody2(req));
        const sessionId = readNonEmptyString(body?.sessionId);
        const data = typeof body?.data === "string" ? body.data : "";
        if (!sessionId) {
          setJson4(res, 400, { error: "Missing sessionId" });
          return;
        }
        terminalManager.write(sessionId, data);
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/thread-terminal/resize") {
        const availability = terminalManager.getAvailability();
        if (!availability.available) {
          setJson4(res, 503, { error: availability.reason || "Integrated terminal is unavailable on this host" });
          return;
        }
        const body = asRecord6(await readJsonBody2(req));
        const sessionId = readNonEmptyString(body?.sessionId);
        if (!sessionId) {
          setJson4(res, 400, { error: "Missing sessionId" });
          return;
        }
        terminalManager.resize(sessionId, body?.cols, body?.rows);
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/thread-terminal/close") {
        const availability = terminalManager.getAvailability();
        if (!availability.available) {
          setJson4(res, 503, { error: availability.reason || "Integrated terminal is unavailable on this host" });
          return;
        }
        const body = asRecord6(await readJsonBody2(req));
        const sessionId = readNonEmptyString(body?.sessionId);
        if (!sessionId) {
          setJson4(res, 400, { error: "Missing sessionId" });
          return;
        }
        terminalManager.close(sessionId);
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-terminal-snapshot") {
        const threadId = url.searchParams.get("threadId")?.trim() ?? "";
        if (!threadId) {
          setJson4(res, 400, { error: "Missing threadId" });
          return;
        }
        setJson4(res, 200, { session: terminalManager.getSnapshotForThread(threadId) });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/upload-file") {
        handleFileUpload(req, res);
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/rpc") {
        const payload = await readJsonBody2(req);
        const body = asRecord6(payload);
        if (payload !== null && payload !== void 0) {
          requestBodyBytes = Buffer.byteLength(JSON.stringify(payload), "utf8");
        }
        rpcMethod = body?.method && typeof body.method === "string" ? body.method : null;
        if (!body || typeof body.method !== "string" || body.method.length === 0) {
          setJson4(res, 400, { error: "Invalid body: expected { method, params? }" });
          return;
        }
        if (body.method === "generate-thread-title") {
          setJson4(res, 200, { result: { title: "" } });
          return;
        }
        if (body.method === "account/rateLimits/read" && !await hasUsableCodexAuth()) {
          setJson4(res, 200, { result: null });
          return;
        }
        let rpcResult;
        try {
          rpcResult = await callRpcWithArchiveRecovery(appServer, body.method, body.params ?? null);
        } catch (error) {
          if (body.method === "account/rateLimits/read" && isUnauthenticatedRateLimitError(error)) {
            setJson4(res, 200, { result: null });
            return;
          }
          if (body.method === "thread/read" && isEmptyThreadReadError(error)) {
            const params = asRecord6(body.params);
            const threadId = typeof params?.threadId === "string" ? params.threadId.trim() : "";
            const snapshot = threadId ? appServer.getLastThreadReadSnapshot(threadId) : null;
            if (snapshot) {
              setJson4(res, 200, { result: snapshot });
              return;
            }
          }
          if (body.method === "thread/read" && isThreadMaterializationPendingError(error)) {
            const params = asRecord6(body.params);
            const threadId = typeof params?.threadId === "string" ? params.threadId.trim() : "";
            if (threadId) {
              setJson4(res, 200, {
                result: {
                  thread: {
                    id: threadId,
                    turns: [],
                    status: { type: "inProgress" }
                  }
                }
              });
              return;
            }
          }
          throw error;
        }
        const trimmedResult = trimThreadTurnsInRpcResult(body.method, rpcResult);
        const errorMergedResult = THREAD_METHODS_WITH_TURNS.has(body.method) ? mergeStreamTurnErrorsIntoThreadResult(appServer, trimmedResult) : trimmedResult;
        const sanitizedResult = await sanitizeThreadTurnsInlinePayloads(body.method, errorMergedResult);
        const result = THREAD_METHODS_WITH_TURNS.has(body.method) ? await mergeSessionSkillInputsIntoThreadResult(sanitizedResult) : sanitizedResult;
        if (THREAD_METHODS_WITH_THREAD_SNAPSHOT.has(body.method)) {
          const rpcRecord = asRecord6(result);
          const rpcThread = asRecord6(rpcRecord?.thread);
          const rpcThreadId = typeof rpcThread?.id === "string" ? rpcThread.id : "";
          if (rpcThreadId) {
            appServer.storeThreadReadSnapshot(rpcThreadId, result);
          }
        }
        setJson4(res, 200, { result });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-turn-page") {
        try {
          const threadId = url.searchParams.get("threadId")?.trim() ?? "";
          const beforeTurnId = url.searchParams.get("beforeTurnId")?.trim() ?? "";
          const limitRaw = url.searchParams.get("limit")?.trim() ?? String(THREAD_RESPONSE_TURN_LIMIT);
          const limit = Math.max(1, Math.min(50, Number.parseInt(limitRaw, 10) || THREAD_RESPONSE_TURN_LIMIT));
          if (!threadId) {
            setJson4(res, 400, { error: "Missing threadId" });
            return;
          }
          const threadReadResult = mergeStreamTurnErrorsIntoThreadResult(appServer, await appServer.readThreadForTurnPage(threadId));
          const record = asRecord6(threadReadResult);
          const thread = asRecord6(record?.thread);
          if (!record || !thread) {
            setJson4(res, 502, { error: "thread/read returned an invalid thread response" });
            return;
          }
          const turns = Array.isArray(thread.turns) ? thread.turns : [];
          const beforeIndex = beforeTurnId ? turns.findIndex((turn) => asRecord6(turn)?.id === beforeTurnId) : turns.length;
          if (beforeTurnId && beforeIndex < 0) {
            setJson4(res, 200, {
              result: {
                ...record,
                thread: {
                  ...thread,
                  turns: []
                }
              },
              startTurnIndex: 0,
              hasMoreOlder: false
            });
            return;
          }
          const endIndex = beforeIndex;
          const startIndex = Math.max(0, endIndex - limit);
          const pageTurns = turns.slice(startIndex, endIndex);
          const pagedResult = {
            ...record,
            thread: {
              ...thread,
              turns: pageTurns
            }
          };
          const sanitized = await sanitizeThreadTurnsInlinePayloads("thread/read", pagedResult);
          const result = await mergeSessionSkillInputsIntoThreadResult(sanitized);
          setJson4(res, 200, {
            result,
            startTurnIndex: startIndex,
            hasMoreOlder: startIndex > 0
          });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to load earlier thread messages") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-file-change-fallback") {
        const threadId = url.searchParams.get("threadId")?.trim() ?? "";
        if (!threadId) {
          setJson4(res, 400, { error: "Missing threadId" });
          return;
        }
        const threadReadResult = await appServer.rpc("thread/read", {
          threadId,
          includeTurns: true
        });
        const threadReadRecord = asRecord6(threadReadResult);
        const threadRecord = asRecord6(threadReadRecord?.thread);
        const sessionPath = readNonEmptyString(threadRecord?.path);
        if (!sessionPath || !isAbsolute2(sessionPath)) {
          setJson4(res, 200, { data: [] });
          return;
        }
        try {
          const sessionLogRaw = await readFile3(sessionPath, "utf8");
          setJson4(res, 200, { data: buildSessionFileChangeFallback(threadReadResult, sessionLogRaw) });
        } catch {
          setJson4(res, 200, { data: [] });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-stream-events") {
        const threadId = url.searchParams.get("threadId")?.trim() ?? "";
        const limitRaw = url.searchParams.get("limit")?.trim() ?? "80";
        const limit = Math.max(1, Math.min(400, Number.parseInt(limitRaw, 10) || 80));
        if (!threadId) {
          setJson4(res, 400, { error: "Missing threadId" });
          return;
        }
        const events = appServer.getStreamEvents(threadId, limit);
        setJson4(res, 200, { events });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-live-state") {
        const threadId = url.searchParams.get("threadId")?.trim() ?? "";
        if (!threadId) {
          setJson4(res, 400, { error: "Missing threadId" });
          return;
        }
        try {
          const threadReadResult = mergeStreamTurnErrorsIntoThreadResult(appServer, await appServer.rpc("thread/read", {
            threadId,
            includeTurns: true
          }));
          const sanitized = await sanitizeThreadTurnsInlinePayloads("thread/read", threadReadResult);
          appServer.storeThreadReadSnapshot(threadId, sanitized);
          const record = asRecord6(sanitized);
          const thread = asRecord6(record?.thread);
          const rawTurns = Array.isArray(thread?.turns) ? thread.turns : [];
          const sessionPath = readNonEmptyString(thread?.path);
          let sessionSize = 0;
          if (sessionPath && isAbsolute2(sessionPath)) {
            try {
              const s = await stat4(sessionPath);
              sessionSize = s.size;
            } catch {
            }
          }
          const cached = appServer.getCachedLiveState(threadId, rawTurns.length, sessionSize);
          if (cached) {
            setJson4(res, 200, cached);
            return;
          }
          let turns = appServer.mergeItemsIntoTurns(threadId, rawTurns);
          if (sessionPath && isAbsolute2(sessionPath) && sessionSize > 0) {
            try {
              const sessionLogRaw = await readFile3(sessionPath, "utf8");
              turns = mergeSessionCommandsIntoTurns(turns, sessionLogRaw);
            } catch {
            }
          }
          const lastTurn = turns.length > 0 ? asRecord6(turns[turns.length - 1]) : null;
          const isInProgress = lastTurn?.status === "inProgress";
          const responseData = {
            threadId,
            conversationState: {
              turns
            },
            ownerClientId: null,
            liveStateError: null,
            isInProgress
          };
          if (!isInProgress) {
            appServer.cacheLiveState(threadId, responseData, rawTurns.length, sessionSize);
          }
          setJson4(res, 200, responseData);
        } catch (error) {
          if (isThreadMaterializationPendingError(error)) {
            setJson4(res, 200, {
              threadId,
              conversationState: { turns: [] },
              ownerClientId: null,
              liveStateError: null,
              isInProgress: true
            });
            return;
          }
          const snapshot = appServer.getLastThreadReadSnapshot(threadId);
          if (snapshot) {
            const record = asRecord6(snapshot);
            const thread = asRecord6(record?.thread);
            const rawTurns = Array.isArray(thread?.turns) ? thread.turns : [];
            const turns = appServer.mergeItemsIntoTurns(threadId, rawTurns);
            setJson4(res, 200, {
              threadId,
              conversationState: { turns },
              ownerClientId: null,
              liveStateError: {
                kind: "readFailed",
                message: getErrorMessage6(error, "thread/read failed")
              },
              isInProgress: false
            });
          } else {
            setJson4(res, 200, {
              threadId,
              conversationState: null,
              ownerClientId: null,
              liveStateError: {
                kind: "readFailed",
                message: getErrorMessage6(error, "thread/read failed")
              },
              isInProgress: false
            });
          }
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/thread/rollback-files") {
        try {
          const body = asRecord6(await readJsonBody2(req));
          const threadId = readNonEmptyString(body?.threadId);
          const turnId = readNonEmptyString(body?.turnId);
          const cwd = readNonEmptyString(body?.cwd);
          if (!threadId || !turnId || !cwd) {
            setJson4(res, 400, { error: "Missing threadId, turnId, or cwd" });
            return;
          }
          const threadReadResult = await appServer.rpc("thread/read", { threadId, includeTurns: true });
          const record = asRecord6(threadReadResult);
          const thread = asRecord6(record?.thread);
          const turns = Array.isArray(thread?.turns) ? thread.turns : [];
          const sessionPath = readNonEmptyString(thread?.path);
          if (!sessionPath || !isAbsolute2(sessionPath)) {
            setJson4(res, 200, { reverted: 0, errors: [], message: "No session log available" });
            return;
          }
          let foundTurnIndex = -1;
          const turnIdsToRevert = /* @__PURE__ */ new Set();
          for (let i = 0; i < turns.length; i++) {
            const turnRecord = asRecord6(turns[i]);
            const id = readNonEmptyString(turnRecord?.id);
            if (id === turnId) {
              foundTurnIndex = i;
            }
            if (foundTurnIndex >= 0 && id) {
              turnIdsToRevert.add(id);
            }
          }
          if (turnIdsToRevert.size === 0) {
            setJson4(res, 200, { reverted: 0, errors: [], message: "No turns to revert" });
            return;
          }
          let sessionLogRaw;
          try {
            sessionLogRaw = await readFile3(sessionPath, "utf8");
          } catch {
            setJson4(res, 200, { reverted: 0, errors: ["Could not read session log"], message: "Session log unreadable" });
            return;
          }
          const turnInfos = collectFileChangesForTurns(sessionLogRaw, turnIdsToRevert, cwd);
          if (turnInfos.size === 0) {
            setJson4(res, 200, { reverted: 0, errors: [], message: "No file changes to revert" });
            return;
          }
          const result = await revertTurnFileChanges(cwd, turnInfos);
          setJson4(res, 200, { ...result, message: `Reverted ${result.reverted} file change(s)` });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to revert file changes") });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/transcribe") {
        const auth = await readCodexAuth();
        if (!auth) {
          setJson4(res, 401, { error: "No auth token available for transcription" });
          return;
        }
        const rawBody = await readRawBody(req);
        const incomingCt = req.headers["content-type"] ?? "application/octet-stream";
        const upstream = await proxyTranscribe(rawBody, incomingCt, auth.accessToken, auth.accountId);
        res.statusCode = upstream.status;
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        res.end(upstream.body);
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/composio/status") {
        try {
          setJson4(res, 200, await readComposioStatus());
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to read Composio status") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/composio/connectors") {
        try {
          const query = url.searchParams.get("query") ?? "";
          const cursor = url.searchParams.get("cursor")?.trim() ?? null;
          const limit = parseComposioLimit(url.searchParams.get("limit"));
          setJson4(res, 200, await listComposioConnectors(query, cursor, limit));
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to list Composio connectors") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/composio/connector") {
        try {
          const slug = url.searchParams.get("slug") ?? "";
          setJson4(res, 200, await readComposioConnectorDetail(slug));
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to load Composio connector") });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/composio/link") {
        try {
          const payload = asRecord6(await readJsonBody2(req));
          const slug = readNonEmptyString(payload?.slug);
          setJson4(res, 200, await startComposioLink(slug));
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to start Composio login") });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/composio/login") {
        try {
          setJson4(res, 200, await startComposioLogin());
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to start Composio CLI login") });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/composio/install") {
        try {
          setJson4(res, 200, await installComposioCli());
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to install Composio CLI") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/connector-logo") {
        const src = url.searchParams.get("src")?.trim() ?? "";
        if (!src) {
          setJson4(res, 400, { error: "Missing src" });
          return;
        }
        try {
          const logo = await fetchConnectorLogo(src);
          res.statusCode = 200;
          res.setHeader("Content-Type", logo.contentType);
          res.setHeader("Cache-Control", "private, max-age=3600");
          res.end(logo.body);
        } catch (error) {
          setJson4(res, 502, { error: getErrorMessage6(error, "Failed to fetch connector logo") });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/server-requests/respond") {
        const payload = await readJsonBody2(req);
        await appServer.respondToServerRequest(payload);
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/server-requests/pending") {
        setJson4(res, 200, { data: appServer.listPendingServerRequests() });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/meta/methods") {
        const methods = await methodCatalog.listMethods();
        setJson4(res, 200, { data: methods });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/meta/notifications") {
        const methods = await methodCatalog.listNotificationMethods();
        setJson4(res, 200, { data: methods });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/provider-models") {
        try {
          const requestedProvider = url.searchParams.get("provider")?.trim() ?? "";
          if (requestedProvider) {
            setJson4(res, 200, {
              ...await readProviderModelIdsForProvider(appServer, requestedProvider),
              exclusive: true
            });
            return;
          }
          const fmState = ensureDefaultFreeModeStateForMissingAuthSync(join6(getCodexHomeDir3(), FREE_MODE_STATE_FILE));
          if (fmState?.enabled) {
            if (fmState.provider === "opencode-zen") {
              try {
                const modelIds = filterOpenCodeZenModelsForAuthState(
                  sortOpenCodeZenModelIds(await fetchOpenCodeZenModelIds(fmState.apiKey)),
                  fmState.apiKey
                );
                if (modelIds.length > 0) {
                  setJson4(res, 200, { data: modelIds, exclusive: true, source: "opencode-zen" });
                  return;
                }
              } catch {
              }
              setJson4(res, 200, { data: ["big-pickle", "minimax-m2.5-free", "nemotron-3-super-free", "trinity-large-preview-free"], exclusive: true, source: "opencode-zen" });
              return;
            }
            if (fmState.provider === "custom" && fmState.customBaseUrl) {
              try {
                const modelsUrl = fmState.customBaseUrl.replace(/\/+$/, "") + "/models";
                const headers = {};
                if (fmState.apiKey && fmState.apiKey !== "dummy") {
                  headers["Authorization"] = `Bearer ${fmState.apiKey}`;
                }
                const resp = await fetch(modelsUrl, { headers, signal: AbortSignal.timeout(8e3) });
                if (resp.ok) {
                  const json = await resp.json();
                  const ids = normalizeProviderModelsData(json);
                  const currentModel = fmState.model?.trim() ?? "";
                  const orderedIds = currentModel && ids.includes(currentModel) ? [currentModel, ...ids.filter((id) => id !== currentModel)] : ids;
                  setJson4(res, 200, { data: orderedIds, exclusive: true, source: "custom" });
                  return;
                }
              } catch {
              }
              setJson4(res, 200, { data: [], exclusive: true, source: "custom" });
              return;
            }
            const freeModels = await getFreeModels();
            setJson4(res, 200, { data: freeModels, exclusive: true });
            return;
          }
        } catch {
        }
        const data = await readProviderBackedModelIds(appServer);
        setJson4(res, 200, data);
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/workspace-roots-state") {
        const state = await readWorkspaceRootsState();
        setJson4(res, 200, { data: state });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-queue-state") {
        const state = await readThreadQueueState();
        setJson4(res, 200, { data: state });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/home-directory") {
        setJson4(res, 200, { data: { path: homedir5() } });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/worktree/create") {
        const payload = asRecord6(await readJsonBody2(req));
        const rawSourceCwd = typeof payload?.sourceCwd === "string" ? payload.sourceCwd.trim() : "";
        const baseBranch = typeof payload?.baseBranch === "string" ? payload.baseBranch.trim() : "";
        if (!rawSourceCwd) {
          setJson4(res, 400, { error: "Missing sourceCwd" });
          return;
        }
        const sourceCwd = isAbsolute2(rawSourceCwd) ? rawSourceCwd : resolve2(rawSourceCwd);
        try {
          const sourceInfo = await stat4(sourceCwd);
          if (!sourceInfo.isDirectory()) {
            setJson4(res, 400, { error: "sourceCwd is not a directory" });
            return;
          }
        } catch {
          setJson4(res, 404, { error: "sourceCwd does not exist" });
          return;
        }
        try {
          let gitRoot = "";
          try {
            gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd: sourceCwd });
          } catch (error) {
            if (!isNotGitRepositoryError2(error)) throw error;
            await runCommand3("git", ["init"], { cwd: sourceCwd });
            gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd: sourceCwd });
          }
          const repoName = basename4(gitRoot) || "repo";
          const worktreesRoot = join6(getCodexHomeDir3(), "worktrees");
          await mkdir4(worktreesRoot, { recursive: true });
          let worktreeId = "";
          let worktreeParent = "";
          let worktreeCwd = "";
          for (let attempt = 0; attempt < 12; attempt += 1) {
            const candidate = randomBytes(2).toString("hex");
            const parent = join6(worktreesRoot, candidate);
            try {
              await stat4(parent);
              continue;
            } catch {
              worktreeId = candidate;
              worktreeParent = parent;
              worktreeCwd = join6(parent, repoName);
              break;
            }
          }
          if (!worktreeId || !worktreeParent || !worktreeCwd) {
            throw new Error("Failed to allocate a unique worktree id");
          }
          const startPoint = baseBranch || "HEAD";
          await mkdir4(worktreeParent, { recursive: true });
          try {
            await runCommand3("git", ["worktree", "add", "--detach", worktreeCwd, startPoint], { cwd: gitRoot });
          } catch (error) {
            if (!isMissingHeadError2(error)) throw error;
            await ensureRepoHasInitialCommit(gitRoot);
            await runCommand3("git", ["worktree", "add", "--detach", worktreeCwd, startPoint], { cwd: gitRoot });
          }
          try {
            await persistWorkspaceRoot(worktreeCwd);
          } catch (error) {
            await rollbackCreatedWorktree(gitRoot, worktreeCwd, worktreeParent);
            throw error;
          }
          setJson4(res, 200, {
            data: {
              cwd: worktreeCwd,
              branch: null,
              gitRoot
            }
          });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to create worktree") });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/worktree/create-permanent") {
        const payload = asRecord6(await readJsonBody2(req));
        const rawSourceCwd = typeof payload?.sourceCwd === "string" ? payload.sourceCwd.trim() : "";
        const rawWorktreeName = typeof payload?.worktreeName === "string" ? payload.worktreeName.trim() : "";
        if (!rawSourceCwd) {
          setJson4(res, 400, { error: "Missing sourceCwd" });
          return;
        }
        if (!rawWorktreeName) {
          setJson4(res, 400, { error: "Missing worktreeName" });
          return;
        }
        if (rawWorktreeName.includes("/") || rawWorktreeName.includes("\\") || rawWorktreeName === "." || rawWorktreeName === "..") {
          setJson4(res, 400, { error: "Worktree name must be a single folder name" });
          return;
        }
        const sourceCwd = isAbsolute2(rawSourceCwd) ? rawSourceCwd : resolve2(rawSourceCwd);
        try {
          const sourceInfo = await stat4(sourceCwd);
          if (!sourceInfo.isDirectory()) {
            setJson4(res, 400, { error: "sourceCwd is not a directory" });
            return;
          }
        } catch {
          setJson4(res, 404, { error: "sourceCwd does not exist" });
          return;
        }
        try {
          let gitRoot = "";
          try {
            gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd: sourceCwd });
          } catch (error) {
            if (!isNotGitRepositoryError2(error)) throw error;
            await runCommand3("git", ["init"], { cwd: sourceCwd });
            gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd: sourceCwd });
          }
          const worktreeCwd = join6(dirname2(gitRoot), rawWorktreeName);
          try {
            await stat4(worktreeCwd);
            setJson4(res, 409, { error: "Worktree folder already exists" });
            return;
          } catch {
          }
          const branchName = await allocatePermanentWorktreeBranchName(gitRoot, rawWorktreeName);
          try {
            await runCommand3("git", ["worktree", "add", "-b", branchName, worktreeCwd, "HEAD"], { cwd: gitRoot });
          } catch (error) {
            if (!isMissingHeadError2(error)) throw error;
            await ensureRepoHasInitialCommit(gitRoot);
            await runCommand3("git", ["worktree", "add", "-b", branchName, worktreeCwd, "HEAD"], { cwd: gitRoot });
          }
          try {
            await persistWorkspaceRoot(worktreeCwd);
          } catch (error) {
            await rollbackCreatedWorktree(gitRoot, worktreeCwd, void 0, branchName);
            throw error;
          }
          setJson4(res, 200, {
            data: {
              cwd: worktreeCwd,
              branch: branchName,
              gitRoot
            }
          });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to create worktree") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/worktree/branches") {
        const rawSourceCwd = (url.searchParams.get("sourceCwd") ?? "").trim();
        if (!rawSourceCwd) {
          setJson4(res, 400, { error: "Missing sourceCwd" });
          return;
        }
        const sourceCwd = isAbsolute2(rawSourceCwd) ? rawSourceCwd : resolve2(rawSourceCwd);
        try {
          const sourceInfo = await stat4(sourceCwd);
          if (!sourceInfo.isDirectory()) {
            setJson4(res, 400, { error: "sourceCwd is not a directory" });
            return;
          }
        } catch {
          setJson4(res, 404, { error: "sourceCwd does not exist" });
          return;
        }
        try {
          let gitRoot = "";
          try {
            gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd: sourceCwd });
          } catch (error) {
            if (!isNotGitRepositoryError2(error)) throw error;
            setJson4(res, 200, { data: [] });
            return;
          }
          const output = await runCommandCapture2(
            "git",
            ["for-each-ref", "--format=%(committerdate:unix)	%(refname)", "refs/heads", "refs/remotes"],
            { cwd: gitRoot }
          );
          const branchActivityByName = /* @__PURE__ */ new Map();
          for (const line of output.split("\n")) {
            const [rawTimestamp = "", rawRefName = ""] = line.split("	");
            const normalized = normalizeBranchRefName(rawRefName);
            if (!normalized || normalized === "origin/HEAD") continue;
            const parsedTimestamp = Number.parseInt(rawTimestamp.trim(), 10);
            const timestamp = Number.isFinite(parsedTimestamp) ? parsedTimestamp : 0;
            const current = branchActivityByName.get(normalized) ?? Number.MIN_SAFE_INTEGER;
            if (timestamp > current) {
              branchActivityByName.set(normalized, timestamp);
            }
          }
          const branches = Array.from(branchActivityByName.entries()).map(([value]) => ({ value, label: value })).sort((a, b) => {
            const aActivity = branchActivityByName.get(a.value) ?? 0;
            const bActivity = branchActivityByName.get(b.value) ?? 0;
            if (bActivity !== aActivity) return bActivity - aActivity;
            return a.value.localeCompare(b.value);
          });
          setJson4(res, 200, { data: branches });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to list branches") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/git/branches") {
        const rawCwd = (url.searchParams.get("cwd") ?? "").trim();
        if (!rawCwd) {
          setJson4(res, 400, { error: "Missing cwd" });
          return;
        }
        const cwd = isAbsolute2(rawCwd) ? rawCwd : resolve2(rawCwd);
        try {
          const cwdInfo = await stat4(cwd);
          if (!cwdInfo.isDirectory()) {
            setJson4(res, 400, { error: "cwd is not a directory" });
            return;
          }
        } catch {
          setJson4(res, 404, { error: "cwd does not exist" });
          return;
        }
        try {
          let gitRoot = "";
          try {
            gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd });
          } catch (error) {
            if (!isNotGitRepositoryError2(error)) throw error;
            setJson4(res, 200, {
              data: {
                currentBranch: null,
                options: []
              }
            });
            return;
          }
          const state = await readGitHeaderState(gitRoot);
          const currentBranch = state.currentBranch;
          const output = await runCommandCapture2(
            "git",
            ["for-each-ref", "--format=%(committerdate:unix)	%(refname)	%(objectname)", "refs/heads", "refs/remotes"],
            { cwd: gitRoot }
          );
          const branchActivityByName = /* @__PURE__ */ new Map();
          for (const line of output.split("\n")) {
            const [rawTimestamp = "", rawRefName = ""] = line.split("	");
            const normalized = normalizeBranchRefName(rawRefName);
            if (!normalized || normalized === "origin/HEAD") continue;
            const parsedTimestamp = Number.parseInt(rawTimestamp.trim(), 10);
            const timestamp = Number.isFinite(parsedTimestamp) ? parsedTimestamp : 0;
            const isRemote = rawRefName.trim().startsWith("refs/remotes/");
            const current = branchActivityByName.get(normalized);
            if (!current || timestamp > current.timestamp) {
              branchActivityByName.set(normalized, { timestamp, isRemote });
            }
          }
          if (currentBranch && !branchActivityByName.has(currentBranch)) {
            branchActivityByName.set(currentBranch, { timestamp: Number.MAX_SAFE_INTEGER, isRemote: false });
          }
          const options = Array.from(branchActivityByName.entries()).map(([value, metadata]) => ({
            value,
            label: value,
            isCurrent: value === currentBranch,
            isRemote: metadata.isRemote
          })).sort((a, b) => {
            const aActivity = branchActivityByName.get(a.value)?.timestamp ?? 0;
            const bActivity = branchActivityByName.get(b.value)?.timestamp ?? 0;
            if (bActivity !== aActivity) return bActivity - aActivity;
            return a.value.localeCompare(b.value);
          });
          setJson4(res, 200, {
            data: {
              ...state,
              options
            }
          });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to read Git branches") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/git/repository-status") {
        const rawCwd = (url.searchParams.get("cwd") ?? "").trim();
        if (!rawCwd) {
          setJson4(res, 400, { error: "Missing cwd" });
          return;
        }
        const cwd = isAbsolute2(rawCwd) ? rawCwd : resolve2(rawCwd);
        try {
          const cwdInfo = await stat4(cwd);
          if (!cwdInfo.isDirectory()) {
            setJson4(res, 400, { error: "cwd is not a directory" });
            return;
          }
        } catch {
          setJson4(res, 404, { error: "cwd does not exist" });
          return;
        }
        try {
          const gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd });
          setJson4(res, 200, {
            data: {
              isGitRepo: true,
              gitRoot
            }
          });
        } catch (error) {
          if (!isNotGitRepositoryError2(error)) {
            setJson4(res, 500, { error: getErrorMessage6(error, "Failed to read Git repository status") });
            return;
          }
          setJson4(res, 200, {
            data: {
              isGitRepo: false,
              gitRoot: ""
            }
          });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/git/checkout") {
        const payload = await readJsonBody2(req);
        const record = asRecord6(payload);
        if (!record) {
          setJson4(res, 400, { error: "Invalid body: expected object" });
          return;
        }
        const rawCwd = readNonEmptyString(record.cwd);
        const targetBranch = readNonEmptyString(record.branch);
        if (!rawCwd) {
          setJson4(res, 400, { error: "Missing cwd" });
          return;
        }
        if (!targetBranch) {
          setJson4(res, 400, { error: "Missing branch" });
          return;
        }
        const cwd = isAbsolute2(rawCwd) ? rawCwd : resolve2(rawCwd);
        try {
          const cwdInfo = await stat4(cwd);
          if (!cwdInfo.isDirectory()) {
            setJson4(res, 400, { error: "cwd is not a directory" });
            return;
          }
        } catch {
          setJson4(res, 404, { error: "cwd does not exist" });
          return;
        }
        try {
          const gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd });
          await assertNoTrackedGitChanges(gitRoot);
          await assertLocalGitBranch(gitRoot, targetBranch);
          await checkoutGitBranchWithWorktreeRecovery(gitRoot, targetBranch);
          setJson4(res, 200, { data: await readGitHeaderState(gitRoot) });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to switch branch") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/git/branch-commits") {
        const rawCwd = (url.searchParams.get("cwd") ?? "").trim();
        const branch = (url.searchParams.get("branch") ?? "").trim();
        const includeResetHistory = url.searchParams.get("includeResetHistory") !== "false";
        if (!rawCwd) {
          setJson4(res, 400, { error: "Missing cwd" });
          return;
        }
        if (!branch) {
          setJson4(res, 400, { error: "Missing branch" });
          return;
        }
        const cwd = isAbsolute2(rawCwd) ? rawCwd : resolve2(rawCwd);
        try {
          const gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd });
          await runCommandCapture2("git", ["rev-parse", "--verify", `${branch}^{commit}`], { cwd: gitRoot });
          let resetHistoryRefs = [];
          if (includeResetHistory) {
            const resetHistoryRefPrefix = `refs/codex/header-git-reset-history/${branch}/`;
            const resetHistoryRefsRaw = await runCommandCapture2(
              "git",
              ["for-each-ref", "--sort=-creatordate", "--format=%(refname)", resetHistoryRefPrefix],
              { cwd: gitRoot }
            ).catch(() => "");
            resetHistoryRefs = resetHistoryRefsRaw.split("\n").map((entry) => entry.trim()).filter(Boolean).slice(0, HEADER_GIT_RESET_HISTORY_REF_LIMIT);
          }
          const output = await runCommandCapture2(
            "git",
            ["log", "-n", "50", "--date=short", "--format=%H%x09%h%x09%cd%x09%s", branch, ...resetHistoryRefs],
            { cwd: gitRoot }
          );
          const commits = output.split("\n").flatMap((line) => {
            const [sha = "", shortSha = "", date = "", ...subjectParts] = line.split("	");
            const subject = subjectParts.join("	").trim();
            return sha.trim() && shortSha.trim() ? [{ sha: sha.trim(), shortSha: shortSha.trim(), date: date.trim(), subject: subject || shortSha.trim() }] : [];
          });
          setJson4(res, 200, { data: commits });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to load branch commits") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/git/commit-files") {
        const rawCwd = (url.searchParams.get("cwd") ?? "").trim();
        const sha = (url.searchParams.get("sha") ?? "").trim();
        if (!rawCwd) {
          setJson4(res, 400, { error: "Missing cwd" });
          return;
        }
        if (!sha) {
          setJson4(res, 400, { error: "Missing sha" });
          return;
        }
        const cwd = isAbsolute2(rawCwd) ? rawCwd : resolve2(rawCwd);
        try {
          const gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd });
          await runCommandCapture2("git", ["rev-parse", "--verify", `${sha}^{commit}`], { cwd: gitRoot });
          const output = await runCommandCaptureRaw2(
            "git",
            ["diff-tree", "--root", "--no-commit-id", "--name-status", "-r", "-M", "-z", sha],
            { cwd: gitRoot }
          );
          const numstatOutput = await runCommandCaptureRaw2(
            "git",
            ["diff-tree", "--root", "--no-commit-id", "--numstat", "-r", "-M", "-z", sha],
            { cwd: gitRoot }
          );
          const splitNumstatRecord = (record) => {
            const firstTab = record.indexOf("	");
            if (firstTab < 0) return null;
            const secondTab = record.indexOf("	", firstTab + 1);
            if (secondTab < 0) return null;
            return {
              addedRaw: record.slice(0, firstTab),
              removedRaw: record.slice(firstTab + 1, secondTab),
              path: record.slice(secondTab + 1)
            };
          };
          const lineCountsByPath = /* @__PURE__ */ new Map();
          const numstatRecords = splitGitPathList2(numstatOutput);
          for (let index = 0; index < numstatRecords.length; index += 1) {
            const record = splitNumstatRecord(numstatRecords[index] ?? "");
            if (!record) continue;
            const { addedRaw, removedRaw } = record;
            const path = record.path || numstatRecords[index + 2] || numstatRecords[index + 1] || "";
            if (!record.path) index += 2;
            if (!path) continue;
            const addedLineCount = /^\d+$/.test(addedRaw) ? Number(addedRaw) : null;
            const removedLineCount = /^\d+$/.test(removedRaw) ? Number(removedRaw) : null;
            lineCountsByPath.set(path, { addedLineCount, removedLineCount });
          }
          const nameStatusRecords = splitGitPathList2(output);
          const files = [];
          for (let index = 0; index < nameStatusRecords.length; index += 1) {
            const status = nameStatusRecords[index] ?? "";
            if (!status) continue;
            const statusKind = status.charAt(0);
            const isRenameOrCopy = statusKind === "R" || statusKind === "C";
            const previousPath = isRenameOrCopy ? nameStatusRecords[index + 1] || null : null;
            const path = isRenameOrCopy ? nameStatusRecords[index + 2] || "" : nameStatusRecords[index + 1] || "";
            index += isRenameOrCopy ? 2 : 1;
            if (!path) continue;
            const label = statusKind === "A" ? "Added" : statusKind === "D" ? "Deleted" : statusKind === "R" ? "Renamed" : statusKind === "C" ? "Copied" : statusKind === "M" ? "Modified" : status;
            const lineCounts = lineCountsByPath.get(path) ?? { addedLineCount: null, removedLineCount: null };
            files.push({ path, previousPath, status, label, ...lineCounts });
          }
          setJson4(res, 200, { data: files });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to load commit files") });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/git/reset-to-commit") {
        const payload = await readJsonBody2(req);
        const record = asRecord6(payload);
        if (!record) {
          setJson4(res, 400, { error: "Invalid body: expected object" });
          return;
        }
        const rawCwd = readNonEmptyString(record.cwd);
        const branch = readNonEmptyString(record.branch);
        const sha = readNonEmptyString(record.sha);
        if (!rawCwd) {
          setJson4(res, 400, { error: "Missing cwd" });
          return;
        }
        if (!branch) {
          setJson4(res, 400, { error: "Missing branch" });
          return;
        }
        if (!sha) {
          setJson4(res, 400, { error: "Missing commit" });
          return;
        }
        const cwd = isAbsolute2(rawCwd) ? rawCwd : resolve2(rawCwd);
        try {
          const gitRoot = await runCommandCapture2("git", ["rev-parse", "--show-toplevel"], { cwd });
          await assertNoTrackedGitChanges(gitRoot);
          await assertLocalGitBranch(gitRoot, branch);
          const currentBranch = (await runCommandCapture2("git", ["branch", "--show-current"], { cwd: gitRoot })).trim();
          if (currentBranch && currentBranch !== branch) {
            await checkoutGitBranchWithWorktreeRecovery(gitRoot, branch);
          } else if (!currentBranch) {
            await checkoutGitBranchWithWorktreeRecovery(gitRoot, branch);
          }
          const previousTip = await runCommandCapture2("git", ["rev-parse", "HEAD"], { cwd: gitRoot });
          const targetSha = await runCommandCapture2("git", ["rev-parse", "--verify", `${sha}^{commit}`], { cwd: gitRoot });
          await runCommand3("git", ["update-ref", toHeaderGitResetHistoryRef(branch, previousTip.trim()), previousTip.trim()], { cwd: gitRoot });
          await pruneHeaderGitResetHistoryRefs(gitRoot, branch);
          await withPreservedUntrackedFilesForGitTarget(gitRoot, targetSha.trim(), async () => {
            await runCommand3("git", ["reset", "--hard", targetSha.trim()], { cwd: gitRoot });
          });
          setJson4(res, 200, { data: await readGitHeaderState(gitRoot) });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to reset branch to commit") });
        }
        return;
      }
      if (req.method === "PUT" && url.pathname === "/codex-api/workspace-roots-state") {
        const payload = await readJsonBody2(req);
        const record = asRecord6(payload);
        if (!record) {
          setJson4(res, 400, { error: "Invalid body: expected object" });
          return;
        }
        await updateWorkspaceRootsState((existingState) => ({
          order: normalizeStringArray(record.order),
          labels: normalizeStringRecord(record.labels),
          active: normalizeStringArray(record.active),
          projectOrder: Array.isArray(record.projectOrder) ? normalizeStringArray(record.projectOrder) : existingState.projectOrder,
          remoteProjects: existingState.remoteProjects
        }));
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "PUT" && url.pathname === "/codex-api/thread-queue-state") {
        const payload = await readJsonBody2(req);
        const record = asRecord6(payload);
        if (!record) {
          setJson4(res, 400, { error: "Invalid body: expected object" });
          return;
        }
        await writeThreadQueueState(normalizeThreadQueueState(record));
        void backendQueueProcessor.scheduleAllQueuedThreads();
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/project-root") {
        const payload = asRecord6(await readJsonBody2(req));
        const rawPath = typeof payload?.path === "string" ? payload.path.trim() : "";
        const createIfMissing = payload?.createIfMissing === true;
        const label = typeof payload?.label === "string" ? payload.label : "";
        if (!rawPath) {
          setJson4(res, 400, { error: "Missing path" });
          return;
        }
        const normalizedPath = isAbsolute2(rawPath) ? rawPath : resolve2(rawPath);
        let pathExists = true;
        try {
          const info = await stat4(normalizedPath);
          if (!info.isDirectory()) {
            setJson4(res, 400, { error: "Path exists but is not a directory" });
            return;
          }
        } catch {
          pathExists = false;
        }
        if (!pathExists && createIfMissing) {
          await mkdir4(normalizedPath, { recursive: true });
        } else if (!pathExists) {
          setJson4(res, 404, { error: "Directory does not exist" });
          return;
        }
        await persistWorkspaceRoot(normalizedPath, label);
        setJson4(res, 200, { data: { path: normalizedPath } });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/local-directory") {
        const payload = asRecord6(await readJsonBody2(req));
        const rawPath = typeof payload?.path === "string" ? payload.path.trim() : "";
        if (!rawPath) {
          setJson4(res, 400, { error: "Missing path" });
          return;
        }
        const normalizedPath = isAbsolute2(rawPath) ? rawPath : resolve2(rawPath);
        try {
          const info = await stat4(normalizedPath);
          if (!info.isDirectory()) {
            setJson4(res, 400, { error: "Path exists but is not a directory" });
            return;
          }
        } catch {
          await mkdir4(normalizedPath, { recursive: true });
        }
        setJson4(res, 200, { data: { path: normalizedPath } });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/github-clone") {
        const payload = asRecord6(await readJsonBody2(req));
        const repoUrl = typeof payload?.url === "string" ? payload.url.trim() : "";
        const basePath = typeof payload?.basePath === "string" ? payload.basePath.trim() : "";
        try {
          const clonedPath = await cloneGithubRepositoryIntoBase(repoUrl, basePath);
          setJson4(res, 200, { data: { path: clonedPath } });
        } catch (error) {
          setJson4(res, 400, { error: error instanceof Error ? error.message : "Failed to clone GitHub repository" });
        }
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/projectless-thread-cwd") {
        const payload = asRecord6(await readJsonBody2(req));
        const prompt = typeof payload?.prompt === "string" ? payload.prompt : null;
        try {
          const directory = await createProjectlessThreadDirectory(prompt);
          setJson4(res, 200, { data: directory });
        } catch (error) {
          setJson4(res, 500, { error: error instanceof Error ? error.message : "Failed to create new chat folder" });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/project-root-suggestion") {
        const basePath = url.searchParams.get("basePath")?.trim() ?? "";
        if (!basePath) {
          setJson4(res, 400, { error: "Missing basePath" });
          return;
        }
        const normalizedBasePath = isAbsolute2(basePath) ? basePath : resolve2(basePath);
        try {
          const baseInfo = await stat4(normalizedBasePath);
          if (!baseInfo.isDirectory()) {
            setJson4(res, 400, { error: "basePath is not a directory" });
            return;
          }
        } catch {
          setJson4(res, 404, { error: "basePath does not exist" });
          return;
        }
        let index = 1;
        while (index < 1e5) {
          const candidateName = `New Project (${String(index)})`;
          const candidatePath = join6(normalizedBasePath, candidateName);
          try {
            await stat4(candidatePath);
            index += 1;
            continue;
          } catch {
            setJson4(res, 200, { data: { name: candidateName, path: candidatePath } });
            return;
          }
        }
        setJson4(res, 500, { error: "Failed to compute project name suggestion" });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/composer-file-search") {
        const payload = asRecord6(await readJsonBody2(req));
        const rawCwd = typeof payload?.cwd === "string" ? payload.cwd.trim() : "";
        const query = typeof payload?.query === "string" ? payload.query.trim() : "";
        const limitRaw = typeof payload?.limit === "number" ? payload.limit : 20;
        const limit = Math.max(1, Math.min(100, Math.floor(limitRaw)));
        if (!rawCwd) {
          setJson4(res, 400, { error: "Missing cwd" });
          return;
        }
        const cwd = isAbsolute2(rawCwd) ? rawCwd : resolve2(rawCwd);
        try {
          const info = await stat4(cwd);
          if (!info.isDirectory()) {
            setJson4(res, 400, { error: "cwd is not a directory" });
            return;
          }
        } catch {
          setJson4(res, 404, { error: "cwd does not exist" });
          return;
        }
        try {
          const files = await listFilesWithRipgrep(cwd);
          const scored = files.map((path) => ({ path, score: scoreFileCandidate(path, query) })).filter((row) => query.length === 0 || row.score < 10).sort((a, b) => a.score - b.score || a.path.localeCompare(b.path)).slice(0, limit).map((row) => ({ path: row.path }));
          setJson4(res, 200, { data: scored });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to search files") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/prompts") {
        setJson4(res, 200, { data: await listComposerPrompts() });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/prompts") {
        const payload = asRecord6(await readJsonBody2(req));
        const name = typeof payload?.name === "string" ? payload.name.trim() : "";
        const content = typeof payload?.content === "string" ? payload.content : "";
        if (!name || !content.trim()) {
          setJson4(res, 400, { error: "Prompt name and content are required" });
          return;
        }
        try {
          const prompt = await createComposerPromptFile(name, content);
          setJson4(res, 200, { data: prompt });
        } catch (error) {
          setJson4(res, 500, { error: getErrorMessage6(error, "Failed to create prompt") });
        }
        return;
      }
      if (req.method === "DELETE" && url.pathname === "/codex-api/prompts") {
        const promptPath = url.searchParams.get("path")?.trim() ?? "";
        if (!promptPath) {
          setJson4(res, 400, { error: "Missing path" });
          return;
        }
        try {
          const removed = await removeComposerPromptFile(promptPath);
          setJson4(res, 200, { data: { removed } });
        } catch (error) {
          setJson4(res, 400, { error: getErrorMessage6(error, "Failed to remove prompt") });
        }
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-titles") {
        const cache = await readMergedThreadTitleCache();
        setJson4(res, 200, { data: cache });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-pins") {
        const threadIds = await readPinnedThreadIds();
        setJson4(res, 200, { data: { threadIds } });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/preferences/first-launch-plugins-card") {
        const dismissed = await readFirstLaunchPluginsCardDismissed();
        setJson4(res, 200, { data: { dismissed } });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-automations") {
        const automationsByThreadId = await listThreadHeartbeatAutomations();
        setJson4(res, 200, { data: toAutomationApiMap(automationsByThreadId) });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/project-automations") {
        const automationsByProjectName = await listProjectCronAutomations();
        setJson4(res, 200, { data: toAutomationApiMap(automationsByProjectName) });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/thread-automation") {
        const threadId = url.searchParams.get("threadId")?.trim() ?? "";
        const automationId = url.searchParams.get("automationId")?.trim() ?? "";
        if (!threadId) {
          setJson4(res, 400, { error: "Missing threadId" });
          return;
        }
        const automation = automationId ? await readThreadHeartbeatAutomation(threadId, automationId) : await readThreadHeartbeatAutomations(threadId);
        setJson4(res, 200, { data: toAutomationApiData(automation) });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/project-automation") {
        const projectName = url.searchParams.get("projectName")?.trim() ?? "";
        const automationId = url.searchParams.get("automationId")?.trim() ?? "";
        if (!projectName) {
          setJson4(res, 400, { error: "Missing projectName" });
          return;
        }
        const automation = automationId ? await readProjectCronAutomation(projectName, automationId) : await readProjectCronAutomations(projectName);
        setJson4(res, 200, { data: toAutomationApiData(automation) });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/thread-search") {
        const payload = asRecord6(await readJsonBody2(req));
        const query = typeof payload?.query === "string" ? payload.query.trim() : "";
        const limitRaw = typeof payload?.limit === "number" ? payload.limit : 200;
        const limit = Math.max(1, Math.min(1e3, Math.floor(limitRaw)));
        if (!query) {
          setJson4(res, 200, { data: { threadIds: [], indexedThreadCount: 0 } });
          return;
        }
        const index = await getThreadSearchIndex();
        const matchedIds = Array.from(index.docsById.entries()).filter(([, doc]) => isExactPhraseMatch(query, doc)).slice(0, limit).map(([id]) => id);
        setJson4(res, 200, { data: { threadIds: matchedIds, indexedThreadCount: index.docsById.size } });
        return;
      }
      if (req.method === "PUT" && url.pathname === "/codex-api/thread-titles") {
        const payload = asRecord6(await readJsonBody2(req));
        const id = typeof payload?.id === "string" ? payload.id : "";
        const title = typeof payload?.title === "string" ? payload.title : "";
        if (!id) {
          setJson4(res, 400, { error: "Missing id" });
          return;
        }
        const cache = await readThreadTitleCache();
        const next2 = title ? updateThreadTitleCache(cache, id, title) : removeFromThreadTitleCache(cache, id);
        await writeThreadTitleCache(next2);
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "PUT" && url.pathname === "/codex-api/thread-pins") {
        const payload = asRecord6(await readJsonBody2(req));
        const threadIds = normalizePinnedThreadIds(payload?.threadIds);
        await writePinnedThreadIds(threadIds);
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "PUT" && url.pathname === "/codex-api/preferences/first-launch-plugins-card") {
        const payload = asRecord6(await readJsonBody2(req));
        const dismissed = payload?.dismissed === true;
        await writeFirstLaunchPluginsCardDismissed(dismissed);
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "PUT" && url.pathname === "/codex-api/thread-automation") {
        const payload = asRecord6(await readJsonBody2(req));
        const threadId = typeof payload?.threadId === "string" ? payload.threadId.trim() : "";
        const id = typeof payload?.id === "string" ? payload.id.trim() : "";
        const name = typeof payload?.name === "string" ? payload.name.trim() : "";
        const prompt = typeof payload?.prompt === "string" ? payload.prompt.trim() : "";
        const rrule = typeof payload?.rrule === "string" ? payload.rrule.trim() : "";
        const status = payload?.status === "PAUSED" ? "PAUSED" : "ACTIVE";
        if (!threadId || !name || !prompt || !rrule) {
          setJson4(res, 400, { error: "threadId, name, prompt, and rrule are required" });
          return;
        }
        const automation = await writeThreadHeartbeatAutomation({ threadId, id, name, prompt, rrule, status });
        setJson4(res, 200, { data: toAutomationApiRecord(automation) });
        return;
      }
      if (req.method === "PUT" && url.pathname === "/codex-api/project-automation") {
        const payload = asRecord6(await readJsonBody2(req));
        const projectName = typeof payload?.projectName === "string" ? payload.projectName.trim() : "";
        const id = typeof payload?.id === "string" ? payload.id.trim() : "";
        const name = typeof payload?.name === "string" ? payload.name.trim() : "";
        const prompt = typeof payload?.prompt === "string" ? payload.prompt.trim() : "";
        const rrule = typeof payload?.rrule === "string" ? payload.rrule.trim() : "";
        const status = payload?.status === "PAUSED" ? "PAUSED" : "ACTIVE";
        if (!projectName || !name || !prompt || !rrule) {
          setJson4(res, 400, { error: "projectName, name, prompt, and rrule are required" });
          return;
        }
        if (!isAbsoluteLikePath(projectName)) {
          setJson4(res, 400, { error: "Project automation cwd must be an absolute path" });
          return;
        }
        const automation = await writeProjectCronAutomation({ projectName, id, name, prompt, rrule, status });
        setJson4(res, 200, { data: toAutomationApiRecord(automation) });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/thread-automation/run") {
        const payload = asRecord6(await readJsonBody2(req));
        const threadId = typeof payload?.threadId === "string" ? payload.threadId.trim() : "";
        const automationId = typeof payload?.automationId === "string" ? payload.automationId.trim() : "";
        if (!threadId || !automationId) {
          setJson4(res, 400, { error: "threadId and automationId are required" });
          return;
        }
        const automation = await readThreadHeartbeatAutomation(threadId, automationId);
        if (!automation) {
          setJson4(res, 404, { error: "Automation not found for thread" });
          return;
        }
        await appendThreadQueuedMessage(threadId, buildHeartbeatQueuedMessage(automation));
        backendQueueProcessor.scheduleThreadQueueDrain(threadId, 0);
        setJson4(res, 200, { data: { queued: true } });
        return;
      }
      if (req.method === "DELETE" && url.pathname === "/codex-api/thread-automation") {
        const threadId = url.searchParams.get("threadId")?.trim() ?? "";
        const automationId = url.searchParams.get("automationId")?.trim() ?? "";
        if (!threadId) {
          setJson4(res, 400, { error: "Missing threadId" });
          return;
        }
        const removed = await deleteThreadHeartbeatAutomation(threadId, automationId);
        setJson4(res, 200, { data: { removed } });
        return;
      }
      if (req.method === "DELETE" && url.pathname === "/codex-api/project-automation") {
        const projectName = url.searchParams.get("projectName")?.trim() ?? "";
        const automationId = url.searchParams.get("automationId")?.trim() ?? "";
        if (!projectName) {
          setJson4(res, 400, { error: "Missing projectName" });
          return;
        }
        const removed = await deleteProjectCronAutomation(projectName, automationId);
        setJson4(res, 200, { data: { removed } });
        return;
      }
      if (req.method === "POST" && url.pathname === "/codex-api/telegram/configure-bot") {
        const payload = asRecord6(await readJsonBody2(req));
        const botToken = typeof payload?.botToken === "string" ? payload.botToken.trim() : "";
        const rawAllowedUserIds = Array.isArray(payload?.allowedUserIds) ? payload.allowedUserIds : [];
        if (!botToken) {
          setJson4(res, 400, { error: "Missing botToken" });
          return;
        }
        const config = normalizeTelegramBridgeConfig({
          botToken,
          allowedUserIds: rawAllowedUserIds
        });
        if (config.allowedUserIds.length === 0) {
          setJson4(res, 400, { error: "At least one allowed Telegram user ID is required" });
          return;
        }
        telegramBridge.configureToken(config.botToken);
        telegramBridge.configureAllowedUserIds(config.allowedUserIds);
        telegramBridge.start();
        const existingConfig = await readTelegramBridgeConfig();
        await writeTelegramBridgeConfig({
          botToken: config.botToken,
          chatIds: existingConfig.chatIds,
          allowedUserIds: config.allowedUserIds
        });
        setJson4(res, 200, { ok: true });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/telegram/config") {
        const config = await readTelegramBridgeConfig();
        setJson4(res, 200, {
          data: {
            botToken: config.botToken,
            allowedUserIds: config.allowedUserIds
          }
        });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/telegram/status") {
        setJson4(res, 200, { data: telegramBridge.getStatus() });
        return;
      }
      if (req.method === "GET" && url.pathname === "/codex-api/events") {
        res.statusCode = 200;
        res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
        res.setHeader("Cache-Control", "no-cache, no-transform");
        res.setHeader("Connection", "keep-alive");
        res.setHeader("X-Accel-Buffering", "no");
        const unsubscribe = middleware.subscribeNotifications((notification) => {
          if (res.writableEnded || res.destroyed) return;
          res.write(`data: ${JSON.stringify(notification)}

`);
        });
        res.write(`event: ready
data: ${JSON.stringify({ ok: true })}

`);
        const keepAlive = setInterval(() => {
          res.write(": ping\n\n");
        }, 15e3);
        const close = () => {
          clearInterval(keepAlive);
          unsubscribe();
          if (!res.writableEnded) {
            res.end();
          }
        };
        req.on("close", close);
        req.on("aborted", close);
        return;
      }
      next();
    } catch (error) {
      const message = getErrorMessage6(error, "Unknown bridge error");
      setJson4(res, 502, { error: message });
    }
  };
  middleware.dispose = () => {
    threadSearchIndex = null;
    telegramBridge.stop();
    terminalManager.dispose();
    backendQueueProcessor.dispose();
    appServer.dispose();
  };
  middleware.subscribeNotifications = (listener) => {
    const unsubscribeAppServer = appServer.onNotification((notification) => {
      listener({
        ...notification,
        atIso: (/* @__PURE__ */ new Date()).toISOString()
      });
    });
    const unsubscribeTerminal = terminalManager.subscribe((notification) => {
      listener({
        ...notification,
        atIso: (/* @__PURE__ */ new Date()).toISOString()
      });
    });
    return () => {
      unsubscribeAppServer();
      unsubscribeTerminal();
    };
  };
  return middleware;
}

// src/server/authMiddleware.ts
import { randomBytes as randomBytes2, timingSafeEqual } from "crypto";
import { existsSync as existsSync5, mkdirSync, readFileSync as readFileSync3, renameSync, writeFileSync as writeFileSync2 } from "fs";
import { homedir as homedir6 } from "os";
import { dirname as dirname3, join as join7 } from "path";
var TOKEN_COOKIE = "portal_session";
var SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1e3;
var SESSION_STORE_FILE = "webui-auth-sessions.json";
var MAX_PERSISTED_TOKENS = 128;
function constantTimeCompare(a, b) {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return timingSafeEqual(bufA, bufB);
}
function parseCookies(header) {
  const cookies = {};
  if (!header) return cookies;
  for (const pair of header.split(";")) {
    const idx = pair.indexOf("=");
    if (idx === -1) continue;
    const key = pair.slice(0, idx).trim();
    const value = pair.slice(idx + 1).trim();
    cookies[key] = value;
  }
  return cookies;
}
function isLocalhostRemote(remote) {
  return remote === "127.0.0.1" || remote === "::1" || remote === "::ffff:127.0.0.1";
}
function isLocalhostHost(host) {
  const normalized = host.toLowerCase();
  return normalized.startsWith("localhost:") || normalized === "localhost" || normalized.startsWith("127.0.0.1:");
}
function isIPv4Octet(value) {
  if (!/^\d{1,3}$/.test(value)) return false;
  const parsed = Number.parseInt(value, 10);
  return parsed >= 0 && parsed <= 255;
}
function isTrustedTailscaleIPv4(remote) {
  const normalized = remote.startsWith("::ffff:") ? remote.slice("::ffff:".length) : remote;
  const parts = normalized.split(".");
  if (parts.length !== 4 || !parts.every(isIPv4Octet)) {
    return false;
  }
  const first = Number.parseInt(parts[0] ?? "", 10);
  const second = Number.parseInt(parts[1] ?? "", 10);
  return first === 100 && second >= 64 && second <= 127;
}
function isTrustedTailscaleIPv6(remote) {
  const normalized = remote.toLowerCase();
  return normalized === "fd7a:115c:a1e0::1" || normalized.startsWith("fd7a:115c:a1e0:");
}
function isTrustedTailscaleRemote(remote) {
  return isTrustedTailscaleIPv4(remote) || isTrustedTailscaleIPv6(remote);
}
function getCodexHomeDir4() {
  const codexHome = process.env.CODEX_HOME?.trim();
  return codexHome && codexHome.length > 0 ? codexHome : join7(homedir6(), ".codex");
}
function getSessionStorePath() {
  return join7(getCodexHomeDir4(), SESSION_STORE_FILE);
}
function readPersistedSessions() {
  const sessionStorePath = getSessionStorePath();
  if (!existsSync5(sessionStorePath)) return /* @__PURE__ */ new Map();
  try {
    const raw = readFileSync3(sessionStorePath, "utf8");
    const parsed = JSON.parse(raw);
    const now = Date.now();
    const sessions = /* @__PURE__ */ new Map();
    for (const entry of parsed.tokens ?? []) {
      const token = typeof entry?.value === "string" ? entry.value : "";
      const expiresAt = typeof entry?.expiresAt === "number" ? entry.expiresAt : 0;
      if (!token || !Number.isFinite(expiresAt) || expiresAt <= now) continue;
      sessions.set(token, expiresAt);
    }
    return sessions;
  } catch {
    return /* @__PURE__ */ new Map();
  }
}
function persistSessions(validTokens) {
  const sessionStorePath = getSessionStorePath();
  mkdirSync(dirname3(sessionStorePath), { recursive: true });
  const tokens = Array.from(validTokens.entries()).sort((left, right) => right[1] - left[1]).slice(0, MAX_PERSISTED_TOKENS).map(([value, expiresAt]) => ({ value, expiresAt }));
  const tmpPath = `${sessionStorePath}.tmp`;
  writeFileSync2(tmpPath, `${JSON.stringify({ tokens }, null, 2)}
`, { encoding: "utf8", mode: 384 });
  renameSync(tmpPath, sessionStorePath);
}
function tryPersistSessions(validTokens) {
  try {
    persistSessions(validTokens);
  } catch (error) {
    console.warn("[auth] failed to persist login sessions:", error);
  }
}
function pruneExpiredSessions(validTokens) {
  const now = Date.now();
  let changed = false;
  for (const [token, expiresAt] of validTokens.entries()) {
    if (expiresAt > now) continue;
    validTokens.delete(token);
    changed = true;
  }
  return changed;
}
function buildSessionCookie(token, expiresAt) {
  const maxAgeSeconds = Math.max(0, Math.floor((expiresAt - Date.now()) / 1e3));
  return [
    `${TOKEN_COOKIE}=${token}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${String(maxAgeSeconds)}`,
    `Expires=${new Date(expiresAt).toUTCString()}`
  ].join("; ");
}
function isAuthorizedByRequestLike(remoteAddress, hostHeader, cookieHeader, validTokens) {
  const remote = remoteAddress ?? "";
  if (isLocalhostRemote(remote) && isLocalhostHost(hostHeader ?? "")) {
    return true;
  }
  if (isTrustedTailscaleRemote(remote)) {
    return true;
  }
  const cookies = parseCookies(cookieHeader);
  const token = cookies[TOKEN_COOKIE];
  if (!token) return false;
  const expiresAt = validTokens.get(token);
  return typeof expiresAt === "number" && expiresAt > Date.now();
}
var LOGIN_PAGE_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Codex Web</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0a0a;color:#e5e5e5;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:1rem}
.card{background:#171717;border:1px solid #262626;border-radius:12px;padding:2rem;width:100%;max-width:380px}
h1{font-size:1.25rem;font-weight:600;margin-bottom:1.5rem;text-align:center;color:#fafafa}
label{display:block;font-size:.875rem;color:#a3a3a3;margin-bottom:.5rem}
input{width:100%;padding:.625rem .75rem;background:#0a0a0a;border:1px solid #404040;border-radius:8px;color:#fafafa;font-size:1rem;outline:none;transition:border-color .15s}
input:focus{border-color:#3b82f6}
button{width:100%;padding:.625rem;margin-top:1rem;background:#3b82f6;color:#fff;border:none;border-radius:8px;font-size:.9375rem;font-weight:500;cursor:pointer;transition:background .15s}
button:hover{background:#2563eb}
.error{color:#ef4444;font-size:.8125rem;margin-top:.75rem;text-align:center;display:none}
</style>
</head>
<body>
<div class="card">
<h1>Codex Web</h1>
<form id="f">
<label for="pw">Password</label>
<input id="pw" name="password" type="password" autocomplete="current-password" autofocus required>
<button type="submit">Sign in</button>
<p class="error" id="err">Incorrect password</p>
</form>
</div>
<script>
const form=document.getElementById('f');
const errEl=document.getElementById('err');
form.addEventListener('submit',async e=>{
  e.preventDefault();
  errEl.style.display='none';
  const res=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('pw').value})});
  if(res.ok){window.location.reload()}else{errEl.style.display='block';document.getElementById('pw').value='';document.getElementById('pw').focus()}
});
</script>
</body>
</html>`;
function createAuthSession(password) {
  const validTokens = readPersistedSessions();
  if (pruneExpiredSessions(validTokens)) {
    tryPersistSessions(validTokens);
  }
  const middleware = (req, res, next) => {
    if (pruneExpiredSessions(validTokens)) {
      tryPersistSessions(validTokens);
    }
    if (isAuthorizedByRequestLike(req.socket.remoteAddress, req.headers.host, req.headers.cookie, validTokens)) {
      next();
      return;
    }
    if (req.method === "POST" && req.path === "/auth/login") {
      let body = "";
      req.setEncoding("utf8");
      req.on("data", (chunk) => {
        body += chunk;
      });
      req.on("end", () => {
        let parsed;
        try {
          parsed = JSON.parse(body);
        } catch {
          res.status(400).json({ error: "Invalid request body" });
          return;
        }
        const provided = typeof parsed.password === "string" ? parsed.password : "";
        if (!constantTimeCompare(provided, password)) {
          res.status(401).json({ error: "Invalid password" });
          return;
        }
        try {
          const token = randomBytes2(32).toString("hex");
          const expiresAt = Date.now() + SESSION_TTL_MS;
          validTokens.set(token, expiresAt);
          tryPersistSessions(validTokens);
          res.setHeader("Set-Cookie", buildSessionCookie(token, expiresAt));
          res.json({ ok: true });
        } catch {
          res.status(500).json({ error: "Failed to create login session" });
        }
      });
      return;
    }
    if (req.method === "GET" && req.path.startsWith("/password=")) {
      const provided = req.path.slice("/password=".length);
      if (constantTimeCompare(provided, password)) {
        const token = randomBytes2(32).toString("hex");
        const expiresAt = Date.now() + SESSION_TTL_MS;
        validTokens.set(token, expiresAt);
        tryPersistSessions(validTokens);
        res.setHeader("Set-Cookie", buildSessionCookie(token, expiresAt));
        res.redirect(302, "/");
        return;
      }
    }
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.status(200).send(LOGIN_PAGE_HTML);
  };
  return {
    middleware,
    isRequestAuthorized: (req) => isAuthorizedByRequestLike(req.socket.remoteAddress, req.headers.host, req.headers.cookie, validTokens)
  };
}

// src/server/localBrowseUi.ts
import { dirname as dirname4, extname as extname2, join as join8 } from "path";
import { open, readFile as readFile4, readdir as readdir3, stat as stat5 } from "fs/promises";
var TEXT_EDITABLE_EXTENSIONS = /* @__PURE__ */ new Set([
  ".txt",
  ".md",
  ".json",
  ".js",
  ".ts",
  ".tsx",
  ".jsx",
  ".css",
  ".scss",
  ".html",
  ".htm",
  ".xml",
  ".yml",
  ".yaml",
  ".log",
  ".csv",
  ".env",
  ".py",
  ".sh",
  ".toml",
  ".ini",
  ".conf",
  ".sql",
  ".bat",
  ".cmd",
  ".ps1"
]);
function languageForPath(pathValue) {
  const extension = extname2(pathValue).toLowerCase();
  switch (extension) {
    case ".js":
      return "javascript";
    case ".ts":
      return "typescript";
    case ".jsx":
      return "javascript";
    case ".tsx":
      return "typescript";
    case ".py":
      return "python";
    case ".sh":
      return "sh";
    case ".css":
    case ".scss":
      return "css";
    case ".html":
    case ".htm":
      return "html";
    case ".json":
      return "json";
    case ".md":
      return "markdown";
    case ".yaml":
    case ".yml":
      return "yaml";
    case ".xml":
      return "xml";
    case ".sql":
      return "sql";
    case ".toml":
      return "ini";
    case ".ini":
    case ".conf":
      return "ini";
    default:
      return "plaintext";
  }
}
function normalizeLocalPath(rawPath) {
  const trimmed = rawPath.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("file://")) {
    try {
      return decodeURIComponent(trimmed.replace(/^file:\/\//u, ""));
    } catch {
      return trimmed.replace(/^file:\/\//u, "");
    }
  }
  return trimmed;
}
function decodeBrowsePath(rawPath) {
  if (!rawPath) return "";
  try {
    return decodeURIComponent(rawPath);
  } catch {
    return rawPath;
  }
}
function isTextEditablePath(pathValue) {
  return TEXT_EDITABLE_EXTENSIONS.has(extname2(pathValue).toLowerCase());
}
function isHiddenName(value) {
  return value.startsWith(".");
}
function looksLikeTextBuffer(buffer) {
  if (buffer.length === 0) return true;
  for (const byte of buffer) {
    if (byte === 0) return false;
  }
  const decoded = buffer.toString("utf8");
  const replacementCount = (decoded.match(/\uFFFD/gu) ?? []).length;
  return replacementCount / decoded.length < 0.05;
}
async function probeFileIsText(localPath) {
  const handle = await open(localPath, "r");
  try {
    const sample = Buffer.allocUnsafe(4096);
    const { bytesRead } = await handle.read(sample, 0, sample.length, 0);
    return looksLikeTextBuffer(sample.subarray(0, bytesRead));
  } finally {
    await handle.close();
  }
}
async function isTextEditableFile(localPath) {
  if (isTextEditablePath(localPath)) return true;
  try {
    const fileStat = await stat5(localPath);
    if (!fileStat.isFile()) return false;
    return await probeFileIsText(localPath);
  } catch {
    return false;
  }
}
function escapeHtml2(value) {
  return value.replace(/&/gu, "&amp;").replace(/</gu, "&lt;").replace(/>/gu, "&gt;").replace(/"/gu, "&quot;").replace(/'/gu, "&#39;");
}
function normalizeNewProjectName(value) {
  return value.trim().replace(/[\\/]+/gu, "").trim();
}
function toBrowseHref(pathValue, newProjectName = "") {
  const normalizedName = normalizeNewProjectName(newProjectName);
  const query = normalizedName ? `?newProjectName=${encodeURIComponent(normalizedName)}` : "";
  return `/codex-local-browse${encodeURI(pathValue)}${query}`;
}
function toEditHref(pathValue, newProjectName = "") {
  const normalizedName = normalizeNewProjectName(newProjectName);
  const query = normalizedName ? `?newProjectName=${encodeURIComponent(normalizedName)}` : "";
  return `/codex-local-edit${encodeURI(pathValue)}${query}`;
}
function escapeForInlineScriptString(value) {
  return JSON.stringify(value).replace(/<\//gu, "<\\/").replace(/<!--/gu, "<\\!--").replace(/\u2028/gu, "\\u2028").replace(/\u2029/gu, "\\u2029");
}
async function getDirectoryItems(localPath) {
  const entries = await readdir3(localPath, { withFileTypes: true });
  const withMeta = await Promise.all(entries.map(async (entry) => {
    const entryPath = join8(localPath, entry.name);
    const entryStat = await stat5(entryPath);
    const editable = !entry.isDirectory() && await isTextEditableFile(entryPath);
    return {
      name: entry.name,
      path: entryPath,
      isDirectory: entry.isDirectory(),
      editable,
      mtimeMs: entryStat.mtimeMs
    };
  }));
  return withMeta.sort((a, b) => {
    if (b.mtimeMs !== a.mtimeMs) return b.mtimeMs - a.mtimeMs;
    if (a.isDirectory && !b.isDirectory) return -1;
    if (!a.isDirectory && b.isDirectory) return 1;
    return a.name.localeCompare(b.name);
  });
}
function projectCreationTargetPath(parentPath, newProjectName) {
  const normalizedName = normalizeNewProjectName(newProjectName);
  if (!normalizedName) return "";
  return join8(parentPath, normalizedName);
}
function projectCreationButtonLabel(newProjectName) {
  const normalizedName = normalizeNewProjectName(newProjectName);
  return normalizedName ? `Create ${normalizedName} here` : "";
}
function projectCreationStatusText(newProjectName) {
  const normalizedName = normalizeNewProjectName(newProjectName);
  return normalizedName ? `Creating ${normalizedName} in Codex...` : "Creating project in Codex...";
}
function openFolderStatusText(newProjectName) {
  const normalizedName = normalizeNewProjectName(newProjectName);
  return normalizedName ? `Opening folder in Codex without creating ${normalizedName}...` : "Opening folder in Codex...";
}
function failureStatusText(newProjectName) {
  const normalizedName = normalizeNewProjectName(newProjectName);
  return normalizedName ? `Failed to open folder or create ${normalizedName}.` : "Failed to open folder.";
}
function actionButtonsHtml(localPath, newProjectName) {
  const normalizedName = normalizeNewProjectName(newProjectName);
  const createTargetPath = projectCreationTargetPath(localPath, normalizedName);
  const createButton = createTargetPath ? `<button class="header-open-btn create-project-btn" type="button" aria-label="${escapeHtml2(projectCreationButtonLabel(normalizedName))}" title="${escapeHtml2(projectCreationButtonLabel(normalizedName))}" data-path="${escapeHtml2(createTargetPath)}" data-label="${escapeHtml2(normalizedName)}" data-status="${escapeHtml2(projectCreationStatusText(normalizedName))}" data-error="${escapeHtml2(failureStatusText(normalizedName))}">${escapeHtml2(projectCreationButtonLabel(normalizedName))}</button>` : "";
  const openButton = `<button class="header-open-btn open-folder-btn" type="button" aria-label="Open current folder in Codex" title="Open folder in Codex" data-path="${escapeHtml2(localPath)}" data-label="" data-status="${escapeHtml2(openFolderStatusText(normalizedName))}" data-error="${escapeHtml2(failureStatusText(normalizedName))}">Open folder in Codex</button>`;
  return `${createButton}${openButton}`;
}
async function getLocalDirectoryListing(localPath, options = {}) {
  const entries = await readdir3(localPath, { withFileTypes: true });
  const directories = entries.filter((entry) => entry.isDirectory()).map((entry) => ({
    name: entry.name,
    path: join8(localPath, entry.name)
  })).filter((entry) => options.showHidden === true || !isHiddenName(entry.name)).sort((a, b) => {
    const aHidden = isHiddenName(a.name);
    const bHidden = isHiddenName(b.name);
    if (aHidden !== bHidden) return aHidden ? -1 : 1;
    return a.name.localeCompare(b.name, void 0, { numeric: true, sensitivity: "base" });
  });
  return {
    path: localPath,
    parentPath: dirname4(localPath),
    entries: directories
  };
}
async function createDirectoryListingHtml(localPath, options) {
  const newProjectName = normalizeNewProjectName(options?.newProjectName ?? "");
  const items = await getDirectoryItems(localPath);
  const parentPath = dirname4(localPath);
  const rows = items.map((item) => {
    const suffix = item.isDirectory ? "/" : "";
    const editAction = item.editable ? ` <a class="icon-btn" aria-label="Edit ${escapeHtml2(item.name)}" href="${escapeHtml2(toEditHref(item.path, newProjectName))}" title="Edit">\u270F\uFE0F</a>` : "";
    return `<li class="file-row"><a class="file-link" href="${escapeHtml2(toBrowseHref(item.path, newProjectName))}">${escapeHtml2(item.name)}${suffix}</a><span class="row-actions">${editAction}</span></li>`;
  }).join("\n");
  const parentLink = localPath !== parentPath ? `<a class="header-parent-link" href="${escapeHtml2(toBrowseHref(parentPath, newProjectName))}">..</a>` : "";
  const pickerSummary = newProjectName ? `<p class="picker-summary">Browse to the parent folder where you want to create <strong>${escapeHtml2(newProjectName)}</strong>, or open the current folder directly.</p>` : "";
  const actionButtons = actionButtonsHtml(localPath, newProjectName);
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Index of ${escapeHtml2(localPath)}</title>
  <style>
    body { font-family: ui-monospace, Menlo, Monaco, monospace; margin: 16px; background: #0b1020; color: #dbe6ff; }
    a { color: #8cc2ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    ul { list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 8px; }
    .file-row { display: grid; grid-template-columns: minmax(0,1fr) auto; align-items: center; gap: 10px; }
    .file-link { display: block; padding: 10px 12px; border: 1px solid #28405f; border-radius: 10px; background: #0f1b33; overflow-wrap: anywhere; }
    .header-actions { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
    .header-parent-link { color: #9ec8ff; font-size: 14px; padding: 8px 10px; border: 1px solid #2a4569; border-radius: 10px; background: #101f3a; }
    .header-parent-link:hover { text-decoration: none; filter: brightness(1.08); }
    .header-open-btn {
      height: 42px;
      padding: 0 14px;
      border: 1px solid #4f8de0;
      border-radius: 10px;
      background: linear-gradient(135deg, #2e6ee6 0%, #3d8cff 100%);
      color: #eef6ff;
      font-weight: 700;
      letter-spacing: 0.01em;
      cursor: pointer;
      box-shadow: 0 6px 18px rgba(33, 90, 199, 0.35);
    }
    .header-open-btn:hover { filter: brightness(1.08); }
    .header-open-btn:disabled { opacity: 0.6; cursor: default; }
    .picker-summary { margin: 10px 0 0; color: #b8d5ff; max-width: 60rem; line-height: 1.45; }
    .row-actions { display: inline-flex; align-items: center; gap: 8px; min-width: 42px; justify-content: flex-end; }
    .icon-btn { display: inline-flex; align-items: center; justify-content: center; width: 42px; height: 42px; border: 1px solid #36557a; border-radius: 10px; background: #162643; color: #dbe6ff; text-decoration: none; cursor: pointer; }
    .icon-btn:hover { filter: brightness(1.08); text-decoration: none; }
    .status { margin: 10px 0 0; color: #8cc2ff; min-height: 1.25em; }
    h1 { font-size: 18px; margin: 0; word-break: break-all; }
    @media (max-width: 640px) {
      body { margin: 12px; }
      .file-row { gap: 8px; }
      .file-link { font-size: 15px; padding: 12px; }
      .icon-btn { width: 44px; height: 44px; }
    }
  </style>
</head>
<body>
  <h1>Index of ${escapeHtml2(localPath)}</h1>
  ${pickerSummary}
  <div class="header-actions">
    ${parentLink}
    ${actionButtons}
  </div>
  <p id="status" class="status"></p>
  <ul>${rows}</ul>
  <script>
    const status = document.getElementById('status');
    document.addEventListener('click', async (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest('.open-folder-btn, .create-project-btn');
      if (!(button instanceof HTMLButtonElement)) return;

      const path = button.getAttribute('data-path') || '';
      const label = button.getAttribute('data-label') || '';
      const statusText = button.getAttribute('data-status') || 'Opening folder in Codex...';
      const errorText = button.getAttribute('data-error') || 'Failed to open folder.';
      if (!path) return;
      button.disabled = true;
      status.textContent = statusText;
      try {
        const response = await fetch('/codex-api/project-root', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            path,
            createIfMissing: button.classList.contains('create-project-btn'),
            label,
          }),
        });
        if (!response.ok) {
          status.textContent = errorText;
          button.disabled = false;
          return;
        }
        status.textContent = 'Folder opened. Returning to Codex...';
        const nextUrl = '/?openProjectPath=' + encodeURIComponent(path) + '#/';
        window.location.assign(nextUrl);
      } catch {
        status.textContent = errorText;
        button.disabled = false;
      }
    });
  </script>
</body>
</html>`;
}
async function createTextEditorHtml(localPath) {
  const content = await readFile4(localPath, "utf8");
  const parentPath = dirname4(localPath);
  const language = languageForPath(localPath);
  const safeContentLiteral = escapeForInlineScriptString(content);
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Edit ${escapeHtml2(localPath)}</title>
  <style>
    html, body { width: 100%; height: 100%; margin: 0; }
    body { font-family: ui-monospace, Menlo, Monaco, monospace; background: #0b1020; color: #dbe6ff; display: flex; flex-direction: column; overflow: hidden; }
    .toolbar { position: sticky; top: 0; z-index: 10; display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; background: #0b1020; border-bottom: 1px solid #243a5a; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    button, a { background: #1b2a4a; color: #dbe6ff; border: 1px solid #345; padding: 6px 10px; border-radius: 6px; text-decoration: none; cursor: pointer; }
    button:hover, a:hover { filter: brightness(1.08); }
    #editor { flex: 1 1 auto; min-height: 0; width: 100%; border: none; overflow: hidden; }
    #status { margin-left: 8px; color: #8cc2ff; }
    .ace_editor { background: #07101f !important; color: #dbe6ff !important; width: 100% !important; height: 100% !important; }
    .ace_gutter { background: #07101f !important; color: #6f8eb5 !important; }
    .ace_marker-layer .ace_active-line { background: #10213c !important; }
    .ace_marker-layer .ace_selection { background: rgba(140, 194, 255, 0.3) !important; }
    .meta { opacity: 0.9; font-size: 12px; overflow-wrap: anywhere; }
  </style>
</head>
<body>
  <div class="toolbar">
    <div class="row">
      <a href="${escapeHtml2(toBrowseHref(parentPath))}">Back</a>
      <button id="saveBtn" type="button">Save</button>
      <span id="status"></span>
    </div>
    <div class="meta">${escapeHtml2(localPath)} \xB7 ${escapeHtml2(language)}</div>
  </div>
  <div id="editor"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/ace/1.36.2/ace.js"></script>
  <script>
    const saveBtn = document.getElementById('saveBtn');
    const status = document.getElementById('status');
    const editor = ace.edit('editor');
    editor.setTheme('ace/theme/tomorrow_night');
    editor.session.setMode('ace/mode/${escapeHtml2(language)}');
    editor.setValue(${safeContentLiteral}, -1);
    editor.setOptions({
      fontSize: '13px',
      wrap: true,
      showPrintMargin: false,
      useSoftTabs: true,
      tabSize: 2,
      behavioursEnabled: true,
    });
    editor.resize();

    saveBtn.addEventListener('click', async () => {
      status.textContent = 'Saving...';
      const response = await fetch(location.pathname, {
        method: 'PUT',
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
        body: editor.getValue(),
      });
      status.textContent = response.ok ? 'Saved' : 'Save failed';
    });
  </script>
</body>
</html>`;
}

// src/server/httpServer.ts
import { WebSocketServer } from "ws";
var __dirname = dirname5(fileURLToPath(import.meta.url));
var distDir = join9(__dirname, "..", "dist");
var spaEntryFile = join9(distDir, "index.html");
var IMAGE_CONTENT_TYPES = {
  ".avif": "image/avif",
  ".bmp": "image/bmp",
  ".gif": "image/gif",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp"
};
function renderFrontendMissingHtml(message, details) {
  const lines = details && details.length > 0 ? `<pre>${details.join("\n")}</pre>` : "";
  return [
    "<!doctype html>",
    '<html lang="en">',
    '<head><meta charset="utf-8"><title>Codex Web UI Error</title></head>',
    "<body>",
    `<h1>${message}</h1>`,
    lines,
    "<p>Redirecting to chat in 3 seconds...</p>",
    '<p><a href="/">Back to chat</a></p>',
    "<script>",
    'setTimeout(() => { window.location.assign("/") }, 3000)',
    "</script>",
    "</body>",
    "</html>"
  ].join("");
}
function normalizeLocalImagePath(rawPath) {
  const trimmed = rawPath.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("file://")) {
    try {
      return decodeURIComponent(trimmed.replace(/^file:\/\//u, ""));
    } catch {
      return trimmed.replace(/^file:\/\//u, "");
    }
  }
  return trimmed;
}
function readWildcardPathParam(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.join("/");
  return "";
}
function createServer(options = {}) {
  const app = express();
  const bridge = createCodexBridgeMiddleware();
  const authSession = options.password ? createAuthSession(options.password) : null;
  if (authSession) {
    app.use(authSession.middleware);
  }
  app.use(bridge);
  app.get("/codex-local-image", (req, res) => {
    const rawPath = typeof req.query.path === "string" ? req.query.path : "";
    const localPath = normalizeLocalImagePath(rawPath);
    if (!localPath || !isAbsolute3(localPath)) {
      res.status(400).json({ error: "Expected absolute local file path." });
      return;
    }
    const contentType = IMAGE_CONTENT_TYPES[extname3(localPath).toLowerCase()];
    if (!contentType) {
      res.status(415).json({ error: "Unsupported image type." });
      return;
    }
    res.type(contentType);
    res.setHeader("Cache-Control", "private, max-age=300");
    res.sendFile(localPath, { dotfiles: "allow" }, (error) => {
      if (!error) return;
      if (!res.headersSent) res.status(404).json({ error: "Image file not found." });
    });
  });
  app.get("/codex-local-file", (req, res) => {
    const rawPath = typeof req.query.path === "string" ? req.query.path : "";
    const localPath = normalizeLocalPath(rawPath);
    if (!localPath || !isAbsolute3(localPath)) {
      res.status(400).json({ error: "Expected absolute local file path." });
      return;
    }
    res.setHeader("Cache-Control", "private, no-store");
    res.setHeader("Content-Disposition", "inline");
    res.sendFile(localPath, { dotfiles: "allow" }, (error) => {
      if (!error) return;
      if (!res.headersSent) res.status(404).json({ error: "File not found." });
    });
  });
  app.get("/codex-local-directories", async (req, res) => {
    const rawPath = typeof req.query.path === "string" ? req.query.path : "";
    const showHidden = typeof req.query.showHidden === "string" && ["1", "true", "yes", "on"].includes(req.query.showHidden.toLowerCase());
    const localPath = normalizeLocalPath(rawPath);
    if (!localPath || !isAbsolute3(localPath)) {
      res.status(400).json({ error: "Expected absolute local directory path." });
      return;
    }
    try {
      const fileStat = await stat6(localPath);
      if (!fileStat.isDirectory()) {
        res.status(400).json({ error: "Expected directory path." });
        return;
      }
      const data = await getLocalDirectoryListing(localPath, { showHidden });
      res.status(200).json({ data });
    } catch {
      res.status(404).json({ error: "Directory not found." });
    }
  });
  app.get("/codex-local-browse/*path", async (req, res) => {
    const rawPath = readWildcardPathParam(req.params.path);
    const localPath = decodeBrowsePath(`/${rawPath}`);
    const newProjectName = typeof req.query.newProjectName === "string" ? req.query.newProjectName : "";
    if (!localPath || !isAbsolute3(localPath)) {
      res.status(400).json({ error: "Expected absolute local file path." });
      return;
    }
    try {
      const fileStat = await stat6(localPath);
      res.setHeader("Cache-Control", "private, no-store");
      if (fileStat.isDirectory()) {
        const html = await createDirectoryListingHtml(localPath, { newProjectName });
        res.status(200).type("text/html; charset=utf-8").send(html);
        return;
      }
      res.sendFile(localPath, { dotfiles: "allow" }, (error) => {
        if (!error) return;
        if (!res.headersSent) res.status(404).json({ error: "File not found." });
      });
    } catch {
      res.status(404).json({ error: "File not found." });
    }
  });
  app.get("/codex-local-edit/*path", async (req, res) => {
    const rawPath = readWildcardPathParam(req.params.path);
    const localPath = decodeBrowsePath(`/${rawPath}`);
    if (!localPath || !isAbsolute3(localPath)) {
      res.status(400).json({ error: "Expected absolute local file path." });
      return;
    }
    try {
      const fileStat = await stat6(localPath);
      if (!fileStat.isFile()) {
        res.status(400).json({ error: "Expected file path." });
        return;
      }
      const html = await createTextEditorHtml(localPath);
      res.status(200).type("text/html; charset=utf-8").send(html);
    } catch {
      res.status(404).json({ error: "File not found." });
    }
  });
  app.put("/codex-local-edit/*path", express.text({ type: "*/*", limit: "10mb" }), async (req, res) => {
    const rawPath = readWildcardPathParam(req.params.path);
    const localPath = decodeBrowsePath(`/${rawPath}`);
    if (!localPath || !isAbsolute3(localPath)) {
      res.status(400).json({ error: "Expected absolute local file path." });
      return;
    }
    if (!await isTextEditableFile(localPath)) {
      res.status(415).json({ error: "Only text-like files are editable." });
      return;
    }
    const body = typeof req.body === "string" ? req.body : "";
    try {
      await writeFile5(localPath, body, "utf8");
      res.status(200).json({ ok: true });
    } catch {
      res.status(404).json({ error: "File not found." });
    }
  });
  const hasFrontendAssets = existsSync6(spaEntryFile);
  if (hasFrontendAssets) {
    app.use(express.static(distDir));
  }
  app.use((_req, res) => {
    if (!hasFrontendAssets) {
      res.status(503).type("text/html; charset=utf-8").send(
        renderFrontendMissingHtml("Codex web UI assets are missing.", [
          `Expected: ${spaEntryFile}`,
          "If running from source, build frontend assets with: pnpm run build:frontend",
          "If running with npx, clear the npx cache and reinstall codexapp."
        ])
      );
      return;
    }
    res.sendFile(spaEntryFile, (error) => {
      if (!error) return;
      if (!res.headersSent) {
        res.status(404).type("text/html; charset=utf-8").send(renderFrontendMissingHtml("Frontend entry file not found."));
      }
    });
  });
  return {
    app,
    dispose: () => bridge.dispose(),
    attachWebSocket: (server) => {
      const wss = new WebSocketServer({ noServer: true });
      server.on("upgrade", (req, socket, head) => {
        const url = new URL(req.url ?? "", "http://localhost");
        if (url.pathname !== "/codex-api/ws") {
          return;
        }
        if (authSession && !authSession.isRequestAuthorized(req)) {
          socket.write("HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n");
          socket.destroy();
          return;
        }
        wss.handleUpgrade(req, socket, head, (ws) => {
          wss.emit("connection", ws, req);
        });
      });
      wss.on("connection", (ws) => {
        ws.send(JSON.stringify({ method: "ready", params: { ok: true }, atIso: (/* @__PURE__ */ new Date()).toISOString() }));
        const unsubscribe = bridge.subscribeNotifications((notification) => {
          if (ws.readyState !== 1) return;
          ws.send(JSON.stringify(notification));
        });
        ws.on("close", unsubscribe);
        ws.on("error", unsubscribe);
      });
    }
  };
}

// src/server/password.ts
import { randomInt } from "crypto";
var CHARS = "abcdefghijklmnopqrstuvwxyz0123456789";
function randomGroup(length) {
  let result = "";
  for (let i = 0; i < length; i++) {
    result += CHARS[randomInt(CHARS.length)];
  }
  return result;
}
function generatePassword() {
  return `${randomGroup(3)}-${randomGroup(3)}-${randomGroup(3)}`;
}

// src/cli/index.ts
var program = new Command().name("codexui").description("Web interface for Codex app-server");
var __dirname2 = dirname6(fileURLToPath2(import.meta.url));
var hasPromptedCloudflaredInstall = false;
function getCodexHomePath() {
  return process.env.CODEX_HOME?.trim() || join10(homedir7(), ".codex");
}
function getCloudflaredPromptMarkerPath() {
  return join10(getCodexHomePath(), ".cloudflared-install-prompted");
}
function hasPromptedCloudflaredInstallPersisted() {
  return existsSync7(getCloudflaredPromptMarkerPath());
}
async function persistCloudflaredInstallPrompted() {
  const codexHome = getCodexHomePath();
  mkdirSync2(codexHome, { recursive: true });
  await writeFile6(getCloudflaredPromptMarkerPath(), `${Date.now()}
`, "utf8");
}
async function readCliVersion() {
  try {
    const packageJsonPath = join10(__dirname2, "..", "package.json");
    const raw = await readFile5(packageJsonPath, "utf8");
    const parsed = JSON.parse(raw);
    return typeof parsed.version === "string" ? parsed.version : "unknown";
  } catch {
    return "unknown";
  }
}
function isTermuxRuntime() {
  return Boolean(process.env.TERMUX_VERSION || process.env.PREFIX?.includes("/com.termux/"));
}
function runOrFail(command, args, label) {
  const result = spawnSyncCommand(command, args, { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error(`${label} failed with exit code ${String(result.status ?? -1)}`);
  }
}
function runWithStatus(command, args) {
  const result = spawnSyncCommand(command, args, { stdio: "inherit" });
  return result.status ?? -1;
}
function resolveCloudflaredCommand() {
  if (canRunCommand("cloudflared", ["--version"])) {
    return "cloudflared";
  }
  const localCandidate = join10(homedir7(), ".local", "bin", "cloudflared");
  if (existsSync7(localCandidate) && canRunCommand(localCandidate, ["--version"])) {
    return localCandidate;
  }
  return null;
}
function mapCloudflaredLinuxArch(arch) {
  if (arch === "x64") {
    return "amd64";
  }
  if (arch === "arm64") {
    return "arm64";
  }
  return null;
}
function downloadFile(url, destination) {
  return new Promise((resolve4, reject) => {
    const request = (currentUrl) => {
      httpsGet(currentUrl, (response) => {
        const code = response.statusCode ?? 0;
        if (code >= 300 && code < 400 && response.headers.location) {
          response.resume();
          request(response.headers.location);
          return;
        }
        if (code !== 200) {
          response.resume();
          reject(new Error(`Download failed with HTTP status ${String(code)}`));
          return;
        }
        const file = createWriteStream(destination, { mode: 493 });
        response.pipe(file);
        file.on("finish", () => {
          file.close();
          resolve4();
        });
        file.on("error", reject);
      }).on("error", reject);
    };
    request(url);
  });
}
async function ensureCloudflaredInstalledLinux() {
  const current = resolveCloudflaredCommand();
  if (current) {
    return current;
  }
  if (process.platform !== "linux") {
    return null;
  }
  const mappedArch = mapCloudflaredLinuxArch(process.arch);
  if (!mappedArch) {
    throw new Error(`cloudflared auto-install is not supported for Linux architecture: ${process.arch}`);
  }
  const userBinDir = join10(homedir7(), ".local", "bin");
  mkdirSync2(userBinDir, { recursive: true });
  const destination = join10(userBinDir, "cloudflared");
  const downloadUrl = `https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${mappedArch}`;
  console.log("\ncloudflared not found. Installing to ~/.local/bin...\n");
  await downloadFile(downloadUrl, destination);
  chmodSync2(destination, 493);
  process.env.PATH = prependPathEntry(process.env.PATH ?? "", userBinDir);
  const installed = resolveCloudflaredCommand();
  if (!installed) {
    throw new Error("cloudflared download completed but executable is still not available");
  }
  console.log("\ncloudflared installed.\n");
  return installed;
}
async function shouldInstallCloudflaredInteractively() {
  if (hasPromptedCloudflaredInstall || hasPromptedCloudflaredInstallPersisted()) {
    return false;
  }
  hasPromptedCloudflaredInstall = true;
  await persistCloudflaredInstallPrompted();
  if (process.platform === "win32") {
    return false;
  }
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    console.warn("\n[cloudflared] cloudflared is missing and terminal is non-interactive, skipping install.");
    return false;
  }
  const prompt = createInterface2({ input: process.stdin, output: process.stdout });
  try {
    const answer = await prompt.question("cloudflared is not installed. Install it now to ~/.local/bin? [y/N] ");
    const normalized = answer.trim().toLowerCase();
    return normalized === "y" || normalized === "yes";
  } finally {
    prompt.close();
  }
}
async function resolveCloudflaredForTunnel() {
  const current = resolveCloudflaredCommand();
  if (current) {
    return current;
  }
  if (process.platform === "win32") {
    return null;
  }
  const installApproved = await shouldInstallCloudflaredInteractively();
  if (!installApproved) {
    return null;
  }
  return ensureCloudflaredInstalledLinux();
}
function hasCodexAuth() {
  const codexHome = getCodexHomePath();
  return existsSync7(join10(codexHome, "auth.json"));
}
function ensureCodexInstalled() {
  let codexCommand = resolveCodexCommand();
  if (!codexCommand) {
    const installWithFallback = (pkg, label) => {
      const status = runWithStatus("npm", ["install", "-g", pkg]);
      if (status === 0) {
        return;
      }
      if (isTermuxRuntime()) {
        throw new Error(`${label} failed with exit code ${String(status)}`);
      }
      const userPrefix = getUserNpmPrefix();
      console.log(`
Global npm install requires elevated permissions. Retrying with --prefix ${userPrefix}...
`);
      runOrFail("npm", ["install", "-g", "--prefix", userPrefix, pkg], `${label} (user prefix)`);
      process.env.PATH = prependPathEntry(process.env.PATH ?? "", getNpmGlobalBinDir(userPrefix));
    };
    if (isTermuxRuntime()) {
      console.log("\nCodex CLI not found. Installing Termux-compatible Codex CLI from npm...\n");
      installWithFallback("@mmmbuto/codex-cli-termux", "Codex CLI install");
      codexCommand = resolveCodexCommand();
      if (!codexCommand) {
        console.log("\nTermux npm package did not expose `codex`. Installing official CLI fallback...\n");
        installWithFallback("@openai/codex", "Codex CLI fallback install");
      }
    } else {
      console.log("\nCodex CLI not found. Installing official Codex CLI from npm...\n");
      installWithFallback("@openai/codex", "Codex CLI install");
    }
    codexCommand = resolveCodexCommand();
    if (!codexCommand && !isTermuxRuntime()) {
      throw new Error("Official Codex CLI install completed but binary is still not available in PATH");
    }
    if (!codexCommand && isTermuxRuntime()) {
      codexCommand = resolveCodexCommand();
    }
    if (!codexCommand) {
      throw new Error("Codex CLI install completed but binary is still not available in PATH");
    }
    console.log("\nCodex CLI installed.\n");
  }
  return codexCommand;
}
function resolvePassword(input) {
  if (input === false) {
    return { password: void 0, generated: false };
  }
  if (typeof input === "string") {
    return { password: input, generated: false };
  }
  return { password: generatePassword(), generated: true };
}
function getGeneratedPasswordPath() {
  return join10(getCodexHomePath(), "codexui-password");
}
async function persistGeneratedPassword(password) {
  const codexHome = getCodexHomePath();
  mkdirSync2(codexHome, { recursive: true });
  const passwordPath = getGeneratedPasswordPath();
  await writeFile6(passwordPath, `${password}
`, { encoding: "utf8", mode: 384 });
  chmodSync2(passwordPath, 384);
  return passwordPath;
}
function printTermuxKeepAlive(lines) {
  if (!isTermuxRuntime()) {
    return;
  }
  lines.push("");
  lines.push("  Android/Termux keep-alive:");
  lines.push("  1) Keep this Termux session open (do not swipe it away).");
  lines.push("  2) Disable battery optimization for Termux in Android settings.");
  lines.push("  3) Optional: run `termux-wake-lock` in another shell.");
}
function openBrowser(url) {
  const command = process.platform === "darwin" ? { cmd: "open", args: [url] } : process.platform === "win32" ? { cmd: "cmd", args: ["/c", "start", "", url] } : { cmd: "xdg-open", args: [url] };
  const child = spawn5(command.cmd, command.args, { detached: true, stdio: "ignore" });
  child.on("error", () => {
  });
  child.unref();
}
function buildTunnelAutologinUrl(tunnelUrl, _password) {
  return tunnelUrl;
}
function parseCloudflaredUrl(chunk) {
  const urlMatch = chunk.match(/https:\/\/[a-zA-Z0-9-]+\.trycloudflare\.com/g);
  if (!urlMatch || urlMatch.length === 0) {
    return null;
  }
  return urlMatch[urlMatch.length - 1] ?? null;
}
function getAccessibleUrls(port) {
  const urls = /* @__PURE__ */ new Set([`http://localhost:${String(port)}`]);
  try {
    const interfaces = networkInterfaces();
    for (const entries of Object.values(interfaces)) {
      if (!entries) {
        continue;
      }
      for (const entry of entries) {
        if (entry.internal) {
          continue;
        }
        if (entry.family === "IPv4") {
          urls.add(`http://${entry.address}:${String(port)}`);
        }
      }
    }
  } catch {
  }
  return Array.from(urls);
}
function isTailscaleIPv4Address(address) {
  const parts = address.split(".");
  if (parts.length !== 4) return false;
  const octets = parts.map((part) => Number.parseInt(part, 10));
  if (octets.some((value) => Number.isNaN(value) || value < 0 || value > 255)) return false;
  return octets[0] === 100 && octets[1] >= 64 && octets[1] <= 127;
}
function isTailscaleIPv6Address(address) {
  const normalized = address.toLowerCase();
  return normalized.startsWith("fd7a:115c:a1e0:");
}
function hasDetectedTailscaleIp() {
  try {
    const interfaces = networkInterfaces();
    for (const entries of Object.values(interfaces)) {
      if (!entries) continue;
      for (const entry of entries) {
        if (entry.internal) continue;
        if (entry.family === "IPv4" && isTailscaleIPv4Address(entry.address)) return true;
        if (entry.family === "IPv6" && isTailscaleIPv6Address(entry.address)) return true;
      }
    }
  } catch {
  }
  return false;
}
async function startCloudflaredTunnel(command, localPort) {
  return new Promise((resolve4, reject) => {
    const child = spawn5(command, ["tunnel", "--url", `http://localhost:${String(localPort)}`], {
      stdio: ["ignore", "pipe", "pipe"]
    });
    const timeout = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error("Timed out waiting for cloudflared tunnel URL"));
    }, 2e4);
    const handleData = (value) => {
      const text = String(value);
      const parsedUrl = parseCloudflaredUrl(text);
      if (!parsedUrl) {
        return;
      }
      clearTimeout(timeout);
      child.stdout?.off("data", handleData);
      child.stderr?.off("data", handleData);
      resolve4({ process: child, url: parsedUrl });
    };
    const onError = (error) => {
      clearTimeout(timeout);
      reject(new Error(`Failed to start cloudflared: ${error.message}`));
    };
    child.once("error", onError);
    child.stdout?.on("data", handleData);
    child.stderr?.on("data", handleData);
    child.once("exit", (code) => {
      if (code === 0) {
        return;
      }
      clearTimeout(timeout);
      reject(new Error(`cloudflared exited before providing a URL (code ${String(code)})`));
    });
  });
}
function listenWithFallback(server, startPort) {
  return new Promise((resolve4, reject) => {
    const attempt = (port) => {
      const onError = (error) => {
        server.off("listening", onListening);
        if (error.code === "EADDRINUSE" || error.code === "EACCES") {
          attempt(port + 1);
          return;
        }
        reject(error);
      };
      const onListening = () => {
        server.off("error", onError);
        resolve4(port);
      };
      server.once("error", onError);
      server.once("listening", onListening);
      server.listen(port, "0.0.0.0");
    };
    attempt(startPort);
  });
}
function getCodexGlobalStatePath2() {
  const codexHome = getCodexHomePath();
  return join10(codexHome, ".codex-global-state.json");
}
function normalizeUniqueStrings(value) {
  if (!Array.isArray(value)) return [];
  const next = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const trimmed = item.trim();
    if (!trimmed || next.includes(trimmed)) continue;
    next.push(trimmed);
  }
  return next;
}
async function persistLaunchProject(projectPath) {
  const trimmed = projectPath.trim();
  if (!trimmed) return;
  const normalizedPath = isAbsolute4(trimmed) ? trimmed : resolve3(trimmed);
  const directoryInfo = await stat7(normalizedPath);
  if (!directoryInfo.isDirectory()) {
    throw new Error(`Not a directory: ${normalizedPath}`);
  }
  const statePath = getCodexGlobalStatePath2();
  let payload = {};
  try {
    const raw = await readFile5(statePath, "utf8");
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      payload = parsed;
    }
  } catch {
    payload = {};
  }
  const roots = normalizeUniqueStrings(payload["electron-saved-workspace-roots"]);
  const activeRoots = normalizeUniqueStrings(payload["active-workspace-roots"]);
  payload["electron-saved-workspace-roots"] = [
    normalizedPath,
    ...roots.filter((value) => value !== normalizedPath)
  ];
  payload["active-workspace-roots"] = [
    normalizedPath,
    ...activeRoots.filter((value) => value !== normalizedPath)
  ];
  await writeFile6(statePath, JSON.stringify(payload), "utf8");
}
async function addProjectOnly(projectPath) {
  const trimmed = projectPath.trim();
  if (!trimmed) {
    throw new Error("Missing project path");
  }
  await persistLaunchProject(trimmed);
}
async function startServer(options) {
  const version = await readCliVersion();
  const projectPath = options.projectPath?.trim() ?? "";
  if (projectPath.length > 0) {
    try {
      await persistLaunchProject(projectPath);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.warn(`
[project] Could not open launch project: ${message}
`);
    }
  }
  const codexCommand = ensureCodexInstalled() ?? resolveCodexCommand();
  if (codexCommand) {
    process.env.CODEXUI_CODEX_COMMAND = codexCommand;
  }
  if (options.sandboxMode) {
    process.env.CODEXUI_SANDBOX_MODE = options.sandboxMode;
  }
  if (options.approvalPolicy) {
    process.env.CODEXUI_APPROVAL_POLICY = options.approvalPolicy;
  }
  const runtimeConfig = resolveAppServerRuntimeConfig();
  if (options.login && !hasCodexAuth()) {
    console.log("\nCodex is not logged in. You can log in later via settings or run `codexui login`.\n");
  }
  const requestedPort = parseInt(options.port, 10);
  const passwordResolution = resolvePassword(options.password);
  const password = passwordResolution.password;
  const generatedPasswordPath = password && passwordResolution.generated ? await persistGeneratedPassword(password) : null;
  const { app, dispose, attachWebSocket } = createServer({ password });
  const server = createServer2(app);
  attachWebSocket(server);
  const port = await listenWithFallback(server, requestedPort);
  process.env.CODEXUI_SERVER_PORT = String(port);
  let tunnelChild = null;
  let tunnelUrl = null;
  if (options.tunnel) {
    try {
      const cloudflaredCommand = await resolveCloudflaredForTunnel();
      if (!cloudflaredCommand) {
        throw new Error("cloudflared is not installed");
      }
      const tunnel = await startCloudflaredTunnel(cloudflaredCommand, port);
      tunnelChild = tunnel.process;
      tunnelUrl = tunnel.url;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.warn(`
[cloudflared] Tunnel not started: ${message}`);
    }
  }
  const lines = [
    "",
    "Codex Web Local is running!",
    `  Version:  ${version}`,
    "  GitHub:   https://github.com/friuns2/codexui",
    "",
    `  Bind:     http://0.0.0.0:${String(port)}`,
    `  Codex sandbox: ${runtimeConfig.sandboxMode}`,
    `  Approval policy: ${runtimeConfig.approvalPolicy}`
  ];
  const accessUrls = getAccessibleUrls(port);
  if (accessUrls.length > 0) {
    lines.push(`  Local:    ${accessUrls[0]}`);
    for (const accessUrl of accessUrls.slice(1)) {
      lines.push(`  Network:  ${accessUrl}`);
    }
  }
  if (port !== requestedPort) {
    lines.push(`  Requested port ${String(requestedPort)} was unavailable; using ${String(port)}.`);
  }
  if (generatedPasswordPath) {
    lines.push(`  Generated password file: ${generatedPasswordPath}`);
    lines.push("  Use that file to retrieve the password for untrusted origins.");
  }
  const tunnelQrUrl = tunnelUrl ? buildTunnelAutologinUrl(tunnelUrl, password) : null;
  if (tunnelUrl) {
    lines.push(`  Tunnel:   ${tunnelQrUrl ?? tunnelUrl}`);
    lines.push("  Tunnel QR code below");
  }
  printTermuxKeepAlive(lines);
  lines.push("");
  console.log(lines.join("\n"));
  if (tunnelQrUrl) {
    qrcode.generate(tunnelQrUrl, { small: true });
    console.log("");
  }
  if (options.open) openBrowser(`http://localhost:${String(port)}`);
  function shutdown() {
    console.log("\nShutting down...");
    if (tunnelChild && !tunnelChild.killed) {
      tunnelChild.kill("SIGTERM");
    }
    server.close(() => {
      dispose();
      process.exit(0);
    });
    setTimeout(() => {
      dispose();
      process.exit(1);
    }, 5e3).unref();
  }
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}
async function runLogin() {
  const codexCommand = ensureCodexInstalled() ?? "codex";
  process.env.CODEXUI_CODEX_COMMAND = codexCommand;
  console.log("\nStarting `codex login`...\n");
  runOrFail(codexCommand, ["login"], "Codex login");
}
program.argument("[projectPath]", "project directory to open on launch").option("--open-project <path>", "open project directory on launch (Codex desktop parity)").option("-p, --port <port>", "port to listen on", "5900").option("--password <pass>", "set a specific password").option("--no-password", "disable password protection").option("--tunnel", "start cloudflared tunnel (default is auto by Tailscale detection)", true).option("--no-tunnel", "disable cloudflared tunnel startup").option("--open", "open browser on startup", true).option("--no-open", "do not open browser on startup").option("--login", "run automatic Codex login bootstrap", true).option("--no-login", "skip automatic Codex login bootstrap").option("--memories", "enable Codex memories for spawned app-server processes", true).option("--no-memories", "disable Codex memories for spawned app-server processes").option("--sandbox-mode <mode>", "Codex sandbox mode: read-only, workspace-write, danger-full-access").option("--approval-policy <policy>", "Codex approval policy: untrusted, on-failure, on-request, never").action(async (projectPath, opts) => {
  const rawArgv = process.argv.slice(2);
  const openProjectFlagIndex = rawArgv.findIndex((arg) => arg === "--open-project" || arg.startsWith("--open-project="));
  const tunnelFlagExplicit = rawArgv.some((arg) => arg === "--tunnel" || arg === "--no-tunnel" || arg.startsWith("--tunnel=") || arg.startsWith("--no-tunnel="));
  const memoriesFlagExplicit = rawArgv.some((arg) => arg === "--memories" || arg === "--no-memories" || arg.startsWith("--memories=") || arg.startsWith("--no-memories="));
  const effectiveTunnel = tunnelFlagExplicit ? opts.tunnel : hasDetectedTailscaleIp();
  if (memoriesFlagExplicit) {
    process.env.CODEXUI_MEMORIES = opts.memories ? "true" : "false";
  }
  let openProjectOnly = (opts.openProject ?? "").trim();
  if (!openProjectOnly && openProjectFlagIndex >= 0 && projectPath?.trim()) {
    openProjectOnly = projectPath.trim();
  }
  if (openProjectOnly.length > 0) {
    await addProjectOnly(openProjectOnly);
    console.log(`Added project: ${openProjectOnly}`);
    return;
  }
  const launchProject = (projectPath ?? "").trim();
  if (opts.sandboxMode) {
    const parsedSandboxMode = parseSandboxMode(opts.sandboxMode);
    if (!parsedSandboxMode) {
      throw new Error(`Invalid sandbox mode: ${opts.sandboxMode}`);
    }
    opts.sandboxMode = parsedSandboxMode;
  }
  if (opts.approvalPolicy) {
    const parsedApprovalPolicy = parseApprovalPolicy(opts.approvalPolicy);
    if (!parsedApprovalPolicy) {
      throw new Error(`Invalid approval policy: ${opts.approvalPolicy}`);
    }
    opts.approvalPolicy = parsedApprovalPolicy;
  }
  await startServer({ ...opts, tunnel: effectiveTunnel, projectPath: launchProject });
});
program.command("login").description("Install/check Codex CLI and run `codex login`").action(runLogin);
program.command("help").description("Show codexui command help").action(() => {
  program.outputHelp();
});
program.parseAsync(process.argv).catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`
Failed to run codexui: ${message}`);
  process.exit(1);
});
//# sourceMappingURL=index.js.map
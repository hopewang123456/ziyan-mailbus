import { api } from "../api";
import type { components } from "../contracts";

/**
 * Audit 域唯一 API 落点。
 * 类型全部来自 contracts.ts 生成；禁止手写 DTO。
 */

type AuditEntryOut = components["schemas"]["AuditEntryOut"];
type AuditListOut = components["schemas"]["AuditListOut"];

export function listAudit(query?: {
  actor?: string | null;
  action?: string | null;
  resource?: string | null;
  from?: string | null;
  to?: string | null;
  limit?: number;
  offset?: number;
}) {
  const params = new URLSearchParams();
  if (query?.actor) params.set("actor", query.actor);
  if (query?.action) params.set("action", query.action);
  if (query?.resource) params.set("resource", query.resource);
  if (query?.from) params.set("from", query.from);
  if (query?.to) params.set("to", query.to);
  if (query?.limit !== undefined) params.set("limit", String(query.limit));
  if (query?.offset !== undefined) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<AuditListOut>(q ? `/api/audit?${q}` : "/api/audit");
}

export function getAudit(auditId: number) {
  return api<AuditEntryOut>(`/api/audit/${encodeURIComponent(String(auditId))}`);
}

import { neon } from "@neondatabase/serverless";
import { createHash, randomBytes, randomUUID, scryptSync, timingSafeEqual } from "node:crypto";
import type { NextRequest } from "next/server";

export type AppUser = {
  username: string;
  displayName: string;
  role: "customer" | "support-agent";
  customerId: string;
};

const demoUsers = [
  { username: "alex.morgan", password: "ReviewerPass-1001", displayName: "Alex Morgan", role: "customer" as const, customerId: "TEL-1001" },
  { username: "jordan.lee", password: "ReviewerPass-1002", displayName: "Jordan Lee", role: "customer" as const, customerId: "TEL-1002" },
  { username: "support.agent", password: "ReviewerPass-3001", displayName: "Support Agent", role: "support-agent" as const, customerId: "OPS-3001" }
];

export type DbClient = ReturnType<typeof neon>;

export function getDb() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not configured.");
  return neon(url);
}

function passwordHash(password: string, username: string) {
  return scryptSync(password, "starter-demo-salt:" + username, 64).toString("hex");
}

export function passwordMatches(password: string, storedHash: string, username: string) {
  const actual = Buffer.from(passwordHash(password, username), "hex");
  const expected = Buffer.from(storedHash, "hex");
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

export function hashToken(token: string) {
  return createHash("sha256").update(token).digest("hex");
}

let schemaPromise: Promise<ReturnType<typeof getDb>> | null = null;

export function ensureSchema() {
  if (!schemaPromise) {
    schemaPromise = initializeSchema();
    schemaPromise.catch(() => { schemaPromise = null; });
  }
  return schemaPromise;
}

async function initializeSchema() {
  const sql = getDb();
  await sql`CREATE TABLE IF NOT EXISTS starter_users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('customer', 'support-agent')),
    customer_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )`;
  await sql`CREATE TABLE IF NOT EXISTS starter_sessions (
    token_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES starter_users(username) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )`;
  await sql`CREATE INDEX IF NOT EXISTS starter_sessions_expiry_idx ON starter_sessions(expires_at)`;
  await sql`CREATE TABLE IF NOT EXISTS starter_pending_actions (
    action_id TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES starter_users(username) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    case_subject TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'cancelled', 'expired')),
    case_id TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )`;
  await sql`CREATE TABLE IF NOT EXISTS starter_cases (
    case_id TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES starter_users(username),
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (username, idempotency_key)
  )`;
  await sql`CREATE INDEX IF NOT EXISTS starter_cases_username_idx ON starter_cases(username, created_at DESC)`;
  await sql`CREATE TABLE IF NOT EXISTS starter_events (
    event_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL DEFAULT 'system',
    trace_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    component TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'failure', 'pending', 'denied')),
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )`;
  await sql`CREATE INDEX IF NOT EXISTS starter_events_created_idx ON starter_events(created_at DESC)`;

  for (const demo of demoUsers) {
    await sql`INSERT INTO starter_users (username, password_hash, display_name, role, customer_id)
      VALUES (${demo.username}, ${passwordHash(demo.password, demo.username)}, ${demo.displayName}, ${demo.role}, ${demo.customerId})
      ON CONFLICT (username) DO NOTHING`;
  }
  return sql;
}

export function newId(prefix = "") {
  return prefix + randomUUID();
}

export function newToken() {
  return randomBytes(32).toString("base64url");
}

export async function recordEvent(
  sql: ReturnType<typeof getDb>,
  username: string,
  traceId: string,
  eventType: string,
  component: string,
  status: "success" | "failure" | "pending" | "denied",
  detail: Record<string, string | number | boolean | null> = {}
) {
  const safeDetail: Record<string, string | number | boolean | null> = {};
  for (const [key, value] of Object.entries(detail)) {
    if (/password|token|secret|api.?key|session|email|phone|credential|idempotency/i.test(key)) continue;
    safeDetail[key] = typeof value === "string" ? value.slice(0, 180) : value;
  }
  await sql`INSERT INTO starter_events (username, trace_id, event_type, component, status, detail)
    VALUES (${username}, ${traceId}, ${eventType}, ${component}, ${status}, ${JSON.stringify(safeDetail)}::jsonb)`;
}

export async function getSessionUser(req: NextRequest, sql: ReturnType<typeof getDb>): Promise<AppUser | null> {
  const token = req.cookies.get("starter_session")?.value;
  if (!token || token.length > 150) return null;
  const rows = await sql`SELECT u.username, u.display_name, u.role, u.customer_id
    FROM starter_sessions s JOIN starter_users u ON u.username = s.username
    WHERE s.token_hash = ${hashToken(token)} AND s.expires_at > NOW()
    LIMIT 1`;
  if (!rows.length) return null;
  const row = rows[0] as { username: string; display_name: string; role: AppUser["role"]; customer_id: string };
  return { username: row.username, displayName: row.display_name, role: row.role, customerId: row.customer_id };
}

export function isGeminiConfigured() {
  return Boolean(process.env.GEMINI_API_KEY?.trim());
}

export function currentAiMode() {
  return process.env.AI_MODE?.trim().toLowerCase() === "live" && isGeminiConfigured() ? "live" : "reviewer";
}

export type IntentResult = {
  intent: "balance" | "usage" | "plan" | "network" | "case" | "general";
  service: "mobile" | "internet" | "billing" | "unknown";
  summary: string;
  source: "gemini" | "fallback";
};

export function deterministicIntent(message: string): IntentResult {
  const m = message.toLowerCase();
  let intent: IntentResult["intent"] = "general";
  let service: IntentResult["service"] = "unknown";
  if (/complaint|support case|open a case|raise (a )?(case|ticket)|create (a )?(case|ticket)|register (an )?issue|report (an )?issue|ticket/.test(m)) {
    intent = "case";
  } else if (/data usage|used.*(data|gb)|how much data|gb.*used|remaining data|internet usage/.test(m)) {
    intent = "usage";
  } else if (/balance|bill|billing|amount due|payment due|next bill|invoice|charge/.test(m)) {
    intent = "balance";
  } else if (/plan|recharge|add.?on|pack|allowance/.test(m)) {
    intent = "plan";
  } else if (/network|signal|no internet|internet.*(slow|down|not working)|not working.*(mobile|internet|network)|connection.*(issue|slow|down)|outage|service.*down/.test(m)) {
    intent = "network";
  }
  if (/wifi|wi-fi|broadband|home internet|router|fixed line/.test(m)) service = "internet";
  else if (/bill|billing|balance|payment|invoice/.test(m)) service = "billing";
  else if (/mobile|sim|signal|cellular|phone/.test(m)) service = "mobile";
  const summary = message.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, 280);
  return { intent, service, summary, source: "fallback" };
}

export async function classifyIntent(message: string): Promise<IntentResult> {
  const fallback = deterministicIntent(message);
  if (currentAiMode() !== "live") return fallback;
  const model = process.env.GEMINI_MODEL?.trim() || "gemini-3.8-flash";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch("https://generativelanguage.googleapis.com/v1beta/models/" + encodeURIComponent(model) + ":generateContent", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": process.env.GEMINI_API_KEY || "" },
      signal: controller.signal,
      body: JSON.stringify({
        systemInstruction: { parts: [{ text: "Classify a customer support message for a synthetic telecom demo. Return JSON only with fields intent (one of balance, usage, plan, network, case, general), service (one of mobile, internet, billing, unknown), and summary (a safe, neutral summary under 160 characters). Do not provide a customer answer, reveal data, claim an action happened, authorize a change, or invent account facts. A request to create/register/report a complaint is case. Reading account balance/bill is balance. Data consumption is usage." }] },
        contents: [{ role: "user", parts: [{ text: message }] }],
        generationConfig: { responseMimeType: "application/json", temperature: 0 }
      })
    });
    if (!response.ok) throw new Error("Gemini provider returned non-success status");
    const data = await response.json() as { candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }> };
    const text = data.candidates?.[0]?.content?.parts?.map(p => p.text || "").join("") || "";
    const parsed = JSON.parse(text) as { intent?: string; service?: string; summary?: string };
    const allowedIntents = ["balance", "usage", "plan", "network", "case", "general"];
    const allowedServices = ["mobile", "internet", "billing", "unknown"];
    if (!parsed || !allowedIntents.includes(String(parsed.intent)) || !allowedServices.includes(String(parsed.service))) {
      throw new Error("Gemini returned invalid intent shape");
    }
    const intent = parsed.intent as IntentResult["intent"];
    const service = parsed.service as IntentResult["service"];
    const summary = String(parsed.summary || fallback.summary).replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, 180);
    // Deterministic safety routing takes precedence whenever it sees a consequential case request.
    if (fallback.intent === "case") return { ...fallback, source: "gemini" };
    return { intent: fallback.intent !== "general" ? fallback.intent : intent, service: fallback.service !== "unknown" ? fallback.service : service, summary, source: "gemini" };
  } catch {
    return fallback;
  } finally {
    clearTimeout(timeout);
  }
}

export function safeTraceId() {
  return "TRACE-" + randomBytes(6).toString("hex").toUpperCase();
}

export function demoProfile(username: string) {
  if (username === "jordan.lee") {
    return { plan: "Connect 5", dataUsedGb: 2.9, dataAllowanceGb: 5, nextBillAmount: 549, nextBillDate: "2026-10-24", networkState: "normal" };
  }
  return { plan: "Connect 5", dataUsedGb: 4.2, dataAllowanceGb: 5, nextBillAmount: 549, nextBillDate: "2026-10-24", networkState: "normal" };
}

import { NextRequest, NextResponse } from "next/server";
import { ensureSchema, getSessionUser, newId, recordEvent, safeTraceId } from "@/app/lib/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const traceId = safeTraceId();
  try {
    const sql = await ensureSchema();
    const user = await getSessionUser(req, sql);
    if (!user) return NextResponse.json({ error: "Your session has expired. Sign in again." }, { status: 401 });
    if (user.role !== "customer") {
      await recordEvent(sql, user.username, traceId, "case.confirmation.denied", "authorization", "denied", { reason: "role_not_customer" });
      return NextResponse.json({ error: "This role cannot create customer support cases." }, { status: 403 });
    }
    const body = await req.json() as { actionId?: unknown; decision?: unknown };
    if (typeof body.actionId !== "string" || body.actionId.length > 100 || !["confirm", "cancel"].includes(String(body.decision))) {
      return NextResponse.json({ error: "A valid pending action and decision are required." }, { status: 400 });
    }
    const actions = await sql`SELECT action_id, username, idempotency_key, summary, case_subject, status, case_id, expires_at
      FROM starter_pending_actions WHERE action_id = ${body.actionId} AND username = ${user.username} LIMIT 1`;
    const action = actions[0] as { action_id: string; username: string; idempotency_key: string; summary: string; case_subject: string; status: string; case_id: string | null; expires_at: string } | undefined;
    if (!action) return NextResponse.json({ error: "The pending action was not found for this session." }, { status: 404 });

    if (action.status === "confirmed" && action.case_id) {
      if (body.decision === "confirm") {
        return NextResponse.json({ ok: true, caseId: action.case_id, idempotentReplay: true, traceId });
      }
      return NextResponse.json({ error: "This case has already been confirmed and cannot be cancelled here." }, { status: 409 });
    }
    if (action.status === "cancelled") {
      return body.decision === "cancel"
        ? NextResponse.json({ ok: true, cancelled: true, idempotentReplay: true, traceId })
        : NextResponse.json({ error: "This pending action has already been cancelled." }, { status: 409 });
    }
    if (action.status !== "pending") return NextResponse.json({ error: "This pending action is no longer active." }, { status: 409 });
    if (new Date(action.expires_at).getTime() <= Date.now()) {
      await sql`UPDATE starter_pending_actions SET status = 'expired' WHERE action_id = ${action.action_id} AND status = 'pending'`;
      return NextResponse.json({ error: "This confirmation has expired. Submit the request again to create a new one." }, { status: 410 });
    }
    if (body.decision === "cancel") {
      await sql`UPDATE starter_pending_actions SET status = 'cancelled' WHERE action_id = ${action.action_id} AND status = 'pending'`;
      await recordEvent(sql, user.username, traceId, "case.confirmation.cancelled", "action-guard", "success", { reason: "user_cancelled" });
      return NextResponse.json({ ok: true, cancelled: true, traceId });
    }

    const proposedId = newId("CASE-").slice(0, 17).toUpperCase();
    const rows = await sql`INSERT INTO starter_cases (case_id, username, subject, description, status, idempotency_key)
      VALUES (${proposedId}, ${user.username}, ${action.case_subject}, ${action.summary}, 'open', ${action.idempotency_key})
      ON CONFLICT (username, idempotency_key) DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
      RETURNING case_id`;
    const caseId = String((rows[0] as { case_id: string }).case_id);
    await sql`UPDATE starter_pending_actions SET status = 'confirmed', case_id = ${caseId} WHERE action_id = ${action.action_id} AND username = ${user.username} AND status = 'pending'`;
    await recordEvent(sql, user.username, traceId, "case.created", "support-case-api", "success", { status: "open" });
    return NextResponse.json({ ok: true, caseId, traceId }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "The confirmation service is temporarily unavailable. No success is reported unless the case has been saved." }, { status: 503 });
  }
}

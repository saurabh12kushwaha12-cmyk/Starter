import { NextRequest, NextResponse } from "next/server";
import { ensureSchema, getSessionUser, recordEvent, safeTraceId } from "@/app/lib/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const traceId = safeTraceId();
  try {
    const sql = await ensureSchema();
    const user = await getSessionUser(req, sql);
    if (!user) return NextResponse.json({ error: "Sign in to view operations data." }, { status: 401 });
    if (user.role !== "support-agent") {
      await recordEvent(sql, user.username, traceId, "ops.access.denied", "authorization", "denied", { requested_view: "operations" });
      return NextResponse.json({ error: "Operations data is restricted to the support-agent role." }, { status: 403 });
    }
    const eventRows = await sql`SELECT COUNT(*)::int AS count FROM starter_events`;
    const caseRows = await sql`SELECT COUNT(*)::int AS total, COUNT(*) FILTER (WHERE status = 'open')::int AS open FROM starter_cases`;
    const recent = await sql`SELECT event_type, status, created_at FROM starter_events ORDER BY created_at DESC LIMIT 25`;
    const eventCount = Number((eventRows[0] as { count: number | string }).count);
    const caseCount = caseRows[0] as { total: number | string; open: number | string };
    await recordEvent(sql, user.username, traceId, "ops.metrics.viewed", "observability", "success", {});
    return NextResponse.json({
      totalEvents: eventCount,
      totalCases: Number(caseCount.total),
      openCases: Number(caseCount.open),
      recentEvents: recent.map(row => {
        const event = row as { event_type: string; status: string; created_at: string | Date };
        return { event_type: event.event_type, status: event.status, created_at: new Date(event.created_at).toISOString() };
      })
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "Operations data is temporarily unavailable." }, { status: 503 });
  }
}

import { NextRequest, NextResponse } from "next/server";
import { classifyIntent, currentAiMode, demoProfile, ensureSchema, getSessionUser, newId, recordEvent, safeTraceId } from "@/app/lib/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function cleanSummary(value: string) {
  return value
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[redacted email]")
    .replace(/(?<!\w)\+?\d[\d ().-]{8,}\d(?!\w)/g, "[redacted phone]")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 240);
}

export async function POST(req: NextRequest) {
  const traceId = safeTraceId();
  try {
    const sql = await ensureSchema();
    const user = await getSessionUser(req, sql);
    if (!user) return NextResponse.json({ error: "Your session has expired. Sign in again." }, { status: 401 });
    const body = await req.json() as { message?: unknown };
    if (typeof body.message !== "string" || !body.message.trim() || body.message.length > 2000) {
      return NextResponse.json({ error: "Enter a message between 1 and 2,000 characters." }, { status: 400 });
    }
    const message = body.message.trim();
    const intent = await classifyIntent(message);
    await recordEvent(sql, user.username, traceId, "chat.intent.classified", "intent-router", "success", { intent: intent.intent, source: intent.source, service: intent.service });

    if (user.role === "support-agent") {
      const reply = "This account is restricted to the operations workspace and cannot access customer account details. Open Operations & observability to review aggregated counts and sanitized events.";
      await recordEvent(sql, user.username, traceId, "chat.customer_access.denied", "authorization", "denied", { intent: intent.intent });
      return NextResponse.json({ reply, intent: intent.intent, aiMode: currentAiMode(), traceId, pendingAction: null });
    }

    const profile = demoProfile(user.username);
    let reply: string;
    let pendingAction: { id: string; summary: string } | null = null;

    switch (intent.intent) {
      case "balance":
        reply = "Your synthetic " + profile.plan + " account shows a monthly bill of ₹" + profile.nextBillAmount + ", due on " + profile.nextBillDate + ". This is challenge demo data, not a live billing-system lookup.";
        break;
      case "usage":
        reply = "Your synthetic account has used " + profile.dataUsedGb.toFixed(1) + " GB out of " + profile.dataAllowanceGb.toFixed(1) + " GB this month (" + Math.round(profile.dataUsedGb / profile.dataAllowanceGb * 100) + "%). This figure comes from the demo profile, not a live carrier network.";
        break;
      case "plan":
        reply = "Your synthetic plan is " + profile.plan + " with a " + profile.dataAllowanceGb + " GB monthly allowance. The sample recurring bill is ₹" + profile.nextBillAmount + ", due " + profile.nextBillDate + ". I have not changed your plan or purchased an add-on.";
        break;
      case "network":
        reply = "The synthetic service record currently shows no broad outage. This demo does not query a real carrier network. Try toggling airplane mode, checking the selected SIM/mobile-data setting, and restarting the device. If the issue continues, ask me to open a support case; I will show the summary and wait for your confirmation.";
        break;
      case "case": {
        const summary = cleanSummary(intent.summary || message) || "Customer-reported service issue";
        const serviceName = intent.service === "internet" ? "Internet service issue" : intent.service === "billing" ? "Billing question" : "Customer-reported service issue";
        const actionId = newId("act_");
        const idempotencyKey = newId("idem_");
        await sql`INSERT INTO starter_pending_actions (action_id, username, idempotency_key, summary, case_subject, status, expires_at)
          VALUES (${actionId}, ${user.username}, ${idempotencyKey}, ${summary}, ${serviceName}, 'pending', NOW() + INTERVAL '10 minutes')`;
        await recordEvent(sql, user.username, traceId, "case.confirmation.required", "action-guard", "pending", { service: intent.service });
        reply = "I have prepared a support-case request for your review. No case has been created yet. Check the summary below and confirm or cancel.";
        pendingAction = { id: actionId, summary: serviceName + ": " + summary };
        break;
      }
      default:
        reply = "I can help with your synthetic plan, bill, data usage, basic network troubleshooting, or a support-case request. For example, ask “How much data have I used?” or “Please open a support case for my slow internet.” I will not make a consequential change without checking your identity and asking for confirmation.";
    }

    await recordEvent(sql, user.username, traceId, "chat.response.generated", "conversation", "success", { intent: intent.intent, source: intent.source });
    return NextResponse.json({ reply, intent: intent.intent, aiMode: intent.source === "gemini" ? "live" : currentAiMode(), traceId, pendingAction }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "The support service is temporarily unavailable. Check database configuration and try again." }, { status: 503 });
  }
}

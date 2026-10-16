import { ensureSchema, isGeminiConfigured, currentAiMode, safeTraceId } from "@/app/lib/server";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = await ensureSchema();
    await sql`SELECT 1 AS ready`;
    return NextResponse.json({
      status: "online",
      database: "ready",
      aiMode: currentAiMode(),
      geminiConfigured: isGeminiConfigured(),
      traceId: safeTraceId()
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({
      status: "unavailable",
      database: "unavailable",
      aiMode: currentAiMode(),
      geminiConfigured: isGeminiConfigured(),
      traceId: safeTraceId(),
      message: "Database connection needs configuration."
    }, { headers: { "Cache-Control": "no-store" } });
  }
}

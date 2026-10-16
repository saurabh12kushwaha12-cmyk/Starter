import { NextRequest, NextResponse } from "next/server";
import { ensureSchema, getSessionUser } from "@/app/lib/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    const sql = await ensureSchema();
    const user = await getSessionUser(req, sql);
    if (!user) return NextResponse.json({ user: null }, { status: 401, headers: { "Cache-Control": "no-store" } });
    return NextResponse.json({ user }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ user: null, error: "Database is not configured." }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}

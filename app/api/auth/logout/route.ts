import { NextRequest, NextResponse } from "next/server";
import { ensureSchema, getDb, hashToken } from "@/app/lib/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const token = req.cookies.get("starter_session")?.value;
    if (token && token.length <= 150) {
      const sql = await ensureSchema();
      await sql`DELETE FROM starter_sessions WHERE token_hash = ${hashToken(token)}`;
    }
  } catch {
    // The browser cookie is still cleared if the data service is temporarily unavailable.
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set("starter_session", "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: "/", maxAge: 0 });
  return response;
}

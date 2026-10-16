import { NextRequest, NextResponse } from "next/server";
import { ensureSchema, newToken, hashToken, passwordMatches, recordEvent, safeTraceId } from "@/app/lib/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const traceId = safeTraceId();
  try {
    const body = await req.json() as { username?: unknown; password?: unknown };
    if (typeof body.username !== "string" || typeof body.password !== "string" || body.username.length > 80 || body.password.length > 256) {
      return NextResponse.json({ error: "Enter a valid username and password." }, { status: 400 });
    }
    const username = body.username.trim().toLowerCase();
    const sql = await ensureSchema();
    const users = await sql`SELECT username, password_hash, display_name, role, customer_id
      FROM starter_users WHERE username = ${username} LIMIT 1`;
    const row = users[0] as { username: string; password_hash: string; display_name: string; role: "customer" | "support-agent"; customer_id: string } | undefined;
    if (!row || !passwordMatches(body.password, row.password_hash, username)) {
      await recordEvent(sql, "system", traceId, "auth.login.failure", "authentication", "denied", { reason: "invalid_credentials" });
      return NextResponse.json({ error: "The username or password is incorrect." }, { status: 401 });
    }
    const token = newToken();
    await sql`INSERT INTO starter_sessions (token_hash, username, expires_at)
      VALUES (${hashToken(token)}, ${username}, NOW() + INTERVAL '8 hours')`;
    await recordEvent(sql, username, traceId, "auth.login.success", "authentication", "success", { role: row.role });
    const response = NextResponse.json({
      user: { username: row.username, displayName: row.display_name, role: row.role, customerId: row.customer_id }
    }, { headers: { "Cache-Control": "no-store" } });
    response.cookies.set("starter_session", token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      maxAge: 60 * 60 * 8
    });
    return response;
  } catch {
    return NextResponse.json({ error: "Sign-in service is temporarily unavailable. Check database configuration and retry." }, { status: 503 });
  }
}

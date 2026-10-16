"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

type User = { username: string; displayName: string; role: string; customerId: string };
type Health = { status: string; database: string; aiMode: string; geminiConfigured: boolean };
type ChatMessage = { id: string; speaker: "assistant" | "user"; text: string; time: string };
type PendingAction = { id: string; summary: string };
type AppReply = { reply: string; intent?: string; aiMode?: string; pendingAction?: PendingAction | null; traceId?: string };
type OpsData = { totalEvents: number; totalCases: number; openCases: number; recentEvents: Array<{ event_type: string; status: string; created_at: string }> };

const demoUsers = [
  { username: "alex.morgan", password: "ReviewerPass-1001", label: "Alex Morgan", role: "Customer demo" },
  { username: "jordan.lee", password: "ReviewerPass-1002", label: "Jordan Lee", role: "Data-isolation demo" },
  { username: "support.agent", password: "ReviewerPass-3001", label: "Support Agent", role: "Operations demo" }
];

function clock() {
  return new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit" }).format(new Date());
}

function Brand() {
  return <div className="brand"><div className="brand-mark">S</div><div><div className="brand-title">Starter CX</div><div className="brand-sub">Support intelligence</div></div></div>;
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [health, setHealth] = useState<Health>({ status: "checking", database: "checking", aiMode: "checking", geminiConfigured: false });
  const [username, setUsername] = useState("alex.morgan");
  const [password, setPassword] = useState("ReviewerPass-1001");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [activePanel, setActivePanel] = useState<"overview" | "operations">("overview");
  const [ops, setOps] = useState<OpsData | null>(null);
  const [opsError, setOpsError] = useState("");
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/health").then(r => r.json()).then(setHealth).catch(() => setHealth({ status: "unavailable", database: "unavailable", aiMode: "fallback", geminiConfigured: false }));
    fetch("/api/auth/me").then(async r => {
      const data = await r.json();
      if (r.ok && data.user) {
        setUser(data.user);
        setMessages([{ id: "welcome", speaker: "assistant", text: "Welcome back, " + data.user.displayName + ". I can check synthetic account details, guide you through network troubleshooting, or prepare a support case. I will ask before creating any case.", time: clock() }]);
      }
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages, chatLoading, pending]);

  async function login(e?: FormEvent) {
    e?.preventDefault();
    setLoginLoading(true);
    setLoginError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not sign in.");
      setUser(data.user);
      setMessages([{ id: crypto.randomUUID(), speaker: "assistant", text: "Hello " + data.user.displayName + ". Your session is secured. This demo uses synthetic telecom records only. Try a quick prompt below, or ask me in your own words.", time: clock() }]);
      setPending(null);
      setActivePanel("overview");
      setOps(null);
      setHealth(prev => ({ ...prev, status: "online" }));
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "Login failed. Please try again.");
    } finally {
      setLoginLoading(false);
    }
  }

  async function logout() {
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch {}
    setUser(null);
    setMessages([]);
    setPending(null);
    setOps(null);
    setActivePanel("overview");
    setPassword("");
  }

  async function sendMessage(raw?: string) {
    const message = (raw ?? draft).trim();
    if (!message || chatLoading) return;
    setDraft("");
    setPending(null);
    setMessages(prev => [...prev, { id: crypto.randomUUID(), speaker: "user", text: message, time: clock() }]);
    setChatLoading(true);
    try {
      const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
      const data = await response.json() as AppReply & { error?: string };
      if (!response.ok) throw new Error(data.error || "The request could not be completed.");
      setMessages(prev => [...prev, { id: crypto.randomUUID(), speaker: "assistant", text: data.reply, time: clock() }]);
      if (data.pendingAction) setPending(data.pendingAction);
      if (data.aiMode) setHealth(prev => ({ ...prev, aiMode: data.aiMode || prev.aiMode }));
    } catch (error) {
      setMessages(prev => [...prev, { id: crypto.randomUUID(), speaker: "assistant", text: error instanceof Error ? error.message : "The service is temporarily unavailable. Please retry.", time: clock() }]);
    } finally {
      setChatLoading(false);
    }
  }

  async function resolveAction(decision: "confirm" | "cancel") {
    if (!pending || actionLoading) return;
    setActionLoading(true);
    try {
      const response = await fetch("/api/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actionId: pending.id, decision })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not process the action.");
      const text = decision === "confirm"
        ? "Confirmed. Your synthetic support case " + data.caseId + " has been created and saved."
        : "Cancelled. No support case was created.";
      setMessages(prev => [...prev, { id: crypto.randomUUID(), speaker: "assistant", text, time: clock() }]);
      setPending(null);
    } catch (error) {
      setMessages(prev => [...prev, { id: crypto.randomUUID(), speaker: "assistant", text: error instanceof Error ? error.message : "Action could not be processed.", time: clock() }]);
    } finally {
      setActionLoading(false);
    }
  }

  async function openOperations() {
    setActivePanel("operations");
    setOpsError("");
    try {
      const response = await fetch("/api/ops");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Operations access is not available for this account.");
      setOps(data);
    } catch (error) {
      setOpsError(error instanceof Error ? error.message : "Could not load operational data.");
      setOps(null);
    }
  }

  function handleComposerKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  }

  const isOpsUser = user?.role === "support-agent";
  const usage = user?.username === "jordan.lee" ? 2.9 : 4.2;
  const allowance = 5;
  const usagePct = Math.round((usage / allowance) * 100);
  const firstName = user?.displayName.split(" ")[0] || "there";

  if (!user) {
    return (
      <main className="login-page">
        <section className="login-hero">
          <Brand />
          <div className="hero-orb" aria-hidden="true" />
          <div className="hero-content">
            <div className="hero-kicker"><span className="status-dot" /> Gemini CX / Telco Challenge</div>
            <h1>Support that<br />understands <span>the whole</span><br />customer.</h1>
            <p>A carefully guarded AI support workspace. Gemini helps interpret a request; verified application logic handles identity, account access, and actions that need your confirmation.</p>
            <div className="hero-points">
              <div className="hero-point"><strong>01 · Understand</strong><span>Everyday language, clear intent</span></div>
              <div className="hero-point"><strong>02 · Verify</strong><span>Identity and account boundaries</span></div>
              <div className="hero-point"><strong>03 · Resolve</strong><span>Traceable, confirmed actions</span></div>
            </div>
          </div>
          <div className="foot-note"><span>BUILT FOR THE GEMINI CX CHALLENGE</span><span>SYNTHETIC DATA ONLY</span></div>
        </section>
        <section className="login-right">
          <div className="login-card">
            <div className="eyebrow"><span className={"status-dot " + (health.status === "unavailable" ? "error" : health.status === "checking" ? "warning" : "")} /> WEB CONSOLE <strong>{health.status === "checking" ? "CONNECTING" : health.status === "unavailable" ? "CHECK CONNECTION" : "READY TO SIGN IN"}</strong></div>
            <h2 style={{ marginTop: 13 }}>Welcome to Starter CX</h2>
            <p className="login-lead">Sign in with one of the synthetic reviewer accounts to begin testing the conversation workflow.</p>
            <form onSubmit={login}>
              <div className="form-field"><label htmlFor="username">USERNAME</label><input id="username" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} placeholder="alex.morgan" required /></div>
              <div className="form-field"><label htmlFor="password">PASSWORD</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter demo password" required /></div>
              {loginError && <div className="login-error" role="alert">{loginError}</div>}
              <button type="submit" className="primary-button full-width" disabled={loginLoading}>{loginLoading ? "Signing in…" : "Sign in securely"} <span>↗</span></button>
            </form>
            <div className="demo-box">
              <div className="demo-box-title"><span>QUICK DEMO ACCOUNTS</span><span className="mini-label">SYNTHETIC</span></div>
              {demoUsers.map(demo => (
                <button key={demo.username} className="demo-choice" onClick={() => { setUsername(demo.username); setPassword(demo.password); setLoginError(""); }}>
                  <span><strong>{demo.label}</strong><br />{demo.role}</span><span>SELECT ↗</span>
                </button>
              ))}
            </div>
            <div className="security-note"><span>◈</span><span>Access is limited by role. Account records are fictional, and support-case creation always requires explicit confirmation.</span></div>
            <div className="foot-note"><span>NEON DATA LAYER</span><span>{health.database === "ready" ? "● CONNECTED" : health.database === "checking" ? "○ CHECKING" : "○ NEEDS CONFIGURATION"}</span></div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="app-layout">
      <aside className="sidebar">
        <Brand />
        <section>
          <div className="side-label">WORKSPACE</div>
          <div className="nav-list">
            <button className={"nav-item " + (activePanel === "overview" ? "active" : "")} onClick={() => setActivePanel("overview")}><span className="nav-symbol">⌂</span>Overview</button>
            <button className={"nav-item " + (activePanel === "operations" ? "active" : "")} onClick={() => void openOperations()}><span className="nav-symbol">⌘</span>Operations & traces</button>
          </div>
        </section>
        <section>
          <div className="side-label">TEST TOOLKIT</div>
          <div className="nav-list">
            <button className="nav-item" onClick={() => { setActivePanel("overview"); void sendMessage("What is my current plan and data usage?"); }}><span className="nav-symbol">◉</span>Account lookup</button>
            <button className="nav-item" onClick={() => { setActivePanel("overview"); void sendMessage("My mobile network is not working."); }}><span className="nav-symbol">⌁</span>Network diagnostics</button>
            <button className="nav-item" onClick={() => { setActivePanel("overview"); void sendMessage("Please open a support case for my issue."); }}><span className="nav-symbol">＋</span>Support case</button>
          </div>
        </section>
        <div className="sidebar-spacer" />
        <div className="side-status">
          <div className="mini-label">SYSTEM STATUS</div>
          <div className="status-row"><span className={"status-dot " + (health.status === "unavailable" ? "error" : health.status === "checking" ? "warning" : "")} /> App {health.status === "checking" ? "checking" : health.status === "unavailable" ? "issue detected" : "operational"}</div>
          <div className="status-row"><span className={"status-dot " + (health.database !== "ready" ? "warning" : "")} /> Neon {health.database === "ready" ? "connected" : health.database === "checking" ? "checking" : "not configured"}</div>
          <div className="status-row"><span className={"status-dot " + (!health.geminiConfigured ? "warning" : "")} /> Gemini {health.geminiConfigured ? "key configured" : "fallback mode"}</div>
        </div>
        <div className="side-footer">
          <div className="avatar">{user.displayName.split(" ").map(v => v[0]).join("").slice(0,2).toUpperCase()}</div>
          <div style={{ flex: 1, minWidth: 0 }}><div className="user-name">{user.displayName}</div><div className="user-role">{user.role === "support-agent" ? "Operations agent" : "Customer · " + user.customerId}</div></div>
          <button className="icon-button" title="Sign out" aria-label="Sign out" onClick={logout}>↗</button>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div>
            <div className="eyebrow">STARTER CX <span> / </span><strong>{activePanel === "overview" ? "WORKSPACE" : "OPERATIONS"}</strong></div>
            <div className="top-title">{activePanel === "overview" ? "Customer experience console" : "Operations & observability"}</div>
          </div>
          <div className="top-actions">
            <span className="pill pill-green"><span className="status-dot" /> {health.status === "unavailable" ? "CHECK HEALTH" : "DEMO ENVIRONMENT"}</span>
            <button className="icon-button" title="Refresh health" aria-label="Refresh health" onClick={() => fetch("/api/health").then(r=>r.json()).then(setHealth).catch(()=>undefined)}>↻</button>
          </div>
        </header>

        <div className="content">
          {activePanel === "overview" ? (
            <>
              <div className="page-heading">
                <div><div className="eyebrow">YOUR WORKSPACE <span>/</span> <strong>OCT 2026</strong></div><h1>Good to see you, {firstName} <span aria-hidden="true">✦</span></h1><p>Track your demo account, ask for help, and review each guarded action before it runs.</p></div>
                <div className="live-badge"><span className="status-dot" /> {health.geminiConfigured ? "GEMINI API CONFIGURED" : "DETERMINISTIC FALLBACK"}</div>
              </div>

              <div className="stat-grid">
                <div className="stat-card"><div className="stat-top"><span>Current plan</span><span className="stat-icon">◈</span></div><div className="stat-value">{user.role === "support-agent" ? "Ops" : "Connect 5"}</div><div className="stat-foot"><span className="trend">●</span> {user.role === "support-agent" ? "Support access" : "Monthly synthetic plan"}</div></div>
                <div className="stat-card"><div className="stat-top"><span>Data used</span><span className="stat-icon">⌁</span></div><div className="stat-value">{user.role === "support-agent" ? "—" : usage + " GB"}</div><div className="stat-foot"><span className="trend">{user.role === "support-agent" ? "ROLE" : usagePct + "%"}</span> {user.role === "support-agent" ? "No customer data" : "of 5 GB allowance"}</div></div>
                <div className="stat-card"><div className="stat-top"><span>Next bill</span><span className="stat-icon">₹</span></div><div className="stat-value">{user.role === "support-agent" ? "—" : "₹549"}</div><div className="stat-foot"><span className="trend">24 Oct</span> {user.role === "support-agent" ? "Operations role" : "Synthetic due date"}</div></div>
                <div className="stat-card"><div className="stat-top"><span>AI assistant</span><span className="stat-icon">✧</span></div><div className="stat-value" style={{ fontSize: 22 }}>{health.geminiConfigured ? "Gemini" : "Guarded"}</div><div className="stat-foot"><span className="trend">●</span> {health.geminiConfigured ? "Live provider ready" : "Safe fallback active"}</div></div>
              </div>

              {!health.geminiConfigured && <div className="alert-strip"><span>◷</span><span>Gemini API key is not configured yet. The app can still run reviewer-mode workflows. Add GEMINI_API_KEY in Vercel Environment Variables to test live AI.</span></div>}

              <div className="workspace-grid">
                <section className="card">
                  <div className="card-head"><div className="card-heading"><div className="card-icon">✧</div><div><h2>AI support assistant</h2><p>Gemini intent routing · verified app actions</p></div></div><span className="pill">TRACEABLE</span></div>
                  <div className="chat-body" ref={chatRef}>
                    <div className="date-divider">SESSION CONVERSATION</div>
                    {messages.map(m => (
                      <div key={m.id} className={"message-row " + m.speaker}>
                        <div className="message-avatar">{m.speaker === "assistant" ? "S" : user.displayName.slice(0,1).toUpperCase()}</div>
                        <div className="message-stack"><div className="message-meta">{m.speaker === "assistant" ? "Starter assistant" : "You"} · {m.time}</div><div className="message-bubble">{m.text}</div></div>
                      </div>
                    ))}
                    {chatLoading && <div className="message-row"><div className="message-avatar">S</div><div className="message-stack"><div className="message-meta">Starter assistant · working</div><div className="thinking"><span /><span /><span /></div></div></div>}
                    {pending && <div className="pending-card"><div className="pending-head"><span>◷</span> CONFIRM BEFORE CREATING CASE</div><div className="pending-copy">{pending.summary}<br />This action will be saved only if you confirm. No customer-side change occurs before confirmation.</div><div className="pending-actions"><button className="confirm-button" disabled={actionLoading} onClick={() => void resolveAction("confirm")}>{actionLoading ? "Processing…" : "Confirm and create case"}</button><button className="cancel-button" disabled={actionLoading} onClick={() => void resolveAction("cancel")}>Cancel request</button></div></div>}
                    {messages.length === 0 && <div className="empty-state">Start with a prompt below to test the assistant.</div>}
                  </div>
                  <div className="chat-compose">
                    <div className="prompt-chips">
                      <button className="prompt-chip" onClick={() => void sendMessage("What is my current bill?")}>Check bill</button>
                      <button className="prompt-chip" onClick={() => void sendMessage("How much data have I used?")}>Data usage</button>
                      <button className="prompt-chip" onClick={() => void sendMessage("My mobile network is not working.")}>Network issue</button>
                      <button className="prompt-chip" onClick={() => void sendMessage("Please open a support case for my slow internet.")}>Open a case</button>
                    </div>
                    <div className="composer"><textarea aria-label="Message the assistant" rows={1} placeholder="Describe the issue or ask about your synthetic account…" value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={handleComposerKey} /><button className="send-button" disabled={!draft.trim() || chatLoading} onClick={() => void sendMessage()} aria-label="Send message">↑</button></div>
                    <div className="compose-hint"><span>Enter to send · Shift + Enter for a new line</span><span>AI is not allowed to authorize actions</span></div>
                  </div>
                </section>

                <div className="right-column">
                  <section className="card">
                    <div className="card-head"><div className="card-heading"><div className="card-icon">◉</div><div><h2>{user.role === "support-agent" ? "Operations identity" : "Account overview"}</h2><p>Verified synthetic record</p></div></div><span className="pill pill-green">VERIFIED</span></div>
                    <div className="account-body">
                      <div className="account-top"><div className="account-avatar">{user.displayName.split(" ").map(v=>v[0]).join("").slice(0,2).toUpperCase()}</div><div><div className="account-name">{user.displayName}</div><div className="account-id">{user.customerId}</div></div></div>
                      <div className="account-divider" />
                      {user.role === "support-agent" ? <div className="mini-grid"><div className="mini-stat"><span>Role</span><strong>Agent</strong></div><div className="mini-stat"><span>Scope</span><strong>Ops only</strong></div></div> : <>
                        <div className="data-label"><span>Monthly data allowance</span><strong>{usage.toFixed(1)} / 5 GB</strong></div><div className="progress-track"><div className="progress-fill" style={{ width: usagePct + "%" }} /></div>
                        <div className="account-divider" />
                        <div className="mini-grid"><div className="mini-stat"><span>Monthly bill</span><strong>₹549</strong></div><div className="mini-stat"><span>Due date</span><strong>24 Oct</strong></div></div>
                      </>}
                    </div>
                  </section>
                  <section className="card">
                    <div className="card-head"><div className="card-heading"><div className="card-icon">↗</div><div><h2>Quick actions</h2><p>Guarded, test-friendly workflows</p></div></div></div>
                    <div className="action-list">
                      <button className="action-item" style={{ width: "100%", border: 0, background: "transparent", color: "inherit", textAlign: "left" }} onClick={() => void sendMessage("What is my plan and current data usage?")}><span className="action-icon">⌁</span><span className="action-copy"><span className="action-title">Account & plan</span><span className="action-subtitle">Review plan, usage and next bill</span></span><span className="action-arrow">›</span></button>
                      <button className="action-item" style={{ width: "100%", border: 0, background: "transparent", color: "inherit", textAlign: "left" }} onClick={() => void sendMessage("Please diagnose my mobile network problem.")}><span className="action-icon">⌁</span><span className="action-copy"><span className="action-title">Network diagnostics</span><span className="action-subtitle">Check the synthetic service status</span></span><span className="action-arrow">›</span></button>
                      <button className="action-item" style={{ width: "100%", border: 0, background: "transparent", color: "inherit", textAlign: "left" }} onClick={() => void sendMessage("Please open a support case because my service is slow.")}><span className="action-icon">＋</span><span className="action-copy"><span className="action-title">Create a support case</span><span className="action-subtitle">Review details and confirm first</span></span><span className="action-arrow">›</span></button>
                    </div>
                  </section>
                </div>
              </div>

              <div className="section-grid">
                <section className="card">
                  <div className="card-head"><div className="card-heading"><div className="card-icon">✓</div><div><h2>Challenge readiness</h2><p>Core behaviors to exercise before submission</p></div></div><span className="pill">CHECKLIST</span></div>
                  <div className="checklist">
                    <div className="check-row"><div className="check-icon">✓</div><div><div className="check-title">Identity and access boundaries</div><div className="check-description">Try Alex and Jordan separately to confirm customer data does not cross sessions.</div></div></div>
                    <div className="check-row"><div className="check-icon">✓</div><div><div className="check-title">Human-confirmed actions</div><div className="check-description">Ask for a support case, cancel it, then try again and confirm. Only the confirmed case should be created.</div></div></div>
                    <div className="check-row"><div className="check-icon">✓</div><div><div className="check-title">AI provider fallback</div><div className="check-description">With Gemini configured, verify live intent classification. Without it, confirm reviewer fallback is labelled clearly.</div></div></div>
                    <div className="check-row"><div className="check-icon">✓</div><div><div className="check-title">Audit events and idempotency</div><div className="check-description">Operations users can inspect summarized events; repeated case confirmation must not create duplicates.</div></div></div>
                  </div>
                </section>
                <section className="card">
                  <div className="card-head"><div className="card-heading"><div className="card-icon">⌘</div><div><h2>System components</h2><p>Live configuration status</p></div></div></div>
                  <div className="ops-body">
                    <div className="event-list">
                      <div className="event-row"><span className="event-name">Web application</span><span className="pill pill-green">ONLINE</span></div>
                      <div className="event-row"><span className="event-name">Neon database</span><span className={"pill " + (health.database === "ready" ? "pill-green" : "")}>{health.database === "ready" ? "CONNECTED" : "CHECK CONFIG"}</span></div>
                      <div className="event-row"><span className="event-name">Gemini API</span><span className={"pill " + (health.geminiConfigured ? "pill-green" : "")}>{health.geminiConfigured ? "CONFIGURED" : "PENDING KEY"}</span></div>
                      <div className="event-row"><span className="event-name">Session protection</span><span className="pill pill-green">HTTP-ONLY</span></div>
                      <div className="event-row"><span className="event-name">Case confirmation</span><span className="pill pill-green">REQUIRED</span></div>
                    </div>
                    <div className="account-divider" />
                    <div className="check-description">This environment is a challenge demo with synthetic accounts. It is not connected to any real telecom subscriber service.</div>
                  </div>
                </section>
              </div>
            </>
          ) : (
            <>
              <div className="page-heading"><div><div className="eyebrow">ADMIN WORKSPACE <span>/</span> <strong>ROLE-GATED</strong></div><h1>Operations & observability</h1><p>Aggregated case counts and sanitized application events. No raw session token is exposed.</p></div><button className="small-button" onClick={() => void openOperations()}>↻ Refresh data</button></div>
              {opsError && <div className="alert-strip"><span>◷</span>{opsError}</div>}
              {!isOpsUser && !ops && <section className="card"><div className="empty-state">This page is restricted to the synthetic support-agent role. Sign out and sign in as support.agent to inspect the operations view.</div></section>}
              {ops && <div className="stat-grid">
                <div className="stat-card"><div className="stat-top"><span>Audit events</span><span className="stat-icon">≋</span></div><div className="stat-value">{ops.totalEvents}</div><div className="stat-foot">Persisted synthetic workflow events</div></div>
                <div className="stat-card"><div className="stat-top"><span>Total support cases</span><span className="stat-icon">＋</span></div><div className="stat-value">{ops.totalCases}</div><div className="stat-foot">Idempotency protected</div></div>
                <div className="stat-card"><div className="stat-top"><span>Open cases</span><span className="stat-icon">◷</span></div><div className="stat-value">{ops.openCases}</div><div className="stat-foot">Awaiting resolution</div></div>
                <div className="stat-card"><div className="stat-top"><span>AI mode</span><span className="stat-icon">✧</span></div><div className="stat-value" style={{ fontSize: 20 }}>{health.geminiConfigured ? "Gemini" : "Fallback"}</div><div className="stat-foot">Secret never returned to browser</div></div>
              </div>}
              <section className="card">
                <div className="card-head"><div className="card-heading"><div className="card-icon">≋</div><div><h2>Recent audit events</h2><p>Latest 25 recorded events · details sanitized</p></div></div><span className="pill">READ-ONLY</span></div>
                {ops?.recentEvents.length ? <div className="checklist">{ops.recentEvents.map((event, i)=><div key={event.event_type + event.created_at + i} className="check-row"><div className="check-icon">{event.status === "success" ? "✓" : "·"}</div><div style={{ flex: 1 }}><div className="check-title">{event.event_type}</div><div className="check-description">{event.status} · {new Date(event.created_at).toLocaleString()}</div></div></div>)}</div> : <div className="empty-state">{opsError ? "No operations data loaded." : "No events are available yet. Use the customer workflow to generate test events, then refresh."}</div>}
              </section>
              <div style={{ marginTop: 14 }}><button className="small-button" onClick={() => setActivePanel("overview")}>← Back to customer workspace</button></div>
            </>
          )}
          <div className="foot-note"><span>STARTER CX · TOPCODER GEMINI CX/TELCO</span><span>TEST BUILD · SYNTHETIC DATA ONLY</span></div>
        </div>
      </section>
    </main>
  );
}

import React, { useEffect, useState } from "react";
import useReveal from "./useReveal.js";

const APP_URL = "https://observeagents.ai";
const CONTACT = "mailto:hello@observeagents.ai";

const FEATURES = [
  { icon: "◎", color: "#7CFFB2", title: "Runtime Discovery",
    desc: "Live execution traces from every AI system — sessions, steps, LLM calls, tool use — the moment telemetry arrives." },
  { icon: "▦", color: "#6FA8FF", title: "Asset Intelligence",
    desc: "Every AI system becomes an inventory card: models, providers, tools, capabilities, and findings that read like an auditor's worklist." },
  { icon: "⛨", color: "#FF5C7A", title: "Security Intelligence",
    desc: "Shell access, database reach, MCP tool surface, sensitive-system access — risky behavior surfaced before it's a problem." },
  { icon: "◈", color: "#B47AFF", title: "Cost Intelligence",
    desc: "Token usage and spend signals per agent, per model, per team — from the same telemetry, no billing exports." },
  { icon: "❋", color: "#FFB547", title: "Advisory Guardrails",
    desc: "Observe-only guardrails: detect, explain, recommend. Nothing is blocked until you decide it should be." },
  { icon: "⌘", color: "#2DD4BF", title: "Dependency Map",
    desc: "Which agent talks to which database, CRM, API, and MCP server — the real integration graph, from runtime evidence." },
];

function Nav() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <nav className={`nav${scrolled ? " scrolled" : ""}`}>
      <div className="nav-inner">
        <a href="#" className="brand"><span className="mark">◆</span>ObserveAgents</a>
        <div className="nav-links">
          <a href="#product">Product</a>
          <a href="#how">How it works</a>
          <a href="#privacy">Privacy</a>
          <a href="#products">Products</a>
        </div>
        <a className="btn small solid" href={APP_URL}>Open the platform</a>
      </div>
    </nav>
  );
}

function Hero() {
  return (
    <header className="hero">
      <div className="hero-bg" />
      <div className="hero-glow" />
      <div className="wrap">
        <div className="eyebrow rise">Enterprise AI Intelligence Platform</div>
        <h1>
          <span className="rise d1">See your real</span>
          <span className="rise d2"> AI footprint.</span>
          <span className="mint rise d3">No manual registration needed.</span>
        </h1>
        <p className="sub rise d4">
          ObserveAgents turns runtime telemetry into a living map of your AI estate —
          what exists, what is running, how it is connected, and how it evolves.
        </p>
        <div className="hero-ctas rise d5">
          <a className="btn solid" href={APP_URL}>Start observing</a>
          <a className="btn" href="#how">2-minute quick start</a>
        </div>
        <div className="frame reveal-scale">
          <div className="frame-bar">
            <span /><span /><span />
            <div className="url">observeagents.ai — Asset Intelligence</div>
          </div>
          <img src="/shots/assets.png" alt="ObserveAgents Asset Intelligence: discovered AI systems with models, providers, tools, and findings" />
        </div>
      </div>
    </header>
  );
}

function TrustStrip() {
  const claims = [
    ["OpenTelemetry", "native"],
    ["No proprietary", "SDK"],
    ["OTLP", "JSON + protobuf"],
    ["Prompts", "never stored"],
  ];
  return (
    <div className="strip">
      <div className="wrap strip-row">
        {claims.map(([a, b], i) => (
          <span key={a} className="badge reveal" style={{ "--stagger": `${i * 0.09}s` }}>
            {a} <b>{b}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

function Statement() {
  return (
    <section className="statement">
      <div className="wrap">
        <div className="section-eyebrow reveal">Why ObserveAgents</div>
        <h2>
          <span className="line reveal">The system of record</span>
          <span className="line reveal" style={{ "--stagger": "0.12s" }}>for enterprise AI.</span>
        </h2>
        <p className="section-sub reveal" style={{ "--stagger": "0.24s" }}>
          Tracing tools show you spans. ObserveAgents answers the questions your
          organization actually asks: what AI exists here, who owns it, what can it
          reach, what does it cost — and what needs attention today. From the agents
          your teams built intentionally to the shadow AI nobody knew about.
        </p>
      </div>
    </section>
  );
}

function Features() {
  return (
    <section id="product">
      <div className="wrap">
        <div className="section-eyebrow reveal">The platform</div>
        <h2 className="reveal">One telemetry stream in.<br />A complete AI inventory out.</h2>
        <div className="grid">
          {FEATURES.map((f, i) => (
            <div key={f.title} className="card reveal" style={{ "--stagger": `${(i % 3) * 0.1}s` }}>
              <div className="icon" style={{ background: `${f.color}1A`, color: f.color }}>{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </div>
          ))}
        </div>

        <div className="feature-row">
          <div className="feature-copy reveal">
            <h3>Runtime, arranged the way agents actually run</h3>
            <p>
              Every prompt, every step, every tool call — grouped by agent session,
              with a waterfall timeline showing exactly where each request spent its time.
            </p>
            <ul>
              <li>Sessions group multi-turn agent work automatically</li>
              <li>LLM, tool, MCP, retrieval, and database steps classified per span</li>
              <li>Works with Claude Code, LangChain, CrewAI, and any OTel SDK</li>
            </ul>
          </div>
          <div className="feature-shot reveal-scale">
            <img src="/shots/runtime.png" alt="Runtime execution traces grouped by agent session" loading="lazy" />
          </div>
        </div>

        <div className="feature-row flip">
          <div className="feature-copy reveal">
            <h3>Findings that read like a worklist, not a log</h3>
            <p>
              Slow calls, error patterns, risky capabilities, unmanaged systems —
              deduplicated, grouped, counted, and ranked by severity. Resolve or
              dismiss each one; the evidence stays attached.
            </p>
            <ul>
              <li>Security, performance, operations, and inventory categories</li>
              <li>Repeated occurrences collapse into one finding with a count</li>
              <li>Derived from runtime evidence — never from stored content</li>
            </ul>
          </div>
          <div className="feature-shot reveal-scale">
            <img src="/shots/findings.png" alt="Findings list with severity, category, and occurrence counts" loading="lazy" />
          </div>
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section id="how" className="dev">
      <div className="wrap dev-grid">
        <div>
          <div className="section-eyebrow reveal">How it works</div>
          <h2 className="reveal">Point any OpenTelemetry SDK at Observe.</h2>
          <p className="section-sub reveal">
            No Collector required. No proprietary SDK. If it speaks OTLP —
            JSON or protobuf — it shows up in Runtime within seconds.
          </p>
          <div className="steps">
            <div className="step reveal">
              <div className="step-num">01</div>
              <div>
                <h4>Create an API key</h4>
                <p>One key per team or experiment. The key determines the organization — isolation is built in.</p>
              </div>
            </div>
            <div className="step reveal" style={{ "--stagger": "0.1s" }}>
              <div className="step-num">02</div>
              <div>
                <h4>Set two environment variables</h4>
                <p>Endpoint and authorization header. Your existing instrumentation does the rest.</p>
              </div>
            </div>
            <div className="step reveal" style={{ "--stagger": "0.2s" }}>
              <div className="step-num">03</div>
              <div>
                <h4>Watch your first trace appear</h4>
                <p>Open Runtime, then press Run Intelligence — capabilities and findings derive automatically.</p>
              </div>
            </div>
          </div>
        </div>
        <div>
          <div className="code reveal-scale">
            <div className="code-bar"><span>any OpenTelemetry SDK</span><span>shell</span></div>
            <pre>{`# `}<span className="c">Where traces go</span>{`
`}<span className="k">export</span>{` OTEL_EXPORTER_OTLP_ENDPOINT=`}<span className="s">https://observeagents.ai/otel</span>{`
`}<span className="k">export</span>{` OTEL_EXPORTER_OTLP_HEADERS=`}<span className="s">"Authorization=Bearer &lt;your-key&gt;"</span>{`
`}<span className="k">export</span>{` OTEL_EXPORTER_OTLP_PROTOCOL=`}<span className="s">http/protobuf</span>{`

# `}<span className="c">Who this agent is in Observe</span>{`
`}<span className="k">export</span>{` OTEL_SERVICE_NAME=`}<span className="s">support-triage-agent</span>{`
`}<span className="k">export</span>{` OTEL_RESOURCE_ATTRIBUTES=`}<span className="s">deployment.environment=production,team=support</span></pre>
          </div>
          <div className="code reveal-scale" style={{ "--stagger": "0.1s" }}>
            <div className="code-bar"><span>or auto-instrument with OpenLLMetry</span><span>python</span></div>
            <pre><span className="c"># pip install traceloop-sdk</span>{`
`}<span className="k">from</span>{` traceloop.sdk `}<span className="k">import</span>{` Traceloop

Traceloop.init(
    api_endpoint=`}<span className="s">"https://observeagents.ai/otel"</span>{`,
    headers={"Authorization": `}<span className="s">"Bearer &lt;your-key&gt;"</span>{`},
)`}</pre>
          </div>
        </div>
      </div>
    </section>
  );
}

function Privacy() {
  const cards = [
    { k: "sha256 + size_bytes", t: "Hashes, not content",
      d: "Prompts, responses, tool arguments, and messages are replaced at ingestion with a hash, a byte size, and counts. The content itself is discarded — it never touches disk." },
    { k: "verdicts only", t: "Signals without retention",
      d: "Security and performance findings are derived in-flight from metadata and structure. You get the alert; we never keep the conversation." },
    { k: "org-scoped everything", t: "Isolation by construction",
      d: "The API key determines the organization. Every span, asset, and finding is stamped and filtered by it — no cross-tenant reads, period." },
  ];
  return (
    <section id="privacy" className="privacy">
      <div className="wrap">
        <div className="section-eyebrow reveal">Privacy-first by construction</div>
        <h2 className="reveal" style={{ margin: "0 auto" }}>Your prompts are none of our business.</h2>
        <p className="section-sub reveal" style={{ margin: "18px auto 0" }}>
          Most platforms scan your content and promise to redact it. ObserveAgents never
          persists it at all — the deciding difference for regulated teams that can't ship
          prompts to a SaaS.
        </p>
        <div className="privacy-cards">
          {cards.map((c, i) => (
            <div key={c.t} className="card reveal" style={{ "--stagger": `${i * 0.1}s` }}>
              <div className="big">{c.k}</div>
              <h3>{c.t}</h3>
              <p>{c.d}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Products() {
  return (
    <section id="products">
      <div className="wrap">
        <div className="section-eyebrow reveal">Two products, one spine</div>
        <h2 className="reveal">Start by seeing. Graduate to control.</h2>
        <p className="section-sub reveal">
          Both products share the same AI inventory — so observation can become
          enforcement one team at a time, without a second vendor.
        </p>
        <div className="products">
          <div className="product reveal">
            <span className="tag" style={{ background: "rgba(124,255,178,0.1)", color: "#7CFFB2" }}>Observability</span>
            <h3>See what AI is actually running.</h3>
            <p>What it connects to, and where it needs attention — from telemetry alone.</p>
            <ul>
              <li>Runtime traces, sessions, and timelines</li>
              <li>Asset inventory with capabilities and findings</li>
              <li>Guardrails that observe, explain, and recommend</li>
            </ul>
          </div>
          <div className="product reveal" style={{ "--stagger": "0.12s" }}>
            <span className="tag" style={{ background: "rgba(111,168,255,0.1)", color: "#6FA8FF" }}>Gateway</span>
            <h3>Control AI traffic without instrumenting every app.</h3>
            <p>One proxy in front of your providers — budgets, policies, and optional enforcement.</p>
            <ul>
              <li>Provider keys managed in one place</li>
              <li>Budgets and spend visibility per team</li>
              <li>Optional enforcement, one team at a time</li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function CtaBand() {
  return (
    <section className="cta-band">
      <div className="wrap">
        <h2 className="reveal">Watch your first trace appear<br />in the next two minutes.</h2>
        <div className="hero-ctas reveal" style={{ "--stagger": "0.15s" }}>
          <a className="btn solid" href={APP_URL}>Start observing</a>
          <a className="btn" href={CONTACT}>Talk to us</a>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer>
      <div className="wrap foot">
        <a href="#" className="brand"><span className="mark">◆</span>ObserveAgents</a>
        <div className="links">
          <a href="#product">Product</a>
          <a href="#privacy">Privacy</a>
          <a href={APP_URL}>Platform</a>
          <a href={CONTACT}>Contact</a>
        </div>
        <div className="copy">© {new Date().getFullYear()} ObserveAgents</div>
      </div>
    </footer>
  );
}

export default function App() {
  useReveal();
  return (
    <>
      <Nav />
      <Hero />
      <TrustStrip />
      <Statement />
      <Features />
      <HowItWorks />
      <Privacy />
      <Products />
      <CtaBand />
      <Footer />
    </>
  );
}

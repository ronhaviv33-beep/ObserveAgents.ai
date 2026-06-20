# AI Asset Management — Introduction for New Team Members

## What is this platform?

Think of it like a map for all the AI agents in your company.

Every day, developers build AI agents — small programs that call OpenAI, Anthropic, or other AI services to do things like answer questions, write code, summarize documents, or automate tasks. The problem is that nobody really knows **how many** of these agents exist, **who owns them**, **how much they cost**, or **whether they are safe**.

This platform solves that. It sits between your AI agents and the AI providers (like OpenAI). Every time an agent makes a request, we see it, log it, and show it on a dashboard.

---

## The two types of agents

### 1. Verified Agents (we know about them — 95% confidence)
These are agents that were registered officially and route their traffic through our gateway. We can see exactly who they belong to, how much they cost, and whether they're behaving normally.

### 2. Potential Agents (we found them but don't know who owns them — 30–80% confidence)
These are agents we discovered by looking at network traffic, billing records, and API key usage. Someone created them without going through the official process. They need to be claimed by a team or validated.

---

## The 6 main sections

| Section | What it does |
|---|---|
| **Agent Inventory** | The full list of all agents — verified, under review, managed, or retired |
| **Discovery Center** | Agents we found that haven't been claimed yet. Teams can claim them here. |
| **Governance Center** | Review queue — new agents need approval before they are considered "managed" |
| **Cost Intelligence** | Shows how much each team is spending on AI per month, broken down by agent |
| **Security Intelligence** | Alerts for anything suspicious — unusual usage, possible prompt injection, policy violations |
| **Ecosystem Discovery** | A view of which AI providers (OpenAI, Anthropic, etc.) your organization is connected to |

---

## How does an agent get into the system?

There are two ways:

**Way 1 — The right way:** A developer points their AI code at our gateway URL instead of directly at OpenAI. We see every request and automatically add the agent to the inventory.

**Way 2 — Discovery:** We scan billing records, API key usage, and network logs to find agents that are calling AI providers directly. These show up as "Potential Agents" and need to be claimed.

---

## How does the gateway work?

It's a proxy. Normally, your code looks like this:

```
Your App → OpenAI
```

After connecting to our platform, it looks like this:

```
Your App → Our Gateway → OpenAI
```

The only change in the code is changing one URL. Everything else stays the same.

When a request passes through the gateway, we:
- Record who sent it (team + agent name)
- Record how many tokens were used
- Check if it violates any security policies
- Make it visible in the dashboard

---

## Who uses the platform?

| Role | What they do |
|---|---|
| **Admin** | Full access — can edit agents, manage users, approve agents, set policies |
| **Analyst** | Can view everything and claim/validate agents, but cannot change settings |
| **Viewer** | Read-only — can see all the dashboards but cannot make changes |

---

## 3 things to do on day one

1. **Look at Agent Inventory** — see what's already there for your team
2. **Check Discovery Center** — there may be agents your team built that haven't been claimed yet
3. **Look at Cost Intelligence** — see what your team is spending

---

## Glossary

| Word | What it means |
|---|---|
| **Agent** | A piece of code that calls an AI API to do a task |
| **Gateway** | Our proxy that sits between your agent and the AI provider |
| **Claim** | A team takes ownership of a discovered agent |
| **Validate** | An admin confirms that a discovered agent is real and belongs to the org |
| **Lifecycle Status** | The stage an agent is in: Unassigned → Needs Validation → Managed → Retired |
| **Asset Key** | A unique ID we generate for each agent (SHA-256 hash) |
| **Criticality** | How important the agent is: Low / Medium / High |

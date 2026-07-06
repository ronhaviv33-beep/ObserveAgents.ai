# Design note: from a local guard script to product behavior

*How a Bash guard script that blocks secret-file access and blind remote execution maps into ObserveAgents — as findings in Observability, as optional policy in the Gateway. General to enterprise AI agents on any platform.*

## 1. Verdict

The guard script's two rules — protect secret-bearing files, stop blind remote-code execution — are exactly the class of signal ObserveAgents is built to carry. Don't port the script; port the **patterns** into the two surfaces: Observability turns them into findings, the Gateway optionally turns them into policy. Same rules, two postures.

## 2. Observability: discover and recommend

Detected from runtime evidence (span attributes: tool names, `gen_ai.tool.name`, command metadata) and surfaced as **security findings** on the agent that did it — never as blocked actions:

- `secret_path_access` — a tool/shell step touched a credential-bearing path → finding (high), evidence = which agent, which step, when.
- `blind_remote_execution` — a fetch-piped-to-interpreter pattern observed → finding (high), plus a guardrail recommendation ("this agent executes unreviewed remote content; consider routing it through the Gateway").
- Privacy stays intact: the scan runs **in-flight at ingestion, before the privacy scrub discards content** — only the verdict is stored (pattern name, hash, span id), never the command line itself. Security checks without content retention.
- The Advisor layer then converts repeats into a skill recommendation (e.g. "add an install-approval step"), keeping it advisory.

## 3. Gateway: control only when explicitly configured

The same pattern catalog becomes **policy rules** on proxied traffic and tool-call metadata:

- Teams start in **observe** (identical behavior to Observability: log + finding).
- **alert** notifies on match; **enforce** returns a policy block (HTTP 403 with the rule name) — only for teams an admin explicitly graduated, with the existing "would block (30d)" shadow preview first.
- Policies reference the shared pattern catalog, so a rule tuned from Observability findings is the same rule the Gateway enforces. One catalog, two postures.

**Observability discovers and recommends. Gateway controls only when explicitly configured.**

## 4. Bash-only assumptions to generalize

The script assumes a Linux shell. The catalog must be **per-platform pattern packs** over two abstract behaviors — *secret access* and *fetch-then-execute* — not one regex file:

| Abstract behavior | Bash/Linux examples | PowerShell/Windows equivalents |
|---|---|---|
| Fetch piped to interpreter | `curl \| sh`, `wget \| sh`, `eval "$(curl …)"` | `iwr … \| iex`, `irm … \| iex`, `Invoke-Expression (Invoke-WebRequest …)` |
| Obfuscated payload then execute | `base64 -d \| sh` | `powershell -EncodedCommand <b64>`, `[Convert]::FromBase64String(…)` → `iex`, decoded file then `& $file` |
| Secret-bearing paths | `~/.ssh`, `~/.aws/credentials`, `.env`, `/etc/shadow` | `%USERPROFILE%\.aws`, DPAPI-protected stores, Windows Credential Manager, certificate stores (`Cert:\`), `web.config`/`unattend.xml`-style secret files, browser credential DBs |
| Interpreter identity | `sh`, `bash`, `zsh` | `powershell.exe`, `pwsh`, `cmd /c`, `mshta`, `rundll32` as execution proxies |

Also generalize: case-insensitivity and alias resolution (`iwr`/`irm` are aliases), argument reordering, and the fact that on Windows the "pipe" often hides inside a single encoded command rather than a visible `|`.

## 5. One product sentence

ObserveAgents ships one catalog of risky-execution and secret-access patterns: the Observability surface reports them as findings with recommendations, and the Gateway can enforce the same catalog as blocking policy — per team, only when you switch it on.

## 6. Recommended next step

Create the shared pattern catalog as data, not code — a small versioned table/JSON (behavior class, platform pack, pattern, severity, recommendation text) consumed by both surfaces. Ship it first as **Observability findings only** (in-flight, verdict-only — this is roadmap item L3/O3 already), watch false-positive rates on real traffic, then expose the same catalog as Gateway policy options for enforce-mode teams.

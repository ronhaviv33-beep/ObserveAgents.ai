# Running the Project in VS Code

This guide walks you through running the backend (FastAPI) and frontend (React/Vite)
locally using Visual Studio Code.

---

## Prerequisites

Install these before you start:

| Tool | Version | Download |
|------|---------|----------|
| Visual Studio Code | Latest | https://code.visualstudio.com |
| Python | 3.12+ | https://www.python.org/downloads |
| Node.js | 18+ | https://nodejs.org |
| Git | Any | https://git-scm.com |

---

## Step 1 — Open the project

```
File → Open Folder → select the ai-asset-management folder
```

VS Code will prompt: **"Do you want to install the recommended extensions?"**
Click **Install All**. This adds Python, Pylance, ESLint, Prettier, and Tailwind support.

---

## Step 2 — Create your `.env` file

In the project root, copy the example file:

**Mac / Linux (Terminal):**
```bash
cp .env.example .env
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

Then open `.env` and fill in your API keys:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
JWT_SECRET=any-long-random-string-change-this
```

> The other values have sensible defaults and can be left as-is for local development.

---

## Step 3 — Set up the Python environment

Open the **integrated terminal** in VS Code:
`View → Terminal` (or `Ctrl+`` `)

```bash
# Create a virtual environment
python -m venv venv

# Activate it
source venv/bin/activate        # Mac / Linux
venv\Scripts\Activate.ps1      # Windows PowerShell

# Install Python dependencies
pip install -r requirements.txt
```

Then tell VS Code to use this interpreter:

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
2. Type **"Python: Select Interpreter"**
3. Choose the one that shows `./venv/bin/python` (or `.\venv\Scripts\python.exe` on Windows)

---

## Step 4 — Install frontend dependencies

In the same terminal (or a new one):

```bash
cd dashboard
npm install
cd ..
```

---

## Step 5 — Run with one click (Compound Launch)

This is the easiest way — starts both servers simultaneously.

1. Press `F5` or go to **Run → Start Debugging**
2. In the dropdown at the top of the Run panel, select **`Full Stack (Backend + Frontend)`**
3. Click the green **▶ Play** button

Both servers start in the integrated terminal panel. You'll see two tabs:

- **Backend: FastAPI** → `http://localhost:8000`
- **Frontend: Vite Dev** → `http://localhost:5173`

Open your browser to **http://localhost:5173** to use the dashboard.

---

## Step 6 — Log in

On first start the backend automatically creates an admin account.

The password is set by `ADMIN_SEED_PASSWORD` in your `.env` file (default: `Admin123!`).
Check `ADMIN_SEED_EMAIL` if set, otherwise the default is:

```
Email:    admin@ai-asset-mgmt.local
Password: Admin123!   ← or whatever you set in .env
```

> Change the password in **Settings → Users** after your first login.

---

## Running them separately (alternative)

If you prefer separate terminals instead of the compound launch:

**Terminal 1 — Backend:**
```bash
source venv/bin/activate   # (Mac/Linux) or venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd dashboard
npm run dev
```

---

## Debugging the backend

To set a breakpoint and step through Python code:

1. Click in the left margin of any `.py` file to add a red dot breakpoint
2. In the Run panel, select **`Backend: FastAPI`** (not the compound)
3. Press **F5**

Execution will pause at your breakpoint. Use the debug toolbar to step over (`F10`), step into (`F11`), or continue (`F5`).

---

## API documentation (Swagger UI)

While the backend is running, open:

```
http://localhost:8000/docs
```

This gives you an interactive API explorer for every endpoint.

---

## Common issues

### `ModuleNotFoundError: No module named 'app'`
You are running Python from the wrong directory. Make sure you're in the project root (`ai-asset-management/`), not inside `app/`.

### `Port 8000 already in use`
Another process is using the port. Find and kill it:
```bash
# Mac / Linux
lsof -i :8000 | grep LISTEN
kill -9 <PID>

# Windows PowerShell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### `VITE_API_BASE not set` / API calls fail
The frontend dev server automatically proxies `/api/*` requests to `http://localhost:8000` — no environment variable needed for local development. If you see API errors, confirm the backend is running and check the terminal for Python errors.

### `npm install` fails on Windows
Make sure Node.js was installed for **all users** (not just current user), or run VS Code as Administrator for the first `npm install`.

### Python interpreter not found
Ensure you created and activated the virtual environment before selecting the interpreter. The `venv` folder must exist inside the project root.

---

## Project structure (quick reference)

```
ai-asset-management/
├── app/                    # FastAPI backend
│   ├── main.py             # Entry point, router registration, startup
│   ├── models.py           # SQLAlchemy ORM models (all DB tables)
│   ├── auth.py             # JWT auth, RBAC helpers
│   ├── routes/             # REST endpoint modules
│   │   ├── agent_inventory.py
│   │   ├── cost_intelligence.py
│   │   └── pricing_registry.py
│   ├── agent_inventory.py  # Agent discovery business logic
│   ├── cost_intelligence.py
│   └── pricing_registry.py
├── dashboard/              # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx         # Root: auth, nav shell, routing
│   │   ├── api.js          # All fetch functions (single source of truth)
│   │   └── pages/          # One file per page
│   │       ├── ExecutiveDashboard.jsx
│   │       ├── AgentInventory.jsx
│   │       ├── DiscoveryCenter.jsx
│   │       ├── GovernanceCenter.jsx
│   │       ├── CostIntelligence.jsx
│   │       ├── SecurityIntelligence.jsx
│   │       ├── EcosystemDiscovery.jsx
│   │       └── PricingRegistry.jsx
│   └── package.json
├── scripts/
│   └── seed_demo_data.py   # Populate DB with demo agents + telemetry
├── .env.example            # Copy to .env and fill in keys
├── .vscode/                # VS Code launch configs (included in repo)
│   ├── launch.json         # F5 run configs
│   ├── tasks.json          # Install tasks
│   └── extensions.json     # Recommended extensions
└── requirements.txt
```

---

## Seed demo data (optional)

To populate the database with demo agents, teams, and telemetry records so the
dashboard has something to show immediately:

```bash
# Make sure venv is active and you are in the project root
python scripts/seed_demo_data.py
```

Then refresh the dashboard — the Agent Inventory, Cost Intelligence, and
Executive Dashboard will show realistic demo data.

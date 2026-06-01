from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import Base
from app.schemas import (
    AskRequest, AskResponse,
    TelemetryRecord, TelemetrySummary,
    BudgetRuleCreate, BudgetRuleOut, BudgetStatusItem,
)
from app import telemetry as tel
from app import budget as bud
from app.openai_client import complete

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AIFinOps Guard",
    description="AI Runtime Intelligence Platform — telemetry, cost, and governance gateway",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "AIFinOps Gateway Running", "version": "0.3.0"}


# ─── AI Gateway ───────────────────────────────────────────────────────────────

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, db: Session = Depends(get_db)):
    # Budget enforcement — runs before calling any LLM
    check = bud.check(db, team=req.team, agent=req.agent)
    if not check["allowed"]:
        blk = check["blocked_by"]
        raise HTTPException(
            status_code=429,
            detail=(
                f"Budget limit exceeded for team '{blk['team']}'"
                + (f", agent '{blk['agent']}'" if blk["agent"] else "")
                + f": ${blk['spend']:.4f} spent of ${blk['limit']:.2f} {blk['period']} limit."
            ),
        )

    try:
        result = await complete(
            prompt=req.prompt,
            model=req.model,
            system_prompt=req.system_prompt,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    record = tel.save(db=db, team=req.team, agent=req.agent, prompt=req.prompt, result=result)

    return AskResponse(
        response=result.content,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        latency_ms=result.latency_ms,
        cost_usd=record.cost_usd,
        telemetry_id=record.id,
        budget_warnings=check["warnings"],
    )


# ─── Telemetry ────────────────────────────────────────────────────────────────

@app.get("/telemetry", response_model=list[TelemetryRecord])
def get_telemetry(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return tel.get_all(db, skip=skip, limit=limit)


@app.get("/telemetry/summary", response_model=TelemetrySummary)
def get_summary(db: Session = Depends(get_db)):
    return tel.get_summary(db)


# ─── Budgets ──────────────────────────────────────────────────────────────────

@app.post("/budgets", response_model=BudgetRuleOut, status_code=201)
def create_budget(rule: BudgetRuleCreate, db: Session = Depends(get_db)):
    return bud.create_rule(
        db,
        team=rule.team,
        agent=rule.agent,
        limit_usd=rule.limit_usd,
        period=rule.period,
        action=rule.action,
    )


@app.get("/budgets", response_model=list[BudgetRuleOut])
def list_budgets(db: Session = Depends(get_db)):
    return bud.get_rules(db)


@app.delete("/budgets/{rule_id}", status_code=204)
def delete_budget(rule_id: int, db: Session = Depends(get_db)):
    if not bud.delete_rule(db, rule_id):
        raise HTTPException(status_code=404, detail="Budget rule not found")


@app.get("/budgets/status", response_model=list[BudgetStatusItem])
def budget_status(db: Session = Depends(get_db)):
    return bud.get_status(db)

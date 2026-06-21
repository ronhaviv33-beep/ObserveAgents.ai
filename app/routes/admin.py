import re as _re
import secrets as _sec

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Organization, User
from app.schemas import OrgCreate, OrgCreated
from app.auth import hash_password, require_platform_admin
from app.roles import seed_roles_for_org

router = APIRouter(tags=["Admin — Platform"])


def _make_org_slug(name: str, db: Session) -> str:
    """Derive a unique URL-safe slug from an org name."""
    base = _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64] or "org"
    slug, n = base, 2
    while db.query(Organization).filter(Organization.slug == slug).first():
        slug = f"{base}-{n}"
        n += 1
    return slug


@router.get("/admin/organizations")
async def list_all_organizations(
    actor=Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """List all organizations on the platform. Platform admin only."""
    orgs = db.query(Organization).order_by(Organization.created_at).all()
    result = []
    for o in orgs:
        user_count = db.query(User).filter(User.organization_id == o.id).count()
        result.append({
            "id":          o.id,
            "name":        o.name,
            "slug":        o.slug,
            "is_internal": o.is_internal,
            "user_count":  user_count,
            "created_at":  o.created_at,
        })
    return result


@router.post("/admin/organizations", response_model=OrgCreated, status_code=201)
async def create_organization(
    req: OrgCreate,
    actor=Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """
    Create a new tenant organization. Platform admin only.

    Auto-seeds the three default roles (admin / analyst / viewer) and creates
    an org-level admin user. If `admin_password` is omitted a secure random
    password is generated; it is returned in `admin_temporary_password` **once**
    and also printed to the server boot log — store it immediately.
    """
    if db.query(Organization).filter(Organization.name == req.name).first():
        raise HTTPException(status_code=409, detail=f"Organization '{req.name}' already exists.")
    if db.query(User).filter(User.email == req.admin_email).first():
        raise HTTPException(status_code=409, detail=f"Email '{req.admin_email}' is already registered.")

    slug = _make_org_slug(req.name, db)
    org = Organization(name=req.name, slug=slug)
    db.add(org)
    db.flush()

    seed_roles_for_org(db, org.id)

    auto_generated = req.admin_password is None
    admin_pw = req.admin_password or _sec.token_urlsafe(20)

    admin_user = User(
        email=req.admin_email,
        name=req.admin_name,
        hashed_password=hash_password(admin_pw),
        role="admin",
        team="Platform",
        organization_id=org.id,
        is_platform_admin=False,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(org)
    db.refresh(admin_user)

    if auto_generated:
        print(
            "\n"
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║           NEW ORG ADMIN — TEMPORARY CREDENTIALS             ║\n"
            "║                                                              ║\n"
            f"║  org     : {org.name:<50} ║\n"
            f"║  email   : {req.admin_email:<50} ║\n"
            f"║  password: {admin_pw:<50} ║\n"
            "║                                                              ║\n"
            "║  Share with the org admin and ask them to change it.        ║\n"
            "╚══════════════════════════════════════════════════════════════╝\n",
            flush=True,
        )

    return OrgCreated(
        id=org.id,
        name=org.name,
        slug=org.slug,
        admin_email=req.admin_email,
        admin_user_id=admin_user.id,
        admin_temporary_password=admin_pw if auto_generated else None,
    )

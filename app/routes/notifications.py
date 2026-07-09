"""
Detection Rules — notification channel admin API (R5).

Admin-only CRUD for webhook notification channels. The webhook URL may embed
a secret, so it is Fernet-encrypted at rest and NEVER returned by any response
(only the host is exposed). Deliveries themselves run in the intelligence
workflow (app/notifications.py), not here.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NotificationChannel, NotificationDelivery, encrypt_credential
from app.auth import require_admin
from app.notifications import safe_host

router = APIRouter()
_log = logging.getLogger("ai_asset_mgmt.notifications")

_ALLOWED_TYPES = {"webhook"}
_ALLOWED_MIN_SEVERITY = {"medium", "high", "critical"}


class ChannelCreate(BaseModel):
    type: str = "webhook"
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1)
    min_severity: str = "medium"


class ChannelPatch(BaseModel):
    enabled: bool | None = None
    name: str | None = None
    min_severity: str | None = None


def _serialize(c: NotificationChannel) -> dict:
    # Deliberately never includes the URL, path, query, or ciphertext.
    return {
        "id": c.id,
        "type": c.type,
        "name": c.name,
        "enabled": c.enabled,
        "host": c.url_host,
        "min_severity": c.min_severity,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


@router.get("/notifications/channels", tags=["Notifications"])
def list_channels(db: Session = Depends(get_db), actor=Depends(require_admin)):
    rows = (
        db.query(NotificationChannel)
        .filter(NotificationChannel.organization_id == actor.organization_id)
        .order_by(NotificationChannel.created_at.desc())
        .all()
    )
    return [_serialize(c) for c in rows]


@router.post("/notifications/channels", status_code=201, tags=["Notifications"])
def create_channel(body: ChannelCreate, db: Session = Depends(get_db), actor=Depends(require_admin)):
    if body.type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported channel type: {body.type}")
    if body.min_severity not in _ALLOWED_MIN_SEVERITY:
        raise HTTPException(status_code=400, detail="min_severity must be medium, high, or critical")
    host = safe_host(body.url)
    if not host or not body.url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="url must be a valid http(s) URL")

    channel = NotificationChannel(
        organization_id=actor.organization_id,
        type=body.type,
        name=body.name,
        enabled=True,
        encrypted_config_json=encrypt_credential(json.dumps({"url": body.url})),
        url_host=host,
        min_severity=body.min_severity,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _serialize(channel)


@router.patch("/notifications/channels/{channel_id}", tags=["Notifications"])
def patch_channel(channel_id: int, body: ChannelPatch, db: Session = Depends(get_db), actor=Depends(require_admin)):
    channel = (
        db.query(NotificationChannel)
        .filter(
            NotificationChannel.id == channel_id,
            NotificationChannel.organization_id == actor.organization_id,
        )
        .first()
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if body.enabled is not None:
        channel.enabled = body.enabled
    if body.name is not None:
        channel.name = body.name
    if body.min_severity is not None:
        if body.min_severity not in _ALLOWED_MIN_SEVERITY:
            raise HTTPException(status_code=400, detail="min_severity must be medium, high, or critical")
        channel.min_severity = body.min_severity
    db.commit()
    db.refresh(channel)
    return _serialize(channel)


@router.delete("/notifications/channels/{channel_id}", status_code=204, tags=["Notifications"])
def delete_channel(channel_id: int, db: Session = Depends(get_db), actor=Depends(require_admin)):
    channel = (
        db.query(NotificationChannel)
        .filter(
            NotificationChannel.id == channel_id,
            NotificationChannel.organization_id == actor.organization_id,
        )
        .first()
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.query(NotificationDelivery).filter(
        NotificationDelivery.channel_id == channel_id,
        NotificationDelivery.organization_id == actor.organization_id,
    ).delete(synchronize_session=False)
    db.delete(channel)
    db.commit()
    return None

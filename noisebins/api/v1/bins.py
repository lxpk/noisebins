from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from noisebins.config import get_settings
from noisebins.db import get_db
from noisebins.models import BinPhoto, ContentHistory, Noisebin, Noisething, User
from noisebins.schemas_api import (
    BinCreate,
    BinReadMember,
    BinUpdate,
    NoisethingCreate,
    NoisethingRead,
    SuggestContentsBody,
    TransferBody,
)
from noisebins.services.audit_log import record_audit
from noisebins.services.labels import build_bin_label_pdf
from noisebins.services.noisecode import generate_noisecode
from noisebins.services.public_payload import bin_public_dict
from noisebins.services.storage import get_storage
from noisebins.users import current_active_user

router = APIRouter(prefix="/bins", tags=["bins"])


def _public_url(noisecode: str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/b/{noisecode}"


@router.get("/search", response_model=list[dict])
async def search_bins(
    q: str = Query(..., min_length=1),
    place_id: uuid.UUID | None = None,
    has_photo: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    tsq = func.plainto_tsquery("english", q)
    stmt = select(Noisebin).where(Noisebin.search_vector.op("@@")(tsq))
    if place_id is not None:
        stmt = stmt.where(Noisebin.noiseplace_id == place_id)
    if has_photo is not None:
        exists_photo = select(BinPhoto.id).where(BinPhoto.bin_id == Noisebin.id).limit(1).exists()
        stmt = stmt.where(exists_photo if has_photo else not_(exists_photo))
    stmt = stmt.options(selectinload(Noisebin.photos)).limit(50)
    rows = (await db.scalars(stmt)).all()
    return [bin_public_dict(b) for b in rows]


@router.get("/limbo", response_model=list[BinReadMember])
async def list_limbo(
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_active_user),
):
    today = datetime.now(UTC).date()
    stmt = (
        select(Noisebin)
        .where(
            or_(
                and_(Noisebin.limbo_after.is_not(None), Noisebin.limbo_after <= today),
                Noisebin.status == "limbo",
            )
        )
        .order_by(Noisebin.limbo_after.asc().nulls_last())
    )
    rows = (await db.scalars(stmt)).all()
    return [_bin_member_dict(b) for b in rows]


def _bin_member_dict(b: Noisebin) -> BinReadMember:
    d = BinReadMember.model_validate(
        b,
        from_attributes=True,
    )
    return d.model_copy(update={"public_url": _public_url(b.noisecode)})


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_bin(
    body: BinCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(current_active_user),
):
    b: Noisebin | None = None
    for _ in range(12):
        code = generate_noisecode()
        b = Noisebin(
            noisecode=code,
            title=body.title,
            description=body.description,
            details=body.details,
            contents_text=body.contents_text,
            noiseplace_id=body.noiseplace_id,
            intent=body.intent,
            limbo_after=body.limbo_after,
            status=body.status,
            shelf_hint=body.shelf_hint,
            maintainer_name=body.maintainer_name,
            maintainer_email=body.maintainer_email,
            maintainer_phone=body.maintainer_phone,
            maintainer_discord=body.maintainer_discord,
            group_maintainer=body.group_maintainer,
        )
        db.add(b)
        try:
            async with db.begin_nested():
                await db.flush()
            await db.refresh(b)
            break
        except IntegrityError:
            db.expunge(b)
            continue
    else:
        raise HTTPException(500, "Could not allocate noisecode")

    await record_audit(
        db,
        actor_user_id=user.id,
        action="bin_created",
        target_type="noisebin",
        target_id=str(b.id),
        payload={"noisecode": b.noisecode},
    )
    return {
        "noisecode": b.noisecode,
        "public_url": _public_url(b.noisecode),
        "id": str(b.id),
    }


@router.get("/{noisecode}", response_model=dict)
async def get_bin_public(
    noisecode: str,
    db: AsyncSession = Depends(get_db),
):
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    await db.refresh(b, ["photos"])
    data = bin_public_dict(b)
    storage = get_storage()
    data["photos"] = [{"sort_order": p.sort_order, "url": storage.public_url(p.blob_key)} for p in b.photos]
    return data


@router.patch("/{noisecode}", response_model=dict)
async def update_bin(
    noisecode: str,
    body: BinUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(current_active_user),
):
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    before = {"contents_text": b.contents_text, "title": b.title}
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(b, k, v)
    await db.flush()
    await db.refresh(b)
    if "contents_text" in data and data["contents_text"] != before.get("contents_text"):
        db.add(
            ContentHistory(
                bin_id=b.id,
                actor_user_id=user.id,
                summary="contents_text updated",
                diff={"before": before.get("contents_text"), "after": b.contents_text},
            )
        )
    return bin_public_dict(b)


@router.post("/{noisecode}/photos", status_code=status.HTTP_201_CREATED)
async def upload_bin_photo(
    noisecode: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(current_active_user),
    file: UploadFile = File(...),
):
    settings = get_settings()
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, "File too large")
    ct = file.content_type or "application/octet-stream"
    if ct not in ("image/jpeg", "image/png", "image/webp", "application/octet-stream"):
        raise HTTPException(400, "Unsupported type")
    storage = get_storage()
    key = storage.store_bytes(raw, ct)
    max_ord = await db.scalar(select(func.coalesce(func.max(BinPhoto.sort_order), -1)).where(BinPhoto.bin_id == b.id))
    db.add(BinPhoto(bin_id=b.id, blob_key=key, sort_order=int(max_ord) + 1))
    await record_audit(
        db,
        actor_user_id=user.id,
        action="bin_photo_added",
        target_type="noisebin",
        target_id=str(b.id),
        payload={"blob_key": key},
    )
    return {"blob_key": key, "url": storage.public_url(key)}


@router.get("/{noisecode}/label.pdf")
async def bin_label(
    noisecode: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_active_user),
):
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    pdf = build_bin_label_pdf(noisecode=b.noisecode, title=b.title)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{b.noisecode}.pdf"'},
    )


@router.post("/{noisecode}/claim", response_model=dict)
async def claim_bin(
    noisecode: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(current_active_user),
):
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    if b.claimed_by_user_id is not None:
        raise HTTPException(409, "Bin already claimed")
    b.claimed_by_user_id = user.id
    b.claimed_at = datetime.now(UTC)
    await record_audit(
        db,
        actor_user_id=user.id,
        action="bin_claimed",
        target_type="noisebin",
        target_id=str(b.id),
    )
    return {"ok": True, "claimed_by_user_id": str(user.id)}


@router.post("/{noisecode}/transfer", response_model=dict)
async def transfer_bin(
    noisecode: str,
    body: TransferBody,
    db: AsyncSession = Depends(get_db),
    user=Depends(current_active_user),
):
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    if b.claimed_by_user_id != user.id:
        raise HTTPException(403, "Only current owner can transfer")
    other = await db.scalar(select(User).where(func.lower(User.email) == body.to_user_email.lower()))
    if other is None:
        raise HTTPException(404, "Target user not found")
    prev = b.claimed_by_user_id
    b.claimed_by_user_id = other.id
    b.claimed_at = datetime.now(UTC)
    await record_audit(
        db,
        actor_user_id=user.id,
        action="bin_transferred",
        target_type="noisebin",
        target_id=str(b.id),
        payload={"from": str(prev), "to": str(other.id)},
    )
    return {"ok": True, "claimed_by_user_id": str(other.id)}


@router.post("/{noisecode}/suggest-contents", response_model=dict)
async def suggest_contents(
    noisecode: str,
    body: SuggestContentsBody,
    db: AsyncSession = Depends(get_db),
    user=Depends(current_active_user),
):
    settings = get_settings()
    if not settings.vision_assist_enabled:
        return {"suggestions": [], "enabled": False}
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    # Stub: no OCR in CI; optional image ignored unless we add Tesseract later
    if body.image_base64:
        try:
            base64.b64decode(body.image_base64[:1000])
        except Exception:
            raise HTTPException(400, "Invalid base64")
    return {
        "enabled": True,
        "suggestions": ["(stub) confirm before saving to bin contents"],
    }


@router.get("/{noisecode}/history", response_model=list[dict])
async def bin_history(
    noisecode: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_active_user),
):
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    rows = (
        await db.scalars(
            select(ContentHistory)
            .where(ContentHistory.bin_id == b.id)
            .order_by(ContentHistory.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "summary": r.summary,
            "diff": r.diff,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/{noisecode}/things", response_model=list[NoisethingRead])
async def list_things(
    noisecode: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_active_user),
):
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    rows = (await db.scalars(select(Noisething).where(Noisething.parent_bin_id == b.id))).all()
    return rows


@router.post("/{noisecode}/things", response_model=NoisethingRead, status_code=status.HTTP_201_CREATED)
async def create_thing(
    noisecode: str,
    body: NoisethingCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(current_active_user),
):
    b = await _get_bin_by_code(db, noisecode)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bin not found")
    t = Noisething(parent_bin_id=b.id, name=body.name, description=body.description, barcode=body.barcode)
    db.add(t)
    await db.flush()
    await db.refresh(t)
    db.add(
        ContentHistory(
            bin_id=b.id,
            actor_user_id=user.id,
            summary=f"Added thing: {body.name}",
            diff=None,
        )
    )
    return t


async def _get_bin_by_code(db: AsyncSession, noisecode: str) -> Noisebin | None:
    stmt = select(Noisebin).where(Noisebin.noisecode == noisecode).options(selectinload(Noisebin.photos))
    return await db.scalar(stmt)

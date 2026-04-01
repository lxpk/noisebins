import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noisebins.db import get_db
from noisebins.models import Noisebin, Noiseplace
from noisebins.schemas_api import PlaceCreate, PlaceRead, PlaceUpdate
from noisebins.services.places import would_create_cycle
from noisebins.users import current_active_user

router = APIRouter(prefix="/places", tags=["places"])


@router.get("", response_model=list[PlaceRead])
async def list_places(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(select(Noiseplace).order_by(Noiseplace.name))
    return list(result.all())


@router.get("/{place_id}", response_model=PlaceRead)
async def get_place(place_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(Noiseplace, place_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    return row


@router.post("", response_model=PlaceRead, status_code=status.HTTP_201_CREATED)
async def create_place(
    body: PlaceCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_active_user),
):
    p = Noiseplace(
        name=body.name,
        description=body.description,
        photo_ref=body.photo_ref,
        parent_place_id=body.parent_place_id,
        maintainer_name=body.maintainer_name,
        maintainer_email=body.maintainer_email,
        group_maintainer=body.group_maintainer,
    )
    db.add(p)
    await db.flush()
    if p.parent_place_id and await would_create_cycle(db, p.id, p.parent_place_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "parent_place_id would create a cycle")
    await db.refresh(p)
    return p


@router.patch("/{place_id}", response_model=PlaceRead)
async def update_place(
    place_id: uuid.UUID,
    body: PlaceUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_active_user),
):
    row = await db.get(Noiseplace, place_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    data = body.model_dump(exclude_unset=True)
    if "parent_place_id" in data:
        if await would_create_cycle(db, place_id, data["parent_place_id"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "parent_place_id would create a cycle")
    for k, v in data.items():
        setattr(row, k, v)
    await db.refresh(row)
    return row


@router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_place(
    place_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_active_user),
):
    row = await db.get(Noiseplace, place_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    n_children = await db.scalar(
        select(func.count()).select_from(Noiseplace).where(Noiseplace.parent_place_id == place_id)
    )
    n_bins = await db.scalar(select(func.count()).select_from(Noisebin).where(Noisebin.noiseplace_id == place_id))
    if (n_children or 0) > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Place has child places")
    if (n_bins or 0) > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Place still has bins")
    await db.delete(row)

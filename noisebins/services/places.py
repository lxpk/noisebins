import uuid

from noisebins.models import Noiseplace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def would_create_cycle(
    db: AsyncSession,
    place_id: uuid.UUID,
    new_parent_id: uuid.UUID | None,
) -> bool:
    if new_parent_id is None:
        return False
    if new_parent_id == place_id:
        return True
    current: uuid.UUID | None = new_parent_id
    seen: set[uuid.UUID] = set()
    while current is not None:
        if current == place_id:
            return True
        if current in seen:
            break
        seen.add(current)
        row = await db.scalar(select(Noiseplace).where(Noiseplace.id == current))
        if row is None:
            break
        current = row.parent_place_id
    return False

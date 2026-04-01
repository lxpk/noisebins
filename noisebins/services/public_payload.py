"""Public-safe serializers for anonymous read (DEVELOPMENT.md / README threat model)."""

from __future__ import annotations

from noisebins import models


def bin_public_dict(b: models.Noisebin, *, mask_pii: bool = True) -> dict:
    data = {
        "noisecode": b.noisecode,
        "title": b.title,
        "description": b.description,
        "details": b.details,
        "contents_text": b.contents_text,
        "group_maintainer": b.group_maintainer,
        "maintainer_name": b.maintainer_name,
        "intent": b.intent,
        "limbo_after": b.limbo_after.isoformat() if b.limbo_after else None,
        "status": b.status,
        "shelf_hint": b.shelf_hint,
        "noiseplace_id": str(b.noiseplace_id) if b.noiseplace_id else None,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        "photos": [{"sort_order": p.sort_order} for p in sorted(b.photos, key=lambda x: x.sort_order)],
    }
    if mask_pii:
        data["maintainer_email"] = None
        data["maintainer_phone"] = None
        data["maintainer_discord"] = None
    else:
        data["maintainer_email"] = b.maintainer_email
        data["maintainer_phone"] = b.maintainer_phone
        data["maintainer_discord"] = b.maintainer_discord
    return data


def place_public_dict(p: models.Noiseplace) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "photo_ref": p.photo_ref,
        "parent_place_id": str(p.parent_place_id) if p.parent_place_id else None,
        "maintainer_name": p.maintainer_name,
        "group_maintainer": p.group_maintainer,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }

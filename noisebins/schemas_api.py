from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PlaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    photo_ref: str | None = None
    parent_place_id: uuid.UUID | None = None
    maintainer_name: str | None = None
    maintainer_email: str | None = None
    group_maintainer: str | None = None


class PlaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    photo_ref: str | None = None
    parent_place_id: uuid.UUID | None = None
    maintainer_name: str | None = None
    maintainer_email: str | None = None
    group_maintainer: str | None = None


class PlaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    photo_ref: str | None
    parent_place_id: uuid.UUID | None
    maintainer_name: str | None
    group_maintainer: str | None
    created_at: datetime
    updated_at: datetime


class BinCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    details: str | None = None
    contents_text: str | None = None
    noiseplace_id: uuid.UUID | None = None
    intent: str | None = None
    limbo_after: date | None = None
    status: str = "active"
    shelf_hint: str | None = None
    maintainer_name: str | None = None
    maintainer_email: str | None = None
    maintainer_phone: str | None = None
    maintainer_discord: str | None = None
    group_maintainer: str | None = None


class BinUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    details: str | None = None
    contents_text: str | None = None
    noiseplace_id: uuid.UUID | None = None
    intent: str | None = None
    limbo_after: date | None = None
    status: str | None = None
    shelf_hint: str | None = None
    maintainer_name: str | None = None
    maintainer_email: str | None = None
    maintainer_phone: str | None = None
    maintainer_discord: str | None = None
    group_maintainer: str | None = None


class BinReadMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    noisecode: str
    title: str
    description: str | None
    details: str | None
    contents_text: str | None
    noiseplace_id: uuid.UUID | None
    intent: str | None
    limbo_after: date | None = None
    status: str
    shelf_hint: str | None
    maintainer_name: str | None
    maintainer_email: str | None
    maintainer_phone: str | None
    maintainer_discord: str | None
    group_maintainer: str | None
    public_url: str = ""
    claimed_by_user_id: uuid.UUID | None = None
    claimed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class NoisethingCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    barcode: str | None = None


class NoisethingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_bin_id: uuid.UUID
    name: str
    description: str | None
    barcode: str | None
    photo_blob_key: str | None
    created_at: datetime


class ClaimBody(BaseModel):
    pass


class TransferBody(BaseModel):
    to_user_email: str = Field(..., min_length=3, max_length=320)


class SuggestContentsBody(BaseModel):
    image_base64: str | None = None


class NoiseportCallback(BaseModel):
    code: str
    state: str | None = None

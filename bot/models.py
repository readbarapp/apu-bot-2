from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from bot.catalogs import STORE_BY_ID

PickupWindow = Literal["1d", "2d", "3d"]
WorkerStatus = Literal[
    "idle",
    "needs_login",
    "logging_in",
    "ready",
    "launching",
    "watching",
    "checking_out",
    "dry_run_paused",
    "completed",
    "stopped",
    "browser_closed",
    "error",
]


class WorkerProfile(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=64)
    session_dir: str = Field(min_length=1, max_length=512)
    sku: str = Field(min_length=3, max_length=64)
    stores: list[str] = Field(min_length=1)
    pickup_window: PickupWindow
    max_qty: int = Field(ge=1, le=99)

    @field_validator("name", "session_dir", "sku")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned

    @field_validator("stores")
    @classmethod
    def unique_known_stores(cls, value: list[str]) -> list[str]:
        stores: list[str] = []
        seen: set[str] = set()
        for store_id in value:
            store_id = store_id.strip()
            if store_id not in STORE_BY_ID:
                raise ValueError(f"unknown Apple Store: {store_id}")
            if store_id not in seen:
                stores.append(store_id)
                seen.add(store_id)
        if not stores:
            raise ValueError("select at least one Hong Kong Apple Store")
        return stores


class WorkerActionRequest(BaseModel):
    test_mode: bool = True
    worker: WorkerProfile


class StartRequest(BaseModel):
    test_mode: bool = True
    workers: list[WorkerProfile] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_workers(self) -> "StartRequest":
        ids = [worker.id for worker in self.workers]
        sessions = [worker.session_dir for worker in self.workers]
        if len(set(ids)) != len(ids):
            raise ValueError("worker id must be unique")
        if len(set(sessions)) != len(sessions):
            raise ValueError("each worker needs its own Apple ID session folder")
        return self


class WorkerPublicState(BaseModel):
    id: str
    name: str
    session_dir: str
    sku: str
    stores: list[str]
    pickup_window: PickupWindow
    max_qty: int
    purchased: int = 0
    status: WorkerStatus = "needs_login"
    last_message: str = ""
    apple_id: str | None = None
    logged_in: bool = False
    sniping: bool = False
    browser_open: bool = False


class StatusResponse(BaseModel):
    running: bool
    test_mode: bool
    workers: list[WorkerPublicState]

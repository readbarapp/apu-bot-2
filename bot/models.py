from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from bot.catalogs import STORE_BY_ID

PickupWindow = Literal["1d", "2d", "3d"]
CheckoutMode = Literal["apple_id", "guest"]
Fulfillment = Literal["pickup", "delivery"]
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
    "paused",
    "browser_closed",
    "error",
]

GUEST_FIELD_LABELS = {
    "last_name": "英文姓氏",
    "first_name": "英文名字",
    "email": "電郵地址",
    "phone": "香港聯絡電話",
    "address": "送貨地址",
    "card_number": "信用卡號碼",
    "card_month": "有效月份",
    "card_year": "有效年份",
    "cvv": "CVV 安全碼",
}


class GuestProfile(BaseModel):
    last_name: str = ""
    first_name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    card_number: str = ""
    card_month: str = ""
    card_year: str = ""
    cvv: str = ""

    @field_validator(*GUEST_FIELD_LABELS)
    @classmethod
    def strip_guest(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("card_number")
    @classmethod
    def sixteen_digit_card(cls, value: str) -> str:
        if not value or "•" in value:
            return value
        digits = re.sub(r"\D", "", value)
        if digits and len(digits) != 16:
            raise ValueError("信用卡號碼必須係 16 個數字")
        return digits

    @field_validator("cvv")
    @classmethod
    def cvv_digits(cls, value: str) -> str:
        if not value:
            return value
        digits = re.sub(r"\D", "", value)
        if len(digits) not in {3, 4}:
            raise ValueError("CVV 必須係 3 或 4 個數字")
        return digits

    def missing_labels(self) -> list[str]:
        missing: list[str] = []
        for key, label in GUEST_FIELD_LABELS.items():
            if not getattr(self, key):
                missing.append(label)
        return missing


class WorkerProfile(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=64)
    session_dir: str = Field(default="", max_length=512)
    sku: str = Field(min_length=3, max_length=64)
    stores: list[str] = Field(default_factory=list)
    pickup_window: PickupWindow = "1d"
    max_qty: int = Field(ge=1, le=99)
    checkout_mode: CheckoutMode = "apple_id"
    fulfillment: Fulfillment = "pickup"
    delivery_max_days: int = Field(default=7, ge=1, le=30)
    guest: GuestProfile = Field(default_factory=GuestProfile)

    @field_validator("name", "sku", "session_dir")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("stores")
    @classmethod
    def unique_known_stores(cls, value: list[str]) -> list[str]:
        stores: list[str] = []
        seen: set[str] = set()
        for store_id in value:
            store_id = store_id.strip()
            if not store_id:
                continue
            if store_id not in STORE_BY_ID:
                raise ValueError(f"unknown Apple Store: {store_id}")
            if store_id not in seen:
                stores.append(store_id)
                seen.add(store_id)
        return stores

    @model_validator(mode="after")
    def validate_modes(self) -> "WorkerProfile":
        if self.checkout_mode == "apple_id":
            if not self.session_dir:
                raise ValueError("Apple ID 模式必須指定 Session 資料夾路徑")
        else:
            if not self.session_dir:
                self.session_dir = f"session_guest_{self.id}"
            card = self.guest.card_number or ""
            masked_card = "•" in card
            missing = []
            for key, label in GUEST_FIELD_LABELS.items():
                value = getattr(self.guest, key) or ""
                if key == "card_number":
                    if not value:
                        missing.append(label)
                    continue
                if key == "cvv":
                    # Blank CVV is OK when the PAN is masked; hydrate fills it from secrets.
                    if not value and not masked_card:
                        missing.append(label)
                    continue
                if not value:
                    missing.append(label)
            if missing:
                raise ValueError(f"訪客模式請填妥：{'、'.join(missing)}")
        if self.fulfillment == "pickup" and not self.stores:
            raise ValueError("門市自取必須至少揀一間香港 Apple Store")
        return self


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
    checkout_mode: CheckoutMode = "apple_id"
    fulfillment: Fulfillment = "pickup"
    delivery_max_days: int = 7
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

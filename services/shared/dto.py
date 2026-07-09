"""Pydantic response DTOs for the B2 reads slice (B2-READS-PLAN.md §8).

All models are camelCase on the wire (FastAPI serializes response_models
by alias by default) while accepting snake_case field names in Python —
that's what lets mappers.py build these directly from snake_case SQL rows.

Refs (`licenseRef`/`masterLicenseRef`) appear ONLY on License/MasterLicense
DTOs, per Decision C — matches what `db/schema.sql` actually has ref columns
for. Don't add ref fields to any other DTO.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from services.shared.schemas import PageInfo


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LicenseeSummary(CamelModel):
    id: int
    name: str
    entity_type: str


class Licensee(LicenseeSummary):
    industry: str | None = None
    country: str | None = None
    region: str | None = None
    external_ref: str | None = None
    created_at: datetime


class MasterLicenseSummary(CamelModel):
    id: int
    master_license_ref: str
    label: str | None = None


class Administrator(CamelModel):
    id: int
    master_license_id: int
    user_id: int
    user_email: str
    renewal_notifications: bool
    added_date: date


class UnallocatedProduct(CamelModel):
    license_product_id: int
    product_code: str
    product_name: str
    seat_count: int
    business_offering_id: int | None = None


class LicenseSummary(CamelModel):
    id: int
    license_ref: str
    status: str
    expiry_date: date
    days_until_expiry: int
    product_count: int


class MasterLicense(MasterLicenseSummary):
    entity_id: int
    program: str | None = None
    sponsor: str | None = None
    created_at: datetime
    # Optional sub-objects, populated per `?include=` (L4 only):
    licenses: list[LicenseSummary] | None = None
    administrators: list[Administrator] | None = None
    licensee: LicenseeSummary | None = None
    unallocated_products: list[UnallocatedProduct] | None = None


class LicensedProduct(CamelModel):
    license_product_id: int
    product_code: str
    product_name: str
    is_suite: bool
    seat_count: int
    seats_active: int
    business_offering_id: int | None = None
    entitlement_count: int


class License(LicenseSummary):
    start_date: date
    master: MasterLicenseSummary
    licensee: LicenseeSummary
    products: list[LicensedProduct]
    end_user_count: int


class MasterLicenseGroup(CamelModel):
    id: int
    master_license_ref: str
    label: str | None = None
    licenses: list[LicenseSummary]


class LicensesByEntityResponse(CamelModel):
    licensee_id: int
    licensee_name: str
    master_licenses: list[MasterLicenseGroup]
    total_licenses: int


class UserContext(CamelModel):
    id: int
    email: str
    first_name: str
    last_name: str
    entity_id: int
    entity_name: str


class Policy(CamelModel):
    id: int
    entitlement_id: int
    policy_name: str | None = None
    quantity: int | None = None
    max_activations: int
    activation_ttl_days: int
    allow_offline: bool
    reactivation_limit: int


class StaleActivation(CamelModel):
    id: int
    machine_id: str
    machine_name: str | None = None
    last_heartbeat: datetime
    days_since_heartbeat: int
    status: str


class EntitlementSummary(CamelModel):
    id: int
    license_id: int
    license_ref: str
    master_license_id: int
    master_license_ref: str
    license_product_id: int
    product_code: str
    product_name: str
    entitlement_type: str
    activation_type: str
    status: str


class Entitlement(EntitlementSummary):
    assignment_role: str | None = None
    assigned_date: date | None = None
    policy: Policy | None = None
    stale_activations: list[StaleActivation] = []


class UserEntitlementsResponse(CamelModel):
    user: UserContext
    items: list[Entitlement]
    page_info: PageInfo

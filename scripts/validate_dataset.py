#!/usr/bin/env python3
"""
A4 — validate the generated + planted dataset (db/schema.sql).

Three checks:
  1. Row counts per table.
  2. FK integrity — every declared FK in schema.sql, checked for orphans
     (expect 0 for all).
  3. One spot-check per B2 endpoint, run against the planted demo record
     (Acme Corp / L-DEMOACME / jane.doe@acmecorp.com) — calling the SAME
     query functions the services use, so this validates the real code
     path, not a hand-rolled duplicate.

Usage (needs the demo planted first — see scripts/generate_bulk.py --plant-demo):
    LICENSING_PG_URL=postgresql://licensing:licensing@localhost:5433/licensing \
        .venv/bin/python scripts/validate_dataset.py
"""

from __future__ import annotations

import argparse
import os
import sys

# Run as a plain script (`python scripts/validate_dataset.py`), not `-m` — Python
# puts scripts/ on sys.path, not the repo root, so `import services` needs help.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402
import sqlalchemy as sa  # noqa: E402

TABLES = [
    "product",
    "product_suite_component",
    "entity",
    "app_user",
    "master_license",
    "license",
    "license_product",
    "entitlement",
    "policy",
    "entitlement_person",
    "activation",
    "license_end_user",
    "master_license_admin",
]

# Every FK declared in db/schema.sql (21, per db/SCHEMA.md) — orphan count must be 0.
FK_CHECKS = {
    "app_user -> entity": "SELECT count(*) FROM app_user c LEFT JOIN entity p ON c.entity_id=p.id WHERE p.id IS NULL",
    "master_license -> entity": "SELECT count(*) FROM master_license c LEFT JOIN entity p ON c.entity_id=p.id WHERE p.id IS NULL",
    "license -> master_license": "SELECT count(*) FROM license c LEFT JOIN master_license p ON c.master_license_id=p.id WHERE p.id IS NULL",
    "license_product -> master_license": "SELECT count(*) FROM license_product c LEFT JOIN master_license p ON c.master_license_id=p.id WHERE p.id IS NULL",
    "license_product -> license (nullable)": "SELECT count(*) FROM license_product c LEFT JOIN license p ON c.license_id=p.id WHERE c.license_id IS NOT NULL AND p.id IS NULL",
    "license_product -> product": "SELECT count(*) FROM license_product c LEFT JOIN product p ON c.product_id=p.id WHERE p.id IS NULL",
    "entitlement -> license": "SELECT count(*) FROM entitlement c LEFT JOIN license p ON c.license_id=p.id WHERE p.id IS NULL",
    "entitlement -> master_license": "SELECT count(*) FROM entitlement c LEFT JOIN master_license p ON c.master_license_id=p.id WHERE p.id IS NULL",
    "entitlement -> license_product": "SELECT count(*) FROM entitlement c LEFT JOIN license_product p ON c.license_product_id=p.id WHERE p.id IS NULL",
    "entitlement -> product": "SELECT count(*) FROM entitlement c LEFT JOIN product p ON c.product_id=p.id WHERE p.id IS NULL",
    "policy -> entitlement": "SELECT count(*) FROM policy c LEFT JOIN entitlement p ON c.entitlement_id=p.id WHERE p.id IS NULL",
    "policy 1:1 coverage (entitlements w/o policy)": "SELECT count(*) FROM entitlement e LEFT JOIN policy p ON p.entitlement_id=e.id WHERE p.id IS NULL",
    "entitlement_person -> entitlement": "SELECT count(*) FROM entitlement_person c LEFT JOIN entitlement p ON c.entitlement_id=p.id WHERE p.id IS NULL",
    "entitlement_person -> app_user": "SELECT count(*) FROM entitlement_person c LEFT JOIN app_user p ON c.user_id=p.id WHERE p.id IS NULL",
    "activation -> entitlement": "SELECT count(*) FROM activation c LEFT JOIN entitlement p ON c.entitlement_id=p.id WHERE p.id IS NULL",
    "activation -> app_user": "SELECT count(*) FROM activation c LEFT JOIN app_user p ON c.user_id=p.id WHERE p.id IS NULL",
    "license_end_user -> license": "SELECT count(*) FROM license_end_user c LEFT JOIN license p ON c.license_id=p.id WHERE p.id IS NULL",
    "license_end_user -> app_user": "SELECT count(*) FROM license_end_user c LEFT JOIN app_user p ON c.user_id=p.id WHERE p.id IS NULL",
    "master_license_admin -> master_license": "SELECT count(*) FROM master_license_admin c LEFT JOIN master_license p ON c.master_license_id=p.id WHERE p.id IS NULL",
    "master_license_admin -> app_user": "SELECT count(*) FROM master_license_admin c LEFT JOIN app_user p ON c.user_id=p.id WHERE p.id IS NULL",
    "product_suite_component -> product (suite)": "SELECT count(*) FROM product_suite_component c LEFT JOIN product p ON c.suite_product_id=p.id WHERE p.id IS NULL",
    "product_suite_component -> product (component)": "SELECT count(*) FROM product_suite_component c LEFT JOIN product p ON c.component_product_id=p.id WHERE p.id IS NULL",
}


def row_counts(conn) -> None:
    print("\n-- row counts --")
    for t in TABLES:
        n = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  {t:34} {n:>12,}")


def fk_integrity(conn) -> bool:
    print("\n-- FK integrity (expect 0) --")
    ok = True
    for name, q in FK_CHECKS.items():
        n = conn.execute(q).fetchone()[0]
        if n != 0:
            ok = False
        print(f"  [{'OK' if n == 0 else 'FAIL'}] {name:45} {n}")
    return ok


def endpoint_spot_checks() -> bool:
    print("\n-- endpoint spot-checks (planted demo record) --")
    from services.entitlement import queries as eq
    from services.activation import queries as aq
    from services.licensing import queries as lq
    from services.shared.db import SessionLocal
    from services.shared.schemas import PageParams

    page = PageParams(page=0, size=100)
    results: list[tuple[str, bool]] = []

    with SessionLocal() as session:
        entity_row = session.execute(sa.text("SELECT id FROM entity WHERE name = 'Acme Corp'")).mappings().first()
        if entity_row is None:
            print("  [FAIL] planted demo not found — run generate_bulk.py --reset --plant-demo first")
            return False
        entity_id = entity_row["id"]

        license_row = session.execute(
            sa.text("SELECT id FROM license WHERE license_ref = 'L-DEMOACME'")
        ).mappings().first()
        license_id = license_row["id"]

        ml_row = session.execute(
            sa.text("SELECT id FROM master_license WHERE master_license_ref = 'ML-DEMOACME'")
        ).mappings().first()
        ml_id = ml_row["id"]

        r = lq.get_licensee(session, entity_id)
        results.append(("L2 get_licensee", r is not None and r["name"] == "Acme Corp"))

        _, total = lq.list_licenses_by_entity(session, entity_id, page)
        results.append(("L3 list_licenses_by_entity", total == 1))

        r = lq.get_master_license_summary(session, ml_id)
        results.append(("L4 get_master_license_summary", r is not None and r["master_license_ref"] == "ML-DEMOACME"))

        _, total = lq.list_licenses_by_master(session, ml_id, page)
        results.append(("L5 list_licenses_by_master", total == 1))

        admins = lq.list_master_administrators(session, ml_id)
        results.append(("L6 list_master_administrators", len(admins) == 1))

        resolved_ml = lq.get_master_license_id_for_license(session, license_id)
        results.append(("L6b get_master_license_id_for_license", resolved_ml == ml_id))

        core = lq.get_license_core(session, license_id)
        products = lq.get_license_products_all(session, license_id)
        end_user_count = lq.get_end_user_count(session, license_id)
        results.append(("L7 get_license_status pieces", core is not None and len(products) == 2 and end_user_count == 10))

        _, ptotal = lq.get_license_products_page(session, license_id, page)
        results.append(("L8 get_license_products_page", ptotal == 2))

        user_row = eq.get_user_context(session, "jane.doe@acmecorp.com")
        results.append(("E1 get_user_context", user_row is not None and user_row["entity_name"] == "Acme Corp"))

        erows, etotal = eq.list_user_entitlements(session, user_row["id"], None, page)
        results.append(("E1 list_user_entitlements", etotal == 1))

        _, etotal2 = eq.list_entitlements(
            session, license_id=license_id, master_license_id=None, license_product_id=None, status=None, page=page
        )
        results.append(("E2 list_entitlements", etotal2 == 2))

        _, atotal = aq.list_stale_activations(session, erows[0]["id"], 30, page)
        results.append(("Activation list_stale_activations (via E1)", atotal == 1))

    ok = True
    for name, passed in results:
        if not passed:
            ok = False
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("LICENSING_PG_URL"))
    args = ap.parse_args()
    if not args.url:
        ap.error("set --url or LICENSING_PG_URL")
    os.environ["LICENSING_PG_URL"] = args.url
    os.environ.setdefault("SERVICE_NAME", "VALIDATE")

    ok = True
    with psycopg.connect(args.url, autocommit=True) as conn:
        row_counts(conn)
        ok = fk_integrity(conn) and ok

    ok = endpoint_spot_checks() and ok

    print("\n== RESULT:", "PASS" if ok else "FAIL", "==")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

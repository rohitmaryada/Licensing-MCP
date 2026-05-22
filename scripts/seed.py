"""
Hybrid seeder: AWS SaaS Sales CSV → entities, Faker → everything else.

Targets:
  ~500 entities, ~1 000 licenses, ~5 000 users, ~8 000 entitlements,
  ~50 CS users, ~2 000 audit records
"""

import json
import os
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))
from licensing_mcp.models import (
    Activation, Base, CSAuditLog, CSPermission, CSRole, CSRoleMember,
    CSUser, Entity, EntityType, Entitlement, Installation, License,
    LicenseAdmin, LicenseProduct, LicenseType, LicenseUser, Product, User,
    create_all, get_engine,
)

fake = Faker()
Faker.seed(42)
random.seed(42)

RAW_CSV = Path("data/raw/SaaS-Sales.csv")
DB_PATH = "data/licensing.db"

# ── MathWorks product catalog ────────────────────────────────────────────────

PRODUCTS = [
    ("MATLAB",                              "ML",   "Core",          4500),
    ("Simulink",                            "SL",   "Core",          3800),
    ("Statistics and Machine Learning Toolbox", "SMLT", "Analytics", 1200),
    ("Signal Processing Toolbox",           "SPT",  "DSP",           1100),
    ("Image Processing Toolbox",            "IPT",  "Vision",        1100),
    ("Control System Toolbox",              "CST",  "Control",       1000),
    ("Optimization Toolbox",                "OPT",  "Math",          1050),
    ("Parallel Computing Toolbox",          "PCT",  "HPC",           1400),
    ("Deep Learning Toolbox",               "DLT",  "AI",            1500),
    ("Computer Vision Toolbox",             "CVT",  "Vision",        1300),
    ("Financial Toolbox",                   "FT",   "Finance",       1600),
    ("Mapping Toolbox",                     "MAP",  "GIS",           900),
    ("MATLAB Compiler",                     "MCC",  "Deployment",    2000),
    ("MATLAB Coder",                        "MCO",  "Deployment",    1800),
    ("Simulink Coder",                      "SCO",  "Deployment",    1900),
    ("Aerospace Toolbox",                   "AST",  "Engineering",   1100),
    ("Communications Toolbox",              "CMT",  "Wireless",      1200),
    ("Bioinformatics Toolbox",              "BIO",  "Life Sciences", 1000),
    ("Database Toolbox",                    "DBT",  "Data",          950),
    ("Symbolic Math Toolbox",               "SMT",  "Math",          950),
]

# Industry → toolboxes that make sense for that vertical
INDUSTRY_TOOLBOXES = {
    "Finance":          ["Financial Toolbox", "Statistics and Machine Learning Toolbox", "Optimization Toolbox", "Database Toolbox"],
    "Energy":           ["Optimization Toolbox", "Signal Processing Toolbox", "Control System Toolbox", "Parallel Computing Toolbox"],
    "Tech":             ["Deep Learning Toolbox", "Parallel Computing Toolbox", "Computer Vision Toolbox", "Statistics and Machine Learning Toolbox"],
    "Manufacturing":    ["Simulink", "Control System Toolbox", "Simulink Coder", "MATLAB Coder", "Aerospace Toolbox"],
    "Healthcare":       ["Statistics and Machine Learning Toolbox", "Bioinformatics Toolbox", "Image Processing Toolbox", "Deep Learning Toolbox"],
    "Consumer Products":["Statistics and Machine Learning Toolbox", "Optimization Toolbox", "Database Toolbox"],
    "Retail":           ["Statistics and Machine Learning Toolbox", "Optimization Toolbox", "Database Toolbox"],
    "Communications":   ["Signal Processing Toolbox", "Communications Toolbox", "Parallel Computing Toolbox"],
    "Transportation":   ["Mapping Toolbox", "Optimization Toolbox", "Control System Toolbox", "Aerospace Toolbox"],
    "Misc":             ["Statistics and Machine Learning Toolbox", "Database Toolbox"],
    "Government":       ["Mapping Toolbox", "Optimization Toolbox", "Signal Processing Toolbox"],
    "Academic":         ["Statistics and Machine Learning Toolbox", "Symbolic Math Toolbox", "Signal Processing Toolbox", "Bioinformatics Toolbox"],
}

# CS write tools gated by role
CS_PERMISSIONS = {
    "CS-L1": ["add_user_to_license", "revoke_activation"],
    "CS-L2": ["add_user_to_license", "revoke_activation", "reset_installation_slot", "update_seat_count"],
    "CS-L3": ["add_user_to_license", "revoke_activation", "reset_installation_slot", "update_seat_count",
               "extend_license_expiry", "transfer_license_admin"],
}

AUDIT_REASONS = {
    "revoke_activation": [
        "User reported inability to activate {product} on new machine. Confirmed entitlement on license {license}. "
        "Seat count ({seats}) at capacity. Found stale activation on decommissioned machine (last heartbeat {days} days ago). "
        "Revoking to free a seat.",
        "Customer replaced laptop. Old machine activation unused for {days} days. Freeing seat for new device activation.",
        "IT decommissioned machine {machine}. Revoking activation to reclaim seat under license {license}.",
    ],
    "add_user_to_license": [
        "New hire {user} joining {entity} team. Adding to license {license} per manager request.",
        "User transferred from a subsidiary. Maintaining access to {product} under consolidated enterprise license {license}.",
        "Academic license expansion: adding research assistant to {license} for thesis project requiring {product}.",
    ],
    "reset_installation_slot": [
        "User received a new machine after hardware failure. Clearing slot on license {license} to allow reinstall of {product}.",
        "OS reinstall required. Resetting installation record so user can re-activate {product} on the same machine.",
    ],
    "update_seat_count": [
        "Customer {entity} purchased {delta} additional seats per order #{order}. Updating license {license} from {old} to {new} seats.",
        "Seat reduction requested after team downsizing. Reducing license {license} from {old} to {new} seats per account team approval.",
    ],
    "extend_license_expiry": [
        "Renewal PO delayed in procurement. Granting {days}-day extension on license {license} to avoid service interruption.",
        "Customer requested extension to evaluate expanded toolbox suite before committing to renewal.",
    ],
    "transfer_license_admin": [
        "Previous admin {old_admin} left {entity}. Transferring license {license} administration to {new_admin} per IT request.",
        "Organizational restructure. Reassigning license admin from departed employee to current IT contact.",
    ],
    "get_audit_history": [
        "CS rep reviewing change history for license {license} during support call.",
    ],
}


def _rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def _domain_from_name(name: str) -> str:
    clean = name.lower().replace(" ", "").replace(",", "").replace(".", "").replace("'", "")
    return f"{clean[:20]}.com"


# ── 1. Static reference data ─────────────────────────────────────────────────

def seed_reference(session: Session):
    entity_types = [
        EntityType(id=1, name="enterprise",  description="Large commercial organizations"),
        EntityType(id=2, name="academic",    description="Universities and research institutions"),
        EntityType(id=3, name="individual",  description="Individual license holders"),
        EntityType(id=4, name="government",  description="Government and defense agencies"),
    ]
    license_types = [
        LicenseType(id=1, name="enterprise",   description="Named-user enterprise license"),
        LicenseType(id=2, name="academic",     description="Academic institution license"),
        LicenseType(id=3, name="individual",   description="Single-user individual license"),
        LicenseType(id=4, name="concurrent",   description="Concurrent/floating seat license"),
        LicenseType(id=5, name="trial",        description="Time-limited trial license"),
    ]
    products = [
        Product(id=i+1, name=name, product_code=code, category=cat, base_price=price)
        for i, (name, code, cat, price) in enumerate(PRODUCTS)
    ]
    cs_roles = [
        CSRole(id=1, name="CS-L1", description="Tier-1: user management and basic activation fixes", level=1),
        CSRole(id=2, name="CS-L2", description="Tier-2: installation management and seat adjustments", level=2),
        CSRole(id=3, name="CS-L3", description="Tier-3: contract-level changes", level=3),
    ]
    role_by_name = {r.name: r for r in cs_roles}
    permissions = [
        CSPermission(role_id=role_by_name[role].id, tool_name=tool)
        for role, tools in CS_PERMISSIONS.items()
        for tool in tools
    ]
    session.add_all(entity_types + license_types + products + cs_roles + permissions)
    session.flush()
    return {et.name: et for et in entity_types}, {lt.name: lt for lt in license_types}, \
           {p.name: p for p in products}, {r.name: r for r in cs_roles}


# ── 2. Entities ──────────────────────────────────────────────────────────────

# Map AWS SaaS segment → entity type
SEGMENT_TO_ETYPE = {"Enterprise": "enterprise", "Strategic": "enterprise", "SMB": "individual"}
INDUSTRY_TO_ETYPE = {
    "Finance": "enterprise", "Energy": "enterprise", "Tech": "enterprise",
    "Manufacturing": "enterprise", "Healthcare": "enterprise",
    "Consumer Products": "enterprise", "Retail": "enterprise",
    "Communications": "enterprise", "Transportation": "enterprise", "Misc": "individual",
}

def seed_entities(session: Session, entity_types: dict) -> list[Entity]:
    df = pd.read_csv(RAW_CSV)
    companies = df[["Customer", "Customer ID", "Industry", "Segment", "Country", "Region"]].drop_duplicates("Customer ID")

    entities = []
    for _, row in companies.iterrows():
        segment = row["Segment"]
        industry = row["Industry"]
        # Prefer segment-based mapping, fall back to industry
        etype_name = SEGMENT_TO_ETYPE.get(segment, INDUSTRY_TO_ETYPE.get(industry, "enterprise"))
        entities.append(Entity(
            name=row["Customer"],
            entity_type_id=entity_types[etype_name].id,
            industry=industry,
            country=row["Country"],
            region=row["Region"],
            external_ref=str(int(row["Customer ID"])),
        ))

    # Pad to ~500 with Faker-generated entities
    faker_industries = list(INDUSTRY_TO_ETYPE.keys()) + ["Government", "Defense", "Education"]
    faker_etypes = ["enterprise", "academic", "individual", "government"]
    countries = ["United States", "United Kingdom", "Germany", "France", "Canada",
                 "Australia", "Japan", "India", "Brazil", "Netherlands"]

    while len(entities) < 500:
        etype = random.choice(faker_etypes)
        if etype == "academic":
            name = f"{fake.city()} University"
            industry = "Academic"
        elif etype == "government":
            name = f"{fake.country()} {random.choice(['Department of Defense', 'Space Agency', 'Research Institute', 'National Laboratory'])}"
            industry = "Government"
        elif etype == "individual":
            name = fake.name()
            industry = random.choice(faker_industries)
        else:
            name = fake.company()
            industry = random.choice(faker_industries)
        entities.append(Entity(
            name=name,
            entity_type_id=entity_types[etype].id,
            industry=industry,
            country=random.choice(countries),
            region=fake.state(),
        ))

    session.add_all(entities)
    session.flush()
    return entities


# ── 3. Licenses ──────────────────────────────────────────────────────────────

ETYPE_TO_LTYPE = {
    "enterprise": ["enterprise", "concurrent"],
    "academic":   ["academic", "concurrent"],
    "individual": ["individual", "trial"],
    "government": ["enterprise", "concurrent"],
}

LTYPE_SEATS = {
    "enterprise":  (20, 100),
    "academic":    (10, 50),
    "individual":  (1, 1),
    "concurrent":  (5, 30),
    "trial":       (2, 5),
}

def seed_licenses(session: Session, entities: list[Entity], license_types: dict) -> list[License]:
    today = date.today()
    licenses = []
    license_counter = 10001

    for entity in entities:
        etype_name = {1: "enterprise", 2: "academic", 3: "individual", 4: "government"}[entity.entity_type_id]
        # 1-3 licenses per entity (enterprise/academic get more)
        n = random.choices([1, 2, 3], weights=[0.3, 0.5, 0.2])[0]
        if etype_name == "individual":
            n = 1

        for _ in range(n):
            lt_name = random.choice(ETYPE_TO_LTYPE[etype_name])
            lt = license_types[lt_name]
            seat_min, seat_max = LTYPE_SEATS[lt_name]
            seats = random.randint(seat_min, seat_max)

            start = _rand_date(date(2020, 1, 1), today - timedelta(days=30))
            # 85% active (expire in future), 10% expired, 5% trial
            r = random.random()
            if lt_name == "trial":
                expiry = start + timedelta(days=random.randint(30, 90))
                status = "trial" if expiry >= today else "expired"
            elif r < 0.10:
                exp_start = start + timedelta(days=90)
                exp_end = today - timedelta(days=1)
                if exp_start >= exp_end:
                    exp_start = start + timedelta(days=30)
                expiry = _rand_date(exp_start, max(exp_start, exp_end))
                status = "expired"
            else:
                expiry = _rand_date(today + timedelta(days=30), today + timedelta(days=730))
                status = "active"

            licenses.append(License(
                id=f"L-{license_counter}",
                entity_id=entity.id,
                license_type_id=lt.id,
                status=status,
                seat_count=seats,
                start_date=start,
                expiry_date=expiry,
            ))
            license_counter += 1

    session.add_all(licenses)
    session.flush()
    return licenses


# ── 4. License products ──────────────────────────────────────────────────────

def seed_license_products(session: Session, licenses: list[License], entities: list[Entity],
                           products: dict) -> dict[str, list[Product]]:
    entity_by_id = {e.id: e for e in entities}
    matlab = products["MATLAB"]
    simulink = products["Simulink"]
    lp_rows = []
    license_product_map: dict[str, list[Product]] = {}

    for lic in licenses:
        entity = entity_by_id[lic.entity_id]
        industry = entity.industry or "Misc"
        toolbox_names = INDUSTRY_TOOLBOXES.get(industry, INDUSTRY_TOOLBOXES["Misc"])

        # Always include MATLAB; enterprise/concurrent also often include Simulink
        chosen = [matlab]
        if lic.license_type_id in (1, 2, 4) and random.random() < 0.6:  # enterprise/academic/concurrent
            chosen.append(simulink)

        # Add 2-6 industry-relevant toolboxes
        available = [products[n] for n in toolbox_names if n in products and products[n] not in chosen]
        n_extra = random.randint(2, min(6, len(available)))
        chosen += random.sample(available, n_extra)

        license_product_map[lic.id] = chosen
        seen = set()
        for p in chosen:
            key = (lic.id, p.id)
            if key not in seen:
                seen.add(key)
                lp_rows.append(LicenseProduct(license_id=lic.id, product_id=p.id))

    session.add_all(lp_rows)
    session.flush()
    return license_product_map


# ── 5. Users ─────────────────────────────────────────────────────────────────

def seed_users(session: Session, entities: list[Entity]) -> dict[int, list[User]]:
    users_by_entity: dict[int, list[User]] = {}
    all_users = []
    seen_emails = set()

    for entity in entities:
        etype_name = {1: "enterprise", 2: "academic", 3: "individual", 4: "government"}[entity.entity_type_id]
        n = {"enterprise": random.randint(8, 20), "academic": random.randint(5, 15),
             "individual": 1, "government": random.randint(5, 12)}[etype_name]

        domain = _domain_from_name(entity.name)
        entity_users = []
        for _ in range(n):
            first = fake.first_name()
            last = fake.last_name()
            base_email = f"{first.lower()}.{last.lower()}@{domain}"
            email = base_email
            suffix = 1
            while email in seen_emails:
                email = f"{first.lower()}.{last.lower()}{suffix}@{domain}"
                suffix += 1
            seen_emails.add(email)
            u = User(email=email, first_name=first, last_name=last, entity_id=entity.id)
            entity_users.append(u)
            all_users.append(u)

        users_by_entity[entity.id] = entity_users

    session.add_all(all_users)
    session.flush()
    return users_by_entity


# ── 6. License membership + admins ──────────────────────────────────────────

def seed_license_memberships(session: Session, licenses: list[License],
                              users_by_entity: dict[int, list[User]]) -> dict[str, list[User]]:
    lu_rows, la_rows = [], []
    license_members: dict[str, list[User]] = {}
    today = date.today()

    for lic in licenses:
        entity_users = users_by_entity.get(lic.entity_id, [])
        if not entity_users:
            license_members[lic.id] = []
            continue

        # Fill seats to 60-95% capacity (leave headroom, except for special demo case)
        max_members = min(lic.seat_count, len(entity_users))
        n_members = max(1, int(max_members * random.uniform(0.6, 0.95)))
        members = random.sample(entity_users, n_members)

        for user in members:
            added = _rand_date(lic.start_date, today)
            lu_rows.append(LicenseUser(license_id=lic.id, user_id=user.id, added_date=added))

        # 1-2 admins from the member list
        n_admins = min(2, len(members))
        for admin in random.sample(members, n_admins):
            la_rows.append(LicenseAdmin(license_id=lic.id, user_id=admin.id, added_date=lic.start_date))

        license_members[lic.id] = members

    session.add_all(lu_rows)
    session.add_all(la_rows)
    session.flush()
    return license_members


# ── 7. Entitlements ──────────────────────────────────────────────────────────

def seed_entitlements(session: Session, licenses: list[License],
                       license_members: dict[str, list[User]],
                       license_product_map: dict[str, list[Product]]) -> list[Entitlement]:
    today = date.today()
    rows = []
    seen = set()
    for lic in licenses:
        members = license_members.get(lic.id, [])
        prods = license_product_map.get(lic.id, [])
        for user in members:
            for prod in prods:
                key = (user.id, lic.id, prod.id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(Entitlement(
                    user_id=user.id,
                    license_id=lic.id,
                    product_id=prod.id,
                    status="active" if lic.status in ("active", "trial") else "inactive",
                    granted_at=_rand_date(lic.start_date, today),
                ))
    session.add_all(rows)
    session.flush()
    return rows


# ── 8. Installations + Activations ──────────────────────────────────────────

OS_LIST = ["Windows 11", "Windows 10", "macOS 14", "macOS 13", "Ubuntu 22.04", "RHEL 9"]

def seed_activations(session: Session, licenses: list[License],
                      license_members: dict[str, list[User]],
                      license_product_map: dict[str, list[Product]]):
    today = date.today()
    inst_rows, act_rows = [], []
    machine_counter = 7000
    seen_act = set()

    for lic in licenses:
        if lic.status not in ("active", "trial"):
            continue
        members = license_members.get(lic.id, [])
        prods = license_product_map.get(lic.id, [])
        matlab_prod = next((p for p in prods if p.product_code == "ML"), None)
        if not matlab_prod or not members:
            continue

        # Each member activates MATLAB on 1-2 machines
        for user in members:
            n_machines = random.choices([1, 2], weights=[0.75, 0.25])[0]
            for m_idx in range(n_machines):
                machine_id = f"MAC-{machine_counter:06d}"
                machine_counter += 1
                os_name = random.choice(OS_LIST)
                install_dt = _rand_date(lic.start_date, today - timedelta(days=7))

                inst_rows.append(Installation(
                    user_id=user.id,
                    product_id=matlab_prod.id,
                    machine_id=machine_id,
                    machine_name=f"{user.first_name.lower()}-{os_name.split()[0].lower()}-{machine_counter % 1000:03d}",
                    os=os_name,
                    install_date=install_dt,
                ))

                # Primary machine (m_idx==0): recent heartbeat. Secondary: sometimes stale.
                stale = (m_idx == 1 and random.random() < 0.4)
                if stale:
                    hb_days_ago = random.randint(91, 365)
                else:
                    hb_days_ago = random.randint(0, 14)

                act_key = (user.id, matlab_prod.id, machine_id)
                if act_key not in seen_act:
                    seen_act.add(act_key)
                    act_rows.append(Activation(
                        user_id=user.id,
                        product_id=matlab_prod.id,
                        machine_id=machine_id,
                        license_id=lic.id,
                        activation_date=install_dt,
                        last_heartbeat=datetime.now() - timedelta(days=hb_days_ago),
                        status="inactive" if stale else "active",
                    ))

    session.add_all(inst_rows)
    session.add_all(act_rows)
    session.flush()


# ── 9. Demo scenario: Acme Corp at seat capacity ─────────────────────────────

def seed_demo_scenario(session: Session, products: dict, license_types: dict):
    """
    Creates a deterministic demo entity (Acme Corp) with a 10-seat Simulink license
    at full capacity, where one activation is stale — ready for the CS Action Agent demo.
    """
    acme = Entity(name="Acme Corp", entity_type_id=1, industry="Manufacturing",
                  country="United States", region="Massachusetts")
    session.add(acme)
    session.flush()

    lic = License(
        id="L-99001",
        entity_id=acme.id,
        license_type_id=license_types["enterprise"].id,
        status="active",
        seat_count=10,
        start_date=date(2024, 1, 1),
        expiry_date=date(2026, 12, 31),
    )
    session.add(lic)
    session.flush()

    matlab = products["MATLAB"]
    simulink = products["Simulink"]
    session.add(LicenseProduct(license_id=lic.id, product_id=matlab.id))
    session.add(LicenseProduct(license_id=lic.id, product_id=simulink.id))
    session.flush()

    # 10 users — fills the license to 10/10
    domain = "acmecorp.com"
    users = []
    for i in range(10):
        first = fake.first_name()
        last = fake.last_name()
        u = User(email=f"{first.lower()}.{last.lower()}@{domain}", first_name=first,
                 last_name=last, entity_id=acme.id)
        session.add(u)
        session.flush()
        users.append(u)
        session.add(LicenseUser(license_id=lic.id, user_id=u.id, added_date=date(2024, 1, 15)))
        for p in [matlab, simulink]:
            session.add(Entitlement(user_id=u.id, license_id=lic.id, product_id=p.id,
                                    status="active", granted_at=date(2024, 1, 15)))

    # The demo user: jane.doe@acme.com (user 0 gets this email overridden)
    jane = users[0]
    jane.email = "jane.doe@acmecorp.com"
    jane.first_name = "Jane"
    jane.last_name = "Doe"
    session.flush()

    # Jane has a stale activation on her old machine (94 days ago) and nothing on new machine
    stale_machine = "MAC-OLD-7291"
    session.add(Activation(
        user_id=jane.id,
        product_id=simulink.id,
        machine_id=stale_machine,
        license_id=lic.id,
        activation_date=date(2024, 3, 1),
        last_heartbeat=datetime.now() - timedelta(days=94),
        status="inactive",
    ))
    session.flush()

    # Admin
    session.add(LicenseAdmin(license_id=lic.id, user_id=users[1].id, added_date=date(2024, 1, 1)))
    session.flush()


# ── 10. CS users ─────────────────────────────────────────────────────────────

def seed_cs_users(session: Session, cs_roles: dict) -> list[CSUser]:
    cs_users = []
    role_assignments = []
    tier_counts = {"CS-L1": 25, "CS-L2": 15, "CS-L3": 10}

    for role_name, count in tier_counts.items():
        role = cs_roles[role_name]
        for _ in range(count):
            first = fake.first_name()
            last = fake.last_name()
            u = CSUser(
                email=f"{first.lower()}.{last.lower()}@mathworks.com",
                first_name=first,
                last_name=last,
            )
            cs_users.append(u)
            session.add(u)
            session.flush()
            role_assignments.append(CSRoleMember(cs_user_id=u.id, cs_role_id=role.id))

    session.add_all(role_assignments)
    session.flush()

    # Named demo rep
    sarah = CSUser(email="rep.sarah@mathworks.com", first_name="Sarah", last_name="Mitchell")
    session.add(sarah)
    session.flush()
    session.add(CSRoleMember(cs_user_id=sarah.id, cs_role_id=cs_roles["CS-L1"].id))
    session.flush()
    cs_users.append(sarah)
    return cs_users


# ── 11. Audit log ─────────────────────────────────────────────────────────────

def _fmt_reason(template: str, **kwargs) -> str:
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def seed_audit_log(session: Session, cs_users: list[CSUser], licenses: list[License],
                    entities: list[Entity], products: dict):
    today = datetime.now()
    entity_by_id = {e.id: e for e in entities}
    actions = list(AUDIT_REASONS.keys())
    role_by_user: dict[int, str] = {}

    # Resolve each CS user's role
    for rm in session.query(CSRoleMember).all():
        role = session.get(CSRole, rm.cs_role_id)
        role_by_user[rm.cs_user_id] = role.name

    active_licenses = [l for l in licenses if l.status == "active"]
    product_list = list(products.values())

    audit_entries = []
    for i in range(2000):
        actor = random.choice(cs_users)
        actor_role = role_by_user.get(actor.id, "CS-L1")
        role_level = int(actor_role[-1])

        # Pick an action the actor's role can perform
        allowed = CS_PERMISSIONS[actor_role]
        action = random.choice(allowed)

        lic = random.choice(active_licenses)
        entity = entity_by_id.get(lic.entity_id)
        entity_name = entity.name if entity else "Unknown Corp"
        prod = random.choice(product_list)

        templates = AUDIT_REASONS.get(action, ["Action performed on license {license}."])
        reason = _fmt_reason(
            random.choice(templates),
            product=prod.name, license=lic.id, seats=lic.seat_count,
            days=random.randint(91, 300), machine=f"MAC-{random.randint(1000,9999)}",
            user=fake.email(), entity=entity_name,
            delta=random.randint(5, 20), order=f"ORD-{random.randint(10000,99999)}",
            old=lic.seat_count, new=lic.seat_count + random.randint(5, 20),
            old_admin=fake.email(), new_admin=fake.email(),
        )

        outcome = random.choices(["success", "failure", "rejected"], weights=[0.88, 0.07, 0.05])[0]
        ts = today - timedelta(days=random.randint(0, 730), hours=random.randint(0, 23))

        audit_entries.append(CSAuditLog(
            audit_id=f"AUD-{i+1:05d}",
            timestamp=ts,
            cs_actor_id=actor.id,
            cs_role=actor_role,
            action=action,
            tool_name=action,
            target_license_id=lic.id,
            target_product_name=prod.name,
            args_json=json.dumps({"license_id": lic.id, "product": prod.name}),
            reason=reason,
            outcome=outcome,
            before_state_json=json.dumps({"seat_utilization": f"{random.randint(7,10)}/{lic.seat_count}"}),
            after_state_json=json.dumps({"seat_utilization": f"{random.randint(6,9)}/{lic.seat_count}"}),
        ))

    session.add_all(audit_entries)
    session.flush()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Creating database schema...")
    engine = get_engine(DB_PATH)
    create_all(engine)

    with Session(engine) as session:
        print("Seeding reference data (entity types, license types, products, CS roles)...")
        entity_types, license_types, products, cs_roles = seed_reference(session)

        print("Seeding entities (AWS SaaS + Faker)...")
        entities = seed_entities(session, entity_types)
        print(f"  → {len(entities)} entities")

        print("Seeding licenses...")
        licenses = seed_licenses(session, entities, license_types)
        print(f"  → {len(licenses)} licenses")

        print("Seeding license products...")
        license_product_map = seed_license_products(session, licenses, entities, products)

        print("Seeding users...")
        users_by_entity = seed_users(session, entities)
        total_users = sum(len(v) for v in users_by_entity.values())
        print(f"  → {total_users} users")

        print("Seeding license memberships + admins...")
        license_members = seed_license_memberships(session, licenses, users_by_entity)

        print("Seeding entitlements...")
        entitlements = seed_entitlements(session, licenses, license_members, license_product_map)
        print(f"  → {len(entitlements)} entitlements")

        print("Seeding installations + activations...")
        seed_activations(session, licenses, license_members, license_product_map)

        print("Seeding demo scenario (Acme Corp, L-99001, jane.doe@acmecorp.com)...")
        seed_demo_scenario(session, products, license_types)

        print("Seeding CS users...")
        cs_users = seed_cs_users(session, cs_roles)
        print(f"  → {len(cs_users)} CS users")

        print("Seeding audit log (2 000 records)...")
        seed_audit_log(session, cs_users, licenses, entities, products)

        session.commit()

    print(f"\nDone. Database at: {DB_PATH}")


if __name__ == "__main__":
    main()

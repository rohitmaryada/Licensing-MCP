"""SQLAlchemy Core table metadata mirroring db/schema.sql.

Explicit Column defs, not reflection — no DB round-trip at import time, and
each service only imports the tables it owns (§3 table ownership is enforced
by which queries.py imports what, not by anything here). Enum columns come
back as plain strings via psycopg, so Text is the right Core type for them.
"""

import sqlalchemy as sa

metadata = sa.MetaData()

product = sa.Table(
    "product",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("product_code", sa.Text),
    sa.Column("name", sa.Text),
    sa.Column("category", sa.Text),
    sa.Column("is_suite", sa.Boolean),
    sa.Column("base_price", sa.Numeric),
)

entity = sa.Table(
    "entity",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("name", sa.Text),
    sa.Column("entity_type", sa.Text),
    sa.Column("industry", sa.Text),
    sa.Column("country", sa.Text),
    sa.Column("region", sa.Text),
    sa.Column("external_ref", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

app_user = sa.Table(
    "app_user",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("web_profile_id", sa.BigInteger),
    sa.Column("email", sa.Text),
    sa.Column("first_name", sa.Text),
    sa.Column("last_name", sa.Text),
    sa.Column("entity_id", sa.BigInteger),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

master_license = sa.Table(
    "master_license",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("master_license_ref", sa.Text),
    sa.Column("entity_id", sa.BigInteger),
    sa.Column("label", sa.Text),
    sa.Column("program", sa.Text),
    sa.Column("sponsor", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

license = sa.Table(
    "license",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("license_ref", sa.Text),
    sa.Column("master_license_id", sa.BigInteger),
    sa.Column("status", sa.Text),
    sa.Column("start_date", sa.Date),
    sa.Column("expiry_date", sa.Date),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

license_product = sa.Table(
    "license_product",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("master_license_id", sa.BigInteger),
    sa.Column("license_id", sa.BigInteger),
    sa.Column("product_id", sa.BigInteger),
    sa.Column("seat_count", sa.Integer),
    sa.Column("business_offering_id", sa.BigInteger),
)

entitlement = sa.Table(
    "entitlement",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("license_id", sa.BigInteger),
    sa.Column("master_license_id", sa.BigInteger),
    sa.Column("license_product_id", sa.BigInteger),
    sa.Column("product_id", sa.BigInteger),
    sa.Column("entitlement_type", sa.Text),
    sa.Column("activation_type", sa.Text),
    sa.Column("status", sa.Text),
    sa.Column("label", sa.Text),
    sa.Column("granted_at", sa.Date),
)

policy = sa.Table(
    "policy",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("entitlement_id", sa.BigInteger),
    sa.Column("policy_name", sa.Text),
    sa.Column("quantity", sa.Integer),
    sa.Column("max_activations", sa.Integer),
    sa.Column("activation_ttl_days", sa.Integer),
    sa.Column("allow_offline", sa.Boolean),
    sa.Column("reactivation_limit", sa.Integer),
)

entitlement_person = sa.Table(
    "entitlement_person",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("entitlement_id", sa.BigInteger),
    sa.Column("user_id", sa.BigInteger),
    sa.Column("role", sa.Text),
    sa.Column("added_date", sa.Date),
    sa.Column("status", sa.Text),
)

activation = sa.Table(
    "activation",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("entitlement_id", sa.BigInteger),
    sa.Column("user_id", sa.BigInteger),
    sa.Column("machine_id", sa.Text),
    sa.Column("machine_name", sa.Text),
    sa.Column("os", sa.Text),
    sa.Column("activation_date", sa.Date),
    sa.Column("last_heartbeat", sa.DateTime(timezone=True)),
    sa.Column("status", sa.Text),
)

license_end_user = sa.Table(
    "license_end_user",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("license_id", sa.BigInteger),
    sa.Column("user_id", sa.BigInteger),
    sa.Column("added_date", sa.Date),
    sa.Column("status", sa.Text),
)

master_license_admin = sa.Table(
    "master_license_admin",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("master_license_id", sa.BigInteger),
    sa.Column("user_id", sa.BigInteger),
    sa.Column("renewal_notifications", sa.Boolean),
    sa.Column("added_date", sa.Date),
)

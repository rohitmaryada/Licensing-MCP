from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Boolean, Float,
    ForeignKey, Text, Enum, UniqueConstraint, create_engine
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class EntityType(Base):
    __tablename__ = "entity_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)   # enterprise, academic, individual, government
    description = Column(String(200))
    entities = relationship("Entity", back_populates="entity_type")


class Entity(Base):
    __tablename__ = "entities"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    entity_type_id = Column(Integer, ForeignKey("entity_types.id"), nullable=False)
    industry = Column(String(100))
    country = Column(String(100))
    region = Column(String(100))
    external_ref = Column(String(50))           # original Customer ID from source data
    created_at = Column(DateTime, default=datetime.utcnow)

    entity_type = relationship("EntityType", back_populates="entities")
    licenses = relationship("License", back_populates="entity")
    users = relationship("User", back_populates="entity")


class LicenseType(Base):
    __tablename__ = "license_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)   # enterprise, academic, individual, concurrent, trial
    description = Column(String(200))
    licenses = relationship("License", back_populates="license_type")


class License(Base):
    __tablename__ = "licenses"
    id = Column(String(20), primary_key=True)               # L-XXXXX
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    license_type_id = Column(Integer, ForeignKey("license_types.id"), nullable=False)
    status = Column(Enum("active", "expired", "trial", "suspended", name="license_status"), default="active")
    seat_count = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    entity = relationship("Entity", back_populates="licenses")
    license_type = relationship("LicenseType", back_populates="licenses")
    license_products = relationship("LicenseProduct", back_populates="license")
    license_users = relationship("LicenseUser", back_populates="license")
    license_admins = relationship("LicenseAdmin", back_populates="license")
    entitlements = relationship("Entitlement", back_populates="license")
    activations = relationship("Activation", back_populates="license")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    product_code = Column(String(50), unique=True, nullable=False)
    category = Column(String(100))
    description = Column(String(500))
    base_price = Column(Float)

    license_products = relationship("LicenseProduct", back_populates="product")
    entitlements = relationship("Entitlement", back_populates="product")
    installations = relationship("Installation", back_populates="product")
    activations = relationship("Activation", back_populates="product")


class LicenseProduct(Base):
    __tablename__ = "license_products"
    id = Column(Integer, primary_key=True)
    license_id = Column(String(20), ForeignKey("licenses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    __table_args__ = (UniqueConstraint("license_id", "product_id"),)

    license = relationship("License", back_populates="license_products")
    product = relationship("Product", back_populates="license_products")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    entity = relationship("Entity", back_populates="users")
    license_memberships = relationship("LicenseUser", back_populates="user")
    admin_roles = relationship("LicenseAdmin", back_populates="user")
    entitlements = relationship("Entitlement", back_populates="user")
    installations = relationship("Installation", back_populates="user")
    activations = relationship("Activation", back_populates="user")


class LicenseUser(Base):
    __tablename__ = "license_users"
    id = Column(Integer, primary_key=True)
    license_id = Column(String(20), ForeignKey("licenses.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    added_date = Column(Date, nullable=False)
    status = Column(Enum("active", "inactive", name="license_user_status"), default="active")
    __table_args__ = (UniqueConstraint("license_id", "user_id"),)

    license = relationship("License", back_populates="license_users")
    user = relationship("User", back_populates="license_memberships")


class LicenseAdmin(Base):
    __tablename__ = "license_admins"
    id = Column(Integer, primary_key=True)
    license_id = Column(String(20), ForeignKey("licenses.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    added_date = Column(Date, nullable=False)
    __table_args__ = (UniqueConstraint("license_id", "user_id"),)

    license = relationship("License", back_populates="license_admins")
    user = relationship("User", back_populates="admin_roles")


class Entitlement(Base):
    """Denormalized: user × license × product. Derived from license membership + license products."""
    __tablename__ = "entitlements"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    license_id = Column(String(20), ForeignKey("licenses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    status = Column(Enum("active", "inactive", name="entitlement_status"), default="active")
    granted_at = Column(Date, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "license_id", "product_id"),)

    user = relationship("User", back_populates="entitlements")
    license = relationship("License", back_populates="entitlements")
    product = relationship("Product", back_populates="entitlements")


class Installation(Base):
    __tablename__ = "installations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    machine_id = Column(String(50), nullable=False)
    machine_name = Column(String(200))
    os = Column(String(50))
    install_date = Column(Date, nullable=False)

    user = relationship("User", back_populates="installations")
    product = relationship("Product", back_populates="installations")


class Activation(Base):
    __tablename__ = "activations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    machine_id = Column(String(50), nullable=False)
    license_id = Column(String(20), ForeignKey("licenses.id"), nullable=False)
    activation_date = Column(Date, nullable=False)
    last_heartbeat = Column(DateTime, nullable=False)
    status = Column(Enum("active", "inactive", name="activation_status"), default="active")
    __table_args__ = (UniqueConstraint("user_id", "product_id", "machine_id"),)

    user = relationship("User", back_populates="activations")
    product = relationship("Product", back_populates="activations")
    license = relationship("License", back_populates="activations")


# ── CS Identity Schema ──────────────────────────────────────────────────────

class CSRole(Base):
    __tablename__ = "cs_roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)   # CS-L1, CS-L2, CS-L3
    description = Column(String(200))
    level = Column(Integer, nullable=False)                  # 1, 2, 3

    permissions = relationship("CSPermission", back_populates="role")
    members = relationship("CSRoleMember", back_populates="role")


class CSUser(Base):
    __tablename__ = "cs_users"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    role_memberships = relationship("CSRoleMember", back_populates="cs_user")
    audit_entries = relationship("CSAuditLog", back_populates="cs_actor")


class CSPermission(Base):
    __tablename__ = "cs_permissions"
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("cs_roles.id"), nullable=False)
    tool_name = Column(String(100), nullable=False)
    __table_args__ = (UniqueConstraint("role_id", "tool_name"),)

    role = relationship("CSRole", back_populates="permissions")


class CSRoleMember(Base):
    __tablename__ = "cs_role_members"
    id = Column(Integer, primary_key=True)
    cs_user_id = Column(Integer, ForeignKey("cs_users.id"), nullable=False)
    cs_role_id = Column(Integer, ForeignKey("cs_roles.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("cs_user_id", "cs_role_id"),)

    cs_user = relationship("CSUser", back_populates="role_memberships")
    role = relationship("CSRole", back_populates="members")


# ── Audit Log ───────────────────────────────────────────────────────────────

class CSAuditLog(Base):
    __tablename__ = "cs_audit_log"
    id = Column(Integer, primary_key=True)
    audit_id = Column(String(20), unique=True, nullable=False)  # AUD-XXXXX
    timestamp = Column(DateTime, nullable=False)
    cs_actor_id = Column(Integer, ForeignKey("cs_users.id"), nullable=False)
    cs_role = Column(String(20), nullable=False)
    action = Column(String(100), nullable=False)
    tool_name = Column(String(100), nullable=False)
    target_user_email = Column(String(200))
    target_license_id = Column(String(20))
    target_product_name = Column(String(200))
    args_json = Column(Text)
    reason = Column(Text, nullable=False)
    outcome = Column(Enum("success", "failure", "rejected", name="audit_outcome"), nullable=False)
    before_state_json = Column(Text)
    after_state_json = Column(Text)

    cs_actor = relationship("CSUser", back_populates="audit_entries")


def get_engine(db_path: str = "data/licensing.db"):
    return create_engine(f"sqlite:///{db_path}", echo=False)


def create_all(engine):
    Base.metadata.create_all(engine)

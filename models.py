# models.py

import os
import enum
from sqlalchemy import (
    create_engine, Column, Integer, String, ForeignKey, DateTime, Text, Numeric, Boolean,
    Enum as SQLAlchemyEnum, UniqueConstraint
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func # For server-side default timestamps
import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("CRITICAL: DATABASE_URL environment variable not set.")
    raise ValueError("DATABASE_URL not found. Please set it in your environment or .env file.")

try:
    engine = create_engine(DATABASE_URL)
except Exception as e:
    print(f"Error creating database engine: {e}")
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Enums ---
class UserLayoutEnumDef(enum.Enum): # Renamed to avoid conflict if UserLayout class exists elsewhere
    WIDE = "wide"
    CENTERED = "centered"

# --- Model Definitions ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False) # Added for Streamlit Authenticator
    layout_preference = Column(SQLAlchemyEnum(UserLayoutEnumDef, name="user_layout_enum_def"), default=UserLayoutEnumDef.WIDE, nullable=False)
    role = Column(String, default="user") # For potential future roles
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships (standardized names)
    ingredients = relationship("Ingredient", back_populates="user_ref", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="user_ref", cascade="all, delete-orphan")
    standard_production_tasks = relationship("StandardProductionTask", back_populates="user_ref", cascade="all, delete-orphan")
    standard_shipping_tasks = relationship("StandardShippingTask", back_populates="user_ref", cascade="all, delete-orphan")
    global_costs = relationship("GlobalCosts", back_populates="user_ref", uselist=False, cascade="all, delete-orphan")
    global_salaries = relationship("GlobalSalary", back_populates="user_ref", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="user_ref", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"

class Ingredient(Base):
    __tablename__ = "ingredients"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    provider = Column(String, nullable=True) # Allow nullable provider
    price_per_unit = Column(Numeric(10, 2), nullable=False)
    unit_quantity_kg = Column(Numeric(10, 3), nullable=False)
    price_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_ref = relationship("User", back_populates="ingredients")
    __table_args__ = (UniqueConstraint('user_id', 'name', 'provider', name='uq_user_ingredient_provider'),)
    def __repr__(self):
        return f"<Ingredient(id={self.id}, name='{self.name}', user_id={self.user_id})>"

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    role = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_ref = relationship("User", back_populates="employees")
    global_salary_entry = relationship("GlobalSalary", back_populates="employee_ref", uselist=False, cascade="all, delete-orphan")
    production_task_assignments = relationship("ProductProductionTask", back_populates="employee_ref")
    shipping_task_assignments = relationship("ProductShippingTask", back_populates="employee_ref")
    __table_args__ = (UniqueConstraint('user_id', 'name', name='uq_user_employee_name'),)
    def __repr__(self):
        return f"<Employee(id={self.id}, name='{self.name}', user_id={self.user_id})>"

class StandardProductionTask(Base):
    __tablename__ = "standard_production_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_ref = relationship("User", back_populates="standard_production_tasks")
    # product_assignments = relationship("ProductProductionTask", back_populates="standard_task_ref")
    __table_args__ = (UniqueConstraint('user_id', 'task_name', name='uq_user_std_prod_task_name'),)

class StandardShippingTask(Base):
    __tablename__ = "standard_shipping_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_ref = relationship("User", back_populates="standard_shipping_tasks")
    # product_assignments = relationship("ProductShippingTask", back_populates="standard_task_ref")
    __table_args__ = (UniqueConstraint('user_id', 'task_name', name='uq_user_std_ship_task_name'),)

class GlobalCosts(Base):
    __tablename__ = "global_costs" # Renamed for consistency
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    monthly_rent = Column(Numeric(10, 2), default=0.0, nullable=False)
    monthly_utilities = Column(Numeric(10, 2), default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_ref = relationship("User", back_populates="global_costs")

class GlobalSalary(Base):
    __tablename__ = "global_salaries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    monthly_amount = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_ref = relationship("User", back_populates="global_salaries")
    employee_ref = relationship("Employee", back_populates="global_salary_entry")
    __table_args__ = (UniqueConstraint('user_id', 'employee_id', name='uq_user_employee_global_salary'),)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_name = Column(String, nullable=False)
    batch_size_items = Column(Integer, default=100, nullable=False)
    monthly_production_items = Column(Integer, default=1000, nullable=False)
    
    # Individual columns for costs/fees/pricing
    packaging_label_cost = Column(Numeric(10, 3), default=0.05, nullable=True)
    packaging_material_cost = Column(Numeric(10, 3), default=0.10, nullable=True)
    
    salary_allocation_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    salary_allocation_items_per_month = Column(Integer, default=1000, nullable=True)
    
    rent_utilities_allocation_items_per_month = Column(Integer, default=1000, nullable=True)
    
    retail_avg_order_value = Column(Numeric(10, 2), default=30.00, nullable=True)
    retail_cc_fee_percent = Column(Numeric(5, 4), default=0.03, nullable=True) # e.g. 0.0299 for 2.99%
    retail_platform_fee_percent = Column(Numeric(5, 4), default=0.05, nullable=True)
    retail_shipping_cost_paid_by_you = Column(Numeric(10, 2), default=5.0, nullable=True)
    
    wholesale_avg_order_value = Column(Numeric(10, 2), default=200.00, nullable=True)
    wholesale_commission_percent = Column(Numeric(5, 4), default=0.15, nullable=True)
    wholesale_processing_fee_percent = Column(Numeric(5, 4), default=0.02, nullable=True)
    wholesale_flat_fee_per_order = Column(Numeric(10, 2), default=0.25, nullable=True)
    
    wholesale_price_per_item = Column(Numeric(10, 2), default=5.00, nullable=True)
    retail_price_per_item = Column(Numeric(10, 2), default=10.00, nullable=True)
    buffer_percentage = Column(Numeric(5, 4), default=0.10, nullable=True) # e.g. 0.10 for 10%
    
    distribution_wholesale_percentage = Column(Numeric(5, 4), default=0.5, nullable=True) # e.g. 0.60 for 60%

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()) # Changed from last_updated

    user_ref = relationship("User", back_populates="products")
    salary_alloc_employee_ref = relationship("Employee") # For the single employee whose salary is allocated

    # Relationships to components/tasks
    materials = relationship("ProductMaterial", back_populates="product_ref", cascade="all, delete-orphan")
    production_tasks = relationship("ProductProductionTask", back_populates="product_ref", cascade="all, delete-orphan")
    shipping_tasks = relationship("ProductShippingTask", back_populates="product_ref", cascade="all, delete-orphan")
    
    __table_args__ = (UniqueConstraint('user_id', 'product_name', name='uq_user_product_name'),)
    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.product_name}', user_id={self.user_id})>"

class ProductMaterial(Base):
    __tablename__ = "product_materials"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False) # Removed ondelete, use ORM cascade
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False) # Removed ondelete
    quantity_grams = Column(Numeric(10, 3), nullable=False) # Renamed from quantity_grams_used

    product_ref = relationship("Product", back_populates="materials")
    ingredient_ref = relationship("Ingredient") # No back_populates to Ingredient.product_materials needed for now
    __table_args__ = (UniqueConstraint('product_id', 'ingredient_id', name='uq_product_material_ingredient'),)

# Abstract base for common task fields - NO TABLE created for this
class ProductTaskPerformanceBase:
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False) # Removed ondelete
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True) # Removed ondelete, allow NULL if employee deleted
    time_minutes = Column(Numeric(10, 1), nullable=False)
    items_processed_in_task = Column(Integer, nullable=False, default=1)

    # employee_ref will be defined in concrete classes if they need to link back to Employee's task lists

class ProductProductionTask(Base, ProductTaskPerformanceBase):
    __tablename__ = "product_production_tasks"
    id = Column(Integer, primary_key=True, index=True) # Own PK
    standard_task_id = Column(Integer, ForeignKey("standard_production_tasks.id"), nullable=False) # Removed ondelete

    product_ref = relationship("Product", back_populates="production_tasks")
    standard_task_ref = relationship("StandardProductionTask") # No back_populates to StandardProductionTask.product_assignments
    employee_ref = relationship("Employee", back_populates="production_task_assignments")

class ProductShippingTask(Base, ProductTaskPerformanceBase):
    __tablename__ = "product_shipping_tasks"
    id = Column(Integer, primary_key=True, index=True) # Own PK
    standard_task_id = Column(Integer, ForeignKey("standard_shipping_tasks.id"), nullable=False) # Removed ondelete

    product_ref = relationship("Product", back_populates="shipping_tasks")
    standard_task_ref = relationship("StandardShippingTask") # No back_populates to StandardShippingTask.product_assignments
    employee_ref = relationship("Employee", back_populates="shipping_task_assignments")


# --- Database Initialization Utility ---
def init_db_structure():
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables checked/created successfully based on models.py.")
    except Exception as e:
        print(f"Error during database table creation: {e}")
        raise

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    db_url_display = DATABASE_URL
    if "@" in db_url_display and db_url_display.count(':') > 1: # Avoid showing password
        parts = db_url_display.split(':')
        db_url_display = f"{parts[0]}:***@{db_url_display.split('@')[-1]}"
    elif "@" in db_url_display:
         db_url_display = f"...@{db_url_display.split('@')[-1]}"

    print(f"Attempting to initialize database structure using DB endpoint: {db_url_display}")
    init_db_structure()
    print("Database structure initialization attempt complete.")
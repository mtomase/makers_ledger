# models.py

import os
import enum
import datetime # <-- Added for Date type
from sqlalchemy import (
    create_engine, Column, Integer, String, ForeignKey, DateTime, Text, Numeric, Boolean,
    Enum as SQLAlchemyEnum, UniqueConstraint, Date # <-- Added Date
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found. Please set it in your environment or .env file.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserLayoutEnumDef(enum.Enum):
    WIDE = "wide"
    CENTERED = "centered"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    layout_preference = Column(SQLAlchemyEnum(UserLayoutEnumDef, name="user_layout_enum_def"), default=UserLayoutEnumDef.WIDE, nullable=False)
    role = Column(String, default="user")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

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
    provider = Column(String, nullable=True)
    price_per_unit = Column(Numeric(10, 2), nullable=False)
    unit_quantity_kg = Column(Numeric(10, 3), nullable=False)
    price_url = Column(Text, nullable=True)
    
    # --- NEW INVENTORY COLUMNS ---
    current_stock_grams = Column(Numeric(10, 3), nullable=False, default=0.0)
    reorder_threshold_grams = Column(Numeric(10, 3), nullable=True)
    # --- END NEW COLUMNS ---

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_ref = relationship("User", back_populates="ingredients")
    
    # --- NEW RELATIONSHIP ---
    stock_additions = relationship("StockAddition", back_populates="ingredient_ref", cascade="all, delete-orphan")
    # --- END NEW RELATIONSHIP ---

    __table_args__ = (UniqueConstraint('user_id', 'name', 'provider', name='uq_user_ingredient_provider'),)
    def __repr__(self):
        return f"<Ingredient(id={self.id}, name='{self.name}', user_id={self.user_id})>"

# --- NEW TABLE MODEL ---
class StockAddition(Base):
    __tablename__ = "stock_additions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    
    quantity_added_grams = Column(Numeric(10, 3), nullable=False)
    purchase_date = Column(Date, nullable=False, default=datetime.date.today)
    cost_of_addition = Column(Numeric(10, 2), nullable=True)
    supplier_info = Column(String, nullable=True) # e.g., "Supplier X - Invoice #123"
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ingredient_ref = relationship("Ingredient", back_populates="stock_additions")
# --- END NEW TABLE ---

# ... (The rest of the models: Employee, StandardProductionTask, etc. remain the same) ...
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
    __table_args__ = (UniqueConstraint('user_id', 'task_name', name='uq_user_std_prod_task_name'),)

class StandardShippingTask(Base):
    __tablename__ = "standard_shipping_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_ref = relationship("User", back_populates="standard_shipping_tasks")
    __table_args__ = (UniqueConstraint('user_id', 'task_name', name='uq_user_std_ship_task_name'),)

class GlobalCosts(Base):
    __tablename__ = "global_costs"
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
    
    packaging_label_cost = Column(Numeric(10, 3), default=0.05, nullable=True)
    packaging_material_cost = Column(Numeric(10, 3), default=0.10, nullable=True)
    
    salary_allocation_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    salary_allocation_items_per_month = Column(Integer, default=1000, nullable=True)
    
    rent_utilities_allocation_items_per_month = Column(Integer, default=1000, nullable=True)
    
    retail_avg_order_value = Column(Numeric(10, 2), default=30.00, nullable=True)
    retail_cc_fee_percent = Column(Numeric(5, 4), default=0.03, nullable=True)
    retail_platform_fee_percent = Column(Numeric(5, 4), default=0.05, nullable=True)
    retail_shipping_cost_paid_by_you = Column(Numeric(10, 2), default=5.0, nullable=True)
    
    wholesale_avg_order_value = Column(Numeric(10, 2), default=200.00, nullable=True)
    wholesale_commission_percent = Column(Numeric(5, 4), default=0.15, nullable=True)
    wholesale_processing_fee_percent = Column(Numeric(5, 4), default=0.02, nullable=True)
    wholesale_flat_fee_per_order = Column(Numeric(10, 2), default=0.25, nullable=True)
    
    wholesale_price_per_item = Column(Numeric(10, 2), default=5.00, nullable=True)
    retail_price_per_item = Column(Numeric(10, 2), default=10.00, nullable=True)
    buffer_percentage = Column(Numeric(5, 4), default=0.10, nullable=True)
    
    distribution_wholesale_percentage = Column(Numeric(5, 4), default=0.5, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_ref = relationship("User", back_populates="products")
    salary_alloc_employee_ref = relationship("Employee")

    materials = relationship("ProductMaterial", back_populates="product_ref", cascade="all, delete-orphan")
    production_tasks = relationship("ProductProductionTask", back_populates="product_ref", cascade="all, delete-orphan")
    shipping_tasks = relationship("ProductShippingTask", back_populates="product_ref", cascade="all, delete-orphan")
    
    __table_args__ = (UniqueConstraint('user_id', 'product_name', name='uq_user_product_name'),)
    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.product_name}', user_id={self.user_id})>"

class ProductMaterial(Base):
    __tablename__ = "product_materials"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    quantity_grams = Column(Numeric(10, 3), nullable=False)

    product_ref = relationship("Product", back_populates="materials")
    ingredient_ref = relationship("Ingredient")
    __table_args__ = (UniqueConstraint('product_id', 'ingredient_id', name='uq_product_material_ingredient'),)

class ProductTaskPerformanceBase:
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    time_minutes = Column(Numeric(10, 1), nullable=False)
    items_processed_in_task = Column(Integer, nullable=False, default=1)

class ProductProductionTask(Base, ProductTaskPerformanceBase):
    __tablename__ = "product_production_tasks"
    id = Column(Integer, primary_key=True, index=True)
    standard_task_id = Column(Integer, ForeignKey("standard_production_tasks.id"), nullable=False)

    product_ref = relationship("Product", back_populates="production_tasks")
    standard_task_ref = relationship("StandardProductionTask")
    employee_ref = relationship("Employee", back_populates="production_task_assignments")

class ProductShippingTask(Base, ProductTaskPerformanceBase):
    __tablename__ = "product_shipping_tasks"
    id = Column(Integer, primary_key=True, index=True)
    standard_task_id = Column(Integer, ForeignKey("standard_shipping_tasks.id"), nullable=False)

    product_ref = relationship("Product", back_populates="shipping_tasks")
    standard_task_ref = relationship("StandardShippingTask")
    employee_ref = relationship("Employee", back_populates="shipping_task_assignments")

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
    print("Initializing database structure...")
    init_db_structure()
    print("Database structure initialization complete.")
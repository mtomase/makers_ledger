# models.py

import os
import enum
import datetime
from decimal import Decimal
from sqlalchemy import (
    create_engine, func, Column, Integer, String, ForeignKey, DateTime, Text, Numeric, Boolean,
    Enum as SQLAlchemyEnum, UniqueConstraint, Date, Table
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

# --- Association Table ---
ingredient_supplier_association = Table('ingredient_supplier_association', Base.metadata,
    Column('ingredient_id', Integer, ForeignKey('ingredients.id', ondelete="CASCADE")),
    Column('supplier_id', Integer, ForeignKey('suppliers.id', ondelete="CASCADE")),
    UniqueConstraint('ingredient_id', 'supplier_id', name='uq_ingredient_supplier')
)

# --- Enums ---
class UserLayoutEnumDef(enum.Enum):
    WIDE = "wide"; CENTERED = "centered"
class SafetyCheckStatus(enum.Enum):
    DONE = "✓"; NOT_DONE = "x"; NOT_APPLICABLE = "N/A"
class InvoiceStatus(enum.Enum):
    DRAFT = "Draft"; SENT = "Sent"; PAID = "Paid"; VOID = "Void"
class TransactionType(enum.Enum):
    EXPENSE = "Expense"; SALE = "Sale"; DRAWING = "Drawing"; CAPITAL_INJECTION = "Capital Injection"

# --- Model Classes ---

class IngredientType(Base):
    __tablename__ = "ingredient_types"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    user_ref = relationship("User")
    __table_args__ = (UniqueConstraint('user_id', 'name', name='uq_user_ingredient_type_name'),)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    country_code = Column(String(2), nullable=True) # e.g., "IE", "US", "GB"
    layout_preference = Column(SQLAlchemyEnum(UserLayoutEnumDef, name="user_layout_enum_def"), default=UserLayoutEnumDef.WIDE, nullable=False)
    role = Column(String, default="user")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # Relationships
    ingredients = relationship("Ingredient", back_populates="user_ref", cascade="all, delete-orphan")
    suppliers = relationship("Supplier", back_populates="user_ref", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="user_ref", cascade="all, delete-orphan")
    standard_production_tasks = relationship("StandardProductionTask", back_populates="user_ref", cascade="all, delete-orphan")
    standard_shipping_tasks = relationship("StandardShippingTask", back_populates="user_ref", cascade="all, delete-orphan")
    global_costs = relationship("GlobalCosts", back_populates="user_ref", uselist=False, cascade="all, delete-orphan")
    global_salaries = relationship("GlobalSalary", back_populates="user_ref", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="user_ref", cascade="all, delete-orphan")
    purchase_orders = relationship("PurchaseOrder", back_populates="user_ref", cascade="all, delete-orphan")
    production_runs = relationship("ProductionRun", back_populates="user_ref", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="user_ref", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="user_ref", cascade="all, delete-orphan")
    expense_categories = relationship("ExpenseCategory", back_populates="user_ref", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user_ref", cascade="all, delete-orphan")

class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    address = Column(Text, nullable=True)
    phone_number = Column(String, nullable=True)
    website_url = Column(Text, nullable=True)
    contact_email = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user_ref = relationship("User", back_populates="suppliers")
    ingredients = relationship("Ingredient", secondary=ingredient_supplier_association, back_populates="suppliers")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier_ref")
    invoices = relationship("Invoice", back_populates="supplier_ref")
    __table_args__ = (UniqueConstraint('user_id', 'name', name='uq_user_supplier_name'),)

class Ingredient(Base):
    __tablename__ = "ingredients"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    inci_name = Column(String, nullable=True)
    ingredient_type_id = Column(Integer, ForeignKey("ingredient_types.id"), nullable=True)
    description = Column(Text, nullable=True)
    reorder_threshold_grams = Column(Numeric(10, 3), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user_ref = relationship("User", back_populates="ingredients")
    ingredient_type_ref = relationship("IngredientType")
    suppliers = relationship("Supplier", secondary=ingredient_supplier_association, back_populates="ingredients")
    stock_additions = relationship("StockAddition", back_populates="ingredient_ref", cascade="all, delete-orphan")
    batch_usages = relationship("BatchIngredientUsage", back_populates="ingredient_ref")
    __table_args__ = (UniqueConstraint('user_id', 'name', name='uq_user_ingredient_name'),)

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    order_date = Column(Date, nullable=False, default=datetime.date.today)
    shipping_cost = Column(Numeric(10, 2), nullable=False, default=Decimal('0.0'))
    notes = Column(Text, nullable=True)
    total_vat = Column(Numeric(10, 2), nullable=False, default=Decimal('0.0'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_ref = relationship("User", back_populates="purchase_orders")
    supplier_ref = relationship("Supplier", back_populates="purchase_orders")
    line_items = relationship("StockAddition", back_populates="purchase_order_ref", cascade="all, delete-orphan")
    documents = relationship("PurchaseDocument", back_populates="purchase_order_ref", cascade="all, delete-orphan")

class PurchaseDocument(Base):
    __tablename__ = "purchase_documents"
    id = Column(Integer, primary_key=True, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    file_path = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    purchase_order_ref = relationship("PurchaseOrder", back_populates="documents")

class StockAddition(Base):
    __tablename__ = "stock_additions"
    id = Column(Integer, primary_key=True, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    quantity_added_grams = Column(Numeric(10, 3), nullable=False)
    item_cost = Column(Numeric(10, 2), nullable=False)
    supplier_lot_number = Column(String, nullable=True)
    quantity_remaining_grams = Column(Numeric(10, 3), nullable=False, default=Decimal('0.0'))
    vat_amount = Column(Numeric(10, 2), nullable=False, default=Decimal('0.0'))
    ingredient_ref = relationship("Ingredient", back_populates="stock_additions")
    purchase_order_ref = relationship("PurchaseOrder", back_populates="line_items")
    batch_usages = relationship("BatchIngredientUsage", back_populates="stock_addition_ref")

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
    batches_responsible_for = relationship("BatchRecord", back_populates="person_responsible_ref")
    batch_production_tasks = relationship("BatchProductionTask", back_populates="employee_ref")
    __table_args__ = (UniqueConstraint('user_id', 'name', name='uq_user_employee_name'),)

class StandardProductionTask(Base):
    __tablename__ = "standard_production_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_name = Column(String, nullable=False)
    user_ref = relationship("User", back_populates="standard_production_tasks")
    __table_args__ = (UniqueConstraint('user_id', 'task_name', name='uq_user_std_prod_task_name'),)

class StandardShippingTask(Base):
    __tablename__ = "standard_shipping_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_name = Column(String, nullable=False)
    user_ref = relationship("User", back_populates="standard_shipping_tasks")
    __table_args__ = (UniqueConstraint('user_id', 'task_name', name='uq_user_std_ship_task_name'),)

class GlobalCosts(Base):
    __tablename__ = "global_costs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    monthly_rent = Column(Numeric(10, 2), default=Decimal('0.0'), nullable=False)
    monthly_utilities = Column(Numeric(10, 2), default=Decimal('0.0'), nullable=False)
    total_monthly_items_for_rent_utilities = Column(Integer, default=1000, nullable=False)
    user_ref = relationship("User", back_populates="global_costs")

class GlobalSalary(Base):
    __tablename__ = "global_salaries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    monthly_amount = Column(Numeric(10, 2), nullable=False)
    user_ref = relationship("User", back_populates="global_salaries")
    employee_ref = relationship("Employee", back_populates="global_salary_entry")
    __table_args__ = (UniqueConstraint('user_id', 'employee_id', name='uq_user_employee_global_salary'),)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_name = Column(String, nullable=False)
    product_code = Column(String(10), nullable=True)
    retail_price_per_item = Column(Numeric(10, 2), default=Decimal('10.00'), nullable=True)
    wholesale_price_per_item = Column(Numeric(10, 2), default=Decimal('5.00'), nullable=True)
    packaging_label_cost = Column(Numeric(10, 3), default=Decimal('0.0'), nullable=True)
    packaging_material_cost = Column(Numeric(10, 3), default=Decimal('0.0'), nullable=True)
    salary_allocation_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    salary_allocation_items_per_month = Column(Integer, default=1000, nullable=True)
    rent_utilities_allocation_items_per_month = Column(Integer, default=1000, nullable=True)
    retail_avg_order_value = Column(Numeric(10, 2), nullable=True)
    retail_cc_fee_percent = Column(Numeric(10, 4), default=Decimal('0.029'), nullable=True)
    retail_platform_fee_percent = Column(Numeric(10, 4), default=Decimal('0.05'), nullable=True)
    retail_shipping_cost_paid_by_you = Column(Numeric(10, 2), nullable=True)
    wholesale_avg_order_value = Column(Numeric(10, 2), nullable=True)
    wholesale_commission_percent = Column(Numeric(10, 4), default=Decimal('0.15'), nullable=True)
    wholesale_processing_fee_percent = Column(Numeric(10, 4), default=Decimal('0.029'), nullable=True)
    wholesale_flat_fee_per_order = Column(Numeric(10, 2), nullable=True)
    distribution_wholesale_percentage = Column(Numeric(5, 4), default=Decimal('0.5'), nullable=True)
    buffer_percentage = Column(Numeric(5, 4), default=Decimal('0.2'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user_ref = relationship("User", back_populates="products")
    materials = relationship("ProductMaterial", back_populates="product_ref", cascade="all, delete-orphan")
    production_tasks = relationship("ProductProductionTask", back_populates="product_ref", cascade="all, delete-orphan")
    shipping_tasks = relationship("ProductShippingTask", back_populates="product_ref", cascade="all, delete-orphan")
    salary_alloc_employee_ref = relationship("Employee")
    production_runs = relationship("ProductionRun", back_populates="product_ref")
    invoice_line_items = relationship("InvoiceLineItem", back_populates="product_ref")
    __table_args__ = (UniqueConstraint('user_id', 'product_name', name='uq_user_product_name'),)

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

class ProductionRun(Base):
    __tablename__ = 'production_runs'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    run_date = Column(DateTime(timezone=True), server_default=func.now())
    planned_batch_count = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    user_ref = relationship("User", back_populates="production_runs")
    product_ref = relationship("Product", back_populates="production_runs")
    batch_records = relationship("BatchRecord", back_populates="production_run_ref", cascade="all, delete-orphan")

class BatchRecord(Base):
    __tablename__ = "batch_records"
    id = Column(Integer, primary_key=True, index=True)
    production_run_id = Column(Integer, ForeignKey("production_runs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    batch_code = Column(String, unique=True, nullable=False)
    person_responsible_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    manufacturing_date = Column(Date, default=datetime.date.today)
    cured_date = Column(Date, nullable=True)
    expiration_date = Column(Date, nullable=True)
    bars_in_batch = Column(Integer, nullable=True)
    final_cured_weight_gr = Column(Numeric(10, 2), nullable=True)
    qc_ph_cured = Column(Numeric(4, 2), nullable=True)
    qc_final_quality_notes = Column(Text, nullable=True)
    production_run_ref = relationship("ProductionRun", back_populates="batch_records")
    person_responsible_ref = relationship("Employee", back_populates="batches_responsible_for")
    ingredient_usages = relationship("BatchIngredientUsage", back_populates="batch_record_ref", cascade="all, delete-orphan")
    safety_checks = relationship("BatchSafetyCheck", back_populates="batch_record_ref", cascade="all, delete-orphan")
    production_tasks = relationship("BatchProductionTask", back_populates="batch_record_ref", cascade="all, delete-orphan")

class BatchIngredientUsage(Base):
    __tablename__ = "batch_ingredient_usages"
    id = Column(Integer, primary_key=True, index=True)
    batch_record_id = Column(Integer, ForeignKey("batch_records.id"), nullable=False)
    stock_addition_id = Column(Integer, ForeignKey("stock_additions.id"), nullable=False)
    quantity_used_grams = Column(Numeric(10, 3), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    batch_record_ref = relationship("BatchRecord", back_populates="ingredient_usages")
    stock_addition_ref = relationship("StockAddition", back_populates="batch_usages")
    ingredient_ref = relationship("Ingredient", back_populates="batch_usages")

class BatchSafetyCheck(Base):
    __tablename__ = "batch_safety_checks"
    id = Column(Integer, primary_key=True, index=True)
    batch_record_id = Column(Integer, ForeignKey("batch_records.id"), nullable=False)
    check_name = Column(String, nullable=False)
    status = Column(SQLAlchemyEnum(SafetyCheckStatus, name="safety_check_status_enum"), nullable=False, default=SafetyCheckStatus.NOT_APPLICABLE)
    batch_record_ref = relationship("BatchRecord", back_populates="safety_checks")
    __table_args__ = (UniqueConstraint('batch_record_id', 'check_name', name='uq_batch_safety_check'),)

class BatchProductionTask(Base):
    __tablename__ = 'batch_production_tasks'
    id = Column(Integer, primary_key=True, index=True)
    batch_record_id = Column(Integer, ForeignKey('batch_records.id'), nullable=False)
    standard_task_id = Column(Integer, ForeignKey('standard_production_tasks.id'), nullable=False)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=False)
    batch_record_ref = relationship("BatchRecord", back_populates="production_tasks")
    standard_task_ref = relationship("StandardProductionTask")
    employee_ref = relationship("Employee", back_populates="batch_production_tasks")
    __table_args__ = (UniqueConstraint('batch_record_id', 'standard_task_id', name='uq_batch_task'),)

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    contact_email = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    vat_number = Column(String, nullable=True)
    user_ref = relationship("User", back_populates="customers")
    invoices = relationship("Invoice", back_populates="customer_ref")
    __table_args__ = (UniqueConstraint('user_id', 'name', name='uq_user_customer_name'),)

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invoice_number = Column(String, nullable=False)
    invoice_date = Column(Date, nullable=False, default=datetime.date.today)
    due_date = Column(Date, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    subtotal = Column(Numeric(10, 2), nullable=False, default=Decimal('0.0'))
    vat_amount = Column(Numeric(10, 2), nullable=False, default=Decimal('0.0'))
    total_amount = Column(Numeric(10, 2), nullable=False, default=Decimal('0.0'))
    status = Column(SQLAlchemyEnum(InvoiceStatus, name="invoice_status_enum"), nullable=False, default=InvoiceStatus.DRAFT)
    notes = Column(Text, nullable=True)
    user_ref = relationship("User", back_populates="invoices")
    customer_ref = relationship("Customer", back_populates="invoices")
    supplier_ref = relationship("Supplier", back_populates="invoices")
    line_items = relationship("InvoiceLineItem", back_populates="invoice_ref", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint('user_id', 'invoice_number', name='uq_user_invoice_number'),)

class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    description = Column(String, nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    vat_rate_percent = Column(Numeric(5, 2), default=Decimal('23.00'))
    line_total = Column(Numeric(10, 2), nullable=False)
    invoice_ref = relationship("Invoice", back_populates="line_items")
    product_ref = relationship("Product", back_populates="invoice_line_items")

class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    user_ref = relationship("User", back_populates="expense_categories")
    transactions = relationship("Transaction", back_populates="category_ref")
    __table_args__ = (UniqueConstraint('user_id', 'name', name='uq_user_expense_category_name'),)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False, default=datetime.date.today)
    description = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    transaction_type = Column(SQLAlchemyEnum(TransactionType, name="transaction_type_enum"), nullable=False)
    category_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    user_ref = relationship("User", back_populates="transactions")
    category_ref = relationship("ExpenseCategory", back_populates="transactions")
    supplier_ref = relationship("Supplier")
    customer_ref = relationship("Customer")
    invoice_ref = relationship("Invoice")
    documents = relationship("TransactionDocument", back_populates="transaction_ref", cascade="all, delete-orphan")

class TransactionDocument(Base):
    __tablename__ = "transaction_documents"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    file_path = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    transaction_ref = relationship("Transaction", back_populates="documents")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
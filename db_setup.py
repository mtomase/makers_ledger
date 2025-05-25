# initialize_database.py
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import text # For executing raw SQL
import bcrypt # Using bcrypt directly for hashing

# Import all models and session/engine from your models.py
from models import (
    engine, Base, User, UserLayoutEnumDef,
    Ingredient, Employee, StandardProductionTask, StandardShippingTask,
    GlobalCosts, GlobalSalary, Product,
    ProductMaterial, ProductProductionTask, ProductShippingTask,
    SessionLocal
)

load_dotenv()

# --- Default User Configuration ---
DEFAULT_USER_USERNAME = os.environ.get("DEFAULT_ADMIN_USERNAME", "mtomas")
DEFAULT_USER_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "manuel.tomas.estarlich@gmail.com")
DEFAULT_USER_NAME = os.environ.get("DEFAULT_ADMIN_NAME", "Manuel")
DEFAULT_USER_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Sistemas8926*")

# --- Bcrypt Hashing Function (from your script) ---
def hash_password_bcrypt(password: str) -> str:
    """Hashes a password using bcrypt."""
    password_bytes = password.encode('utf-8')
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    hashed_str = hashed_bytes.decode('utf-8')
    return hashed_str

# --- Default Data Structure ---
DEFAULT_APP_DATA = {
    "ingredients": [
        {"name": "Distilled Water", "provider": "AquaPure Inc.", "price_per_unit": 1.39, "unit_quantity_kg": 8.3, "price_url": "https://example.com/water"},
        {"name": "Distilled Water", "provider": "Local Supply", "price_per_unit": 1.20, "unit_quantity_kg": 10.0, "price_url": ""},
        {"name": "Sodium Hydroxide (Lye)", "provider": "ChemCo", "price_per_unit": 45.0, "unit_quantity_kg": 5.0, "price_url": "https://example.com/lye"},
        {"name": "Olive Oil", "provider": "Olio Verde", "price_per_unit": 18.0, "unit_quantity_kg": 3.5, "price_url": ""},
    ],
    "employees": [
        {"name": "Owner", "hourly_rate": 25.0, "role": "Production Manager"},
        {"name": "Employee 1", "hourly_rate": 18.0, "role": "Production Assistant"},
    ],
    "standard_production_tasks": [ {"task_name": "Mix Ingredients"}, {"task_name": "Pour into Molds"}, {"task_name": "Unmold & Clean"}, {"task_name": "Cut Loaves"} ],
    "standard_shipping_tasks": [ {"task_name": "Pick from Shelf"}, {"task_name": "Wrap Product"}, {"task_name": "Label Package"}, {"task_name": "Prepare Shipment"} ],
    "global_costs": {"monthly_rent": 1500.0, "monthly_utilities": 250.0},
    "global_salaries": [
        {"employee_name_ref": "Owner", "monthly_amount": 5000.0}
    ],
    "products": [
        {
            "product_name": "Lavender Bliss Soap",
            "batch_size_items": 120,
            "monthly_production_items": 1000,
            "packaging_label_cost": 0.06,
            "packaging_material_cost": 0.12,
            "salary_allocation_employee_name_ref": "Owner",
            "salary_allocation_items_per_month": 1000,
            "rent_utilities_allocation_items_per_month": 1000,
            "retail_avg_order_value": 35.00,
            "retail_cc_fee_percent": 0.029,
            "retail_platform_fee_percent": 0.05,
            "retail_shipping_cost_paid_by_you": 5.50,
            "wholesale_avg_order_value": 250.00,
            "wholesale_commission_percent": 0.12,
            "wholesale_processing_fee_percent": 0.025,
            "wholesale_flat_fee_per_order": 0.30,
            "wholesale_price_per_item": 6.50,
            "retail_price_per_item": 12.00,
            "buffer_percentage": 0.15,
            "distribution_wholesale_percentage": 0.60,
            "materials": [
                {"ingredient_name_ref": "Olive Oil", "ingredient_provider_ref": "Olio Verde", "quantity_grams": 70.0},
                {"ingredient_name_ref": "Sodium Hydroxide (Lye)", "ingredient_provider_ref": "ChemCo", "quantity_grams": 10.0},
                {"ingredient_name_ref": "Distilled Water", "ingredient_provider_ref": "AquaPure Inc.", "quantity_grams": 20.0},
            ],
            "production_tasks": [
                {"task_name_ref": "Mix Ingredients", "employee_name_ref": "Owner", "time_minutes": 30, "items_processed_in_task": 120},
                {"task_name_ref": "Cut Loaves", "employee_name_ref": "Employee 1", "time_minutes": 60, "items_processed_in_task": 120},
            ],
            "shipping_tasks": [
                 {"task_name_ref": "Wrap Product", "employee_name_ref": "Employee 1", "time_minutes": 1, "items_processed_in_task": 1},
            ]
        }
    ]
}

def create_database_and_tables():
    print("Initializing database structure (dropping and recreating tables)...")
    try:
        Base.metadata.drop_all(bind=engine)
        print("Standard drop_all executed.")
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully based on models.py.")

    except Exception as e:
        print(f"Error during standard table recreation: {e}")
        pg_error_code = None
        if hasattr(e, 'orig') and hasattr(e.orig, 'pgcode'):
            pg_error_code = e.orig.pgcode
        
        if pg_error_code == '2BP01' and engine.name == 'postgresql': # 2BP01 is for dependent_objects_still_exist
            print("PostgreSQL dependency error detected (2BP01). Attempting forceful drop with CASCADE...")
            try:
                with engine.connect() as connection:
                    table_names_in_metadata = list(Base.metadata.tables.keys())
                    print(f"Attempting to drop known tables with CASCADE: {table_names_in_metadata}")
                    for table_name in reversed(table_names_in_metadata):
                        try:
                            connection.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;'))
                            print(f"Force dropped table: {table_name} with CASCADE")
                        except Exception as drop_e:
                            print(f"Warning: Could not force drop table {table_name}: {drop_e}")
                    connection.commit()
                
                Base.metadata.create_all(bind=engine)
                print("New tables created successfully after attempting forceful drop.")
            except Exception as e2:
                print(f"Error even after attempting forceful drop: {e2}")
                print("Please ensure your database user has permissions to DROP and CREATE tables.")
                raise
        else:
            print("The error was not identified as a PostgreSQL dependency issue (2BP01) for forceful drop, or not PostgreSQL.")
            raise


def populate_default_data_for_user(db: Session):
    print(f"Populating default data for user: {DEFAULT_USER_USERNAME}")

    user = db.query(User).filter(User.username == DEFAULT_USER_USERNAME).first()
    if not user:
        print(f"User {DEFAULT_USER_USERNAME} not found, creating...")
        # Use the imported bcrypt hashing function
        hashed_password = hash_password_bcrypt(DEFAULT_USER_PASSWORD)
        user = User(
            username=DEFAULT_USER_USERNAME,
            email=DEFAULT_USER_EMAIL,
            name=DEFAULT_USER_NAME,
            hashed_password=hashed_password,
            layout_preference=UserLayoutEnumDef.WIDE
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
            print(f"User {user.username} created with ID {user.id}.")
        except Exception as e:
            db.rollback()
            print(f"Error creating user: {e}")
            user = db.query(User).filter(User.username == DEFAULT_USER_USERNAME).first()
            if not user:
                print("Failed to create or find user. Aborting data population.")
                return
    else:
        print(f"User {user.username} found with ID {user.id}.")
        # Verify password and update if necessary
        try:
            # bcrypt.checkpw returns True if password matches, False otherwise
            if bcrypt.checkpw(DEFAULT_USER_PASSWORD.encode('utf-8'), user.hashed_password.encode('utf-8')):
                print(f"Password for existing user {user.username} matches the default.")
            else:
                print(f"Password for existing user {user.username} does not match the default. Updating password...")
                new_hashed_password = hash_password_bcrypt(DEFAULT_USER_PASSWORD)
                user.hashed_password = new_hashed_password
                try:
                    db.commit()
                    print(f"Password updated for user {user.username}.")
                except Exception as e_pw_update:
                    db.rollback()
                    print(f"Error updating password for user {user.username}: {e_pw_update}")
        except Exception as verify_exc: # Catch broad exception for bcrypt.checkpw if hash is malformed
            print(f"Could not verify password for existing user {user.username} (hash might be incompatible or malformed): {verify_exc}")
            print(f"Attempting to update password for user {user.username} due to verification issue...")
            try:
                new_hashed_password = hash_password_bcrypt(DEFAULT_USER_PASSWORD)
                user.hashed_password = new_hashed_password
                db.commit()
                print(f"Password forcefully updated for user {user.username} due to verification issue.")
            except Exception as e_pw_force_update:
                db.rollback()
                print(f"Error forcefully updating password for user {user.username}: {e_pw_force_update}")


    # --- Populate Ingredients ---
    if not db.query(Ingredient).filter(Ingredient.user_id == user.id).first():
        print("Populating ingredients...")
        for ing_data in DEFAULT_APP_DATA["ingredients"]:
            db.add(Ingredient(user_id=user.id, **ing_data))
    else:
        print("Default ingredients seem to exist. Skipping.")

    # --- Populate Employees ---
    employee_map_by_name = {}
    existing_employees = db.query(Employee).filter(Employee.user_id == user.id).all()
    if not existing_employees:
        print("Populating employees...")
        for emp_data in DEFAULT_APP_DATA["employees"]:
            employee = Employee(user_id=user.id, **emp_data)
            db.add(employee)
            db.flush()
            employee_map_by_name[employee.name] = employee
    else:
        print("Default employees seem to exist. Skipping population, but mapping existing ones.")
        for emp in existing_employees:
            employee_map_by_name[emp.name] = emp
    
    # --- Populate Standard Production Tasks ---
    std_prod_task_map_by_name = {}
    existing_std_prod_tasks = db.query(StandardProductionTask).filter(StandardProductionTask.user_id == user.id).all()
    if not existing_std_prod_tasks:
        print("Populating standard production tasks...")
        for task_data in DEFAULT_APP_DATA["standard_production_tasks"]:
            task = StandardProductionTask(user_id=user.id, **task_data)
            db.add(task)
            db.flush()
            std_prod_task_map_by_name[task.task_name] = task
    else:
        print("Std Production Tasks seem to exist. Skipping population, mapping existing.")
        for task in existing_std_prod_tasks:
            std_prod_task_map_by_name[task.task_name] = task

    # --- Populate Standard Shipping Tasks ---
    std_ship_task_map_by_name = {}
    existing_std_ship_tasks = db.query(StandardShippingTask).filter(StandardShippingTask.user_id == user.id).all()
    if not existing_std_ship_tasks:
        print("Populating standard shipping tasks...")
        for task_data in DEFAULT_APP_DATA["standard_shipping_tasks"]:
            task = StandardShippingTask(user_id=user.id, **task_data)
            db.add(task)
            db.flush()
            std_ship_task_map_by_name[task.task_name] = task
    else:
        print("Std Shipping Tasks seem to exist. Skipping population, mapping existing.")
        for task in existing_std_ship_tasks:
            std_ship_task_map_by_name[task.task_name] = task

    # --- Populate Global Costs ---
    if not db.query(GlobalCosts).filter(GlobalCosts.user_id == user.id).first():
        print("Populating global costs...")
        db.add(GlobalCosts(user_id=user.id, **DEFAULT_APP_DATA["global_costs"]))
    else:
        print("Global costs seem to exist. Skipping.")

    # --- Populate Global Salaries ---
    if not db.query(GlobalSalary).filter(GlobalSalary.user_id == user.id).first():
        print("Populating global salaries...")
        for sal_data in DEFAULT_APP_DATA["global_salaries"]:
            emp_name = sal_data["employee_name_ref"]
            if emp_name in employee_map_by_name:
                db.add(GlobalSalary(user_id=user.id, employee_id=employee_map_by_name[emp_name].id, monthly_amount=sal_data["monthly_amount"]))
            else:
                print(f"Warning: Employee '{emp_name}' not found for global salary. Skipping.")
    else:
        print("Global salaries seem to exist. Skipping.")

    # --- Populate Products and their components ---
    if not db.query(Product).filter(Product.user_id == user.id).first():
        print("Populating products and their components...")
        for prod_data_full in DEFAULT_APP_DATA["products"]:
            current_prod_data = prod_data_full.copy()
            materials_data = current_prod_data.pop("materials", [])
            prod_tasks_data = current_prod_data.pop("production_tasks", [])
            ship_tasks_data = current_prod_data.pop("shipping_tasks", [])
            salary_alloc_emp_name = current_prod_data.pop("salary_allocation_employee_name_ref", None)
            
            salary_alloc_emp_id = None
            if salary_alloc_emp_name and salary_alloc_emp_name in employee_map_by_name:
                salary_alloc_emp_id = employee_map_by_name[salary_alloc_emp_name].id

            product = Product(user_id=user.id, salary_allocation_employee_id=salary_alloc_emp_id, **current_prod_data)
            db.add(product)
            db.flush()

            for mat_data in materials_data:
                ing_name = mat_data["ingredient_name_ref"]
                ing_provider = mat_data.get("ingredient_provider_ref")
                ing_filters = [Ingredient.user_id == user.id, Ingredient.name == ing_name]
                if ing_provider: ing_filters.append(Ingredient.provider == ing_provider)
                else: ing_filters.append(Ingredient.provider.is_(None))
                ingredient_obj = db.query(Ingredient).filter(*ing_filters).first()
                if ingredient_obj:
                    db.add(ProductMaterial(product_id=product.id, ingredient_id=ingredient_obj.id, quantity_grams=mat_data["quantity_grams"]))
                else:
                    print(f"Warning: Ingredient '{ing_name}' (Provider: {ing_provider}) not found for product '{product.product_name}'. Skipping material.")

            for task_data in prod_tasks_data:
                std_task_name = task_data["task_name_ref"]
                emp_name = task_data["employee_name_ref"]
                std_task_obj = std_prod_task_map_by_name.get(std_task_name)
                emp_obj = employee_map_by_name.get(emp_name)
                if std_task_obj and emp_obj:
                    db.add(ProductProductionTask(product_id=product.id, standard_task_id=std_task_obj.id, employee_id=emp_obj.id, time_minutes=task_data["time_minutes"], items_processed_in_task=task_data["items_processed_in_task"]))
                else:
                    print(f"Warning: Standard prod task '{std_task_name}' or employee '{emp_name}' not found for product '{product.product_name}'. Skipping task.")
            
            for task_data in ship_tasks_data:
                std_task_name = task_data["task_name_ref"]
                emp_name = task_data["employee_name_ref"]
                std_task_obj = std_ship_task_map_by_name.get(std_task_name)
                emp_obj = employee_map_by_name.get(emp_name)
                if std_task_obj and emp_obj:
                    db.add(ProductShippingTask(product_id=product.id, standard_task_id=std_task_obj.id, employee_id=emp_obj.id, time_minutes=task_data["time_minutes"], items_processed_in_task=task_data["items_processed_in_task"]))
                else:
                    print(f"Warning: Standard ship task '{std_task_name}' or employee '{emp_name}' not found for product '{product.product_name}'. Skipping task.")
    else:
        print("Products seem to exist. Skipping.")

    try:
        db.commit()
        print("Default data committed successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error committing default data: {e}")
        raise

if __name__ == "__main__":
    db_url_display = os.environ.get("DATABASE_URL", "NOT SET")
    if "@" in db_url_display and db_url_display.count(':') > 1:
        parts = db_url_display.split(':')
        if len(parts) > 2 and "@" in parts[2]:
             db_url_display = f"{parts[0]}:***:{parts[2].split('@')[0]}@{parts[2].split('@')[-1]}"
        elif "@" in parts[1]:
             db_url_display = f"{parts[0]}:***@{parts[1].split('@')[-1]}"
        else:
            db_url_display = f"...@{db_url_display.split('@')[-1]}" if "@" in db_url_display else db_url_display
    elif "@" in db_url_display:
         db_url_display = f"...@{db_url_display.split('@')[-1]}"
    
    print(f"Starting database initialization using URL ending with: {db_url_display}")
    
    # Check if bcrypt is installed
    try:
        import bcrypt
    except ImportError:
        print("ERROR: The 'bcrypt' library is not installed. Please install it by running: pip install bcrypt")
        exit(1)

    confirmation = input(
        "This script will attempt to DROP ALL EXISTING TABLES and then recreate them "
        "based on models.py, then populate default data. "
        "THIS IS A DESTRUCTIVE OPERATION FOR EXISTING DATA. "
        "Are you absolutely sure you want to continue? (yes/no): "
    )

    if confirmation.lower() == 'yes':
        create_database_and_tables()
        
        db = SessionLocal()
        try:
            populate_default_data_for_user(db)
        finally:
            db.close()
        print("Database initialization process finished.")
    else:
        print("Database initialization aborted by user.")
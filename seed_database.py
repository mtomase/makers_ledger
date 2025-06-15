# seed_database.py

import datetime
import bcrypt
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text # ADDED: To execute raw SQL
import pathlib

from models import (
    Base, engine, SessionLocal, User, InventoryItem, Supplier, PurchaseOrder, StockAddition,
    Employee, Product, ProductMaterial, ProductionRun, BatchRecord, IngredientType,
    StandardProductionTask, StandardShippingTask, GlobalSalary, GlobalCosts,
    BatchIngredientUsage, ProductProductionTask, Customer, Invoice, InvoiceLineItem, InvoiceStatus,
    ExpenseCategory, Transaction, TransactionType, TransactionDocument,
    UserLayoutEnumDef
)
import yaml
from yaml.loader import SafeLoader
import os

print("--- Starting Comprehensive Database Seeding Script ---")

# --- Schema Reset ---
if input("This will delete ALL data from your database. Are you sure? (y/n): ").lower() == 'y':
    print("Dropping all tables using a robust method for Azure SQL...")
    
    # --- CHANGED: Implemented a more robust drop_all logic for Azure SQL ---
    with engine.connect() as connection:
        with connection.begin(): # Start a transaction for the whole process
            
            # Step 1: Discover all foreign key constraints in the database
            print("  - Step 1: Discovering all foreign key constraints...")
            # This query is specific to MS SQL Server / Azure SQL and gets the commands to drop all FKs
            fk_query = text("""
                SELECT 
                    'ALTER TABLE ' + QUOTENAME(OBJECT_SCHEMA_NAME(parent_object_id)) + '.' + QUOTENAME(OBJECT_NAME(parent_object_id)) + 
                    ' DROP CONSTRAINT ' + QUOTENAME(name)
                FROM sys.foreign_keys
            """)
            result = connection.execute(fk_query)
            drop_commands = [row[0] for row in result.fetchall()]

            # Step 2: Execute the drop commands for each constraint
            if drop_commands:
                print(f"  - Step 2: Dropping {len(drop_commands)} foreign key constraints...")
                for i, command in enumerate(drop_commands):
                    try:
                        connection.execute(text(command))
                        if (i + 1) % 10 == 0:
                            print(f"    ... dropped {i + 1}/{len(drop_commands)}")
                    except Exception as e:
                        print(f"    - Warning: Could not drop constraint with command: {command}. Error: {e}")
            else:
                print("  - Step 2: No foreign key constraints found to drop.")

            # Step 3: Now that constraints are gone, drop all tables
            print("  - Step 3: Dropping all tables...")
            Base.metadata.drop_all(bind=connection)

    print("Creating new tables...")
    Base.metadata.create_all(bind=engine)
    print("Schema reset complete.")
    # --- END CHANGED ---
else:
    print("Operation cancelled.")
    exit()

db: Session = SessionLocal()

try:
    print("\n--- Seeding Data ---")
    
    # --- 1. User ---
    print("Seeding All Users from config.yaml...")
    try:
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, 'config.yaml')
        with open(CONFIG_FILE_PATH, 'r') as file:
            config = yaml.load(file, Loader=SafeLoader)
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Could not read or parse config.yaml. Error: {e}"); exit()

    users_from_config = config.get('credentials', {}).get('usernames', {})
    if not users_from_config:
        print("❌ No users found in config.yaml."); exit()

    main_user_for_data = None 

    for username, user_details in users_from_config.items():
        user = db.query(User).filter(User.username == username).first()
        
        full_name = user_details.get('name')
        if not full_name:
            first = user_details.get('first_name', '')
            last = user_details.get('last_name', '')
            full_name = f"{first} {last}".strip()
        if not full_name:
            full_name = username

        if not user:
            new_user = User(
                username=username, 
                name=full_name,
                email=user_details['email'],
                hashed_password=user_details['password'], 
                country_code='IE', 
                layout_preference=UserLayoutEnumDef.WIDE,
                backup_retention_days=7 
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            print(f"  - User '{username}' created.")
            user = new_user
        else:
            user.name = full_name
            user.email = user_details['email']
            user.hashed_password = user_details['password']
            if not hasattr(user, 'backup_retention_days') or user.backup_retention_days is None:
                 user.backup_retention_days = 7
            db.commit()
            print(f"  - User '{username}' already exists and has been updated.")

        if main_user_for_data is None:
            main_user_for_data = user
    
    if main_user_for_data is None:
        print("❌ CRITICAL ERROR: No users were processed. Cannot seed sample data.")
        exit()

    main_user = main_user_for_data
    print(f"\n--- All subsequent sample data will be associated with user: '{main_user.username}' ---")

    # --- 2. Inventory Item Types ---
    print("\nSeeding Inventory Item Types...")
    db.query(IngredientType).filter(IngredientType.user_id == main_user.id).delete()
    db.commit()
    type_names = ["Oil/Fat/Butter", "Additive", "Lye", "Liquid", "Exfoliant", "Colorant", "Fragrance", "Packaging"]
    seeded_types = {}
    for name in type_names:
        db.add(IngredientType(user_id=main_user.id, name=name))
    db.commit()
    for itype in db.query(IngredientType).filter(IngredientType.user_id == main_user.id).all():
        seeded_types[itype.name] = itype
    print(f"  > {len(seeded_types)} types seeded.")

    # --- 3. Suppliers ---
    print("\nSeeding Suppliers...")
    db.query(Supplier).filter(Supplier.user_id == main_user.id).delete()
    db.commit()
    suppliers_data = [
        {'name': 'SoapSupplies Co.', 'contact_email': 'sales@soapsupplies.com'},
        {'name': 'BulkOils Inc.', 'website_url': 'https://bulkoils.com'},
        {'name': 'ChemDirect', 'phone_number': '555-CHEM-123'},
        {'name': 'Essential Oils Emporium', 'contact_email': 'aroma@eoe.com'},
        {'name': 'Packaging Pros', 'website_url': 'https://packpros.com'},
    ]
    seeded_suppliers = {}
    for sup_data in suppliers_data:
        db.add(Supplier(user_id=main_user.id, **sup_data))
    db.commit()
    for sup in db.query(Supplier).filter(Supplier.user_id == main_user.id).all():
        seeded_suppliers[sup.name] = sup
    print(f"  > {len(seeded_suppliers)} suppliers seeded.")

    # --- 4. Inventory Items ---
    print("\nSeeding Inventory Items (Ingredients & Packaging)...")
    db.query(InventoryItem).filter(InventoryItem.user_id == main_user.id).delete()
    db.commit()
    inventoryitems_data = [
        {'name': 'Coconut Oil', 'inventoryitem_type_id': seeded_types['Oil/Fat/Butter'].id, 'reorder_threshold_grams': 1000},
        {'name': 'Shea Butter', 'inventoryitem_type_id': seeded_types['Oil/Fat/Butter'].id, 'reorder_threshold_grams': 500},
        {'name': 'Sodium Hydroxide (Lye)', 'inventoryitem_type_id': seeded_types['Lye'].id},
        {'name': 'Lavender Essential Oil', 'inventoryitem_type_id': seeded_types['Fragrance'].id},
        {'name': 'Distilled Water', 'inventoryitem_type_id': seeded_types['Liquid'].id},
        {'name': 'Activated Charcoal', 'inventoryitem_type_id': seeded_types['Additive'].id},
        {'name': 'Kaolin Clay', 'inventoryitem_type_id': seeded_types['Additive'].id},
        {'name': 'Pink Himalayan Salt', 'inventoryitem_type_id': seeded_types['Exfoliant'].id},
        {'name': 'Cardboard Soap Box', 'inventoryitem_type_id': seeded_types['Packaging'].id, 'reorder_threshold_grams': 50},
        {'name': 'Logo Sticker (Round)', 'inventoryitem_type_id': seeded_types['Packaging'].id, 'reorder_threshold_grams': 100},
    ]
    seeded_inventoryitems = {}
    for item_data in inventoryitems_data:
        db.add(InventoryItem(user_id=main_user.id, **item_data))
    db.commit()
    for item in db.query(InventoryItem).filter(InventoryItem.user_id == main_user.id).all():
        seeded_inventoryitems[item.name] = item
    print(f"  > {len(seeded_inventoryitems)} inventory items seeded.")

    # --- 5. Employees ---
    print("\nSeeding Employees...")
    db.query(Employee).filter(Employee.user_id == main_user.id).delete()
    db.commit()
    emp_maker = Employee(user_id=main_user.id, name='John Maker', hourly_rate=Decimal('20.00'), role='Soap Maker')
    emp_packer = Employee(user_id=main_user.id, name='Sarah Packer', hourly_rate=Decimal('16.50'), role='Shipping Clerk')
    emp_manager = Employee(user_id=main_user.id, name='Admin Alex', hourly_rate=Decimal('0.00'), role='Manager')
    emp_marketer = Employee(user_id=main_user.id, name='Marketing Mary', hourly_rate=Decimal('0.00'), role='Marketing Manager')
    db.add_all([emp_maker, emp_packer, emp_manager, emp_marketer]); db.commit()
    print("  > 4 employees seeded.")

    # --- 6. Global Costs & Salaries ---
    print("\nSeeding Global Costs & Salaries...")
    db.query(GlobalSalary).filter(GlobalSalary.user_id == main_user.id).delete()
    db.query(GlobalCosts).filter(GlobalCosts.user_id == main_user.id).delete()
    db.commit()
    db.add(GlobalSalary(user_id=main_user.id, employee_id=emp_manager.id, monthly_amount=Decimal('4000.00')))
    db.add(GlobalSalary(user_id=main_user.id, employee_id=emp_marketer.id, monthly_amount=Decimal('3500.00')))
    db.add(GlobalCosts(user_id=main_user.id, monthly_rent=Decimal('1200.00'), monthly_utilities=Decimal('350.00')))
    db.commit()
    print("  > Global costs and 2 global salaries seeded.")

    # --- 7. Standard Tasks ---
    print("\nSeeding Standard Tasks...")
    db.query(StandardProductionTask).filter(StandardProductionTask.user_id == main_user.id).delete()
    db.query(StandardShippingTask).filter(StandardShippingTask.user_id == main_user.id).delete()
    db.commit()
    prod_tasks = ["Weigh Oils", "Mix Lye Solution", "Blend & Pour", "Cut Soap", "Cure Bars"]
    ship_tasks = ["Print Shipping Label", "Package Items", "Schedule Pickup"]
    for task_name in prod_tasks: db.add(StandardProductionTask(user_id=main_user.id, task_name=task_name))
    for task_name in ship_tasks: db.add(StandardShippingTask(user_id=main_user.id, task_name=task_name))
    db.commit()
    print(f"  > {len(prod_tasks)} production and {len(ship_tasks)} shipping tasks seeded.")

    # --- 8. Purchase Orders and Stock Additions ---
    print("\nSeeding Purchases and Stock Lots...")
    po1 = PurchaseOrder(user_id=main_user.id, supplier_id=seeded_suppliers['SoapSupplies Co.'].id, order_date=datetime.date(2024, 5, 10), shipping_cost=Decimal('25.00'))
    po2 = PurchaseOrder(user_id=main_user.id, supplier_id=seeded_suppliers['ChemDirect'].id, order_date=datetime.date(2024, 5, 20), shipping_cost=Decimal('7.50'))
    po3 = PurchaseOrder(user_id=main_user.id, supplier_id=seeded_suppliers['Essential Oils Emporium'].id, order_date=datetime.date(2024, 6, 1), shipping_cost=Decimal('12.00'))
    po4 = PurchaseOrder(user_id=main_user.id, supplier_id=seeded_suppliers['BulkOils Inc.'].id, order_date=datetime.date(2024, 6, 5), shipping_cost=Decimal('30.00'))
    po5 = PurchaseOrder(user_id=main_user.id, supplier_id=seeded_suppliers['Packaging Pros'].id, order_date=datetime.date(2024, 6, 7), shipping_cost=Decimal('15.00'))
    db.add_all([po1, po2, po3, po4, po5]); db.flush()
    
    s1 = StockAddition(purchase_order_id=po1.id, inventoryitem_id=seeded_inventoryitems['Coconut Oil'].id, quantity_added_grams=5000, quantity_remaining_grams=5000, item_cost=40, vat_amount=9.2, supplier_lot_number='SSC-CO-01')
    s2 = StockAddition(purchase_order_id=po1.id, inventoryitem_id=seeded_inventoryitems['Shea Butter'].id, quantity_added_grams=2000, quantity_remaining_grams=2000, item_cost=55, vat_amount=12.65, supplier_lot_number='SSC-SB-01')
    s3 = StockAddition(purchase_order_id=po2.id, inventoryitem_id=seeded_inventoryitems['Sodium Hydroxide (Lye)'].id, quantity_added_grams=1000, quantity_remaining_grams=1000, item_cost=15, vat_amount=3.45, supplier_lot_number='CD-SH-01')
    s4 = StockAddition(purchase_order_id=po3.id, inventoryitem_id=seeded_inventoryitems['Lavender Essential Oil'].id, quantity_added_grams=500, quantity_remaining_grams=500, item_cost=80, vat_amount=18.4, supplier_lot_number='EOE-LAV-01')
    s5 = StockAddition(purchase_order_id=po4.id, inventoryitem_id=seeded_inventoryitems['Kaolin Clay'].id, quantity_added_grams=1000, quantity_remaining_grams=1000, item_cost=25, vat_amount=5.75, supplier_lot_number='BO-KC-01')
    s6 = StockAddition(purchase_order_id=po4.id, inventoryitem_id=seeded_inventoryitems['Activated Charcoal'].id, quantity_added_grams=500, quantity_remaining_grams=500, item_cost=30, vat_amount=6.9, supplier_lot_number='BO-AC-01')
    s7 = StockAddition(purchase_order_id=po5.id, inventoryitem_id=seeded_inventoryitems['Cardboard Soap Box'].id, quantity_added_grams=200, quantity_remaining_grams=200, item_cost=50, vat_amount=11.5, supplier_lot_number='PP-BOX-01')
    s8 = StockAddition(purchase_order_id=po5.id, inventoryitem_id=seeded_inventoryitems['Logo Sticker (Round)'].id, quantity_added_grams=500, quantity_remaining_grams=500, item_cost=20, vat_amount=4.6, supplier_lot_number='PP-STICK-01')
    db.add_all([s1, s2, s3, s4, s5, s6, s7, s8]); db.commit()
    print(f"  > 5 POs with {db.query(StockAddition).count()} stock lots seeded.")

    # --- 9. Products with Recipes & Workflows ---
    print("\nSeeding Products, Recipes, and Workflows...")
    db.query(Product).filter(Product.user_id == main_user.id).delete()
    db.commit()
    prod1 = Product(user_id=main_user.id, product_name="Lavender Bliss Soap Bar", product_code="LAV-001", retail_price_per_item=8.50)
    prod2 = Product(user_id=main_user.id, product_name="Charcoal Detox Bar", product_code="CHA-001", retail_price_per_item=9.00)
    prod3 = Product(user_id=main_user.id, product_name="Himalayan Salt Scrub", product_code="SAL-001", retail_price_per_item=12.50)
    db.add_all([prod1, prod2, prod3]); db.commit()
    db.add_all([
        ProductMaterial(product_id=prod1.id, inventoryitem_id=seeded_inventoryitems['Coconut Oil'].id, quantity_grams=40),
        ProductMaterial(product_id=prod1.id, inventoryitem_id=seeded_inventoryitems['Shea Butter'].id, quantity_grams=30),
        ProductMaterial(product_id=prod1.id, inventoryitem_id=seeded_inventoryitems['Sodium Hydroxide (Lye)'].id, quantity_grams=12),
        ProductMaterial(product_id=prod1.id, inventoryitem_id=seeded_inventoryitems['Lavender Essential Oil'].id, quantity_grams=5),
        ProductMaterial(product_id=prod1.id, inventoryitem_id=seeded_inventoryitems['Cardboard Soap Box'].id, quantity_grams=1),
        ProductMaterial(product_id=prod1.id, inventoryitem_id=seeded_inventoryitems['Logo Sticker (Round)'].id, quantity_grams=1),
        ProductMaterial(product_id=prod2.id, inventoryitem_id=seeded_inventoryitems['Coconut Oil'].id, quantity_grams=50),
        ProductMaterial(product_id=prod2.id, inventoryitem_id=seeded_inventoryitems['Sodium Hydroxide (Lye)'].id, quantity_grams=15),
        ProductMaterial(product_id=prod2.id, inventoryitem_id=seeded_inventoryitems['Activated Charcoal'].id, quantity_grams=10),
        ProductMaterial(product_id=prod2.id, inventoryitem_id=seeded_inventoryitems['Cardboard Soap Box'].id, quantity_grams=1),
        ProductMaterial(product_id=prod2.id, inventoryitem_id=seeded_inventoryitems['Logo Sticker (Round)'].id, quantity_grams=1),
    ]); db.commit()
    print(f"  > 3 products with recipes (including packaging) seeded.")

    # --- 10. Production Runs & Batches ---
    print("\nSeeding Production Runs and Batches...")
    run1 = ProductionRun(user_id=main_user.id, product_id=prod1.id, planned_batch_count=1, notes="Initial test run")
    run2 = ProductionRun(user_id=main_user.id, product_id=prod2.id, planned_batch_count=2, notes="First full run of charcoal soap")
    db.add_all([run1, run2]); db.flush()
    b1 = BatchRecord(production_run_id=run1.id, user_id=main_user.id, batch_code="LAV-001-240610-01", person_responsible_id=emp_maker.id, manufacturing_date=datetime.date.today(), bars_in_batch=12)
    b2 = BatchRecord(production_run_id=run2.id, user_id=main_user.id, batch_code="CHA-001-240611-01", person_responsible_id=emp_maker.id, manufacturing_date=datetime.date.today(), bars_in_batch=12)
    b3 = BatchRecord(production_run_id=run2.id, user_id=main_user.id, batch_code="CHA-001-240611-02", person_responsible_id=emp_maker.id, manufacturing_date=datetime.date.today(), bars_in_batch=12)
    db.add_all([b1, b2, b3]); db.flush()
    db.add_all([
        BatchIngredientUsage(batch_record_id=b1.id, stock_addition_id=s1.id, inventoryitem_id=s1.inventoryitem_id, quantity_used_grams=40),
        BatchIngredientUsage(batch_record_id=b1.id, stock_addition_id=s2.id, inventoryitem_id=s2.inventoryitem_id, quantity_used_grams=30),
        BatchIngredientUsage(batch_record_id=b2.id, stock_addition_id=s1.id, inventoryitem_id=s1.inventoryitem_id, quantity_used_grams=50),
        BatchIngredientUsage(batch_record_id=b2.id, stock_addition_id=s6.id, inventoryitem_id=s6.inventoryitem_id, quantity_used_grams=10),
    ]); db.commit()
    print(f"  > 2 runs with 3 batches and traceability seeded.")

    # --- 11. Customers & Invoices ---
    print("\nSeeding Customers and Invoices...")
    db.query(Customer).filter(Customer.user_id == main_user.id).delete()
    db.commit()
    c1 = Customer(user_id=main_user.id, name='The Corner Cafe', vat_number='IE1234567T')
    c2 = Customer(user_id=main_user.id, name='Boutique Blooms', address='123 Floral Lane, Dublin')
    c3 = Customer(user_id=main_user.id, name='The Health Hub', contact_email='orders@healthhub.ie')
    c4 = Customer(user_id=main_user.id, name='Gifts & More')
    c5 = Customer(user_id=main_user.id, name='Jane Doe (Online)', address='45 Online Avenue')
    db.add_all([c1, c2, c3, c4, c5]); db.commit()
    
    inv1 = Invoice(user_id=main_user.id, customer_id=c1.id, invoice_number="INV-0001", invoice_date=datetime.date.today() - datetime.timedelta(days=30), status=InvoiceStatus.PAID)
    inv2 = Invoice(user_id=main_user.id, customer_id=c2.id, invoice_number="INV-0002", invoice_date=datetime.date.today() - datetime.timedelta(days=10), status=InvoiceStatus.SENT)
    inv3 = Invoice(user_id=main_user.id, customer_id=c3.id, invoice_number="INV-0003", invoice_date=datetime.date.today(), status=InvoiceStatus.DRAFT)
    inv4 = Invoice(user_id=main_user.id, customer_id=c5.id, invoice_number="INV-0004", invoice_date=datetime.date.today() - datetime.timedelta(days=5), status=InvoiceStatus.PAID)
    db.add_all([inv1, inv2, inv3, inv4]); db.flush()
    db.add(InvoiceLineItem(invoice_id=inv1.id, product_id=prod1.id, quantity=20, unit_price=4.25, line_total=85, description=prod1.product_name))
    db.add(InvoiceLineItem(invoice_id=inv2.id, product_id=prod2.id, quantity=15, unit_price=4.50, line_total=67.5, description=prod2.product_name))
    db.add(InvoiceLineItem(invoice_id=inv3.id, product_id=prod1.id, quantity=10, unit_price=4.25, line_total=42.5, description=prod1.product_name))
    db.add(InvoiceLineItem(invoice_id=inv4.id, product_id=prod2.id, quantity=2, unit_price=9.00, line_total=18.00, description=prod2.product_name))
    db.commit()
    print(f"  > 5 customers and 4 invoices seeded.")

    # --- 12. Expense Categories & Transactions ---
    print("\nSeeding Expense Categories and Transactions...")
    db.query(ExpenseCategory).filter(ExpenseCategory.user_id == main_user.id).delete()
    db.commit()
    exp_cat_names = ['Materials', 'Stationary', 'Phones', 'Advertising', 'Light & Heat', 'Rent & Rates', 'Misc', 'Capital']
    seeded_exp_cats = {}
    for name in exp_cat_names: db.add(ExpenseCategory(user_id=main_user.id, name=name))
    db.commit()
    for cat in db.query(ExpenseCategory).filter(ExpenseCategory.user_id == main_user.id).all():
        seeded_exp_cats[cat.name] = cat
    
    t1 = Transaction(user_id=main_user.id, date=inv1.invoice_date, description=f"Payment for {inv1.invoice_number}", amount=inv1.total_amount, transaction_type=TransactionType.SALE, customer_id=c1.id)
    t2 = Transaction(user_id=main_user.id, date=po1.order_date, description=f"Payment to {seeded_suppliers['SoapSupplies Co.'].name}", amount=100, transaction_type=TransactionType.EXPENSE, category_id=seeded_exp_cats['Materials'].id, supplier_id=po1.supplier_id)
    t3 = Transaction(user_id=main_user.id, date=datetime.date.today() - datetime.timedelta(days=10), description="Owner Drawings", amount=500, transaction_type=TransactionType.DRAWING)
    t4 = Transaction(user_id=main_user.id, date=datetime.date.today() - datetime.timedelta(days=5), description="Phone Bill", amount=60, transaction_type=TransactionType.EXPENSE, category_id=seeded_exp_cats['Phones'].id)
    t5_with_doc = Transaction(user_id=main_user.id, date=datetime.date.today() - datetime.timedelta(days=3), description="Facebook Ads", amount=150, transaction_type=TransactionType.EXPENSE, category_id=seeded_exp_cats['Advertising'].id)
    db.add_all([t1, t2, t3, t4, t5_with_doc]); db.flush()

    save_dir = pathlib.Path(f"uploaded_files/transactions/{main_user.id}/{t5_with_doc.id}")
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / "sample_receipt.txt"
    with open(file_path, "w") as f:
        f.write(f"This is a sample receipt for transaction ID {t5_with_doc.id}.\n")
        f.write(f"Amount: {t5_with_doc.amount}\nDate: {t5_with_doc.date}")
    
    doc = TransactionDocument(transaction_id=t5_with_doc.id, file_path=str(file_path), original_filename="sample_receipt.txt")
    db.add(doc); db.commit()
    print(f"  > 5 transactions seeded, with one sample document attached.")

    print("\n\n✅ --- Seeding Complete! --- ✅")
    print("Your database has been successfully populated. You can now run the main application.")

except Exception as e:
    print(f"\n❌ AN ERROR OCCURRED DURING SEEDING: {e}")
    import traceback
    traceback.print_exc()

finally:
    db.close()
    print("Database session closed.")
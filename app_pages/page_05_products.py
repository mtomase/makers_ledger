# app_pages/page_05_products.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session, selectinload, joinedload
from decimal import Decimal

from models import (
    User, Product, Ingredient, Employee, StandardProductionTask, StandardShippingTask,
    ProductMaterial, ProductProductionTask, ProductShippingTask
)
from utils.db_helpers import get_all_for_user, create_ingredient_display_string

def render(db: Session, user: User, is_mobile: bool):
    st.header("📦 Manage Products")
    
    # Product Selection
    products = get_all_for_user(db, Product, user.id, order_by_col=Product.product_name)
    product_options = {p.product_name: p.id for p in products}
    
    selected_product_name = st.selectbox(
        "Select a Product to View/Edit, or Add a New One",
        options=[None] + list(product_options.keys()),
        format_func=lambda x: "✨ Add New Product" if x is None else x,
        key="product_selector"
    )
    
    if selected_product_name:
        st.session_state.selected_product_id = product_options[selected_product_name]
    
    if st.session_state.get("selected_product_id"):
        render_product_detail_manager(db, user, is_mobile)

    elif selected_product_name is None:
        st.session_state.selected_product_id = None
        render_add_new_product(db, user)

def render_add_new_product(db: Session, user: User):
    st.subheader("Add New Product")
    with st.form("new_product_form"):
        new_product_name = st.text_input("New Product Name*")
        submitted = st.form_submit_button("Create New Product", type="primary")
        if submitted:
            if not new_product_name:
                st.error("Product name is required.")
            else:
                try:
                    new_product = Product(user_id=user.id, product_name=new_product_name)
                    db.add(new_product)
                    db.commit()
                    st.success(f"Product '{new_product_name}' created successfully!")
                    st.session_state.selected_product_id = new_product.id
                    st.rerun()
                except Exception as e:
                    db.rollback()
                    st.error(f"Error creating product. Does a product with this name already exist? Details: {e}")

def render_product_detail_manager(db: Session, user: User, is_mobile: bool):
    product_id = st.session_state.selected_product_id
    product = db.query(Product).options(
        selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref),
        selectinload(Product.production_tasks),
        selectinload(Product.shipping_tasks)
    ).filter(Product.id == product_id).first()

    if not product:
        st.error("Product not found. Please select another product.")
        st.session_state.selected_product_id = None
        return

    st.subheader(f"Editing: {product.product_name}")

    # --- NEW: Production Simulation Section ---
    st.markdown("---")
    st.subheader("🏭 Simulate Production Run")
    st.write("Calculate required ingredients for a production run and deduct them from your inventory.")

    with st.form("production_run_form"):
        batches_to_produce = st.number_input("Number of Batches to Produce", min_value=1, value=1, step=1)
        run_production_submitted = st.form_submit_button("Check Stock & Run Production", type="primary")

        if run_production_submitted:
            required_ingredients = {}
            for material in product.materials:
                total_needed = material.quantity_grams * batches_to_produce
                if material.ingredient_id not in required_ingredients:
                    required_ingredients[material.ingredient_id] = {'needed': Decimal('0'), 'name': material.ingredient_ref.name}
                required_ingredients[material.ingredient_id]['needed'] += total_needed

            # Check stock levels
            ingredients_to_check_ids = list(required_ingredients.keys())
            ingredients_in_db = db.query(Ingredient).filter(Ingredient.id.in_(ingredients_to_check_ids)).all()
            
            stock_ok = True
            error_messages = []
            
            for ing_db in ingredients_in_db:
                needed = required_ingredients[ing_db.id]['needed']
                if ing_db.current_stock_grams < needed:
                    stock_ok = False
                    shortfall = needed - ing_db.current_stock_grams
                    error_messages.append(f"  - **{ing_db.name}**: Needed: {needed:,.2f}g, Have: {ing_db.current_stock_grams:,.2f}g (Short by **{shortfall:,.2f}g**)")

            if stock_ok:
                try:
                    # Deduct stock
                    for ing_db in ingredients_in_db:
                        ing_db.current_stock_grams -= required_ingredients[ing_db.id]['needed']
                    
                    db.commit()
                    st.success(f"✅ Production run successful! Stock for {len(ingredients_in_db)} ingredients has been deducted.")
                    # We don't rerun here to allow user to see the success message clearly
                except Exception as e:
                    db.rollback()
                    st.error(f"An error occurred during stock deduction: {e}")
            else:
                st.error("❌ Insufficient stock for production run. Please purchase more of the following ingredients:")
                for msg in error_messages:
                    st.markdown(msg)

    st.markdown("---")
    # --- END: Production Simulation Section ---


    # --- Existing Product Management Tabs ---
    tab_titles = ["Recipe / Materials", "Production Tasks", "Shipping Tasks", "Pricing & Costs"]
    tabs = st.tabs(tab_titles)

    with tabs[0]:
        render_materials_tab(db, user, product)
    with tabs[1]:
        render_production_tasks_tab(db, user, product)
    with tabs[2]:
        render_shipping_tasks_tab(db, user, product)
    with tabs[3]:
        render_pricing_tab(db, user, product)

# ... (The rest of the functions: render_materials_tab, render_production_tasks_tab, etc. remain the same) ...
def render_materials_tab(db: Session, user: User, product: Product):
    st.subheader("Recipe / Materials")
    st.write("Define the ingredients and quantities (in grams) required for one batch of this product.")
    
    all_ingredients = get_all_for_user(db, Ingredient, user.id, order_by_col=Ingredient.name)
    ingredient_options = {create_ingredient_display_string(ing.name, ing.provider): ing.id for ing in all_ingredients}
    
    materials_data = [
        {"ID": mat.id, "Ingredient ID": mat.ingredient_id, "Quantity (grams)": mat.quantity_grams}
        for mat in product.materials
    ]
    materials_df = pd.DataFrame(materials_data)

    edited_materials_df = st.data_editor(
        materials_df,
        num_rows="dynamic",
        key="materials_editor",
        column_config={
            "ID": None,
            "Ingredient ID": st.column_config.SelectboxColumn(
                "Ingredient*",
                options=list(ingredient_options.values()),
                format_func=lambda ing_id: next((k for k, v in ingredient_options.items() if v == ing_id), "Unknown"),
                required=True,
            ),
            "Quantity (grams)": st.column_config.NumberColumn("Quantity (grams)*", min_value=0.0, required=True)
        },
        use_container_width=True,
        hide_index=True
    )

    if st.button("Save Recipe Changes", type="primary", key="save_materials"):
        try:
            # Handle deletions
            original_ids = set(materials_df['ID'].dropna())
            edited_ids = set(edited_materials_df['ID'].dropna())
            ids_to_delete = original_ids - edited_ids
            if ids_to_delete:
                db.query(ProductMaterial).filter(ProductMaterial.id.in_(ids_to_delete)).delete(synchronize_session=False)

            # Handle additions and updates
            for _, row in edited_materials_df.iterrows():
                mat_id = row.get('ID')
                ing_id = row.get('Ingredient ID')
                quantity = row.get('Quantity (grams)')
                
                if not ing_id or quantity is None:
                    st.warning("Skipping row with missing Ingredient or Quantity.")
                    continue

                if pd.isna(mat_id): # New row
                    new_material = ProductMaterial(product_id=product.id, ingredient_id=ing_id, quantity_grams=Decimal(str(quantity)))
                    db.add(new_material)
                else: # Existing row
                    material_to_update = db.query(ProductMaterial).filter(ProductMaterial.id == mat_id).first()
                    if material_to_update:
                        material_to_update.ingredient_id = ing_id
                        material_to_update.quantity_grams = Decimal(str(quantity))
            
            db.commit()
            st.success("Recipe saved successfully!")
            st.rerun()
        except Exception as e:
            db.rollback()
            st.error(f"Error saving recipe. Do you have duplicate ingredients? Details: {e}")

def render_tasks_tab_factory(task_type, standard_task_model, product_task_model, product_relationship_name):
    def render_tab(db: Session, user: User, product: Product):
        st.subheader(f"{task_type} Tasks")
        st.write(f"Define the {task_type.lower()} tasks and time required for one batch of this product.")

        all_employees = get_all_for_user(db, Employee, user.id, order_by_col=Employee.name)
        employee_options = {emp.name: emp.id for emp in all_employees}
        
        all_standard_tasks = get_all_for_user(db, standard_task_model, user.id, order_by_col=standard_task_model.task_name)
        task_options = {task.task_name: task.id for task in all_standard_tasks}

        tasks_data = [
            {
                "ID": task.id,
                "Task ID": task.standard_task_id,
                "Employee ID": task.employee_id,
                "Time (minutes)": task.time_minutes,
                "Items Processed": task.items_processed_in_task
            }
            for task in getattr(product, product_relationship_name)
        ]
        tasks_df = pd.DataFrame(tasks_data)

        edited_tasks_df = st.data_editor(
            tasks_df,
            num_rows="dynamic",
            key=f"{task_type}_tasks_editor",
            column_config={
                "ID": None,
                "Task ID": st.column_config.SelectboxColumn(
                    "Task*",
                    options=list(task_options.values()),
                    format_func=lambda task_id: next((k for k, v in task_options.items() if v == task_id), "Unknown"),
                    required=True,
                ),
                "Employee ID": st.column_config.SelectboxColumn(
                    "Employee (Optional)",
                    options=[None] + list(employee_options.values()),
                    format_func=lambda emp_id: "N/A" if emp_id is None else next((k for k, v in employee_options.items() if v == emp_id), "Unknown"),
                ),
                "Time (minutes)": st.column_config.NumberColumn("Time (minutes)*", min_value=0.0, required=True),
                "Items Processed": st.column_config.NumberColumn("Items Processed in this Time*", min_value=1, step=1, required=True)
            },
            use_container_width=True,
            hide_index=True
        )

        if st.button(f"Save {task_type} Task Changes", type="primary", key=f"save_{task_type}_tasks"):
            try:
                original_ids = set(tasks_df['ID'].dropna())
                edited_ids = set(edited_tasks_df['ID'].dropna())
                ids_to_delete = original_ids - edited_ids
                if ids_to_delete:
                    db.query(product_task_model).filter(product_task_model.id.in_(ids_to_delete)).delete(synchronize_session=False)

                for _, row in edited_tasks_df.iterrows():
                    task_instance_id = row.get('ID')
                    std_task_id = row.get('Task ID')
                    emp_id = row.get('Employee ID')
                    time_min = row.get('Time (minutes)')
                    items_proc = row.get('Items Processed')

                    if not std_task_id or time_min is None or items_proc is None:
                        st.warning("Skipping row with missing Task, Time, or Items Processed.")
                        continue

                    if pd.isna(task_instance_id): # New
                        new_task = product_task_model(
                            product_id=product.id, standard_task_id=std_task_id, employee_id=emp_id,
                            time_minutes=Decimal(str(time_min)), items_processed_in_task=items_proc
                        )
                        db.add(new_task)
                    else: # Update
                        task_to_update = db.query(product_task_model).filter(product_task_model.id == task_instance_id).first()
                        if task_to_update:
                            task_to_update.standard_task_id = std_task_id
                            task_to_update.employee_id = emp_id
                            task_to_update.time_minutes = Decimal(str(time_min))
                            task_to_update.items_processed_in_task = items_proc
                
                db.commit()
                st.success(f"{task_type} tasks saved successfully!")
                st.rerun()
            except Exception as e:
                db.rollback()
                st.error(f"Error saving {task_type.lower()} tasks. Details: {e}")
    return render_tab

render_production_tasks_tab = render_tasks_tab_factory("Production", StandardProductionTask, ProductProductionTask, "production_tasks")
render_shipping_tasks_tab = render_tasks_tab_factory("Shipping", StandardShippingTask, ProductShippingTask, "shipping_tasks")

def render_pricing_tab(db: Session, user: User, product: Product):
    st.subheader("Pricing & Costs")
    st.write("Configure general costs, pricing, and allocation settings for this specific product.")
    
    with st.form("pricing_form"):
        st.write("##### General Product Settings")
        c1, c2 = st.columns(2)
        product.batch_size_items = c1.number_input("Items per Batch", min_value=1, value=product.batch_size_items or 100, step=10)
        product.monthly_production_items = c2.number_input("Target Monthly Production (Items)", min_value=1, value=product.monthly_production_items or 1000, step=100)
        
        st.write("##### Final Pricing")
        c1, c2, c3 = st.columns(3)
        product.retail_price_per_item = c1.number_input("Retail Price per Item (€)", min_value=0.0, value=float(product.retail_price_per_item or 10.0), format="%.2f")
        product.wholesale_price_per_item = c2.number_input("Wholesale Price per Item (€)", min_value=0.0, value=float(product.wholesale_price_per_item or 5.0), format="%.2f")
        product.buffer_percentage = c3.number_input("Contingency Buffer (%)", min_value=0.0, max_value=100.0, value=float((product.buffer_percentage or Decimal('0.1')) * 100), format="%.2f") / 100.0
        
        submitted = st.form_submit_button("Save Pricing & Cost Settings", type="primary")
        if submitted:
            try:
                db.commit()
                st.success("Settings saved successfully!")
                st.rerun()
            except Exception as e:
                db.rollback()
                st.error(f"Error saving settings: {e}")
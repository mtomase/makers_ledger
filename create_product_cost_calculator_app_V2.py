# app.py
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import os
import pandas as pd
import numpy as np
# import json # No longer needed for primary data storage
from datetime import datetime
import re
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

# --- Authentication & DB Imports ---
from models import (
    init_db_structure, get_db, User, UserLayout,
    Ingredient, Employee, StandardProductionTask, StandardShippingTask,
    GlobalCosts, GlobalSalary, Product, ProductMaterial,
    ProductProductionTask, ProductShippingTask
)
from auth_utils import get_or_create_db_user

# --- Initialize Database Structure (from models.py) ---
# This should ideally run once. models.py's init_db_structure handles table creation.
if 'db_structure_initialized' not in st.session_state:
    try:
        # init_db_structure() # This creates tables. Run it manually via models.py or db_setup.py first.
        # For the app, we just need to ensure the engine is ready.
        # The init_db_structure() call is more for a setup phase.
        # If you run this in app.py, ensure it's idempotent and safe.
        # For Render, the tables should be created by db_setup.py or a migration tool.
        st.session_state.db_structure_initialized = True # Assume tables exist
        print("Database structure assumed to be initialized.")
    except Exception as e:
        st.error(f"Critical error related to database structure: {e}")
        st.stop()

# --- Load streamlit-authenticator Configuration from YAML ---
# (This part remains the same as before)
try:
    with open('config.yaml', 'r') as file:
        config_auth = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("CRITICAL ERROR: config.yaml not found.")
    st.stop()
except yaml.YAMLError as e:
    st.error(f"CRITICAL ERROR: Could not parse config.yaml: {e}")
    st.stop()
except Exception as e:
    st.error(f"CRITICAL ERROR: An unexpected error occurred loading config.yaml: {e}")
    st.stop()

# --- Initialize Authenticator ---
authenticator = stauth.Authenticate(
    config_auth['credentials'],
    config_auth['cookie']['name'],
    config_auth['cookie']['key'],
    config_auth['cookie']['expiry_days'],
    config_auth.get('preauthorized')
)

# --- Render Login Form and Handle Authentication ---
name, authentication_status, username = authenticator.login('Login', 'main')

# --- Helper function to get a DB session (context manager might be better in long run) ---
def get_db_session():
    db = next(get_db())
    return db

# --- Conditional Page Config and App Logic ---
if authentication_status is False:
    # ... (login page config and error message as before) ...
    if 'page_config_set' not in st.session_state or not st.session_state.page_config_set == "login":
        try:
            st.set_page_config(page_title="Login - PCC", layout="centered", initial_sidebar_state="collapsed")
            st.session_state.page_config_set = "login"
        except st.errors.StreamlitAPIException as e:
            if "st.set_page_config() has already been called" not in str(e): raise e
    st.error('Username/password is incorrect')


elif authentication_status is None:
    # ... (login page config and warning message as before) ...
    if 'page_config_set' not in st.session_state or not st.session_state.page_config_set == "login":
        try:
            st.set_page_config(page_title="Login - PCC", layout="centered", initial_sidebar_state="collapsed")
            st.session_state.page_config_set = "login"
        except st.errors.StreamlitAPIException as e:
            if "st.set_page_config() has already been called" not in str(e): raise e
    st.warning('Please enter your username and password')
    if st.checkbox("New user? Register here"):
        try:
            if authenticator.register_user('Register user', preauthorization=False):
                st.success('User registered successfully! Please login.')
        except Exception as e:
            st.error(f"Registration error: {e}")


elif authentication_status:
    # --- User is Authenticated ---
    st.session_state.username = username
    st.session_state.name = name

    db = get_db_session() # Get a database session for this authenticated block
    try:
        user_email_from_config = config_auth["credentials"]["usernames"].get(st.session_state["username"], {}).get("email", f"{st.session_state.username}@example.com")
        db_user = get_or_create_db_user(
            db=db,
            username=st.session_state["username"],
            email=user_email_from_config,
            name=st.session_state["name"]
        )
        st.session_state.user_id = db_user.id
        st.session_state.user_layout = db_user.layout_preference.value
        st.session_state.db_user_object = db_user

        # --- Set Page Config for Authenticated User ---
        if 'page_config_set' not in st.session_state or not st.session_state.page_config_set == "user_app":
            try:
                st.set_page_config(
                    page_title="Product Cost Calculator",
                    page_icon="🏭",
                    layout=st.session_state.user_layout,
                    initial_sidebar_state="expanded"
                )
                st.session_state.page_config_set = "user_app"
                st.rerun()
            except st.errors.StreamlitAPIException as e:
                if "st.set_page_config() has already been called" not in str(e):
                    st.warning(f"Could not set page config for user: {e}. Using defaults.")
                st.session_state.page_config_set = "user_app"

        # --- Application Logic (Now using Database) ---

        # --- Sidebar for Authenticated User ---
        st.sidebar.title(f"Welcome *{st.session_state['name']}*")
        st.sidebar.caption(f"(User ID: {st.session_state.user_id})")
        authenticator.logout('Logout', 'sidebar')
        st.sidebar.markdown("---")

        st.sidebar.header("Navigation")
        app_mode = st.sidebar.radio("Choose a section:", ["Manage Products", "Manage Global Data", "Tutorial"])

        # Layout Preference (from DB)
        layout_options_enum = [layout.value for layout in UserLayout]
        try:
            current_layout_index_db = layout_options_enum.index(st.session_state.user_layout)
        except ValueError:
            current_layout_index_db = 0
        new_layout_str_db = st.sidebar.selectbox(
            "Set Page Layout:", options=layout_options_enum, index=current_layout_index_db, key="user_layout_selector_db"
        )
        if new_layout_str_db != st.session_state.user_layout:
            if st.sidebar.button("Apply Layout Change", key="apply_layout_btn_db"):
                try:
                    user_to_update = db.query(User).filter(User.id == st.session_state.user_id).first()
                    if user_to_update:
                        user_to_update.layout_preference = UserLayout(new_layout_str_db)
                        db.commit()
                        st.session_state.user_layout = new_layout_str_db
                        st.session_state.page_config_set = None
                        st.success("Layout preference updated! Rerunning...")
                        st.rerun()
                except SQLAlchemyError as e_layout_db:
                    db.rollback(); st.error(f"DB Error updating layout: {e_layout_db}")
        st.sidebar.markdown("---")

        # --- Main Application Title ---
        st.title("📦 Product Cost Calculator (Database Mode)")

        # --- Helper Functions for Data Display (parsing remains similar) ---
        def create_ingredient_display_string(name, provider):
            return f"{name} (Provider: {provider})"

        def parse_ingredient_display_string(display_string):
            if display_string is None: return None, None
            match = re.match(r"^(.*?) \(Provider: (.*?)\)$", display_string)
            if match: return match.group(1), match.group(2)
            return display_string, None

        # --- Data Column Rename Maps (for display in data_editor) ---
        ingr_rename_map = {"name": "Ingredient Name", "provider": "Provider", "price_per_unit": "Price (€) for Unit", "unit_quantity_kg": "Unit Qty (kg)", "price_url": "Price URL", "id": "DB ID"}
        emp_rename_map = {"name": "Employee Name", "hourly_rate": "Hourly Rate (€)", "role": "Role", "id": "DB ID"}
        task_rename_map = {"task_name": "Task Name", "id": "DB ID"}
        gsal_rename_map = {"employee_name_display": "Employee Name", "monthly_amount": "Monthly Salary (€)", "id": "DB ID"} # employee_name_display will be joined

        # --- Tutorial Tab ---
        if app_mode == "Tutorial":
            # ... (Your full Tutorial tab content - no changes needed here) ...
            st.header("📖 Application Tutorial")
            st.markdown("Welcome to the Product Cost Calculator! ...") # Truncated

        # --- Global Data Management UI (Database Version) ---
        elif app_mode == "Manage Global Data":
            st.header("🌍 Manage Global Data (from Database)")
            st.info("Define shared resources. All data is specific to your user account.")
            tab_ingr, tab_emp, tab_tsk, tab_gcost, tab_gsal = st.tabs(["Ingredients", "Employees", "Tasks", "Overheads", "Salaries"])
            user_id = st.session_state.user_id

            with tab_ingr:
                st.subheader("Global Ingredient List")
                try:
                    ingredients_db = db.query(Ingredient).filter(Ingredient.user_id == user_id).order_by(Ingredient.name).all()
                    ingr_df_data = [{"id": ing.id, "name": ing.name, "provider": ing.provider, "price_per_unit": ing.price_per_unit, "unit_quantity_kg": ing.unit_quantity_kg, "price_url": ing.price_url} for ing in ingredients_db]
                    df_ingr_display = pd.DataFrame(ingr_df_data).rename(columns=ingr_rename_map)

                    edited_ingr_df = st.data_editor(
                        df_ingr_display,
                        column_config={
                            ingr_rename_map["id"]: st.column_config.NumberColumn(disabled=True, help="Database ID (cannot be changed)"),
                            ingr_rename_map["name"]: st.column_config.TextColumn(required=True),
                            ingr_rename_map["provider"]: st.column_config.TextColumn(required=True),
                            ingr_rename_map["price_per_unit"]: st.column_config.NumberColumn(format="%.2f", required=True, min_value=0.0),
                            ingr_rename_map["unit_quantity_kg"]: st.column_config.NumberColumn(format="%.3f", required=True, min_value=0.001),
                            ingr_rename_map["price_url"]: st.column_config.LinkColumn(validate=r"^(https?://[^\s/$.?#].[^\s]*)?$") # Optional URL
                        },
                        num_rows="dynamic", key="global_ingredients_editor_db", hide_index=True
                    )
                    if st.button("Save Global Ingredients", key="save_glob_ingr_db"):
                        # Process saves (adds, updates, deletes)
                        db_ids_in_editor = set(edited_ingr_df[ingr_rename_map["id"]].dropna().astype(int))
                        initial_db_ids = set(ing.id for ing in ingredients_db)

                        for _, row in edited_ingr_df.iterrows():
                            ing_id = row[ingr_rename_map["id"]]
                            data = {
                                "name": row[ingr_rename_map["name"]], "provider": row[ingr_rename_map["provider"]],
                                "price_per_unit": row[ingr_rename_map["price_per_unit"]],
                                "unit_quantity_kg": row[ingr_rename_map["unit_quantity_kg"]],
                                "price_url": row[ingr_rename_map["price_url"]]
                            }
                            if pd.isna(ing_id): # New row
                                if data["name"] and data["provider"]: # Basic validation
                                    db.add(Ingredient(user_id=user_id, **data))
                            else: # Existing row
                                ing_id = int(ing_id)
                                if ing_id in initial_db_ids:
                                    db.query(Ingredient).filter(Ingredient.id == ing_id, Ingredient.user_id == user_id).update(data)
                        
                        ids_to_delete = initial_db_ids - db_ids_in_editor
                        if ids_to_delete:
                            db.query(Ingredient).filter(Ingredient.id.in_(ids_to_delete), Ingredient.user_id == user_id).delete(synchronize_session=False)
                        
                        db.commit(); st.success("Global ingredients saved!"); st.rerun()
                except SQLAlchemyError as e: db.rollback(); st.error(f"DB Error (Ingredients): {e}")
                except Exception as e: st.error(f"Error (Ingredients): {e}")


            with tab_emp:
                st.subheader("Global Employee List")
                try:
                    employees_db = db.query(Employee).filter(Employee.user_id == user_id).order_by(Employee.name).all()
                    emp_df_data = [{"id": emp.id, "name": emp.name, "hourly_rate": emp.hourly_rate, "role": emp.role} for emp in employees_db]
                    df_emp_display = pd.DataFrame(emp_df_data).rename(columns=emp_rename_map)

                    edited_emp_df = st.data_editor(
                        df_emp_display,
                        column_config={
                            emp_rename_map["id"]: st.column_config.NumberColumn(disabled=True),
                            emp_rename_map["name"]: st.column_config.TextColumn(required=True),
                            emp_rename_map["hourly_rate"]: st.column_config.NumberColumn(format="%.2f", required=True, min_value=0.0),
                            emp_rename_map["role"]: st.column_config.TextColumn()
                        },
                        num_rows="dynamic", key="global_employees_editor_db", hide_index=True
                    )
                    if st.button("Save Global Employees", key="save_glob_emp_db"):
                        db_ids_in_editor = set(edited_emp_df[emp_rename_map["id"]].dropna().astype(int))
                        initial_db_ids = set(emp.id for emp in employees_db)
                        for _, row in edited_emp_df.iterrows():
                            emp_id = row[emp_rename_map["id"]]
                            data = {"name": row[emp_rename_map["name"]], "hourly_rate": row[emp_rename_map["hourly_rate"]], "role": row[emp_rename_map["role"]]}
                            if pd.isna(emp_id):
                                if data["name"]: db.add(Employee(user_id=user_id, **data))
                            else:
                                emp_id = int(emp_id)
                                if emp_id in initial_db_ids:
                                    db.query(Employee).filter(Employee.id == emp_id, Employee.user_id == user_id).update(data)
                        ids_to_delete = initial_db_ids - db_ids_in_editor
                        if ids_to_delete: # Before deleting employees, check/handle related GlobalSalary entries or set FK to null/cascade
                            for emp_id_del in ids_to_delete:
                                db.query(GlobalSalary).filter(GlobalSalary.employee_id == emp_id_del, GlobalSalary.user_id == user_id).delete(synchronize_session=False)
                            db.query(Employee).filter(Employee.id.in_(ids_to_delete), Employee.user_id == user_id).delete(synchronize_session=False)
                        db.commit(); st.success("Global employees saved!"); st.rerun()
                except SQLAlchemyError as e: db.rollback(); st.error(f"DB Error (Employees): {e}")


            with tab_tsk: # Standard Tasks
                st.subheader("Standard Production Tasks")
                try:
                    prod_tasks_db = db.query(StandardProductionTask).filter(StandardProductionTask.user_id == user_id).order_by(StandardProductionTask.task_name).all()
                    prod_df_data = [{"id": t.id, "task_name": t.task_name} for t in prod_tasks_db]
                    df_prod_display = pd.DataFrame(prod_df_data).rename(columns=task_rename_map)
                    edited_prod_df = st.data_editor(df_prod_display, column_config={task_rename_map["id"]: st.column_config.NumberColumn(disabled=True), task_rename_map["task_name"]: st.column_config.TextColumn(required=True)}, num_rows="dynamic", key="g_prod_tsk_db", hide_index=True)
                    if st.button("Save Prod Tasks", key="s_g_ptsk_db"):
                        # Similar save logic as ingredients/employees
                        db_ids_in_editor = set(edited_prod_df[task_rename_map["id"]].dropna().astype(int))
                        initial_db_ids = set(t.id for t in prod_tasks_db)
                        for _, row in edited_prod_df.iterrows():
                            task_id = row[task_rename_map["id"]]
                            data = {"task_name": row[task_rename_map["task_name"]]}
                            if pd.isna(task_id):
                                if data["task_name"]: db.add(StandardProductionTask(user_id=user_id, **data))
                            else:
                                task_id = int(task_id)
                                if task_id in initial_db_ids:
                                     db.query(StandardProductionTask).filter(StandardProductionTask.id == task_id, StandardProductionTask.user_id == user_id).update(data)
                        ids_to_delete = initial_db_ids - db_ids_in_editor
                        if ids_to_delete: db.query(StandardProductionTask).filter(StandardProductionTask.id.in_(ids_to_delete), StandardProductionTask.user_id == user_id).delete(synchronize_session=False)
                        db.commit(); st.success("Prod tasks saved!"); st.rerun()
                except SQLAlchemyError as e: db.rollback(); st.error(f"DB Error (Prod Tasks): {e}")

                st.subheader("Standard Shipping Tasks")
                # ... Similar logic for Shipping Tasks ...
                try:
                    ship_tasks_db = db.query(StandardShippingTask).filter(StandardShippingTask.user_id == user_id).order_by(StandardShippingTask.task_name).all()
                    ship_df_data = [{"id": t.id, "task_name": t.task_name} for t in ship_tasks_db]
                    df_ship_display = pd.DataFrame(ship_df_data).rename(columns=task_rename_map)
                    edited_ship_df = st.data_editor(df_ship_display, column_config={task_rename_map["id"]: st.column_config.NumberColumn(disabled=True), task_rename_map["task_name"]: st.column_config.TextColumn(required=True)}, num_rows="dynamic", key="g_ship_tsk_db", hide_index=True)
                    if st.button("Save Ship Tasks", key="s_g_stsk_db"):
                        db_ids_in_editor = set(edited_ship_df[task_rename_map["id"]].dropna().astype(int))
                        initial_db_ids = set(t.id for t in ship_tasks_db)
                        for _, row in edited_ship_df.iterrows():
                            task_id = row[task_rename_map["id"]]
                            data = {"task_name": row[task_rename_map["task_name"]]}
                            if pd.isna(task_id):
                                if data["task_name"]: db.add(StandardShippingTask(user_id=user_id, **data))
                            else:
                                task_id = int(task_id)
                                if task_id in initial_db_ids:
                                    db.query(StandardShippingTask).filter(StandardShippingTask.id == task_id, StandardShippingTask.user_id == user_id).update(data)
                        ids_to_delete = initial_db_ids - db_ids_in_editor
                        if ids_to_delete: db.query(StandardShippingTask).filter(StandardShippingTask.id.in_(ids_to_delete), StandardShippingTask.user_id == user_id).delete(synchronize_session=False)
                        db.commit(); st.success("Ship tasks saved!"); st.rerun()
                except SQLAlchemyError as e: db.rollback(); st.error(f"DB Error (Ship Tasks): {e}")


            with tab_gcost:
                st.subheader("Global Monthly Overheads")
                try:
                    gc_settings = db.query(GlobalCosts).filter(GlobalCosts.user_id == user_id).first()
                    if not gc_settings: # Create if doesn't exist for the user
                        gc_settings = GlobalCosts(user_id=user_id, monthly_rent=0.0, monthly_utilities=0.0)
                        db.add(gc_settings)
                        db.commit()
                        db.refresh(gc_settings)
                    
                    n_rent = st.number_input("Global Monthly Rent (€)", value=float(gc_settings.monthly_rent), min_value=0.0, format="%.2f", key="gc_rent_db")
                    n_util = st.number_input("Global Monthly Utilities (€)", value=float(gc_settings.monthly_utilities), min_value=0.0, format="%.2f", key="gc_util_db")
                    if st.button("Save Global Overheads", key="s_g_oh_db"):
                        gc_settings.monthly_rent = n_rent
                        gc_settings.monthly_utilities = n_util
                        db.commit(); st.success("Global overheads saved!")
                except SQLAlchemyError as e: db.rollback(); st.error(f"DB Error (Overheads): {e}")


            with tab_gsal:
                st.subheader("Global Salaries (Linked to Employees)")
                try:
                    employees_for_salary_db = db.query(Employee.id, Employee.name).filter(Employee.user_id == user_id).order_by(Employee.name).all()
                    employee_options_for_salary = {emp.name: emp.id for emp in employees_for_salary_db}
                    employee_display_names_for_salary = list(employee_options_for_salary.keys())

                    global_salaries_db = db.query(GlobalSalary).join(Employee).filter(GlobalSalary.user_id == user_id).options(joinedload(GlobalSalary.employee_ref)).order_by(Employee.name).all()
                    
                    gsal_df_data = [{"id": sal.id, "employee_name_display": sal.employee_ref.name, "monthly_amount": sal.monthly_amount, "_employee_id_hidden": sal.employee_id} for sal in global_salaries_db]
                    df_gsal_display = pd.DataFrame(gsal_df_data).rename(columns=gsal_rename_map)

                    edited_gsal_df = st.data_editor(
                        df_gsal_display,
                        column_config={
                            gsal_rename_map["id"]: st.column_config.NumberColumn(disabled=True),
                            gsal_rename_map["employee_name_display"]: st.column_config.SelectboxColumn(options=employee_display_names_for_salary, required=True),
                            gsal_rename_map["monthly_amount"]: st.column_config.NumberColumn(format="%.2f", required=True, min_value=0.0)
                            # "_employee_id_hidden": st.column_config.NumberColumn(disabled=True) # Not for display
                        },
                        num_rows="dynamic", key="g_sal_ed_db", hide_index=True
                    )
                    if st.button("Save Global Salaries", key="s_g_sal_db"):
                        db_ids_in_editor = set(edited_gsal_df[gsal_rename_map["id"]].dropna().astype(int))
                        initial_db_ids = set(sal.id for sal in global_salaries_db)

                        for _, row in edited_gsal_df.iterrows():
                            sal_id = row[gsal_rename_map["id"]]
                            emp_name_selected = row[gsal_rename_map["employee_name_display"]]
                            emp_id_selected = employee_options_for_salary.get(emp_name_selected)

                            if not emp_id_selected:
                                st.warning(f"Employee '{emp_name_selected}' not found for salary. Skipping row.")
                                continue
                            data = {"employee_id": emp_id_selected, "monthly_amount": row[gsal_rename_map["monthly_amount"]]}

                            if pd.isna(sal_id): # New
                                db.add(GlobalSalary(user_id=user_id, **data))
                            else: # Existing
                                sal_id = int(sal_id)
                                if sal_id in initial_db_ids:
                                    db.query(GlobalSalary).filter(GlobalSalary.id == sal_id, GlobalSalary.user_id == user_id).update(data)
                        
                        ids_to_delete = initial_db_ids - db_ids_in_editor
                        if ids_to_delete: db.query(GlobalSalary).filter(GlobalSalary.id.in_(ids_to_delete), GlobalSalary.user_id == user_id).delete(synchronize_session=False)
                        db.commit(); st.success("Global salaries saved!"); st.rerun()
                except SQLAlchemyError as e: db.rollback(); st.error(f"DB Error (Salaries): {e}")


        # --- Product Management UI (Database Version) ---
        elif app_mode == "Manage Products":
            user_id = st.session_state.user_id
            st.sidebar.subheader("Products (from DB)")
            try:
                products_db = db.query(Product.id, Product.product_name).filter(Product.user_id == user_id).order_by(Product.product_name).all()
                product_names_from_db = [p.product_name for p in products_db]
                product_id_map = {p.product_name: p.id for p in products_db}

                # --- Product Creation / Selection in Sidebar ---
                if 'new_product_cb_db' not in st.session_state: st.session_state.new_product_cb_db = False
                if 'new_product_name_input_db' not in st.session_state: st.session_state.new_product_name_input_db = "New DB Product"
                
                if 'form_message_db' in st.session_state and st.session_state.form_message_db:
                    msg_type, msg_content = st.session_state.form_message_db
                    if msg_type == "success": st.success(msg_content) # Display in main area
                    elif msg_type == "warning": st.warning(msg_content)
                    del st.session_state.form_message_db

                st.sidebar.checkbox("Create New Product", key="new_product_cb_db")
                if st.session_state.new_product_cb_db:
                    st.sidebar.text_input("New Product Name", key="new_product_name_input_db")
                    if st.sidebar.button("Initialize New Product (DB)", key="init_new_prod_btn_db"):
                        prod_to_init = st.session_state.new_product_name_input_db.strip()
                        if not prod_to_init:
                            st.session_state.form_message_db = ("warning", "Product name cannot be empty.")
                        elif db.query(Product).filter(Product.user_id == user_id, Product.product_name == prod_to_init).first():
                            st.session_state.form_message_db = ("warning", "Product name already exists in DB.")
                        else:
                            # Create product with default JSON values from model
                            new_prod_db = Product(user_id=user_id, product_name=prod_to_init)
                            db.add(new_prod_db)
                            db.commit()
                            st.session_state.current_product_id_db = new_prod_db.id # Select the new product
                            st.session_state.new_product_cb_db = False
                            st.session_state.form_message_db = ("success", f"Product '{prod_to_init}' initialized in DB.")
                        st.rerun()
                    st.session_state.current_product_id_db = None # Don't show product details if creating new
                else: # Product Selection
                    if product_names_from_db:
                        if 'current_product_id_db' not in st.session_state or not st.session_state.current_product_id_db or not db.query(Product).filter(Product.id == st.session_state.current_product_id_db, Product.user_id == user_id).first():
                            st.session_state.current_product_id_db = product_id_map.get(product_names_from_db[0]) if product_names_from_db else None
                        
                        # Get current product name for display in selectbox
                        current_selected_prod_name = None
                        if st.session_state.current_product_id_db:
                             current_prod_obj_for_select = db.query(Product.product_name).filter(Product.id == st.session_state.current_product_id_db).scalar()
                             if current_prod_obj_for_select:
                                 current_selected_prod_name = current_prod_obj_for_select


                        selected_prod_name_sidebar = st.sidebar.selectbox(
                            "Select Product", product_names_from_db,
                            index=product_names_from_db.index(current_selected_prod_name) if current_selected_prod_name and current_selected_prod_name in product_names_from_db else 0,
                            key="select_product_sidebar_db"
                        )
                        selected_prod_id = product_id_map.get(selected_prod_name_sidebar)
                        if selected_prod_id != st.session_state.current_product_id_db:
                            st.session_state.current_product_id_db = selected_prod_id
                            st.rerun()
                    else:
                        st.sidebar.info("No products in DB. Create one.")
                        st.session_state.current_product_id_db = None
                
                # --- Display Selected Product Details ---
                if st.session_state.get("current_product_id_db"):
                    current_product_id = st.session_state.current_product_id_db
                    # Eagerly load related data for the product
                    product_data_db = db.query(Product)\
                        .options(
                            selectinload(Product.materials_used).joinedload(ProductMaterial.ingredient),
                            selectinload(Product.production_tasks_performed).joinedload(ProductProductionTask.standard_task),
                            selectinload(Product.production_tasks_performed).joinedload(ProductProductionTask.employee),
                            selectinload(Product.shipping_tasks_performed).joinedload(ProductShippingTask.standard_task),
                            selectinload(Product.shipping_tasks_performed).joinedload(ProductShippingTask.employee)
                            # selectinload(Product.salary_allocation_employee_ref) # if you add this relationship
                        )\
                        .filter(Product.id == current_product_id, Product.user_id == user_id).first()

                    if not product_data_db:
                        st.error("Selected product not found or access denied.")
                    else:
                        st.header(f"📝 Managing Product: {product_data_db.product_name} (DB ID: {product_data_db.id})")
                        prod_tab1, prod_tab2, prod_tab3, prod_tab4 = st.tabs(["Materials", "Labor", "Other Costs", "Summary & Pricing"])
                        
                        # Initialize cost variables (as in your original logic)
                        mats_cost_pi, prod_lab_cost_pi, ship_lab_cost_pi = 0.0, 0.0, 0.0
                        sal_cost_pi, rent_util_cost_pi, pkg_cost_pi = 0.0, 0.0, 0.0
                        # ... any other cost variables ...

                        # Rename maps for product sub-editors
                        mat_used_rename_map_prod = {"ingredient_display": "Ingredient (Provider)", "quantity_grams_used": "Grams Used", "id": "Mat. ID"}
                        task_perf_rename_map_prod = {"task_display": "Task", "employee_display": "Performed By", "time_minutes": "Time (min)", "items_processed_in_task": "# Items", "id": "Perf. ID"}


                        with prod_tab1: # Materials
                            st.subheader("🧪 Materials Used")
                            product_data_db.batch_size_items = st.number_input("Batch Yield (Items)", value=int(product_data_db.batch_size_items), min_value=1, key=f"prod_{current_product_id}_bsi_db")
                            
                            # Get global ingredients for selectbox
                            g_ingr_db_for_prod = db.query(Ingredient).filter(Ingredient.user_id == user_id).order_by(Ingredient.name).all()
                            ingr_options_prod = {create_ingredient_display_string(ing.name, ing.provider): ing.id for ing in g_ingr_db_for_prod}
                            ingr_display_list_prod = list(ingr_options_prod.keys())

                            prod_mats_data = []
                            for pm in product_data_db.materials_used:
                                prod_mats_data.append({
                                    "id": pm.id,
                                    "ingredient_display": create_ingredient_display_string(pm.ingredient.name, pm.ingredient.provider),
                                    "quantity_grams_used": pm.quantity_grams_used,
                                    "_ingredient_id_hidden": pm.ingredient_id # For saving
                                })
                            df_prod_mats_display = pd.DataFrame(prod_mats_data).rename(columns=mat_used_rename_map_prod)
                            
                            edited_prod_mats_df = st.data_editor(
                                df_prod_mats_display,
                                column_config={
                                    mat_used_rename_map_prod["id"]: st.column_config.NumberColumn(disabled=True),
                                    mat_used_rename_map_prod["ingredient_display"]: st.column_config.SelectboxColumn(options=ingr_display_list_prod, required=True),
                                    mat_used_rename_map_prod["quantity_grams_used"]: st.column_config.NumberColumn(format="%.2f", required=True, min_value=0.0)
                                },
                                num_rows="dynamic", key=f"prod_{current_product_id}_mats_db", hide_index=True
                            )

                            # Calculate Materials Cost (similar to your original logic, but using DB data)
                            total_mats_cost_for_prod_db = 0.0
                            if product_data_db.materials_used: # Use the committed data for calculation display
                                for pm_calc in product_data_db.materials_used:
                                    grams_used_calc = float(pm_calc.quantity_grams_used)
                                    ing_calc = pm_calc.ingredient # Already loaded
                                    if ing_calc and ing_calc.unit_quantity_kg > 0:
                                        cost_per_gram = float(ing_calc.price_per_unit) / (float(ing_calc.unit_quantity_kg) * 1000)
                                        total_mats_cost_for_prod_db += grams_used_calc * cost_per_gram
                            
                            cur_bsi_db = product_data_db.batch_size_items
                            mats_cost_pi = total_mats_cost_for_prod_db / cur_bsi_db if cur_bsi_db > 0 else 0.0
                            st.metric("Total Materials Cost for Batch (DB)", f"€{total_mats_cost_for_prod_db:.2f}")
                            st.metric("Materials Cost per Item (DB)", f"€{mats_cost_pi:.2f}")

                        # ... Other Product Tabs (Labor, Other Costs, Summary & Pricing) ...
                        # These will require similar refactoring:
                        # 1. Load data from product_data_db and its relationships.
                        # 2. Populate st.data_editor or other widgets.
                        # 3. Implement save logic for each sub-section.
                        # 4. Recalculate costs based on data from product_data_db.

                        with prod_tab2: # Labor
                            st.subheader("🛠️ Labor")
                            # Load global employees and tasks for dropdowns
                            g_emp_db_for_prod = db.query(Employee).filter(Employee.user_id == user_id).all()
                            emp_options_prod = {emp.name: emp.id for emp in g_emp_db_for_prod}
                            
                            g_prod_tasks_db = db.query(StandardProductionTask).filter(StandardProductionTask.user_id == user_id).all()
                            prod_task_options = {t.task_name: t.id for t in g_prod_tasks_db}

                            g_ship_tasks_db = db.query(StandardShippingTask).filter(StandardShippingTask.user_id == user_id).all()
                            ship_task_options = {t.task_name: t.id for t in g_ship_tasks_db}

                            st.markdown("#### Production Tasks Performed")
                            prod_tasks_perf_data = []
                            for ptp in product_data_db.production_tasks_performed:
                                prod_tasks_perf_data.append({
                                    "id": ptp.id,
                                    "task_display": ptp.standard_task.task_name,
                                    "employee_display": ptp.employee.name,
                                    "time_minutes": ptp.time_minutes,
                                    "items_processed_in_task": ptp.items_processed_in_task,
                                    "_task_id_hidden": ptp.standard_task_id,
                                    "_employee_id_hidden": ptp.employee_id
                                })
                            df_prod_tasks_perf = pd.DataFrame(prod_tasks_perf_data).rename(columns=task_perf_rename_map_prod)
                            edited_prod_tasks_perf_df = st.data_editor(df_prod_tasks_perf, column_config={
                                task_perf_rename_map_prod["id"]: st.column_config.NumberColumn(disabled=True),
                                task_perf_rename_map_prod["task_display"]: st.column_config.SelectboxColumn(options=list(prod_task_options.keys()), required=True),
                                task_perf_rename_map_prod["employee_display"]: st.column_config.SelectboxColumn(options=list(emp_options_prod.keys()), required=True),
                                task_perf_rename_map_prod["time_minutes"]: st.column_config.NumberColumn(format="%.1f", min_value=0.0, required=True),
                                task_perf_rename_map_prod["items_processed_in_task"]: st.column_config.NumberColumn(format="%d", min_value=1, required=True)
                            }, num_rows="dynamic", key=f"prod_{current_product_id}_prod_tasks_db", hide_index=True)
                            # Calculate prod labor cost
                            # ...

                            st.markdown("#### Shipping Tasks Performed")
                            # ... similar for shipping tasks ...

                            st.markdown("#### Salary Allocation (Optional)")
                            # ... similar for salary allocation, linking to Employee ...
                            salaried_emp_options = {emp.name: emp.id for emp in g_emp_db_for_prod if db.query(GlobalSalary).filter(GlobalSalary.employee_id == emp.id, GlobalSalary.user_id == user_id).first()}
                            
                            selected_sal_emp_id = product_data_db.salary_allocation_employee_id
                            selected_sal_emp_name = None
                            if selected_sal_emp_id:
                                for name, id_val in salaried_emp_options.items():
                                    if id_val == selected_sal_emp_id:
                                        selected_sal_emp_name = name
                                        break
                            
                            sel_emp_name_for_sal_db = st.selectbox("Allocate Salary of Employee", options=["None"] + list(salaried_emp_options.keys()), 
                                index = (["None"] + list(salaried_emp_options.keys())).index(selected_sal_emp_name) if selected_sal_emp_name else 0,
                                key=f"prod_{current_product_id}_sal_emp_db")
                            product_data_db.salary_allocation_items_per_month = st.number_input("Items of THIS Product per Month (for salary)", 
                                value=int(product_data_db.salary_allocation_items_per_month), min_value=1, key=f"prod_{current_product_id}_sal_items_db")
                            
                            # Calculate salary cost per item
                            # ...

                        with prod_tab3: # Other Costs
                            st.subheader("📦 Other Costs")
                            st.markdown("#### Rent & Utilities Allocation")
                            product_data_db.rent_utilities_allocation_items_per_month = st.number_input("Items of THIS Product per Month (for rent/utilities)",
                                value=int(product_data_db.rent_utilities_allocation_items_per_month), min_value=1, key=f"prod_{current_product_id}_rent_items_db")
                            # Calculate rent/util cost
                            # ...

                            st.markdown("#### Packaging Costs (per Item)")
                            # These are stored as JSON in Product model
                            pkg_costs_dict = product_data_db.packaging_costs if isinstance(product_data_db.packaging_costs, dict) else {}
                            lc_db = st.number_input("Label Cost/Item (€)", value=float(pkg_costs_dict.get("label_cost_per_item", 0.05)), min_value=0.0, format="%.2f", key=f"prod_{current_product_id}_lc_db")
                            pmc_db = st.number_input("Other Pkg Materials Cost/Item (€)", value=float(pkg_costs_dict.get("materials_cost_per_item", 0.10)), min_value=0.0, format="%.2f", key=f"prod_{current_product_id}_pmc_db")
                            product_data_db.packaging_costs = {"label_cost_per_item": lc_db, "materials_cost_per_item": pmc_db}
                            # ...

                            st.markdown("#### Online Selling Fees - Retail / Wholesale")
                            # ... similar for retail_fees (JSON), wholesale_fees (JSON) ...

                        with prod_tab4: # Summary & Pricing
                            st.subheader("📊 Summary & Pricing")
                            # ... All your cost summary, pricing, and projection logic ...
                            # This will use the calculated cost_pi variables (mats_cost_pi, prod_lab_cost_pi, etc.)
                            # And read/write pricing strategy and distribution from product_data_db.pricing_strategy (JSON)
                            # and product_data_db.distribution_split (JSON)

                        # --- Product Save Button ---
                        if st.button(f"Save Product: {product_data_db.product_name} to DB", key=f"save_prod_{current_product_id}_db"):
                            try:
                                # Save main product fields (batch_size, JSON fields, etc.)
                                # product_data_db object is already updated by widgets for simple fields.
                                
                                # Save Product Materials (from edited_prod_mats_df)
                                initial_mat_ids = {pm.id for pm in product_data_db.materials_used}
                                current_mat_ids_in_editor = set()
                                for _, mat_row in edited_prod_mats_df.iterrows():
                                    mat_id = mat_row[mat_used_rename_map_prod["id"]]
                                    ing_display = mat_row[mat_used_rename_map_prod["ingredient_display"]]
                                    ing_id_for_save = ingr_options_prod.get(ing_display)
                                    qty_grams = mat_row[mat_used_rename_map_prod["quantity_grams_used"]]

                                    if not ing_id_for_save: continue # Skip if ingredient not found

                                    if pd.isna(mat_id): # New material for this product
                                        db.add(ProductMaterial(product_id=current_product_id, ingredient_id=ing_id_for_save, quantity_grams_used=qty_grams))
                                    else: # Existing material
                                        mat_id = int(mat_id)
                                        current_mat_ids_in_editor.add(mat_id)
                                        pm_to_update = db.query(ProductMaterial).filter(ProductMaterial.id == mat_id, ProductMaterial.product_id == current_product_id).first()
                                        if pm_to_update:
                                            pm_to_update.ingredient_id = ing_id_for_save
                                            pm_to_update.quantity_grams_used = qty_grams
                                mats_to_delete = initial_mat_ids - current_mat_ids_in_editor
                                if mats_to_delete:
                                    db.query(ProductMaterial).filter(ProductMaterial.id.in_(mats_to_delete), ProductMaterial.product_id == current_product_id).delete(synchronize_session=False)

                                # Save Product Production Tasks (from edited_prod_tasks_perf_df)
                                # ... similar add/update/delete logic for ProductProductionTask ...
                                # Save Product Shipping Tasks
                                # ... similar add/update/delete logic for ProductShippingTask ...

                                # Save salary allocation choice
                                if sel_emp_name_for_sal_db == "None":
                                    product_data_db.salary_allocation_employee_id = None
                                else:
                                    product_data_db.salary_allocation_employee_id = salaried_emp_options.get(sel_emp_name_for_sal_db)
                                
                                # The product_data_db object itself has been updated for simple fields and JSON fields
                                # by direct assignment from widgets.
                                db.commit()
                                st.success(f"Product '{product_data_db.product_name}' saved to DB!")
                                st.toast(f"'{product_data_db.product_name}' updated.", icon="✅")
                                # st.rerun() # Rerun to reflect any calculation changes based on saved data
                            except SQLAlchemyError as e_prod_save:
                                db.rollback()
                                st.error(f"DB Error saving product: {e_prod_save}")
                            except Exception as e_gen_save:
                                db.rollback()
                                st.error(f"Error saving product: {e_gen_save}")
                else: # No product selected
                     if not st.session_state.new_product_cb_db : # Only show if not in "create new" mode
                        st.info("Select a product from the sidebar to edit, or create a new one.")


            except SQLAlchemyError as e_prod_load:
                db.rollback()
                st.error(f"DB Error in Product Management: {e_prod_load}")
            except Exception as e_gen_prod:
                st.error(f"General Error in Product Management: {e_gen_prod}")


        # --- Footer (if any) ---
        if app_mode != "Tutorial":
            st.markdown("---"); st.markdown(f"Product Cost Calculator (DB Mode) - User: {st.session_state.name}")

    except SQLAlchemyError as e_auth_block: # Catch DB errors within the authenticated block
        if db.is_active: db.rollback()
        st.error(f"A database error occurred: {e_auth_block}. Please try again or contact support.")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}") # For debugging
    except Exception as e_main: # Catch other errors
        st.error(f"An unexpected application error occurred: {e_main}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
    finally:
        if db.is_active: # Ensure session is closed
            db.close()
            print("Database session closed for authenticated user block.")
else: # Not authenticated
    pass # Login UI handled above
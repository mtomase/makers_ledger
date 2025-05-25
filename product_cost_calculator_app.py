# product_cost_calculator_app.py

import streamlit as st
import streamlit_authenticator as stauth
from streamlit_option_menu import option_menu
import yaml
from yaml.loader import SafeLoader
import os
import datetime
import pandas as pd
# import numpy as np # Not strictly needed in this version
# import json # Not strictly needed for product model anymore
import re

# --- Database Setup ---
from dotenv import load_dotenv
load_dotenv()

try:
    from models import (
        User, Ingredient, Employee, Product, GlobalCosts, GlobalSalary,
        StandardProductionTask, StandardShippingTask,
        ProductMaterial, ProductProductionTask, ProductShippingTask,
        # UserLayoutEnumDef, # Not directly used in app logic, but in model
        init_db_structure, get_db, SessionLocal, engine
    )
    from sqlalchemy.orm import Session, joinedload, selectinload
    from sqlalchemy.exc import IntegrityError
except ImportError as e:
    st.error(f"Error importing database models: {e}. Ensure models.py is correct and accessible.")
    st.stop()
except Exception as e:
    st.error(f"An error occurred during database setup: {e}")
    st.stop()

# --- Page Configuration ---
st.set_page_config(page_title="Product Cost Calculator", layout="wide", initial_sidebar_state="expanded")

# --- Common Column Config for ID ---
id_col_config = st.column_config.NumberColumn(
    "ID", disabled=True, help="Internal Database ID (not editable).", width="small"
)

# --- Helper Functions ---
def create_ingredient_display_string(name, provider):
    if provider:
        return f"{name} (Provider: {provider})"
    return name # No provider, just return name

def parse_ingredient_display_string(display_string):
    if display_string is None: return None, None
    match = re.match(r"^(.*?) \(Provider: (.*?)\)$", display_string)
    if match: return match.group(1), match.group(2)
    return display_string, None # Return original string as name, and None as provider

def get_ingredient_id_from_display(db_session, display_string, user_id):
    name, provider = parse_ingredient_display_string(display_string)
    if not name: return None
    
    filters = [Ingredient.user_id == user_id, Ingredient.name == name]
    if provider is not None: # Explicitly check for None, as empty string provider might be valid
        filters.append(Ingredient.provider == provider)
    else: # If provider is None after parsing, it means no provider was in the display string
        filters.append(Ingredient.provider.is_(None))

    ing = db_session.query(Ingredient).filter(*filters).first()
    return ing.id if ing else None

def get_employee_id_from_name(db_session, name_val, user_id):
    if not name_val: return None
    emp = db_session.query(Employee).filter(Employee.user_id == user_id, Employee.name == name_val).first()
    return emp.id if emp else None

def get_std_prod_task_id_from_name(db_session, name_val, user_id):
    if not name_val: return None
    task = db_session.query(StandardProductionTask).filter(StandardProductionTask.user_id == user_id, StandardProductionTask.task_name == name_val).first()
    return task.id if task else None

def get_std_ship_task_id_from_name(db_session, name_val, user_id):
    if not name_val: return None
    task = db_session.query(StandardShippingTask).filter(StandardShippingTask.user_id == user_id, StandardShippingTask.task_name == name_val).first()
    return task.id if task else None

# --- Authenticator Setup ---
CONFIG_FILE_PATH = 'config.yaml'
try:
    with open(CONFIG_FILE_PATH, 'r') as file: config_auth = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError: st.error(f"CRITICAL: Auth config file '{CONFIG_FILE_PATH}' not found."); st.stop()
except Exception as e: st.error(f"Error loading auth config: {e}"); st.stop()

if 'credentials' not in config_auth or 'usernames' not in config_auth['credentials']:
    st.error("CRITICAL: 'credentials' or 'credentials.usernames' not found in config.yaml. Please create/register a user first or fix the config.")
    # Create a dummy structure if it's completely missing to avoid crashing Authenticate,
    # but user won't be able to log in.
    config_auth['credentials'] = config_auth.get('credentials', {})
    config_auth['credentials']['usernames'] = config_auth['credentials'].get('usernames', {})
    # st.stop() # Or stop if you prefer

if not config_auth.get('cookie', {}).get('name') or not config_auth.get('cookie', {}).get('key'):
    st.error("CRITICAL: Cookie 'name' and 'key' must be set in config.yaml."); st.stop()

authenticator = stauth.Authenticate(
    config_auth['credentials'], config_auth['cookie']['name'], config_auth['cookie']['key'],
    config_auth['cookie']['expiry_days'], pre_authorized=config_auth.get('preauthorized') # Use 'preauthorized' from config
)

try:
    authenticator.login() # Renders login form
except Exception as e:
    st.error(f"Login widget error: {e}")

authentication_status = st.session_state.get("authentication_status")
username = st.session_state.get("username")
# name = st.session_state.get("name") # 'name' from authenticator is the user's display name

if 'selected_product_id' not in st.session_state: st.session_state.selected_product_id = None

if authentication_status:
    # Use the name from the authenticator's session state
    user_display_name = st.session_state.get("name", username) # Fallback to username if display name not set

    with st.sidebar: # Sidebar Menu
        st.success(f"Welcome, {user_display_name}!") # Use display name
        authenticator.logout("Logout", "sidebar", key='sidebar_logout_button')
        menu_titles = ["Manage Ingredients", "Manage Employees", "Manage Production Tasks", "Manage Shipping Tasks", "Manage Products", "Global Costs/Salaries", "Product Cost Breakdown", "User Settings"]
        menu_icons = ["bi-cart4", "bi-people-fill", "bi-tools", "bi-truck", "bi-box-seam", "bi-globe", "bi-bar-chart-line-fill", "bi-gear-fill"]
        
        # Default selection logic
        default_selection = menu_titles[0]
        if 'main_menu_selected' in st.session_state and st.session_state.main_menu_selected in menu_titles:
            default_selection = st.session_state.main_menu_selected
        else:
            st.session_state.main_menu_selected = default_selection
            
        selected_option = option_menu(
            menu_title="Main Menu", 
            options=menu_titles, 
            icons=menu_icons, 
            menu_icon="bi-list-ul",
            default_index=menu_titles.index(default_selection),
            orientation="vertical", 
            key="main_menu"
        )
        if selected_option != st.session_state.main_menu_selected:
            st.session_state.main_menu_selected = selected_option
            if selected_option != "Manage Products": 
                st.session_state.selected_product_id = None # Reset product selection if navigating away
            st.rerun() # Rerun on menu change for cleaner state
    choice = st.session_state.main_menu_selected


    db: Session = next(get_db())
    current_user_db = db.query(User).filter(User.username == username).first()
    if not current_user_db: 
        st.error(f"User '{username}' not found in the database. Please ensure the user exists or re-register."); 
        db.close(); 
        st.stop()

    st.title("🧮 Product Cost Calculator Dashboard")

    if choice == "Manage Ingredients":
        st.header("📝 Manage Ingredients")
        st.write("Edit, add, or delete ingredients directly in the table below. Click 'Save Changes' to persist.")
        ingredients_db = db.query(Ingredient).filter(Ingredient.user_id == current_user_db.id).order_by(Ingredient.id).all()
        
        data_for_editor_ing = []
        for ing in ingredients_db:
            data_for_editor_ing.append({
                "ID": ing.id, 
                "Name": ing.name, 
                "Provider": ing.provider, 
                "Price/Unit (€)": ing.price_per_unit, 
                "Unit (kg)": ing.unit_quantity_kg, 
                "Price URL": ing.price_url if ing.price_url else ""
            })
        
        df_ing_cols = ["ID", "Name", "Provider", "Price/Unit (€)", "Unit (kg)", "Price URL"]
        df_ingredients_for_editor = pd.DataFrame(data_for_editor_ing, columns=df_ing_cols)
        if df_ingredients_for_editor.empty:
             df_ingredients_for_editor = pd.DataFrame(columns=df_ing_cols).astype({
                "ID": "float64", "Name": "object", "Provider": "object", 
                "Price/Unit (€)": "float64", "Unit (kg)": "float64", "Price URL": "object"
            })


        snapshot_key_ing = 'df_ingredients_snapshot'
        if snapshot_key_ing not in st.session_state or not st.session_state[snapshot_key_ing].columns.equals(df_ingredients_for_editor.columns):
            st.session_state[snapshot_key_ing] = df_ingredients_for_editor.copy()

        edited_df_ing = st.data_editor(st.session_state[snapshot_key_ing], num_rows="dynamic", key="ingredients_editor",
            column_config={
                "ID": id_col_config, 
                "Name": st.column_config.TextColumn("Ingredient Name*", required=True),
                "Provider": st.column_config.TextColumn("Provider (Optional)"), # Provider can be optional
                "Price/Unit (€)": st.column_config.NumberColumn("Price per Unit (€)*", required=True, min_value=0.00, step=0.01, format="%.2f"),
                "Unit (kg)": st.column_config.NumberColumn("Unit Quantity (kg)*", required=True, min_value=0.001, step=0.001, format="%.3f"),
                "Price URL": st.column_config.TextColumn("Price URL (Optional)")},
            use_container_width=True, hide_index=True)

        if st.button("Save Ingredient Changes"):
            try:
                original_df_snapshot_ing = st.session_state[snapshot_key_ing]
                original_snapshot_ids_ing = set(original_df_snapshot_ing['ID'].dropna().astype(int))
                edited_df_ids_ing = set(edited_df_ing['ID'].dropna().astype(int))
                ids_to_delete_from_db_ing = original_snapshot_ids_ing - edited_df_ids_ing

                for ing_id_del in ids_to_delete_from_db_ing:
                    ing_to_del = db.query(Ingredient).filter(Ingredient.id == ing_id_del, Ingredient.user_id == current_user_db.id).first()
                    if ing_to_del: db.delete(ing_to_del); st.toast(f"Deleted ID: {ing_id_del}", icon="➖")
                
                for index, row in edited_df_ing.iterrows():
                    ing_id, name_val, prov_val = row.get('ID'), row.get("Name"), row.get("Provider")
                    price_val, unit_kg_val = row.get("Price/Unit (€)"), row.get("Unit (kg)")
                    ing_id = int(ing_id) if pd.notna(ing_id) else None
                    
                    if not all([name_val, pd.notna(price_val), pd.notna(unit_kg_val)]): # Provider is optional
                        if ing_id is None and not any([name_val, prov_val, pd.notna(price_val), pd.notna(unit_kg_val)]): continue
                        st.error(f"Row {index+1}: Name, Price/Unit, Unit (kg) are required. Skipping."); continue
                    
                    prov_val = prov_val if prov_val and str(prov_val).strip() else None # Handle empty string provider as None

                    if ing_id: # Update
                        item_to_update = db.query(Ingredient).filter(Ingredient.id == ing_id, Ingredient.user_id == current_user_db.id).first()
                        if item_to_update:
                            changed = False
                            if item_to_update.name != name_val: item_to_update.name = name_val; changed=True
                            if item_to_update.provider != prov_val: item_to_update.provider = prov_val; changed=True
                            if item_to_update.price_per_unit != float(price_val): item_to_update.price_per_unit = float(price_val); changed=True
                            if item_to_update.unit_quantity_kg != float(unit_kg_val): item_to_update.unit_quantity_kg = float(unit_kg_val); changed=True
                            url_val = row.get("Price URL", ""); url_val = url_val if url_val and str(url_val).strip() else None
                            if item_to_update.price_url != url_val: item_to_update.price_url = url_val; changed=True
                            if changed: st.toast(f"Updated ID: {ing_id}", icon="🔄")
                    elif ing_id is None: # Add
                        db.add(Ingredient(user_id=current_user_db.id, name=name_val, provider=prov_val, 
                                          price_per_unit=float(price_val), unit_quantity_kg=float(unit_kg_val), 
                                          price_url=row.get("Price URL") if row.get("Price URL") else None))
                        st.toast(f"Added: {name_val}", icon="➕")
                db.commit(); st.success("Ingredient changes saved!")
                st.session_state[snapshot_key_ing] = edited_df_ing.copy()
                st.rerun()
            except Exception as e: db.rollback(); st.error(f"Error saving ingredients: {e}"); st.exception(e)

    elif choice == "Manage Employees":
        st.header("👥 Manage Employees")
        st.write("Edit, add, or delete employees. Click 'Save Changes' to persist.")
        employees_db = db.query(Employee).filter(Employee.user_id == current_user_db.id).order_by(Employee.id).all()
        data_for_editor_emp = [{"ID": emp.id, "Name": emp.name, "Hourly Rate (€)": emp.hourly_rate, "Role": emp.role} for emp in employees_db]
        
        df_emp_cols = ["ID", "Name", "Hourly Rate (€)", "Role"]
        df_employees_for_editor = pd.DataFrame(data_for_editor_emp, columns=df_emp_cols)
        if df_employees_for_editor.empty:
            df_employees_for_editor = pd.DataFrame(columns=df_emp_cols).astype({
                "ID": "float64", "Name": "object", "Hourly Rate (€)": "float64", "Role": "object"
            })

        snapshot_key_emp = 'df_employees_snapshot'
        if snapshot_key_emp not in st.session_state or not st.session_state[snapshot_key_emp].columns.equals(df_employees_for_editor.columns):
            st.session_state[snapshot_key_emp] = df_employees_for_editor.copy()

        edited_df_emp = st.data_editor(st.session_state[snapshot_key_emp], num_rows="dynamic", key="employees_editor",
            column_config={
                "ID": id_col_config, 
                "Name": st.column_config.TextColumn("Employee Name*", required=True),
                "Hourly Rate (€)": st.column_config.NumberColumn("Hourly Rate (€)*", required=True, min_value=0.00, step=0.01, format="%.2f"),
                "Role": st.column_config.TextColumn("Role (Optional)")},
            use_container_width=True, hide_index=True)

        if st.button("Save Employee Changes"):
            try:
                original_df_snapshot_emp = st.session_state[snapshot_key_emp]
                original_snapshot_ids_emp = set(original_df_snapshot_emp['ID'].dropna().astype(int))
                edited_df_ids_emp = set(edited_df_emp['ID'].dropna().astype(int))
                ids_to_delete_from_db_emp = original_snapshot_ids_emp - edited_df_ids_emp

                for emp_id_del in ids_to_delete_from_db_emp:
                    emp_to_del = db.query(Employee).filter(Employee.id == emp_id_del, Employee.user_id == current_user_db.id).first()
                    if emp_to_del: db.delete(emp_to_del); st.toast(f"Deleted employee ID: {emp_id_del}", icon="➖")

                for index, row in edited_df_emp.iterrows():
                    emp_id, name_val, rate_val, role_val = row.get('ID'), row.get("Name"), row.get("Hourly Rate (€)"), row.get("Role")
                    emp_id = int(emp_id) if pd.notna(emp_id) else None
                    if not all([name_val, pd.notna(rate_val)]):
                        if emp_id is None and not any([name_val, pd.notna(rate_val), role_val]): continue
                        st.error(f"Row {index+1}: Name and Hourly Rate are required. Skipping."); continue
                    
                    role_val = role_val if role_val and str(role_val).strip() else None

                    if emp_id: # Update
                        item_to_update = db.query(Employee).filter(Employee.id == emp_id, Employee.user_id == current_user_db.id).first()
                        if item_to_update:
                            changed = False
                            if item_to_update.name != name_val: item_to_update.name = name_val; changed=True
                            if item_to_update.hourly_rate != float(rate_val): item_to_update.hourly_rate = float(rate_val); changed=True
                            if item_to_update.role != role_val: item_to_update.role = role_val; changed=True
                            if changed: st.toast(f"Updated employee ID: {emp_id}", icon="🔄")
                    elif emp_id is None: # Add
                        db.add(Employee(user_id=current_user_db.id, name=name_val, hourly_rate=float(rate_val), role=role_val))
                        st.toast(f"Added employee: {name_val}", icon="➕")
                db.commit(); st.success("Employee changes saved!")
                st.session_state[snapshot_key_emp] = edited_df_emp.copy()
                st.rerun()
            except Exception as e: db.rollback(); st.error(f"Error saving employees: {e}"); st.exception(e)

    elif choice == "Manage Production Tasks":
        st.header("🏭 Manage Standard Production Tasks")
        tasks_db = db.query(StandardProductionTask).filter(StandardProductionTask.user_id == current_user_db.id).order_by(StandardProductionTask.id).all()
        data_for_editor_ptask = [{"ID": task.id, "Task Name": task.task_name} for task in tasks_db]
        
        df_ptask_cols = ["ID", "Task Name"]
        df_ptasks_for_editor = pd.DataFrame(data_for_editor_ptask, columns=df_ptask_cols)
        if df_ptasks_for_editor.empty:
            df_ptasks_for_editor = pd.DataFrame(columns=df_ptask_cols).astype({"ID": "float64", "Task Name": "object"})

        snapshot_key_ptask = 'df_ptasks_snapshot'
        if snapshot_key_ptask not in st.session_state or not st.session_state[snapshot_key_ptask].columns.equals(df_ptasks_for_editor.columns):
            st.session_state[snapshot_key_ptask] = df_ptasks_for_editor.copy()
        
        edited_df_ptask = st.data_editor(st.session_state[snapshot_key_ptask], num_rows="dynamic", key="prod_tasks_editor",
            column_config={"ID": id_col_config, "Task Name": st.column_config.TextColumn("Task Name*", required=True)},
            use_container_width=True, hide_index=True)

        if st.button("Save Production Task Changes"):
            try:
                original_df_snapshot_ptask = st.session_state[snapshot_key_ptask]
                original_snapshot_ids_ptask = set(original_df_snapshot_ptask['ID'].dropna().astype(int))
                edited_df_ids_ptask = set(edited_df_ptask['ID'].dropna().astype(int))
                ids_to_delete_from_db_ptask = original_snapshot_ids_ptask - edited_df_ids_ptask

                for task_id_del in ids_to_delete_from_db_ptask:
                    task_to_del = db.query(StandardProductionTask).filter(StandardProductionTask.id == task_id_del, StandardProductionTask.user_id == current_user_db.id).first()
                    if task_to_del: db.delete(task_to_del); st.toast(f"Deleted task ID: {task_id_del}", icon="➖")

                for index, row in edited_df_ptask.iterrows():
                    task_id, name_val = row.get('ID'), row.get("Task Name")
                    task_id = int(task_id) if pd.notna(task_id) else None
                    if not name_val:
                        if task_id is None and not name_val: continue
                        st.error(f"Row {index+1}: Task Name is required. Skipping."); continue
                    
                    if task_id: # Update
                        item_to_update = db.query(StandardProductionTask).filter(StandardProductionTask.id == task_id, StandardProductionTask.user_id == current_user_db.id).first()
                        if item_to_update and item_to_update.task_name != name_val:
                            item_to_update.task_name = name_val; st.toast(f"Updated task ID: {task_id}", icon="🔄")
                    elif task_id is None: # Add
                        db.add(StandardProductionTask(user_id=current_user_db.id, task_name=name_val))
                        st.toast(f"Added task: {name_val}", icon="➕")
                db.commit(); st.success("Production Task changes saved!")
                st.session_state[snapshot_key_ptask] = edited_df_ptask.copy()
                st.rerun()
            except Exception as e: db.rollback(); st.error(f"Error saving production tasks: {e}"); st.exception(e)

    elif choice == "Manage Shipping Tasks":
        st.header("🚚 Manage Standard Shipping Tasks")
        # Similar CRUD logic as Production Tasks
        tasks_db_ship = db.query(StandardShippingTask).filter(StandardShippingTask.user_id == current_user_db.id).order_by(StandardShippingTask.id).all()
        data_for_editor_stask = [{"ID": task.id, "Task Name": task.task_name} for task in tasks_db_ship]
        
        df_stask_cols = ["ID", "Task Name"]
        df_stasks_for_editor = pd.DataFrame(data_for_editor_stask, columns=df_stask_cols)
        if df_stasks_for_editor.empty:
            df_stasks_for_editor = pd.DataFrame(columns=df_stask_cols).astype({"ID": "float64", "Task Name": "object"})

        snapshot_key_stask = 'df_stasks_snapshot'
        if snapshot_key_stask not in st.session_state or not st.session_state[snapshot_key_stask].columns.equals(df_stasks_for_editor.columns):
            st.session_state[snapshot_key_stask] = df_stasks_for_editor.copy()

        edited_df_stask = st.data_editor(st.session_state[snapshot_key_stask], num_rows="dynamic", key="ship_tasks_editor",
            column_config={"ID": id_col_config, "Task Name": st.column_config.TextColumn("Task Name*", required=True)},
            use_container_width=True, hide_index=True)

        if st.button("Save Shipping Task Changes"):
            try:
                original_df_snapshot_stask = st.session_state[snapshot_key_stask]
                original_snapshot_ids_stask = set(original_df_snapshot_stask['ID'].dropna().astype(int))
                edited_df_ids_stask = set(edited_df_stask['ID'].dropna().astype(int))
                ids_to_delete_from_db_stask = original_snapshot_ids_stask - edited_df_ids_stask

                for task_id_del in ids_to_delete_from_db_stask:
                    task_to_del = db.query(StandardShippingTask).filter(StandardShippingTask.id == task_id_del, StandardShippingTask.user_id == current_user_db.id).first()
                    if task_to_del: db.delete(task_to_del); st.toast(f"Deleted task ID: {task_id_del}", icon="➖")
                
                for index, row in edited_df_stask.iterrows():
                    task_id, name_val = row.get('ID'), row.get("Task Name")
                    task_id = int(task_id) if pd.notna(task_id) else None
                    if not name_val:
                        if task_id is None and not name_val: continue
                        st.error(f"Row {index+1}: Task Name is required. Skipping."); continue
                    if task_id:
                        item_to_update = db.query(StandardShippingTask).filter(StandardShippingTask.id == task_id, StandardShippingTask.user_id == current_user_db.id).first()
                        if item_to_update and item_to_update.task_name != name_val:
                             item_to_update.task_name = name_val; st.toast(f"Updated task ID: {task_id}", icon="🔄")
                    elif task_id is None:
                        db.add(StandardShippingTask(user_id=current_user_db.id, task_name=name_val))
                        st.toast(f"Added task: {name_val}", icon="➕")
                db.commit(); st.success("Shipping Task changes saved!")
                st.session_state[snapshot_key_stask] = edited_df_stask.copy()
                st.rerun()
            except Exception as e: db.rollback(); st.error(f"Error saving shipping tasks: {e}"); st.exception(e)
            
    elif choice == "Manage Products":
        st.header("📦 Manage Products")
        st.write("Add, edit, or delete main product attributes. Select a product from the table or the dropdown below to manage its detailed components.")

        products_db = db.query(Product).filter(Product.user_id == current_user_db.id).order_by(Product.id).all()
        product_editor_columns = ["ID", "Product Name", "Batch Size", "Monthly Production"]
        data_for_editor_prod = [{"ID": p.id, "Product Name": p.product_name, "Batch Size": p.batch_size_items, "Monthly Production": p.monthly_production_items} for p in products_db]
        
        df_products_for_editor = pd.DataFrame(data_for_editor_prod, columns=product_editor_columns)
        if df_products_for_editor.empty:
            df_products_for_editor = pd.DataFrame(columns=product_editor_columns).astype({
                "ID": "float64", "Product Name": "object", "Batch Size": "int64", "Monthly Production": "int64"
            })

        snapshot_key_prod = 'df_products_snapshot'
        if snapshot_key_prod not in st.session_state or not st.session_state[snapshot_key_prod].columns.equals(df_products_for_editor.columns):
            st.session_state[snapshot_key_prod] = df_products_for_editor.copy()
        
        product_column_config = {
            "ID": id_col_config, 
            "Product Name": st.column_config.TextColumn("Product Name*", required=True, width="large"),
            "Batch Size": st.column_config.NumberColumn("Batch Size (items)*", required=True, min_value=1, step=1, format="%d", width="medium"),
            "Monthly Production": st.column_config.NumberColumn("Monthly Prod (items)*", required=True, min_value=0, step=1, format="%d", width="medium")
        }

        edited_df_prod = st.data_editor(
            st.session_state[snapshot_key_prod], num_rows="dynamic", key="products_editor",
            column_config=product_column_config, use_container_width=True, hide_index=True
        )

        if st.button("Save Product Attribute Changes"):
            try:
                original_df_snapshot_prod = st.session_state[snapshot_key_prod]
                original_snapshot_ids_prod = set(original_df_snapshot_prod['ID'].dropna().astype(int))
                edited_df_ids_prod = set(edited_df_prod['ID'].dropna().astype(int))
                ids_to_delete_from_db_prod = original_snapshot_ids_prod - edited_df_ids_prod

                for p_id_del in ids_to_delete_from_db_prod:
                    prod_to_del = db.query(Product).filter(Product.id == p_id_del, Product.user_id == current_user_db.id).first()
                    if prod_to_del: 
                        # Cascades are handled by relationships in models.py (cascade="all, delete-orphan")
                        db.delete(prod_to_del)
                        st.toast(f"Deleted product ID: {p_id_del}", icon="➖")
                        if st.session_state.selected_product_id == p_id_del: st.session_state.selected_product_id = None
                
                for index, edited_row in edited_df_prod.iterrows():
                    p_id = edited_row.get('ID'); p_id = int(p_id) if pd.notna(p_id) else None
                    name_val, batch_val, monthly_val = edited_row.get("Product Name"), edited_row.get("Batch Size"), edited_row.get("Monthly Production")

                    if not all([name_val, pd.notna(batch_val), pd.notna(monthly_val)]):
                        if p_id is None and not any([name_val, pd.notna(batch_val), pd.notna(monthly_val)]): continue
                        st.error(f"Row {index+1} (Products): Name, Batch Size, Monthly Prod are required. Skipping."); continue
                    
                    if p_id: # Update
                        p_to_update = db.query(Product).filter(Product.id == p_id, Product.user_id == current_user_db.id).first()
                        if p_to_update:
                            changed = False
                            if p_to_update.product_name != name_val: p_to_update.product_name = name_val; changed=True
                            if p_to_update.batch_size_items != int(batch_val): p_to_update.batch_size_items = int(batch_val); changed=True
                            if p_to_update.monthly_production_items != int(monthly_val): p_to_update.monthly_production_items = int(monthly_val); changed=True
                            if changed: st.toast(f"Updated product ID: {p_id}", icon="🔄")
                    elif p_id is None: # Add
                        new_prod = Product(user_id=current_user_db.id, product_name=name_val, batch_size_items=int(batch_val), monthly_production_items=int(monthly_val))
                        db.add(new_prod); db.flush(); st.session_state.selected_product_id = new_prod.id
                        st.toast(f"Added: {name_val}. Selected for detail editing.", icon="➕")
                db.commit(); st.success("Product attribute changes saved!")
                st.session_state[snapshot_key_prod] = edited_df_prod.copy()
                st.rerun()
            except Exception as e: db.rollback(); st.error(f"Error saving products: {e}"); st.exception(e)

        st.markdown("---")
        product_list_for_details = db.query(Product).filter(Product.user_id == current_user_db.id).order_by(Product.product_name).all()
        product_names_for_select = {p.product_name: p.id for p in product_list_for_details}
        
        if product_list_for_details:
            current_selected_name_for_dropdown = None
            if st.session_state.selected_product_id:
                for name_key, id_val in product_names_for_select.items():
                    if id_val == st.session_state.selected_product_id: current_selected_name_for_dropdown = name_key; break
            
            if not current_selected_name_for_dropdown and product_list_for_details:
                 current_selected_name_for_dropdown = product_list_for_details[0].product_name
                 st.session_state.selected_product_id = product_list_for_details[0].id
            elif current_selected_name_for_dropdown not in product_names_for_select and product_list_for_details:
                 current_selected_name_for_dropdown = product_list_for_details[0].product_name
                 st.session_state.selected_product_id = product_list_for_details[0].id

            selected_product_name_for_details = st.selectbox("Select Product to Manage Details:", options=list(product_names_for_select.keys()),
                index=list(product_names_for_select.keys()).index(current_selected_name_for_dropdown) if current_selected_name_for_dropdown in product_names_for_select else 0,
                key="product_detail_selector", placeholder="Choose a product...")
            if selected_product_name_for_details and product_names_for_select.get(selected_product_name_for_details) != st.session_state.selected_product_id:
                st.session_state.selected_product_id = product_names_for_select[selected_product_name_for_details]
                st.rerun()
        else:
            st.info("No products available to manage details. Please add a product above.")
            if st.session_state.selected_product_id is not None: # Clear selection if list becomes empty
                st.session_state.selected_product_id = None
                st.rerun()


        if st.session_state.selected_product_id:
            selected_product_object = db.query(Product)\
                .options(selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref),
                         selectinload(Product.production_tasks).joinedload(ProductProductionTask.employee_ref),
                         selectinload(Product.production_tasks).joinedload(ProductProductionTask.standard_task_ref),
                         selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.employee_ref),
                         selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.standard_task_ref),
                         joinedload(Product.salary_alloc_employee_ref) # Eager load this too
                         )\
                .filter(Product.id == st.session_state.selected_product_id, Product.user_id == current_user_db.id).first()

            if not selected_product_object: 
                st.warning("The previously selected product could not be found. Please select another product.")
                st.session_state.selected_product_id = None
            else:
                st.subheader(f"Managing Details for: {selected_product_object.product_name}")

                with st.expander("🧪 Product Materials", expanded=True):
                    all_ingredients_db = db.query(Ingredient).filter(Ingredient.user_id == current_user_db.id).all()
                    ingredient_display_options = [create_ingredient_display_string(ing.name, ing.provider) for ing in all_ingredients_db] if all_ingredients_db else ["No ingredients defined globally"]
                    
                    # product_materials_db = selected_product_object.materials # Use eager loaded
                    data_for_pm_editor = []
                    if selected_product_object.materials: # Check if materials exist
                        for pm in selected_product_object.materials:
                            if pm.ingredient_ref: # Check if ingredient_ref is loaded
                                data_for_pm_editor.append({"ID": pm.id, "Ingredient": create_ingredient_display_string(pm.ingredient_ref.name, pm.ingredient_ref.provider), "Quantity (g)": pm.quantity_grams})
                            else: # Should not happen with joinedload
                                st.warning(f"Material link ID {pm.id} has a missing ingredient reference.")
                    
                    df_pm_cols = ["ID", "Ingredient", "Quantity (g)"]
                    df_pm_for_editor = pd.DataFrame(data_for_pm_editor, columns=df_pm_cols)
                    if df_pm_for_editor.empty:
                        df_pm_for_editor = pd.DataFrame(columns=df_pm_cols).astype({"ID":"float64", "Ingredient":"object", "Quantity (g)":"float64"})

                    snapshot_key_pm = f'df_pm_snapshot_{selected_product_object.id}'
                    if snapshot_key_pm not in st.session_state or not st.session_state[snapshot_key_pm].columns.equals(df_pm_for_editor.columns):
                        st.session_state[snapshot_key_pm] = df_pm_for_editor.copy()
                    
                    edited_df_pm = st.data_editor(st.session_state[snapshot_key_pm], num_rows="dynamic", key=f"pm_editor_{selected_product_object.id}",
                        column_config={"ID": id_col_config, 
                                       "Ingredient": st.column_config.SelectboxColumn("Ingredient (Provider)*", options=ingredient_display_options, required=True), 
                                       "Quantity (g)": st.column_config.NumberColumn("Quantity (grams)*", required=True, min_value=0.001, step=0.01, format="%.3f")},
                        use_container_width=True, hide_index=True)

                    if st.button(f"Save Materials for {selected_product_object.product_name}", key=f"save_pm_{selected_product_object.id}"):
                        try:
                            original_df_snapshot_pm = st.session_state[snapshot_key_pm]
                            original_snapshot_ids_pm = set(original_df_snapshot_pm['ID'].dropna().astype(int))
                            edited_df_ids_pm = set(edited_df_pm['ID'].dropna().astype(int))
                            ids_to_delete_from_db_pm = original_snapshot_ids_pm - edited_df_ids_pm

                            for pm_id_del in ids_to_delete_from_db_pm:
                                pm_to_del = db.query(ProductMaterial).filter(ProductMaterial.id == pm_id_del, ProductMaterial.product_id == selected_product_object.id).first()
                                if pm_to_del: db.delete(pm_to_del); st.toast(f"Deleted material ID: {pm_id_del}", icon="➖")

                            for index, row in edited_df_pm.iterrows():
                                pm_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                                ing_display_val, qty_val = row.get("Ingredient"), row.get("Quantity (g)")
                                if not all([ing_display_val, ing_display_val != "No ingredients defined globally", pd.notna(qty_val), float(qty_val or 0) > 0]):
                                    if pm_id is None and not any([ing_display_val, pd.notna(qty_val)]): continue
                                    st.error(f"Row {index+1} (Materials): Invalid data. Skipping."); continue
                                
                                ingredient_id_for_row = get_ingredient_id_from_display(db, ing_display_val, current_user_db.id)
                                if not ingredient_id_for_row: st.error(f"Row {index+1} (Materials): Could not find '{ing_display_val}'. Skipping."); continue
                                
                                if pm_id: # Update
                                    pm_to_update = db.query(ProductMaterial).filter(ProductMaterial.id == pm_id, ProductMaterial.product_id == selected_product_object.id).first()
                                    if pm_to_update:
                                        changed = False
                                        if pm_to_update.ingredient_id != ingredient_id_for_row: pm_to_update.ingredient_id = ingredient_id_for_row; changed=True
                                        if pm_to_update.quantity_grams != float(qty_val): pm_to_update.quantity_grams = float(qty_val); changed=True
                                        if changed: st.toast(f"Updated material ID: {pm_id}", icon="🔄")
                                elif pm_id is None: # Add
                                    db.add(ProductMaterial(product_id=selected_product_object.id, ingredient_id=ingredient_id_for_row, quantity_grams=float(qty_val)))
                                    st.toast(f"Added material: {ing_display_val}", icon="➕")
                            db.commit(); st.success(f"Materials for '{selected_product_object.product_name}' saved!")
                            st.session_state[snapshot_key_pm] = edited_df_pm.copy()
                            st.rerun()
                        except Exception as e: db.rollback(); st.error(f"Error saving materials: {e}"); st.exception(e)
                
                with st.expander("🛠️ Product Production Tasks", expanded=False):
                    all_std_prod_tasks_db = db.query(StandardProductionTask).filter(StandardProductionTask.user_id == current_user_db.id).all()
                    std_prod_task_options = [task.task_name for task in all_std_prod_tasks_db] if all_std_prod_tasks_db else ["No standard prod tasks defined"]
                    all_employees_db = db.query(Employee).filter(Employee.user_id == current_user_db.id).all()
                    employee_name_options = [emp.name for emp in all_employees_db] if all_employees_db else ["No employees defined"] # Renamed for clarity
                    
                    data_for_ppt_editor = []
                    if selected_product_object.production_tasks:
                        for ppt in selected_product_object.production_tasks:
                            if ppt.standard_task_ref and ppt.employee_ref: # Check refs
                                data_for_ppt_editor.append({
                                    "ID": ppt.id, "Task": ppt.standard_task_ref.task_name, 
                                    "Employee": ppt.employee_ref.name, "Time (min)": ppt.time_minutes, 
                                    "# Items in Task": ppt.items_processed_in_task
                                })
                    
                    df_ppt_cols = ["ID", "Task", "Employee", "Time (min)", "# Items in Task"]
                    df_ppt_for_editor = pd.DataFrame(data_for_ppt_editor, columns=df_ppt_cols)
                    if df_ppt_for_editor.empty:
                        df_ppt_for_editor = pd.DataFrame(columns=df_ppt_cols).astype({
                            "ID":"float64", "Task":"object", "Employee":"object", 
                            "Time (min)":"float64", "# Items in Task":"int64"
                        })

                    snapshot_key_ppt = f'df_ppt_snapshot_{selected_product_object.id}'
                    if snapshot_key_ppt not in st.session_state or not st.session_state[snapshot_key_ppt].columns.equals(df_ppt_for_editor.columns):
                        st.session_state[snapshot_key_ppt] = df_ppt_for_editor.copy()

                    edited_df_ppt = st.data_editor(st.session_state[snapshot_key_ppt], num_rows="dynamic", key=f"ppt_editor_{selected_product_object.id}",
                        column_config={
                            "ID": id_col_config,
                            "Task": st.column_config.SelectboxColumn("Task*", options=std_prod_task_options, required=True),
                            "Employee": st.column_config.SelectboxColumn("Performed By*", options=employee_name_options, required=True),
                            "Time (min)": st.column_config.NumberColumn("Time (min)*", required=True, min_value=0.0, step=0.1, format="%.1f"),
                            "# Items in Task": st.column_config.NumberColumn("# Items in Task*", required=True, min_value=1, step=1, format="%d")
                        }, use_container_width=True, hide_index=True)

                    if st.button(f"Save Production Tasks for {selected_product_object.product_name}", key=f"save_ppt_{selected_product_object.id}"):
                        try:
                            original_df_snapshot_ppt = st.session_state[snapshot_key_ppt]
                            original_snapshot_ids_ppt = set(original_df_snapshot_ppt['ID'].dropna().astype(int))
                            edited_df_ids_ppt = set(edited_df_ppt['ID'].dropna().astype(int))
                            ids_to_delete_from_db_ppt = original_snapshot_ids_ppt - edited_df_ids_ppt

                            for ppt_id_del in ids_to_delete_from_db_ppt:
                                ppt_to_del = db.query(ProductProductionTask).filter(ProductProductionTask.id == ppt_id_del, ProductProductionTask.product_id == selected_product_object.id).first()
                                if ppt_to_del: db.delete(ppt_to_del); st.toast(f"Deleted prod task ID: {ppt_id_del}", icon="➖")
                            
                            for index, row in edited_df_ppt.iterrows():
                                ppt_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                                task_name_val, emp_name_val, time_val, items_val = row.get("Task"), row.get("Employee"), row.get("Time (min)"), row.get("# Items in Task")
                                if not all([task_name_val, task_name_val != "No standard prod tasks defined", 
                                            emp_name_val, emp_name_val != "No employees defined", 
                                            pd.notna(time_val), pd.notna(items_val), int(items_val or 0) > 0]):
                                    if ppt_id is None and not any([task_name_val, emp_name_val, pd.notna(time_val), pd.notna(items_val)]): continue
                                    st.error(f"Row {index+1} (Prod Tasks): Invalid data. Skipping."); continue
                                
                                std_task_id_for_row = get_std_prod_task_id_from_name(db, task_name_val, current_user_db.id)
                                emp_id_for_row = get_employee_id_from_name(db, emp_name_val, current_user_db.id)
                                if not std_task_id_for_row or not emp_id_for_row: st.error(f"Row {index+1} (Prod Tasks): Invalid task/employee. Skipping."); continue
                                
                                if ppt_id: # Update
                                    ppt_to_update = db.query(ProductProductionTask).filter(ProductProductionTask.id == ppt_id, ProductProductionTask.product_id == selected_product_object.id).first()
                                    if ppt_to_update:
                                        changed = False
                                        if ppt_to_update.standard_task_id != std_task_id_for_row: ppt_to_update.standard_task_id = std_task_id_for_row; changed=True
                                        if ppt_to_update.employee_id != emp_id_for_row: ppt_to_update.employee_id = emp_id_for_row; changed=True
                                        if ppt_to_update.time_minutes != float(time_val): ppt_to_update.time_minutes = float(time_val); changed=True
                                        if ppt_to_update.items_processed_in_task != int(items_val): ppt_to_update.items_processed_in_task = int(items_val); changed=True
                                        if changed: st.toast(f"Updated prod task ID: {ppt_id}", icon="🔄")
                                elif ppt_id is None: # Add
                                    db.add(ProductProductionTask(product_id=selected_product_object.id, standard_task_id=std_task_id_for_row, 
                                                                 employee_id=emp_id_for_row, time_minutes=float(time_val), items_processed_in_task=int(items_val)))
                                    st.toast(f"Added prod task: {task_name_val}", icon="➕")
                            db.commit(); st.success(f"Production tasks saved!")
                            st.session_state[snapshot_key_ppt] = edited_df_ppt.copy()
                            st.rerun()
                        except Exception as e: db.rollback(); st.error(f"Error saving prod tasks: {e}"); st.exception(e)

                with st.expander("🚚 Product Shipping Tasks", expanded=False):
                    all_std_ship_tasks_db = db.query(StandardShippingTask).filter(StandardShippingTask.user_id == current_user_db.id).all()
                    std_ship_task_options = [task.task_name for task in all_std_ship_tasks_db] if all_std_ship_tasks_db else ["No standard ship tasks defined"]
                    # employee_name_options is the same
                    
                    data_for_pst_editor = []
                    if selected_product_object.shipping_tasks:
                        for pst in selected_product_object.shipping_tasks:
                            if pst.standard_task_ref and pst.employee_ref:
                                data_for_pst_editor.append({
                                    "ID": pst.id, "Task": pst.standard_task_ref.task_name, 
                                    "Employee": pst.employee_ref.name, "Time (min)": pst.time_minutes, 
                                    "# Items in Task": pst.items_processed_in_task
                                })
                    df_pst_cols = ["ID", "Task", "Employee", "Time (min)", "# Items in Task"]
                    df_pst_for_editor = pd.DataFrame(data_for_pst_editor, columns=df_pst_cols)
                    if df_pst_for_editor.empty:
                        df_pst_for_editor = pd.DataFrame(columns=df_pst_cols).astype({
                            "ID":"float64", "Task":"object", "Employee":"object", 
                            "Time (min)":"float64", "# Items in Task":"int64"
                        })
                    
                    snapshot_key_pst = f'df_pst_snapshot_{selected_product_object.id}'
                    if snapshot_key_pst not in st.session_state or not st.session_state[snapshot_key_pst].columns.equals(df_pst_for_editor.columns):
                        st.session_state[snapshot_key_pst] = df_pst_for_editor.copy()

                    edited_df_pst = st.data_editor(st.session_state[snapshot_key_pst], num_rows="dynamic", key=f"pst_editor_{selected_product_object.id}",
                        column_config={
                            "ID": id_col_config,
                            "Task": st.column_config.SelectboxColumn("Task*", options=std_ship_task_options, required=True),
                            "Employee": st.column_config.SelectboxColumn("Performed By*", options=employee_name_options, required=True),
                            "Time (min)": st.column_config.NumberColumn("Time (min)*", required=True, min_value=0.0, step=0.1, format="%.1f"),
                            "# Items in Task": st.column_config.NumberColumn("# Items in Task*", required=True, min_value=1, step=1, format="%d")
                        }, use_container_width=True, hide_index=True)

                    if st.button(f"Save Shipping Tasks for {selected_product_object.product_name}", key=f"save_pst_{selected_product_object.id}"):
                        # Similar save logic as production tasks
                        try:
                            original_df_snapshot_pst = st.session_state[snapshot_key_pst]
                            original_snapshot_ids_pst = set(original_df_snapshot_pst['ID'].dropna().astype(int))
                            edited_df_ids_pst = set(edited_df_pst['ID'].dropna().astype(int))
                            ids_to_delete_from_db_pst = original_snapshot_ids_pst - edited_df_ids_pst

                            for pst_id_del in ids_to_delete_from_db_pst:
                                pst_to_del = db.query(ProductShippingTask).filter(ProductShippingTask.id == pst_id_del, ProductShippingTask.product_id == selected_product_object.id).first()
                                if pst_to_del: db.delete(pst_to_del); st.toast(f"Deleted ship task ID: {pst_id_del}", icon="➖")
                            
                            for index, row in edited_df_pst.iterrows():
                                pst_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                                task_name_val, emp_name_val, time_val, items_val = row.get("Task"), row.get("Employee"), row.get("Time (min)"), row.get("# Items in Task")
                                if not all([task_name_val, task_name_val != "No standard ship tasks defined", 
                                            emp_name_val, emp_name_val != "No employees defined", 
                                            pd.notna(time_val), pd.notna(items_val), int(items_val or 0) > 0]):
                                    if pst_id is None and not any([task_name_val, emp_name_val, pd.notna(time_val), pd.notna(items_val)]): continue
                                    st.error(f"Row {index+1} (Ship Tasks): Invalid data. Skipping."); continue
                                std_task_id_for_row = get_std_ship_task_id_from_name(db, task_name_val, current_user_db.id)
                                emp_id_for_row = get_employee_id_from_name(db, emp_name_val, current_user_db.id)
                                if not std_task_id_for_row or not emp_id_for_row: st.error(f"Row {index+1} (Ship Tasks): Invalid task/employee. Skipping."); continue
                                if pst_id: # Update
                                    pst_to_update = db.query(ProductShippingTask).filter(ProductShippingTask.id == pst_id, ProductShippingTask.product_id == selected_product_object.id).first()
                                    if pst_to_update:
                                        changed = False
                                        if pst_to_update.standard_task_id != std_task_id_for_row: pst_to_update.standard_task_id = std_task_id_for_row; changed=True
                                        if pst_to_update.employee_id != emp_id_for_row: pst_to_update.employee_id = emp_id_for_row; changed=True
                                        if pst_to_update.time_minutes != float(time_val): pst_to_update.time_minutes = float(time_val); changed=True
                                        if pst_to_update.items_processed_in_task != int(items_val): pst_to_update.items_processed_in_task = int(items_val); changed=True
                                        if changed: st.toast(f"Updated ship task ID: {pst_id}", icon="🔄")
                                elif pst_id is None: # Add
                                    db.add(ProductShippingTask(product_id=selected_product_object.id, standard_task_id=std_task_id_for_row, 
                                                               employee_id=emp_id_for_row, time_minutes=float(time_val), items_processed_in_task=int(items_val)))
                                    st.toast(f"Added ship task: {task_name_val}", icon="➕")
                            db.commit(); st.success(f"Shipping tasks saved!")
                            st.session_state[snapshot_key_pst] = edited_df_pst.copy()
                            st.rerun()
                        except Exception as e: db.rollback(); st.error(f"Error saving ship tasks: {e}"); st.exception(e)

                with st.expander("📦 Other Product Specific Costs & Pricing", expanded=False):
                    st.markdown("#### Packaging Costs (per Item)")
                    col_pkg1, col_pkg2 = st.columns(2)
                    # Ensure default values from model are used if attribute is None
                    pkg_label_cost = selected_product_object.packaging_label_cost if selected_product_object.packaging_label_cost is not None else 0.0
                    pkg_material_cost = selected_product_object.packaging_material_cost if selected_product_object.packaging_material_cost is not None else 0.0

                    new_pkg_label_cost = col_pkg1.number_input("Label Cost/Item (€)", value=float(pkg_label_cost), min_value=0.0, format="%.3f", key=f"pkg_label_{selected_product_object.id}")
                    new_pkg_material_cost = col_pkg2.number_input("Other Pkg Materials Cost/Item (€)", value=float(pkg_material_cost), min_value=0.0, format="%.3f", key=f"pkg_mat_{selected_product_object.id}")

                    st.markdown("#### Salary & Overhead Allocation")
                    salaried_employees_db = db.query(Employee).join(GlobalSalary, GlobalSalary.employee_id == Employee.id, isouter=True).filter(Employee.user_id == current_user_db.id).all() # isouter=True to include employees without global salary for selection
                    
                    # Filter for employees who actually have a global salary for allocation purposes
                    allocatable_salaried_employees = [emp for emp in salaried_employees_db if emp.global_salary_entry]
                    salaried_employee_options = {emp.name: emp.id for emp in allocatable_salaried_employees}
                    salaried_employee_names = ["None"] + list(salaried_employee_options.keys())
                    
                    current_salary_alloc_emp_name = "None"
                    if selected_product_object.salary_allocation_employee_id and selected_product_object.salary_alloc_employee_ref:
                        current_salary_alloc_emp_name = selected_product_object.salary_alloc_employee_ref.name
                    
                    idx_sal_emp = 0
                    if current_salary_alloc_emp_name in salaried_employee_names:
                        idx_sal_emp = salaried_employee_names.index(current_salary_alloc_emp_name)

                    selected_salary_emp_name = st.selectbox("Allocate Salary of Employee (must have Global Salary)", options=salaried_employee_names, 
                                                            index=idx_sal_emp, key=f"sal_alloc_emp_{selected_product_object.id}")
                    
                    sal_alloc_items = selected_product_object.salary_allocation_items_per_month if selected_product_object.salary_allocation_items_per_month is not None else 1000
                    new_sal_alloc_items = st.number_input("Items of THIS Product per Month (for salary allocation)", value=int(sal_alloc_items), min_value=1, format="%d", key=f"sal_alloc_items_{selected_product_object.id}")
                    
                    rent_alloc_items = selected_product_object.rent_utilities_allocation_items_per_month if selected_product_object.rent_utilities_allocation_items_per_month is not None else 1000
                    new_rent_alloc_items = st.number_input("Items of THIS Product per Month (for rent/utilities)", value=int(rent_alloc_items), min_value=1, format="%d", key=f"rent_alloc_items_{selected_product_object.id}")
                    
                    st.markdown("#### Online Selling Fees - Retail")
                    sp = selected_product_object # shorthand
                    new_ret_ao = st.number_input("Avg Retail Order Value (€)", value=float(sp.retail_avg_order_value or 0.0), min_value=0.0, format="%.2f", key=f"ret_ao_{sp.id}")
                    new_ret_cc = st.number_input("Retail Credit Card Fee (%)", value=float(sp.retail_cc_fee_percent or 0.0), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ret_cc_{sp.id}")
                    new_ret_plat = st.number_input("Retail Platform Fee (%)", value=float(sp.retail_platform_fee_percent or 0.0), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ret_plat_{sp.id}")
                    new_ret_ship = st.number_input("Retail Avg Shipping Paid by You (€)", value=float(sp.retail_shipping_cost_paid_by_you or 0.0), min_value=0.0, format="%.2f", key=f"ret_ship_{sp.id}")

                    st.markdown("#### Online Selling Fees - Wholesale")
                    new_ws_ao = st.number_input("Avg Wholesale Order Value (€)", value=float(sp.wholesale_avg_order_value or 0.0), min_value=0.0, format="%.2f", key=f"ws_ao_{sp.id}")
                    new_ws_comm = st.number_input("Wholesale Commission (%)", value=float(sp.wholesale_commission_percent or 0.0), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ws_comm_{sp.id}")
                    new_ws_proc = st.number_input("Wholesale Payment Processing Fee (%)", value=float(sp.wholesale_processing_fee_percent or 0.0), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ws_proc_{sp.id}")
                    new_ws_flat = st.number_input("Wholesale Flat Fee per Order (€)", value=float(sp.wholesale_flat_fee_per_order or 0.0), min_value=0.0, format="%.2f", key=f"ws_flat_{sp.id}")

                    st.markdown("#### Pricing Strategy")
                    col_price1, col_price2, col_price3 = st.columns(3)
                    new_ws_price = col_price1.number_input("Wholesale Price/Item (€)", value=float(sp.wholesale_price_per_item or 0.0), min_value=0.0, format="%.2f", key=f"ws_price_{sp.id}")
                    new_rt_price = col_price2.number_input("Retail Price/Item (€)", value=float(sp.retail_price_per_item or 0.0), min_value=0.0, format="%.2f", key=f"rt_price_{sp.id}")
                    new_buffer = col_price3.slider("Buffer Percentage", min_value=0.0, max_value=1.0, value=float(sp.buffer_percentage or 0.0), step=0.01, format="%.2f", key=f"buffer_{sp.id}")
                    
                    st.markdown("#### Distribution")
                    new_dist_ws = st.slider("Wholesale Distribution (%)", min_value=0.0, max_value=1.0, value=float(sp.distribution_wholesale_percentage or 0.0), step=0.01, format="%.2f", key=f"dist_ws_{sp.id}")
                    st.metric("Retail Distribution (%)", f"{(1.0 - new_dist_ws):.0%}")

                    if st.button(f"Save Other Costs & Pricing for {sp.product_name}", key=f"save_other_costs_{sp.id}"):
                        try:
                            sp.packaging_label_cost = new_pkg_label_cost
                            sp.packaging_material_cost = new_pkg_material_cost
                            sp.salary_allocation_employee_id = salaried_employee_options.get(selected_salary_emp_name) # Will be None if "None" is selected
                            sp.salary_allocation_items_per_month = new_sal_alloc_items
                            sp.rent_utilities_allocation_items_per_month = new_rent_alloc_items
                            sp.retail_avg_order_value = new_ret_ao
                            sp.retail_cc_fee_percent = new_ret_cc
                            sp.retail_platform_fee_percent = new_ret_plat
                            sp.retail_shipping_cost_paid_by_you = new_ret_ship
                            sp.wholesale_avg_order_value = new_ws_ao
                            sp.wholesale_commission_percent = new_ws_comm
                            sp.wholesale_processing_fee_percent = new_ws_proc
                            sp.wholesale_flat_fee_per_order = new_ws_flat
                            sp.wholesale_price_per_item = new_ws_price
                            sp.retail_price_per_item = new_rt_price
                            sp.buffer_percentage = new_buffer
                            sp.distribution_wholesale_percentage = new_dist_ws
                            
                            db.add(sp); db.commit(); st.success("Other costs and pricing saved!"); st.rerun()
                        except Exception as e: db.rollback(); st.error(f"Error saving other costs: {e}"); st.exception(e)

    elif choice == "Global Costs/Salaries":
        st.header("🌍 Global Costs & Salaries")
        st.info("Manage global fixed costs and monthly salaries here.")
        with st.expander("Monthly Fixed Overheads", expanded=True):
            global_costs_obj = db.query(GlobalCosts).filter(GlobalCosts.user_id == current_user_db.id).first()
            if not global_costs_obj: global_costs_obj = GlobalCosts(user_id=current_user_db.id, monthly_rent=0.0, monthly_utilities=0.0)
            
            rent_val = st.number_input("Global Monthly Rent (€)", value=float(global_costs_obj.monthly_rent or 0.0), min_value=0.0, format="%.2f", key="global_rent")
            util_val = st.number_input("Global Monthly Utilities (€)", value=float(global_costs_obj.monthly_utilities or 0.0), min_value=0.0, format="%.2f", key="global_utilities")
            
            if st.button("Save Global Overheads", key="save_global_overheads"):
                global_costs_obj.monthly_rent = rent_val
                global_costs_obj.monthly_utilities = util_val
                db.add(global_costs_obj)
                try: db.commit(); st.success("Global overheads saved!"); st.rerun()
                except Exception as e: db.rollback(); st.error(f"Error saving global overheads: {e}")
        
        st.subheader("Global Monthly Salaries")
        st.write("Edit, add, or delete global salaries. These are fixed monthly amounts for specific employees.")
        global_salaries_db = db.query(GlobalSalary).options(joinedload(GlobalSalary.employee_ref)).filter(GlobalSalary.user_id == current_user_db.id).order_by(GlobalSalary.id).all()
        all_employees_list = db.query(Employee).filter(Employee.user_id == current_user_db.id).all()
        employee_options_gs = {emp.name: emp.id for emp in all_employees_list}
        employee_names_gs = list(employee_options_gs.keys()) if employee_options_gs else ["No employees defined"]
        
        data_for_gs_editor = []
        if global_salaries_db:
            for gs in global_salaries_db:
                if gs.employee_ref: # Ensure employee_ref is loaded
                     data_for_gs_editor.append({"ID": gs.id, "Employee Name": gs.employee_ref.name, "Monthly Salary (€)": gs.monthly_amount})

        df_gs_cols = ["ID", "Employee Name", "Monthly Salary (€)"]
        df_gs_for_editor = pd.DataFrame(data_for_gs_editor, columns=df_gs_cols)
        if df_gs_for_editor.empty:
            df_gs_for_editor = pd.DataFrame(columns=df_gs_cols).astype({"ID":"float64", "Employee Name":"object", "Monthly Salary (€)":"float64"})

        snapshot_key_gs = 'df_gs_snapshot'
        if snapshot_key_gs not in st.session_state or not st.session_state[snapshot_key_gs].columns.equals(df_gs_for_editor.columns):
            st.session_state[snapshot_key_gs] = df_gs_for_editor.copy()

        edited_df_gs = st.data_editor(st.session_state[snapshot_key_gs], num_rows="dynamic", key="global_salaries_editor",
            column_config={
                "ID": id_col_config, 
                "Employee Name": st.column_config.SelectboxColumn("Employee*", options=employee_names_gs, required=True), 
                "Monthly Salary (€)": st.column_config.NumberColumn("Monthly Salary (€)*", required=True, min_value=0.0, step=10.0, format="%.2f")
            }, use_container_width=True, hide_index=True)

        if st.button("Save Global Salaries"):
            try:
                original_df_snapshot_gs = st.session_state[snapshot_key_gs]
                original_snapshot_ids_gs = set(original_df_snapshot_gs['ID'].dropna().astype(int))
                edited_df_ids_gs = set(edited_df_gs['ID'].dropna().astype(int))
                ids_to_delete_from_db_gs = original_snapshot_ids_gs - edited_df_ids_gs

                for gs_id_del in ids_to_delete_from_db_gs:
                    gs_to_del = db.query(GlobalSalary).filter(GlobalSalary.id == gs_id_del, GlobalSalary.user_id == current_user_db.id).first()
                    if gs_to_del: db.delete(gs_to_del); st.toast(f"Deleted global salary ID: {gs_id_del}", icon="➖")

                for index, row in edited_df_gs.iterrows():
                    gs_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                    emp_name_val, amount_val = row.get("Employee Name"), row.get("Monthly Salary (€)")
                    if not all([emp_name_val, emp_name_val != "No employees defined", pd.notna(amount_val)]):
                        if gs_id is None and not any([emp_name_val, pd.notna(amount_val)]): continue
                        st.error(f"Row {index+1} (Global Salaries): Invalid data. Skipping."); continue
                    
                    employee_id_for_gs = employee_options_gs.get(emp_name_val)
                    if not employee_id_for_gs: st.error(f"Row {index+1} (Global Salaries): Employee '{emp_name_val}' not found. Skipping."); continue

                    if gs_id: # Update
                        gs_to_update = db.query(GlobalSalary).filter(GlobalSalary.id == gs_id, GlobalSalary.user_id == current_user_db.id).first()
                        if gs_to_update:
                            changed = False
                            if gs_to_update.employee_id != employee_id_for_gs: gs_to_update.employee_id = employee_id_for_gs; changed=True
                            if gs_to_update.monthly_amount != float(amount_val): gs_to_update.monthly_amount = float(amount_val); changed=True
                            if changed: st.toast(f"Updated global salary ID: {gs_id}", icon="🔄")
                    elif gs_id is None: # Add
                        existing_salary = db.query(GlobalSalary).filter(GlobalSalary.user_id == current_user_db.id, GlobalSalary.employee_id == employee_id_for_gs).first()
                        if existing_salary: st.warning(f"Employee '{emp_name_val}' already has a global salary. Edit existing. Skipping addition."); continue
                        db.add(GlobalSalary(user_id=current_user_db.id, employee_id=employee_id_for_gs, monthly_amount=float(amount_val)))
                        st.toast(f"Added global salary for {emp_name_val}", icon="➕")
                db.commit(); st.success("Global salaries saved!")
                st.session_state[snapshot_key_gs] = edited_df_gs.copy()
                st.rerun()
            except IntegrityError: db.rollback(); st.error("Error: An employee can only have one global salary entry. Please ensure no duplicates by employee.")
            except Exception as e: db.rollback(); st.error(f"Error saving global salaries: {e}"); st.exception(e)

    elif choice == "Product Cost Breakdown":
        st.header("📊 View Product Cost Breakdown")
        st.info("This feature is under development. Cost calculation logic and display will be implemented here.")
        # Placeholder for selecting product and showing breakdown
        # You would query products, let user select one, then calculate and display costs.

    elif choice == "User Settings":
        st.header("⚙️ User Settings")
        st.write("Manage your user profile and application settings.")
        
        st.subheader("Profile Information")
        st.write(f"**Username:** {current_user_db.username}")
        st.write(f"**Email:** {current_user_db.email}")
        st.write(f"**Name:** {current_user_db.name if current_user_db.name else 'Not set'}")

        st.subheader("Update Password")
        try:
            if authenticator.reset_password(username, 'Reset password'): # Location can be 'main' or 'sidebar'
                st.success('Password reset successfully! Please check your email if configured, or note the new password if shown.')
                # Update config.yaml if reset_password modified it (depends on authenticator's implementation)
                with open(CONFIG_FILE_PATH, 'w') as file: yaml.dump(config_auth, file, default_flow_style=False, allow_unicode=True)
        except Exception as e_pw:
            st.error(f"Error during password reset widget: {e_pw}")
        
        st.subheader("Update User Details")
        try:
            # The update_user_details method in streamlit-authenticator typically handles form display and logic
            if authenticator.update_user_details(username, 'Update user details'):
                st.success('User details updated successfully!')
                # config_auth would have been updated by the authenticator library
                with open(CONFIG_FILE_PATH, 'w') as file:
                    yaml.dump(config_auth, file, default_flow_style=False, allow_unicode=True)
                st.rerun() # Rerun to reflect changes, e.g., updated name in sidebar
        except Exception as e_details:
            st.error(f"Error updating details: {e_details}")

    db.close()

elif authentication_status is False:
    st.error("Username/password is incorrect. Please try again.")
    try:
        if st.checkbox("Forgot Password?"):
            # Note: forgot_password returns: username_forgot_pw, email_forgot_pw, new_random_password
            # You need to implement the secure delivery of this new_random_password
            forgot_password_response = authenticator.forgot_password('Forgot password')
            if forgot_password_response:
                st.success('If your username exists, instructions to reset your password will be sent (not really, this is a placeholder).')
                # Actual implementation would involve emailing new_random_password
            elif forgot_password_response is False: # Explicitly False if username not found
                st.error('Username not found.')
        
        if st.checkbox("Forgot Username?"):
            # Note: forgot_username returns: username_of_forgotten_username, email_of_forgotten_username
            forgot_username_response = authenticator.forgot_username('Forgot username')
            if forgot_username_response:
                st.success('If your email exists, your username will be sent (not really, this is a placeholder).')
            elif forgot_username_response is False: # Explicitly False if email not found
                st.error('Email not found.')

    except Exception as e_recovery: 
        st.error(f"Account recovery error: {e_recovery}")

elif authentication_status is None:
    st.warning("Please enter your username and password to login, or register if you are a new user.")
    # Registration form
    # Ensure preauthorized emails are loaded if you use that feature
    pre_authorized_emails = config_auth.get('preauthorized', {}).get('emails', [])
    try:
        register_user_response = authenticator.register_user('Register user', pre_authorization=True if pre_authorized_emails else False)
        if register_user_response:
            st.success('User registered successfully! Please login.')
            # config_auth is updated by the authenticator library after successful registration
            with open(CONFIG_FILE_PATH, 'w') as file:
                yaml.dump(config_auth, file, default_flow_style=False, allow_unicode=True)
            st.rerun()
    except Exception as e_register:
        st.error(f"Registration error: {e_register}")


st.markdown("---")
st.markdown(f"Product Cost Calculator © {datetime.date.today().year}")
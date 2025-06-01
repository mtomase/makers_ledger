# product_cost_calculator_app.py

import streamlit as st
import streamlit_authenticator as stauth
from streamlit_option_menu import option_menu # Ensure this is in requirements.txt
import yaml
from yaml.loader import SafeLoader
import os
import datetime
import pandas as pd
import re
from decimal import Decimal, ROUND_HALF_UP

# --- Detailed Configuration File Path and Permission Check ---
CONFIG_FILE_PATH = None
config_auth_diagnostic_check = None 

try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, 'config.yaml')

    # print(f"DEBUG: Expected config file location: {CONFIG_FILE_PATH}") # Local debug

    if not os.path.exists(CONFIG_FILE_PATH):
        # print(f"ERROR: Config file does NOT exist at {CONFIG_FILE_PATH}") # Local debug
        st.error(f"❌ CRITICAL: Config file does NOT exist at the expected location: `{CONFIG_FILE_PATH}`. Please create `config.yaml` in the same directory as your script or check the path.")
        st.stop()
    # else: print(f"INFO: Config file found at {CONFIG_FILE_PATH}.") # Local debug

    if not os.access(CONFIG_FILE_PATH, os.R_OK):
        # print(f"ERROR: Read permission DENIED for config file at {CONFIG_FILE_PATH}.") # Local debug
        st.error(f"❌ CRITICAL: Read permission DENIED for config file at `{CONFIG_FILE_PATH}`.")
        st.markdown(f"""Please check the file system permissions... (details omitted for brevity)""")
        st.stop()
    # else: print(f"INFO: Read permission GRANTED for config file.") # Local debug

    if not os.access(CONFIG_FILE_PATH, os.W_OK):
        # print(f"WARNING: Write permission DENIED for config file at {CONFIG_FILE_PATH}.") # Local debug
        st.warning(f"⚠️ Write permission DENIED for config file at `{CONFIG_FILE_PATH}`. Login might work, but user registration or password/detail updates by the authenticator will likely fail.")
    # else: print(f"INFO: Write permission GRANTED for config file.") # Local debug

    # print("INFO: Attempting to open the file for reading to load YAML...") # Local debug
    with open(CONFIG_FILE_PATH, 'r') as file:
        config_auth_diagnostic_check = yaml.load(file, Loader=SafeLoader)
    # print(f"INFO: Successfully opened and loaded YAML from {CONFIG_FILE_PATH}.") # Local debug

except Exception as e: # Catching a broader range of startup errors for config
    st.error(f"❌ CRITICAL ERROR during configuration file setup: {e}")
    st.exception(e)
    st.info("Ensure 'config.yaml' exists, is readable/writable, and is valid YAML.")
    st.stop()
# --- End of Detailed Configuration File Path and Permission Check ---


# --- Database Setup ---
from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file

try:
    from models import (
        User, Ingredient, Employee, Product, GlobalCosts, GlobalSalary,
        StandardProductionTask, StandardShippingTask,
        ProductMaterial, ProductProductionTask, ProductShippingTask,
        init_db_structure, get_db, SessionLocal, engine # Assuming get_db yields a session
    )
    from sqlalchemy.orm import Session, joinedload, selectinload
    from sqlalchemy.exc import IntegrityError, SQLAlchemyError
except ImportError as e_models: 
    st.error(f"Error importing database models: {e_models}. Ensure models.py is correct and accessible.")
    st.exception(e_models)
    st.stop()
except Exception as e_db_setup: 
    st.error(f"An error occurred during database setup: {e_db_setup}")
    st.exception(e_db_setup)
    st.stop()

# --- Page Configuration ---
st.set_page_config(page_title="Product Cost Calculator", layout="wide", initial_sidebar_state="expanded")

# --- Helper Functions (Copied from your provided working script) ---
def create_ingredient_display_string(name, provider):
    if provider:
        return f"{name} (Provider: {provider})"
    return name

def parse_ingredient_display_string(display_string):
    if display_string is None: return None, None
    match = re.match(r"^(.*?) \(Provider: (.*?)\)$", display_string)
    if match: return match.group(1), match.group(2)
    return display_string, None

def get_ingredient_id_from_display(db_session, display_string, user_id):
    name, provider = parse_ingredient_display_string(display_string)
    if not name: return None
    filters = [Ingredient.user_id == user_id, Ingredient.name == name]
    if provider is not None:
        filters.append(Ingredient.provider == provider)
    else:
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

def format_currency(value):
    if pd.notna(value) and isinstance(value, (int, float, Decimal)):
        if isinstance(value, Decimal): 
            return f"€{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"
        return f"€{float(value):,.2f}" 
    return "N/A"

def format_percentage(value):
    if pd.notna(value) and isinstance(value, (int, float, Decimal)):
        if isinstance(value, Decimal):
            return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"
        return f"{float(value):.2f}%"
    return "N/A"

def format_decimal_for_table(value, precision='0.001'):
    if pd.notna(value) and isinstance(value, Decimal):
        return f"{value.quantize(Decimal(precision), rounding=ROUND_HALF_UP)}"
    elif pd.notna(value) and isinstance(value, (int,float)):
        return f"{float(value):.{len(precision.split('.')[1])}f}" 
    return "N/A"

# --- Cost Breakdown Calculation Function (Copied from your provided working script) ---
def calculate_cost_breakdown(product_id: int, db: Session, current_user_id: int):
    product = db.query(Product).options(
        selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref),
        selectinload(Product.production_tasks).joinedload(ProductProductionTask.employee_ref),
        selectinload(Product.production_tasks).joinedload(ProductProductionTask.standard_task_ref),
        selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.employee_ref),
        selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.standard_task_ref),
        joinedload(Product.salary_alloc_employee_ref).joinedload(Employee.global_salary_entry)
    ).filter(Product.id == product_id, Product.user_id == current_user_id).first()

    if not product:
        return None
    breakdown = {}
    # I. Direct Material Costs
    material_details = []
    total_material_cost_per_item = Decimal('0.0')
    for pm in product.materials:
        if pm.ingredient_ref:
            ing = pm.ingredient_ref
            qty_grams = Decimal(str(pm.quantity_grams)) if pd.notna(pm.quantity_grams) else Decimal('0.0')
            price_per_unit = Decimal(str(ing.price_per_unit)) if pd.notna(ing.price_per_unit) else Decimal('0.0')
            unit_kg = Decimal(str(ing.unit_quantity_kg)) if pd.notna(ing.unit_quantity_kg) and ing.unit_quantity_kg > 0 else Decimal('1.0')
            cost = (qty_grams / Decimal('1000.0')) * (price_per_unit / unit_kg) if unit_kg > Decimal('0.0') else Decimal('0.0')
            total_material_cost_per_item += cost
            material_details.append({"Ingredient": ing.name, "Provider": ing.provider or "-","Qty (g)": qty_grams, "Cost": cost})
    breakdown['material_details'] = material_details
    breakdown['total_material_cost_per_item'] = total_material_cost_per_item
    # II. Direct Labor Costs (Production)
    prod_labor_details = []
    total_production_labor_cost_per_item = Decimal('0.0')
    for ppt in product.production_tasks:
        if ppt.employee_ref:
            emp = ppt.employee_ref
            time_min = Decimal(str(ppt.time_minutes)) if pd.notna(ppt.time_minutes) else Decimal('0.0')
            hourly_rate = Decimal(str(emp.hourly_rate)) if pd.notna(emp.hourly_rate) else Decimal('0.0')
            items_proc = Decimal(str(ppt.items_processed_in_task)) if pd.notna(ppt.items_processed_in_task) and ppt.items_processed_in_task > 0 else Decimal('1.0')
            cost = (time_min / Decimal('60.0')) * hourly_rate
            cost_per_item = cost / items_proc if items_proc > Decimal('0.0') else Decimal('0.0')
            total_production_labor_cost_per_item += cost_per_item
            prod_labor_details.append({"Task": ppt.standard_task_ref.task_name if ppt.standard_task_ref else "N/A", "Employee": emp.name, "Time (min)": time_min, "Items in Task": items_proc, "Cost": cost_per_item})
    breakdown['prod_labor_details'] = prod_labor_details
    breakdown['total_production_labor_cost_per_item'] = total_production_labor_cost_per_item
    # III. Direct Labor Costs (Shipping)
    ship_labor_details = []
    total_shipping_labor_cost_per_item = Decimal('0.0')
    for pst in product.shipping_tasks:
        if pst.employee_ref:
            emp = pst.employee_ref
            time_min = Decimal(str(pst.time_minutes)) if pd.notna(pst.time_minutes) else Decimal('0.0')
            hourly_rate = Decimal(str(emp.hourly_rate)) if pd.notna(emp.hourly_rate) else Decimal('0.0')
            items_proc = Decimal(str(pst.items_processed_in_task)) if pd.notna(pst.items_processed_in_task) and pst.items_processed_in_task > 0 else Decimal('1.0')
            cost = (time_min / Decimal('60.0')) * hourly_rate
            cost_per_item = cost / items_proc if items_proc > Decimal('0.0') else Decimal('0.0')
            total_shipping_labor_cost_per_item += cost_per_item
            ship_labor_details.append({"Task": pst.standard_task_ref.task_name if pst.standard_task_ref else "N/A", "Employee": emp.name, "Time (min)": time_min, "Items in Task": items_proc, "Cost": cost_per_item})
    breakdown['ship_labor_details'] = ship_labor_details
    breakdown['total_shipping_labor_cost_per_item'] = total_shipping_labor_cost_per_item
    # IV. Packaging Costs
    pkg_label_cost = Decimal(str(product.packaging_label_cost)) if pd.notna(product.packaging_label_cost) else Decimal('0.0')
    pkg_material_cost = Decimal(str(product.packaging_material_cost)) if pd.notna(product.packaging_material_cost) else Decimal('0.0')
    breakdown['packaging_label_cost_per_item'] = pkg_label_cost
    breakdown['packaging_material_cost_per_item'] = pkg_material_cost
    breakdown['total_packaging_cost_per_item'] = pkg_label_cost + pkg_material_cost
    # V. Subtotal Direct COGS
    breakdown['direct_cogs_per_item'] = (total_material_cost_per_item + total_production_labor_cost_per_item + total_shipping_labor_cost_per_item + breakdown['total_packaging_cost_per_item'])
    # VI. Allocated Overheads
    allocated_salary_cost_per_item = Decimal('0.0')
    if product.salary_allocation_employee_id and product.salary_alloc_employee_ref and product.salary_alloc_employee_ref.global_salary_entry and pd.notna(product.salary_allocation_items_per_month) and product.salary_allocation_items_per_month > 0:
        monthly_salary = Decimal(str(product.salary_alloc_employee_ref.global_salary_entry.monthly_amount)) if pd.notna(product.salary_alloc_employee_ref.global_salary_entry.monthly_amount) else Decimal('0.0')
        alloc_items = Decimal(str(product.salary_allocation_items_per_month))
        allocated_salary_cost_per_item = monthly_salary / alloc_items if alloc_items > Decimal('0.0') else Decimal('0.0')
    breakdown['allocated_salary_cost_per_item'] = allocated_salary_cost_per_item
    allocated_rent_utilities_cost_per_item = Decimal('0.0')
    global_costs_obj = db.query(GlobalCosts).filter(GlobalCosts.user_id == current_user_id).first()
    if global_costs_obj and pd.notna(product.rent_utilities_allocation_items_per_month) and product.rent_utilities_allocation_items_per_month > 0:
        rent = Decimal(str(global_costs_obj.monthly_rent)) if pd.notna(global_costs_obj.monthly_rent) else Decimal('0.0')
        utilities = Decimal(str(global_costs_obj.monthly_utilities)) if pd.notna(global_costs_obj.monthly_utilities) else Decimal('0.0')
        total_monthly_fixed_overheads = rent + utilities
        alloc_items_rent = Decimal(str(product.rent_utilities_allocation_items_per_month))
        allocated_rent_utilities_cost_per_item = total_monthly_fixed_overheads / alloc_items_rent if alloc_items_rent > Decimal('0.0') else Decimal('0.0')
    breakdown['allocated_rent_utilities_cost_per_item'] = allocated_rent_utilities_cost_per_item
    breakdown['total_allocated_overheads_per_item'] = allocated_salary_cost_per_item + allocated_rent_utilities_cost_per_item
    # VII. Total Production Cost
    breakdown['total_production_cost_per_item'] = breakdown['direct_cogs_per_item'] + breakdown['total_allocated_overheads_per_item']
    # VIII. Selling Channel Costs & Profitability (Retail)
    retail_price = Decimal(str(product.retail_price_per_item)) if pd.notna(product.retail_price_per_item) else Decimal('0.0')
    items_per_retail_order = Decimal('1.0')
    retail_avg_order_val = Decimal(str(product.retail_avg_order_value)) if pd.notna(product.retail_avg_order_value) else Decimal('0.0')
    if retail_avg_order_val > Decimal('0.0') and retail_price > Decimal('0.0'): items_per_retail_order = retail_avg_order_val / retail_price
    if items_per_retail_order <= Decimal('0.0'): items_per_retail_order = Decimal('1.0') 
    retail_cc_fee_percent_val = Decimal(str(product.retail_cc_fee_percent)) if pd.notna(product.retail_cc_fee_percent) else Decimal('0.0')
    retail_platform_fee_percent_val = Decimal(str(product.retail_platform_fee_percent)) if pd.notna(product.retail_platform_fee_percent) else Decimal('0.0')
    retail_shipping_cost_paid_val = Decimal(str(product.retail_shipping_cost_paid_by_you)) if pd.notna(product.retail_shipping_cost_paid_by_you) else Decimal('0.0')
    retail_cc_fee = retail_price * retail_cc_fee_percent_val
    retail_platform_fee = retail_price * retail_platform_fee_percent_val
    retail_shipping_per_item = retail_shipping_cost_paid_val / items_per_retail_order
    total_retail_channel_costs = retail_cc_fee + retail_platform_fee + retail_shipping_per_item
    total_cost_retail_item = breakdown['total_production_cost_per_item'] + total_retail_channel_costs
    profit_retail = retail_price - total_cost_retail_item
    margin_retail = (profit_retail / retail_price) * Decimal('100.0') if retail_price > Decimal('0.0') else Decimal('0.0')
    breakdown['retail_metrics'] = {"price": retail_price, "cc_fee": retail_cc_fee, "platform_fee": retail_platform_fee, "shipping_cost": retail_shipping_per_item, "total_channel_costs": total_retail_channel_costs, "total_cost_item": total_cost_retail_item, "profit": profit_retail, "margin_percent": margin_retail}
    # VIII. Selling Channel Costs & Profitability (Wholesale)
    wholesale_price = Decimal(str(product.wholesale_price_per_item)) if pd.notna(product.wholesale_price_per_item) else Decimal('0.0')
    items_per_ws_order = Decimal('1.0')
    ws_avg_order_val = Decimal(str(product.wholesale_avg_order_value)) if pd.notna(product.wholesale_avg_order_value) else Decimal('0.0')
    if ws_avg_order_val > Decimal('0.0') and wholesale_price > Decimal('0.0'): items_per_ws_order = ws_avg_order_val / wholesale_price
    if items_per_ws_order <= Decimal('0.0'): items_per_ws_order = Decimal('1.0')
    ws_commission_percent_val = Decimal(str(product.wholesale_commission_percent)) if pd.notna(product.wholesale_commission_percent) else Decimal('0.0')
    ws_processing_fee_percent_val = Decimal(str(product.wholesale_processing_fee_percent)) if pd.notna(product.wholesale_processing_fee_percent) else Decimal('0.0')
    ws_flat_fee_per_order_val = Decimal(str(product.wholesale_flat_fee_per_order)) if pd.notna(product.wholesale_flat_fee_per_order) else Decimal('0.0')
    ws_commission = wholesale_price * ws_commission_percent_val
    ws_processing_fee = wholesale_price * ws_processing_fee_percent_val
    ws_flat_fee_per_item = ws_flat_fee_per_order_val / items_per_ws_order
    total_wholesale_channel_costs = ws_commission + ws_processing_fee + ws_flat_fee_per_item
    total_cost_wholesale_item = breakdown['total_production_cost_per_item'] + total_wholesale_channel_costs
    profit_wholesale = wholesale_price - total_cost_wholesale_item
    margin_wholesale = (profit_wholesale / wholesale_price) * Decimal('100.0') if wholesale_price > Decimal('0.0') else Decimal('0.0')
    breakdown['wholesale_metrics'] = {"price": wholesale_price, "commission": ws_commission, "processing_fee": ws_processing_fee, "flat_fee_item_share": ws_flat_fee_per_item, "total_channel_costs": total_wholesale_channel_costs, "total_cost_item": total_cost_wholesale_item, "profit": profit_wholesale, "margin_percent": margin_wholesale}
    # IX. Blended Metrics
    ws_dist_val = Decimal(str(product.distribution_wholesale_percentage)) if pd.notna(product.distribution_wholesale_percentage) else Decimal('0.0')
    rt_dist_val = Decimal('1.0') - ws_dist_val
    breakdown['blended_avg_price'] = (retail_price * rt_dist_val) + (wholesale_price * ws_dist_val)
    breakdown['blended_avg_total_cost'] = (total_cost_retail_item * rt_dist_val) + (total_cost_wholesale_item * ws_dist_val)
    breakdown['blended_avg_profit'] = breakdown['blended_avg_price'] - breakdown['blended_avg_total_cost']
    breakdown['blended_avg_margin_percent'] = (breakdown['blended_avg_profit'] / breakdown['blended_avg_price']) * Decimal('100.0') if breakdown['blended_avg_price'] > Decimal('0.0') else Decimal('0.0')
    # X. Buffer & Target Pricing
    buffer_percentage_val = Decimal(str(product.buffer_percentage)) if pd.notna(product.buffer_percentage) else Decimal('0.0')
    breakdown['cost_plus_buffer'] = breakdown['total_production_cost_per_item'] * (Decimal('1.0') + buffer_percentage_val)
    return breakdown

# --- Authenticator Setup ---
config_auth = config_auth_diagnostic_check # Use the loaded config

if 'credentials' not in config_auth or 'usernames' not in config_auth['credentials']:
    st.error("CRITICAL: 'credentials' or 'credentials.usernames' not found in the loaded config_auth. Please create/register a user first or fix the config content.")
    # Initialize to prevent further errors if config is truly minimal
    config_auth['credentials'] = config_auth.get('credentials', {})
    config_auth['credentials']['usernames'] = config_auth['credentials'].get('usernames', {})

if not config_auth.get('cookie', {}).get('name') or not config_auth.get('cookie', {}).get('key'):
    st.error("CRITICAL: Cookie 'name' and 'key' must be set in config_auth (from config.yaml)."); st.stop()

authenticator = stauth.Authenticate(
    config_auth['credentials'],
    config_auth['cookie']['name'],
    config_auth['cookie']['key'],
    config_auth['cookie']['expiry_days'],
    pre_authorized=config_auth.get('preauthorized', {}).get('emails', [])
)

try:
    authenticator.login() # Renders login and registration form
except Exception as e_login_widget: # Catch potential errors from the widget itself
    st.error(f"An error occurred with the login/registration widget: {e_login_widget}")
    st.exception(e_login_widget)
    # Potentially stop if login widget itself fails critically, though often it handles its own errors.

authentication_status = st.session_state.get("authentication_status")
username = st.session_state.get("username")

# Initialize selected_product_id if not already in session state
if 'selected_product_id' not in st.session_state: 
    st.session_state.selected_product_id = None


# --- Main Application Logic ---
if authentication_status:
    user_display_name = st.session_state.get("name", username) # Use 'name' from session if available
    db_session_main_app = None # Initialize to ensure it's defined for finally block

    try:
        db_session_main_app = next(get_db()) # Obtain a new session for the authenticated part
        current_user_db = db_session_main_app.query(User).filter(User.username == username).first()
        if not current_user_db: 
            st.error(f"User '{username}' not found in the application database. Please contact support."); 
            st.stop()

        with st.sidebar:
            st.success(f"Welcome, **{user_display_name}**!")
            authenticator.logout("Logout", "sidebar", key='sidebar_logout_button')
            st.markdown("---")
            menu_titles = [
                "Manage Ingredients", "Manage Employees", 
                "Manage Production Tasks", "Manage Shipping Tasks", 
                "Manage Products", "Global Costs/Salaries", 
                "Product Cost Breakdown", "User Settings", 
                "User Guide"  # New section
            ]
            menu_icons = [
                "bi-basket3-fill", "bi-people-fill", "bi-tools", "bi-truck", 
                "bi-box-seam-fill", "bi-globe2", "bi-bar-chart-line-fill", 
                "bi-gear-fill", "bi-book-half"  # New icon
            ]
            
            default_selection_index = 0 # Default to the first item
            if 'main_menu_selected' in st.session_state and st.session_state.main_menu_selected in menu_titles:
                default_selection_index = menu_titles.index(st.session_state.main_menu_selected)
            else:
                st.session_state.main_menu_selected = menu_titles[default_selection_index] # Set initial if not present
                
            selected_option = option_menu(
                menu_title="🛠️ Main Menu", 
                options=menu_titles, 
                icons=menu_icons, 
                menu_icon="bi-list-task",
                default_index=default_selection_index,
                orientation="vertical", 
                key="main_menu_option_selector" # Unique key for option_menu
            )
            
            if selected_option != st.session_state.main_menu_selected:
                st.session_state.main_menu_selected = selected_option
                # Reset selected_product_id if navigating away from product-specific pages
                if selected_option not in ["Manage Products", "Product Cost Breakdown"]: 
                    st.session_state.selected_product_id = None
                st.rerun()

        choice = st.session_state.main_menu_selected
        st.title(f"🧮 Product Cost Calculator: {choice}") # Dynamic title
        
        # --- Section: Manage Ingredients ---
        if choice == "Manage Ingredients":
            st.header("📝 Manage Ingredients")
            st.write("Edit, add, or delete ingredients directly in the table below. Click **'Save Ingredient Changes'** to persist.")
            ingredients_db = db_session_main_app.query(Ingredient).filter(Ingredient.user_id == current_user_db.id).order_by(Ingredient.id).all()
            
            data_for_editor_ing = []
            for ing in ingredients_db:
                data_for_editor_ing.append({
                    "ID": ing.id, "Name": ing.name, "Provider": ing.provider, 
                    "Price/Unit (€)": ing.price_per_unit, "Unit (kg)": ing.unit_quantity_kg, 
                    "Price URL": ing.price_url if ing.price_url else ""
                })
            
            df_ing_cols = ["ID", "Name", "Provider", "Price/Unit (€)", "Unit (kg)", "Price URL"]
            df_ingredients_for_editor = pd.DataFrame(data_for_editor_ing, columns=df_ing_cols)
            if df_ingredients_for_editor.empty: # Ensure correct dtypes for empty DataFrame for data_editor
                 df_ingredients_for_editor = pd.DataFrame(columns=df_ing_cols).astype({
                    "ID": "float64", "Name": "object", "Provider": "object", 
                    "Price/Unit (€)": "float64", "Unit (kg)": "float64", "Price URL": "object"
                })

            snapshot_key_ing = 'df_ingredients_snapshot'
            if snapshot_key_ing not in st.session_state or \
               not isinstance(st.session_state.get(snapshot_key_ing), pd.DataFrame) or \
               not st.session_state[snapshot_key_ing].columns.equals(df_ingredients_for_editor.columns):
                st.session_state[snapshot_key_ing] = df_ingredients_for_editor.copy()

            ing_display_columns = ("Name", "Provider", "Price/Unit (€)", "Unit (kg)", "Price URL")
            
            edited_df_ing = st.data_editor(
                st.session_state[snapshot_key_ing], 
                num_rows="dynamic", key="ingredients_editor",
                column_order=ing_display_columns,
                column_config={
                    "Name": st.column_config.TextColumn("Ingredient Name*", required=True, help="The common name of the ingredient."),
                    "Provider": st.column_config.TextColumn("Provider (Optional)", help="Supplier or source of the ingredient."), 
                    "Price/Unit (€)": st.column_config.NumberColumn("Price per Unit (€)*", required=True, min_value=0.00, step=0.01, format="%.2f", help="Cost for the quantity specified in 'Unit (kg)'."),
                    "Unit (kg)": st.column_config.NumberColumn("Unit Quantity (kg)*", required=True, min_value=0.001, step=0.001, format="%.3f", help="The amount in kilograms this price refers to (e.g., 1 for 1kg, 0.5 for 500g)."),
                    "Price URL": st.column_config.LinkColumn("Price URL (Optional)", help="Web link to the ingredient's source or price information.")
                },
                use_container_width=True, hide_index=True
            )

            if st.button("Save Ingredient Changes", type="primary"):
                try:
                    original_df_snapshot_ing = st.session_state[snapshot_key_ing]
                    original_snapshot_ids_ing = set(original_df_snapshot_ing['ID'].dropna().astype(int))
                    edited_df_ids_ing = set(edited_df_ing['ID'].dropna().astype(int))
                    ids_to_delete_from_db_ing = original_snapshot_ids_ing - edited_df_ids_ing

                    for ing_id_del in ids_to_delete_from_db_ing:
                        ing_to_del = db_session_main_app.query(Ingredient).filter(Ingredient.id == ing_id_del, Ingredient.user_id == current_user_db.id).first()
                        if ing_to_del: db_session_main_app.delete(ing_to_del); st.toast(f"Deleted ID: {ing_id_del}", icon="➖")
                    
                    for index, row in edited_df_ing.iterrows():
                        ing_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                        name_val, prov_val = row.get("Name"), row.get("Provider")
                        price_val, unit_kg_val = row.get("Price/Unit (€)"), row.get("Unit (kg)")
                        
                        if not all([name_val, pd.notna(price_val), pd.notna(unit_kg_val)]): 
                            if ing_id is None and not any([name_val, prov_val, pd.notna(price_val), pd.notna(unit_kg_val)]): continue # Skip truly empty new rows
                            st.error(f"Row {index+1}: Name, Price/Unit, Unit (kg) are required. Skipping."); continue
                        
                        prov_val = str(prov_val).strip() if prov_val and str(prov_val).strip() else None
                        url_val = str(row.get("Price URL", "")).strip() if row.get("Price URL") and str(row.get("Price URL", "")).strip() else None


                        if ing_id: # Existing item
                            item_to_update = db_session_main_app.query(Ingredient).filter(Ingredient.id == ing_id, Ingredient.user_id == current_user_db.id).first()
                            if item_to_update:
                                changed = False
                                if item_to_update.name != name_val: item_to_update.name = name_val; changed=True
                                if item_to_update.provider != prov_val: item_to_update.provider = prov_val; changed=True
                                if item_to_update.price_per_unit != Decimal(str(price_val)): item_to_update.price_per_unit = Decimal(str(price_val)); changed=True 
                                if item_to_update.unit_quantity_kg != Decimal(str(unit_kg_val)): item_to_update.unit_quantity_kg = Decimal(str(unit_kg_val)); changed=True 
                                if item_to_update.price_url != url_val: item_to_update.price_url = url_val; changed=True
                                if changed: st.toast(f"Updated ID: {ing_id}", icon="🔄")
                        elif ing_id is None: # New item (should not happen if ID is present, but as a fallback)
                             st.warning(f"Row {index+1} has an ID but was not found for update. Treating as new if valid.")
                             db_session_main_app.add(Ingredient(user_id=current_user_db.id, name=name_val, provider=prov_val, price_per_unit=Decimal(str(price_val)), unit_quantity_kg=Decimal(str(unit_kg_val)), price_url=url_val))
                             st.toast(f"Added: {name_val}", icon="➕")
                    
                    # Handle new rows (those without an ID from the original snapshot)
                    new_rows_df = edited_df_ing[edited_df_ing['ID'].isna()]
                    for index, row in new_rows_df.iterrows():
                        name_val, prov_val = row.get("Name"), row.get("Provider")
                        price_val, unit_kg_val = row.get("Price/Unit (€)"), row.get("Unit (kg)")
                        if not all([name_val, pd.notna(price_val), pd.notna(unit_kg_val)]): 
                            if not any([name_val, prov_val, pd.notna(price_val), pd.notna(unit_kg_val)]): continue # Skip truly empty new rows
                            st.error(f"New Row (approx original index {index+1}): Name, Price/Unit, Unit (kg) are required. Skipping."); continue
                        
                        prov_val = str(prov_val).strip() if prov_val and str(prov_val).strip() else None
                        url_val = str(row.get("Price URL", "")).strip() if row.get("Price URL") and str(row.get("Price URL", "")).strip() else None
                        db_session_main_app.add(Ingredient(user_id=current_user_db.id, name=name_val, provider=prov_val, price_per_unit=Decimal(str(price_val)), unit_quantity_kg=Decimal(str(unit_kg_val)), price_url=url_val))
                        st.toast(f"Added: {name_val}", icon="➕")

                    db_session_main_app.commit(); st.success("Ingredient changes saved!")
                    st.session_state[snapshot_key_ing] = edited_df_ing.copy() # Update snapshot
                    st.rerun()
                except Exception as e_save_ing: 
                    db_session_main_app.rollback()
                    st.error(f"Error saving ingredients: {e_save_ing}")
                    st.exception(e_save_ing)

        # --- Section: Manage Employees ---
        elif choice == "Manage Employees":
            st.header("👥 Manage Employees")
            st.write("Edit, add, or delete employees. Click **'Save Employee Changes'** to persist.")
            employees_db = db_session_main_app.query(Employee).filter(Employee.user_id == current_user_db.id).order_by(Employee.id).all()
            data_for_editor_emp = [{"ID": emp.id, "Name": emp.name, "Hourly Rate (€)": emp.hourly_rate, "Role": emp.role} for emp in employees_db]
            
            df_emp_cols = ["ID", "Name", "Hourly Rate (€)", "Role"]
            df_employees_for_editor = pd.DataFrame(data_for_editor_emp, columns=df_emp_cols)
            if df_employees_for_editor.empty:
                df_employees_for_editor = pd.DataFrame(columns=df_emp_cols).astype({
                    "ID": "float64", "Name": "object", "Hourly Rate (€)": "float64", "Role": "object"
                })

            snapshot_key_emp = 'df_employees_snapshot'
            if snapshot_key_emp not in st.session_state or \
               not isinstance(st.session_state.get(snapshot_key_emp), pd.DataFrame) or \
               not st.session_state[snapshot_key_emp].columns.equals(df_employees_for_editor.columns):
                st.session_state[snapshot_key_emp] = df_employees_for_editor.copy()

            emp_display_columns = ("Name", "Hourly Rate (€)", "Role")
            edited_df_emp = st.data_editor(
                st.session_state[snapshot_key_emp], 
                num_rows="dynamic", key="employees_editor",
                column_order=emp_display_columns, 
                column_config={
                    "Name": st.column_config.TextColumn("Employee Name*", required=True),
                    "Hourly Rate (€)": st.column_config.NumberColumn("Hourly Rate (€)*", required=True, min_value=0.00, step=0.01, format="%.2f"),
                    "Role": st.column_config.TextColumn("Role (Optional)")
                },
                use_container_width=True, hide_index=True
            )

            if st.button("Save Employee Changes", type="primary"):
                try:
                    # (Similar save/update/delete logic as Ingredients)
                    original_df_snapshot_emp = st.session_state[snapshot_key_emp]
                    original_snapshot_ids_emp = set(original_df_snapshot_emp['ID'].dropna().astype(int))
                    edited_df_ids_emp = set(edited_df_emp['ID'].dropna().astype(int))
                    ids_to_delete_from_db_emp = original_snapshot_ids_emp - edited_df_ids_emp

                    for emp_id_del in ids_to_delete_from_db_emp:
                        emp_to_del = db_session_main_app.query(Employee).filter(Employee.id == emp_id_del, Employee.user_id == current_user_db.id).first()
                        if emp_to_del: db_session_main_app.delete(emp_to_del); st.toast(f"Deleted employee ID: {emp_id_del}", icon="➖")

                    for index, row in edited_df_emp.iterrows():
                        emp_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                        name_val, rate_val, role_val = row.get("Name"), row.get("Hourly Rate (€)"), row.get("Role")
                        if not all([name_val, pd.notna(rate_val)]):
                            if emp_id is None and not any([name_val, pd.notna(rate_val), role_val]): continue
                            st.error(f"Row {index+1}: Name and Hourly Rate are required. Skipping."); continue
                        role_val = str(role_val).strip() if role_val and str(role_val).strip() else None
                        if emp_id: 
                            item_to_update = db_session_main_app.query(Employee).filter(Employee.id == emp_id, Employee.user_id == current_user_db.id).first()
                            if item_to_update:
                                changed = False
                                if item_to_update.name != name_val: item_to_update.name = name_val; changed=True
                                if item_to_update.hourly_rate != Decimal(str(rate_val)): item_to_update.hourly_rate = Decimal(str(rate_val)); changed=True 
                                if item_to_update.role != role_val: item_to_update.role = role_val; changed=True
                                if changed: st.toast(f"Updated employee ID: {emp_id}", icon="🔄")
                        # Handle new rows (those without an ID from the original snapshot)
                    new_rows_df_emp = edited_df_emp[edited_df_emp['ID'].isna()]
                    for index, row in new_rows_df_emp.iterrows():
                        name_val, rate_val, role_val = row.get("Name"), row.get("Hourly Rate (€)"), row.get("Role")
                        if not all([name_val, pd.notna(rate_val)]):
                            if not any([name_val, pd.notna(rate_val), role_val]): continue
                            st.error(f"New Row (approx original index {index+1}): Name and Hourly Rate are required. Skipping."); continue
                        role_val = str(role_val).strip() if role_val and str(role_val).strip() else None
                        db_session_main_app.add(Employee(user_id=current_user_db.id, name=name_val, hourly_rate=Decimal(str(rate_val)), role=role_val)) 
                        st.toast(f"Added employee: {name_val}", icon="➕")
                    
                    db_session_main_app.commit(); st.success("Employee changes saved!")
                    st.session_state[snapshot_key_emp] = edited_df_emp.copy()
                    st.rerun()
                except Exception as e_save_emp: 
                    db_session_main_app.rollback()
                    st.error(f"Error saving employees: {e_save_emp}")
                    st.exception(e_save_emp)
        
        # --- Section: Manage Production Tasks ---
        elif choice == "Manage Production Tasks":
            st.header("🏭 Manage Standard Production Tasks")
            st.write("Define common tasks involved in production. Click **'Save Production Task Changes'** to persist.")
            tasks_db = db_session_main_app.query(StandardProductionTask).filter(StandardProductionTask.user_id == current_user_db.id).order_by(StandardProductionTask.id).all()
            data_for_editor_ptask = [{"ID": task.id, "Task Name": task.task_name} for task in tasks_db]
            
            df_ptask_cols = ["ID", "Task Name"]
            df_ptasks_for_editor = pd.DataFrame(data_for_editor_ptask, columns=df_ptask_cols)
            if df_ptasks_for_editor.empty:
                df_ptasks_for_editor = pd.DataFrame(columns=df_ptask_cols).astype({"ID": "float64", "Task Name": "object"})

            snapshot_key_ptask = 'df_ptasks_snapshot'
            if snapshot_key_ptask not in st.session_state or \
               not isinstance(st.session_state.get(snapshot_key_ptask), pd.DataFrame) or \
               not st.session_state[snapshot_key_ptask].columns.equals(df_ptasks_for_editor.columns):
                st.session_state[snapshot_key_ptask] = df_ptasks_for_editor.copy()
            
            ptask_display_columns = ("Task Name",)
            edited_df_ptask = st.data_editor(
                st.session_state[snapshot_key_ptask], 
                num_rows="dynamic", key="prod_tasks_editor",
                column_order=ptask_display_columns, 
                column_config={"Task Name": st.column_config.TextColumn("Task Name*", required=True)},
                use_container_width=True, hide_index=True
            )

            if st.button("Save Production Task Changes", type="primary"):
                try:
                    # (Similar save/update/delete logic)
                    original_df_snapshot_ptask = st.session_state[snapshot_key_ptask]
                    original_snapshot_ids_ptask = set(original_df_snapshot_ptask['ID'].dropna().astype(int))
                    edited_df_ids_ptask = set(edited_df_ptask['ID'].dropna().astype(int))
                    ids_to_delete_from_db_ptask = original_snapshot_ids_ptask - edited_df_ids_ptask

                    for task_id_del in ids_to_delete_from_db_ptask:
                        task_to_del = db_session_main_app.query(StandardProductionTask).filter(StandardProductionTask.id == task_id_del, StandardProductionTask.user_id == current_user_db.id).first()
                        if task_to_del: db_session_main_app.delete(task_to_del); st.toast(f"Deleted task ID: {task_id_del}", icon="➖")

                    for index, row in edited_df_ptask.iterrows():
                        task_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                        name_val = row.get("Task Name")
                        if not name_val:
                            if task_id is None and not name_val: continue
                            st.error(f"Row {index+1}: Task Name is required. Skipping."); continue
                        if task_id: 
                            item_to_update = db_session_main_app.query(StandardProductionTask).filter(StandardProductionTask.id == task_id, StandardProductionTask.user_id == current_user_db.id).first()
                            if item_to_update and item_to_update.task_name != name_val:
                                item_to_update.task_name = name_val; st.toast(f"Updated task ID: {task_id}", icon="🔄")
                    
                    new_rows_df_ptask = edited_df_ptask[edited_df_ptask['ID'].isna()]
                    for index, row in new_rows_df_ptask.iterrows():
                        name_val = row.get("Task Name")
                        if not name_val:
                            if not name_val: continue # Skip empty new row
                            st.error(f"New Row (approx original index {index+1}): Task Name is required. Skipping."); continue
                        db_session_main_app.add(StandardProductionTask(user_id=current_user_db.id, task_name=name_val))
                        st.toast(f"Added task: {name_val}", icon="➕")
                    
                    db_session_main_app.commit(); st.success("Production Task changes saved!")
                    st.session_state[snapshot_key_ptask] = edited_df_ptask.copy()
                    st.rerun()
                except Exception as e_save_ptask: 
                    db_session_main_app.rollback()
                    st.error(f"Error saving production tasks: {e_save_ptask}")
                    st.exception(e_save_ptask)

        # --- Section: Manage Shipping Tasks ---
        elif choice == "Manage Shipping Tasks":
            st.header("🚚 Manage Standard Shipping Tasks")
            st.write("Define common tasks for shipping. Click **'Save Shipping Task Changes'** to persist.")
            tasks_db_ship = db_session_main_app.query(StandardShippingTask).filter(StandardShippingTask.user_id == current_user_db.id).order_by(StandardShippingTask.id).all()
            data_for_editor_stask = [{"ID": task.id, "Task Name": task.task_name} for task in tasks_db_ship]
            
            df_stask_cols = ["ID", "Task Name"]
            df_stasks_for_editor = pd.DataFrame(data_for_editor_stask, columns=df_stask_cols)
            if df_stasks_for_editor.empty:
                df_stasks_for_editor = pd.DataFrame(columns=df_stask_cols).astype({"ID": "float64", "Task Name": "object"})

            snapshot_key_stask = 'df_stasks_snapshot'
            if snapshot_key_stask not in st.session_state or \
               not isinstance(st.session_state.get(snapshot_key_stask), pd.DataFrame) or \
               not st.session_state[snapshot_key_stask].columns.equals(df_stasks_for_editor.columns):
                st.session_state[snapshot_key_stask] = df_stasks_for_editor.copy()

            stask_display_columns = ("Task Name",)
            edited_df_stask = st.data_editor(
                st.session_state[snapshot_key_stask], 
                num_rows="dynamic", key="ship_tasks_editor",
                column_order=stask_display_columns, 
                column_config={"Task Name": st.column_config.TextColumn("Task Name*", required=True)},
                use_container_width=True, hide_index=True
            )

            if st.button("Save Shipping Task Changes", type="primary"):
                try:
                    # (Similar save/update/delete logic)
                    original_df_snapshot_stask = st.session_state[snapshot_key_stask]
                    original_snapshot_ids_stask = set(original_df_snapshot_stask['ID'].dropna().astype(int))
                    edited_df_ids_stask = set(edited_df_stask['ID'].dropna().astype(int))
                    ids_to_delete_from_db_stask = original_snapshot_ids_stask - edited_df_ids_stask

                    for task_id_del in ids_to_delete_from_db_stask:
                        task_to_del = db_session_main_app.query(StandardShippingTask).filter(StandardShippingTask.id == task_id_del, StandardShippingTask.user_id == current_user_db.id).first()
                        if task_to_del: db_session_main_app.delete(task_to_del); st.toast(f"Deleted task ID: {task_id_del}", icon="➖")
                    
                    for index, row in edited_df_stask.iterrows():
                        task_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                        name_val = row.get("Task Name")
                        if not name_val:
                            if task_id is None and not name_val: continue
                            st.error(f"Row {index+1}: Task Name is required. Skipping."); continue
                        if task_id:
                            item_to_update = db_session_main_app.query(StandardShippingTask).filter(StandardShippingTask.id == task_id, StandardShippingTask.user_id == current_user_db.id).first()
                            if item_to_update and item_to_update.task_name != name_val:
                                 item_to_update.task_name = name_val; st.toast(f"Updated task ID: {task_id}", icon="🔄")
                    
                    new_rows_df_stask = edited_df_stask[edited_df_stask['ID'].isna()]
                    for index, row in new_rows_df_stask.iterrows():
                        name_val = row.get("Task Name")
                        if not name_val:
                            if not name_val: continue
                            st.error(f"New Row (approx original index {index+1}): Task Name is required. Skipping."); continue
                        db_session_main_app.add(StandardShippingTask(user_id=current_user_db.id, task_name=name_val))
                        st.toast(f"Added task: {name_val}", icon="➕")

                    db_session_main_app.commit(); st.success("Shipping Task changes saved!")
                    st.session_state[snapshot_key_stask] = edited_df_stask.copy()
                    st.rerun()
                except Exception as e_save_stask: 
                    db_session_main_app.rollback()
                    st.error(f"Error saving shipping tasks: {e_save_stask}")
                    st.exception(e_save_stask)
        
        # --- Section: Manage Products (Main + Details) ---
        elif choice == "Manage Products":
            # (This section is extensive, using the structure from your provided working script)
            # For brevity in this response, I'll assume the structure you had before.
            # Ensure all sub-components (materials, prod tasks, ship tasks, other costs)
            # use db_session_main_app correctly.
            st.header("📦 Manage Products")
            st.write("Add, edit, or delete main product attributes. Select a product from the table or the dropdown below to manage its detailed components.")

            products_db = db_session_main_app.query(Product).filter(Product.user_id == current_user_db.id).order_by(Product.id).all()
            product_editor_columns = ["ID", "Product Name", "Batch Size", "Monthly Production"]
            data_for_editor_prod = [{"ID": p.id, "Product Name": p.product_name, "Batch Size": p.batch_size_items, "Monthly Production": p.monthly_production_items} for p in products_db]
            
            df_products_for_editor = pd.DataFrame(data_for_editor_prod, columns=product_editor_columns)
            if df_products_for_editor.empty:
                df_products_for_editor = pd.DataFrame(columns=product_editor_columns).astype({
                    "ID": "float64", "Product Name": "object", "Batch Size": "int64", "Monthly Production": "int64"
                })

            snapshot_key_prod = 'df_products_snapshot'
            if snapshot_key_prod not in st.session_state or \
               not isinstance(st.session_state.get(snapshot_key_prod), pd.DataFrame) or \
               not st.session_state[snapshot_key_prod].columns.equals(df_products_for_editor.columns):
                st.session_state[snapshot_key_prod] = df_products_for_editor.copy()
            
            prod_display_columns = ("Product Name", "Batch Size", "Monthly Production")
            product_column_config = {
                "Product Name": st.column_config.TextColumn("Product Name*", required=True, width="large"),
                "Batch Size": st.column_config.NumberColumn("Batch Size (items)*", required=True, min_value=1, step=1, format="%d", width="medium"),
                "Monthly Production": st.column_config.NumberColumn("Monthly Prod (items)*", required=True, min_value=0, step=1, format="%d", width="medium")
            }

            edited_df_prod = st.data_editor(
                st.session_state[snapshot_key_prod], 
                num_rows="dynamic", key="products_editor",
                column_order=prod_display_columns, column_config=product_column_config, 
                use_container_width=True, hide_index=True
            )

            if st.button("Save Product Attribute Changes", type="primary"):
                try:
                    original_df_snapshot_prod = st.session_state[snapshot_key_prod]
                    original_snapshot_ids_prod = set(original_df_snapshot_prod['ID'].dropna().astype(int))
                    edited_df_ids_prod = set(edited_df_prod['ID'].dropna().astype(int))
                    ids_to_delete_from_db_prod = original_snapshot_ids_prod - edited_df_ids_prod

                    for p_id_del in ids_to_delete_from_db_prod:
                        prod_to_del = db_session_main_app.query(Product).filter(Product.id == p_id_del, Product.user_id == current_user_db.id).first()
                        if prod_to_del: 
                            db_session_main_app.delete(prod_to_del)
                            st.toast(f"Deleted product ID: {p_id_del}", icon="➖")
                            if st.session_state.selected_product_id == p_id_del: st.session_state.selected_product_id = None
                    
                    for index, edited_row in edited_df_prod.iterrows():
                        p_id = edited_row.get('ID'); p_id = int(p_id) if pd.notna(p_id) else None
                        name_val, batch_val, monthly_val = edited_row.get("Product Name"), edited_row.get("Batch Size"), edited_row.get("Monthly Production")

                        if not all([name_val, pd.notna(batch_val), pd.notna(monthly_val)]):
                            if p_id is None and not any([name_val, pd.notna(batch_val), pd.notna(monthly_val)]): continue
                            st.error(f"Row {index+1} (Products): Name, Batch Size, Monthly Prod are required. Skipping."); continue
                        
                        if p_id: 
                            p_to_update = db_session_main_app.query(Product).filter(Product.id == p_id, Product.user_id == current_user_db.id).first()
                            if p_to_update:
                                changed = False
                                if p_to_update.product_name != name_val: p_to_update.product_name = name_val; changed=True
                                if p_to_update.batch_size_items != int(batch_val): p_to_update.batch_size_items = int(batch_val); changed=True
                                if p_to_update.monthly_production_items != int(monthly_val): p_to_update.monthly_production_items = int(monthly_val); changed=True
                                if changed: st.toast(f"Updated product ID: {p_id}", icon="🔄")
                    
                    new_rows_df_prod = edited_df_prod[edited_df_prod['ID'].isna()]
                    for index, row in new_rows_df_prod.iterrows():
                        name_val, batch_val, monthly_val = row.get("Product Name"), row.get("Batch Size"), row.get("Monthly Production")
                        if not all([name_val, pd.notna(batch_val), pd.notna(monthly_val)]):
                            if not any([name_val, pd.notna(batch_val), pd.notna(monthly_val)]): continue
                            st.error(f"New Row (approx original index {index+1}): Name, Batch Size, Monthly Prod are required. Skipping."); continue
                        new_prod = Product(user_id=current_user_db.id, product_name=name_val, batch_size_items=int(batch_val), monthly_production_items=int(monthly_val))
                        db_session_main_app.add(new_prod); db_session_main_app.flush(); # Flush to get ID for new_prod
                        st.session_state.selected_product_id = new_prod.id # Auto-select new product
                        st.toast(f"Added: {name_val}. Selected for detail editing.", icon="➕")

                    db_session_main_app.commit(); st.success("Product attribute changes saved!")
                    st.session_state[snapshot_key_prod] = edited_df_prod.copy()
                    st.rerun()
                except Exception as e_save_prod: 
                    db_session_main_app.rollback()
                    st.error(f"Error saving products: {e_save_prod}")
                    st.exception(e_save_prod)

            st.markdown("---")
            # Product Detail Selector
            product_list_for_details = db_session_main_app.query(Product).filter(Product.user_id == current_user_db.id).order_by(Product.product_name).all()
            product_names_for_select = {p.product_name: p.id for p in product_list_for_details}
            
            if product_list_for_details:
                current_selected_name_for_dropdown = None
                # Try to find name for current selected_product_id
                if st.session_state.selected_product_id:
                    for name_key, id_val in product_names_for_select.items():
                        if id_val == st.session_state.selected_product_id: 
                            current_selected_name_for_dropdown = name_key
                            break
                
                # If no valid selection or selected_product_id is stale, default to first product
                if not current_selected_name_for_dropdown or \
                   (st.session_state.selected_product_id and st.session_state.selected_product_id not in product_names_for_select.values()):
                    current_selected_name_for_dropdown = product_list_for_details[0].product_name
                    st.session_state.selected_product_id = product_names_for_select[current_selected_name_for_dropdown]

                selected_product_name_for_details = st.selectbox(
                    "Select Product to Manage Details:", 
                    options=list(product_names_for_select.keys()),
                    index=list(product_names_for_select.keys()).index(current_selected_name_for_dropdown) if current_selected_name_for_dropdown in product_names_for_select else 0,
                    key="product_detail_selector", 
                    placeholder="Choose a product..."
                )
                if selected_product_name_for_details and product_names_for_select.get(selected_product_name_for_details) != st.session_state.selected_product_id:
                    st.session_state.selected_product_id = product_names_for_select[selected_product_name_for_details]
                    st.rerun() # Rerun to update context for the selected product
            else:
                st.info("No products available to manage details. Please add a product above.")
                if st.session_state.selected_product_id is not None: 
                    st.session_state.selected_product_id = None # Reset if no products
                    st.rerun()

            # --- Product Detail Sub-Sections (Materials, Tasks, Other Costs) ---
            if st.session_state.selected_product_id:
                selected_product_object = db_session_main_app.query(Product)\
                    .options(selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref),
                             selectinload(Product.production_tasks).joinedload(ProductProductionTask.employee_ref),
                             selectinload(Product.production_tasks).joinedload(ProductProductionTask.standard_task_ref),
                             selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.employee_ref),
                             selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.standard_task_ref),
                             joinedload(Product.salary_alloc_employee_ref).joinedload(Employee.global_salary_entry)
                             )\
                    .filter(Product.id == st.session_state.selected_product_id, Product.user_id == current_user_db.id).first()

                if not selected_product_object: 
                    st.warning("The previously selected product could not be found. Please select another product.")
                    st.session_state.selected_product_id = None # Reset if product not found
                    # No rerun here, let user pick from dropdown again
                else:
                    st.subheader(f"Managing Details for: **{selected_product_object.product_name}**")

                    # Product Materials Expander
                    with st.expander("🧪 Product Materials", expanded=True):
                        # (Logic from your script, ensure db_session_main_app is used)
                        all_ingredients_db = db_session_main_app.query(Ingredient).filter(Ingredient.user_id == current_user_db.id).all()
                        ingredient_display_options = [create_ingredient_display_string(ing.name, ing.provider) for ing in all_ingredients_db] if all_ingredients_db else ["No ingredients defined globally"]
                        
                        data_for_pm_editor = []
                        if selected_product_object.materials: 
                            for pm in selected_product_object.materials:
                                if pm.ingredient_ref: 
                                    data_for_pm_editor.append({"ID": pm.id, "Ingredient": create_ingredient_display_string(pm.ingredient_ref.name, pm.ingredient_ref.provider), "Quantity (g)": pm.quantity_grams})
                        
                        df_pm_cols = ["ID", "Ingredient", "Quantity (g)"]
                        df_pm_for_editor = pd.DataFrame(data_for_pm_editor, columns=df_pm_cols)
                        if df_pm_for_editor.empty:
                            df_pm_for_editor = pd.DataFrame(columns=df_pm_cols).astype({"ID":"float64", "Ingredient":"object", "Quantity (g)":"float64"})

                        snapshot_key_pm = f'df_pm_snapshot_{selected_product_object.id}'
                        if snapshot_key_pm not in st.session_state or \
                           not isinstance(st.session_state.get(snapshot_key_pm), pd.DataFrame) or \
                           not st.session_state[snapshot_key_pm].columns.equals(df_pm_for_editor.columns):
                            st.session_state[snapshot_key_pm] = df_pm_for_editor.copy()
                        
                        pm_display_columns = ("Ingredient", "Quantity (g)")
                        edited_df_pm = st.data_editor(
                            st.session_state[snapshot_key_pm], 
                            num_rows="dynamic", key=f"pm_editor_{selected_product_object.id}",
                            column_order=pm_display_columns, 
                            column_config={
                                "Ingredient": st.column_config.SelectboxColumn("Ingredient (Provider)*", options=ingredient_display_options, required=True), 
                                "Quantity (g)": st.column_config.NumberColumn("Quantity (grams)*", required=True, min_value=0.001, step=0.01, format="%.3f")
                            },
                            use_container_width=True, hide_index=True
                        )

                        if st.button(f"Save Materials for {selected_product_object.product_name}", key=f"save_pm_{selected_product_object.id}", type="primary"):
                            try:
                                # (Save logic for ProductMaterials using db_session_main_app)
                                original_df_snapshot_pm = st.session_state[snapshot_key_pm]
                                original_snapshot_ids_pm = set(original_df_snapshot_pm['ID'].dropna().astype(int))
                                edited_df_ids_pm = set(edited_df_pm['ID'].dropna().astype(int))
                                ids_to_delete_from_db_pm = original_snapshot_ids_pm - edited_df_ids_pm

                                for pm_id_del in ids_to_delete_from_db_pm:
                                    pm_to_del = db_session_main_app.query(ProductMaterial).filter(ProductMaterial.id == pm_id_del, ProductMaterial.product_id == selected_product_object.id).first()
                                    if pm_to_del: db_session_main_app.delete(pm_to_del); st.toast(f"Deleted material ID: {pm_id_del}", icon="➖")

                                for index, row in edited_df_pm.iterrows():
                                    pm_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                                    ing_display_val, qty_val = row.get("Ingredient"), row.get("Quantity (g)")
                                    if not all([ing_display_val, ing_display_val != "No ingredients defined globally", pd.notna(qty_val), float(qty_val or 0) > 0]):
                                        if pm_id is None and not any([ing_display_val, pd.notna(qty_val)]): continue
                                        st.error(f"Row {index+1} (Materials): Invalid data. Skipping."); continue
                                    
                                    ingredient_id_for_row = get_ingredient_id_from_display(db_session_main_app, ing_display_val, current_user_db.id)
                                    if not ingredient_id_for_row: st.error(f"Row {index+1} (Materials): Could not find '{ing_display_val}'. Skipping."); continue
                                    
                                    if pm_id: 
                                        pm_to_update = db_session_main_app.query(ProductMaterial).filter(ProductMaterial.id == pm_id, ProductMaterial.product_id == selected_product_object.id).first()
                                        if pm_to_update:
                                            changed = False
                                            if pm_to_update.ingredient_id != ingredient_id_for_row: pm_to_update.ingredient_id = ingredient_id_for_row; changed=True
                                            if pm_to_update.quantity_grams != Decimal(str(qty_val)): pm_to_update.quantity_grams = Decimal(str(qty_val)); changed=True 
                                            if changed: st.toast(f"Updated material ID: {pm_id}", icon="🔄")
                                
                                new_rows_df_pm = edited_df_pm[edited_df_pm['ID'].isna()]
                                for index, row in new_rows_df_pm.iterrows():
                                    ing_display_val, qty_val = row.get("Ingredient"), row.get("Quantity (g)")
                                    if not all([ing_display_val, ing_display_val != "No ingredients defined globally", pd.notna(qty_val), float(qty_val or 0) > 0]):
                                        if not any([ing_display_val, pd.notna(qty_val)]): continue
                                        st.error(f"New Row (Materials - approx original index {index+1}): Invalid data. Skipping."); continue
                                    ingredient_id_for_row = get_ingredient_id_from_display(db_session_main_app, ing_display_val, current_user_db.id)
                                    if not ingredient_id_for_row: st.error(f"New Row (Materials - approx original index {index+1}): Could not find '{ing_display_val}'. Skipping."); continue
                                    db_session_main_app.add(ProductMaterial(product_id=selected_product_object.id, ingredient_id=ingredient_id_for_row, quantity_grams=Decimal(str(qty_val)))) 
                                    st.toast(f"Added material: {ing_display_val}", icon="➕")

                                db_session_main_app.commit(); st.success(f"Materials for '{selected_product_object.product_name}' saved!")
                                st.session_state[snapshot_key_pm] = edited_df_pm.copy()
                                st.rerun()
                            except Exception as e_save_pm: 
                                db_session_main_app.rollback()
                                st.error(f"Error saving materials: {e_save_pm}")
                                st.exception(e_save_pm)
                    
                    # Product Production Tasks Expander
                    with st.expander("🛠️ Product Production Tasks", expanded=False):
                        # (Logic from your script, ensure db_session_main_app is used)
                        all_std_prod_tasks_db = db_session_main_app.query(StandardProductionTask).filter(StandardProductionTask.user_id == current_user_db.id).all()
                        std_prod_task_options = [task.task_name for task in all_std_prod_tasks_db] if all_std_prod_tasks_db else ["No standard prod tasks defined"]
                        all_employees_db_ppt = db_session_main_app.query(Employee).filter(Employee.user_id == current_user_db.id).all() # Renamed to avoid conflict
                        employee_name_options_ppt = [emp.name for emp in all_employees_db_ppt] if all_employees_db_ppt else ["No employees defined"]
                        
                        data_for_ppt_editor = []
                        if selected_product_object.production_tasks:
                            for ppt in selected_product_object.production_tasks:
                                if ppt.standard_task_ref and ppt.employee_ref: 
                                    data_for_ppt_editor.append({"ID": ppt.id, "Task": ppt.standard_task_ref.task_name, "Employee": ppt.employee_ref.name, "Time (min)": ppt.time_minutes, "# Items in Task": ppt.items_processed_in_task})
                        
                        df_ppt_cols = ["ID", "Task", "Employee", "Time (min)", "# Items in Task"]
                        df_ppt_for_editor = pd.DataFrame(data_for_ppt_editor, columns=df_ppt_cols)
                        if df_ppt_for_editor.empty:
                            df_ppt_for_editor = pd.DataFrame(columns=df_ppt_cols).astype({"ID":"float64", "Task":"object", "Employee":"object", "Time (min)":"float64", "# Items in Task":"int64"})

                        snapshot_key_ppt = f'df_ppt_snapshot_{selected_product_object.id}'
                        if snapshot_key_ppt not in st.session_state or \
                           not isinstance(st.session_state.get(snapshot_key_ppt), pd.DataFrame) or \
                           not st.session_state[snapshot_key_ppt].columns.equals(df_ppt_for_editor.columns):
                            st.session_state[snapshot_key_ppt] = df_ppt_for_editor.copy()

                        ppt_display_columns = ("Task", "Employee", "Time (min)", "# Items in Task")
                        edited_df_ppt = st.data_editor(
                            st.session_state[snapshot_key_ppt], 
                            num_rows="dynamic", key=f"ppt_editor_{selected_product_object.id}",
                            column_order=ppt_display_columns, 
                            column_config={
                                "Task": st.column_config.SelectboxColumn("Task*", options=std_prod_task_options, required=True),
                                "Employee": st.column_config.SelectboxColumn("Performed By*", options=employee_name_options_ppt, required=True),
                                "Time (min)": st.column_config.NumberColumn("Time (min)*", required=True, min_value=0.0, step=0.1, format="%.1f"),
                                "# Items in Task": st.column_config.NumberColumn("# Items in Task*", required=True, min_value=1, step=1, format="%d")
                            }, 
                            use_container_width=True, hide_index=True
                        )

                        if st.button(f"Save Production Tasks for {selected_product_object.product_name}", key=f"save_ppt_{selected_product_object.id}", type="primary"):
                            try:
                                # (Save logic for ProductProductionTasks using db_session_main_app)
                                original_df_snapshot_ppt = st.session_state[snapshot_key_ppt]
                                original_snapshot_ids_ppt = set(original_df_snapshot_ppt['ID'].dropna().astype(int))
                                edited_df_ids_ppt = set(edited_df_ppt['ID'].dropna().astype(int))
                                ids_to_delete_from_db_ppt = original_snapshot_ids_ppt - edited_df_ids_ppt

                                for ppt_id_del in ids_to_delete_from_db_ppt:
                                    ppt_to_del = db_session_main_app.query(ProductProductionTask).filter(ProductProductionTask.id == ppt_id_del, ProductProductionTask.product_id == selected_product_object.id).first()
                                    if ppt_to_del: db_session_main_app.delete(ppt_to_del); st.toast(f"Deleted prod task ID: {ppt_id_del}", icon="➖")
                                
                                for index, row in edited_df_ppt.iterrows():
                                    ppt_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                                    task_name_val, emp_name_val, time_val, items_val = row.get("Task"), row.get("Employee"), row.get("Time (min)"), row.get("# Items in Task")
                                    if not all([task_name_val, task_name_val != "No standard prod tasks defined", emp_name_val, emp_name_val != "No employees defined", pd.notna(time_val), pd.notna(items_val), int(items_val or 0) > 0]):
                                        if ppt_id is None and not any([task_name_val, emp_name_val, pd.notna(time_val), pd.notna(items_val)]): continue
                                        st.error(f"Row {index+1} (Prod Tasks): Invalid data. Skipping."); continue
                                    
                                    std_task_id_for_row = get_std_prod_task_id_from_name(db_session_main_app, task_name_val, current_user_db.id)
                                    emp_id_for_row = get_employee_id_from_name(db_session_main_app, emp_name_val, current_user_db.id)
                                    if not std_task_id_for_row or not emp_id_for_row: st.error(f"Row {index+1} (Prod Tasks): Invalid task/employee. Skipping."); continue
                                    
                                    if ppt_id: 
                                        ppt_to_update = db_session_main_app.query(ProductProductionTask).filter(ProductProductionTask.id == ppt_id, ProductProductionTask.product_id == selected_product_object.id).first()
                                        if ppt_to_update:
                                            changed = False
                                            if ppt_to_update.standard_task_id != std_task_id_for_row: ppt_to_update.standard_task_id = std_task_id_for_row; changed=True
                                            if ppt_to_update.employee_id != emp_id_for_row: ppt_to_update.employee_id = emp_id_for_row; changed=True
                                            if ppt_to_update.time_minutes != Decimal(str(time_val)): ppt_to_update.time_minutes = Decimal(str(time_val)); changed=True 
                                            if ppt_to_update.items_processed_in_task != int(items_val): ppt_to_update.items_processed_in_task = int(items_val); changed=True
                                            if changed: st.toast(f"Updated prod task ID: {ppt_id}", icon="🔄")

                                new_rows_df_ppt = edited_df_ppt[edited_df_ppt['ID'].isna()]
                                for index, row in new_rows_df_ppt.iterrows():
                                    task_name_val, emp_name_val, time_val, items_val = row.get("Task"), row.get("Employee"), row.get("Time (min)"), row.get("# Items in Task")
                                    if not all([task_name_val, task_name_val != "No standard prod tasks defined", emp_name_val, emp_name_val != "No employees defined", pd.notna(time_val), pd.notna(items_val), int(items_val or 0) > 0]):
                                        if not any([task_name_val, emp_name_val, pd.notna(time_val), pd.notna(items_val)]): continue
                                        st.error(f"New Row (Prod Tasks - approx original index {index+1}): Invalid data. Skipping."); continue
                                    std_task_id_for_row = get_std_prod_task_id_from_name(db_session_main_app, task_name_val, current_user_db.id)
                                    emp_id_for_row = get_employee_id_from_name(db_session_main_app, emp_name_val, current_user_db.id)
                                    if not std_task_id_for_row or not emp_id_for_row: st.error(f"New Row (Prod Tasks - approx original index {index+1}): Invalid task/employee. Skipping."); continue
                                    db_session_main_app.add(ProductProductionTask(product_id=selected_product_object.id, standard_task_id=std_task_id_for_row, employee_id=emp_id_for_row, time_minutes=Decimal(str(time_val)), items_processed_in_task=int(items_val))) 
                                    st.toast(f"Added prod task: {task_name_val}", icon="➕")
                                
                                db_session_main_app.commit(); st.success(f"Production tasks saved!")
                                st.session_state[snapshot_key_ppt] = edited_df_ppt.copy()
                                st.rerun()
                            except Exception as e_save_ppt: 
                                db_session_main_app.rollback()
                                st.error(f"Error saving prod tasks: {e_save_ppt}")
                                st.exception(e_save_ppt)

                    # Product Shipping Tasks Expander
                    with st.expander("🚚 Product Shipping Tasks", expanded=False):
                        # (Logic from your script, ensure db_session_main_app is used)
                        all_std_ship_tasks_db = db_session_main_app.query(StandardShippingTask).filter(StandardShippingTask.user_id == current_user_db.id).all()
                        std_ship_task_options = [task.task_name for task in all_std_ship_tasks_db] if all_std_ship_tasks_db else ["No standard ship tasks defined"]
                        # Assuming employee_name_options_ppt (defined for prod tasks) can be reused if same employee list applies
                        
                        data_for_pst_editor = []
                        if selected_product_object.shipping_tasks:
                            for pst in selected_product_object.shipping_tasks:
                                if pst.standard_task_ref and pst.employee_ref:
                                    data_for_pst_editor.append({"ID": pst.id, "Task": pst.standard_task_ref.task_name, "Employee": pst.employee_ref.name, "Time (min)": pst.time_minutes, "# Items in Task": pst.items_processed_in_task})
                        
                        df_pst_cols = ["ID", "Task", "Employee", "Time (min)", "# Items in Task"]
                        df_pst_for_editor = pd.DataFrame(data_for_pst_editor, columns=df_pst_cols)
                        if df_pst_for_editor.empty:
                            df_pst_for_editor = pd.DataFrame(columns=df_pst_cols).astype({"ID":"float64", "Task":"object", "Employee":"object", "Time (min)":"float64", "# Items in Task":"int64"})
                        
                        snapshot_key_pst = f'df_pst_snapshot_{selected_product_object.id}'
                        if snapshot_key_pst not in st.session_state or \
                           not isinstance(st.session_state.get(snapshot_key_pst), pd.DataFrame) or \
                           not st.session_state[snapshot_key_pst].columns.equals(df_pst_for_editor.columns):
                            st.session_state[snapshot_key_pst] = df_pst_for_editor.copy()

                        pst_display_columns = ("Task", "Employee", "Time (min)", "# Items in Task")
                        edited_df_pst = st.data_editor(
                            st.session_state[snapshot_key_pst], 
                            num_rows="dynamic", key=f"pst_editor_{selected_product_object.id}",
                            column_order=pst_display_columns, 
                            column_config={
                                "Task": st.column_config.SelectboxColumn("Task*", options=std_ship_task_options, required=True),
                                "Employee": st.column_config.SelectboxColumn("Performed By*", options=employee_name_options_ppt, required=True), # Reusing employee options
                                "Time (min)": st.column_config.NumberColumn("Time (min)*", required=True, min_value=0.0, step=0.1, format="%.1f"),
                                "# Items in Task": st.column_config.NumberColumn("# Items in Task*", required=True, min_value=1, step=1, format="%d")
                            }, 
                            use_container_width=True, hide_index=True
                        )

                        if st.button(f"Save Shipping Tasks for {selected_product_object.product_name}", key=f"save_pst_{selected_product_object.id}", type="primary"):
                            try:
                                # (Save logic for ProductShippingTasks using db_session_main_app)
                                original_df_snapshot_pst = st.session_state[snapshot_key_pst]
                                original_snapshot_ids_pst = set(original_df_snapshot_pst['ID'].dropna().astype(int))
                                edited_df_ids_pst = set(edited_df_pst['ID'].dropna().astype(int))
                                ids_to_delete_from_db_pst = original_snapshot_ids_pst - edited_df_ids_pst

                                for pst_id_del in ids_to_delete_from_db_pst:
                                    pst_to_del = db_session_main_app.query(ProductShippingTask).filter(ProductShippingTask.id == pst_id_del, ProductShippingTask.product_id == selected_product_object.id).first()
                                    if pst_to_del: db_session_main_app.delete(pst_to_del); st.toast(f"Deleted ship task ID: {pst_id_del}", icon="➖")
                                
                                for index, row in edited_df_pst.iterrows():
                                    pst_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                                    task_name_val, emp_name_val, time_val, items_val = row.get("Task"), row.get("Employee"), row.get("Time (min)"), row.get("# Items in Task")
                                    if not all([task_name_val, task_name_val != "No standard ship tasks defined", emp_name_val, emp_name_val != "No employees defined", pd.notna(time_val), pd.notna(items_val), int(items_val or 0) > 0]):
                                        if pst_id is None and not any([task_name_val, emp_name_val, pd.notna(time_val), pd.notna(items_val)]): continue
                                        st.error(f"Row {index+1} (Ship Tasks): Invalid data. Skipping."); continue
                                    std_task_id_for_row = get_std_ship_task_id_from_name(db_session_main_app, task_name_val, current_user_db.id)
                                    emp_id_for_row = get_employee_id_from_name(db_session_main_app, emp_name_val, current_user_db.id)
                                    if not std_task_id_for_row or not emp_id_for_row: st.error(f"Row {index+1} (Ship Tasks): Invalid task/employee. Skipping."); continue
                                    if pst_id: 
                                        pst_to_update = db_session_main_app.query(ProductShippingTask).filter(ProductShippingTask.id == pst_id, ProductShippingTask.product_id == selected_product_object.id).first()
                                        if pst_to_update:
                                            changed = False
                                            if pst_to_update.standard_task_id != std_task_id_for_row: pst_to_update.standard_task_id = std_task_id_for_row; changed=True
                                            if pst_to_update.employee_id != emp_id_for_row: pst_to_update.employee_id = emp_id_for_row; changed=True
                                            if pst_to_update.time_minutes != Decimal(str(time_val)): pst_to_update.time_minutes = Decimal(str(time_val)); changed=True 
                                            if pst_to_update.items_processed_in_task != int(items_val): pst_to_update.items_processed_in_task = int(items_val); changed=True
                                            if changed: st.toast(f"Updated ship task ID: {pst_id}", icon="🔄")

                                new_rows_df_pst = edited_df_pst[edited_df_pst['ID'].isna()]
                                for index, row in new_rows_df_pst.iterrows():
                                    task_name_val, emp_name_val, time_val, items_val = row.get("Task"), row.get("Employee"), row.get("Time (min)"), row.get("# Items in Task")
                                    if not all([task_name_val, task_name_val != "No standard ship tasks defined", emp_name_val, emp_name_val != "No employees defined", pd.notna(time_val), pd.notna(items_val), int(items_val or 0) > 0]):
                                        if not any([task_name_val, emp_name_val, pd.notna(time_val), pd.notna(items_val)]): continue
                                        st.error(f"New Row (Ship Tasks - approx original index {index+1}): Invalid data. Skipping."); continue
                                    std_task_id_for_row = get_std_ship_task_id_from_name(db_session_main_app, task_name_val, current_user_db.id)
                                    emp_id_for_row = get_employee_id_from_name(db_session_main_app, emp_name_val, current_user_db.id)
                                    if not std_task_id_for_row or not emp_id_for_row: st.error(f"New Row (Ship Tasks - approx original index {index+1}): Invalid task/employee. Skipping."); continue
                                    db_session_main_app.add(ProductShippingTask(product_id=selected_product_object.id, standard_task_id=std_task_id_for_row, employee_id=emp_id_for_row, time_minutes=Decimal(str(time_val)), items_processed_in_task=int(items_val))) 
                                    st.toast(f"Added ship task: {task_name_val}", icon="➕")
                                
                                db_session_main_app.commit(); st.success(f"Shipping tasks saved!")
                                st.session_state[snapshot_key_pst] = edited_df_pst.copy()
                                st.rerun()
                            except Exception as e_save_pst: 
                                db_session_main_app.rollback()
                                st.error(f"Error saving ship tasks: {e_save_pst}")
                                st.exception(e_save_pst)

                    # Other Product Costs & Pricing Expander
                    with st.expander("🪙 Other Product Specific Costs & Pricing", expanded=False):
                        st.markdown("#### Packaging Costs (per Item)")
                        col_pkg1, col_pkg2 = st.columns(2)
                        pkg_label_cost = selected_product_object.packaging_label_cost if selected_product_object.packaging_label_cost is not None else Decimal('0.0')
                        pkg_material_cost = selected_product_object.packaging_material_cost if selected_product_object.packaging_material_cost is not None else Decimal('0.0')
                        new_pkg_label_cost = col_pkg1.number_input("Label Cost/Item (€)", value=float(pkg_label_cost), min_value=0.0, format="%.3f", key=f"pkg_label_{selected_product_object.id}")
                        new_pkg_material_cost = col_pkg2.number_input("Other Pkg Materials Cost/Item (€)", value=float(pkg_material_cost), min_value=0.0, format="%.3f", key=f"pkg_mat_{selected_product_object.id}")

                        st.markdown("#### Salary & Overhead Allocation")
                        all_employees_db_other = db_session_main_app.query(Employee).filter(Employee.user_id == current_user_db.id).all() # Fresh query or reuse
                        allocatable_salaried_employees = [emp for emp in all_employees_db_other if emp.global_salary_entry] 
                        salaried_employee_options = {emp.name: emp.id for emp in allocatable_salaried_employees}
                        salaried_employee_names = ["None"] + list(salaried_employee_options.keys())
                        current_salary_alloc_emp_name = "None"
                        if selected_product_object.salary_allocation_employee_id and selected_product_object.salary_alloc_employee_ref:
                            current_salary_alloc_emp_name = selected_product_object.salary_alloc_employee_ref.name
                        idx_sal_emp = salaried_employee_names.index(current_salary_alloc_emp_name) if current_salary_alloc_emp_name in salaried_employee_names else 0
                        selected_salary_emp_name = st.selectbox("Allocate Salary of Employee (must have Global Salary)", options=salaried_employee_names, index=idx_sal_emp, key=f"sal_alloc_emp_{selected_product_object.id}")
                        
                        sal_alloc_items = selected_product_object.salary_allocation_items_per_month if selected_product_object.salary_allocation_items_per_month is not None else 1000
                        new_sal_alloc_items = st.number_input("Items of THIS Product per Month (for salary allocation)", value=int(sal_alloc_items), min_value=1, format="%d", key=f"sal_alloc_items_{selected_product_object.id}")
                        rent_alloc_items = selected_product_object.rent_utilities_allocation_items_per_month if selected_product_object.rent_utilities_allocation_items_per_month is not None else 1000
                        new_rent_alloc_items = st.number_input("Items of THIS Product per Month (for rent/utilities)", value=int(rent_alloc_items), min_value=1, format="%d", key=f"rent_alloc_items_{selected_product_object.id}")
                        
                        st.markdown("#### Online Selling Fees - Retail")
                        sp = selected_product_object 
                        new_ret_ao = st.number_input("Avg Retail Order Value (€)", value=float(sp.retail_avg_order_value or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ret_ao_{sp.id}")
                        new_ret_cc = st.number_input("Retail Credit Card Fee (%)", value=float(sp.retail_cc_fee_percent or Decimal('0.0')), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ret_cc_{sp.id}")
                        new_ret_plat = st.number_input("Retail Platform Fee (%)", value=float(sp.retail_platform_fee_percent or Decimal('0.0')), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ret_plat_{sp.id}")
                        new_ret_ship = st.number_input("Retail Avg Shipping Paid by You (€)", value=float(sp.retail_shipping_cost_paid_by_you or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ret_ship_{sp.id}")

                        st.markdown("#### Online Selling Fees - Wholesale")
                        new_ws_ao = st.number_input("Avg Wholesale Order Value (€)", value=float(sp.wholesale_avg_order_value or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ws_ao_{sp.id}")
                        new_ws_comm = st.number_input("Wholesale Commission (%)", value=float(sp.wholesale_commission_percent or Decimal('0.0')), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ws_comm_{sp.id}")
                        new_ws_proc = st.number_input("Wholesale Payment Processing Fee (%)", value=float(sp.wholesale_processing_fee_percent or Decimal('0.0')), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ws_proc_{sp.id}")
                        new_ws_flat = st.number_input("Wholesale Flat Fee per Order (€)", value=float(sp.wholesale_flat_fee_per_order or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ws_flat_{sp.id}")

                        st.markdown("#### Pricing Strategy")
                        col_price1, col_price2, col_price3 = st.columns(3)
                        new_ws_price = col_price1.number_input("Wholesale Price/Item (€)", value=float(sp.wholesale_price_per_item or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ws_price_{sp.id}")
                        new_rt_price = col_price2.number_input("Retail Price/Item (€)", value=float(sp.retail_price_per_item or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"rt_price_{sp.id}")
                        new_buffer = col_price3.slider("Buffer Percentage", min_value=0.0, max_value=1.0, value=float(sp.buffer_percentage or Decimal('0.0')), step=0.01, format="%.2f", key=f"buffer_{sp.id}")
                        
                        st.markdown("#### Distribution")
                        new_dist_ws = st.slider("Wholesale Distribution (%)", min_value=0.0, max_value=1.0, value=float(sp.distribution_wholesale_percentage or Decimal('0.0')), step=0.01, format="%.2f", key=f"dist_ws_{sp.id}")
                        st.metric("Retail Distribution (%)", f"{(1.0 - new_dist_ws):.0%}")

                        if st.button(f"Save Other Costs & Pricing for {sp.product_name}", key=f"save_other_costs_{sp.id}", type="primary"):
                            try:
                                sp.packaging_label_cost = Decimal(str(new_pkg_label_cost))
                                sp.packaging_material_cost = Decimal(str(new_pkg_material_cost))
                                sp.salary_allocation_employee_id = salaried_employee_options.get(selected_salary_emp_name) 
                                sp.salary_allocation_items_per_month = new_sal_alloc_items
                                sp.rent_utilities_allocation_items_per_month = new_rent_alloc_items
                                sp.retail_avg_order_value = Decimal(str(new_ret_ao))
                                sp.retail_cc_fee_percent = Decimal(str(new_ret_cc))
                                sp.retail_platform_fee_percent = Decimal(str(new_ret_plat))
                                sp.retail_shipping_cost_paid_by_you = Decimal(str(new_ret_ship))
                                sp.wholesale_avg_order_value = Decimal(str(new_ws_ao))
                                sp.wholesale_commission_percent = Decimal(str(new_ws_comm))
                                sp.wholesale_processing_fee_percent = Decimal(str(new_ws_proc))
                                sp.wholesale_flat_fee_per_order = Decimal(str(new_ws_flat))
                                sp.wholesale_price_per_item = Decimal(str(new_ws_price))
                                sp.retail_price_per_item = Decimal(str(new_rt_price))
                                sp.buffer_percentage = Decimal(str(new_buffer))
                                sp.distribution_wholesale_percentage = Decimal(str(new_dist_ws))
                                
                                db_session_main_app.add(sp); db_session_main_app.commit(); st.success("Other costs and pricing saved!"); st.rerun()
                            except Exception as e_save_other: 
                                db_session_main_app.rollback()
                                st.error(f"Error saving other costs: {e_save_other}")
                                st.exception(e_save_other)

        # --- Section: Global Costs/Salaries ---
        elif choice == "Global Costs/Salaries":
            st.header("🌍 Global Costs & Salaries")
            st.info("Manage global fixed costs and monthly salaries here. These are used for overhead allocation to products.")
            with st.expander("💰 Monthly Fixed Overheads", expanded=True):
                global_costs_obj = db_session_main_app.query(GlobalCosts).filter(GlobalCosts.user_id == current_user_db.id).first()
                if not global_costs_obj: 
                    global_costs_obj = GlobalCosts(user_id=current_user_db.id, monthly_rent=Decimal('0.0'), monthly_utilities=Decimal('0.0'))
                
                rent_val = st.number_input("Global Monthly Rent (€)", value=float(global_costs_obj.monthly_rent or Decimal('0.0')), min_value=0.0, format="%.2f", key="global_rent")
                util_val = st.number_input("Global Monthly Utilities (€)", value=float(global_costs_obj.monthly_utilities or Decimal('0.0')), min_value=0.0, format="%.2f", key="global_utilities")
                
                if st.button("Save Global Overheads", key="save_global_overheads", type="primary"):
                    global_costs_obj.monthly_rent = Decimal(str(rent_val))
                    global_costs_obj.monthly_utilities = Decimal(str(util_val))
                    db_session_main_app.add(global_costs_obj)
                    try: 
                        db_session_main_app.commit(); st.success("Global overheads saved!"); st.rerun()
                    except Exception as e_save_global: 
                        db_session_main_app.rollback()
                        st.error(f"Error saving global overheads: {e_save_global}")
            
            st.markdown("---")
            st.subheader("💵 Global Monthly Salaries")
            st.write("Edit, add, or delete global salaries. These are fixed monthly amounts for specific employees used in overhead allocation.")
            global_salaries_db = db_session_main_app.query(GlobalSalary).options(joinedload(GlobalSalary.employee_ref)).filter(GlobalSalary.user_id == current_user_db.id).order_by(GlobalSalary.id).all()
            all_employees_list_gs = db_session_main_app.query(Employee).filter(Employee.user_id == current_user_db.id).all() 
            employee_options_gs = {emp.name: emp.id for emp in all_employees_list_gs}
            employee_names_gs = list(employee_options_gs.keys()) if employee_options_gs else ["No employees defined"]
            
            data_for_gs_editor = []
            if global_salaries_db:
                for gs in global_salaries_db:
                    if gs.employee_ref: 
                         data_for_gs_editor.append({"ID": gs.id, "Employee Name": gs.employee_ref.name, "Monthly Salary (€)": gs.monthly_amount})

            df_gs_cols = ["ID", "Employee Name", "Monthly Salary (€)"]
            df_gs_for_editor = pd.DataFrame(data_for_gs_editor, columns=df_gs_cols)
            if df_gs_for_editor.empty:
                df_gs_for_editor = pd.DataFrame(columns=df_gs_cols).astype({"ID":"float64", "Employee Name":"object", "Monthly Salary (€)":"float64"})

            snapshot_key_gs = 'df_gs_snapshot'
            if snapshot_key_gs not in st.session_state or \
               not isinstance(st.session_state.get(snapshot_key_gs), pd.DataFrame) or \
               not st.session_state[snapshot_key_gs].columns.equals(df_gs_for_editor.columns):
                st.session_state[snapshot_key_gs] = df_gs_for_editor.copy()

            gs_display_columns = ("Employee Name", "Monthly Salary (€)")
            edited_df_gs = st.data_editor(
                st.session_state[snapshot_key_gs], 
                num_rows="dynamic", key="global_salaries_editor",
                column_order=gs_display_columns, 
                column_config={
                    "Employee Name": st.column_config.SelectboxColumn("Employee*", options=employee_names_gs, required=True), 
                    "Monthly Salary (€)": st.column_config.NumberColumn("Monthly Salary (€)*", required=True, min_value=0.0, step=10.0, format="%.2f")
                }, 
                use_container_width=True, hide_index=True
            )

            if st.button("Save Global Salaries", type="primary"):
                try:
                    # (Similar save/update/delete logic)
                    original_df_snapshot_gs = st.session_state[snapshot_key_gs]
                    original_snapshot_ids_gs = set(original_df_snapshot_gs['ID'].dropna().astype(int))
                    edited_df_ids_gs = set(edited_df_gs['ID'].dropna().astype(int))
                    ids_to_delete_from_db_gs = original_snapshot_ids_gs - edited_df_ids_gs

                    for gs_id_del in ids_to_delete_from_db_gs:
                        gs_to_del = db_session_main_app.query(GlobalSalary).filter(GlobalSalary.id == gs_id_del, GlobalSalary.user_id == current_user_db.id).first()
                        if gs_to_del: db_session_main_app.delete(gs_to_del); st.toast(f"Deleted global salary ID: {gs_id_del}", icon="➖")

                    for index, row in edited_df_gs.iterrows():
                        gs_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                        emp_name_val, amount_val = row.get("Employee Name"), row.get("Monthly Salary (€)")
                        if not all([emp_name_val, emp_name_val != "No employees defined", pd.notna(amount_val)]):
                            if gs_id is None and not any([emp_name_val, pd.notna(amount_val)]): continue
                            st.error(f"Row {index+1} (Global Salaries): Invalid data. Skipping."); continue
                        
                        employee_id_for_gs = employee_options_gs.get(emp_name_val)
                        if not employee_id_for_gs: st.error(f"Row {index+1} (Global Salaries): Employee '{emp_name_val}' not found. Skipping."); continue

                        if gs_id: 
                            gs_to_update = db_session_main_app.query(GlobalSalary).filter(GlobalSalary.id == gs_id, GlobalSalary.user_id == current_user_db.id).first()
                            if gs_to_update:
                                changed = False
                                if gs_to_update.employee_id != employee_id_for_gs: gs_to_update.employee_id = employee_id_for_gs; changed=True
                                if gs_to_update.monthly_amount != Decimal(str(amount_val)): gs_to_update.monthly_amount = Decimal(str(amount_val)); changed=True 
                                if changed: st.toast(f"Updated global salary ID: {gs_id}", icon="🔄")
                    
                    new_rows_df_gs = edited_df_gs[edited_df_gs['ID'].isna()]
                    for index, row in new_rows_df_gs.iterrows():
                        emp_name_val, amount_val = row.get("Employee Name"), row.get("Monthly Salary (€)")
                        if not all([emp_name_val, emp_name_val != "No employees defined", pd.notna(amount_val)]):
                            if not any([emp_name_val, pd.notna(amount_val)]): continue
                            st.error(f"New Row (Global Salaries - approx original index {index+1}): Invalid data. Skipping."); continue
                        employee_id_for_gs = employee_options_gs.get(emp_name_val)
                        if not employee_id_for_gs: st.error(f"New Row (Global Salaries - approx original index {index+1}): Employee '{emp_name_val}' not found. Skipping."); continue
                        
                        existing_salary = db_session_main_app.query(GlobalSalary).filter(GlobalSalary.user_id == current_user_db.id, GlobalSalary.employee_id == employee_id_for_gs).first()
                        if existing_salary: st.warning(f"Employee '{emp_name_val}' already has a global salary. Edit existing. Skipping addition."); continue
                        db_session_main_app.add(GlobalSalary(user_id=current_user_db.id, employee_id=employee_id_for_gs, monthly_amount=Decimal(str(amount_val)))) 
                        st.toast(f"Added global salary for {emp_name_val}", icon="➕")

                    db_session_main_app.commit(); st.success("Global salaries saved!")
                    st.session_state[snapshot_key_gs] = edited_df_gs.copy()
                    st.rerun()
                except IntegrityError: 
                    db_session_main_app.rollback()
                    st.error("Error: An employee can only have one global salary entry. Please ensure no duplicates by employee.")
                except Exception as e_save_gs: 
                    db_session_main_app.rollback()
                    st.error(f"Error saving global salaries: {e_save_gs}")
                    st.exception(e_save_gs)

        # --- Section: Product Cost Breakdown ---
        elif choice == "Product Cost Breakdown":
            st.header("📊 Product Cost Breakdown")
            products_for_calc = db_session_main_app.query(Product).filter(Product.user_id == current_user_db.id).order_by(Product.product_name).all()
            
            if not products_for_calc:
                st.info("No products found. Please add products in 'Manage Products' to see a cost breakdown.")
            else:
                product_names_for_calc = {p.product_name: p.id for p in products_for_calc}
                
                # Initialize or retain selection for this specific selectbox
                if 'calc_selected_product_name' not in st.session_state or st.session_state.calc_selected_product_name not in product_names_for_calc:
                    st.session_state.calc_selected_product_name = list(product_names_for_calc.keys())[0]

                selected_product_name_calc = st.selectbox(
                    "Select Product for Breakdown:", 
                    options=list(product_names_for_calc.keys()), 
                    key="calc_prod_select_sb", # Unique key
                    index=list(product_names_for_calc.keys()).index(st.session_state.calc_selected_product_name)
                )
                # Update session state if selection changes
                if selected_product_name_calc != st.session_state.calc_selected_product_name:
                    st.session_state.calc_selected_product_name = selected_product_name_calc
                    # No rerun needed here, calculation will use the new selection

                if selected_product_name_calc:
                    selected_product_id_calc = product_names_for_calc[selected_product_name_calc]
                    breakdown_data = calculate_cost_breakdown(selected_product_id_calc, db_session_main_app, current_user_db.id)

                    if breakdown_data:
                        st.subheader(f"Cost Analysis for: **{selected_product_name_calc}**")
                        # (Display logic from your script)
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Total Production Cost/Item", format_currency(breakdown_data['total_production_cost_per_item']))
                        col2.metric("Target Price (with Buffer)", format_currency(breakdown_data['cost_plus_buffer']))
                        col3.metric("Blended Avg Profit/Item", format_currency(breakdown_data['blended_avg_profit']))
                        st.markdown("---")
                        with st.expander("💰 Direct COGS Details", expanded=True):
                            st.markdown(f"**Total Material Cost/Item:** {format_currency(breakdown_data['total_material_cost_per_item'])}")
                            if breakdown_data['material_details']:
                                df_mat = pd.DataFrame(breakdown_data['material_details']); df_mat_display = df_mat.copy()
                                df_mat_display["Qty (g)"] = df_mat_display["Qty (g)"].apply(lambda x: format_decimal_for_table(x, '0.001'))
                                df_mat_display["Cost"] = df_mat_display["Cost"].apply(format_currency); st.table(df_mat_display)
                            st.markdown(f"**Total Production Labor Cost/Item:** {format_currency(breakdown_data['total_production_labor_cost_per_item'])}")
                            if breakdown_data['prod_labor_details']:
                                df_prod_labor = pd.DataFrame(breakdown_data['prod_labor_details']); df_prod_labor_display = df_prod_labor.copy()
                                df_prod_labor_display["Time (min)"] = df_prod_labor_display["Time (min)"].apply(lambda x: format_decimal_for_table(x, '0.1'))
                                df_prod_labor_display["Items in Task"] = df_prod_labor_display["Items in Task"].apply(lambda x: format_decimal_for_table(x, '0'))
                                df_prod_labor_display["Cost"] = df_prod_labor_display["Cost"].apply(format_currency); st.table(df_prod_labor_display)
                            st.markdown(f"**Total Shipping Labor Cost/Item (Direct):** {format_currency(breakdown_data['total_shipping_labor_cost_per_item'])}")
                            if breakdown_data['ship_labor_details']:
                                df_ship_labor = pd.DataFrame(breakdown_data['ship_labor_details']); df_ship_labor_display = df_ship_labor.copy()
                                df_ship_labor_display["Time (min)"] = df_ship_labor_display["Time (min)"].apply(lambda x: format_decimal_for_table(x, '0.1'))
                                df_ship_labor_display["Items in Task"] = df_ship_labor_display["Items in Task"].apply(lambda x: format_decimal_for_table(x, '0'))
                                df_ship_labor_display["Cost"] = df_ship_labor_display["Cost"].apply(format_currency); st.table(df_ship_labor_display)
                            st.markdown(f"**Packaging - Label Cost/Item:** {format_currency(breakdown_data['packaging_label_cost_per_item'])}")
                            st.markdown(f"**Packaging - Material Cost/Item:** {format_currency(breakdown_data['packaging_material_cost_per_item'])}")
                            st.markdown(f"**Total Packaging Cost/Item:** {format_currency(breakdown_data['total_packaging_cost_per_item'])}")
                            st.markdown(f"##### **Subtotal Direct COGS/Item:** {format_currency(breakdown_data['direct_cogs_per_item'])}")
                        with st.expander("🏢 Allocated Overheads per Item"):
                            st.markdown(f"**Allocated Salary Cost/Item:** {format_currency(breakdown_data['allocated_salary_cost_per_item'])}")
                            st.markdown(f"**Allocated Rent/Utilities Cost/Item:** {format_currency(breakdown_data['allocated_rent_utilities_cost_per_item'])}")
                            st.markdown(f"##### **Subtotal Allocated Overheads/Item:** {format_currency(breakdown_data['total_allocated_overheads_per_item'])}")
                        st.markdown("---")
                        st.subheader("📈 Channel Performance Analysis (per Item)")
                        col_ret, col_ws = st.columns(2)
                        with col_ret:
                            st.markdown("#### 🛍️ Retail Channel")
                            rt = breakdown_data['retail_metrics']
                            st.metric("Retail Price", format_currency(rt['price']))
                            st.write(f"CC Fee: {format_currency(rt['cc_fee'])} | Platform Fee: {format_currency(rt['platform_fee'])}")
                            st.write(f"Shipping Paid by You (per item): {format_currency(rt['shipping_cost'])}")
                            st.write(f"**Total Retail Channel Costs:** {format_currency(rt['total_channel_costs'])}")
                            st.metric("Total Cost (Prod + Retail Fees)", format_currency(rt['total_cost_item']))
                            st.metric("Profit per Retail Item", format_currency(rt['profit']), delta_color="normal")
                            st.metric("Retail Margin", format_percentage(rt['margin_percent']))
                        with col_ws:
                            st.markdown("#### 🏭 Wholesale Channel")
                            ws = breakdown_data['wholesale_metrics']
                            st.metric("Wholesale Price", format_currency(ws['price']))
                            st.write(f"Commission: {format_currency(ws['commission'])} | Processing Fee: {format_currency(ws['processing_fee'])}")
                            st.write(f"Flat Fee (Item Share): {format_currency(ws['flat_fee_item_share'])}")
                            st.write(f"**Total Wholesale Channel Costs:** {format_currency(ws['total_channel_costs'])}")
                            st.metric("Total Cost (Prod + Wholesale Fees)", format_currency(ws['total_cost_item']))
                            st.metric("Profit per Wholesale Item", format_currency(ws['profit']), delta_color="normal")
                            st.metric("Wholesale Margin", format_percentage(ws['margin_percent']))
                        st.markdown("---")
                        st.subheader("⚖️ Blended Performance (Weighted by Distribution)")
                        st.metric("Weighted Average Selling Price/Item", format_currency(breakdown_data['blended_avg_price']))
                        st.metric("Weighted Average Total Cost/Item", format_currency(breakdown_data['blended_avg_total_cost']))
                        st.metric("Weighted Average Profit/Item", format_currency(breakdown_data['blended_avg_profit']), delta_color="normal")
                        st.metric("Weighted Average Margin", format_percentage(breakdown_data['blended_avg_margin_percent']))
                    else:
                        st.error("Could not calculate breakdown for the selected product. Ensure all product data is complete, especially in the 'Manage Products -> Other Costs & Pricing' section.")

        # --- Section: User Settings ---
        elif choice == "User Settings":
            st.header("⚙️ User Settings")
            st.write("Manage your user profile and application settings.")
            st.subheader("Profile Information")
            # username is already defined from st.session_state.get("username")
            user_credentials = config_auth['credentials']['usernames'].get(username, {})
            current_name = user_credentials.get('name', '') 
            current_email = user_credentials.get('email', '')
            st.write(f"**Username:** `{username}`")
            new_name = st.text_input("Name:", value=current_name, key="update_user_name_input")
            new_email = st.text_input("Email:", value=current_email, key="update_user_email_input")

            if st.button("Save User Details", key="save_user_details_button_key", type="primary"):
                if not new_name.strip(): st.error("Name cannot be empty.")
                elif not new_email.strip(): st.error("Email cannot be empty.")
                else:
                    try:
                        config_auth['credentials']['usernames'][username]['name'] = new_name.strip()
                        config_auth['credentials']['usernames'][username]['email'] = new_email.strip()
                        st.session_state['name'] = new_name.strip() # Update session state for immediate display
                        with open(CONFIG_FILE_PATH, 'w') as file:
                            yaml.dump(config_auth, file, default_flow_style=False, allow_unicode=True)
                        st.success("User details updated successfully!")
                        st.rerun() 
                    except Exception as e_update_manual: st.error(f"Error updating details: {e_update_manual}")
            st.markdown("---") 
            st.subheader("Update Password")
            try:
                if authenticator.reset_password(username=username, location='main'): 
                    st.success('Password reset successfully! Saving to config file.')
                    with open(CONFIG_FILE_PATH, 'w') as file: 
                        yaml.dump(config_auth, file, default_flow_style=False, allow_unicode=True)
            except Exception as e_pw: st.error(f"Error during password reset widget: {e_pw}") 

        # --- Section: User Guide ---
        elif choice == "User Guide":
            st.markdown("## 📖 User Guide: Product Cost Calculator")
            st.markdown("""
                Welcome to the **Product Cost Calculator**! This guide will walk you through each section of the application, 
                helping you effectively manage your product costs and pricing strategies.
            """)
            st.markdown("---")

            with st.expander("🚀 Getting Started & Navigation", expanded=True):
                st.markdown("### Logging In & Registration")
                st.markdown("""
                    - **Login:** If you have an existing account, enter your `Username` and `Password` in the main panel and click the **Login** button.
                    - **Registration:** 
                        - If you are a new user, click on the **Register** tab/link.
                        - Fill in your `Name`, `Username`, `Email`, and `Password` (enter it twice for confirmation).
                        - Click the **Register** button.
                    - Upon successful login or registration, you'll see a welcome message and the main menu will appear in the sidebar.
                """)
                st.markdown("### Navigating the App")
                st.markdown("""
                    - The main navigation is done via the **sidebar menu** on the left, under "🛠️ Main Menu".
                    - Click on any menu item (e.g., "Manage Ingredients", "Manage Products") to navigate to that section.
                    - Your current selection is highlighted in the sidebar.
                """)
            st.markdown("---")

            with st.expander("🗃️ Core Data Management Sections", expanded=False):
                st.markdown("### Manage Ingredients")
                st.markdown("""
                    *Purpose: Track your raw materials, their costs, and suppliers. This data is fundamental for calculating material costs per product.*
                    
                    **How to Use:**
                    - The table displays your current ingredients.
                    - **To Add a New Ingredient:**
                        1. Click the `+ Add row` button at the bottom of the data editor.
                        2. Fill in the details in the new row.
                    - **To Edit an Existing Ingredient:** Click directly into any cell and modify its value.
                    - **To Delete an Ingredient:** Click the trash can icon (`🗑️`) next to the row you wish to remove.
                    - **Important:** After making any additions, edits, or deletions, you **MUST** click the **"Save Ingredient Changes"** button to persist your modifications to the database.
                    
                    **Key Fields:**
                    - `Ingredient Name*`: The descriptive name of the raw material (e.g., "Organic Cocoa Butter"). *This field is required.*
                    - `Provider (Optional)`: The supplier or source of the ingredient (e.g., "Supplier X").
                    - `Price per Unit (€)*`: The cost for the quantity specified in `Unit (kg)` (e.g., if the price is €10 for a 5kg bag, enter `10.00`). *This field is required.*
                    - `Unit Quantity (kg)*`: The amount in kilograms that the `Price per Unit` refers to (e.g., for a 5kg bag, enter `5.000`). *This field is required.*
                    - `Price URL (Optional)`: A web link to where you source the ingredient, for your reference. Use the Link icon to validate/open.
                """)
                st.markdown("---")

                st.markdown("### Manage Employees")
                st.markdown("""
                    *Purpose: Track your employees, particularly those whose labor contributes directly to product costs (if paid hourly) or whose salaries are allocated as overheads.*
                    
                    **How to Use:** Similar to "Manage Ingredients" – use the data editor to add, edit, or delete employee records. Always click **"Save Employee Changes"**.
                    
                    **Key Fields:**
                    - `Employee Name*`: Full name of the employee. *Required.*
                    - `Hourly Rate (€)*`: The labor cost of this employee per hour. This is crucial for employees involved in timed production or shipping tasks. For salaried employees whose cost is allocated via the "Global Salaries" section, this can be `0.00` if their cost is *only* covered by the global salary allocation. *Required.*
                    - `Role (Optional)`: The employee's job title or primary role (e.g., "Production Staff", "Packer", "Admin").
                """)
                st.markdown("---")

                st.markdown("### Manage Standard Production Tasks")
                st.markdown("""
                    *Purpose: Define a reusable list of common tasks involved in producing your products (e.g., "Mixing Ingredients", "Molding", "Quality Check", "Machine Setup").*
                    
                    **How to Use:** Add, edit, or delete task names. Click **"Save Production Task Changes"**.
                    
                    **Key Fields:**
                    - `Task Name*`: A clear, descriptive name for the production task. *Required.*
                """)
                st.markdown("---")
                
                st.markdown("### Manage Standard Shipping Tasks")
                st.markdown("""
                    *Purpose: Define a reusable list of common tasks involved in preparing and shipping your products (e.g., "Order Picking", "Box Assembly", "Label Printing", "Post Office Run").*
                    
                    **How to Use:** Add, edit, or delete task names. Click **"Save Shipping Task Changes"**.
                    
                    **Key Fields:**
                    - `Task Name*`: A clear, descriptive name for the shipping task. *Required.*
                """)
                st.markdown("---")

                st.markdown("### 🌍 Global Costs/Salaries")
                st.markdown("""
                    *Purpose: Define business-wide fixed costs (like rent) and fixed monthly salaries for employees. These are then used for overhead allocation to individual products.*
                    
                    **Monthly Fixed Overheads (Expander):**
                    - `Global Monthly Rent (€)`: Your total monthly rent expense for your business premises.
                    - `Global Monthly Utilities (€)`: Your total monthly utilities (e.g., electricity, water, internet).
                    - Click **"Save Global Overheads"** after entering/updating these values.
                    
                    **Global Monthly Salaries (Table):**
                    - *Purpose:* For employees who receive a fixed monthly salary (e.g., administrative staff, marketing personnel, or yourself if you draw a fixed salary). This is distinct from hourly rates used for direct labor calculations.
                    - **How to Use:**
                        1. Select an employee from the `Employee*` dropdown (employees must first be defined in "Manage Employees").
                        2. Enter their `Monthly Salary (€)*`.
                        3. Add, edit, or delete salary entries as needed.
                        4. *Note:* An employee can only have one global salary entry. The system will prevent duplicates.
                    - Click **"Save Global Salaries"** to persist changes.
                """)
            st.markdown("---")

            with st.expander("📦 Manage Products (The Core Engine!)", expanded=False):
                st.markdown("### Adding/Editing Basic Product Attributes (Top Table)")
                st.markdown("""
                    - This table lists all your products and their high-level attributes.
                    - **How to Use:** Add, edit, or delete products here.
                    - **Key Fields:**
                        - `Product Name*`: The unique name of your final product (e.g., "Luxury Chocolate Bar - 70% Dark").
                        - `Batch Size (items)*`: The typical number of items produced in one manufacturing run or batch for this product.
                        - `Monthly Prod (items)*`: The total number of items of this specific product you typically produce (or plan to produce/sell) in a month. This is used for some overhead allocation calculations.
                    - After making changes, click **"Save Product Attribute Changes"**.
                    - *Tip:* When you add a new product and save, it's often automatically selected for detailed editing below.
                """)
                st.markdown("---")

                st.markdown("### Managing Detailed Product Components (Lower Section)")
                st.markdown("""
                    - Once you have products, **select a product from the `Select Product to Manage Details:` dropdown**. 
                    - All the expanders below this dropdown will then apply to the currently selected product.
                """)
                st.markdown("---")

                st.markdown("#### 🧪 Product Materials (for the selected product)")
                st.markdown("""
                    *Purpose: Define which ingredients (from your "Manage Ingredients" list) go into **one unit** of the selected product, and in what quantity.*
                    
                    **How to Use:**
                    - For each ingredient in the product:
                        1. Select an `Ingredient (Provider)*` from the dropdown.
                        2. Enter the `Quantity (grams)*` of that ingredient needed for **one single item** of the selected product.
                    - Add as many ingredient rows as needed for the recipe.
                    - Click **"Save Materials for [Product Name]"**.
                """)
                st.markdown("---")

                st.markdown("#### 🛠️ Product Production Tasks (for the selected product)")
                st.markdown("""
                    *Purpose: Assign specific production tasks and employees to the selected product to calculate direct production labor costs.*
                    
                    **How to Use:** For each step in the production process:
                    - `Task*`: Select a standard production task (defined in "Manage Standard Production Tasks").
                    - `Performed By*`: Select the employee (defined in "Manage Employees") who performs this task. Their hourly rate will be used in cost calculations.
                    - `Time (min)*`: The time in minutes it takes this employee to perform this specific task.
                    - `# Items in Task*`: Crucially, this is the number of product items that are processed or completed by the employee during that specified `Time (min)`. 
                        - *Example:* If an employee spends 60 minutes mixing ingredients for a batch that yields 10 product items, you would enter `60` for time and `10` for items. The cost of that 60 minutes of labor will then be distributed across those 10 items.
                    - Click **"Save Production Tasks for [Product Name]"**.
                """)
                st.markdown("---")

                st.markdown("#### 🚚 Product Shipping Tasks (for the selected product)")
                st.markdown("""
                    *Purpose: Similar to Production Tasks, but for direct labor involved in preparing and shipping one or more items of the selected product.*
                    
                    **How to Use:** For each step in your shipping process:
                    - `Task*`: Select a standard shipping task.
                    - `Performed By*`: Select the employee.
                    - `Time (min)*`: Time spent by the employee on this shipping task.
                    - `# Items in Task*`: The number of product items processed for shipping in that time. 
                        - *Example:* If an employee spends 30 minutes packing 5 orders, and each order contains, on average, 1 item of *this specific product*, you might enter `30` for time and `5` for items if you want to allocate that packing time across those 5 items.
                    - Click **"Save Shipping Tasks for [Product Name]"**.
                """)
                st.markdown("---")

                st.markdown("#### 🪙 Other Product Specific Costs & Pricing (for the selected product)")
                st.markdown("""
                    *This expander is vital for detailed costings and pricing strategy.*
                    
                    **Packaging Costs (per Item):**
                    - `Label Cost/Item (€)`: Cost of labels specifically for one item of this product.
                    - `Other Pkg Materials Cost/Item (€)`: Cost of boxes, fillings, tape, etc., for one item of this product.

                    **Salary & Overhead Allocation:**
                    - `Allocate Salary of Employee`: From the dropdown, choose an employee (who must have a "Global Salary" defined) whose salary you want to partially allocate to this product. Select "None" if no specific salary is allocated this way.
                    - `Items of THIS Product per Month (for salary allocation)`: To allocate a portion of the selected employee's global monthly salary, enter the total number of units of *this specific product* that you estimate are related to that employee's work or that their salary should be fairly spread across. 
                        - The system calculates: `(Employee's Global Monthly Salary / Items of THIS Product)` to get a per-item allocated salary cost.
                    - `Items of THIS Product per Month (for rent/utilities)`: Similar to salary allocation, enter the number of units of *this specific product* that your global rent and utilities (from "Global Costs/Salaries") should be spread across.
                        - The system calculates: `(Total Global Rent + Utilities) / Items` to get a per-item allocated fixed overhead cost.

                    **Online Selling Fees - Retail Channel:**
                    - `Avg Retail Order Value (€)`: The average total value (€) of a typical customer's order when they buy through your retail channel (e.g., your website, Etsy). This helps determine how many items are typically in an order, which is used to distribute per-order shipping costs if applicable.
                    - `Retail Credit Card Fee (%)`: The percentage fee charged by payment processors (e.g., Stripe, PayPal). Enter as a decimal (e.g., `0.029` for 2.9%).
                    - `Retail Platform Fee (%)`: The percentage fee charged by your retail sales platform (e.g., Etsy commission, Shopify transaction fee). Enter as a decimal.
                    - `Retail Avg Shipping Paid by You (€)`: The average amount *you* actually pay to ship a typical retail order (not what the customer pays, but your cost).

                    **Online Selling Fees - Wholesale Channel:**
                    - `Avg Wholesale Order Value (€)`: The average total value (€) of a typical wholesale order.
                    - `Wholesale Commission (%)`: Percentage commission paid to wholesale platforms or sales agents. Enter as a decimal.
                    - `Wholesale Payment Processing Fee (%)`: Payment processing fees for wholesale transactions. Enter as a decimal.
                    - `Wholesale Flat Fee per Order (€)`: Any flat fee you incur per wholesale order (e.g., a platform's fixed order fee).

                    **Pricing Strategy:**
                    - `Wholesale Price/Item (€)`: The price at which you sell **one unit** of this product to wholesale customers.
                    - `Retail Price/Item (€)`: The price at which you sell **one unit** of this product to retail customers.
                    - `Buffer Percentage`: A safety margin you want to add to your production costs. Enter as a decimal (e.g., `0.10` for 10%, `0.25` for 25%). This is added to your calculated `Total Production Cost/Item` to give a "Cost Plus Buffer" target price, helping ensure profitability and cover unforeseen costs.

                    **Distribution Mix:**
                    - `Wholesale Distribution (%)`: Estimate the percentage of your total sales volume for *this specific product* that you anticipate will be through the wholesale channel (e.g., `0.60` for 60%).
                    - `Retail Distribution (%)` will be automatically calculated as (100% - Wholesale Distribution %).
                    - These percentages are crucial for calculating the blended average profit and margin in the "Product Cost Breakdown" section.

                    **Remember to click "Save Other Costs & Pricing for [Product Name]"** after making any changes in this detailed section.
                """)
            st.markdown("---")

            with st.expander("📈 Product Cost Breakdown Analysis", expanded=False):
                st.markdown("### Interpreting the Breakdown Section")
                st.markdown("""
                    *Purpose: This section provides a comprehensive financial analysis for any product you select from its dropdown menu. It synthesizes all the data you've entered in other sections.*
                    
                    **How to Use:**
                    1. Navigate to the "Product Cost Breakdown" section from the sidebar.
                    2. Select a product from the `Select Product for Breakdown:` dropdown.
                    3. The analysis for the selected product will update automatically.
                    
                    **Key Metrics & Sections to Understand:**

                    **Summary Metrics (Displayed at the Top):**
                    - `Total Production Cost/Item`: This is the **fully loaded cost** to produce one unit of the selected product. It includes:
                        - Direct Materials
                        - Direct Production Labor
                        - Direct Shipping Labor (labor directly associated with preparing an item for shipment)
                        - Packaging Costs (label + materials)
                        - Allocated Overheads (share of global salaries and rent/utilities)
                    - `Target Price (with Buffer)`: Calculated as: `Total Production Cost/Item * (1 + Buffer Percentage)`. This is a suggested minimum selling price to ensure you cover all costs and your desired buffer.
                    - `Blended Avg Profit/Item`: Your average profit per item across *both* retail and wholesale channels, weighted by the distribution percentages you set in "Manage Products -> Other Costs & Pricing -> Distribution".

                    **Detailed Breakdown Expanders:**

                    - **💰 Direct COGS (Cost of Goods Sold) Details:**
                        - `Total Material Cost/Item`: Sum of all ingredient costs for one product unit. A table below shows individual ingredient contributions.
                        - `Total Production Labor Cost/Item`: Sum of all production labor costs for one unit. A table details task-specific labor.
                        - `Total Shipping Labor Cost/Item (Direct)`: Sum of direct labor for shipping tasks for one unit. A table details task-specific labor.
                        - `Packaging - Label Cost/Item` & `Packaging - Material Cost/Item`: As entered.
                        - `Total Packaging Cost/Item`: Sum of label and material packaging costs.
                        - `Subtotal Direct COGS/Item`: The sum of all the above direct costs. This is a key metric representing variable costs directly tied to producing each item.

                    - **🏢 Allocated Overheads per Item:**
                        - `Allocated Salary Cost/Item`: The portion of a globally defined salary (from "Global Costs/Salaries" and assigned in "Manage Products") that is allocated to one unit of this product, based on your `Items of THIS Product per Month (for salary allocation)` input.
                        - `Allocated Rent/Utilities Cost/Item`: The portion of your global rent and utilities (from "Global Costs/Salaries") allocated to one unit of this product, based on your `Items of THIS Product per Month (for rent/utilities)` input.
                        - `Subtotal Allocated Overheads/Item`: The sum of these allocated fixed costs per item.

                    **📈 Channel Performance Analysis (per Item - Retail vs. Wholesale):**
                    This section provides a side-by-side comparison of profitability through your retail and wholesale channels.
                        - For each channel (Retail, Wholesale), you'll see:
                            - `Price`: Your selling price for that channel (from "Manage Products").
                            - *Channel-Specific Fees:* Calculated fees (e.g., `CC Fee %`, `Platform Fee %` for retail; `Commission %`, `Processing Fee %`, `Flat Fee per Order` for wholesale) based on your inputs in "Manage Products". These are shown as per-item costs.
                            - `Shipping Paid by You (per item)`: 
                                - *Retail:* Your average shipping cost for a retail order, divided by the average number of items in that retail order (both from "Manage Products").
                                - *Wholesale:* Direct shipping labor is already in COGS. This line item here primarily reflects the retail context. Distinct per-item wholesale shipping *costs paid by you* (beyond labor) aren't explicitly broken out here unless they are part of other defined fees or absorbed into the wholesale price.
                            - `Total Channel Costs`: Sum of all calculated fees and applicable shipping costs for selling through that specific channel.
                            - `Total Cost (Production + Channel Fees)`: This is the crucial `Total Production Cost/Item + Total Channel Costs` for that channel. It represents your *total cost to get one item to the customer* via that channel.
                            - `Profit per Item`: `Selling Price (for that channel) - Total Cost (Production + Channel Fees for that channel)`.
                            - `Margin (%)`: `(Profit per Item / Selling Price for that channel) * 100`.

                    **⚖️ Blended Performance (Weighted by Distribution):**
                    These metrics provide an overall picture of your product's financial health, considering your sales mix.
                    - `Weighted Average Selling Price/Item`: The average price you receive per item, taking into account how much you sell through retail vs. wholesale.
                    - `Weighted Average Total Cost/Item`: The average total cost (production + channel fees) per item, weighted by your distribution.
                    - `Weighted Average Profit/Item`: Your overall average profit per item.
                    - `Weighted Average Margin (%)`: Your overall average profit margin.
                """)
            st.markdown("---")

            with st.expander("⚙️ User Settings & Profile", expanded=False):
                st.markdown("### Updating Your Profile & Password")
                st.markdown("""
                    - **Profile Information:**
                        - You can update your display `Name` and `Email` address associated with your account.
                        - Click the **"Save User Details"** button to apply these changes.
                    - **Update Password:**
                        - To change your login password, use the fields provided:
                            1. Enter your *current* password.
                            2. Enter your *new* password.
                            3. Repeat your *new* password for confirmation.
                        - Click the **"Reset password"** button.
                """)
            
            st.markdown("---")
            st.success("🎉 You've reached the end of the User Guide! If you have more questions, consider re-reading the relevant sections or experimenting in the app.")


        # --- Ensure db_session_main_app is closed after all choices ---
        if db_session_main_app and db_session_main_app.is_active:
            db_session_main_app.close()
            # print("DEBUG: Main app DB session closed.") # Local debug

    except Exception as e_main_app: # Catch any unexpected errors in the authenticated part
        st.error(f"An unexpected error occurred in the application: {e_main_app}")
        st.exception(e_main_app)
        if db_session_main_app and db_session_main_app.is_active: # Ensure closure even on error
            db_session_main_app.close()
            # print("DEBUG: Main app DB session closed after error.") # Local debug


elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning("Please enter your username and password to login, or register if you are a new user.")
    
    # --- Registration Logic (using the simpler version from your working script) ---
    # This version prioritizes getting the app running over the form clearing issue,
    # which is likely a component-specific behavior.
    actual_form_name = "Register user" # Default form name used by streamlit-authenticator
    observed_reg_form_submit_key = f"FormSubmitter:{actual_form_name}-Register"
    pre_authorized_emails_list = config_auth.get('preauthorized', {}).get('emails', [])
    
    try:
        register_user_response = authenticator.register_user(
            pre_authorized=pre_authorized_emails_list
        ) 
        
        is_successful_authenticator_registration = False
        if isinstance(register_user_response, tuple) and len(register_user_response) == 3:
            reg_email, reg_username_val, reg_name = register_user_response # Renamed to avoid conflict
            if isinstance(reg_email, str) and isinstance(reg_username_val, str) and isinstance(reg_name, str):
                # Check if the user now exists in the in-memory config_auth
                if reg_username_val in config_auth.get('credentials', {}).get('usernames', {}):
                    is_successful_authenticator_registration = True
        
        if is_successful_authenticator_registration: 
            st.success('User registered successfully with authenticator!')
            
            # Save the updated config_auth (modified in memory by authenticator) to file
            with open(CONFIG_FILE_PATH, 'w') as file:
                yaml.dump(config_auth, file, default_flow_style=False, allow_unicode=True)

            actual_email_reg = register_user_response[0] # Use distinct names
            actual_username_reg = register_user_response[1]
            actual_name_reg = register_user_response[2]

            hashed_password_for_db = None
            try:
                hashed_password_for_db = config_auth['credentials']['usernames'][actual_username_reg]['password']
            except KeyError:
                st.error(f"CRITICAL: Hashed password for '{actual_username_reg}' not found in config after registration. DB entry cannot be completed.")
                # This shouldn't happen if authenticator.register_user was successful and updated config_auth
            
            db_operation_encountered_error_reg = False # Distinct variable name
            db_session_for_registration = None 
            try:
                if not (actual_username_reg and actual_email_reg and hashed_password_for_db):
                    st.error("Essential data missing for database registration. Please contact support.")
                    db_operation_encountered_error_reg = True
                else:
                    db_session_for_registration = next(get_db())
                    existing_pg_user = db_session_for_registration.query(User).filter(
                        (User.username == actual_username_reg) | (User.email == actual_email_reg)
                    ).first()

                    if existing_pg_user:
                        st.warning(f"User '{actual_username_reg}' or email '{actual_email_reg}' already exists in the application database (PostgreSQL).")
                        # This is okay if config.yaml was the source of truth and DB is catching up.
                    else:
                        db_user = User(
                            username=actual_username_reg, email=actual_email_reg, name=actual_name_reg,
                            hashed_password=hashed_password_for_db
                        )
                        db_session_for_registration.add(db_user)
                        db_session_for_registration.commit()
                        st.info(f"User '{actual_username_reg}' also registered in the application database.")

            except Exception as e_pg_reg: 
                if db_session_for_registration: db_session_for_registration.rollback()
                st.error(f"Database error during user registration: {e_pg_reg}")
                st.exception(e_pg_reg)
                db_operation_encountered_error_reg = True
            finally:
                if db_session_for_registration:
                    db_session_for_registration.close()
            
            if not db_operation_encountered_error_reg:
                # Attempt to clear the submit button state to prevent re-submission on widget refresh
                if observed_reg_form_submit_key in st.session_state:
                    del st.session_state[observed_reg_form_submit_key]
                st.info("Please login with your new credentials.")
                st.rerun() # Rerun to clear forms and show login
            # If there was a DB error, messages are shown, no rerun to allow user to see them.
        
        # else: # No successful registration response from authenticator
            # This case is often handled by streamlit-authenticator itself displaying errors
            # like "Username already taken" directly on its form.
            # if st.session_state.get(observed_reg_form_submit_key) is True:
            # st.warning("Registration form submitted, but it did not result in a recognized successful authenticator registration.")


    except stauth.RegisterError as e_reg_known: # Known registration errors from the library
        st.error(f"Registration Error: {e_reg_known}")
    except Exception as e_register_outer: # Other unexpected errors in the registration block
        st.error(f"An unexpected error occurred during the registration process: {e_register_outer}")
        st.exception(e_register_outer)

st.markdown("---")
st.markdown(f"<div style='text-align: center; color: grey;'>Product Cost Calculator © {datetime.date.today().year}</div>", unsafe_allow_html=True)
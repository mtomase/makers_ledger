# product_cost_calculator_app.py

import streamlit as st
import streamlit_authenticator as stauth
from streamlit_option_menu import option_menu
import yaml
from yaml.loader import SafeLoader
import os
import datetime
import pandas as pd
import re
from decimal import Decimal, ROUND_HALF_UP
from streamlit_js_eval import streamlit_js_eval # Import for screen width

# --- Screen Width Detection ---
if 'screen_width' not in st.session_state:
    st.session_state.screen_width = streamlit_js_eval(js_expressions='window.innerWidth', key='INIT_SCR_WIDTH_FETCH_STREAMLIT_MAIN')

if st.session_state.screen_width is None or st.session_state.screen_width == 0:
    st.session_state.screen_width = 1024 
    if 'initial_rerun_for_width_done_streamlit_main' not in st.session_state:
        st.session_state.initial_rerun_for_width_done_streamlit_main = True
        st.rerun()

MOBILE_BREAKPOINT = 768
IS_MOBILE = st.session_state.screen_width < MOBILE_BREAKPOINT
# --- End Screen Width Detection ---

# --- Detailed Configuration File Path and Permission Check ---
CONFIG_FILE_PATH = None
config_auth_diagnostic_check = None 
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, 'config.yaml')
    if not os.path.exists(CONFIG_FILE_PATH):
        st.error(f"❌ CRITICAL: Config file does NOT exist at `{CONFIG_FILE_PATH}`.")
        st.stop()
    if not os.access(CONFIG_FILE_PATH, os.R_OK):
        st.error(f"❌ CRITICAL: Read permission DENIED for config file at `{CONFIG_FILE_PATH}`.")
        st.stop()
    if not os.access(CONFIG_FILE_PATH, os.W_OK):
        st.warning(f"⚠️ Write permission DENIED for config file at `{CONFIG_FILE_PATH}`. User registration or password/detail updates by the authenticator will likely fail.")
    with open(CONFIG_FILE_PATH, 'r') as file:
        config_auth_diagnostic_check = yaml.load(file, Loader=SafeLoader)
except Exception as e: 
    st.error(f"❌ CRITICAL ERROR during configuration file setup: {e}")
    st.exception(e)
    st.info("Ensure 'config.yaml' exists, is readable/writable, and is valid YAML.")
    st.stop()
# --- End of Detailed Configuration File Path and Permission Check ---


# --- Database Setup ---
from dotenv import load_dotenv
load_dotenv() 
try:
    from models import (
        User, Ingredient, Employee, Product, GlobalCosts, GlobalSalary,
        StandardProductionTask, StandardShippingTask,
        ProductMaterial, ProductProductionTask, ProductShippingTask,
        init_db_structure, get_db, SessionLocal, engine 
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

# --- Helper Functions ---
def create_ingredient_display_string(name, provider):
    if provider: return f"{name} (Provider: {provider})"
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
    if provider is not None: filters.append(Ingredient.provider == provider)
    else: filters.append(Ingredient.provider.is_(None))
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
        if isinstance(value, Decimal): return f"€{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"
        return f"€{float(value):,.2f}" 
    return "N/A"

def format_percentage(value):
    if pd.notna(value) and isinstance(value, (int, float, Decimal)):
        if isinstance(value, Decimal): return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"
        return f"{float(value):.2f}%"
    return "N/A"

def format_decimal_for_table(value, precision='0.001'):
    if pd.notna(value) and isinstance(value, Decimal): return f"{value.quantize(Decimal(precision), rounding=ROUND_HALF_UP)}"
    elif pd.notna(value) and isinstance(value, (int,float)): return f"{float(value):.{len(precision.split('.')[1])}f}" 
    return "N/A"

# --- Cost Breakdown Calculation Function ---
def calculate_cost_breakdown(product_id: int, db: Session, current_user_id: int):
    product = db.query(Product).options(
        selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref),
        selectinload(Product.production_tasks).joinedload(ProductProductionTask.employee_ref),
        selectinload(Product.production_tasks).joinedload(ProductProductionTask.standard_task_ref),
        selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.employee_ref),
        selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.standard_task_ref),
        joinedload(Product.salary_alloc_employee_ref).joinedload(Employee.global_salary_entry)
    ).filter(Product.id == product_id, Product.user_id == current_user_id).first()
    if not product: return None
    breakdown = {}
    material_details = []
    total_material_cost_per_item = Decimal('0.0')
    for pm in product.materials:
        if pm.ingredient_ref:
            ing = pm.ingredient_ref; qty_grams = Decimal(str(pm.quantity_grams)) if pd.notna(pm.quantity_grams) else Decimal('0.0')
            price_per_unit = Decimal(str(ing.price_per_unit)) if pd.notna(ing.price_per_unit) else Decimal('0.0')
            unit_kg = Decimal(str(ing.unit_quantity_kg)) if pd.notna(ing.unit_quantity_kg) and ing.unit_quantity_kg > 0 else Decimal('1.0')
            cost = (qty_grams / Decimal('1000.0')) * (price_per_unit / unit_kg) if unit_kg > Decimal('0.0') else Decimal('0.0')
            total_material_cost_per_item += cost
            material_details.append({"Ingredient": ing.name, "Provider": ing.provider or "-","Qty (g)": qty_grams, "Cost": cost})
    breakdown['material_details'] = material_details; breakdown['total_material_cost_per_item'] = total_material_cost_per_item
    prod_labor_details = []; total_production_labor_cost_per_item = Decimal('0.0')
    for ppt in product.production_tasks:
        if ppt.employee_ref:
            emp = ppt.employee_ref; time_min = Decimal(str(ppt.time_minutes)) if pd.notna(ppt.time_minutes) else Decimal('0.0')
            hourly_rate = Decimal(str(emp.hourly_rate)) if pd.notna(emp.hourly_rate) else Decimal('0.0')
            items_proc = Decimal(str(ppt.items_processed_in_task)) if pd.notna(ppt.items_processed_in_task) and ppt.items_processed_in_task > 0 else Decimal('1.0')
            cost = (time_min / Decimal('60.0')) * hourly_rate; cost_per_item = cost / items_proc if items_proc > Decimal('0.0') else Decimal('0.0')
            total_production_labor_cost_per_item += cost_per_item
            prod_labor_details.append({"Task": ppt.standard_task_ref.task_name if ppt.standard_task_ref else "N/A", "Employee": emp.name, "Time (min)": time_min, "Items in Task": items_proc, "Cost": cost_per_item})
    breakdown['prod_labor_details'] = prod_labor_details; breakdown['total_production_labor_cost_per_item'] = total_production_labor_cost_per_item
    ship_labor_details = []; total_shipping_labor_cost_per_item = Decimal('0.0')
    for pst in product.shipping_tasks:
        if pst.employee_ref:
            emp = pst.employee_ref; time_min = Decimal(str(pst.time_minutes)) if pd.notna(pst.time_minutes) else Decimal('0.0')
            hourly_rate = Decimal(str(emp.hourly_rate)) if pd.notna(emp.hourly_rate) else Decimal('0.0')
            items_proc = Decimal(str(pst.items_processed_in_task)) if pd.notna(pst.items_processed_in_task) and pst.items_processed_in_task > 0 else Decimal('1.0')
            cost = (time_min / Decimal('60.0')) * hourly_rate; cost_per_item = cost / items_proc if items_proc > Decimal('0.0') else Decimal('0.0')
            total_shipping_labor_cost_per_item += cost_per_item
            ship_labor_details.append({"Task": pst.standard_task_ref.task_name if pst.standard_task_ref else "N/A", "Employee": emp.name, "Time (min)": time_min, "Items in Task": items_proc, "Cost": cost_per_item})
    breakdown['ship_labor_details'] = ship_labor_details; breakdown['total_shipping_labor_cost_per_item'] = total_shipping_labor_cost_per_item
    pkg_label_cost = Decimal(str(product.packaging_label_cost)) if pd.notna(product.packaging_label_cost) else Decimal('0.0')
    pkg_material_cost = Decimal(str(product.packaging_material_cost)) if pd.notna(product.packaging_material_cost) else Decimal('0.0')
    breakdown['packaging_label_cost_per_item'] = pkg_label_cost; breakdown['packaging_material_cost_per_item'] = pkg_material_cost
    breakdown['total_packaging_cost_per_item'] = pkg_label_cost + pkg_material_cost
    breakdown['direct_cogs_per_item'] = (total_material_cost_per_item + total_production_labor_cost_per_item + total_shipping_labor_cost_per_item + breakdown['total_packaging_cost_per_item'])
    allocated_salary_cost_per_item = Decimal('0.0')
    if product.salary_allocation_employee_id and product.salary_alloc_employee_ref and product.salary_alloc_employee_ref.global_salary_entry and pd.notna(product.salary_allocation_items_per_month) and product.salary_allocation_items_per_month > 0:
        monthly_salary = Decimal(str(product.salary_alloc_employee_ref.global_salary_entry.monthly_amount)) if pd.notna(product.salary_alloc_employee_ref.global_salary_entry.monthly_amount) else Decimal('0.0')
        alloc_items = Decimal(str(product.salary_allocation_items_per_month)); allocated_salary_cost_per_item = monthly_salary / alloc_items if alloc_items > Decimal('0.0') else Decimal('0.0')
    breakdown['allocated_salary_cost_per_item'] = allocated_salary_cost_per_item
    allocated_rent_utilities_cost_per_item = Decimal('0.0')
    global_costs_obj = db.query(GlobalCosts).filter(GlobalCosts.user_id == current_user_id).first()
    if global_costs_obj and pd.notna(product.rent_utilities_allocation_items_per_month) and product.rent_utilities_allocation_items_per_month > 0:
        rent = Decimal(str(global_costs_obj.monthly_rent)) if pd.notna(global_costs_obj.monthly_rent) else Decimal('0.0')
        utilities = Decimal(str(global_costs_obj.monthly_utilities)) if pd.notna(global_costs_obj.monthly_utilities) else Decimal('0.0')
        total_monthly_fixed_overheads = rent + utilities; alloc_items_rent = Decimal(str(product.rent_utilities_allocation_items_per_month))
        allocated_rent_utilities_cost_per_item = total_monthly_fixed_overheads / alloc_items_rent if alloc_items_rent > Decimal('0.0') else Decimal('0.0')
    breakdown['allocated_rent_utilities_cost_per_item'] = allocated_rent_utilities_cost_per_item
    breakdown['total_allocated_overheads_per_item'] = allocated_salary_cost_per_item + allocated_rent_utilities_cost_per_item
    breakdown['total_production_cost_per_item'] = breakdown['direct_cogs_per_item'] + breakdown['total_allocated_overheads_per_item']
    retail_price = Decimal(str(product.retail_price_per_item)) if pd.notna(product.retail_price_per_item) else Decimal('0.0')
    items_per_retail_order = Decimal('1.0'); retail_avg_order_val = Decimal(str(product.retail_avg_order_value)) if pd.notna(product.retail_avg_order_value) else Decimal('0.0')
    if retail_avg_order_val > Decimal('0.0') and retail_price > Decimal('0.0'): items_per_retail_order = retail_avg_order_val / retail_price
    if items_per_retail_order <= Decimal('0.0'): items_per_retail_order = Decimal('1.0') 
    retail_cc_fee_percent_val = Decimal(str(product.retail_cc_fee_percent)) if pd.notna(product.retail_cc_fee_percent) else Decimal('0.0')
    retail_platform_fee_percent_val = Decimal(str(product.retail_platform_fee_percent)) if pd.notna(product.retail_platform_fee_percent) else Decimal('0.0')
    retail_shipping_cost_paid_val = Decimal(str(product.retail_shipping_cost_paid_by_you)) if pd.notna(product.retail_shipping_cost_paid_by_you) else Decimal('0.0')
    retail_cc_fee = retail_price * retail_cc_fee_percent_val; retail_platform_fee = retail_price * retail_platform_fee_percent_val
    retail_shipping_per_item = retail_shipping_cost_paid_val / items_per_retail_order
    total_retail_channel_costs = retail_cc_fee + retail_platform_fee + retail_shipping_per_item
    total_cost_retail_item = breakdown['total_production_cost_per_item'] + total_retail_channel_costs
    profit_retail = retail_price - total_cost_retail_item
    margin_retail = (profit_retail / retail_price) * Decimal('100.0') if retail_price > Decimal('0.0') else Decimal('0.0')
    breakdown['retail_metrics'] = {"price": retail_price, "cc_fee": retail_cc_fee, "platform_fee": retail_platform_fee, "shipping_cost": retail_shipping_per_item, "total_channel_costs": total_retail_channel_costs, "total_cost_item": total_cost_retail_item, "profit": profit_retail, "margin_percent": margin_retail}
    wholesale_price = Decimal(str(product.wholesale_price_per_item)) if pd.notna(product.wholesale_price_per_item) else Decimal('0.0')
    items_per_ws_order = Decimal('1.0'); ws_avg_order_val = Decimal(str(product.wholesale_avg_order_value)) if pd.notna(product.wholesale_avg_order_value) else Decimal('0.0')
    if ws_avg_order_val > Decimal('0.0') and wholesale_price > Decimal('0.0'): items_per_ws_order = ws_avg_order_val / wholesale_price
    if items_per_ws_order <= Decimal('0.0'): items_per_ws_order = Decimal('1.0')
    ws_commission_percent_val = Decimal(str(product.wholesale_commission_percent)) if pd.notna(product.wholesale_commission_percent) else Decimal('0.0')
    ws_processing_fee_percent_val = Decimal(str(product.wholesale_processing_fee_percent)) if pd.notna(product.wholesale_processing_fee_percent) else Decimal('0.0')
    ws_flat_fee_per_order_val = Decimal(str(product.wholesale_flat_fee_per_order)) if pd.notna(product.wholesale_flat_fee_per_order) else Decimal('0.0')
    ws_commission = wholesale_price * ws_commission_percent_val; ws_processing_fee = wholesale_price * ws_processing_fee_percent_val
    ws_flat_fee_per_item = ws_flat_fee_per_order_val / items_per_ws_order
    total_wholesale_channel_costs = ws_commission + ws_processing_fee + ws_flat_fee_per_item
    total_cost_wholesale_item = breakdown['total_production_cost_per_item'] + total_wholesale_channel_costs
    profit_wholesale = wholesale_price - total_cost_wholesale_item
    margin_wholesale = (profit_wholesale / wholesale_price) * Decimal('100.0') if wholesale_price > Decimal('0.0') else Decimal('0.0')
    breakdown['wholesale_metrics'] = {"price": wholesale_price, "commission": ws_commission, "processing_fee": ws_processing_fee, "flat_fee_item_share": ws_flat_fee_per_item, "total_channel_costs": total_wholesale_channel_costs, "total_cost_item": total_cost_wholesale_item, "profit": profit_wholesale, "margin_percent": margin_wholesale}
    ws_dist_val = Decimal(str(product.distribution_wholesale_percentage)) if pd.notna(product.distribution_wholesale_percentage) else Decimal('0.0')
    rt_dist_val = Decimal('1.0') - ws_dist_val
    breakdown['blended_avg_price'] = (retail_price * rt_dist_val) + (wholesale_price * ws_dist_val)
    breakdown['blended_avg_total_cost'] = (total_cost_retail_item * rt_dist_val) + (total_cost_wholesale_item * ws_dist_val)
    breakdown['blended_avg_profit'] = breakdown['blended_avg_price'] - breakdown['blended_avg_total_cost']
    breakdown['blended_avg_margin_percent'] = (breakdown['blended_avg_profit'] / breakdown['blended_avg_price']) * Decimal('100.0') if breakdown['blended_avg_price'] > Decimal('0.0') else Decimal('0.0')
    buffer_percentage_val = Decimal(str(product.buffer_percentage)) if pd.notna(product.buffer_percentage) else Decimal('0.0')
    breakdown['cost_plus_buffer'] = breakdown['total_production_cost_per_item'] * (Decimal('1.0') + buffer_percentage_val)
    return breakdown

# --- Authenticator Setup ---
config_auth = config_auth_diagnostic_check
if 'credentials' not in config_auth or 'usernames' not in config_auth['credentials']:
    st.error("CRITICAL: 'credentials' or 'credentials.usernames' not found in the loaded config_auth.")
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
    authenticator.login() 
except Exception as e_login_widget:
    st.error(f"An error occurred with the login/registration widget: {e_login_widget}")
    st.exception(e_login_widget)
authentication_status = st.session_state.get("authentication_status")
username = st.session_state.get("username")
if 'selected_product_id' not in st.session_state: 
    st.session_state.selected_product_id = None

# --- Main Application Logic ---
if authentication_status:
    user_display_name = st.session_state.get("name", username)
    db_session_main_app = None 
    try:
        db_session_main_app = next(get_db())
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
                "Global Costs/Salaries", "Manage Products", 
                "Product Cost Breakdown", 
                "User Guide", "User Settings"
            ]
            menu_icons = [
                "bi-basket3-fill", "bi-people-fill", "bi-tools", "bi-truck", 
                "bi-globe2", "bi-box-seam-fill", "bi-bar-chart-line-fill", 
                "bi-book-half", "bi-gear-fill"
            ]
            default_selection_index = 0
            if 'main_menu_selected' in st.session_state and st.session_state.main_menu_selected in menu_titles:
                default_selection_index = menu_titles.index(st.session_state.main_menu_selected)
            else:
                st.session_state.main_menu_selected = menu_titles[default_selection_index]
            selected_option = option_menu(
                menu_title="🛠️ Main Menu", options=menu_titles, icons=menu_icons, 
                menu_icon="bi-list-task", default_index=default_selection_index,
                orientation="vertical", key="main_menu_option_selector"
            )
            if selected_option != st.session_state.main_menu_selected:
                st.session_state.main_menu_selected = selected_option
                if selected_option not in ["Manage Products", "Product Cost Breakdown"]: 
                    st.session_state.selected_product_id = None
                st.rerun()
        choice = st.session_state.main_menu_selected
        st.title(f"🧮 Product Cost Calculator: {choice}")
        
        if choice == "Manage Ingredients":
            st.header("📝 Manage Ingredients")
            st.write("Edit, add, or delete ingredients. Click **'Save Ingredient Changes'** to persist.")
            ingredients_db = db_session_main_app.query(Ingredient).filter(Ingredient.user_id == current_user_db.id).order_by(Ingredient.id).all()
            data_for_editor_ing = [{"ID": ing.id, "Name": ing.name, "Provider": ing.provider, "Price/Unit (€)": ing.price_per_unit, "Unit (kg)": ing.unit_quantity_kg, "Price URL": ing.price_url if ing.price_url else ""} for ing in ingredients_db]
            df_ing_cols = ["ID", "Name", "Provider", "Price/Unit (€)", "Unit (kg)", "Price URL"]
            df_ingredients_for_editor = pd.DataFrame(data_for_editor_ing, columns=df_ing_cols)
            if df_ingredients_for_editor.empty:
                 df_ingredients_for_editor = pd.DataFrame(columns=df_ing_cols).astype({"ID": "float64", "Name": "object", "Provider": "object", "Price/Unit (€)": "float64", "Unit (kg)": "float64", "Price URL": "object"})
            snapshot_key_ing = 'df_ingredients_snapshot'
            if snapshot_key_ing not in st.session_state or not isinstance(st.session_state.get(snapshot_key_ing), pd.DataFrame) or not st.session_state[snapshot_key_ing].columns.equals(df_ingredients_for_editor.columns):
                st.session_state[snapshot_key_ing] = df_ingredients_for_editor.copy()

            ing_display_columns_desktop = ("Name", "Provider", "Price/Unit (€)", "Unit (kg)", "Price URL")
            ing_display_columns_mobile = ("Name", "Price/Unit (€)", "Unit (kg)") 
            ing_columns_to_display = ing_display_columns_mobile if IS_MOBILE else ing_display_columns_desktop
            
            edited_df_ing = st.data_editor(
                st.session_state[snapshot_key_ing], num_rows="dynamic", key="ingredients_editor",
                column_order=ing_columns_to_display, 
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
                    original_df_snapshot_ing = st.session_state[snapshot_key_ing]; original_snapshot_ids_ing = set(original_df_snapshot_ing['ID'].dropna().astype(int))
                    edited_df_ids_ing = set(edited_df_ing['ID'].dropna().astype(int)); ids_to_delete_from_db_ing = original_snapshot_ids_ing - edited_df_ids_ing
                    for ing_id_del in ids_to_delete_from_db_ing:
                        ing_to_del = db_session_main_app.query(Ingredient).filter(Ingredient.id == ing_id_del, Ingredient.user_id == current_user_db.id).first()
                        if ing_to_del: db_session_main_app.delete(ing_to_del); st.toast(f"Deleted ID: {ing_id_del}", icon="➖")
                    for index, row in edited_df_ing.iterrows():
                        ing_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None; name_val, prov_val = row.get("Name"), row.get("Provider")
                        price_val, unit_kg_val = row.get("Price/Unit (€)"), row.get("Unit (kg)")
                        if not all([name_val, pd.notna(price_val), pd.notna(unit_kg_val)]): 
                            if ing_id is None and not any([name_val, prov_val, pd.notna(price_val), pd.notna(unit_kg_val)]): continue 
                            st.error(f"Row {index+1}: Name, Price/Unit, Unit (kg) are required. Skipping."); continue
                        prov_val = str(prov_val).strip() if prov_val and str(prov_val).strip() else None; url_val = str(row.get("Price URL", "")).strip() if row.get("Price URL") and str(row.get("Price URL", "")).strip() else None
                        if ing_id: 
                            item_to_update = db_session_main_app.query(Ingredient).filter(Ingredient.id == ing_id, Ingredient.user_id == current_user_db.id).first()
                            if item_to_update:
                                changed = False
                                if item_to_update.name != name_val: item_to_update.name = name_val; changed=True
                                if item_to_update.provider != prov_val: item_to_update.provider = prov_val; changed=True
                                if item_to_update.price_per_unit != Decimal(str(price_val)): item_to_update.price_per_unit = Decimal(str(price_val)); changed=True 
                                if item_to_update.unit_quantity_kg != Decimal(str(unit_kg_val)): item_to_update.unit_quantity_kg = Decimal(str(unit_kg_val)); changed=True 
                                if item_to_update.price_url != url_val: item_to_update.price_url = url_val; changed=True
                                if changed: st.toast(f"Updated ID: {ing_id}", icon="🔄")
                    new_rows_df = edited_df_ing[edited_df_ing['ID'].isna()]
                    for index, row in new_rows_df.iterrows():
                        name_val, prov_val = row.get("Name"), row.get("Provider"); price_val, unit_kg_val = row.get("Price/Unit (€)"), row.get("Unit (kg)")
                        if not all([name_val, pd.notna(price_val), pd.notna(unit_kg_val)]): 
                            if not any([name_val, prov_val, pd.notna(price_val), pd.notna(unit_kg_val)]): continue
                            st.error(f"New Row (approx original index {index+1}): Name, Price/Unit, Unit (kg) are required. Skipping."); continue
                        prov_val = str(prov_val).strip() if prov_val and str(prov_val).strip() else None; url_val = str(row.get("Price URL", "")).strip() if row.get("Price URL") and str(row.get("Price URL", "")).strip() else None
                        db_session_main_app.add(Ingredient(user_id=current_user_db.id, name=name_val, provider=prov_val, price_per_unit=Decimal(str(price_val)), unit_quantity_kg=Decimal(str(unit_kg_val)), price_url=url_val))
                        st.toast(f"Added: {name_val}", icon="➕")
                    db_session_main_app.commit(); st.success("Ingredient changes saved!"); st.session_state[snapshot_key_ing] = edited_df_ing.copy(); st.rerun()
                except Exception as e_save_ing: db_session_main_app.rollback(); st.error(f"Error saving ingredients: {e_save_ing}"); st.exception(e_save_ing)

        elif choice == "Manage Employees":
            st.header("👥 Manage Employees")
            st.write("Edit, add, or delete employees. Click **'Save Employee Changes'** to persist.")
            employees_db = db_session_main_app.query(Employee).filter(Employee.user_id == current_user_db.id).order_by(Employee.id).all()
            data_for_editor_emp = [{"ID": emp.id, "Name": emp.name, "Hourly Rate (€)": emp.hourly_rate, "Role": emp.role} for emp in employees_db]
            df_emp_cols = ["ID", "Name", "Hourly Rate (€)", "Role"]; df_employees_for_editor = pd.DataFrame(data_for_editor_emp, columns=df_emp_cols)
            if df_employees_for_editor.empty: df_employees_for_editor = pd.DataFrame(columns=df_emp_cols).astype({"ID": "float64", "Name": "object", "Hourly Rate (€)": "float64", "Role": "object"})
            snapshot_key_emp = 'df_employees_snapshot'
            if snapshot_key_emp not in st.session_state or not isinstance(st.session_state.get(snapshot_key_emp), pd.DataFrame) or not st.session_state[snapshot_key_emp].columns.equals(df_employees_for_editor.columns): st.session_state[snapshot_key_emp] = df_employees_for_editor.copy()
            
            emp_display_columns_desktop = ("Name", "Hourly Rate (€)", "Role")
            emp_display_columns_mobile = ("Name", "Hourly Rate (€)") 
            emp_columns_to_display = emp_display_columns_mobile if IS_MOBILE else emp_display_columns_desktop
            
            edited_df_emp = st.data_editor(st.session_state[snapshot_key_emp], num_rows="dynamic", key="employees_editor", 
                                           column_order=emp_columns_to_display, 
                                           column_config={"Name": st.column_config.TextColumn("Employee Name*", required=True),"Hourly Rate (€)": st.column_config.NumberColumn("Hourly Rate (€)*", required=True, min_value=0.00, step=0.01, format="%.2f"),"Role": st.column_config.TextColumn("Role (Optional)")}, 
                                           use_container_width=True, hide_index=True)
            if st.button("Save Employee Changes", type="primary"):
                try:
                    original_df_snapshot_emp = st.session_state[snapshot_key_emp]; original_snapshot_ids_emp = set(original_df_snapshot_emp['ID'].dropna().astype(int))
                    edited_df_ids_emp = set(edited_df_emp['ID'].dropna().astype(int)); ids_to_delete_from_db_emp = original_snapshot_ids_emp - edited_df_ids_emp
                    for emp_id_del in ids_to_delete_from_db_emp:
                        emp_to_del = db_session_main_app.query(Employee).filter(Employee.id == emp_id_del, Employee.user_id == current_user_db.id).first()
                        if emp_to_del: db_session_main_app.delete(emp_to_del); st.toast(f"Deleted employee ID: {emp_id_del}", icon="➖")
                    for index, row in edited_df_emp.iterrows():
                        emp_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None; name_val, rate_val, role_val = row.get("Name"), row.get("Hourly Rate (€)"), row.get("Role")
                        if role_val is None and "Role" not in edited_df_emp.columns: role_val = "" # Default if column hidden
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
                    new_rows_df_emp = edited_df_emp[edited_df_emp['ID'].isna()]
                    for index, row in new_rows_df_emp.iterrows():
                        name_val, rate_val, role_val = row.get("Name"), row.get("Hourly Rate (€)"), row.get("Role")
                        if role_val is None and "Role" not in edited_df_emp.columns: role_val = ""
                        if not all([name_val, pd.notna(rate_val)]):
                            if not any([name_val, pd.notna(rate_val), role_val]): continue
                            st.error(f"New Row (approx original index {index+1}): Name and Hourly Rate are required. Skipping."); continue
                        role_val = str(role_val).strip() if role_val and str(role_val).strip() else None
                        db_session_main_app.add(Employee(user_id=current_user_db.id, name=name_val, hourly_rate=Decimal(str(rate_val)), role=role_val)) 
                        st.toast(f"Added employee: {name_val}", icon="➕")
                    db_session_main_app.commit(); st.success("Employee changes saved!"); st.session_state[snapshot_key_emp] = edited_df_emp.copy(); st.rerun()
                except Exception as e_save_emp: db_session_main_app.rollback(); st.error(f"Error saving employees: {e_save_emp}"); st.exception(e_save_emp)

        elif choice == "Manage Production Tasks":
            st.header("🏭 Manage Standard Production Tasks")
            st.write("Define common tasks involved in production. Click **'Save Production Task Changes'** to persist.")
            tasks_db = db_session_main_app.query(StandardProductionTask).filter(StandardProductionTask.user_id == current_user_db.id).order_by(StandardProductionTask.id).all()
            data_for_editor_ptask = [{"ID": task.id, "Task Name": task.task_name} for task in tasks_db]
            df_ptask_cols = ["ID", "Task Name"]; df_ptasks_for_editor = pd.DataFrame(data_for_editor_ptask, columns=df_ptask_cols)
            if df_ptasks_for_editor.empty: df_ptasks_for_editor = pd.DataFrame(columns=df_ptask_cols).astype({"ID": "float64", "Task Name": "object"})
            snapshot_key_ptask = 'df_ptasks_snapshot'
            if snapshot_key_ptask not in st.session_state or not isinstance(st.session_state.get(snapshot_key_ptask), pd.DataFrame) or not st.session_state[snapshot_key_ptask].columns.equals(df_ptasks_for_editor.columns): st.session_state[snapshot_key_ptask] = df_ptasks_for_editor.copy()
            ptask_display_columns = ("Task Name",)
            edited_df_ptask = st.data_editor(st.session_state[snapshot_key_ptask], num_rows="dynamic", key="prod_tasks_editor", column_order=ptask_display_columns, column_config={"Task Name": st.column_config.TextColumn("Task Name*", required=True)}, use_container_width=True, hide_index=True)
            if st.button("Save Production Task Changes", type="primary"):
                try:
                    original_df_snapshot_ptask = st.session_state[snapshot_key_ptask]; original_snapshot_ids_ptask = set(original_df_snapshot_ptask['ID'].dropna().astype(int))
                    edited_df_ids_ptask = set(edited_df_ptask['ID'].dropna().astype(int)); ids_to_delete_from_db_ptask = original_snapshot_ids_ptask - edited_df_ids_ptask
                    for task_id_del in ids_to_delete_from_db_ptask:
                        task_to_del = db_session_main_app.query(StandardProductionTask).filter(StandardProductionTask.id == task_id_del, StandardProductionTask.user_id == current_user_db.id).first()
                        if task_to_del: db_session_main_app.delete(task_to_del); st.toast(f"Deleted task ID: {task_id_del}", icon="➖")
                    for index, row in edited_df_ptask.iterrows():
                        task_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None; name_val = row.get("Task Name")
                        if not name_val:
                            if task_id is None and not name_val: continue
                            st.error(f"Row {index+1}: Task Name is required. Skipping."); continue
                        if task_id: 
                            item_to_update = db_session_main_app.query(StandardProductionTask).filter(StandardProductionTask.id == task_id, StandardProductionTask.user_id == current_user_db.id).first()
                            if item_to_update and item_to_update.task_name != name_val: item_to_update.task_name = name_val; st.toast(f"Updated task ID: {task_id}", icon="🔄")
                    new_rows_df_ptask = edited_df_ptask[edited_df_ptask['ID'].isna()]
                    for index, row in new_rows_df_ptask.iterrows():
                        name_val = row.get("Task Name")
                        if not name_val:
                            if not name_val: continue
                            st.error(f"New Row (approx original index {index+1}): Task Name is required. Skipping."); continue
                        db_session_main_app.add(StandardProductionTask(user_id=current_user_db.id, task_name=name_val)); st.toast(f"Added task: {name_val}", icon="➕")
                    db_session_main_app.commit(); st.success("Production Task changes saved!"); st.session_state[snapshot_key_ptask] = edited_df_ptask.copy(); st.rerun()
                except Exception as e_save_ptask: db_session_main_app.rollback(); st.error(f"Error saving production tasks: {e_save_ptask}"); st.exception(e_save_ptask)

        elif choice == "Manage Shipping Tasks":
            st.header("🚚 Manage Standard Shipping Tasks")
            st.write("Define common tasks for shipping. Click **'Save Shipping Task Changes'** to persist.")
            tasks_db_ship = db_session_main_app.query(StandardShippingTask).filter(StandardShippingTask.user_id == current_user_db.id).order_by(StandardShippingTask.id).all()
            data_for_editor_stask = [{"ID": task.id, "Task Name": task.task_name} for task in tasks_db_ship]
            df_stask_cols = ["ID", "Task Name"]; df_stasks_for_editor = pd.DataFrame(data_for_editor_stask, columns=df_stask_cols)
            if df_stasks_for_editor.empty: df_stasks_for_editor = pd.DataFrame(columns=df_stask_cols).astype({"ID": "float64", "Task Name": "object"})
            snapshot_key_stask = 'df_stasks_snapshot'
            if snapshot_key_stask not in st.session_state or not isinstance(st.session_state.get(snapshot_key_stask), pd.DataFrame) or not st.session_state[snapshot_key_stask].columns.equals(df_stasks_for_editor.columns): st.session_state[snapshot_key_stask] = df_stasks_for_editor.copy()
            stask_display_columns = ("Task Name",)
            edited_df_stask = st.data_editor(st.session_state[snapshot_key_stask], num_rows="dynamic", key="ship_tasks_editor", column_order=stask_display_columns, column_config={"Task Name": st.column_config.TextColumn("Task Name*", required=True)}, use_container_width=True, hide_index=True)
            if st.button("Save Shipping Task Changes", type="primary"):
                try:
                    original_df_snapshot_stask = st.session_state[snapshot_key_stask]; original_snapshot_ids_stask = set(original_df_snapshot_stask['ID'].dropna().astype(int))
                    edited_df_ids_stask = set(edited_df_stask['ID'].dropna().astype(int)); ids_to_delete_from_db_stask = original_snapshot_ids_stask - edited_df_ids_stask
                    for task_id_del in ids_to_delete_from_db_stask:
                        task_to_del = db_session_main_app.query(StandardShippingTask).filter(StandardShippingTask.id == task_id_del, StandardShippingTask.user_id == current_user_db.id).first()
                        if task_to_del: db_session_main_app.delete(task_to_del); st.toast(f"Deleted task ID: {task_id_del}", icon="➖")
                    for index, row in edited_df_stask.iterrows():
                        task_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None; name_val = row.get("Task Name")
                        if not name_val:
                            if task_id is None and not name_val: continue
                            st.error(f"Row {index+1}: Task Name is required. Skipping."); continue
                        if task_id:
                            item_to_update = db_session_main_app.query(StandardShippingTask).filter(StandardShippingTask.id == task_id, StandardShippingTask.user_id == current_user_db.id).first()
                            if item_to_update and item_to_update.task_name != name_val: item_to_update.task_name = name_val; st.toast(f"Updated task ID: {task_id}", icon="🔄")
                    new_rows_df_stask = edited_df_stask[edited_df_stask['ID'].isna()]
                    for index, row in new_rows_df_stask.iterrows():
                        name_val = row.get("Task Name")
                        if not name_val:
                            if not name_val: continue
                            st.error(f"New Row (approx original index {index+1}): Task Name is required. Skipping."); continue
                        db_session_main_app.add(StandardShippingTask(user_id=current_user_db.id, task_name=name_val)); st.toast(f"Added task: {name_val}", icon="➕")
                    db_session_main_app.commit(); st.success("Shipping Task changes saved!"); st.session_state[snapshot_key_stask] = edited_df_stask.copy(); st.rerun()
                except Exception as e_save_stask: db_session_main_app.rollback(); st.error(f"Error saving shipping tasks: {e_save_stask}"); st.exception(e_save_stask)
        
        elif choice == "Global Costs/Salaries":
            st.header("🌍 Global Costs & Salaries")
            st.info("Manage global fixed costs and monthly salaries. These are used for overhead allocation.")
            with st.expander("💰 Monthly Fixed Overheads", expanded=True):
                global_costs_obj = db_session_main_app.query(GlobalCosts).filter(GlobalCosts.user_id == current_user_db.id).first()
                if not global_costs_obj: global_costs_obj = GlobalCosts(user_id=current_user_db.id, monthly_rent=Decimal('0.0'), monthly_utilities=Decimal('0.0'))
                rent_val = st.number_input("Global Monthly Rent (€)", value=float(global_costs_obj.monthly_rent or Decimal('0.0')), min_value=0.0, format="%.2f", key="global_rent")
                util_val = st.number_input("Global Monthly Utilities (€)", value=float(global_costs_obj.monthly_utilities or Decimal('0.0')), min_value=0.0, format="%.2f", key="global_utilities")
                if st.button("Save Global Overheads", key="save_global_overheads", type="primary"):
                    global_costs_obj.monthly_rent = Decimal(str(rent_val)); global_costs_obj.monthly_utilities = Decimal(str(util_val))
                    db_session_main_app.add(global_costs_obj)
                    try: db_session_main_app.commit(); st.success("Global overheads saved!"); st.rerun()
                    except Exception as e_save_global: db_session_main_app.rollback(); st.error(f"Error saving global overheads: {e_save_global}")
            st.markdown("---")
            st.subheader("💵 Global Monthly Salaries")
            st.write("Edit, add, or delete global salaries.")
            global_salaries_db = db_session_main_app.query(GlobalSalary).options(joinedload(GlobalSalary.employee_ref)).filter(GlobalSalary.user_id == current_user_db.id).order_by(GlobalSalary.id).all()
            all_employees_list_gs = db_session_main_app.query(Employee).filter(Employee.user_id == current_user_db.id).all() 
            employee_options_gs = {emp.name: emp.id for emp in all_employees_list_gs}
            employee_names_gs = list(employee_options_gs.keys()) if employee_options_gs else ["No employees defined"]
            data_for_gs_editor = []
            if global_salaries_db:
                for gs in global_salaries_db:
                    if gs.employee_ref: data_for_gs_editor.append({"ID": gs.id, "Employee Name": gs.employee_ref.name, "Monthly Salary (€)": gs.monthly_amount})
            df_gs_cols = ["ID", "Employee Name", "Monthly Salary (€)"]; df_gs_for_editor = pd.DataFrame(data_for_gs_editor, columns=df_gs_cols)
            if df_gs_for_editor.empty: df_gs_for_editor = pd.DataFrame(columns=df_gs_cols).astype({"ID":"float64", "Employee Name":"object", "Monthly Salary (€)":"float64"})
            snapshot_key_gs = 'df_gs_snapshot'
            if snapshot_key_gs not in st.session_state or not isinstance(st.session_state.get(snapshot_key_gs), pd.DataFrame) or not st.session_state[snapshot_key_gs].columns.equals(df_gs_for_editor.columns): st.session_state[snapshot_key_gs] = df_gs_for_editor.copy()
            
            gs_display_columns_desktop = ("Employee Name", "Monthly Salary (€)")
            gs_display_columns_mobile = ("Employee Name",) # Salary might be less critical for quick mobile view
            gs_columns_to_display = gs_display_columns_mobile if IS_MOBILE else gs_display_columns_desktop

            edited_df_gs = st.data_editor(st.session_state[snapshot_key_gs], num_rows="dynamic", key="global_salaries_editor", 
                                          column_order=gs_columns_to_display, 
                                          column_config={"Employee Name": st.column_config.SelectboxColumn("Employee*", options=employee_names_gs, required=True), "Monthly Salary (€)": st.column_config.NumberColumn("Monthly Salary (€)*", required=True, min_value=0.0, step=10.0, format="%.2f")}, 
                                          use_container_width=True, hide_index=True)
            if st.button("Save Global Salaries", type="primary"):
                try:
                    original_df_snapshot_gs = st.session_state[snapshot_key_gs]; original_snapshot_ids_gs = set(original_df_snapshot_gs['ID'].dropna().astype(int))
                    edited_df_ids_gs = set(edited_df_gs['ID'].dropna().astype(int)); ids_to_delete_from_db_gs = original_snapshot_ids_gs - edited_df_ids_gs
                    for gs_id_del in ids_to_delete_from_db_gs:
                        gs_to_del = db_session_main_app.query(GlobalSalary).filter(GlobalSalary.id == gs_id_del, GlobalSalary.user_id == current_user_db.id).first()
                        if gs_to_del: db_session_main_app.delete(gs_to_del); st.toast(f"Deleted global salary ID: {gs_id_del}", icon="➖")
                    for index, row in edited_df_gs.iterrows():
                        gs_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None; emp_name_val, amount_val = row.get("Employee Name"), row.get("Monthly Salary (€)")
                        if amount_val is None and "Monthly Salary (€)" not in edited_df_gs.columns: 
                            st.error(f"Row {index+1} (Global Salaries): Salary amount missing. Please edit on a wider screen or ensure data is complete."); continue
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
                        if amount_val is None and "Monthly Salary (€)" not in edited_df_gs.columns: 
                            st.error(f"New Row (Global Salaries): Salary amount missing."); continue
                        if not all([emp_name_val, emp_name_val != "No employees defined", pd.notna(amount_val)]):
                            if not any([emp_name_val, pd.notna(amount_val)]): continue
                            st.error(f"New Row (Global Salaries - approx original index {index+1}): Invalid data. Skipping."); continue
                        employee_id_for_gs = employee_options_gs.get(emp_name_val)
                        if not employee_id_for_gs: st.error(f"New Row (Global Salaries - approx original index {index+1}): Employee '{emp_name_val}' not found. Skipping."); continue
                        existing_salary = db_session_main_app.query(GlobalSalary).filter(GlobalSalary.user_id == current_user_db.id, GlobalSalary.employee_id == employee_id_for_gs).first()
                        if existing_salary: st.warning(f"Employee '{emp_name_val}' already has a global salary. Edit existing. Skipping addition."); continue
                        db_session_main_app.add(GlobalSalary(user_id=current_user_db.id, employee_id=employee_id_for_gs, monthly_amount=Decimal(str(amount_val)))); st.toast(f"Added global salary for {emp_name_val}", icon="➕")
                    db_session_main_app.commit(); st.success("Global salaries saved!"); st.session_state[snapshot_key_gs] = edited_df_gs.copy(); st.rerun()
                except IntegrityError: db_session_main_app.rollback(); st.error("Error: An employee can only have one global salary entry.")
                except Exception as e_save_gs: db_session_main_app.rollback(); st.error(f"Error saving global salaries: {e_save_gs}"); st.exception(e_save_gs)

        elif choice == "Manage Products":
            st.header("📦 Manage Products")
            st.write("Add, edit, or delete main product attributes. Select a product to manage its detailed components.")
            products_db = db_session_main_app.query(Product).filter(Product.user_id == current_user_db.id).order_by(Product.id).all()
            product_editor_columns = ["ID", "Product Name", "Batch Size", "Monthly Production"]
            data_for_editor_prod = [{"ID": p.id, "Product Name": p.product_name, "Batch Size": p.batch_size_items, "Monthly Production": p.monthly_production_items} for p in products_db]
            df_products_for_editor = pd.DataFrame(data_for_editor_prod, columns=product_editor_columns)
            if df_products_for_editor.empty: df_products_for_editor = pd.DataFrame(columns=product_editor_columns).astype({"ID": "float64", "Product Name": "object", "Batch Size": "int64", "Monthly Production": "int64"})
            snapshot_key_prod = 'df_products_snapshot'
            if snapshot_key_prod not in st.session_state or not isinstance(st.session_state.get(snapshot_key_prod), pd.DataFrame) or not st.session_state[snapshot_key_prod].columns.equals(df_products_for_editor.columns): st.session_state[snapshot_key_prod] = df_products_for_editor.copy()
            
            prod_display_columns_desktop = ("Product Name", "Batch Size", "Monthly Production")
            prod_display_columns_mobile = ("Product Name", "Batch Size") 
            prod_columns_to_display = prod_display_columns_mobile if IS_MOBILE else prod_display_columns_desktop
            
            product_column_config = {
                "Product Name": st.column_config.TextColumn("Product Name*", required=True, width="large"),
                "Batch Size": st.column_config.NumberColumn("Batch Size (items)*", required=True, min_value=1, step=1, format="%d", width="medium"),
                "Monthly Production": st.column_config.NumberColumn("Monthly Prod (items)*", required=True, min_value=0, step=1, format="%d", width="medium")}
            edited_df_prod = st.data_editor(st.session_state[snapshot_key_prod], num_rows="dynamic", key="products_editor", 
                                            column_order=prod_columns_to_display, 
                                            column_config=product_column_config, use_container_width=True, hide_index=True)
            if st.button("Save Product Attribute Changes", type="primary"):
                try:
                    original_df_snapshot_prod = st.session_state[snapshot_key_prod]; original_snapshot_ids_prod = set(original_df_snapshot_prod['ID'].dropna().astype(int))
                    edited_df_ids_prod = set(edited_df_prod['ID'].dropna().astype(int)); ids_to_delete_from_db_prod = original_snapshot_ids_prod - edited_df_ids_prod
                    for p_id_del in ids_to_delete_from_db_prod:
                        prod_to_del = db_session_main_app.query(Product).filter(Product.id == p_id_del, Product.user_id == current_user_db.id).first()
                        if prod_to_del: db_session_main_app.delete(prod_to_del); st.toast(f"Deleted product ID: {p_id_del}", icon="➖")
                        if st.session_state.selected_product_id == p_id_del: st.session_state.selected_product_id = None
                    for index, edited_row in edited_df_prod.iterrows():
                        p_id = edited_row.get('ID'); p_id = int(p_id) if pd.notna(p_id) else None
                        name_val, batch_val = edited_row.get("Product Name"), edited_row.get("Batch Size")
                        monthly_val = edited_row.get("Monthly Production") # Get it regardless of display
                        
                        # Validation logic needs to be careful if a column is hidden
                        is_monthly_prod_expected = "Monthly Production" in prod_columns_to_display # Check if it was displayed
                        
                        if not name_val or not pd.notna(batch_val) or (is_monthly_prod_expected and not pd.notna(monthly_val)):
                            if p_id is None and not any([name_val, pd.notna(batch_val)]): continue # Skip truly empty new rows
                            st.error(f"Row {index+1} (Products): Required fields missing. Ensure Name, Batch Size, and Monthly Production (if visible) are filled. Skipping."); continue
                        
                        if p_id: 
                            p_to_update = db_session_main_app.query(Product).filter(Product.id == p_id, Product.user_id == current_user_db.id).first()
                            if p_to_update:
                                changed = False
                                if p_to_update.product_name != name_val: p_to_update.product_name = name_val; changed=True
                                if p_to_update.batch_size_items != int(batch_val): p_to_update.batch_size_items = int(batch_val); changed=True
                                # Only update monthly_production if it was part of the edited form OR if it's a new row where it's expected
                                if is_monthly_prod_expected and pd.notna(monthly_val) and p_to_update.monthly_production_items != int(monthly_val):
                                    p_to_update.monthly_production_items = int(monthly_val); changed=True
                                elif not is_monthly_prod_expected and p_to_update.monthly_production_items is None: # If hidden and was None, maybe default
                                     p_to_update.monthly_production_items = 0 # Or keep as is if that's preferred
                                if changed: st.toast(f"Updated product ID: {p_id}", icon="🔄")
                    new_rows_df_prod = edited_df_prod[edited_df_prod['ID'].isna()]
                    for index, row in new_rows_df_prod.iterrows():
                        name_val, batch_val = row.get("Product Name"), row.get("Batch Size")
                        monthly_val = row.get("Monthly Production")
                        is_monthly_prod_expected_new = "Monthly Production" in prod_columns_to_display

                        if not name_val or not pd.notna(batch_val) or (is_monthly_prod_expected_new and not pd.notna(monthly_val)):
                            if not any([name_val, pd.notna(batch_val)]): continue
                            st.error(f"New Row (approx original index {index+1}): Required fields missing. Ensure Name, Batch Size, and Monthly Production (if visible) are filled. Skipping."); continue
                        
                        # Provide a default for monthly_production if it's not in the form (hidden) and not provided
                        final_monthly_val = int(monthly_val) if pd.notna(monthly_val) else (p_to_update.monthly_production_items if p_id and p_to_update else 0)


                        new_prod = Product(user_id=current_user_db.id, product_name=name_val, 
                                           batch_size_items=int(batch_val), 
                                           monthly_production_items=final_monthly_val)
                        db_session_main_app.add(new_prod); db_session_main_app.flush(); 
                        st.session_state.selected_product_id = new_prod.id 
                        st.toast(f"Added: {name_val}. Selected for detail editing.", icon="➕")
                    db_session_main_app.commit(); st.success("Product attribute changes saved!"); st.session_state[snapshot_key_prod] = edited_df_prod.copy(); st.rerun()
                except Exception as e_save_prod: db_session_main_app.rollback(); st.error(f"Error saving products: {e_save_prod}"); st.exception(e_save_prod)

            st.markdown("---")
            product_list_for_details = db_session_main_app.query(Product).filter(Product.user_id == current_user_db.id).order_by(Product.product_name).all()
            product_names_for_select = {p.product_name: p.id for p in product_list_for_details}
            if product_list_for_details:
                current_selected_name_for_dropdown = None
                if st.session_state.selected_product_id:
                    for name_key, id_val in product_names_for_select.items():
                        if id_val == st.session_state.selected_product_id: current_selected_name_for_dropdown = name_key; break
                if not current_selected_name_for_dropdown or (st.session_state.selected_product_id and st.session_state.selected_product_id not in product_names_for_select.values()):
                    current_selected_name_for_dropdown = product_list_for_details[0].product_name
                    st.session_state.selected_product_id = product_names_for_select[current_selected_name_for_dropdown]
                selected_product_name_for_details = st.selectbox("Select Product to Manage Details:", options=list(product_names_for_select.keys()), index=list(product_names_for_select.keys()).index(current_selected_name_for_dropdown) if current_selected_name_for_dropdown in product_names_for_select else 0, key="product_detail_selector", placeholder="Choose a product...")
                if selected_product_name_for_details and product_names_for_select.get(selected_product_name_for_details) != st.session_state.selected_product_id:
                    st.session_state.selected_product_id = product_names_for_select[selected_product_name_for_details]; st.rerun()
            else:
                st.info("No products available to manage details. Please add a product above.")
                if st.session_state.selected_product_id is not None: st.session_state.selected_product_id = None; st.rerun()

            if st.session_state.selected_product_id:
                selected_product_object = db_session_main_app.query(Product).options(selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref), selectinload(Product.production_tasks).joinedload(ProductProductionTask.employee_ref), selectinload(Product.production_tasks).joinedload(ProductProductionTask.standard_task_ref), selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.employee_ref), selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.standard_task_ref), joinedload(Product.salary_alloc_employee_ref).joinedload(Employee.global_salary_entry)).filter(Product.id == st.session_state.selected_product_id, Product.user_id == current_user_db.id).first()
                if not selected_product_object: 
                    st.warning("The previously selected product could not be found. Please select another product.")
                    st.session_state.selected_product_id = None
                else:
                    st.subheader(f"Managing Details for: **{selected_product_object.product_name}**")
                    with st.expander("🧪 Product Materials", expanded=True):
                        all_ingredients_db = db_session_main_app.query(Ingredient).filter(Ingredient.user_id == current_user_db.id).all()
                        ingredient_display_options = [create_ingredient_display_string(ing.name, ing.provider) for ing in all_ingredients_db] if all_ingredients_db else ["No ingredients defined globally"]
                        data_for_pm_editor = []
                        if selected_product_object.materials: 
                            for pm in selected_product_object.materials:
                                if pm.ingredient_ref: data_for_pm_editor.append({"ID": pm.id, "Ingredient": create_ingredient_display_string(pm.ingredient_ref.name, pm.ingredient_ref.provider), "Quantity (g)": pm.quantity_grams})
                        df_pm_cols = ["ID", "Ingredient", "Quantity (g)"]; df_pm_for_editor = pd.DataFrame(data_for_pm_editor, columns=df_pm_cols)
                        if df_pm_for_editor.empty: df_pm_for_editor = pd.DataFrame(columns=df_pm_cols).astype({"ID":"float64", "Ingredient":"object", "Quantity (g)":"float64"})
                        snapshot_key_pm = f'df_pm_snapshot_{selected_product_object.id}'
                        if snapshot_key_pm not in st.session_state or not isinstance(st.session_state.get(snapshot_key_pm), pd.DataFrame) or not st.session_state[snapshot_key_pm].columns.equals(df_pm_for_editor.columns): st.session_state[snapshot_key_pm] = df_pm_for_editor.copy()
                        pm_display_columns = ("Ingredient", "Quantity (g)")
                        edited_df_pm = st.data_editor(st.session_state[snapshot_key_pm], num_rows="dynamic", key=f"pm_editor_{selected_product_object.id}", column_order=pm_display_columns, column_config={"Ingredient": st.column_config.SelectboxColumn("Ingredient (Provider)*", options=ingredient_display_options, required=True), "Quantity (g)": st.column_config.NumberColumn("Quantity (grams)*", required=True, min_value=0.001, step=0.01, format="%.3f")}, use_container_width=True, hide_index=True)
                        if st.button(f"Save Materials for {selected_product_object.product_name}", key=f"save_pm_{selected_product_object.id}", type="primary"):
                            try:
                                original_df_snapshot_pm = st.session_state[snapshot_key_pm]; original_snapshot_ids_pm = set(original_df_snapshot_pm['ID'].dropna().astype(int))
                                edited_df_ids_pm = set(edited_df_pm['ID'].dropna().astype(int)); ids_to_delete_from_db_pm = original_snapshot_ids_pm - edited_df_ids_pm
                                for pm_id_del in ids_to_delete_from_db_pm:
                                    pm_to_del = db_session_main_app.query(ProductMaterial).filter(ProductMaterial.id == pm_id_del, ProductMaterial.product_id == selected_product_object.id).first()
                                    if pm_to_del: db_session_main_app.delete(pm_to_del); st.toast(f"Deleted material ID: {pm_id_del}", icon="➖")
                                for index, row in edited_df_pm.iterrows():
                                    pm_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None; ing_display_val, qty_val = row.get("Ingredient"), row.get("Quantity (g)")
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
                                    db_session_main_app.add(ProductMaterial(product_id=selected_product_object.id, ingredient_id=ingredient_id_for_row, quantity_grams=Decimal(str(qty_val)))); st.toast(f"Added material: {ing_display_val}", icon="➕")
                                db_session_main_app.commit(); st.success(f"Materials for '{selected_product_object.product_name}' saved!"); st.session_state[snapshot_key_pm] = edited_df_pm.copy(); st.rerun()
                            except Exception as e_save_pm: db_session_main_app.rollback(); st.error(f"Error saving materials: {e_save_pm}"); st.exception(e_save_pm)
                    
                    with st.expander("🛠️ Product Production Tasks", expanded=False):
                        all_std_prod_tasks_db = db_session_main_app.query(StandardProductionTask).filter(StandardProductionTask.user_id == current_user_db.id).all()
                        std_prod_task_options = [task.task_name for task in all_std_prod_tasks_db] if all_std_prod_tasks_db else ["No standard prod tasks defined"]
                        all_employees_db_ppt = db_session_main_app.query(Employee).filter(Employee.user_id == current_user_db.id).all()
                        employee_name_options_ppt = [emp.name for emp in all_employees_db_ppt] if all_employees_db_ppt else ["No employees defined"]
                        data_for_ppt_editor = []
                        if selected_product_object.production_tasks:
                            for ppt in selected_product_object.production_tasks:
                                if ppt.standard_task_ref and ppt.employee_ref: data_for_ppt_editor.append({"ID": ppt.id, "Task": ppt.standard_task_ref.task_name, "Employee": ppt.employee_ref.name, "Time (min)": ppt.time_minutes, "# Items in Task": ppt.items_processed_in_task})
                        df_ppt_cols = ["ID", "Task", "Employee", "Time (min)", "# Items in Task"]; df_ppt_for_editor = pd.DataFrame(data_for_ppt_editor, columns=df_ppt_cols)
                        if df_ppt_for_editor.empty: df_ppt_for_editor = pd.DataFrame(columns=df_ppt_cols).astype({"ID":"float64", "Task":"object", "Employee":"object", "Time (min)":"float64", "# Items in Task":"int64"})
                        snapshot_key_ppt = f'df_ppt_snapshot_{selected_product_object.id}'
                        if snapshot_key_ppt not in st.session_state or not isinstance(st.session_state.get(snapshot_key_ppt), pd.DataFrame) or not st.session_state[snapshot_key_ppt].columns.equals(df_ppt_for_editor.columns): st.session_state[snapshot_key_ppt] = df_ppt_for_editor.copy()
                        
                        ppt_display_columns_desktop = ("Task", "Employee", "Time (min)", "# Items in Task")
                        ppt_display_columns_mobile = ("Task", "Time (min)") # Employee and #Items might be too much for mobile
                        ppt_columns_to_display = ppt_display_columns_mobile if IS_MOBILE else ppt_display_columns_desktop

                        edited_df_ppt = st.data_editor(st.session_state[snapshot_key_ppt], num_rows="dynamic", key=f"ppt_editor_{selected_product_object.id}", 
                                                       column_order=ppt_columns_to_display, 
                                                       column_config={"Task": st.column_config.SelectboxColumn("Task*", options=std_prod_task_options, required=True), "Employee": st.column_config.SelectboxColumn("Performed By*", options=employee_name_options_ppt, required=True), "Time (min)": st.column_config.NumberColumn("Time (min)*", required=True, min_value=0.0, step=0.1, format="%.1f"),"# Items in Task": st.column_config.NumberColumn("# Items in Task*", required=True, min_value=1, step=1, format="%d")}, 
                                                       use_container_width=True, hide_index=True)
                        if st.button(f"Save Production Tasks for {selected_product_object.product_name}", key=f"save_ppt_{selected_product_object.id}", type="primary"):
                            try:
                                original_df_snapshot_ppt = st.session_state[snapshot_key_ppt]; original_snapshot_ids_ppt = set(original_df_snapshot_ppt['ID'].dropna().astype(int))
                                edited_df_ids_ppt = set(edited_df_ppt['ID'].dropna().astype(int)); ids_to_delete_from_db_ppt = original_snapshot_ids_ppt - edited_df_ids_ppt
                                for ppt_id_del in ids_to_delete_from_db_ppt:
                                    ppt_to_del = db_session_main_app.query(ProductProductionTask).filter(ProductProductionTask.id == ppt_id_del, ProductProductionTask.product_id == selected_product_object.id).first()
                                    if ppt_to_del: db_session_main_app.delete(ppt_to_del); st.toast(f"Deleted prod task ID: {ppt_id_del}", icon="➖")
                                for index, row in edited_df_ppt.iterrows():
                                    ppt_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                                    task_name_val, emp_name_val, time_val, items_val = row.get("Task"), row.get("Employee"), row.get("Time (min)"), row.get("# Items in Task")
                                    if emp_name_val is None and "Employee" not in edited_df_ppt.columns: 
                                        st.error(f"Row {index+1} (Prod Tasks): Employee data is missing. Please edit on a wider screen or ensure data is complete."); continue
                                    if items_val is None and "# Items in Task" not in edited_df_ppt.columns:
                                        st.error(f"Row {index+1} (Prod Tasks): '# Items in Task' data is missing. Please edit on a wider screen or ensure data is complete."); continue
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
                                    if emp_name_val is None and "Employee" not in edited_df_ppt.columns: st.error(f"New Row (Prod Tasks): Employee data missing."); continue
                                    if items_val is None and "# Items in Task" not in edited_df_ppt.columns: st.error(f"New Row (Prod Tasks): '# Items in Task' data missing."); continue
                                    if not all([task_name_val, task_name_val != "No standard prod tasks defined", emp_name_val, emp_name_val != "No employees defined", pd.notna(time_val), pd.notna(items_val), int(items_val or 0) > 0]):
                                        if not any([task_name_val, emp_name_val, pd.notna(time_val), pd.notna(items_val)]): continue
                                        st.error(f"New Row (Prod Tasks - approx original index {index+1}): Invalid data. Skipping."); continue
                                    std_task_id_for_row = get_std_prod_task_id_from_name(db_session_main_app, task_name_val, current_user_db.id)
                                    emp_id_for_row = get_employee_id_from_name(db_session_main_app, emp_name_val, current_user_db.id)
                                    if not std_task_id_for_row or not emp_id_for_row: st.error(f"New Row (Prod Tasks - approx original index {index+1}): Invalid task/employee. Skipping."); continue
                                    db_session_main_app.add(ProductProductionTask(product_id=selected_product_object.id, standard_task_id=std_task_id_for_row, employee_id=emp_id_for_row, time_minutes=Decimal(str(time_val)), items_processed_in_task=int(items_val))); st.toast(f"Added prod task: {task_name_val}", icon="➕")
                                db_session_main_app.commit(); st.success(f"Production tasks saved!"); st.session_state[snapshot_key_ppt] = edited_df_ppt.copy(); st.rerun()
                            except Exception as e_save_ppt: db_session_main_app.rollback(); st.error(f"Error saving prod tasks: {e_save_ppt}"); st.exception(e_save_ppt)

                    with st.expander("🚚 Product Shipping Tasks", expanded=False):
                        all_std_ship_tasks_db = db_session_main_app.query(StandardShippingTask).filter(StandardShippingTask.user_id == current_user_db.id).all()
                        std_ship_task_options = [task.task_name for task in all_std_ship_tasks_db] if all_std_ship_tasks_db else ["No standard ship tasks defined"]
                        data_for_pst_editor = []
                        if selected_product_object.shipping_tasks:
                            for pst in selected_product_object.shipping_tasks:
                                if pst.standard_task_ref and pst.employee_ref: data_for_pst_editor.append({"ID": pst.id, "Task": pst.standard_task_ref.task_name, "Employee": pst.employee_ref.name, "Time (min)": pst.time_minutes, "# Items in Task": pst.items_processed_in_task})
                        df_pst_cols = ["ID", "Task", "Employee", "Time (min)", "# Items in Task"]; df_pst_for_editor = pd.DataFrame(data_for_pst_editor, columns=df_pst_cols)
                        if df_pst_for_editor.empty: df_pst_for_editor = pd.DataFrame(columns=df_pst_cols).astype({"ID":"float64", "Task":"object", "Employee":"object", "Time (min)":"float64", "# Items in Task":"int64"})
                        snapshot_key_pst = f'df_pst_snapshot_{selected_product_object.id}'
                        if snapshot_key_pst not in st.session_state or not isinstance(st.session_state.get(snapshot_key_pst), pd.DataFrame) or not st.session_state[snapshot_key_pst].columns.equals(df_pst_for_editor.columns): st.session_state[snapshot_key_pst] = df_pst_for_editor.copy()
                        
                        pst_display_columns_desktop = ("Task", "Employee", "Time (min)", "# Items in Task")
                        pst_display_columns_mobile = ("Task", "Time (min)") 
                        pst_columns_to_display = pst_display_columns_mobile if IS_MOBILE else pst_display_columns_desktop

                        edited_df_pst = st.data_editor(st.session_state[snapshot_key_pst], num_rows="dynamic", key=f"pst_editor_{selected_product_object.id}", 
                                                       column_order=pst_columns_to_display, 
                                                       column_config={"Task": st.column_config.SelectboxColumn("Task*", options=std_ship_task_options, required=True), "Employee": st.column_config.SelectboxColumn("Performed By*", options=employee_name_options_ppt, required=True), "Time (min)": st.column_config.NumberColumn("Time (min)*", required=True, min_value=0.0, step=0.1, format="%.1f"), "# Items in Task": st.column_config.NumberColumn("# Items in Task*", required=True, min_value=1, step=1, format="%d")}, 
                                                       use_container_width=True, hide_index=True)
                        if st.button(f"Save Shipping Tasks for {selected_product_object.product_name}", key=f"save_pst_{selected_product_object.id}", type="primary"):
                            try:
                                original_df_snapshot_pst = st.session_state[snapshot_key_pst]; original_snapshot_ids_pst = set(original_df_snapshot_pst['ID'].dropna().astype(int))
                                edited_df_ids_pst = set(edited_df_pst['ID'].dropna().astype(int)); ids_to_delete_from_db_pst = original_snapshot_ids_pst - edited_df_ids_pst
                                for pst_id_del in ids_to_delete_from_db_pst:
                                    pst_to_del = db_session_main_app.query(ProductShippingTask).filter(ProductShippingTask.id == pst_id_del, ProductShippingTask.product_id == selected_product_object.id).first()
                                    if pst_to_del: db_session_main_app.delete(pst_to_del); st.toast(f"Deleted ship task ID: {pst_id_del}", icon="➖")
                                for index, row in edited_df_pst.iterrows():
                                    pst_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None; task_name_val, emp_name_val, time_val, items_val = row.get("Task"), row.get("Employee"), row.get("Time (min)"), row.get("# Items in Task")
                                    if emp_name_val is None and "Employee" not in edited_df_pst.columns: st.error(f"Row {index+1} (Ship Tasks): Employee data missing."); continue
                                    if items_val is None and "# Items in Task" not in edited_df_pst.columns: st.error(f"Row {index+1} (Ship Tasks): '# Items in Task' data missing."); continue
                                    if not all([task_name_val, task_name_val != "No standard ship tasks defined", emp_name_val, emp_name_val != "No employees defined", pd.notna(time_val), pd.notna(items_val), int(items_val or 0) > 0]):
                                        if pst_id is None and not any([task_name_val, emp_name_val, pd.notna(time_val), pd.notna(items_val)]): continue
                                        st.error(f"Row {index+1} (Ship Tasks): Invalid data. Skipping."); continue
                                    std_task_id_for_row = get_std_ship_task_id_from_name(db_session_main_app, task_name_val, current_user_db.id); emp_id_for_row = get_employee_id_from_name(db_session_main_app, emp_name_val, current_user_db.id)
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
                                    if emp_name_val is None and "Employee" not in edited_df_pst.columns: st.error(f"New Row (Ship Tasks): Employee data missing."); continue
                                    if items_val is None and "# Items in Task" not in edited_df_pst.columns: st.error(f"New Row (Ship Tasks): '# Items in Task' data missing."); continue
                                    if not all([task_name_val, task_name_val != "No standard ship tasks defined", emp_name_val, emp_name_val != "No employees defined", pd.notna(time_val), pd.notna(items_val), int(items_val or 0) > 0]):
                                        if not any([task_name_val, emp_name_val, pd.notna(time_val), pd.notna(items_val)]): continue
                                        st.error(f"New Row (Ship Tasks - approx original index {index+1}): Invalid data. Skipping."); continue
                                    std_task_id_for_row = get_std_ship_task_id_from_name(db_session_main_app, task_name_val, current_user_db.id); emp_id_for_row = get_employee_id_from_name(db_session_main_app, emp_name_val, current_user_db.id)
                                    if not std_task_id_for_row or not emp_id_for_row: st.error(f"New Row (Ship Tasks - approx original index {index+1}): Invalid task/employee. Skipping."); continue
                                    db_session_main_app.add(ProductShippingTask(product_id=selected_product_object.id, standard_task_id=std_task_id_for_row, employee_id=emp_id_for_row, time_minutes=Decimal(str(time_val)), items_processed_in_task=int(items_val))); st.toast(f"Added ship task: {task_name_val}", icon="➕")
                                db_session_main_app.commit(); st.success(f"Shipping tasks saved!"); st.session_state[snapshot_key_pst] = edited_df_pst.copy(); st.rerun()
                            except Exception as e_save_pst: db_session_main_app.rollback(); st.error(f"Error saving ship tasks: {e_save_pst}"); st.exception(e_save_pst)

                    with st.expander("🪙 Other Product Specific Costs & Pricing", expanded=False):
                        st.markdown("#### Packaging Costs (per Item)")
                        if IS_MOBILE:
                            new_pkg_label_cost = st.number_input("Label Cost/Item (€)", value=float(selected_product_object.packaging_label_cost or Decimal('0.0')), min_value=0.0, format="%.3f", key=f"pkg_label_{selected_product_object.id}_mob")
                            new_pkg_material_cost = st.number_input("Other Pkg Materials Cost/Item (€)", value=float(selected_product_object.packaging_material_cost or Decimal('0.0')), min_value=0.0, format="%.3f", key=f"pkg_mat_{selected_product_object.id}_mob")
                        else:
                            col_pkg1, col_pkg2 = st.columns(2)
                            new_pkg_label_cost = col_pkg1.number_input("Label Cost/Item (€)", value=float(selected_product_object.packaging_label_cost or Decimal('0.0')), min_value=0.0, format="%.3f", key=f"pkg_label_{selected_product_object.id}")
                            new_pkg_material_cost = col_pkg2.number_input("Other Pkg Materials Cost/Item (€)", value=float(selected_product_object.packaging_material_cost or Decimal('0.0')), min_value=0.0, format="%.3f", key=f"pkg_mat_{selected_product_object.id}")
                        
                        st.markdown("#### Salary & Overhead Allocation")
                        all_employees_db_other = db_session_main_app.query(Employee).filter(Employee.user_id == current_user_db.id).all()
                        allocatable_salaried_employees = [emp for emp in all_employees_db_other if emp.global_salary_entry] 
                        salaried_employee_options = {emp.name: emp.id for emp in allocatable_salaried_employees}
                        salaried_employee_names = ["None"] + list(salaried_employee_options.keys())
                        current_salary_alloc_emp_name = "None"
                        if selected_product_object.salary_allocation_employee_id and selected_product_object.salary_alloc_employee_ref: current_salary_alloc_emp_name = selected_product_object.salary_alloc_employee_ref.name
                        idx_sal_emp = salaried_employee_names.index(current_salary_alloc_emp_name) if current_salary_alloc_emp_name in salaried_employee_names else 0
                        selected_salary_emp_name = st.selectbox("Allocate Salary of Employee", options=salaried_employee_names, index=idx_sal_emp, key=f"sal_alloc_emp_{selected_product_object.id}")
                        sal_alloc_items = selected_product_object.salary_allocation_items_per_month if selected_product_object.salary_allocation_items_per_month is not None else 1000
                        new_sal_alloc_items = st.number_input("Items/Month (salary alloc)", value=int(sal_alloc_items), min_value=1, format="%d", key=f"sal_alloc_items_{selected_product_object.id}")
                        rent_alloc_items = selected_product_object.rent_utilities_allocation_items_per_month if selected_product_object.rent_utilities_allocation_items_per_month is not None else 1000
                        new_rent_alloc_items = st.number_input("Items/Month (rent/util alloc)", value=int(rent_alloc_items), min_value=1, format="%d", key=f"rent_alloc_items_{selected_product_object.id}")
                        
                        st.markdown("#### Online Selling Fees - Retail")
                        sp = selected_product_object 
                        new_ret_ao = st.number_input("Avg Retail Order Value (€)", value=float(sp.retail_avg_order_value or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ret_ao_{sp.id}")
                        new_ret_cc = st.number_input("Retail CC Fee (%)", value=float(sp.retail_cc_fee_percent or Decimal('0.0')), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ret_cc_{sp.id}")
                        new_ret_plat = st.number_input("Retail Platform Fee (%)", value=float(sp.retail_platform_fee_percent or Decimal('0.0')), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ret_plat_{sp.id}")
                        new_ret_ship = st.number_input("Retail Avg Shipping Paid by You (€)", value=float(sp.retail_shipping_cost_paid_by_you or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ret_ship_{sp.id}")

                        st.markdown("#### Online Selling Fees - Wholesale")
                        new_ws_ao = st.number_input("Avg Wholesale Order Value (€)", value=float(sp.wholesale_avg_order_value or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ws_ao_{sp.id}")
                        new_ws_comm = st.number_input("Wholesale Commission (%)", value=float(sp.wholesale_commission_percent or Decimal('0.0')), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ws_comm_{sp.id}")
                        new_ws_proc = st.number_input("Wholesale Payment Processing Fee (%)", value=float(sp.wholesale_processing_fee_percent or Decimal('0.0')), min_value=0.0, max_value=1.0, format="%.4f", step=0.0001, key=f"ws_proc_{sp.id}")
                        new_ws_flat = st.number_input("Wholesale Flat Fee per Order (€)", value=float(sp.wholesale_flat_fee_per_order or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ws_flat_{sp.id}")

                        st.markdown("#### Pricing Strategy")
                        if IS_MOBILE:
                            new_ws_price = st.number_input("Wholesale Price/Item (€)", value=float(sp.wholesale_price_per_item or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ws_price_{sp.id}_mob")
                            new_rt_price = st.number_input("Retail Price/Item (€)", value=float(sp.retail_price_per_item or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"rt_price_{sp.id}_mob")
                            new_buffer = st.slider("Buffer Percentage", min_value=0.0, max_value=1.0, value=float(sp.buffer_percentage or Decimal('0.0')), step=0.01, format="%.2f", key=f"buffer_{sp.id}_mob")
                        else:
                            col_price1, col_price2, col_price3 = st.columns(3)
                            new_ws_price = col_price1.number_input("Wholesale Price/Item (€)", value=float(sp.wholesale_price_per_item or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"ws_price_{sp.id}")
                            new_rt_price = col_price2.number_input("Retail Price/Item (€)", value=float(sp.retail_price_per_item or Decimal('0.0')), min_value=0.0, format="%.2f", key=f"rt_price_{sp.id}")
                            new_buffer = col_price3.slider("Buffer Percentage", min_value=0.0, max_value=1.0, value=float(sp.buffer_percentage or Decimal('0.0')), step=0.01, format="%.2f", key=f"buffer_{sp.id}")
                        
                        st.markdown("#### Distribution")
                        new_dist_ws = st.slider("Wholesale Distribution (%)", min_value=0.0, max_value=1.0, value=float(sp.distribution_wholesale_percentage or Decimal('0.0')), step=0.01, format="%.2f", key=f"dist_ws_{sp.id}")
                        st.metric("Retail Distribution (%)", f"{(1.0 - new_dist_ws):.0%}")
                        if st.button(f"Save Other Costs & Pricing for {sp.product_name}", key=f"save_other_costs_{sp.id}", type="primary"):
                            try:
                                sp.packaging_label_cost = Decimal(str(new_pkg_label_cost)); sp.packaging_material_cost = Decimal(str(new_pkg_material_cost))
                                sp.salary_allocation_employee_id = salaried_employee_options.get(selected_salary_emp_name); sp.salary_allocation_items_per_month = new_sal_alloc_items
                                sp.rent_utilities_allocation_items_per_month = new_rent_alloc_items; sp.retail_avg_order_value = Decimal(str(new_ret_ao))
                                sp.retail_cc_fee_percent = Decimal(str(new_ret_cc)); sp.retail_platform_fee_percent = Decimal(str(new_ret_plat))
                                sp.retail_shipping_cost_paid_by_you = Decimal(str(new_ret_ship)); sp.wholesale_avg_order_value = Decimal(str(new_ws_ao))
                                sp.wholesale_commission_percent = Decimal(str(new_ws_comm)); sp.wholesale_processing_fee_percent = Decimal(str(new_ws_proc))
                                sp.wholesale_flat_fee_per_order = Decimal(str(new_ws_flat)); sp.wholesale_price_per_item = Decimal(str(new_ws_price))
                                sp.retail_price_per_item = Decimal(str(new_rt_price)); sp.buffer_percentage = Decimal(str(new_buffer))
                                sp.distribution_wholesale_percentage = Decimal(str(new_dist_ws))
                                db_session_main_app.add(sp); db_session_main_app.commit(); st.success("Other costs and pricing saved!"); st.rerun()
                            except Exception as e_save_other: db_session_main_app.rollback(); st.error(f"Error saving other costs: {e_save_other}"); st.exception(e_save_other)

        elif choice == "Product Cost Breakdown":
            st.header("📊 Product Cost Breakdown")
            products_for_calc = db_session_main_app.query(Product).filter(Product.user_id == current_user_db.id).order_by(Product.product_name).all()
            if not products_for_calc:
                st.info("No products found. Please add products in 'Manage Products' to see a cost breakdown.")
            else:
                product_names_for_calc = {p.product_name: p.id for p in products_for_calc}
                if 'calc_selected_product_name' not in st.session_state or st.session_state.calc_selected_product_name not in product_names_for_calc:
                    st.session_state.calc_selected_product_name = list(product_names_for_calc.keys())[0]
                selected_product_name_calc = st.selectbox("Select Product for Breakdown:", options=list(product_names_for_calc.keys()), key="calc_prod_select_sb", index=list(product_names_for_calc.keys()).index(st.session_state.calc_selected_product_name))
                if selected_product_name_calc != st.session_state.calc_selected_product_name:
                    st.session_state.calc_selected_product_name = selected_product_name_calc
                if selected_product_name_calc:
                    selected_product_id_calc = product_names_for_calc[selected_product_name_calc]
                    breakdown_data = calculate_cost_breakdown(selected_product_id_calc, db_session_main_app, current_user_db.id)
                    if breakdown_data:
                        st.subheader(f"Cost Analysis for: **{selected_product_name_calc}**")
                        if IS_MOBILE:
                            st.metric("Total Production Cost/Item", format_currency(breakdown_data['total_production_cost_per_item']))
                            st.metric("Target Price (with Buffer)", format_currency(breakdown_data['cost_plus_buffer']))
                            st.metric("Blended Avg Profit/Item", format_currency(breakdown_data['blended_avg_profit']))
                        else:
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
                                df_mat_display["Cost"] = df_mat_display["Cost"].apply(format_currency)
                                st.dataframe(df_mat_display, hide_index=True, use_container_width=True) # CHANGED
                            st.markdown(f"**Total Production Labor Cost/Item:** {format_currency(breakdown_data['total_production_labor_cost_per_item'])}")
                            if breakdown_data['prod_labor_details']:
                                df_prod_labor = pd.DataFrame(breakdown_data['prod_labor_details']); df_prod_labor_display = df_prod_labor.copy()
                                df_prod_labor_display["Time (min)"] = df_prod_labor_display["Time (min)"].apply(lambda x: format_decimal_for_table(x, '0.1'))
                                df_prod_labor_display["Items in Task"] = df_prod_labor_display["Items in Task"].apply(lambda x: format_decimal_for_table(x, '0'))
                                df_prod_labor_display["Cost"] = df_prod_labor_display["Cost"].apply(format_currency)
                                st.dataframe(df_prod_labor_display, hide_index=True, use_container_width=True) # CHANGED
                            st.markdown(f"**Total Shipping Labor Cost/Item (Direct):** {format_currency(breakdown_data['total_shipping_labor_cost_per_item'])}")
                            if breakdown_data['ship_labor_details']:
                                df_ship_labor = pd.DataFrame(breakdown_data['ship_labor_details']); df_ship_labor_display = df_ship_labor.copy()
                                df_ship_labor_display["Time (min)"] = df_ship_labor_display["Time (min)"].apply(lambda x: format_decimal_for_table(x, '0.1'))
                                df_ship_labor_display["Items in Task"] = df_ship_labor_display["Items in Task"].apply(lambda x: format_decimal_for_table(x, '0'))
                                df_ship_labor_display["Cost"] = df_ship_labor_display["Cost"].apply(format_currency)
                                st.dataframe(df_ship_labor_display, hide_index=True, use_container_width=True) # CHANGED
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
                        if IS_MOBILE:
                            st.markdown("#### 🛍️ Retail Channel")
                            rt = breakdown_data['retail_metrics']
                            st.metric("Retail Price", format_currency(rt['price']))
                            st.write(f"CC Fee: {format_currency(rt['cc_fee'])} | Platform Fee: {format_currency(rt['platform_fee'])}")
                            st.write(f"Shipping Paid by You (per item): {format_currency(rt['shipping_cost'])}")
                            st.write(f"**Total Retail Channel Costs:** {format_currency(rt['total_channel_costs'])}")
                            st.metric("Total Cost (Prod + Retail Fees)", format_currency(rt['total_cost_item']))
                            st.metric("Profit per Retail Item", format_currency(rt['profit']), delta_color="normal")
                            st.metric("Retail Margin", format_percentage(rt['margin_percent']))
                            st.markdown("---")
                            st.markdown("#### 🏭 Wholesale Channel")
                            ws = breakdown_data['wholesale_metrics']
                            st.metric("Wholesale Price", format_currency(ws['price']))
                            st.write(f"Commission: {format_currency(ws['commission'])} | Processing Fee: {format_currency(ws['processing_fee'])}")
                            st.write(f"Flat Fee (Item Share): {format_currency(ws['flat_fee_item_share'])}")
                            st.write(f"**Total Wholesale Channel Costs:** {format_currency(ws['total_channel_costs'])}")
                            st.metric("Total Cost (Prod + Wholesale Fees)", format_currency(ws['total_cost_item']))
                            st.metric("Profit per Wholesale Item", format_currency(ws['profit']), delta_color="normal")
                            st.metric("Wholesale Margin", format_percentage(ws['margin_percent']))
                        else:
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
                    else: st.error("Could not calculate breakdown. Ensure product data is complete.")

        elif choice == "User Guide":
            st.markdown("## 📖 User Guide: Product Cost Calculator")
            st.markdown("Welcome to the **Product Cost Calculator**! This guide will walk you through each section...")
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
                    
                    **How to Use:** Similar to "Manage Ingredients" -- use the data editor to add, edit, or delete employee records. Always click **"Save Employee Changes"**.
                    
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
                    **Key Fields:** - `Task Name*`: A clear, descriptive name for the production task. *Required.*
                """)
                st.markdown("---")
                st.markdown("### Manage Standard Shipping Tasks")
                st.markdown("""
                    *Purpose: Define a reusable list of common tasks involved in preparing and shipping your products (e.g., "Order Picking", "Box Assembly", "Label Printing", "Post Office Run").*
                    **How to Use:** Add, edit, or delete task names. Click **"Save Shipping Task Changes"**.
                    **Key Fields:** - `Task Name*`: A clear, descriptive name for the shipping task. *Required.*
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
                    - *Purpose:* For employees who receive a fixed monthly salary.
                    - **How to Use:** Select an employee, enter their `Monthly Salary (€)*`. Add, edit, or delete. *Note:* An employee can only have one global salary entry.
                    - Click **"Save Global Salaries"** to persist changes.
                """)
            st.markdown("---")
            with st.expander("📦 Manage Products (The Core Engine!)", expanded=False):
                st.markdown("### Adding/Editing Basic Product Attributes (Top Table)")
                st.markdown("""
                    - Add, edit, or delete products.
                    - **Key Fields:** `Product Name*`, `Batch Size (items)*`, `Monthly Prod (items)*`.
                    - Click **"Save Product Attribute Changes"**.
                """)
                st.markdown("---")
                st.markdown("### Managing Detailed Product Components (Lower Section)")
                st.markdown("Select a product from the dropdown. Expanders below apply to it.")
                st.markdown("---")
                st.markdown("#### 🧪 Product Materials (for the selected product)")
                st.markdown("""
                    *Purpose: Define ingredients for **one unit** of the product.*
                    **How to Use:** Select `Ingredient (Provider)*`, enter `Quantity (grams)*`. Click **"Save Materials for [Product Name]"**.
                """)
                st.markdown("---")
                st.markdown("#### 🛠️ Product Production Tasks (for the selected product)")
                st.markdown("""
                    *Purpose: Assign tasks and employees for direct production labor costs.*
                    **How to Use:** Select `Task*`, `Performed By*`, enter `Time (min)*` and `# Items in Task*` (items processed in that time). Click **"Save Production Tasks for [Product Name]"**.
                """)
                st.markdown("---")
                st.markdown("#### 🚚 Product Shipping Tasks (for the selected product)")
                st.markdown("""
                    *Purpose: Direct labor for shipping.*
                    **How to Use:** Similar to Production Tasks. Click **"Save Shipping Tasks for [Product Name]"**.
                """)
                st.markdown("---")
                st.markdown("#### 🪙 Other Product Specific Costs & Pricing (for the selected product)")
                st.markdown("""
                    **Packaging Costs (per Item):** `Label Cost/Item (€)`, `Other Pkg Materials Cost/Item (€)`.
                    **Salary & Overhead Allocation:** Allocate a global salary or rent/utilities to this product based on `Items of THIS Product per Month`.
                    **Online Selling Fees - Retail/Wholesale:** Enter average order values, percentage fees, and flat fees.
                    **Pricing Strategy:** Set `Wholesale Price/Item (€)`, `Retail Price/Item (€)`, and a `Buffer Percentage`.
                    **Distribution Mix:** Set `Wholesale Distribution (%)`.
                    Click **"Save Other Costs & Pricing for [Product Name]"**.
                """)
            st.markdown("---")
            with st.expander("📈 Product Cost Breakdown Analysis", expanded=False):
                st.markdown("### Interpreting the Breakdown Section")
                st.markdown("""
                    Select a product to see its full cost analysis.
                    **Key Metrics:** `Total Production Cost/Item`, `Target Price (with Buffer)`, `Blended Avg Profit/Item`.
                    **Details:** Direct COGS (Materials, Labor, Packaging), Allocated Overheads.
                    **Channel Performance:** Compares Retail vs. Wholesale profitability (fees, total costs, profit, margin).
                    **Blended Performance:** Overall metrics weighted by your distribution mix.
                """)
            st.markdown("---")
            with st.expander("⚙️ User Settings & Profile", expanded=False):
                st.markdown("### Updating Your Profile & Password")
                st.markdown("""
                    - **Profile Information:** Update your display `Name` and `Email`. Click **"Save User Details"**.
                    - **Update Password:** Enter current and new passwords. Click **"Reset password"**.
                """)
            st.markdown("---")
            st.success("🎉 You've reached the end of the User Guide!")

        elif choice == "User Settings":
            st.header("⚙️ User Settings")
            st.write("Manage your user profile and application settings.")
            st.subheader("Profile Information")
            user_credentials = config_auth['credentials']['usernames'].get(username, {})
            current_name = user_credentials.get('name', ''); current_email = user_credentials.get('email', '')
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
                        st.session_state['name'] = new_name.strip()
                        with open(CONFIG_FILE_PATH, 'w') as file: yaml.dump(config_auth, file, default_flow_style=False, allow_unicode=True)
                        st.success("User details updated successfully!"); st.rerun() 
                    except Exception as e_update_manual: st.error(f"Error updating details: {e_update_manual}")
            st.markdown("---"); st.subheader("Update Password")
            try:
                if authenticator.reset_password(username=username, location='main'): 
                    st.success('Password reset successfully! Saving to config file.')
                    with open(CONFIG_FILE_PATH, 'w') as file: yaml.dump(config_auth, file, default_flow_style=False, allow_unicode=True)
            except Exception as e_pw: st.error(f"Error during password reset widget: {e_pw}") 

        if db_session_main_app and db_session_main_app.is_active:
            db_session_main_app.close()
    except Exception as e_main_app:
        st.error(f"An unexpected error occurred in the application: {e_main_app}")
        st.exception(e_main_app)
        if db_session_main_app and db_session_main_app.is_active:
            db_session_main_app.close()

elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning("Please enter your username and password to login, or register if you are a new user.")
    actual_form_name = "Register user"
    observed_reg_form_submit_key = f"FormSubmitter:{actual_form_name}-Register"
    pre_authorized_emails_list = config_auth.get('preauthorized', {}).get('emails', [])
    try:
        register_user_response = authenticator.register_user(pre_authorized=pre_authorized_emails_list) 
        is_successful_authenticator_registration = False
        if isinstance(register_user_response, tuple) and len(register_user_response) == 3:
            reg_email, reg_username_val, reg_name = register_user_response
            if isinstance(reg_email, str) and isinstance(reg_username_val, str) and isinstance(reg_name, str):
                if reg_username_val in config_auth.get('credentials', {}).get('usernames', {}):
                    is_successful_authenticator_registration = True
        if is_successful_authenticator_registration: 
            st.success('User registered successfully with authenticator!')
            with open(CONFIG_FILE_PATH, 'w') as file: yaml.dump(config_auth, file, default_flow_style=False, allow_unicode=True)
            actual_email_reg, actual_username_reg, actual_name_reg = register_user_response[0], register_user_response[1], register_user_response[2]
            hashed_password_for_db = None
            try: hashed_password_for_db = config_auth['credentials']['usernames'][actual_username_reg]['password']
            except KeyError: st.error(f"CRITICAL: Hashed password for '{actual_username_reg}' not found in config after registration.")
            db_operation_encountered_error_reg = False
            db_session_for_registration = None 
            try:
                if not (actual_username_reg and actual_email_reg and hashed_password_for_db):
                    st.error("Essential data missing for database registration."); db_operation_encountered_error_reg = True
                else:
                    db_session_for_registration = next(get_db())
                    existing_pg_user = db_session_for_registration.query(User).filter((User.username == actual_username_reg) | (User.email == actual_email_reg)).first()
                    if existing_pg_user: st.warning(f"User '{actual_username_reg}' or email '{actual_email_reg}' already exists in the application database.")
                    else:
                        db_user = User(username=actual_username_reg, email=actual_email_reg, name=actual_name_reg, hashed_password=hashed_password_for_db)
                        db_session_for_registration.add(db_user); db_session_for_registration.commit()
                        st.info(f"User '{actual_username_reg}' also registered in the application database.")
            except Exception as e_pg_reg: 
                if db_session_for_registration: db_session_for_registration.rollback()
                st.error(f"Database error during user registration: {e_pg_reg}"); st.exception(e_pg_reg); db_operation_encountered_error_reg = True
            finally:
                if db_session_for_registration: db_session_for_registration.close()
            if not db_operation_encountered_error_reg:
                if observed_reg_form_submit_key in st.session_state: del st.session_state[observed_reg_form_submit_key]
                st.info("Please login with your new credentials."); st.rerun()
    except stauth.RegisterError as e_reg_known: st.error(f"Registration Error: {e_reg_known}")
    except Exception as e_register_outer: st.error(f"An unexpected error occurred during the registration process: {e_register_outer}"); st.exception(e_register_outer)

st.markdown("---")
st.markdown(f"<div style='text-align: center; color: grey;'>Product Cost Calculator © {datetime.date.today().year}</div>", unsafe_allow_html=True)
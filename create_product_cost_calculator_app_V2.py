import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime
import re

# --- Configuration for File Paths ---
BASE_DIR = "data_files_product_cost_app" # Changed to a relative path for Streamlit Cloud
# For Streamlit Cloud, it's better to use relative paths or paths Streamlit provides.
# Let's assume the script is in the root of the repo, and data files are in a 'data_files_product_cost_app' subdirectory.

GLOBAL_DATA_FILENAME = "global_data.json"
SAVED_PRODUCTS_FILENAME = "saved_products.json"

# Construct paths relative to the script file if needed, or use a known directory for Streamlit Cloud.
# For simplicity, let's assume BASE_DIR will be created in the current working directory of the app on Streamlit Cloud.
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR, exist_ok=True)

GLOBAL_DATA_FILE_PATH = os.path.join(BASE_DIR, GLOBAL_DATA_FILENAME)
SAVED_PRODUCTS_FILE_PATH = os.path.join(BASE_DIR, SAVED_PRODUCTS_FILENAME)

# --- Page Configuration ---
st.set_page_config(
    page_title="Product Cost Calculator",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Helper Functions for Data Handling --- (Keep as is)
def load_json_data(file_path, default_data=None):
    if default_data is None: default_data = {}
    try:
        with open(file_path, "r") as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        if default_data: save_json_data(file_path, default_data)
        return default_data

def save_json_data(file_path, data):
    with open(file_path, "w") as f: json.dump(data, f, indent=4)

def create_ingredient_display_string(name, provider):
    return f"{name} (Provider: {provider})"

def parse_ingredient_display_string(display_string):
    if display_string is None: return None, None
    match = re.match(r"^(.*?) \(Provider: (.*?)\)$", display_string)
    if match: return match.group(1), match.group(2)
    return display_string, None

# --- Load Global and Product Data ---
DEFAULT_GLOBAL_DATA = {
    "ingredients": [
        {"name": "Distilled Water", "provider": "AquaPure Inc.", "price_per_unit": 1.39, "unit_quantity_kg": 8.3, "price_url": "https://example.com/water"},
        {"name": "Distilled Water", "provider": "Local Supply", "price_per_unit": 1.20, "unit_quantity_kg": 10.0, "price_url": ""},
        {"name": "Sodium Hydroxide (Lye)", "provider": "ChemCo", "price_per_unit": 45.0, "unit_quantity_kg": 5.0, "price_url": "https://example.com/lye"},
        # ... other ingredients with "price_url": "" or actual URLs
    ],
    "employees": [ # Keep as is
        {"name": "Owner", "hourly_rate": 20.0, "role": "Production Manager"},
        {"name": "Employee 1", "hourly_rate": 18.0, "role": "Production Assistant"},
    ],
    "standard_production_tasks": [ {"task_name": "Unmold & Clean"}, {"task_name": "Cut Loaves"} ], # Keep as is
    "standard_shipping_tasks": [ {"task_name": "Remove from Shelf"}, {"task_name": "Label"} ], # Keep as is
    "global_costs": {"monthly_rent": 1500.0, "monthly_utilities": 250.0}, # Keep as is
    "global_salaries": [ {"employee_name": "Owner", "monthly_amount": 5000.0} ] # Keep as is
}
global_data = load_json_data(GLOBAL_DATA_FILE_PATH, DEFAULT_GLOBAL_DATA)
# Migration and default key checks (Keep as is from v2.7, ensure price_url is handled if migrating old data)
for key, value in DEFAULT_GLOBAL_DATA.items():
    if key not in global_data: global_data[key] = value
    if key == "ingredients": # Ensure new price_url key exists
        for item in global_data[key]:
            if "price_url" not in item:
                item["price_url"] = ""
    # ... (rest of migration logic from v2.7 for salaries) ...
    if key == "global_salaries" and global_data.get(key) and isinstance(global_data[key], list) and len(global_data[key]) > 0 and "salary_name" in global_data[key][0]:
        # (Salary migration logic from v2.7)
        new_salaries = []
        for old_salary_entry in global_data[key]:
            emp_name_to_use = old_salary_entry.get("salary_name")
            if "employees" in global_data:
                for emp in global_data["employees"]:
                    if emp.get("name") == old_salary_entry.get("salary_name"): emp_name_to_use = emp.get("name"); break
            new_salaries.append({"employee_name": emp_name_to_use, "monthly_amount": old_salary_entry.get("monthly_amount", 0.0)})
        global_data[key] = new_salaries; # save_json_data(GLOBAL_DATA_FILE_PATH, global_data) # Be careful with auto-saving during load

# Only save if a migration actually happened and made changes
# This part needs careful thought to avoid saving on every script run if no migration was needed.
# For now, let's assume manual review or that the initial default includes price_url.
# A more robust migration would track if changes were made.

saved_products = load_json_data(SAVED_PRODUCTS_FILE_PATH, {})

st.title("📦 Product Cost Calculator")

with st.sidebar:
    st.header("Navigation")
    app_mode = st.radio("Choose a section:", ["Manage Products", "Manage Global Data", "Tutorial"])

    if app_mode == "Manage Products":
        st.subheader("Products")
        product_names = list(saved_products.keys())
        # The key for the checkbox is 'new_product_cb'
        new_product_checkbox = st.checkbox("Create New Product", key="new_product_cb")

        if new_product_checkbox:
            # The key for the text_input is 'new_product_name_input_widget'
            st.session_state.current_product_name_input = st.text_input(
                "New Product Name",
                st.session_state.get("current_product_name_input_widget", "My New Product"), # Use the widget's key for .get()
                key="new_product_name_input_widget"
            )
            st.session_state.load_saved_product = False
            if st.button("Initialize New Product", key="init_new_prod_btn"):
                product_to_init = st.session_state.current_product_name_input_widget # Get value from widget's state key
                if not product_to_init.strip(): st.warning("Product name cannot be empty.")
                elif product_to_init in saved_products: st.warning("Product name already exists.")
                else:
                    # ... (product data initialization as before) ...
                    saved_products[product_to_init] = {
                        "product_name": product_to_init, "batch_size_items": 100, "materials_used": [],
                        "production_tasks_performed": [], "shipping_tasks_performed": [],
                        "salary_allocation": {"employee_name_for_salary": "None", "items_per_month_for_salary": 1000},
                        "rent_utilities_allocation": {"items_per_month_for_rent": 1000},
                        "packaging": {"label_cost_per_item": 0.05, "materials_cost_per_item": 0.10},
                        "retail_fees": {"average_order_value": 30.00, "cc_fee_percent": 0.03, "platform_fee_percent": 0.05, "shipping_cost_paid_by_you": 5.0},
                        "wholesale_fees": {"average_order_value": 200.00, "commission_percent": 0.15, "processing_fee_percent": 0.02, "flat_fee_per_order": 0.25},
                        "pricing": {"wholesale_price_per_item": 5.00, "retail_price_per_item": 10.00, "buffer_percentage": 0.10},
                        "distribution": {"wholesale_percentage": 0.5, "retail_percentage": 0.5},
                        "monthly_production_items": 1000, "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_json_data(SAVED_PRODUCTS_FILE_PATH, saved_products)
                    st.success(f"Product '{product_to_init}' initialized.")
                    st.session_state.current_product_name = product_to_init
                    st.session_state.load_saved_product = True

                    # Explicitly reset the "Create New Product" UI state
                    if 'new_product_cb' in st.session_state:
                        st.session_state.new_product_cb = False
                    if 'new_product_name_input_widget' in st.session_state:
                        st.session_state.new_product_name_input_widget = "" # Clear the input field

                    st.rerun() # Use st.rerun()
        else: # new_product_checkbox is false
            if product_names:
                current_selection = st.session_state.get('current_product_name')
                if current_selection not in product_names: current_selection = product_names[0] if product_names else None
                
                # Ensure index is valid if current_selection is None (e.g. first run, no product selected yet)
                idx = 0
                if current_selection and current_selection in product_names:
                    idx = product_names.index(current_selection)
                
                selected_product_name_sidebar = st.selectbox("Select Product", product_names,
                    index=idx,
                    key="select_product_sidebar")
                if selected_product_name_sidebar:
                    st.session_state.current_product_name = selected_product_name_sidebar
                    st.session_state.load_saved_product = True # This might trigger a load if not already loaded
            else:
                st.info("No saved products. Tick 'Create New Product' to start.")
                st.session_state.load_saved_product = False
                if 'current_product_name' in st.session_state: del st.session_state.current_product_name

# --- Tutorial Tab --- (Keep as is from v2.7, but add mention of Price URL)
if app_mode == "Tutorial":
    st.header("📖 Application Tutorial")
    # ... (all existing tutorial content) ...
    st.subheader("Ingredients Tab") # Find this section and add to it
    st.markdown("""
    List all raw materials or ingredients you purchase.
    -   **Ingredient Name:** The common name of the ingredient (e.g., "Olive Oil").
    -   **Provider:** The supplier of this ingredient (e.g., "Olio Verde"). This is important if the same ingredient from different providers has different costs.
    -   **Price (€) for Unit:** The price you pay for the bulk quantity of this ingredient (e.g., if a 5kg container of Olive Oil costs €25.00, enter `25.00`).
    -   **Unit Quantity (kg):** The quantity (in kilograms) that the "Price (€) for Unit" corresponds to (e.g., for the 5kg container, enter `5.0`).
    -   **Price URL:** (Optional) A web link to the ingredient's purchasing page or price reference. This will be displayed as a clickable link.
        *Example: If you buy Lye in 2kg bags for €15, you'd enter: Name: Sodium Hydroxide (Lye), Provider: ChemCo, Price: 15.00, Unit Qty: 2.0, Price URL: https://example.com/chemco/lye.*
    """)
    # ... (rest of tutorial content) ...

# --- Global Data Management UI ---
elif app_mode == "Manage Global Data":
    st.header("🌍 Manage Global Data")
    st.info("Define shared resources like ingredients, employees, and global costs here.")
    tab_ingr, tab_emp, tab_tsk, tab_gcost, tab_gsal = st.tabs(["Ingredients", "Employees", "Tasks", "Overheads", "Salaries"])

    ingr_rename_map = {
        "name": "Ingredient Name", "provider": "Provider",
        "price_per_unit": "Price (€) for Unit", "unit_quantity_kg": "Unit Quantity (kg)",
        "price_url": "Price URL" # Added
    }
    ingr_inv_rename_map = {v: k for k, v in ingr_rename_map.items()}
    # ... (other rename maps as in v2.7) ...
    emp_rename_map = {"name": "Employee Name", "hourly_rate": "Hourly Rate (€)", "role": "Role"}
    emp_inv_rename_map = {v: k for k, v in emp_rename_map.items()}
    task_rename_map = {"task_name": "Task Name"}
    task_inv_rename_map = {v: k for k, v in task_rename_map.items()}
    gsal_rename_map = {"employee_name": "Employee Name", "monthly_amount": "Monthly Salary Amount (€)"}
    gsal_inv_rename_map = {v: k for k, v in gsal_rename_map.items()}


    with tab_ingr:
        st.subheader("Global Ingredient List")
        # Ensure 'price_url' column exists in DataFrame if data is empty or old
        current_ingredients_data = global_data.get("ingredients", [])
        for item in current_ingredients_data: # Ensure all items have the new key
            if "price_url" not in item:
                item["price_url"] = ""
        
        df_ingr_orig = pd.DataFrame(current_ingredients_data)
        if df_ingr_orig.empty: # Handle case where no ingredients exist yet
             df_ingr_orig = pd.DataFrame(columns=ingr_inv_rename_map.values())


        df_ingr_renamed = df_ingr_orig.rename(columns=ingr_rename_map)

        edited_ingr_df = st.data_editor(df_ingr_renamed,
            column_config={
                ingr_rename_map["name"]: st.column_config.TextColumn(required=True),
                ingr_rename_map["provider"]: st.column_config.TextColumn(required=True),
                ingr_rename_map["price_per_unit"]: st.column_config.NumberColumn(format="%.2f",required=True,min_value=0.01, help="Price for the 'Unit Quantity'"),
                ingr_rename_map["unit_quantity_kg"]: st.column_config.NumberColumn(help="E.g., if price is for a 5kg bag, enter 5.",format="%.3f",required=True,min_value=0.001),
                ingr_rename_map["price_url"]: st.column_config.LinkColumn(help="Link to ingredient purchasing page. Will display as clickable URL.", validate="^https?://[^\s/$.?#].[^\s]*$") # Added LinkColumn
            },
            num_rows="dynamic", key="global_ingredients_editor_v3") # Incremented key
        if st.button("Save Global Ingredients",key="save_glob_ingr_v3"): # Incremented key
            global_data["ingredients"]=edited_ingr_df.rename(columns=ingr_inv_rename_map).to_dict("records")
            save_json_data(GLOBAL_DATA_FILE_PATH,global_data); st.success("Global ingredients saved!"); st.rerun() # Changed to st.rerun

    # ... (rest of Global Data tabs: Employees, Tasks, Overheads, Salaries - keep as in v2.7, ensuring st.rerun() is used if st.experimental_rerun() was there)

    with tab_emp: # Example of ensuring st.rerun
        st.subheader("Global Employee List")
        df_emp = pd.DataFrame(global_data.get("employees", [])).rename(columns=emp_rename_map)
        edited_emp_df = st.data_editor(df_emp,
            column_config={
                emp_rename_map["name"]: st.column_config.TextColumn(required=True),
                emp_rename_map["hourly_rate"]: st.column_config.NumberColumn(format="%.2f",required=True,min_value=0.0, help="Rate in €"),
                emp_rename_map["role"]: st.column_config.TextColumn()},
            num_rows="dynamic", key="global_employees_editor_v2")
        if st.button("Save Global Employees",key="save_glob_emp_v2"):
            global_data["employees"]=edited_emp_df.rename(columns=emp_inv_rename_map).to_dict("records")
            save_json_data(GLOBAL_DATA_FILE_PATH,global_data); st.success("Global employees saved!"); st.rerun() # Changed here

    with tab_tsk: # Example of ensuring st.rerun
        st.subheader("Standard Production Tasks")
        df_prod_tsk = pd.DataFrame(global_data.get("standard_production_tasks", [])).rename(columns=task_rename_map)
        edited_prod_tsk_df = st.data_editor(df_prod_tsk,
            column_config={task_rename_map["task_name"]:st.column_config.TextColumn(required=True)},num_rows="dynamic",key="g_prod_tsk_ed_v2")
        if st.button("Save Prod Tasks",key="s_g_ptsk_v2"):
            global_data["standard_production_tasks"]=edited_prod_tsk_df.rename(columns=task_inv_rename_map).to_dict("records")
            save_json_data(GLOBAL_DATA_FILE_PATH,global_data); st.success("Prod tasks saved!"); st.rerun() # Changed here
        st.subheader("Standard Shipping Tasks")
        df_ship_tsk = pd.DataFrame(global_data.get("standard_shipping_tasks", [])).rename(columns=task_rename_map)
        edited_ship_tsk_df = st.data_editor(df_ship_tsk,
            column_config={task_rename_map["task_name"]:st.column_config.TextColumn(required=True)},num_rows="dynamic",key="g_ship_tsk_ed_v2")
        if st.button("Save Ship Tasks",key="s_g_stsk_v2"):
            global_data["standard_shipping_tasks"]=edited_ship_tsk_df.rename(columns=task_inv_rename_map).to_dict("records")
            save_json_data(GLOBAL_DATA_FILE_PATH,global_data); st.success("Ship tasks saved!"); st.rerun() # Changed here
    
    with tab_gcost: # No rerun needed here as it doesn't affect dropdowns elsewhere typically
        st.subheader("Global Monthly Overheads")
        cg_costs = global_data.get("global_costs",DEFAULT_GLOBAL_DATA["global_costs"])
        if not isinstance(cg_costs, dict): cg_costs = DEFAULT_GLOBAL_DATA["global_costs"]
        n_rent = st.number_input("Global Monthly Rent (€)",value=float(cg_costs.get("monthly_rent",0.0)),min_value=0.0,format="%.2f")
        n_util = st.number_input("Global Monthly Utilities (€)",value=float(cg_costs.get("monthly_utilities",0.0)),min_value=0.0,format="%.2f")
        if st.button("Save Global Overheads",key="s_g_oh_v2"): global_data["global_costs"]={"monthly_rent":n_rent,"monthly_utilities":n_util}; save_json_data(GLOBAL_DATA_FILE_PATH,global_data); st.success("Global overheads saved!")

    with tab_gsal: # Example of ensuring st.rerun
        st.subheader("Global Salaries (Linked to Employees)")
        employee_names_for_salary_dropdown = [emp.get("name") for emp in global_data.get("employees", []) if emp.get("name")]
        if not employee_names_for_salary_dropdown: employee_names_for_salary_dropdown = ["No Employees Defined"]
        df_gsal_orig = pd.DataFrame(global_data.get("global_salaries", []))
        if df_gsal_orig.empty: df_gsal_orig = pd.DataFrame(columns=['employee_name', 'monthly_amount'])
        df_gsal_renamed = df_gsal_orig.rename(columns=gsal_rename_map)
        edited_gsal_df = st.data_editor(df_gsal_renamed,
            column_config={
                gsal_rename_map["employee_name"]:st.column_config.SelectboxColumn(options=employee_names_for_salary_dropdown, required=True),
                gsal_rename_map["monthly_amount"]:st.column_config.NumberColumn(format="%.2f",required=True,min_value=0.0, help="Salary in €")},
            num_rows="dynamic",key="g_sal_ed_v2")
        if st.button("Save Global Salaries",key="s_g_sal_v2"):
            valid_salaries_df = edited_gsal_df.rename(columns=gsal_inv_rename_map)
            valid_salaries = []
            for sal_entry in valid_salaries_df.to_dict("records"):
                if sal_entry.get("employee_name") in employee_names_for_salary_dropdown and sal_entry.get("employee_name") != "No Employees Defined":
                    valid_salaries.append(sal_entry)
            global_data["global_salaries"]=valid_salaries
            save_json_data(GLOBAL_DATA_FILE_PATH,global_data); st.success("Global salaries saved!"); st.rerun() # Changed here


# --- Product Management UI ---
elif app_mode == "Manage Products" and 'current_product_name' in st.session_state and st.session_state.current_product_name:
    # ... (Product management code from v2.7, ensure all st.experimental_rerun are st.rerun) ...
    # (No changes needed here if already using st.rerun from previous versions and column renaming is handled)
    product_name = st.session_state.current_product_name
    if product_name not in saved_products: st.error(f"Product '{product_name}' not found."); st.stop()
    product_data = saved_products[product_name]
    st.header(f"📝 Managing Product: {product_name}")
    prod_tab1,prod_tab2,prod_tab3,prod_tab4=st.tabs(["Materials","Labor","Other Costs","Summary & Pricing"])
    mats_cost_pi,prod_lab_cost_pi,ship_lab_cost_pi=0.0,0.0,0.0
    sal_cost_pi,rent_util_cost_pi,pkg_cost_pi=0.0,0.0,0.0
    ret_fee_perc_calc,ws_fee_perc_calc=0.0,0.0

    mat_used_rename_map = {"ingredient_display_name": "Ingredient (Provider)", "quantity_grams_used": "Grams Used in Batch"}
    mat_used_inv_rename_map = {v: k for k, v in mat_used_rename_map.items()}
    task_perf_rename_map = {"task_name": "Task", "employee_name": "Performed By", "time_minutes": "Time (min)", "items_processed_in_task": "# Items in Task"}
    task_perf_inv_rename_map = {v: k for k, v in task_perf_rename_map.items()}

    with prod_tab1: # MATERIALS Product Tab
        st.subheader("🧪 Materials Used")
        product_data["batch_size_items"]=st.number_input("Batch Yield (Number of Items)",value=int(product_data.get("batch_size_items",1)),min_value=1,key=f"{product_name}_bsi")
        g_ingr_list = global_data.get("ingredients", [])
        ingr_display_opts = [create_ingredient_display_string(ing.get("name"), ing.get("provider")) for ing in g_ingr_list if ing.get("name") and ing.get("provider")]
        if not ingr_display_opts: ingr_display_opts = ["No ingredients (with provider) defined globally"]
        
        current_mats_list = product_data.get('materials_used',[])
        df_mats_orig = pd.DataFrame(current_mats_list)
        if df_mats_orig.empty and ingr_display_opts[0] != "No ingredients (with provider) defined globally":
             df_mats_orig = pd.DataFrame([{"ingredient_display_name": ingr_display_opts[0], "quantity_grams_used":0.0}])
        elif df_mats_orig.empty: # Ensure columns for empty df for rename
             df_mats_orig = pd.DataFrame(columns=mat_used_inv_rename_map.values()) # Use original keys
        df_mats_renamed = df_mats_orig.rename(columns=mat_used_rename_map)

        edited_mats_df = st.data_editor(df_mats_renamed,
            column_config={
                mat_used_rename_map["ingredient_display_name"]:st.column_config.SelectboxColumn(options=ingr_display_opts,required=True),
                mat_used_rename_map["quantity_grams_used"]:st.column_config.NumberColumn(format="%.2f",required=True,min_value=0.0, help="Total grams for the entire batch")},
            num_rows="dynamic",key=f"{product_name}_mats_ed_v2")
        
        product_data['materials_used'] = edited_mats_df.rename(columns=mat_used_inv_rename_map).to_dict("records")
        product_data['materials_used'] = [r for r in product_data['materials_used'] if r.get("ingredient_display_name") and r.get("ingredient_display_name") != "No ingredients (with provider) defined globally" and float(r.get("quantity_grams_used", 0.0)) > 0]
        total_mats_cost_for_prod=0.0
        if product_data['materials_used'] and g_ingr_list:
            temp_cost_list = []
            for mat_used_row in product_data['materials_used']:
                display_name_stored = mat_used_row.get("ingredient_display_name")
                ingr_name_parsed, ingr_provider_parsed = parse_ingredient_display_string(display_name_stored)
                grams_used = float(mat_used_row.get("quantity_grams_used", 0))
                found_ingredient = next((gi for gi in g_ingr_list if gi.get("name") == ingr_name_parsed and gi.get("provider") == ingr_provider_parsed), None)
                if found_ingredient:
                    price_per_unit = float(found_ingredient.get("price_per_unit", 0)); unit_qty_kg = float(found_ingredient.get("unit_quantity_kg", 0))
                    if unit_qty_kg > 0: temp_cost_list.append(grams_used * (price_per_unit / (unit_qty_kg * 1000)))
            total_mats_cost_for_prod = sum(temp_cost_list)
        cur_bsi=product_data.get("batch_size_items",1); cur_bsi=1 if cur_bsi==0 else cur_bsi
        mats_cost_pi=total_mats_cost_for_prod/cur_bsi if cur_bsi > 0 else 0
        st.metric("Total Materials Cost for Batch",f"€{total_mats_cost_for_prod:.2f}"); st.metric("Materials Cost per Item",f"€{mats_cost_pi:.2f}")

    with prod_tab2: # LABOR Product Tab
        st.subheader("🛠️ Labor")
        g_emp_df=pd.DataFrame(global_data.get("employees",[]))
        emp_opts_g=g_emp_df["name"].tolist() if not g_emp_df.empty else ["No employees defined globally"]
        prod_tsk_opts=[t.get("task_name","") for t in global_data.get("standard_production_tasks",[]) if t.get("task_name")] or ["No prod tasks defined"]
        ship_tsk_opts=[t.get("task_name","") for t in global_data.get("standard_shipping_tasks",[]) if t.get("task_name")] or ["No ship tasks defined"]
        
        st.markdown("#### Production Tasks")
        df_prod_tsk_orig = pd.DataFrame(product_data.get('production_tasks_performed',[]))
        if df_prod_tsk_orig.empty and prod_tsk_opts[0]!="No prod tasks defined" and emp_opts_g[0]!="No employees defined globally":
            df_prod_tsk_orig = pd.DataFrame([{"task_name":prod_tsk_opts[0],"employee_name":emp_opts_g[0],"time_minutes":0.0,"items_processed_in_task":1}])
        elif df_prod_tsk_orig.empty: df_prod_tsk_orig = pd.DataFrame(columns=task_perf_inv_rename_map.values())
        df_prod_tsk_renamed = df_prod_tsk_orig.rename(columns=task_perf_rename_map)
        edited_prod_tsk_df=st.data_editor(df_prod_tsk_renamed,
            column_config={
                task_perf_rename_map["task_name"]:st.column_config.SelectboxColumn(options=prod_tsk_opts,required=True),
                task_perf_rename_map["employee_name"]:st.column_config.SelectboxColumn(options=emp_opts_g,required=True),
                task_perf_rename_map["time_minutes"]:st.column_config.NumberColumn(format="%.1f",required=True,min_value=0.0, help="in minutes"),
                task_perf_rename_map["items_processed_in_task"]:st.column_config.NumberColumn(format="%d",required=True,min_value=1)},
            num_rows="dynamic",key=f"{product_name}_prod_tsk_ed_v2")
        product_data['production_tasks_performed']=edited_prod_tsk_df.rename(columns=task_perf_inv_rename_map).to_dict("records")
        product_data['production_tasks_performed'] = [r for r in product_data['production_tasks_performed'] if not (r.get("task_name") is None and r.get("employee_name") is None and r.get("time_minutes",0.0)==0.0) and r.get("task_name")!="No prod tasks defined" and r.get("employee_name")!="No employees defined globally" and float(r.get("time_minutes",0.0)) > 0]
        if product_data['production_tasks_performed'] and not g_emp_df.empty:
            emp_rate_lookup=dict(zip(g_emp_df["name"],g_emp_df["hourly_rate"].astype(float)))
            prod_lab_cost_pi=sum([(float(r.get("time_minutes",0))/60*emp_rate_lookup.get(r.get("employee_name"),0))/int(r.get("items_processed_in_task",1) or 1) for r in product_data['production_tasks_performed']])
        st.metric("Production Labor Cost per Item",f"€{prod_lab_cost_pi:.2f}")

        st.markdown("#### Shipping Tasks")
        df_ship_tsk_orig = pd.DataFrame(product_data.get('shipping_tasks_performed',[]))
        if df_ship_tsk_orig.empty and ship_tsk_opts[0]!="No ship tasks defined" and emp_opts_g[0]!="No employees defined globally":
            df_ship_tsk_orig = pd.DataFrame([{"task_name":ship_tsk_opts[0],"employee_name":emp_opts_g[0],"time_minutes":0.0,"items_processed_in_task":1}])
        elif df_ship_tsk_orig.empty: df_ship_tsk_orig = pd.DataFrame(columns=task_perf_inv_rename_map.values())
        df_ship_tsk_renamed = df_ship_tsk_orig.rename(columns=task_perf_rename_map)
        edited_ship_tsk_df=st.data_editor(df_ship_tsk_renamed,
            column_config={
                task_perf_rename_map["task_name"]:st.column_config.SelectboxColumn(options=ship_tsk_opts,required=True),
                task_perf_rename_map["employee_name"]:st.column_config.SelectboxColumn(options=emp_opts_g,required=True),
                task_perf_rename_map["time_minutes"]:st.column_config.NumberColumn(format="%.1f",required=True,min_value=0.0, help="in minutes"),
                task_perf_rename_map["items_processed_in_task"]:st.column_config.NumberColumn(format="%d",required=True,min_value=1)},
            num_rows="dynamic",key=f"{product_name}_ship_tsk_ed_v2")
        product_data['shipping_tasks_performed']=edited_ship_tsk_df.rename(columns=task_perf_inv_rename_map).to_dict("records")
        product_data['shipping_tasks_performed'] = [r for r in product_data['shipping_tasks_performed'] if not (r.get("task_name") is None and r.get("employee_name") is None and r.get("time_minutes",0.0)==0.0) and r.get("task_name")!="No ship tasks defined" and r.get("employee_name")!="No employees defined globally" and float(r.get("time_minutes",0.0)) > 0]
        if product_data['shipping_tasks_performed'] and not g_emp_df.empty:
            emp_rate_lookup=dict(zip(g_emp_df["name"],g_emp_df["hourly_rate"].astype(float)))
            ship_lab_cost_pi=sum([(float(r.get("time_minutes",0))/60*emp_rate_lookup.get(r.get("employee_name"),0))/int(r.get("items_processed_in_task",1) or 1) for r in product_data['shipping_tasks_performed']])
        st.metric("Shipping Labor Cost per Item",f"€{ship_lab_cost_pi:.2f}")
        st.metric("Total Direct Labor Cost per Item",f"€{prod_lab_cost_pi+ship_lab_cost_pi:.2f}")
        
        st.markdown("#### Salary Allocation (Optional)")
        salaried_employees_globally = [sal.get("employee_name") for sal in global_data.get("global_salaries", []) if sal.get("employee_name")]
        if not salaried_employees_globally: salaried_employees_globally = ["No Global Salaries Defined"]
        current_sal_alloc=product_data.get("salary_allocation",{"employee_name_for_salary":"None","items_per_month_for_salary":1000})
        selected_employee_for_salary = current_sal_alloc.get("employee_name_for_salary", "None")
        if selected_employee_for_salary not in (["None"] + salaried_employees_globally): selected_employee_for_salary = "None"
        sel_emp_name_for_sal=st.selectbox("Allocate Salary of Employee",options=["None"]+salaried_employees_globally,
            index=(["None"]+salaried_employees_globally).index(selected_employee_for_salary),
            key=f"{product_name}_sel_emp_for_sal")
        items_for_sal_alloc=st.number_input("Items of THIS Product per Month (for salary allocation)",value=int(current_sal_alloc.get("items_per_month_for_salary",1000)),min_value=1,key=f"{product_name}_items_for_sal")
        product_data["salary_allocation"]={"employee_name_for_salary":sel_emp_name_for_sal,"items_per_month_for_salary":items_for_sal_alloc}
        sal_cost_pi = 0.0
        if sel_emp_name_for_sal!="None" and sel_emp_name_for_sal != "No Global Salaries Defined" and items_for_sal_alloc>0:
            sal_info=next((s for s in global_data.get("global_salaries",[]) if s.get("employee_name")==sel_emp_name_for_sal),None)
            if sal_info: sal_cost_pi=float(sal_info.get("monthly_amount",0))/items_for_sal_alloc
        st.metric("Allocated Salary Cost per Item",f"€{sal_cost_pi:.2f}")

    with prod_tab3: # OTHER COSTS Product Tab (No st.data_editor here, so no changes for column titles)
        # ... (content from v2.7) ...
        st.subheader("📦 Other Costs")
        st.markdown("#### Rent & Utilities Allocation")
        items_for_rent_alloc=st.number_input("Items of THIS Product per Month (for rent/utilities)",value=int(product_data.get("rent_utilities_allocation",{}).get("items_per_month_for_rent",1000)),min_value=1,key=f"{product_name}_items_for_rent")
        product_data["rent_utilities_allocation"]={"items_per_month_for_rent":items_for_rent_alloc}
        if items_for_rent_alloc>0:
            g_rent=float(global_data.get("global_costs",{}).get("monthly_rent",0)); g_util=float(global_data.get("global_costs",{}).get("monthly_utilities",0))
            rent_util_cost_pi=(g_rent+g_util)/items_for_rent_alloc
        st.metric("Allocated Rent & Utilities Cost per Item",f"€{rent_util_cost_pi:.2f}")
        st.markdown("#### Packaging Costs (per Item)")
        cpk=product_data.get("packaging",{"label_cost_per_item":0.0,"materials_cost_per_item":0.0})
        lc=st.number_input("Label Cost/Item (€)",value=float(cpk.get("label_cost_per_item",0.0)),min_value=0.0,format="%.2f",key=f"{product_name}_lc")
        pmc=st.number_input("Other Pkg Materials Cost/Item (€)",value=float(cpk.get("materials_cost_per_item",0.0)),min_value=0.0,format="%.2f",key=f"{product_name}_pmc")
        product_data["packaging"]={"label_cost_per_item":lc,"materials_cost_per_item":pmc}; pkg_cost_pi=lc+pmc
        st.metric("Total Packaging Cost per Item",f"€{pkg_cost_pi:.2f}")
        st.markdown("#### Online Selling Fees - Retail")
        crf=product_data.get("retail_fees",{})
        def_rf_ao=float(crf.get("average_order_value",0.01)); def_rf_ao=0.01 if def_rf_ao<0.01 else def_rf_ao
        rf_ao=st.number_input("Avg Retail Order Value (€)",value=def_rf_ao,min_value=0.01,format="%.2f",key=f"{product_name}_rf_ao")
        rf_cc=st.number_input("Retail Credit Card Fee (%)",value=float(crf.get("cc_fee_percent",0.03)),min_value=0.0,format="%.3f",key=f"{product_name}_rf_cc")
        rf_p=st.number_input("Retail Platform Fee (%)",value=float(crf.get("platform_fee_percent",0.05)),min_value=0.0,format="%.3f",key=f"{product_name}_rf_p")
        rf_s=st.number_input("Retail Avg Shipping Paid by You (€)",value=float(crf.get("shipping_cost_paid_by_you",0.0)),min_value=0.0,format="%.2f",key=f"{product_name}_rf_s")
        product_data["retail_fees"]={"average_order_value":rf_ao,"cc_fee_percent":rf_cc,"platform_fee_percent":rf_p,"shipping_cost_paid_by_you":rf_s}
        ret_total_fees_calc=(rf_ao*rf_cc)+(rf_ao*rf_p)+rf_s; ret_fee_perc_calc=ret_total_fees_calc/rf_ao if rf_ao>0 else 0
        st.metric("Retail Fees per Order",f"€{ret_total_fees_calc:.2f}"); st.metric("Retail Fees % of Order",f"{ret_fee_perc_calc:.1%}")
        st.markdown("#### Online Selling Fees - Wholesale")
        cwsf=product_data.get("wholesale_fees",{})
        def_ws_ao=float(cwsf.get("average_order_value",0.01)); def_ws_ao=0.01 if def_ws_ao<0.01 else def_ws_ao
        ws_ao=st.number_input("Avg Wholesale Order Value (€)",value=def_ws_ao,min_value=0.01,format="%.2f",key=f"{product_name}_ws_ao")
        ws_c=st.number_input("Wholesale Commission (%)",value=float(cwsf.get("commission_percent",0.15)),min_value=0.0,format="%.3f",key=f"{product_name}_ws_c")
        ws_p=st.number_input("Wholesale Payment Processing Fee (%)",value=float(cwsf.get("processing_fee_percent",0.02)),min_value=0.0,format="%.3f",key=f"{product_name}_ws_p")
        ws_f=st.number_input("Wholesale Flat Fee per Order (€)",value=float(cwsf.get("flat_fee_per_order",0.0)),min_value=0.0,format="%.2f",key=f"{product_name}_ws_f")
        product_data["wholesale_fees"]={"average_order_value":ws_ao,"commission_percent":ws_c,"processing_fee_percent":ws_p,"flat_fee_per_order":ws_f}
        ws_total_fees_calc=(ws_ao*ws_c)+(ws_ao*ws_p)+ws_f; ws_fee_perc_calc=ws_total_fees_calc/ws_ao if ws_ao>0 else 0
        st.metric("Wholesale Fees per Order",f"€{ws_total_fees_calc:.2f}"); st.metric("Wholesale Fees % of Order",f"{ws_fee_perc_calc:.1%}")


    with prod_tab4: # SUMMARY & PRICING Product Tab (No st.data_editor here)
        # ... (content from v2.7) ...
        st.subheader("📊 Summary & Pricing")
        cost_comps={"Materials Cost/Item":mats_cost_pi,"Production Labor Cost/Item":prod_lab_cost_pi,
                    "Shipping Labor Cost/Item":ship_lab_cost_pi,"Allocated Salary Cost/Item":sal_cost_pi,
                    "Allocated Rent & Utilities Cost/Item":rent_util_cost_pi,"Packaging Cost/Item":pkg_cost_pi}
        cost_sum_df=pd.DataFrame(list(cost_comps.items()),columns=["Component","Cost per Item (€)"])
        st.dataframe(cost_sum_df.style.format({"Cost per Item (€)":"€{:.2f}"}))
        subtotal_cost_pi=sum(cost_comps.values()); st.metric("Subtotal Cost per Item",f"€{subtotal_cost_pi:.2f}")
        cpr=product_data.get("pricing",{})
        buf_p=st.slider("Buffer Percentage",0.0,0.5,float(cpr.get("buffer_percentage",0.1)),0.01,format="%.2f",key=f"{product_name}_buf")
        product_data["pricing"]["buffer_percentage"]=buf_p
        final_cost_pi_w_buf=subtotal_cost_pi*(1+buf_p); st.metric("Final Cost per Item (with Buffer)",f"€{final_cost_pi_w_buf:.2f}")
        st.markdown("#### Pricing Strategy")
        def_ws_pr=float(cpr.get("wholesale_price_per_item",0.01)); def_ws_pr=0.01 if def_ws_pr<0.01 else def_ws_pr
        def_rt_pr=float(cpr.get("retail_price_per_item",0.01)); def_rt_pr=0.01 if def_rt_pr<0.01 else def_rt_pr
        ws_pr=st.number_input("Wholesale Price/Item (€)",value=def_ws_pr,min_value=0.01,format="%.2f",key=f"{product_name}_ws_pr")
        rt_pr=st.number_input("Retail Price/Item (€)",value=def_rt_pr,min_value=0.01,format="%.2f",key=f"{product_name}_rt_pr")
        product_data["pricing"]["wholesale_price_per_item"]=ws_pr; product_data["pricing"]["retail_price_per_item"]=rt_pr
        ws_prof=ws_pr-final_cost_pi_w_buf-(ws_pr*ws_fee_perc_calc)
        rt_prof=rt_pr-final_cost_pi_w_buf-(rt_pr*ret_fee_perc_calc)
        ws_marg=ws_prof/ws_pr if ws_pr>0 else 0; rt_marg=rt_prof/rt_pr if rt_pr>0 else 0
        prof_df=pd.DataFrame({"Channel":["Wholesale","Retail"],"Price/Item (€)":[ws_pr,rt_pr],
            "Final Cost/Item (€)":[final_cost_pi_w_buf]*2,"Fees/Item (Est.) (€)":[ws_pr*ws_fee_perc_calc,rt_pr*ret_fee_perc_calc],
            "Profit/Item (€)":[ws_prof,rt_prof],"Profit Margin (%)":[ws_marg*100,rt_marg*100]})
        st.dataframe(prof_df.style.format({"Price/Item (€)":"€{:.2f}","Final Cost/Item (€)":"€{:.2f}","Fees/Item (Est.) (€)":"€{:.2f}","Profit/Item (€)":"€{:.2f}","Profit Margin (%)":"{:.1f}%"}))
        st.markdown("#### Revenue and Profit Projection")
        mpi_key=f"{product_name}_monthly_prod_items_v6" # Incremented key
        product_data["monthly_production_items"]=st.number_input("Monthly Production (Items)",value=int(product_data.get("monthly_production_items",1000)),min_value=1,key=mpi_key)
        ann_prod=product_data["monthly_production_items"]*12
        c_dist=product_data.get("distribution",{})
        ws_dist_p=st.slider("Wholesale Distribution (%)",0.0,1.0,float(c_dist.get("wholesale_percentage",0.5)),0.01,format="%.2f",key=f"{product_name}_ws_dist")
        rt_dist_p=1.0-ws_dist_p; st.slider("Retail Distribution (%)",0.0,1.0,rt_dist_p,0.01,format="%.2f",disabled=True,key=f"{product_name}_rt_dist_disp")
        product_data["distribution"]={"wholesale_percentage":ws_dist_p,"retail_percentage":rt_dist_p}
        ws_items_yr=ann_prod*ws_dist_p; rt_items_yr=ann_prod*rt_dist_p
        ws_rev_yr=ws_items_yr*ws_pr; rt_rev_yr=rt_items_yr*rt_pr
        ws_prof_yr=ws_items_yr*ws_prof; rt_prof_yr=rt_items_yr*rt_prof
        total_rev_yr=ws_rev_yr+rt_rev_yr; total_prof_yr=ws_prof_yr+rt_prof_yr
        overall_marg_yr=total_prof_yr/total_rev_yr if total_rev_yr>0 else 0
        proj_df=pd.DataFrame({"Channel":["Wholesale","Retail","Total"],"Annual Items":[ws_items_yr,rt_items_yr,ann_prod],
            "Annual Revenue (€)":[ws_rev_yr,rt_rev_yr,total_rev_yr],"Annual Profit (€)":[ws_prof_yr,rt_prof_yr,total_prof_yr]})
        st.dataframe(proj_df.style.format({"Annual Items":"{:,.0f}","Annual Revenue (€)":"€{:,.2f}","Annual Profit (€)":"€{:,.2f}"}))
        st.metric("Overall Annual Profit Margin",f"{overall_marg_yr:.1%}")


    if st.button(f"Save Product: {product_name}",key=f"save_{product_name}"):
        product_data["last_updated"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        saved_products[product_name]=product_data
        save_json_data(SAVED_PRODUCTS_FILE_PATH,saved_products)
        st.success(f"Product '{product_name}' saved!"); st.toast(f"'{product_name}' updated.",icon="✅")

elif app_mode=="Manage Products" and not ('current_product_name' in st.session_state and st.session_state.current_product_name):
    st.info("Select a product from the sidebar to edit, or create a new one.")

if app_mode != "Tutorial":
    st.markdown("---"); st.markdown("Product Cost Calculator v2.8 - Cloud Fix & Price URL")
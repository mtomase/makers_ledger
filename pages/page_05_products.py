# pages/page_05_products.py
import streamlit as st
import pandas as pd
from decimal import Decimal
from sqlalchemy.orm import Session, selectinload, joinedload
from models import (
    Product, User, Ingredient, Employee, StandardProductionTask, StandardShippingTask,
    ProductMaterial, ProductProductionTask, ProductShippingTask
)
from utils.db_helpers import (
    create_ingredient_display_string, get_ingredient_id_from_display,
    get_employee_id_from_name, get_std_prod_task_id_from_name, get_std_ship_task_id_from_name
)

def render(db: Session, user: User, is_mobile: bool):
    # This is a large function that will contain all sub-sections for managing a product
    # We will break it down internally for clarity

    render_main_product_editor(db, user, is_mobile)
    st.markdown("---")
    render_product_detail_manager(db, user, is_mobile)

def render_main_product_editor(db: Session, user: User, is_mobile: bool):
    st.header("📦 Manage Products")
    st.write("Add, edit, or delete main product attributes. Select a product to manage its detailed components.")
    
    products_db = db.query(Product).filter(Product.user_id == user.id).order_by(Product.id).all()
    product_editor_columns = ["ID", "Product Name", "Batch Size", "Monthly Production"]
    data_for_editor_prod = [{"ID": p.id, "Product Name": p.product_name, "Batch Size": p.batch_size_items, "Monthly Production": p.monthly_production_items} for p in products_db]
    df_products_for_editor = pd.DataFrame(data_for_editor_prod, columns=product_editor_columns)
    if df_products_for_editor.empty:
        df_products_for_editor = pd.DataFrame(columns=product_editor_columns).astype({"ID": "float64", "Product Name": "object", "Batch Size": "int64", "Monthly Production": "int64"})
    
    snapshot_key_prod = 'df_products_snapshot'
    if snapshot_key_prod not in st.session_state or not isinstance(st.session_state.get(snapshot_key_prod), pd.DataFrame) or not st.session_state[snapshot_key_prod].columns.equals(df_products_for_editor.columns):
        st.session_state[snapshot_key_prod] = df_products_for_editor.copy()
    
    prod_display_columns_desktop = ("Product Name", "Batch Size", "Monthly Production")
    prod_display_columns_mobile = ("Product Name", "Batch Size") 
    prod_columns_to_display = prod_display_columns_mobile if is_mobile else prod_display_columns_desktop
    
    product_column_config = {
        "Product Name": st.column_config.TextColumn("Product Name*", required=True, width="large"),
        "Batch Size": st.column_config.NumberColumn("Batch Size (items)*", required=True, min_value=1, step=1, format="%d", width="medium"),
        "Monthly Production": st.column_config.NumberColumn("Monthly Prod (items)*", required=True, min_value=0, step=1, format="%d", width="medium")}
    
    edited_df_prod = st.data_editor(st.session_state[snapshot_key_prod], num_rows="dynamic", key="products_editor", 
                                    column_order=prod_columns_to_display, 
                                    column_config=product_column_config, use_container_width=True, hide_index=True)
    
    if st.button("Save Product Attribute Changes", type="primary"):
        # ... (Same save logic as before, using `db` and `user` parameters)
        try:
            original_df_snapshot_prod = st.session_state[snapshot_key_prod]; original_snapshot_ids_prod = set(original_df_snapshot_prod['ID'].dropna().astype(int))
            edited_df_ids_prod = set(edited_df_prod['ID'].dropna().astype(int)); ids_to_delete_from_db_prod = original_snapshot_ids_prod - edited_df_ids_prod
            for p_id_del in ids_to_delete_from_db_prod:
                prod_to_del = db.query(Product).filter(Product.id == p_id_del, Product.user_id == user.id).first()
                if prod_to_del: db.delete(prod_to_del); st.toast(f"Deleted product ID: {p_id_del}", icon="➖")
                if st.session_state.selected_product_id == p_id_del: st.session_state.selected_product_id = None
            for index, edited_row in edited_df_prod.iterrows():
                p_id = edited_row.get('ID'); p_id = int(p_id) if pd.notna(p_id) else None
                name_val, batch_val = edited_row.get("Product Name"), edited_row.get("Batch Size")
                monthly_val = edited_row.get("Monthly Production") 
                is_monthly_prod_expected = "Monthly Production" in prod_columns_to_display
                
                if not name_val or not pd.notna(batch_val) or (is_monthly_prod_expected and not pd.notna(monthly_val)):
                    if p_id is None and not any([name_val, pd.notna(batch_val)]): continue
                    st.error(f"Row {index+1} (Products): Required fields missing. Ensure Name, Batch Size, and Monthly Production (if visible) are filled. Skipping."); continue
                
                if p_id: 
                    p_to_update = db.query(Product).filter(Product.id == p_id, Product.user_id == user.id).first()
                    if p_to_update:
                        changed = False
                        if p_to_update.product_name != name_val: p_to_update.product_name = name_val; changed=True
                        if p_to_update.batch_size_items != int(batch_val): p_to_update.batch_size_items = int(batch_val); changed=True
                        if is_monthly_prod_expected and pd.notna(monthly_val) and p_to_update.monthly_production_items != int(monthly_val):
                            p_to_update.monthly_production_items = int(monthly_val); changed=True
                        elif not is_monthly_prod_expected and p_to_update.monthly_production_items is None:
                             p_to_update.monthly_production_items = int(monthly_val) if pd.notna(monthly_val) else 0 
                        if changed: st.toast(f"Updated product ID: {p_id}", icon="🔄")
            new_rows_df_prod = edited_df_prod[edited_df_prod['ID'].isna()]
            for index, row in new_rows_df_prod.iterrows():
                name_val, batch_val = row.get("Product Name"), row.get("Batch Size")
                monthly_val = row.get("Monthly Production")
                is_monthly_prod_expected_new = "Monthly Production" in prod_columns_to_display
                if not name_val or not pd.notna(batch_val) or (is_monthly_prod_expected_new and not pd.notna(monthly_val)):
                    if not any([name_val, pd.notna(batch_val)]): continue
                    st.error(f"New Row (approx original index {index+1}): Required fields missing. Ensure Name, Batch Size, and Monthly Production (if visible) are filled. Skipping."); continue
                final_monthly_val = int(monthly_val) if pd.notna(monthly_val) else 0
                new_prod = Product(user_id=user.id, product_name=name_val, 
                                   batch_size_items=int(batch_val), 
                                   monthly_production_items=final_monthly_val)
                db.add(new_prod); db.flush(); 
                st.session_state.selected_product_id = new_prod.id 
                st.toast(f"Added: {name_val}. Selected for detail editing.", icon="➕")
            db.commit(); st.success("Product attribute changes saved!"); st.session_state[snapshot_key_prod] = edited_df_prod.copy(); st.rerun()
        except Exception as e_save_prod: db.rollback(); st.error(f"Error saving products: {e_save_prod}"); st.exception(e_save_prod)

def render_product_detail_manager(db: Session, user: User, is_mobile: bool):
    # ... (Code for the dropdown and all expanders, using `db` and `user` parameters)
    product_list_for_details = db.query(Product).filter(Product.user_id == user.id).order_by(Product.product_name).all()
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
        selected_product_object = db.query(Product).options(selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref), selectinload(Product.production_tasks).joinedload(ProductProductionTask.employee_ref), selectinload(Product.production_tasks).joinedload(ProductProductionTask.standard_task_ref), selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.employee_ref), selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.standard_task_ref), joinedload(Product.salary_alloc_employee_ref).joinedload(Employee.global_salary_entry)).filter(Product.id == st.session_state.selected_product_id, Product.user_id == user.id).first()
        if not selected_product_object: 
            st.warning("The previously selected product could not be found. Please select another product.")
            st.session_state.selected_product_id = None
        else:
            st.subheader(f"Managing Details for: **{selected_product_object.product_name}**")
            # All expanders follow here
            render_materials_expander(db, user, selected_product_object)
            render_prod_tasks_expander(db, user, selected_product_object, is_mobile)
            render_ship_tasks_expander(db, user, selected_product_object, is_mobile)
            render_other_costs_expander(db, user, selected_product_object, is_mobile)

# --- Sub-functions for each expander ---
def render_materials_expander(db, user, product):
    # ... (Code from the materials expander)
    pass
def render_prod_tasks_expander(db, user, product, is_mobile):
    # ... (Code from the production tasks expander)
    pass
def render_ship_tasks_expander(db, user, product, is_mobile):
    # ... (Code from the shipping tasks expander)
    pass
def render_other_costs_expander(db, user, product, is_mobile):
    # ... (Code from the other costs expander)
    pass
# NOTE: To keep this response from becoming excessively long, I've stubbed out the expander functions.
# You would copy the code from your main script into these functions, just as we did for the main pages.
# The logic is identical, just broken into smaller functions for readability.
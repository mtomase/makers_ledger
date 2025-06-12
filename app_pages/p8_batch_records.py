# app_pages/p8_batch_records.py
import streamlit as st
import pandas as pd
import datetime
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import (
    SessionLocal, User, Product, ProductionRun, BatchRecord, 
    BatchIngredientUsage, StockAddition, ProductMaterial, Employee,
    ProductProductionTask, StandardProductionTask, BatchProductionTask, PurchaseOrder
)

# --- Helper Functions (Unchanged) ---
def init_state():
    if 'editing_batch_id' not in st.session_state: st.session_state.editing_batch_id = None
    if 'show_new_run_form' not in st.session_state: st.session_state.show_new_run_form = False
    # State for confirmation dialogs
    if 'show_back_confirm_batch' not in st.session_state: st.session_state.show_back_confirm_batch = False
    if 'show_delete_confirm_batch' not in st.session_state: st.session_state.show_delete_confirm_batch = False

def get_all_batch_records(db: Session, user_id: int):
    return db.query(BatchRecord).join(ProductionRun).filter(ProductionRun.user_id == user_id).options(joinedload(BatchRecord.production_run_ref).joinedload(ProductionRun.product_ref), joinedload(BatchRecord.person_responsible_ref)).order_by(BatchRecord.manufacturing_date.desc(), BatchRecord.batch_code.desc()).all()

def get_full_batch_details(db: Session, batch_id: int):
    return db.query(BatchRecord).options(joinedload(BatchRecord.production_run_ref).joinedload(ProductionRun.product_ref).selectinload(Product.materials).selectinload(ProductMaterial.ingredient_ref), joinedload(BatchRecord.production_run_ref).joinedload(ProductionRun.product_ref).selectinload(Product.production_tasks).selectinload(ProductProductionTask.standard_task_ref), joinedload(BatchRecord.production_run_ref).joinedload(ProductionRun.product_ref).selectinload(Product.production_tasks).selectinload(ProductProductionTask.employee_ref), selectinload(BatchRecord.ingredient_usages).joinedload(BatchIngredientUsage.stock_addition_ref).joinedload(StockAddition.purchase_order_ref), selectinload(BatchRecord.ingredient_usages).joinedload(BatchIngredientUsage.stock_addition_ref).joinedload(StockAddition.ingredient_ref), selectinload(BatchRecord.production_tasks).joinedload(BatchProductionTask.employee_ref), selectinload(BatchRecord.production_tasks).joinedload(BatchProductionTask.standard_task_ref), joinedload(BatchRecord.person_responsible_ref)).filter(BatchRecord.id == batch_id).first()

def generate_next_batch_code(db: Session, user_id: int, product_code: str | None) -> str:
    prefix_code = product_code if product_code and product_code.strip() else "PROD"
    today = datetime.date.today(); date_str = today.strftime('%y%m%d'); search_prefix = f"{prefix_code}-{date_str}-"
    count_today = db.query(func.count(BatchRecord.id)).join(ProductionRun).filter(ProductionRun.user_id == user_id, BatchRecord.batch_code.like(f"{search_prefix}%")).scalar()
    next_seq = (count_today or 0) + 1
    return f"{search_prefix}{next_seq:02d}"

def render_new_run_form(db: Session, user: User):
    # Unchanged
    st.subheader("🚀 Start New Production Run")
    products = db.query(Product).filter(Product.user_id == user.id).order_by(Product.product_name).all()
    if not products: st.error("You must create a Product before you can start a production run."); return
    with st.form("new_run_form"):
        product_options = {p.id: p.product_name for p in products}
        selected_product_id = st.selectbox("Select Product", options=list(product_options.keys()), format_func=lambda x: product_options[x])
        planned_count = st.number_input("Number of Batches to Plan in this Run", min_value=1, value=1, step=1)
        notes = st.text_area("Notes for this Run")
        if st.form_submit_button("Create Run and First Batch"):
            with SessionLocal() as transaction_db:
                try:
                    new_run = ProductionRun(user_id=user.id, product_id=selected_product_id, planned_batch_count=planned_count, notes=notes)
                    transaction_db.add(new_run); transaction_db.flush()
                    selected_product = transaction_db.query(Product).filter(Product.id == selected_product_id).first()
                    new_batch_code = generate_next_batch_code(transaction_db, user.id, selected_product.product_code)
                    new_batch = BatchRecord(production_run_id=new_run.id, user_id=user.id, batch_code=new_batch_code, manufacturing_date=datetime.date.today())
                    transaction_db.add(new_batch); transaction_db.commit()
                    st.success(f"Production run started for '{product_options[selected_product_id]}' and batch '{new_batch_code}' has been created.")
                    st.session_state.show_new_run_form = False; st.session_state.editing_batch_id = new_batch.id
                except Exception as e:
                    transaction_db.rollback(); st.error(f"An error occurred: {e}")
            st.rerun()

def render_batch_editor(db: Session, user: User):
    batch_id = st.session_state.editing_batch_id
    if not batch_id: return
    batch = get_full_batch_details(db, batch_id)
    if not batch:
        st.error("Could not load the selected batch."); st.session_state.editing_batch_id = None; st.rerun(); return

    # --- Confirmation Dialog Logic ---
    if st.session_state.show_back_confirm_batch:
        with st.container(border=True):
            st.warning("Are you sure you want to go back to the list? Unsaved changes in the main details form will be lost.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Go Back", use_container_width=True, key="confirm_back_batch"):
                st.session_state.show_back_confirm_batch = False
                st.session_state.editing_batch_id = None
                st.rerun()
            if c2.button("No, Stay Here", use_container_width=True, key="keep_editing_batch"):
                st.session_state.show_back_confirm_batch = False
                st.rerun()
        return

    if st.session_state.show_delete_confirm_batch:
        with st.container(border=True):
            st.error(f"Are you sure you want to permanently delete batch **{batch.batch_code}**? This cannot be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Delete Permanently", type="primary", use_container_width=True, key="confirm_delete_batch"):
                with SessionLocal() as t_db:
                    batch_to_delete = t_db.query(BatchRecord).filter(BatchRecord.id == batch.id).one()
                    t_db.delete(batch_to_delete); t_db.commit()
                st.success(f"Batch '{batch.batch_code}' has been deleted.")
                st.session_state.show_delete_confirm_batch = False
                st.session_state.editing_batch_id = None
                st.rerun()
            if c2.button("No, Go Back", use_container_width=True, key="keep_batch_safe"):
                st.session_state.show_delete_confirm_batch = False
                st.rerun()
        return

    # --- Main Editor View ---
    st.subheader(f"📝 Editing Batch: {batch.batch_code}")
    tab_main, tab_trace, tab_workflow = st.tabs(["Main Details", "🌿 Ingredient Traceability", "📋 Production Workflow"])
    with tab_main:
        render_main_details_form(db, user, batch)
    with tab_trace:
        render_traceability_section(db, user, batch)
    with tab_workflow:
        render_workflow_section(db, user, batch)

def render_main_details_form(db: Session, user: User, batch: BatchRecord):
    employees = db.query(Employee).filter(Employee.user_id == user.id).order_by(Employee.name).all()
    employee_options = {emp.id: emp.name for emp in employees}; employee_options[None] = "N/A"
    
    with st.form("batch_edit_form"):
        st.markdown(f"**Product:** {batch.production_run_ref.product_ref.product_name}")
        c1, c2 = st.columns(2)
        batch_code = c1.text_input("Batch Code", value=batch.batch_code)
        person_id_options = list(employee_options.keys())
        person_id_index = person_id_options.index(batch.person_responsible_id) if batch.person_responsible_id in person_id_options else 0
        person_id = c2.selectbox("Person Responsible", options=person_id_options, format_func=lambda x: employee_options[x], index=person_id_index)
        c1, c2, c3 = st.columns(3)
        mfg_date = c1.date_input("Manufacturing Date", value=batch.manufacturing_date or datetime.date.today())
        cured_date = c2.date_input("Cured Date", value=batch.cured_date, min_value=mfg_date if mfg_date else None)
        exp_date = c3.date_input("Expiration Date", value=batch.expiration_date, min_value=cured_date if cured_date else None)
        st.markdown("---")
        st.markdown("**Batch Details & QC**")
        d1, d2, d3 = st.columns(3)
        bars_in_batch = d1.number_input("Bars in Batch", value=int(batch.bars_in_batch or 0), min_value=0)
        final_weight = d2.number_input("Final Cured Weight (g)", value=float(batch.final_cured_weight_gr or 0.0), format="%.2f")
        ph_cured = d3.number_input("Cured pH", value=float(batch.qc_ph_cured or 0.0), format="%.2f")
        notes = st.text_area("Final Quality Notes", value=batch.qc_final_quality_notes or "")
        
        # --- FIX: Removed use_container_width=True ---
        submitted = st.form_submit_button("💾 Save Main Details", type="primary")
        if submitted:
            with SessionLocal() as transaction_db:
                try:
                    b = transaction_db.query(BatchRecord).filter(BatchRecord.id == batch.id).one()
                    b.batch_code, b.person_responsible_id, b.manufacturing_date, b.cured_date, b.expiration_date, b.bars_in_batch, b.final_cured_weight_gr, b.qc_ph_cured, b.qc_final_quality_notes = batch_code, person_id, mfg_date, cured_date, exp_date, bars_in_batch, (Decimal(str(final_weight)) if final_weight else None), (Decimal(str(ph_cured)) if ph_cured else None), notes
                    transaction_db.commit()
                    st.success(f"Batch '{batch.batch_code}' updated successfully.")
                except Exception as e:
                    transaction_db.rollback(); st.error(f"Error saving: {e}")
            st.rerun()

    # --- Action Buttons (outside the form) ---
    c1, c2, _ = st.columns([1, 1, 5])
    if c1.button("⬅️ Back to List", use_container_width=True):
        st.session_state.show_back_confirm_batch = True
        st.rerun()

    if c2.button("🗑️ Delete Batch", use_container_width=True):
        st.session_state.show_delete_confirm_batch = True
        st.rerun()

def render_traceability_section(db: Session, user: User, batch: BatchRecord):
    # Unchanged
    product_recipe = batch.production_run_ref.product_ref.materials
    if not product_recipe: st.warning("This product has no recipe defined. Please add materials on the 'Manage Products' page."); return
    usage_summary = {m.ingredient_id: {"name": m.ingredient_ref.name, "required": m.quantity_grams, "used": Decimal("0.0")} for m in product_recipe}
    for usage in batch.ingredient_usages:
        if usage.ingredient_id in usage_summary: usage_summary[usage.ingredient_id]["used"] += usage.quantity_used_grams
    summary_data = [{"Ingredient": v["name"], "Required (g)": f"{v['required']:.2f}", "Used (g)": f"{v['used']:.2f}", "Status": "✅" if v['used'] >= v['required'] else "⏳"} for k, v in usage_summary.items()]
    st.dataframe(summary_data, hide_index=True, use_container_width=True)
    st.markdown("---")
    for material in product_recipe:
        with st.expander(f"Allocate **{material.ingredient_ref.name}** (Required: {material.quantity_grams:.2f}g)"):
            required_qty, used_qty = usage_summary[material.ingredient_id]['required'], usage_summary[material.ingredient_id]['used']
            remaining_needed = max(Decimal("0.0"), required_qty - used_qty)
            st.write("**Current Allocations for this Ingredient:**")
            current_usages_for_ingredient = [u for u in batch.ingredient_usages if u.ingredient_id == material.ingredient_id]
            if not current_usages_for_ingredient: st.write("_None_")
            else:
                for usage in current_usages_for_ingredient:
                    st.info(f"Used **{usage.quantity_used_grams:.2f}g** from Lot #**{usage.stock_addition_ref.supplier_lot_number or 'N/A'}** (Purchased: {usage.stock_addition_ref.purchase_order_ref.order_date})")
            st.markdown("---")
            if remaining_needed <= 0: st.success(f"✅ Requirement for {material.ingredient_ref.name} has been met.")
            else:
                st.write("**Add New Allocation**")
                available_stock = db.query(StockAddition).join(PurchaseOrder).filter(PurchaseOrder.user_id == user.id, StockAddition.ingredient_id == material.ingredient_id, StockAddition.quantity_remaining_grams > 0).order_by(PurchaseOrder.order_date).all()
                if not available_stock: st.warning(f"No stock available for {material.ingredient_ref.name}. Please add a purchase on the 'Stock Management' page."); continue
                with st.form(key=f"form_alloc_{material.ingredient_id}"):
                    lot_options = {f"Lot #{s.supplier_lot_number or 'N/A'} (Rem: {s.quantity_remaining_grams:.2f}g, Date: {s.purchase_order_ref.order_date})": s.id for s in available_stock}
                    selected_lot_str = st.selectbox("Select Stock Lot", options=lot_options.keys())
                    selected_stock_id = lot_options.get(selected_lot_str)
                    selected_stock_obj = next((s for s in available_stock if s.id == selected_stock_id), None)
                    max_qty_in_lot = selected_stock_obj.quantity_remaining_grams if selected_stock_obj else Decimal("0.0")
                    default_qty_to_use = min(remaining_needed, max_qty_in_lot)
                    qty_to_use = st.number_input("Quantity to Use (g)", min_value=0.01, max_value=float(max_qty_in_lot), value=float(default_qty_to_use), format="%.3f")
                    if st.form_submit_button("Allocate"):
                        with SessionLocal() as transaction_db:
                            try:
                                stock_to_update = transaction_db.query(StockAddition).filter(StockAddition.id == selected_stock_id).one()
                                if Decimal(str(qty_to_use)) > stock_to_update.quantity_remaining_grams:
                                    st.error("Cannot use more than the remaining quantity in the selected lot."); transaction_db.rollback()
                                else:
                                    new_usage = BatchIngredientUsage(batch_record_id=batch.id, stock_addition_id=selected_stock_id, ingredient_id=material.ingredient_id, quantity_used_grams=Decimal(str(qty_to_use)))
                                    transaction_db.add(new_usage)
                                    stock_to_update.quantity_remaining_grams -= Decimal(str(qty_to_use)); transaction_db.commit()
                                    st.success("Allocation saved!"); st.rerun()
                            except Exception as e:
                                transaction_db.rollback(); st.error(f"An error occurred: {e}")

def render_workflow_section(db: Session, user: User, batch: BatchRecord):
    # Unchanged
    st.write("Record the actual employee who performed each task for this specific batch. The default is from the product template.")
    standard_workflow = batch.production_run_ref.product_ref.production_tasks
    if not standard_workflow: st.warning("This product has no workflow defined on the 'Manage Products' page."); return
    all_employees = db.query(Employee).filter(Employee.user_id == user.id).order_by(Employee.name).all()
    if not all_employees: st.error("No employees found. Please add employees on the 'Manage Employees' page."); return
    batch_task_map = {bt.standard_task_id: bt.employee_ref.name for bt in batch.production_tasks}
    workflow_data = [{"ID": std_task.standard_task_id, "Task": std_task.standard_task_ref.task_name, "Assigned To": batch_task_map.get(std_task.standard_task_id, std_task.employee_ref.name), "Time (minutes)": std_task.time_minutes} for std_task in standard_workflow]
    df_workflow = pd.DataFrame(workflow_data)
    with st.form("workflow_form"):
        st.markdown("**Edit Batch Workflow**")
        edited_df = st.data_editor(df_workflow, key="batch_workflow_editor", use_container_width=True, hide_index=True, column_config={"ID": None, "Task": st.column_config.TextColumn("Task", disabled=True), "Time (minutes)": st.column_config.NumberColumn("Time (minutes)", disabled=True, format="%.1f"), "Assigned To": st.column_config.SelectboxColumn("Assigned To", options=[emp.name for emp in all_employees], required=True)})
        if st.form_submit_button("Save Workflow Changes", type="primary"):
            with SessionLocal() as transaction_db:
                try:
                    transaction_db.query(BatchProductionTask).filter(BatchProductionTask.batch_record_id == batch.id).delete()
                    emp_map = {emp.name: emp.id for emp in all_employees}
                    for _, row in edited_df.iterrows():
                        std_task_id, assigned_emp_name = row["ID"], row["Assigned To"]
                        if emp_id := emp_map.get(assigned_emp_name):
                            transaction_db.add(BatchProductionTask(batch_record_id=batch.id, standard_task_id=std_task_id, employee_id=emp_id))
                    transaction_db.commit()
                    st.success("Batch workflow assignments saved!")
                except Exception as e:
                    transaction_db.rollback(); st.error(f"An error occurred while saving: {e}")
            st.rerun()

def render(db: Session, user: User, is_mobile: bool):
    # Unchanged
    st.header("📋 Batch Records")
    st.write("Create and manage your production batch records, ensuring full traceability from raw materials to finished goods.")
    init_state()
    if st.session_state.editing_batch_id:
        render_batch_editor(db, user)
    elif st.session_state.show_new_run_form:
        render_new_run_form(db, user)
    else:
        st.subheader("📖 All Batch Records")
        if st.button("➕ Start New Production Run", type="primary"):
            st.session_state.show_new_run_form = True; st.session_state.editing_batch_id = None; st.rerun()
        records = get_all_batch_records(db, user.id)
        if not records: st.info("No batch records found. Start a new production run to begin.")
        else:
            df_data = [{"id": r.id, "Batch Code": r.batch_code, "Product": r.production_run_ref.product_ref.product_name, "Date": r.manufacturing_date, "Responsible": r.person_responsible_ref.name if r.person_responsible_ref else "N/A"} for r in records]
            df = pd.DataFrame(df_data)
            selection_result = st.dataframe(df, on_select="rerun", selection_mode="single-row", hide_index=True, use_container_width=True, column_order=("Batch Code", "Product", "Date", "Responsible"), column_config={"id": None, "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD")})
            if selection_result.selection.rows:
                st.session_state.editing_batch_id = int(df.iloc[selection_result.selection.rows[0]]["id"])
                st.session_state.show_new_run_form = False; st.rerun()
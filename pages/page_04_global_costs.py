# pages/page_04_global_costs.py
import streamlit as st
import pandas as pd
from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from models import GlobalCosts, GlobalSalary, Employee, User

def render(db: Session, user: User, is_mobile: bool):
    st.header("🌍 Global Costs & Salaries")
    st.info("Manage global fixed costs and monthly salaries. These are used for overhead allocation.")

    with st.expander("💰 Monthly Fixed Overheads", expanded=True):
        global_costs_obj = db.query(GlobalCosts).filter(GlobalCosts.user_id == user.id).first()
        if not global_costs_obj:
            global_costs_obj = GlobalCosts(user_id=user.id, monthly_rent=Decimal('0.0'), monthly_utilities=Decimal('0.0'))
        
        rent_val = st.number_input("Global Monthly Rent (€)", value=float(global_costs_obj.monthly_rent or Decimal('0.0')), min_value=0.0, format="%.2f", key="global_rent")
        util_val = st.number_input("Global Monthly Utilities (€)", value=float(global_costs_obj.monthly_utilities or Decimal('0.0')), min_value=0.0, format="%.2f", key="global_utilities")
        
        if st.button("Save Global Overheads", key="save_global_overheads", type="primary"):
            global_costs_obj.monthly_rent = Decimal(str(rent_val))
            global_costs_obj.monthly_utilities = Decimal(str(util_val))
            db.add(global_costs_obj)
            try:
                db.commit()
                st.success("Global overheads saved!")
                st.rerun()
            except Exception as e_save_global:
                db.rollback()
                st.error(f"Error saving global overheads: {e_save_global}")

    st.markdown("---")
    st.subheader("💵 Global Monthly Salaries")
    st.write("Edit, add, or delete global salaries.")
    
    global_salaries_db = db.query(GlobalSalary).options(joinedload(GlobalSalary.employee_ref)).filter(GlobalSalary.user_id == user.id).order_by(GlobalSalary.id).all()
    all_employees_list_gs = db.query(Employee).filter(Employee.user_id == user.id).all() 
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
    if snapshot_key_gs not in st.session_state or not isinstance(st.session_state.get(snapshot_key_gs), pd.DataFrame) or not st.session_state[snapshot_key_gs].columns.equals(df_gs_for_editor.columns):
        st.session_state[snapshot_key_gs] = df_gs_for_editor.copy()
    
    gs_display_columns_desktop = ("Employee Name", "Monthly Salary (€)")
    gs_display_columns_mobile = ("Employee Name",) 
    gs_columns_to_display = gs_display_columns_mobile if is_mobile else gs_display_columns_desktop

    edited_df_gs = st.data_editor(
        st.session_state[snapshot_key_gs], num_rows="dynamic", key="global_salaries_editor",
        column_order=gs_columns_to_display, 
        column_config={
            "Employee Name": st.column_config.SelectboxColumn("Employee*", options=employee_names_gs, required=True), 
            "Monthly Salary (€)": st.column_config.NumberColumn("Monthly Salary (€)*", required=True, min_value=0.0, step=10.0, format="%.2f")
        }, 
        use_container_width=True, hide_index=True
    )

    if st.button("Save Global Salaries", type="primary"):
        try:
            original_df_snapshot_gs = st.session_state[snapshot_key_gs]
            original_snapshot_ids_gs = set(original_df_snapshot_gs['ID'].dropna().astype(int))
            edited_df_ids_gs = set(edited_df_gs['ID'].dropna().astype(int))
            ids_to_delete_from_db_gs = original_snapshot_ids_gs - edited_df_ids_gs

            for gs_id_del in ids_to_delete_from_db_gs:
                gs_to_del = db.query(GlobalSalary).filter(GlobalSalary.id == gs_id_del, GlobalSalary.user_id == user.id).first()
                if gs_to_del: db.delete(gs_to_del); st.toast(f"Deleted global salary ID: {gs_id_del}", icon="➖")

            for index, row in edited_df_gs.iterrows():
                gs_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                emp_name_val = row.get("Employee Name")
                amount_val = row.get("Monthly Salary (€)") 
                if amount_val is None and "Monthly Salary (€)" not in gs_columns_to_display: 
                    original_row = original_df_snapshot_gs[original_df_snapshot_gs["ID"] == gs_id] if gs_id else None
                    if original_row is not None and not original_row.empty:
                        amount_val = original_row["Monthly Salary (€)"].iloc[0]
                    else:
                        st.error(f"Row {index+1} (Global Salaries): Salary amount missing. Please edit on a wider screen or ensure data is complete."); continue
                
                if not all([emp_name_val, emp_name_val != "No employees defined", pd.notna(amount_val)]):
                    if gs_id is None and not any([emp_name_val, pd.notna(amount_val)]): continue
                    st.error(f"Row {index+1} (Global Salaries): Invalid data. Skipping."); continue
                
                employee_id_for_gs = employee_options_gs.get(emp_name_val)
                if not employee_id_for_gs:
                    st.error(f"Row {index+1} (Global Salaries): Employee '{emp_name_val}' not found. Skipping."); continue

                if gs_id: 
                    gs_to_update = db.query(GlobalSalary).filter(GlobalSalary.id == gs_id, GlobalSalary.user_id == user.id).first()
                    if gs_to_update:
                        changed = False
                        if gs_to_update.employee_id != employee_id_for_gs: gs_to_update.employee_id = employee_id_for_gs; changed=True
                        if gs_to_update.monthly_amount != Decimal(str(amount_val)): gs_to_update.monthly_amount = Decimal(str(amount_val)); changed=True 
                        if changed: st.toast(f"Updated global salary ID: {gs_id}", icon="🔄")
            
            new_rows_df_gs = edited_df_gs[edited_df_gs['ID'].isna()]
            for index, row in new_rows_df_gs.iterrows():
                emp_name_val = row.get("Employee Name")
                amount_val = row.get("Monthly Salary (€)")
                if amount_val is None and "Monthly Salary (€)" not in gs_columns_to_display:
                    st.error(f"New Row (Global Salaries): Salary amount missing."); continue
                if not all([emp_name_val, emp_name_val != "No employees defined", pd.notna(amount_val)]):
                    if not any([emp_name_val, pd.notna(amount_val)]): continue
                    st.error(f"New Row (Global Salaries - approx original index {index+1}): Invalid data. Skipping."); continue
                
                employee_id_for_gs = employee_options_gs.get(emp_name_val)
                if not employee_id_for_gs:
                    st.error(f"New Row (Global Salaries - approx original index {index+1}): Employee '{emp_name_val}' not found. Skipping."); continue
                
                existing_salary = db.query(GlobalSalary).filter(GlobalSalary.user_id == user.id, GlobalSalary.employee_id == employee_id_for_gs).first()
                if existing_salary:
                    st.warning(f"Employee '{emp_name_val}' already has a global salary. Edit existing. Skipping addition."); continue
                
                db.add(GlobalSalary(user_id=user.id, employee_id=employee_id_for_gs, monthly_amount=Decimal(str(amount_val))))
                st.toast(f"Added global salary for {emp_name_val}", icon="➕")

            db.commit()
            st.success("Global salaries saved!")
            st.session_state[snapshot_key_gs] = edited_df_gs.copy()
            st.rerun()
        except IntegrityError:
            db.rollback()
            st.error("Error: An employee can only have one global salary entry.")
        except Exception as e_save_gs:
            db.rollback()
            st.error(f"Error saving global salaries: {e_save_gs}")
            st.exception(e_save_gs)
# pages/page_02_employees.py
import streamlit as st
import pandas as pd
from decimal import Decimal
from sqlalchemy.orm import Session
from models import Employee, User

def render(db: Session, user: User, is_mobile: bool):
    st.header("👥 Manage Employees")
    st.write("Edit, add, or delete employees. Click **'Save Employee Changes'** to persist.")
    
    employees_db = db.query(Employee).filter(Employee.user_id == user.id).order_by(Employee.id).all()
    data_for_editor_emp = [{"ID": emp.id, "Name": emp.name, "Hourly Rate (€)": emp.hourly_rate, "Role": emp.role} for emp in employees_db]
    df_emp_cols = ["ID", "Name", "Hourly Rate (€)", "Role"]; df_employees_for_editor = pd.DataFrame(data_for_editor_emp, columns=df_emp_cols)
    if df_employees_for_editor.empty: df_employees_for_editor = pd.DataFrame(columns=df_emp_cols).astype({"ID": "float64", "Name": "object", "Hourly Rate (€)": "float64", "Role": "object"})
    snapshot_key_emp = 'df_employees_snapshot'
    if snapshot_key_emp not in st.session_state or not isinstance(st.session_state.get(snapshot_key_emp), pd.DataFrame) or not st.session_state[snapshot_key_emp].columns.equals(df_employees_for_editor.columns): st.session_state[snapshot_key_emp] = df_employees_for_editor.copy()
    
    emp_display_columns_desktop = ("Name", "Hourly Rate (€)", "Role")
    emp_display_columns_mobile = ("Name", "Hourly Rate (€)") 
    emp_columns_to_display = emp_display_columns_mobile if is_mobile else emp_display_columns_desktop
    
    edited_df_emp = st.data_editor(st.session_state[snapshot_key_emp], num_rows="dynamic", key="employees_editor", 
                                   column_order=emp_columns_to_display, 
                                   column_config={"Name": st.column_config.TextColumn("Employee Name*", required=True),"Hourly Rate (€)": st.column_config.NumberColumn("Hourly Rate (€)*", required=True, min_value=0.00, step=0.01, format="%.2f"),"Role": st.column_config.TextColumn("Role (Optional)")}, 
                                   use_container_width=True, hide_index=True)
    if st.button("Save Employee Changes", type="primary"):
        try:
            original_df_snapshot_emp = st.session_state[snapshot_key_emp]; original_snapshot_ids_emp = set(original_df_snapshot_emp['ID'].dropna().astype(int))
            edited_df_ids_emp = set(edited_df_emp['ID'].dropna().astype(int)); ids_to_delete_from_db_emp = original_snapshot_ids_emp - edited_df_ids_emp
            for emp_id_del in ids_to_delete_from_db_emp:
                emp_to_del = db.query(Employee).filter(Employee.id == emp_id_del, Employee.user_id == user.id).first()
                if emp_to_del: db.delete(emp_to_del); st.toast(f"Deleted employee ID: {emp_id_del}", icon="➖")
            for index, row in edited_df_emp.iterrows():
                emp_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None; name_val, rate_val = row.get("Name"), row.get("Hourly Rate (€)")
                role_val = row.get("Role") 
                if role_val is None and "Role" not in emp_columns_to_display: role_val = "" 
                
                if not all([name_val, pd.notna(rate_val)]):
                    if emp_id is None and not any([name_val, pd.notna(rate_val), role_val]): continue
                    st.error(f"Row {index+1}: Name and Hourly Rate are required. Skipping."); continue
                role_val = str(role_val).strip() if role_val and str(role_val).strip() else None
                if emp_id: 
                    item_to_update = db.query(Employee).filter(Employee.id == emp_id, Employee.user_id == user.id).first()
                    if item_to_update:
                        changed = False
                        if item_to_update.name != name_val: item_to_update.name = name_val; changed=True
                        if item_to_update.hourly_rate != Decimal(str(rate_val)): item_to_update.hourly_rate = Decimal(str(rate_val)); changed=True 
                        if item_to_update.role != role_val: item_to_update.role = role_val; changed=True
                        if changed: st.toast(f"Updated employee ID: {emp_id}", icon="🔄")
            new_rows_df_emp = edited_df_emp[edited_df_emp['ID'].isna()]
            for index, row in new_rows_df_emp.iterrows():
                name_val, rate_val = row.get("Name"), row.get("Hourly Rate (€)")
                role_val = row.get("Role")
                if role_val is None and "Role" not in emp_columns_to_display: role_val = ""
                if not all([name_val, pd.notna(rate_val)]):
                    if not any([name_val, pd.notna(rate_val), role_val]): continue
                    st.error(f"New Row (approx original index {index+1}): Name and Hourly Rate are required. Skipping."); continue
                role_val = str(role_val).strip() if role_val and str(role_val).strip() else None
                db.add(Employee(user_id=user.id, name=name_val, hourly_rate=Decimal(str(rate_val)), role=role_val)) 
                st.toast(f"Added employee: {name_val}", icon="➕")
            db.commit(); st.success("Employee changes saved!"); st.session_state[snapshot_key_emp] = edited_df_emp.copy(); st.rerun()
        except Exception as e_save_emp: db.rollback(); st.error(f"Error saving employees: {e_save_emp}"); st.exception(e_save_emp)
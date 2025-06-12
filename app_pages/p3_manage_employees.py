# app_pages/p3_manage_employees.py
import streamlit as st
import pandas as pd
from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import SessionLocal, User, Employee, GlobalSalary

# --- Helper Function to fetch combined data ---
def get_employee_data(db: Session, user_id: int):
    """
    Fetches all employees and their corresponding monthly salaries using a LEFT JOIN.
    This ensures all employees are returned, even those without a salary.
    """
    results = db.query(
        Employee,
        GlobalSalary.monthly_amount
    ).outerjoin(GlobalSalary, Employee.id == GlobalSalary.employee_id)\
     .filter(Employee.user_id == user_id)\
     .order_by(Employee.id)\
     .all()
    
    data = []
    for employee, salary in results:
        data.append({
            "ID": employee.id,
            "Name": employee.name,
            "Hourly Rate (€)": employee.hourly_rate,
            "Role": employee.role,
            "Monthly Salary (€)": salary if salary is not None else Decimal('0.00')
        })
    return data

# --- Page-specific content ---
def render(db: Session, user: User, is_mobile: bool):
    st.header("👥 Manage Employees")
    st.write("Define your employees, their hourly rates, and any fixed monthly salaries for overhead calculations in one place.")
    
    st.subheader("Employee & Salary List")
    
    # Fetch the combined employee and salary data
    employee_salary_data = get_employee_data(db, user.id)
    df_employees = pd.DataFrame(employee_salary_data)
    
    # Use the dataframe to power the data editor
    edited_df = st.data_editor(
        df_employees,
        num_rows="dynamic",
        key="employees_editor",
        column_config={
            "ID": None, # Hide the ID column
            "Name": st.column_config.TextColumn("Employee Name*", required=True),
            "Hourly Rate (€)": st.column_config.NumberColumn("Hourly Rate (€)*", required=True, min_value=0.00, format="€%.2f"),
            "Role": st.column_config.TextColumn("Role (Optional)"),
            "Monthly Salary (€)": st.column_config.NumberColumn("Monthly Salary (€)", min_value=0.00, format="€%.2f", help="Set to 0 if not applicable.")
        },
        use_container_width=True,
        hide_index=True
    )

    if st.button("💾 Save All Employee Changes", type="primary"):
        with SessionLocal() as transaction_db:
            try:
                # Get IDs before and after editing to handle deletions
                ids_before = set(df_employees['ID'].dropna())
                ids_after = set(edited_df['ID'].dropna())
                ids_to_delete = ids_before - ids_after
                
                # Process deletions
                if ids_to_delete:
                    transaction_db.query(Employee).filter(
                        Employee.id.in_(ids_to_delete),
                        Employee.user_id == user.id
                    ).delete(synchronize_session=False)

                # Process updates and inserts
                for _, row in edited_df.iterrows():
                    emp_id = row.get("ID")
                    name = row.get("Name")
                    rate = row.get("Hourly Rate (€)")
                    salary = row.get("Monthly Salary (€)")

                    if not name or pd.isna(rate):
                        continue # Skip rows without a name or rate

                    # Convert to Decimal for precision
                    rate_decimal = Decimal(str(rate))
                    salary_decimal = Decimal(str(salary if not pd.isna(salary) else '0.0'))

                    if pd.notna(emp_id): # Update existing employee
                        employee = transaction_db.query(Employee).filter_by(id=int(emp_id), user_id=user.id).one()
                        employee.name = name.strip()
                        employee.hourly_rate = rate_decimal
                        employee.role = row.get("Role", "").strip() or None
                        
                        # Handle salary (update, create, or delete)
                        salary_entry = transaction_db.query(GlobalSalary).filter_by(employee_id=employee.id).first()
                        if salary_decimal > 0:
                            if salary_entry:
                                salary_entry.monthly_amount = salary_decimal
                            else:
                                new_salary = GlobalSalary(user_id=user.id, employee_id=employee.id, monthly_amount=salary_decimal)
                                transaction_db.add(new_salary)
                        elif salary_entry: # Salary is 0 or None, so delete existing entry
                            transaction_db.delete(salary_entry)

                    else: # Insert new employee
                        new_employee = Employee(
                            user_id=user.id,
                            name=name.strip(),
                            hourly_rate=rate_decimal,
                            role=row.get("Role", "").strip() or None
                        )
                        transaction_db.add(new_employee)
                        transaction_db.flush() # Flush to get the new_employee.id

                        # If salary is provided for the new employee, create it
                        if salary_decimal > 0:
                            new_salary = GlobalSalary(user_id=user.id, employee_id=new_employee.id, monthly_amount=salary_decimal)
                            transaction_db.add(new_salary)
                
                transaction_db.commit()
                st.success("✅ Employee and salary changes saved successfully!")
            except IntegrityError:
                transaction_db.rollback()
                st.error("❌ Save failed. Employee names must be unique.")
            except Exception as e:
                transaction_db.rollback()
                st.error(f"❌ An error occurred: {e}")
        st.rerun()
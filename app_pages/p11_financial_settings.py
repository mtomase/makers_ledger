# app_pages/p11_financial_settings.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import SessionLocal, User, ExpenseCategory

def render(db: Session, user: User, is_mobile: bool):
    st.header("⚙️ Financial Settings")
    st.write("Define your expense categories. These will be used to classify your spending on the Transaction Ledger and in reports.")

    st.subheader("Expense Categories")
    st.info("Add, rename, or delete your expense categories here (e.g., 'Materials', 'Stationary', 'Phones', 'Advertising', 'Light & Heat', 'Rent & Rates', 'Misc', 'Capital').")

    categories_db = db.query(ExpenseCategory).filter(ExpenseCategory.user_id == user.id).order_by(ExpenseCategory.name).all()
    
    data_for_editor = [{"ID": cat.id, "Category Name": cat.name, "Description": cat.description} for cat in categories_db]
    df_for_editor = pd.DataFrame(data_for_editor)

    edited_df = st.data_editor(
        df_for_editor,
        num_rows="dynamic",
        key="expense_categories_editor",
        column_config={
            "ID": None,
            "Category Name": st.column_config.TextColumn("Category Name*", required=True),
            "Description": st.column_config.TextColumn("Description"),
        },
        use_container_width=True,
        hide_index=True
    )

    if st.button("Save Category Changes", type="primary"):
        with SessionLocal() as transaction_db:
            try:
                # Simple brute-force sync: delete all and re-add.
                transaction_db.query(ExpenseCategory).filter(ExpenseCategory.user_id == user.id).delete(synchronize_session=False)
                
                all_cat_names = set()
                for _, row in edited_df.iterrows():
                    name_val = row.get("Category Name")
                    if name_val and str(name_val).strip():
                        clean_name = str(name_val).strip()
                        if clean_name not in all_cat_names:
                            new_cat = ExpenseCategory(
                                user_id=user.id, 
                                name=clean_name,
                                description=row.get("Description")
                            )
                            transaction_db.add(new_cat)
                            all_cat_names.add(clean_name)
                
                transaction_db.commit()
                st.success("Expense categories saved successfully!")
            except IntegrityError:
                transaction_db.rollback()
                st.error("Save failed. Category names must be unique.")
            except Exception as e:
                transaction_db.rollback()
                st.error(f"An error occurred: {e}")
        st.rerun()
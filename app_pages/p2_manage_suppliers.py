# app_pages/p2_manage_suppliers.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import get_db, User, Supplier

# --- Page-specific content ---
def render(db: Session, user: User, is_mobile: bool):
    st.header("🏢 Manage Suppliers")
    st.write("Add, edit, or delete your inventory item and material suppliers.")

    suppliers_db = db.query(Supplier).filter(Supplier.user_id == user.id).order_by(Supplier.name).all()
    
    data_for_editor = [
        {"ID": sup.id, "Supplier Name": sup.name, "Email": sup.contact_email, "Website": sup.website_url, "Phone": sup.phone_number, "Address": sup.address} 
        for sup in suppliers_db
    ]
    
    df_cols = ["ID", "Supplier Name", "Email", "Website", "Phone", "Address"]
    df_for_editor = pd.DataFrame(data_for_editor, columns=df_cols)

    #st.info("To delete a supplier, remove its row using the trash can icon and click save.", icon="🗑️")

    edited_df = st.data_editor(
        df_for_editor, num_rows="dynamic", key="suppliers_editor",
        column_config={
            "ID": None, "Supplier Name": st.column_config.TextColumn("Supplier Name*", required=True),
            "Email": st.column_config.TextColumn("Contact Email"), "Website": st.column_config.LinkColumn("Website URL"),
            "Phone": st.column_config.TextColumn("Phone Number"), "Address": st.column_config.TextColumn("Address", width="large")
        },
        use_container_width=True, hide_index=True, column_order=("Supplier Name", "Email", "Website", "Phone", "Address")
    )

    if st.button("Save Supplier Changes", type="primary"):
        try:
            original_ids = set(df_for_editor['ID'].dropna().astype(int))
            edited_ids = set(edited_df['ID'].dropna().astype(int))
            
            ids_to_delete = original_ids - edited_ids
            if ids_to_delete:
                db.query(Supplier).filter(Supplier.id.in_(ids_to_delete), Supplier.user_id == user.id).delete(synchronize_session=False)

            for index, row in edited_df.iterrows():
                sup_id = int(row['ID']) if pd.notna(row['ID']) else None
                name = row["Supplier Name"]
                if not name or not str(name).strip(): continue

                if sup_id:
                    item_to_update = db.query(Supplier).filter(Supplier.id == sup_id, Supplier.user_id == user.id).first()
                    if item_to_update:
                        item_to_update.name, item_to_update.contact_email = name, row["Email"]
                        item_to_update.website_url, item_to_update.phone_number = row["Website"], row["Phone"]
                        item_to_update.address = row["Address"]
                else:
                    new_supplier = Supplier(
                        user_id=user.id, name=name, contact_email=row["Email"],
                        website_url=row["Website"], phone_number=row["Phone"], address=row["Address"]
                    )
                    db.add(new_supplier)
            
            db.commit()
            st.success("Supplier changes saved successfully!")
            st.rerun()
        except Exception as e:
            db.rollback()
            st.error(f"An error occurred: {e}")
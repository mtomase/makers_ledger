# app_pages/p1b_manage_inventoryitem_types.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import SessionLocal, User, InventoryItemType

def render(db: Session, user: User, is_mobile: bool):
    st.header("🏷️ Manage Inventory Item Types")
    st.write("Define the categories for your inventory items (e.g., Oil, Additive, Packaging). These will be used as dropdown options on the 'Manage Inventory' page.")

    item_types_db = db.query(InventoryItemType).filter(InventoryItemType.user_id == user.id).order_by(InventoryItemType.name).all()
    
    data_for_editor = [{"ID": t.id, "Type Name": t.name} for t in item_types_db]
    df_for_editor = pd.DataFrame(data_for_editor)

    edited_df = st.data_editor(
        df_for_editor,
        num_rows="dynamic",
        key="inventoryitem_types_editor",
        column_config={
            "ID": None,
            "Type Name": st.column_config.TextColumn("Type Name*", required=True),
        },
        use_container_width=True,
        hide_index=True
    )

    if st.button("Save Type Changes", type="primary"):
        with SessionLocal() as transaction_db:
            try:
                ui_type_names = set()
                for _, row in edited_df.iterrows():
                    name_val = row.get("Type Name")
                    if name_val and str(name_val).strip():
                        clean_name = str(name_val).strip()
                        if clean_name in ui_type_names:
                            raise ValueError(f"The name '{clean_name}' is duplicated in your list.")
                        ui_type_names.add(clean_name)

                db_types = {t.name: t for t in transaction_db.query(InventoryItemType).filter(InventoryItemType.user_id == user.id).all()}
                db_type_names = set(db_types.keys())

                names_to_add = ui_type_names - db_type_names
                names_to_delete = db_type_names - ui_type_names

                for name in names_to_delete:
                    transaction_db.delete(db_types[name])

                for name in names_to_add:
                    transaction_db.add(InventoryItemType(user_id=user.id, name=name))
                
                transaction_db.commit()
                st.success("Inventory Item Types saved successfully!")

            except ValueError as e:
                transaction_db.rollback()
                st.error(f"Save failed: {e}")
            except IntegrityError as e:
                transaction_db.rollback()
                error_info = str(e.orig).lower()
                if 'foreign key' in error_info:
                    st.error("Save failed. You cannot delete a type that is currently in use by an inventory item. Please update your inventory items before deleting this type.")
                elif 'unique constraint' in error_info or 'duplicate key' in error_info:
                    st.error("Save failed. Type names must be unique.")
                else:
                    st.error(f"An unexpected database error occurred: {e}")
            except Exception as e:
                transaction_db.rollback()
                st.error(f"An error occurred: {e}")
        st.rerun()
# app_pages/p1b_manage_inventoryitem_types.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import SessionLocal, User, IngredientType

def render(db: Session, user: User, is_mobile: bool):
    """
    This is the function that main_app.py calls to render this page.
    """
    st.header("🏷️ Manage Inventory Item Types")
    st.write("Define the categories for your inventoryitems (e.g., Oil, Additive, Lye). These will be used as dropdown options on the 'Manage Ingredients' page.")

    types_db = db.query(IngredientType).filter(IngredientType.user_id == user.id).order_by(IngredientType.name).all()
    
    data_for_editor = [{"ID": t.id, "Type Name": t.name} for t in types_db]
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
                # --- NEW: Intelligent Sync Logic ---

                # 1. Get desired state from the UI, checking for duplicates first.
                ui_type_names = set()
                for _, row in edited_df.iterrows():
                    name_val = row.get("Type Name")
                    if name_val and str(name_val).strip():
                        clean_name = str(name_val).strip()
                        if clean_name in ui_type_names:
                            raise ValueError(f"The name '{clean_name}' is duplicated in your list.")
                        ui_type_names.add(clean_name)

                # 2. Get current state from the database.
                db_types = {t.name: t for t in transaction_db.query(IngredientType).filter(IngredientType.user_id == user.id).all()}
                db_type_names = set(db_types.keys())

                # 3. Determine what to add and what to delete.
                names_to_add = ui_type_names - db_type_names
                names_to_delete = db_type_names - ui_type_names

                # 4. Perform deletions.
                for name in names_to_delete:
                    transaction_db.delete(db_types[name])

                # 5. Perform additions.
                for name in names_to_add:
                    transaction_db.add(IngredientType(user_id=user.id, name=name))
                
                # 6. Commit all changes.
                transaction_db.commit()
                st.success("Ingredient types saved successfully!")

            except ValueError as e:
                # Catches the duplicate check from step 1.
                transaction_db.rollback()
                st.error(f"Save failed: {e}")
            except IntegrityError as e:
                # --- NEW: Better error message for IntegrityError ---
                transaction_db.rollback()
                error_info = str(e.orig).lower()
                if 'foreign key' in error_info:
                    st.error("Save failed. You cannot delete a type that is currently in use by an inventoryitem. Please update your inventoryitems before deleting this type.")
                elif 'unique constraint' in error_info or 'duplicate key' in error_info:
                    st.error("Save failed. Type names must be unique.")
                else:
                    st.error(f"An unexpected database error occurred: {e}")
            except Exception as e:
                transaction_db.rollback()
                st.error(f"An error occurred: {e}")
        st.rerun()
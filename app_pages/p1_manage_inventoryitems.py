# app_pages/p1_manage_inventoryitems.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import SessionLocal, User, Ingredient, IngredientType

def render(db: Session, user: User, is_mobile: bool):
    st.header("🌿 Manage Ingredients")
    st.write("Define your inventoryitems, their INCI names for compliance, and their types. Costing is now handled via the Stock Management page.")

    # --- MODIFIED: Fetch dynamic inventory item types ---
    inventoryitem_types_db = db.query(IngredientType).filter(IngredientType.user_id == user.id).order_by(IngredientType.name).all()
    type_options = [t.name for t in inventoryitem_types_db]

    if not type_options:
        st.warning("Please define at least one 'Ingredient Type' on the 'Manage Inventory Item Types' page before adding inventoryitems.")
        return

    # --- MODIFIED: Eager load the inventoryitem_type_ref ---
    inventoryitems_db = db.query(Ingredient).options(joinedload(Ingredient.inventoryitem_type_ref)).filter(Ingredient.user_id == user.id).order_by(Ingredient.name).all()

    # --- MODIFIED: Added INCI Name and changed Type handling ---
    data_for_editor = [
        {
            "ID": ing.id, 
            "Ingredient Name": ing.name, 
            "INCI Name": ing.inci_name,
            "Type": ing.inventoryitem_type_ref.name if ing.inventoryitem_type_ref else None, 
            "Description": ing.description, 
            "Reorder Point (g)": ing.reorder_threshold_grams
        } 
        for ing in inventoryitems_db
    ]
    
    edited_df = st.data_editor(
        pd.DataFrame(data_for_editor), 
        num_rows="dynamic", 
        key="inventoryitems_editor",
        column_config={
            "ID": None,
            "Ingredient Name": st.column_config.TextColumn("Ingredient Name*", required=True),
            "INCI Name": st.column_config.TextColumn("INCI Name (for cosmetics)"),
            "Type": st.column_config.SelectboxColumn("Type*", options=type_options, required=True),
            "Description": st.column_config.TextColumn("Description", width="large"),
            "Reorder Point (g)": st.column_config.NumberColumn("Reorder Point (g)", min_value=0, format="%d")
        },
        use_container_width=True, 
        hide_index=True,
        column_order=("Ingredient Name", "INCI Name", "Type", "Description", "Reorder Point (g)")
    )

    if st.button("Save Inventory Item Changes", type="primary"):
        with SessionLocal() as transaction_db:
            try:
                original_ids = set(d['ID'] for d in data_for_editor if d['ID'] is not None)
                edited_ids = set(edited_df['ID'].dropna().astype(int))

                ids_to_delete = original_ids - edited_ids
                if ids_to_delete:
                    transaction_db.query(Ingredient).filter(Ingredient.id.in_(ids_to_delete), Ingredient.user_id == user.id).delete(synchronize_session=False)

                type_map = {t.name: t.id for t in inventoryitem_types_db}

                for _, row in edited_df.iterrows():
                    ing_id = int(row['ID']) if pd.notna(row['ID']) else None
                    name = row["Ingredient Name"]
                    ing_type_name = row["Type"]
                    
                    if not name or not str(name).strip() or not ing_type_name: continue
                    
                    type_id = type_map.get(ing_type_name)
                    if not type_id:
                        st.error(f"Type '{ing_type_name}' is not valid. Skipping row for inventory item '{name}'.")
                        continue

                    data_dict = {
                        "name": name.strip(),
                        "inci_name": row["INCI Name"].strip() if pd.notna(row["INCI Name"]) and row["INCI Name"] else None,
                        "inventoryitem_type_id": type_id,
                        "description": row["Description"].strip() if pd.notna(row["Description"]) and row["Description"] else None,
                        "reorder_threshold_grams": Decimal(str(row["Reorder Point (g)"])) if pd.notna(row["Reorder Point (g)"]) else None
                    }

                    if ing_id:
                        if ing_id not in ids_to_delete:
                            transaction_db.query(Ingredient).filter(Ingredient.id == ing_id, Ingredient.user_id == user.id).update(data_dict)
                    else:
                        new_inventoryitem = Ingredient(user_id=user.id, **data_dict)
                        transaction_db.add(new_inventoryitem)
                
                transaction_db.commit()
                st.success("Ingredient changes saved successfully!")
            except IntegrityError:
                transaction_db.rollback()
                st.error("Save failed. Inventory Item names must be unique.")
            except Exception as e:
                transaction_db.rollback()
                st.error(f"An error occurred: {e}")
        st.rerun()
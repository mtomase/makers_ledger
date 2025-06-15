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
from models import SessionLocal, User, InventoryItem, InventoryItemType

def render(db: Session, user: User, is_mobile: bool):
    st.header("🌿 Manage Inventory Items")
    st.write("Define all your stock items here, including raw materials, packaging, and any other consumables. Their types and reorder points can also be set.")

    item_types_db = db.query(InventoryItemType).filter(InventoryItemType.user_id == user.id).order_by(InventoryItemType.name).all()
    type_options = [t.name for t in item_types_db]

    if not type_options:
        st.warning("Please define at least one 'Item Type' on the 'Manage Inventory Item Types' page before adding inventory items.")
        return

    inventory_items_db = db.query(InventoryItem).options(joinedload(InventoryItem.inventoryitem_type_ref)).filter(InventoryItem.user_id == user.id).order_by(InventoryItem.name).all()

    data_for_editor = [
        {
            "ID": item.id, 
            "Item Name": item.name, 
            "INCI Name": item.inci_name,
            "Type": item.inventoryitem_type_ref.name if item.inventoryitem_type_ref else None, 
            "Description": item.description, 
            "Reorder Point": item.reorder_threshold_grams
        } 
        for item in inventory_items_db
    ]
    
    edited_df = st.data_editor(
        pd.DataFrame(data_for_editor), 
        num_rows="dynamic", 
        key="inventoryitems_editor",
        column_config={
            "ID": None,
            "Item Name": st.column_config.TextColumn("Item Name*", required=True),
            "INCI Name": st.column_config.TextColumn("INCI Name (for cosmetic ingredients)"),
            "Type": st.column_config.SelectboxColumn("Type*", options=type_options, required=True),
            "Description": st.column_config.TextColumn("Description", width="large"),
            "Reorder Point": st.column_config.NumberColumn("Reorder Point (units or g)", help="Set a threshold to get a low stock warning.", min_value=0, format="%d")
        },
        use_container_width=True, 
        hide_index=True,
        column_order=("Item Name", "INCI Name", "Type", "Description", "Reorder Point")
    )

    if st.button("Save Inventory Item Changes", type="primary"):
        with SessionLocal() as transaction_db:
            try:
                original_ids = set(d['ID'] for d in data_for_editor if d['ID'] is not None)
                edited_ids = set(edited_df['ID'].dropna().astype(int))

                ids_to_delete = original_ids - edited_ids
                if ids_to_delete:
                    transaction_db.query(InventoryItem).filter(InventoryItem.id.in_(ids_to_delete), InventoryItem.user_id == user.id).delete(synchronize_session=False)

                type_map = {t.name: t.id for t in item_types_db}

                for _, row in edited_df.iterrows():
                    item_id = int(row['ID']) if pd.notna(row['ID']) else None
                    name = row["Item Name"]
                    item_type_name = row["Type"]
                    
                    if not name or not str(name).strip() or not item_type_name: continue
                    
                    type_id = type_map.get(item_type_name)
                    if not type_id:
                        st.error(f"Type '{item_type_name}' is not valid. Skipping row for item '{name}'.")
                        continue

                    data_dict = {
                        "name": name.strip(),
                        "inci_name": row["INCI Name"].strip() if pd.notna(row["INCI Name"]) and row["INCI Name"] else None,
                        "inventoryitem_type_id": type_id,
                        "description": row["Description"].strip() if pd.notna(row["Description"]) and row["Description"] else None,
                        "reorder_threshold_grams": Decimal(str(row["Reorder Point"])) if pd.notna(row["Reorder Point"]) else None
                    }

                    if item_id:
                        if item_id not in ids_to_delete:
                            transaction_db.query(InventoryItem).filter(InventoryItem.id == item_id, InventoryItem.user_id == user.id).update(data_dict)
                    else:
                        new_inventoryitem = InventoryItem(user_id=user.id, **data_dict)
                        transaction_db.add(new_inventoryitem)
                
                transaction_db.commit()
                st.success("Inventory item changes saved successfully!")
            except IntegrityError:
                transaction_db.rollback()
                st.error("Save failed. Inventory Item names must be unique.")
            except Exception as e:
                transaction_db.rollback()
                st.error(f"An error occurred: {e}")
        st.rerun()
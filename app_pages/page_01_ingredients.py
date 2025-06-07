# pages/page_01_ingredients.py
import streamlit as st
import pandas as pd
from decimal import Decimal
from sqlalchemy.orm import Session
from models import Ingredient, User

def render(db: Session, user: User, is_mobile: bool):
    st.header("📝 Manage Ingredients")
    st.write("Edit, add, or delete ingredients. Click **'Save Ingredient Changes'** to persist.")
    
    ingredients_db = db.query(Ingredient).filter(Ingredient.user_id == user.id).order_by(Ingredient.id).all()
    data_for_editor_ing = [{"ID": ing.id, "Name": ing.name, "Provider": ing.provider, "Price/Unit (€)": ing.price_per_unit, "Unit (kg)": ing.unit_quantity_kg, "Price URL": ing.price_url if ing.price_url else ""} for ing in ingredients_db]
    df_ing_cols = ["ID", "Name", "Provider", "Price/Unit (€)", "Unit (kg)", "Price URL"]
    df_ingredients_for_editor = pd.DataFrame(data_for_editor_ing, columns=df_ing_cols)
    if df_ingredients_for_editor.empty:
         df_ingredients_for_editor = pd.DataFrame(columns=df_ing_cols).astype({"ID": "float64", "Name": "object", "Provider": "object", "Price/Unit (€)": "float64", "Unit (kg)": "float64", "Price URL": "object"})
    
    snapshot_key_ing = 'df_ingredients_snapshot'
    if snapshot_key_ing not in st.session_state or not isinstance(st.session_state.get(snapshot_key_ing), pd.DataFrame) or not st.session_state[snapshot_key_ing].columns.equals(df_ingredients_for_editor.columns):
        st.session_state[snapshot_key_ing] = df_ingredients_for_editor.copy()

    ing_display_columns_desktop = ("Name", "Provider", "Price/Unit (€)", "Unit (kg)", "Price URL")
    ing_display_columns_mobile = ("Name", "Price/Unit (€)", "Unit (kg)") 
    ing_columns_to_display = ing_display_columns_mobile if is_mobile else ing_display_columns_desktop
    
    edited_df_ing = st.data_editor(
        st.session_state[snapshot_key_ing], num_rows="dynamic", key="ingredients_editor",
        column_order=ing_columns_to_display, 
        column_config={
            "Name": st.column_config.TextColumn("Ingredient Name*", required=True, help="The common name of the ingredient."),
            "Provider": st.column_config.TextColumn("Provider (Optional)", help="Supplier or source of the ingredient."), 
            "Price/Unit (€)": st.column_config.NumberColumn("Price per Unit (€)*", required=True, min_value=0.00, step=0.01, format="%.2f", help="Cost for the quantity specified in 'Unit (kg)'."),
            "Unit (kg)": st.column_config.NumberColumn("Unit Quantity (kg)*", required=True, min_value=0.001, step=0.001, format="%.3f", help="The amount in kilograms this price refers to (e.g., 1 for 1kg, 0.5 for 500g)."),
            "Price URL": st.column_config.LinkColumn("Price URL (Optional)", help="Web link to the ingredient's source or price information.")
        },
        use_container_width=True, hide_index=True
    )
    if st.button("Save Ingredient Changes", type="primary"):
        try:
            original_df_snapshot_ing = st.session_state[snapshot_key_ing]; original_snapshot_ids_ing = set(original_df_snapshot_ing['ID'].dropna().astype(int))
            edited_df_ids_ing = set(edited_df_ing['ID'].dropna().astype(int)); ids_to_delete_from_db_ing = original_snapshot_ids_ing - edited_df_ids_ing
            for ing_id_del in ids_to_delete_from_db_ing:
                ing_to_del = db.query(Ingredient).filter(Ingredient.id == ing_id_del, Ingredient.user_id == user.id).first()
                if ing_to_del: db.delete(ing_to_del); st.toast(f"Deleted ID: {ing_id_del}", icon="➖")
            for index, row in edited_df_ing.iterrows():
                ing_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None; name_val, prov_val = row.get("Name"), row.get("Provider")
                price_val, unit_kg_val = row.get("Price/Unit (€)"), row.get("Unit (kg)")
                if not all([name_val, pd.notna(price_val), pd.notna(unit_kg_val)]): 
                    if ing_id is None and not any([name_val, prov_val, pd.notna(price_val), pd.notna(unit_kg_val)]): continue 
                    st.error(f"Row {index+1}: Name, Price/Unit, Unit (kg) are required. Skipping."); continue
                prov_val = str(prov_val).strip() if prov_val and str(prov_val).strip() else None; url_val = str(row.get("Price URL", "")).strip() if row.get("Price URL") and str(row.get("Price URL", "")).strip() else None
                if ing_id: 
                    item_to_update = db.query(Ingredient).filter(Ingredient.id == ing_id, Ingredient.user_id == user.id).first()
                    if item_to_update:
                        changed = False
                        if item_to_update.name != name_val: item_to_update.name = name_val; changed=True
                        if item_to_update.provider != prov_val: item_to_update.provider = prov_val; changed=True
                        if item_to_update.price_per_unit != Decimal(str(price_val)): item_to_update.price_per_unit = Decimal(str(price_val)); changed=True 
                        if item_to_update.unit_quantity_kg != Decimal(str(unit_kg_val)): item_to_update.unit_quantity_kg = Decimal(str(unit_kg_val)); changed=True 
                        if item_to_update.price_url != url_val: item_to_update.price_url = url_val; changed=True
                        if changed: st.toast(f"Updated ID: {ing_id}", icon="🔄")
            new_rows_df = edited_df_ing[edited_df_ing['ID'].isna()]
            for index, row in new_rows_df.iterrows():
                name_val, prov_val = row.get("Name"), row.get("Provider"); price_val, unit_kg_val = row.get("Price/Unit (€)"), row.get("Unit (kg)")
                if not all([name_val, pd.notna(price_val), pd.notna(unit_kg_val)]): 
                    if not any([name_val, prov_val, pd.notna(price_val), pd.notna(unit_kg_val)]): continue
                    st.error(f"New Row (approx original index {index+1}): Name, Price/Unit, Unit (kg) are required. Skipping."); continue
                prov_val = str(prov_val).strip() if prov_val and str(prov_val).strip() else None; url_val = str(row.get("Price URL", "")).strip() if row.get("Price URL") and str(row.get("Price URL", "")).strip() else None
                db.add(Ingredient(user_id=user.id, name=name_val, provider=prov_val, price_per_unit=Decimal(str(price_val)), unit_quantity_kg=Decimal(str(unit_kg_val)), price_url=url_val))
                st.toast(f"Added: {name_val}", icon="➕")
            db.commit(); st.success("Ingredient changes saved!"); st.session_state[snapshot_key_ing] = edited_df_ing.copy(); st.rerun()
        except Exception as e_save_ing: db.rollback(); st.error(f"Error saving ingredients: {e_save_ing}"); st.exception(e_save_ing)
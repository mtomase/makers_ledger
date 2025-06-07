# app_pages/page_08_stock_management.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from decimal import Decimal
import datetime

from models import User, Ingredient, StockAddition
from utils.db_helpers import create_ingredient_display_string

def render(db: Session, user: User, is_mobile: bool):
    st.header("📦 Ingredient Stock Management")
    st.write("View current stock levels, set reorder points, and record new stock purchases.")

    # --- Section 1: Stock Level Overview & Reorder Point Editor ---
    st.subheader("Current Stock Levels")
    
    ingredients = db.query(Ingredient).filter(Ingredient.user_id == user.id).order_by(Ingredient.name).all()
    if not ingredients:
        st.info("No ingredients found. Please add some in the 'Manage Ingredients' page first.")
        return

    # Prepare data for the editor
    stock_data = []
    for ing in ingredients:
        stock_data.append({
            "ID": ing.id,
            "Ingredient": ing.name,
            "Provider": ing.provider or "-",
            "Current Stock (g)": ing.current_stock_grams,
            "Reorder Threshold (g)": ing.reorder_threshold_grams
        })
    
    stock_df = pd.DataFrame(stock_data)
    
    edited_stock_df = st.data_editor(
        stock_df,
        key="stock_overview_editor",
        column_config={
            "ID": None, # Hide the ID column
            "Ingredient": st.column_config.TextColumn("Ingredient", disabled=True),
            "Provider": st.column_config.TextColumn("Provider", disabled=True),
            "Current Stock (g)": st.column_config.NumberColumn("Current Stock (g)", disabled=True, format="%.2f g"),
            "Reorder Threshold (g)": st.column_config.NumberColumn("Reorder Threshold (g)", min_value=0, format="%d g", help="Set a value to receive future reorder alerts.")
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed"
    )

    if st.button("Save Reorder Thresholds", type="primary"):
        try:
            for index, row in edited_stock_df.iterrows():
                ing_id = row["ID"]
                new_threshold = row["Reorder Threshold (g)"]
                
                ingredient_to_update = db.query(Ingredient).filter(Ingredient.id == ing_id, Ingredient.user_id == user.id).first()
                if ingredient_to_update:
                    # Only update if the value has changed
                    if ingredient_to_update.reorder_threshold_grams != (Decimal(str(new_threshold)) if new_threshold is not None else None):
                        ingredient_to_update.reorder_threshold_grams = Decimal(str(new_threshold)) if new_threshold is not None else None
                        st.toast(f"Updated reorder point for {ingredient_to_update.name}", icon="🔄")
            db.commit()
            st.success("Reorder thresholds saved successfully!")
            st.rerun()
        except Exception as e:
            db.rollback()
            st.error(f"An error occurred while saving reorder points: {e}")

    st.markdown("---")

    # --- Section 2: Record a New Stock Purchase ---
    st.subheader("Record a New Stock Purchase")
    
    # Create display names for the selectbox
    ingredient_options = {create_ingredient_display_string(ing.name, ing.provider): ing.id for ing in ingredients}
    
    with st.form(key="add_stock_form"):
        selected_ing_display = st.selectbox(
            "Select Ingredient",
            options=list(ingredient_options.keys()),
            index=0,
            help="Choose the ingredient you have purchased."
        )
        
        col1, col2 = st.columns(2)
        with col1:
            quantity_added = st.number_input("Quantity Added (grams)", min_value=0.01, format="%.2f", step=10.0)
        with col2:
            cost_of_addition = st.number_input("Total Cost of Purchase (€)", min_value=0.00, format="%.2f")
        
        purchase_date = st.date_input("Purchase Date", value=datetime.date.today())
        supplier_info = st.text_input("Supplier / Invoice Info (Optional)", placeholder="e.g., Supplier X - Invoice #12345")

        submitted = st.form_submit_button("Add Stock to Inventory", type="primary")

        if submitted:
            if not selected_ing_display or quantity_added <= 0:
                st.warning("Please select an ingredient and enter a valid quantity.")
            else:
                try:
                    selected_ing_id = ingredient_options[selected_ing_display]
                    
                    # 1. Find the ingredient to update its stock
                    ingredient_to_update = db.query(Ingredient).filter(Ingredient.id == selected_ing_id, Ingredient.user_id == user.id).first()
                    
                    if ingredient_to_update:
                        # 2. Create the ledger entry in StockAddition
                        new_stock_addition = StockAddition(
                            user_id=user.id,
                            ingredient_id=selected_ing_id,
                            quantity_added_grams=Decimal(str(quantity_added)),
                            purchase_date=purchase_date,
                            cost_of_addition=Decimal(str(cost_of_addition)),
                            supplier_info=supplier_info
                        )
                        db.add(new_stock_addition)
                        
                        # 3. Update the current stock level on the Ingredient itself
                        ingredient_to_update.current_stock_grams += Decimal(str(quantity_added))
                        
                        db.commit()
                        st.success(f"Successfully added {quantity_added}g of {ingredient_to_update.name} to your inventory!")
                        st.rerun()
                    else:
                        st.error("Could not find the selected ingredient. Please refresh.")
                except Exception as e:
                    db.rollback()
                    st.error(f"An error occurred: {e}")
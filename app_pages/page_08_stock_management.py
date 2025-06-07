# app_pages/page_08_stock_management.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session, joinedload
from decimal import Decimal
import datetime

from models import User, Ingredient, StockAddition
from utils.db_helpers import create_ingredient_display_string

def render(db: Session, user: User, is_mobile: bool):
    st.header("📦 Ingredient Stock Management")
    st.write("View current stock levels, set reorder points, and record new stock purchases.")

    # --- Section 1: Stock Level Overview & Reorder Point Editor ---
    st.subheader("Current Stock Levels")
    
    # Eagerly load the stock_additions relationship to prevent lazy loading later
    ingredients = db.query(Ingredient).options(joinedload(Ingredient.stock_additions)).filter(Ingredient.user_id == user.id).order_by(Ingredient.name).all()
    if not ingredients:
        st.info("No ingredients found. Please add some in the 'Manage Ingredients' page first.")
        return

    # Prepare data for the editor
    stock_data = []
    for ing in ingredients:
        # --- NEW: Low Stock Logic ---
        is_low_stock = False
        if ing.reorder_threshold_grams is not None and ing.current_stock_grams <= ing.reorder_threshold_grams:
            is_low_stock = True
        
        stock_data.append({
            "ID": ing.id,
            "Ingredient": f"⚠️ {ing.name}" if is_low_stock else ing.name, # Add visual indicator
            "Provider": ing.provider or "-",
            "Current Stock (g)": ing.current_stock_grams,
            "Reorder Threshold (g)": ing.reorder_threshold_grams,
            "_is_low_stock": is_low_stock # Hidden column for styling
        })
    
    stock_df = pd.DataFrame(stock_data)

    # --- NEW: Styling for Low Stock ---
    def highlight_low_stock(row):
        return ['background-color: #FFD2D2; color: #D8000C;' if row._is_low_stock else '' for _ in row]

    st.dataframe(
        stock_df.style.apply(highlight_low_stock, axis=1),
        column_config={
            "ID": None,
            "_is_low_stock": None, # Hide the helper column
            "Ingredient": st.column_config.TextColumn("Ingredient"),
            "Provider": st.column_config.TextColumn("Provider"),
            "Current Stock (g)": st.column_config.NumberColumn("Current Stock (g)", format="%.2f g"),
            "Reorder Threshold (g)": st.column_config.NumberColumn("Reorder Threshold (g)", format="%d g")
        },
        use_container_width=True,
        hide_index=True,
    )
    
    st.markdown("---")
    
    # --- Section 2: Edit Reorder Thresholds & Record Purchases ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("✍️ Edit Reorder Thresholds")
        with st.form("reorder_form"):
            # Use a dictionary for easier lookup
            ingredient_thresholds = {ing.id: ing.reorder_threshold_grams for ing in ingredients}
            
            for ing_id, current_threshold in ingredient_thresholds.items():
                ing_obj = next((ing for ing in ingredients if ing.id == ing_id), None)
                if ing_obj:
                    new_val = st.number_input(
                        f"{ing_obj.name} (g)", 
                        min_value=0, 
                        value=int(current_threshold) if current_threshold is not None else 0,
                        key=f"reorder_{ing_id}"
                    )
                    ingredient_thresholds[ing_id] = new_val

            submitted_reorder = st.form_submit_button("Save Reorder Thresholds", type="primary")
            if submitted_reorder:
                try:
                    for ing_id, new_threshold in ingredient_thresholds.items():
                        ing_to_update = db.query(Ingredient).filter(Ingredient.id == ing_id).first()
                        if ing_to_update:
                            ing_to_update.reorder_threshold_grams = Decimal(str(new_threshold)) if new_threshold > 0 else None
                    db.commit()
                    st.success("Reorder thresholds saved!")
                    st.rerun()
                except Exception as e:
                    db.rollback()
                    st.error(f"Error saving thresholds: {e}")


    with col2:
        st.subheader("➕ Record New Stock Purchase")
        ingredient_options = {create_ingredient_display_string(ing.name, ing.provider): ing.id for ing in ingredients}
        
        with st.form(key="add_stock_form"):
            selected_ing_display = st.selectbox("Select Ingredient", options=list(ingredient_options.keys()), index=0)
            
            form_col1, form_col2 = st.columns(2)
            with form_col1:
                quantity_added = st.number_input("Quantity Added (grams)", min_value=0.01, format="%.2f", step=10.0)
            with form_col2:
                cost_of_addition = st.number_input("Total Cost of Purchase (€)", min_value=0.00, format="%.2f")
            
            purchase_date = st.date_input("Purchase Date", value=datetime.date.today())
            supplier_info = st.text_input("Supplier / Invoice Info (Optional)", placeholder="e.g., Supplier X - Invoice #12345")

            submitted_add = st.form_submit_button("Add Stock to Inventory", type="primary")

            if submitted_add:
                if not selected_ing_display or quantity_added <= 0:
                    st.warning("Please select an ingredient and enter a valid quantity.")
                else:
                    try:
                        selected_ing_id = ingredient_options[selected_ing_display]
                        ingredient_to_update = db.query(Ingredient).filter(Ingredient.id == selected_ing_id).first()
                        
                        if ingredient_to_update:
                            new_stock_addition = StockAddition(
                                user_id=user.id,
                                ingredient_id=selected_ing_id,
                                quantity_added_grams=Decimal(str(quantity_added)),
                                purchase_date=purchase_date,
                                cost_of_addition=Decimal(str(cost_of_addition)),
                                supplier_info=supplier_info
                            )
                            db.add(new_stock_addition)
                            ingredient_to_update.current_stock_grams += Decimal(str(quantity_added))
                            
                            db.commit()
                            st.success(f"Successfully added {quantity_added}g of {ingredient_to_update.name} to inventory!")
                            st.rerun()
                        else:
                            st.error("Could not find the selected ingredient.")
                    except Exception as e:
                        db.rollback()
                        st.error(f"An error occurred: {e}")

    st.markdown("---")

    # --- NEW Section 3: Purchase History Viewer ---
    st.subheader("📜 Purchase History")
    
    history_ing_display = st.selectbox(
        "Select an ingredient to view its purchase history",
        options=list(ingredient_options.keys()),
        index=None,
        placeholder="Choose an ingredient..."
    )

    if history_ing_display:
        history_ing_id = ingredient_options[history_ing_display]
        selected_ingredient = next((ing for ing in ingredients if ing.id == history_ing_id), None)

        if selected_ingredient and selected_ingredient.stock_additions:
            history_data = [
                {
                    "Purchase Date": sa.purchase_date.strftime("%Y-%m-%d"),
                    "Quantity Added (g)": sa.quantity_added_grams,
                    "Total Cost (€)": sa.cost_of_addition,
                    "Supplier/Info": sa.supplier_info or "-"
                }
                for sa in sorted(selected_ingredient.stock_additions, key=lambda x: x.purchase_date, reverse=True)
            ]
            history_df = pd.DataFrame(history_data)
            st.dataframe(history_df, use_container_width=True, hide_index=True)
        else:
            st.info("No purchase history found for this ingredient.")
# app_pages/p7_stock_management.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
import datetime
import sys
import os
import pathlib

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import SessionLocal, User, Ingredient, Supplier, StockAddition, PurchaseOrder, PurchaseDocument

def initialize_state():
    if 'purchase_view_state' not in st.session_state:
        st.session_state.purchase_view_state = 'list'
    if 'purchase_to_edit_id' not in st.session_state:
        st.session_state.purchase_to_edit_id = None
    if 'show_cancel_confirm_po' not in st.session_state:
        st.session_state.show_cancel_confirm_po = False
    if 'show_delete_confirm_po' not in st.session_state:
        st.session_state.show_delete_confirm_po = False

def get_inventory_data(db: Session, user_id: int):
    stock_levels_sq = db.query(
        StockAddition.ingredient_id,
        func.sum(StockAddition.quantity_remaining_grams).label('current_stock')
    ).join(PurchaseOrder).where(PurchaseOrder.user_id == user_id).group_by(StockAddition.ingredient_id).subquery()
    results = db.query(Ingredient, stock_levels_sq.c.current_stock).outerjoin(
        stock_levels_sq, Ingredient.id == stock_levels_sq.c.ingredient_id
    ).filter(Ingredient.user_id == user_id).order_by(Ingredient.name).all()
    inventory = []
    for ing, stock in results:
        stock_level = stock or Decimal('0.0')
        additions = db.query(StockAddition).join(PurchaseOrder).filter(StockAddition.ingredient_id == ing.id, PurchaseOrder.user_id == user_id).all()
        total_cost, total_grams = Decimal('0.0'), Decimal('0.0')
        for add in additions:
            po_line_item_count = len(add.purchase_order_ref.line_items)
            shipping_per_item = add.purchase_order_ref.shipping_cost / po_line_item_count if po_line_item_count > 0 else Decimal('0.0')
            total_cost += add.item_cost + shipping_per_item
            total_grams += add.quantity_added_grams
        avg_cost_per_gram = (total_cost / total_grams) if total_grams > 0 else Decimal('0.0')
        is_low_stock = (ing.reorder_threshold_grams is not None and stock_level <= ing.reorder_threshold_grams)
        inventory.append({"id": ing.id, "Ingredient": f"⚠️ {ing.name}" if is_low_stock else ing.name, "name_for_header": ing.name, "Current Stock (g)": stock_level, "Avg. Cost / kg": avg_cost_per_gram * 1000, "_is_low_stock": is_low_stock})
    return inventory

def save_uploaded_files(user_id: int, po_id: int, uploaded_files):
    saved_paths = []
    save_dir = pathlib.Path(f"uploaded_files/{user_id}/{po_id}")
    save_dir.mkdir(parents=True, exist_ok=True)
    for uploaded_file in uploaded_files:
        file_path = save_dir / uploaded_file.name
        with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
        saved_paths.append({"path": str(file_path), "name": uploaded_file.name})
    return saved_paths

def render_purchase_history_list(db: Session, user: User):
    st.subheader("Complete Purchase History")
    all_pos = db.query(PurchaseOrder).options(joinedload(PurchaseOrder.supplier_ref), joinedload(PurchaseOrder.line_items)).filter(PurchaseOrder.user_id == user.id).order_by(PurchaseOrder.order_date.desc()).all()
    if not all_pos:
        st.info("No purchases have been recorded yet."); return
    po_data = [{"id": po.id, "Date": po.order_date, "PO #": po.id, "Supplier": po.supplier_ref.name if po.supplier_ref else "N/A", "Shipping": po.shipping_cost, "VAT": po.total_vat, "Total Cost": sum(item.item_cost for item in po.line_items) + po.shipping_cost} for po in all_pos]
    df = pd.DataFrame(po_data)
    selection = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", column_config={"id": None, "Date": st.column_config.DateColumn(format="YYYY-MM-DD"), "Shipping": st.column_config.NumberColumn(format="€%.2f"), "VAT": st.column_config.NumberColumn(format="€%.2f"), "Total Cost": st.column_config.NumberColumn(format="€%.2f")})
    if selection.selection.rows:
        st.session_state.purchase_to_edit_id = int(df.iloc[selection.selection.rows[0]]['id'])
        st.session_state.purchase_view_state = 'edit'
        st.rerun()

def render_purchase_edit_form(db: Session, user: User):
    po_id = st.session_state.purchase_to_edit_id
    po = db.query(PurchaseOrder).options(joinedload(PurchaseOrder.supplier_ref), joinedload(PurchaseOrder.line_items).joinedload(StockAddition.ingredient_ref), joinedload(PurchaseOrder.documents)).filter(PurchaseOrder.id == po_id, PurchaseOrder.user_id == user.id).first()
    if not po:
        st.error("Purchase Order not found."); st.session_state.purchase_view_state = 'list'; st.rerun(); return

    if st.session_state.show_cancel_confirm_po:
        with st.container(border=True):
            st.warning("Are you sure you want to cancel? All unsaved changes will be lost.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Cancel", use_container_width=True, key="confirm_cancel_po"):
                st.session_state.show_cancel_confirm_po = False
                st.session_state.purchase_view_state = 'list'
                st.rerun()
            if c2.button("No, Keep Editing", use_container_width=True, key="keep_editing_po"):
                st.session_state.show_cancel_confirm_po = False
                st.rerun()
        return

    if st.session_state.show_delete_confirm_po:
        with st.container(border=True):
            st.error(f"Are you sure you want to permanently delete PO #**{po.id}**? This cannot be undone and will also remove associated stock additions.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Delete Permanently", type="primary", use_container_width=True, key="confirm_delete_po"):
                try:
                    with SessionLocal() as t_db:
                        po_to_delete = t_db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
                        t_db.delete(po_to_delete); t_db.commit()
                    st.warning(f"Purchase Order #{po_id} has been deleted.")
                    st.session_state.show_delete_confirm_po = False
                    st.session_state.purchase_view_state = 'list'
                    st.rerun()
                except IntegrityError:
                    st.error(f"Cannot delete PO #{po.id} as its stock is currently allocated in a batch record. Please remove allocations first.")
                    st.session_state.show_delete_confirm_po = False; st.rerun()
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    st.session_state.show_delete_confirm_po = False; st.rerun()
            if c2.button("No, Go Back", use_container_width=True, key="keep_po_safe"):
                st.session_state.show_delete_confirm_po = False
                st.rerun()
        return

    st.subheader(f"Edit Purchase Order #{po.id}")

    # --- NEW: Display existing documents OUTSIDE and BEFORE the form ---
    if po.documents:
        with st.container(border=True):
            st.markdown("#### Current Attachments")
            doc_cols = st.columns(4)
            col_idx = 0
            for doc in po.documents:
                try:
                    with open(doc.file_path, "rb") as file_data:
                        doc_cols[col_idx % 4].download_button(
                            label=f"📄 {doc.original_filename}",
                            data=file_data,
                            file_name=doc.original_filename,
                            key=f"form_po_doc_{doc.id}",
                            use_container_width=True
                        )
                    col_idx += 1
                except FileNotFoundError:
                    doc_cols[col_idx % 4].error(f"Missing: {doc.original_filename}")
                    col_idx += 1
        st.markdown("---")

    ingredients = db.query(Ingredient).filter(Ingredient.user_id == user.id).order_by(Ingredient.name).all()
    ing_map = {ing.name: ing.id for ing in ingredients}
    ing_options = list(ing_map.keys())
    suppliers = db.query(Supplier).filter(Supplier.user_id == user.id).order_by(Supplier.name).all()
    sup_options = {sup.id: sup.name for sup in suppliers}; sup_options[None] = "N/A"
    
    with st.form("edit_purchase_form"):
        c1, c2 = st.columns(2)
        order_date = c1.date_input("Order Date*", value=po.order_date)
        sup_ids = list(sup_options.keys())
        current_sup_idx = sup_ids.index(po.supplier_id) if po.supplier_id in sup_ids else 0
        selected_sup_id = c2.selectbox("Supplier", options=sup_ids, format_func=lambda x: sup_options[x], index=current_sup_idx)
        shipping_cost = st.number_input("Total Shipping Cost (€)", min_value=0.0, value=float(po.shipping_cost), format="%.2f")
        notes = st.text_area("Order Notes", value=po.notes or "")
        st.markdown("---")
        st.markdown("#### Line Items")
        line_items_data = [{"Ingredient": item.ingredient_ref.name, "Quantity (g)": float(item.quantity_added_grams), "Item Cost (€)": float(item.item_cost), "Supplier Lot #": item.supplier_lot_number or ""} for item in po.line_items]
        edited_line_items = st.data_editor(pd.DataFrame(line_items_data), num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Ingredient": st.column_config.SelectboxColumn("Ingredient*", options=ing_options, required=True), "Quantity (g)": st.column_config.NumberColumn("Quantity (g)*", min_value=0.01, required=True, format="%.2f"), "Item Cost (€)": st.column_config.NumberColumn("Item Cost (€)*", min_value=0.0, required=True, format="%.2f"), "Supplier Lot #": st.column_config.TextColumn("Supplier Lot #")})
        
        # --- File uploader for NEW files remains inside the form ---
        uploaded_files = st.file_uploader("Upload New Documents", accept_multiple_files=True, key=f"po_uploader_{po.id}")

        st.markdown("---")
        submitted = st.form_submit_button("💾 Save Changes", type="primary")
        if submitted:
            with SessionLocal() as transaction_db:
                try:
                    po_to_update = transaction_db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
                    po_to_update.order_date = order_date; po_to_update.supplier_id = selected_sup_id
                    po_to_update.shipping_cost = Decimal(str(shipping_cost)); po_to_update.notes = notes
                    transaction_db.query(StockAddition).filter(StockAddition.purchase_order_id == po_id).delete()
                    for _, row in edited_line_items.iterrows():
                        if ing_id := ing_map.get(row["Ingredient"]):
                            new_stock = StockAddition(purchase_order_id=po_id, ingredient_id=ing_id, quantity_added_grams=Decimal(str(row["Quantity (g)"])), item_cost=Decimal(str(row["Item Cost (€)"])), supplier_lot_number=row["Supplier Lot #"], quantity_remaining_grams=Decimal(str(row["Quantity (g)"])))
                            transaction_db.add(new_stock)
                    if uploaded_files:
                        saved_files = save_uploaded_files(user.id, po_id, uploaded_files)
                        for file_info in saved_files:
                            transaction_db.add(PurchaseDocument(purchase_order_id=po_id, file_path=file_info["path"], original_filename=file_info["name"]))
                    transaction_db.commit()
                    st.success("Purchase Order updated successfully!")
                    st.session_state.purchase_view_state = 'list'; st.rerun()
                except Exception as e:
                    transaction_db.rollback(); st.error(f"An error occurred: {e}")

    c1, c2, _ = st.columns([1, 1, 5])
    if c1.button("✖️ Cancel", use_container_width=True, key="cancel_po_edit"):
        st.session_state.show_cancel_confirm_po = True
        st.rerun()
    if c2.button("🗑️ Delete", use_container_width=True, key="delete_po_edit"):
        st.session_state.show_delete_confirm_po = True
        st.rerun()

    if po and po.documents:
        st.sidebar.markdown("---")
        st.sidebar.markdown("#### Attached Documents")
        for doc in po.documents:
            try:
                with open(doc.file_path, "rb") as file_data:
                    st.sidebar.download_button(label=f"📄 {doc.original_filename}", data=file_data, file_name=doc.original_filename, key=f"sidebar_po_doc_{doc.id}")
            except FileNotFoundError:
                st.sidebar.error(f"File not found: {doc.original_filename}")

def render(db: Session, user: User, is_mobile: bool):
    initialize_state()
    st.header("📦 Stock Management")
    st.write("View current stock levels, record new purchases, and see your purchase history.")
    
    if st.session_state.purchase_view_state == 'edit':
        render_purchase_edit_form(db, user)
    else:
        tab1, tab2, tab3 = st.tabs(["📊 Inventory Overview", "➕ Record New Purchase", "📖 Purchase History"])
        with tab1:
            st.subheader("Current Inventory Levels & Costs")
            inventory_data = get_inventory_data(db, user.id)
            if not inventory_data:
                st.warning("No ingredients found. Add ingredients and record purchases to see your inventory.")
            else:
                df = pd.DataFrame(inventory_data)
                selection = st.dataframe(df.style.apply(lambda row: ['background-color: #FFD2D2' if row._is_low_stock else '' for _ in row], axis=1), column_config={"id": None, "_is_low_stock": None, "name_for_header": None, "Current Stock (g)": st.column_config.NumberColumn(format="%.2f g"), "Avg. Cost / kg": st.column_config.NumberColumn("Avg. Cost / kg", format="€%.2f")}, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                if selection.selection.rows:
                    selected_ingredient_id = int(df.iloc[selection.selection.rows[0]]["id"])
                    selected_ingredient_name = df.iloc[selection.selection.rows[0]]["name_for_header"]
                    st.markdown("---"); st.subheader(f"Active Lots for: {selected_ingredient_name}")
                    active_lots = db.query(StockAddition).join(PurchaseOrder).options(joinedload(StockAddition.purchase_order_ref).joinedload(PurchaseOrder.supplier_ref)).filter(PurchaseOrder.user_id == user.id, StockAddition.ingredient_id == selected_ingredient_id, StockAddition.quantity_remaining_grams > 0).order_by(PurchaseOrder.order_date.asc()).all()
                    if not active_lots: st.info("No active lots for this ingredient.")
                    else:
                        lots_data = [{"Purchase Date": lot.purchase_order_ref.order_date, "Supplier": lot.purchase_order_ref.supplier_ref.name if lot.purchase_order_ref.supplier_ref else "N/A", "Lot #": lot.supplier_lot_number or "N/A", "Initial (g)": lot.quantity_added_grams, "Remaining (g)": lot.quantity_remaining_grams, "Item Cost": lot.item_cost} for lot in active_lots]
                        st.dataframe(lots_data, hide_index=True, use_container_width=True, column_config={"Purchase Date": st.column_config.DateColumn(format="YYYY-MM-DD"), "Initial (g)": st.column_config.NumberColumn(format="%.2f g"), "Remaining (g)": st.column_config.NumberColumn(format="%.2f g"), "Item Cost": st.column_config.NumberColumn(format="€%.2f")})
        with tab2:
            st.subheader("Record a New Multi-Item Purchase")
            ingredients = db.query(Ingredient).filter(Ingredient.user_id == user.id).order_by(Ingredient.name).all()
            suppliers = db.query(Supplier).filter(Supplier.user_id == user.id).order_by(Supplier.name).all()
            if not ingredients:
                st.error("You must add an ingredient on the 'Manage Ingredients' page before you can record a purchase."); 
            else:
                with st.form("purchase_order_form", clear_on_submit=True):
                    sup_options = {sup.id: sup.name for sup in suppliers}; sup_options[None] = "N/A"
                    c1, c2 = st.columns(2)
                    order_date = c1.date_input("Order Date*", value=datetime.date.today())
                    selected_sup_id = c2.selectbox("Supplier", options=list(sup_options.keys()), format_func=lambda x: sup_options[x])
                    shipping_cost = st.number_input("Total Shipping Cost (€)", min_value=0.0, value=0.0, format="%.2f")
                    notes = st.text_area("Order Notes (e.g., Invoice #)")
                    uploaded_files = st.file_uploader("Attach Documents (Invoice, Photos, etc.)", accept_multiple_files=True)
                    st.markdown("**Step 2: Add ingredients included in this purchase**")
                    line_items_df = pd.DataFrame([{"Ingredient": None, "Quantity (g)": 0.0, "Item Cost (€)": 0.0, "Supplier Lot #": ""}])
                    edited_line_items = st.data_editor(line_items_df, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Ingredient": st.column_config.SelectboxColumn("Ingredient*", options=[ing.name for ing in ingredients], required=True), "Quantity (g)": st.column_config.NumberColumn("Quantity (g)*", min_value=0.01, required=True, format="%.2f"), "Item Cost (€)": st.column_config.NumberColumn("Item Cost (€)*", min_value=0.0, required=True, format="%.2f"), "Supplier Lot #": st.column_config.TextColumn("Supplier Lot #")})
                    if st.form_submit_button("💾 Save Full Purchase Order", type="primary"):
                        with SessionLocal() as transaction_db:
                            try:
                                line_items_to_save = edited_line_items.dropna(subset=["Ingredient", "Quantity (g)", "Item Cost (€)"])
                                if line_items_to_save.empty:
                                    st.error("Please add at least one valid ingredient line item."); transaction_db.rollback()
                                else:
                                    new_po = PurchaseOrder(user_id=user.id, supplier_id=selected_sup_id, order_date=order_date, shipping_cost=Decimal(str(shipping_cost)), notes=notes)
                                    transaction_db.add(new_po); transaction_db.flush()
                                    if uploaded_files:
                                        saved_files = save_uploaded_files(user.id, new_po.id, uploaded_files)
                                        for file_info in saved_files: transaction_db.add(PurchaseDocument(purchase_order_id=new_po.id, file_path=file_info["path"], original_filename=file_info["name"]))
                                    ing_map = {ing.name: ing.id for ing in ingredients}
                                    for _, row in line_items_to_save.iterrows():
                                        if ing_id := ing_map.get(row["Ingredient"]):
                                            new_stock = StockAddition(purchase_order_id=new_po.id, ingredient_id=ing_id, quantity_added_grams=Decimal(str(row["Quantity (g)"])), item_cost=Decimal(str(row["Item Cost (€)"])), supplier_lot_number=row["Supplier Lot #"], quantity_remaining_grams=Decimal(str(row["Quantity (g)"])))
                                            transaction_db.add(new_stock)
                                    transaction_db.commit()
                                    st.success("Purchase order and all line items saved successfully!")
                                    st.rerun()
                            except Exception as e:
                                transaction_db.rollback(); st.error(f"An error occurred: {e}")
        with tab3:
            render_purchase_history_list(db, user)
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
from models import (
    SessionLocal, User, InventoryItem, Supplier, StockAddition, PurchaseOrder, 
    PurchaseDocument, Transaction, TransactionType, ExpenseCategory
)

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
        StockAddition.inventoryitem_id,
        func.sum(StockAddition.quantity_remaining_grams).label('current_stock')
    ).join(PurchaseOrder).where(PurchaseOrder.user_id == user_id).group_by(StockAddition.inventoryitem_id).subquery()
    
    results = db.query(InventoryItem, stock_levels_sq.c.current_stock).outerjoin(
        stock_levels_sq, InventoryItem.id == stock_levels_sq.c.inventoryitem_id
    ).filter(InventoryItem.user_id == user_id).order_by(InventoryItem.name).all()
    
    inventory = []
    for item, stock in results:
        stock_level = stock or Decimal('0.0')
        additions = db.query(StockAddition).join(PurchaseOrder).filter(StockAddition.inventoryitem_id == item.id, PurchaseOrder.user_id == user_id).all()
        total_cost, total_qty = Decimal('0.0'), Decimal('0.0')
        for add in additions:
            po_line_item_count = len(add.purchase_order_ref.line_items) if add.purchase_order_ref.line_items else 1
            shipping_per_item = add.purchase_order_ref.shipping_cost / po_line_item_count
            total_cost += add.item_cost + shipping_per_item
            total_qty += add.quantity_added_grams
        
        avg_cost_per_unit = (total_cost / total_qty) if total_qty > 0 else Decimal('0.0')
        is_low_stock = (item.reorder_threshold_grams is not None and stock_level <= item.reorder_threshold_grams)
        
        inventory.append({
            "id": item.id, 
            "Inventory Item": f"⚠️ {item.name}" if is_low_stock else item.name, 
            "name_for_header": item.name, 
            "Current Stock (g or units)": stock_level, 
            "Avg. Cost / Unit": avg_cost_per_unit, 
            "_is_low_stock": is_low_stock
        })
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

def sync_po_transaction(db: Session, po: PurchaseOrder, line_items_df: pd.DataFrame, user: User):
    total_items_cost = line_items_df['Item Cost (€)'].sum()
    total_cost = Decimal(str(total_items_cost)) + po.shipping_cost
    materials_category = db.query(ExpenseCategory).filter(
        ExpenseCategory.user_id == user.id,
        func.lower(ExpenseCategory.name) == 'materials'
    ).first()
    category_id = materials_category.id if materials_category else None
    linked_transaction = db.query(Transaction).filter(Transaction.purchase_order_id == po.id).first()
    description = f"Purchase from {po.supplier_ref.name if po.supplier_ref else 'N/A'} (PO #{po.id})"
    if linked_transaction:
        linked_transaction.date = po.order_date
        linked_transaction.amount = total_cost
        linked_transaction.description = description
        linked_transaction.supplier_id = po.supplier_id
        linked_transaction.category_id = category_id
    else:
        new_transaction = Transaction(
            user_id=user.id, date=po.order_date, description=description, amount=total_cost,
            transaction_type=TransactionType.EXPENSE, category_id=category_id,
            supplier_id=po.supplier_id, purchase_order_id=po.id
        )
        db.add(new_transaction)
    st.toast("Transaction Ledger updated automatically.", icon="🧾")

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
    po = db.query(PurchaseOrder).options(joinedload(PurchaseOrder.supplier_ref), joinedload(PurchaseOrder.line_items).joinedload(StockAddition.inventoryitem_ref), joinedload(PurchaseOrder.documents)).filter(PurchaseOrder.id == po_id, PurchaseOrder.user_id == user.id).first()
    if not po:
        st.error("Purchase Order not found."); st.session_state.purchase_view_state = 'list'; st.rerun(); return

    if st.session_state.show_cancel_confirm_po:
        with st.container(border=True):
            st.warning("Are you sure you want to cancel? All unsaved changes will be lost.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Cancel", use_container_width=True, key="confirm_cancel_po"):
                st.session_state.show_cancel_confirm_po = False; st.session_state.purchase_view_state = 'list'; st.rerun()
            if c2.button("No, Keep Editing", use_container_width=True, key="keep_editing_po"):
                st.session_state.show_cancel_confirm_po = False; st.rerun()
        return

    if st.session_state.show_delete_confirm_po:
        with st.container(border=True):
            st.error(f"Are you sure you want to permanently delete PO #**{po.id}**? This cannot be undone and will also remove associated stock additions and the linked financial transaction.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Delete Permanently", type="primary", use_container_width=True, key="confirm_delete_po"):
                try:
                    with SessionLocal() as t_db:
                        po_to_delete = t_db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
                        for doc in po_to_delete.documents:
                            try: os.remove(doc.file_path)
                            except FileNotFoundError: pass
                        t_db.delete(po_to_delete); t_db.commit()
                    st.warning(f"Purchase Order #{po_id} has been deleted.")
                    st.session_state.show_delete_confirm_po = False; st.session_state.purchase_view_state = 'list'; st.rerun()
                except IntegrityError:
                    st.error(f"Cannot delete PO #{po.id} as its stock is currently allocated in a batch record. Please remove allocations first.")
                    st.session_state.show_delete_confirm_po = False; st.rerun()
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    st.session_state.show_delete_confirm_po = False; st.rerun()
            if c2.button("No, Go Back", use_container_width=True, key="keep_po_safe"):
                st.session_state.show_delete_confirm_po = False; st.rerun()
        return

    st.subheader(f"Edit Purchase Order #{po.id}")

    if po.documents:
        with st.container(border=True):
            st.markdown("#### Current Attachments")
            for doc in list(po.documents):
                c1, c2 = st.columns([5, 1])
                try:
                    with open(doc.file_path, "rb") as file_data:
                        c1.download_button(label=f"📄 {doc.original_filename}", data=file_data, file_name=doc.original_filename, key=f"form_po_doc_{doc.id}", use_container_width=True)
                except FileNotFoundError: c1.error(f"Missing: {doc.original_filename}")
                if c2.button("🗑️", key=f"delete_po_doc_{doc.id}", help="Delete this attachment"):
                    try: os.remove(doc.file_path)
                    except FileNotFoundError: st.toast(f"File was already deleted from disk.", icon="⚠️")
                    with SessionLocal() as t_db:
                        doc_to_delete = t_db.query(PurchaseDocument).filter(PurchaseDocument.id == doc.id).one_or_none()
                        if doc_to_delete: t_db.delete(doc_to_delete); t_db.commit()
                    st.success(f"Deleted attachment: {doc.original_filename}"); st.rerun()
        st.markdown("---")

    inventory_items = db.query(InventoryItem).filter(InventoryItem.user_id == user.id).order_by(InventoryItem.name).all()
    item_map = {item.name: item.id for item in inventory_items}
    item_options = list(item_map.keys())
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
        st.markdown("---"); st.markdown("#### Line Items")
        line_items_data = [{"Item": item.inventoryitem_ref.name, "Quantity (g or units)": float(item.quantity_added_grams), "Item Cost (€)": float(item.item_cost), "Supplier Lot #": item.supplier_lot_number or ""} for item in po.line_items]
        edited_line_items = st.data_editor(pd.DataFrame(line_items_data), num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Item": st.column_config.SelectboxColumn("Item*", options=item_options, required=True), "Quantity (g or units)": st.column_config.NumberColumn("Quantity (g or units)*", min_value=0.01, required=True, format="%.2f"), "Item Cost (€)": st.column_config.NumberColumn("Item Cost (€)*", min_value=0.0, required=True, format="%.2f"), "Supplier Lot #": st.column_config.TextColumn("Supplier Lot #")})
        uploaded_files = st.file_uploader("Upload New Documents", accept_multiple_files=True, key=f"po_uploader_{po.id}")
        st.markdown("---")
        submitted = st.form_submit_button("💾 Save Changes", type="primary")
        if submitted:
            with SessionLocal() as transaction_db:
                try:
                    po_to_update = transaction_db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
                    po_to_update.order_date, po_to_update.supplier_id = order_date, selected_sup_id
                    po_to_update.shipping_cost, po_to_update.notes = Decimal(str(shipping_cost)), notes
                    transaction_db.query(StockAddition).filter(StockAddition.purchase_order_id == po_id).delete()
                    for _, row in edited_line_items.iterrows():
                        if item_id := item_map.get(row["Item"]):
                            new_stock = StockAddition(purchase_order_id=po_id, inventoryitem_id=item_id, quantity_added_grams=Decimal(str(row["Quantity (g or units)"])), item_cost=Decimal(str(row["Item Cost (€)"])), supplier_lot_number=row["Supplier Lot #"], quantity_remaining_grams=Decimal(str(row["Quantity (g or units)"])))
                            transaction_db.add(new_stock)
                    if uploaded_files:
                        saved_files = save_uploaded_files(user.id, po_id, uploaded_files)
                        for file_info in saved_files:
                            transaction_db.add(PurchaseDocument(purchase_order_id=po_id, file_path=file_info["path"], original_filename=file_info["name"]))
                    transaction_db.flush()
                    sync_po_transaction(transaction_db, po_to_update, edited_line_items, user)
                    transaction_db.commit()
                    st.success("Purchase Order updated successfully!"); st.session_state.purchase_view_state = 'list'; st.rerun()
                except Exception as e:
                    transaction_db.rollback(); st.error(f"An error occurred: {e}")

    c1, c2, _ = st.columns([1, 1, 5])
    if c1.button("✖️ Cancel", use_container_width=True, key="cancel_po_edit"):
        st.session_state.show_cancel_confirm_po = True; st.rerun()
    if c2.button("🗑️ Delete PO", use_container_width=True, key="delete_po_edit"):
        st.session_state.show_delete_confirm_po = True; st.rerun()

    if po and po.documents:
        st.sidebar.markdown("---"); st.sidebar.markdown("#### Attached Documents")
        for doc in po.documents:
            try:
                with open(doc.file_path, "rb") as file_data:
                    st.sidebar.download_button(label=f"📄 {doc.original_filename}", data=file_data, file_name=doc.original_filename, key=f"sidebar_po_doc_{doc.id}")
            except FileNotFoundError: st.sidebar.error(f"File not found: {doc.original_filename}")

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
                st.warning("No inventory items found. Add items and record purchases to see your inventory.")
            else:
                df = pd.DataFrame(inventory_data)
                # --- CHANGED: Re-added on_select and selection handling ---
                selection = st.dataframe(
                    df.style.apply(lambda row: ['background-color: #FFD2D2' if row._is_low_stock else '' for _ in row], axis=1), 
                    column_config={"id": None, "_is_low_stock": None, "name_for_header": None, "Current Stock (g or units)": st.column_config.NumberColumn(format="%.2f"), "Avg. Cost / Unit": st.column_config.NumberColumn(format="€%.3f")}, 
                    use_container_width=True, 
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row"
                )

                # --- ADDED: Restored the logic to display stock lots for the selected item ---
                if selection.selection.rows:
                    selected_row_index = selection.selection.rows[0]
                    selected_item_id = int(df.iloc[selected_row_index]["id"])
                    selected_item_name = df.iloc[selected_row_index]["name_for_header"]

                    st.markdown("---")
                    st.subheader(f"Active Stock Lots for: {selected_item_name}")

                    active_lots = db.query(StockAddition).join(PurchaseOrder).options(
                        joinedload(StockAddition.purchase_order_ref).joinedload(PurchaseOrder.supplier_ref)
                    ).filter(
                        PurchaseOrder.user_id == user.id,
                        StockAddition.inventoryitem_id == selected_item_id,
                        StockAddition.quantity_remaining_grams > 0
                    ).order_by(PurchaseOrder.order_date.asc()).all()

                    if not active_lots:
                        st.info("No active lots with remaining stock for this item.")
                    else:
                        lots_data = [{
                            "Purchase Date": lot.purchase_order_ref.order_date,
                            "Supplier": lot.purchase_order_ref.supplier_ref.name if lot.purchase_order_ref.supplier_ref else "N/A",
                            "Lot #": lot.supplier_lot_number or "N/A",
                            "Initial Qty": lot.quantity_added_grams,
                            "Remaining Qty": lot.quantity_remaining_grams,
                            "Item Cost": lot.item_cost
                        } for lot in active_lots]
                        
                        st.dataframe(
                            lots_data,
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "Purchase Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                                "Initial Qty": st.column_config.NumberColumn(format="%.2f"),
                                "Remaining Qty": st.column_config.NumberColumn(format="%.2f"),
                                "Item Cost": st.column_config.NumberColumn(format="€%.2f")
                            }
                        )
                # --- END ADDED ---

        with tab2:
            st.subheader("Record a New Multi-Item Purchase")
            inventory_items = db.query(InventoryItem).filter(InventoryItem.user_id == user.id).order_by(InventoryItem.name).all()
            suppliers = db.query(Supplier).filter(Supplier.user_id == user.id).order_by(Supplier.name).all()
            if not inventory_items:
                st.error("You must add an inventory item on the 'Manage Inventory' page before you can record a purchase."); 
            else:
                with st.form("purchase_order_form", clear_on_submit=True):
                    sup_options = {sup.id: sup.name for sup in suppliers}; sup_options[None] = "N/A"
                    c1, c2 = st.columns(2)
                    order_date = c1.date_input("Order Date*", value=datetime.date.today())
                    selected_sup_id = c2.selectbox("Supplier", options=list(sup_options.keys()), format_func=lambda x: sup_options[x])
                    shipping_cost = st.number_input("Total Shipping Cost (€)", min_value=0.0, value=0.0, format="%.2f")
                    notes = st.text_area("Order Notes (e.g., Invoice #)")
                    uploaded_files = st.file_uploader("Attach Documents (Invoice, Photos, etc.)", accept_multiple_files=True)
                    st.markdown("**Step 2: Add items included in this purchase**")
                    line_items_df = pd.DataFrame([{"Item": None, "Quantity (g or units)": 0.0, "Item Cost (€)": 0.0, "Supplier Lot #": ""}])
                    edited_line_items = st.data_editor(line_items_df, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Item": st.column_config.SelectboxColumn("Item*", options=[item.name for item in inventory_items], required=True), "Quantity (g or units)": st.column_config.NumberColumn("Quantity (g or units)*", min_value=0.01, required=True, format="%.2f"), "Item Cost (€)": st.column_config.NumberColumn("Item Cost (€)*", min_value=0.0, required=True, format="%.2f"), "Supplier Lot #": st.column_config.TextColumn("Supplier Lot #")})
                    
                    if st.form_submit_button("💾 Save Full Purchase Order", type="primary"):
                        with SessionLocal() as transaction_db:
                            try:
                                line_items_to_save = edited_line_items.dropna(subset=["Item", "Quantity (g or units)", "Item Cost (€)"])
                                if line_items_to_save.empty:
                                    st.error("Please add at least one valid inventory item line."); transaction_db.rollback()
                                else:
                                    new_po = PurchaseOrder(user_id=user.id, supplier_id=selected_sup_id, order_date=order_date, shipping_cost=Decimal(str(shipping_cost)), notes=notes)
                                    transaction_db.add(new_po); transaction_db.flush()
                                    if uploaded_files:
                                        saved_files = save_uploaded_files(user.id, new_po.id, uploaded_files)
                                        for file_info in saved_files: 
                                            transaction_db.add(PurchaseDocument(purchase_order_id=new_po.id, file_path=file_info["path"], original_filename=file_info["name"]))
                                    item_map = {item.name: item.id for item in inventory_items}
                                    for _, row in line_items_to_save.iterrows():
                                        if item_id := item_map.get(row["Item"]):
                                            new_stock = StockAddition(purchase_order_id=new_po.id, inventoryitem_id=item_id, quantity_added_grams=Decimal(str(row["Quantity (g or units)"])), item_cost=Decimal(str(row["Item Cost (€)"])), supplier_lot_number=row["Supplier Lot #"], quantity_remaining_grams=Decimal(str(row["Quantity (g or units)"])))
                                            transaction_db.add(new_stock)
                                    
                                    transaction_db.flush()
                                    sync_po_transaction(transaction_db, new_po, line_items_to_save, user)
                                    
                                    transaction_db.commit()
                                    st.success("Purchase order and all line items saved successfully!")
                                    st.rerun()
                            except Exception as e:
                                transaction_db.rollback(); st.error(f"An error occurred: {e}")
        with tab3:
            render_purchase_history_list(db, user)
# app_pages/p12_transaction_ledger.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
import datetime
import sys
import os
import pathlib

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import SessionLocal, User, Transaction, TransactionType, ExpenseCategory, Supplier, Customer, TransactionDocument

# --- State Management ---
def initialize_state():
    if 'transaction_view_state' not in st.session_state:
        st.session_state.transaction_view_state = 'list'
    if 'transaction_to_edit_id' not in st.session_state:
        st.session_state.transaction_to_edit_id = None
    if 'show_cancel_dialog' not in st.session_state:
        st.session_state.show_cancel_dialog = False
    if 'show_delete_dialog' not in st.session_state:
        st.session_state.show_delete_dialog = False

# --- Helper function for saving files ---
def save_uploaded_files(user_id: int, transaction_id: int, uploaded_files):
    saved_paths = []
    save_dir = pathlib.Path(f"uploaded_files/transactions/{user_id}/{transaction_id}")
    save_dir.mkdir(parents=True, exist_ok=True)
    for uploaded_file in uploaded_files:
        file_path = save_dir / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        saved_paths.append({"path": str(file_path), "name": uploaded_file.name})
    return saved_paths

# --- UI Rendering Functions ---

def render_list_view(db: Session, user: User):
    st.subheader("Transaction History")
    if st.button("➕ Add New Transaction", type="primary"):
        st.session_state.transaction_view_state = 'create'
        st.session_state.transaction_to_edit_id = None
        st.rerun()
        
    transactions = db.query(Transaction).options(
        joinedload(Transaction.category_ref), 
        joinedload(Transaction.supplier_ref), 
        joinedload(Transaction.customer_ref)
    ).filter(Transaction.user_id == user.id).order_by(Transaction.date.desc()).all()
    
    if not transactions:
        st.info("No transactions recorded. Click the button above to add one."); return
    
    df_data = []
    for t in transactions:
        source = "Manual Entry"
        if t.purchase_order_id:
            source = f"PO #{t.purchase_order_id}"
        elif t.invoice_id:
            source = f"Invoice #{t.invoice_id}"

        df_data.append({
            "id": t.id, 
            "Date": t.date, 
            "Description": t.description, 
            "Type": t.transaction_type.value, 
            "Amount": t.amount, 
            "Category": t.category_ref.name if t.category_ref else "N/A",
            "Source": source
        })
    
    df = pd.DataFrame(df_data)
    
    selection = st.dataframe(
        df, 
        on_select="rerun", 
        selection_mode="single-row", 
        hide_index=True, 
        use_container_width=True, 
        column_order=["Date", "Description", "Type", "Amount", "Category", "Source"],
        column_config={"id": None, "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"), "Amount": st.column_config.NumberColumn("Amount", format="€%.2f")}
    )
    
    if selection.selection.rows:
        st.session_state.transaction_to_edit_id = int(df.iloc[selection.selection.rows[0]]["id"])
        st.session_state.transaction_view_state = 'edit'
        st.rerun()

def render_cancel_dialog():
    st.subheader("Confirm Cancel")
    with st.container(border=True):
        st.warning("Are you sure you want to cancel? All unsaved changes will be lost.")
        c1, c2 = st.columns(2)
        if c1.button("Yes, Cancel", use_container_width=True, key="confirm_cancel"):
            st.session_state.show_cancel_dialog = False
            st.session_state.transaction_view_state = 'list'
            st.rerun()
        if c2.button("No, Keep Editing", use_container_width=True, key="deny_cancel"):
            st.session_state.show_cancel_dialog = False
            st.rerun()

def render_delete_dialog(db: Session):
    transaction_id = st.session_state.transaction_to_edit_id
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    
    # --- ADDED: Prevent deletion of auto-generated transactions ---
    if transaction and transaction.purchase_order_id:
        st.error(f"This transaction is linked to Purchase Order #{transaction.purchase_order_id} and cannot be deleted from here. Please delete the Purchase Order from the 'Stock Management' page to remove this transaction.")
        if st.button("OK, Go Back"):
            st.session_state.show_delete_dialog = False
            st.rerun()
        return

    description = f"Transaction #{transaction.id} ('{transaction.description}')" if transaction else f"Transaction #{transaction_id}"
    st.subheader("Confirm Delete")
    with st.container(border=True):
        st.error(f"Are you sure you want to permanently delete **{description}**? This cannot be undone.")
        c1, c2 = st.columns(2)
        if c1.button("Yes, Delete Permanently", type="primary", use_container_width=True, key="confirm_delete"):
            with SessionLocal() as t_db:
                t_to_delete = t_db.query(Transaction).filter(Transaction.id == transaction_id).one()
                for doc in t_to_delete.documents:
                    try:
                        os.remove(doc.file_path)
                    except FileNotFoundError:
                        pass
                t_db.delete(t_to_delete)
                t_db.commit()
                st.success("Transaction deleted!")
                st.session_state.show_delete_dialog = False
                st.session_state.transaction_view_state = 'list'
                st.rerun()
        if c2.button("No, Go Back", use_container_width=True, key="deny_delete"):
            st.session_state.show_delete_dialog = False
            st.rerun()

def render_form_view(db: Session, user: User):
    if st.session_state.get('show_cancel_dialog'):
        render_cancel_dialog(); return
    if st.session_state.get('show_delete_dialog'):
        render_delete_dialog(db); return

    is_edit_mode = st.session_state.transaction_view_state == 'edit'
    transaction = None
    if is_edit_mode and st.session_state.transaction_to_edit_id:
        transaction = db.query(Transaction).options(joinedload(Transaction.documents)).filter(Transaction.id == st.session_state.transaction_to_edit_id).first()
        if not transaction:
            st.error("Transaction not found."); st.session_state.transaction_view_state = 'list'; st.rerun()
        st.subheader(f"Edit Transaction #{transaction.id}")
    else:
        st.subheader("Add New Transaction")
    
    is_linked_to_po = is_edit_mode and transaction and transaction.purchase_order_id is not None
    if is_linked_to_po:
        st.info(f"🧾 This transaction is linked to **Purchase Order #{transaction.purchase_order_id}**. Its date, amount, and supplier are managed automatically from the Stock Management page. You can still change the description or expense category here.")

    if is_edit_mode and transaction and transaction.documents:
        with st.container(border=True):
            st.markdown("#### Current Attachments")
            # ... (document display logic is unchanged) ...

    categories = db.query(ExpenseCategory).filter(ExpenseCategory.user_id == user.id).order_by(ExpenseCategory.name).all()
    cat_options = {cat.id: cat.name for cat in categories}
    suppliers = db.query(Supplier).filter(Supplier.user_id == user.id).order_by(Supplier.name).all()
    sup_options = {sup.id: sup.name for sup in suppliers}; sup_options[None] = "N/A"
    customers = db.query(Customer).filter(Customer.user_id == user.id).order_by(Customer.name).all()
    cust_options = {cust.id: cust.name for cust in customers}; cust_options[None] = "N/A"

    with st.form("transaction_form"):
        c1, c2 = st.columns(2)
        date = c1.date_input("Date*", value=transaction.date if transaction else datetime.date.today(), disabled=is_linked_to_po)
        ttype_options = [t.value for t in TransactionType]
        ttype_index = ttype_options.index(transaction.transaction_type.value) if transaction else 0
        transaction_type_val = c2.selectbox("Type*", options=ttype_options, index=ttype_index, disabled=is_linked_to_po)
        
        min_amount = 0.01
        default_value = max(float(transaction.amount), min_amount) if transaction else min_amount
        amount = st.number_input("Amount (€)*", min_value=min_amount, value=default_value, format="%.2f", disabled=is_linked_to_po)
        
        description = st.text_input("Description*", value=transaction.description if transaction else "")
        
        category_id, supplier_id, customer_id = None, None, None
        if transaction_type_val == TransactionType.EXPENSE.value:
            if cat_options:
                cat_id_options = list(cat_options.keys())
                cat_id_index = cat_id_options.index(transaction.category_id) if transaction and transaction.category_id in cat_id_options else 0
                category_id = st.selectbox("Expense Category*", options=cat_id_options, format_func=lambda x: cat_options[x], index=cat_id_index)
            
            sup_id_options = list(sup_options.keys())
            sup_id_index = sup_id_options.index(transaction.supplier_id) if transaction and transaction.supplier_id in sup_id_options else 0
            supplier_id = st.selectbox("Supplier (Optional)", options=sup_id_options, format_func=lambda x: sup_options[x], index=sup_id_index, disabled=is_linked_to_po)
        
        if transaction_type_val == TransactionType.SALE.value:
            cust_id_options = list(cust_options.keys())
            cust_id_index = cust_id_options.index(transaction.customer_id) if transaction and transaction.customer_id in cust_id_options else 0
            customer_id = st.selectbox("Customer (Optional)", options=cust_id_options, format_func=lambda x: cust_options[x], index=cust_id_index)
        
        uploaded_files = st.file_uploader("Upload New Documents", accept_multiple_files=True)
        
        st.markdown("---")
        submitted = st.form_submit_button("💾 Save", type="primary")

        if submitted:
            if not description or not amount:
                st.error("Description and Amount are required fields."); return
            with SessionLocal() as t_db:
                try:
                    target = t_db.query(Transaction).filter(Transaction.id == st.session_state.transaction_to_edit_id).first() if is_edit_mode else Transaction(user_id=user.id)
                    if not is_edit_mode: t_db.add(target)
                    
                    # Only update fields if not linked, or if they are fields we allow editing on
                    if not is_linked_to_po:
                        target.date = date
                        target.transaction_type = TransactionType(transaction_type_val)
                        target.amount = Decimal(str(amount))
                        target.supplier_id = supplier_id
                        target.customer_id = customer_id
                    
                    target.description = description
                    target.category_id = category_id
                    
                    t_db.flush()
                    if uploaded_files:
                        saved_files = save_uploaded_files(user.id, target.id, uploaded_files)
                        for file_info in saved_files:
                            t_db.add(TransactionDocument(transaction_id=target.id, file_path=file_info["path"], original_filename=file_info["name"]))
                    t_db.commit()
                    st.success("Transaction saved!"); st.session_state.transaction_view_state = 'list'; st.rerun()
                except Exception as e:
                    t_db.rollback(); st.error(f"Error saving: {e}")

    c1, c2, _ = st.columns([1, 1, 5])
    if c1.button("✖️ Cancel", use_container_width=True):
        st.session_state.show_cancel_dialog = True
        st.rerun()
    if is_edit_mode:
        if c2.button("🗑️ Delete", use_container_width=True):
            st.session_state.show_delete_dialog = True
            st.rerun()

def render(db: Session, user: User, is_mobile: bool):
    st.header("💸 Transaction Ledger")
    st.write("A complete record of all money coming in and going out of your business.")
    initialize_state()
    
    if st.session_state.get('show_cancel_dialog') or st.session_state.get('show_delete_dialog'):
        render_form_view(db, user)
    elif st.session_state.transaction_view_state in ['create', 'edit']:
        render_form_view(db, user)
    else:
        render_list_view(db, user)
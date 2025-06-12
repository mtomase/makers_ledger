# app_pages/p10_sales_invoices.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
import datetime
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import SessionLocal, User, Customer, Product, Invoice, InvoiceLineItem, InvoiceStatus

def initialize_state():
    """Initializes session state variables for the invoice page."""
    if 'invoice_view_state' not in st.session_state:
        st.session_state.invoice_view_state = 'list'
    if 'invoice_to_edit_id' not in st.session_state:
        st.session_state.invoice_to_edit_id = None
    # State for confirmation dialogs
    if 'show_cancel_confirm_invoice' not in st.session_state:
        st.session_state.show_cancel_confirm_invoice = False
    if 'show_delete_confirm_invoice' not in st.session_state:
        st.session_state.show_delete_confirm_invoice = False

def get_next_invoice_number(db: Session, user_id: int):
    """Generates the next sequential invoice number."""
    last_invoice = db.query(Invoice).filter(Invoice.user_id == user_id).order_by(Invoice.id.desc()).first()
    if not last_invoice or not last_invoice.invoice_number:
        return "INV-0001"
    try:
        prefix, number = last_invoice.invoice_number.rsplit('-', 1)
        return f"{prefix}-{int(number) + 1:04d}"
    except:
        return f"{last_invoice.invoice_number}-1"

def render_list_view(db: Session, user: User):
    """Displays the list of existing invoices and handles creation/selection."""
    st.subheader("Existing Invoices")
    if st.button("➕ Create New Sales Invoice", type="primary"):
        st.session_state.invoice_view_state = 'create'
        st.session_state.invoice_to_edit_id = None
        st.rerun()

    invoices = db.query(Invoice).options(joinedload(Invoice.customer_ref)).filter(Invoice.user_id == user.id).order_by(Invoice.invoice_date.desc()).all()
    if not invoices:
        st.info("No invoices found. Click the button above to create one.")
        return

    df_data = [{"id": inv.id, "Invoice #": inv.invoice_number, "Customer": inv.customer_ref.name if inv.customer_ref else "N/A", "Date": inv.invoice_date, "Total": f"€{inv.total_amount:,.2f}", "Status": inv.status.value} for inv in invoices]
    df = pd.DataFrame(df_data)
    
    selection = st.dataframe(df, on_select="rerun", selection_mode="single-row", hide_index=True, use_container_width=True, column_config={"id": None, "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD")})
    
    if selection.selection.rows:
        st.session_state.invoice_to_edit_id = int(df.iloc[selection.selection.rows[0]]["id"])
        st.session_state.invoice_view_state = 'edit'
        st.rerun()

def render_form_view(db: Session, user: User):
    """Renders the form for creating or editing an invoice, including confirmation dialogs."""
    is_edit_mode = st.session_state.invoice_view_state == 'edit'
    invoice = None
    if is_edit_mode and st.session_state.invoice_to_edit_id:
        invoice = db.query(Invoice).options(joinedload(Invoice.line_items)).filter(Invoice.id == st.session_state.invoice_to_edit_id).first()
        if not invoice:
            st.error("Invoice not found.")
            st.session_state.invoice_view_state = 'list'
            st.rerun()

    # --- Confirmation Dialog Logic ---
    if st.session_state.show_cancel_confirm_invoice:
        with st.container(border=True):
            st.warning("Are you sure you want to cancel? All unsaved changes will be lost.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Cancel", use_container_width=True, key="confirm_cancel_invoice"):
                st.session_state.show_cancel_confirm_invoice = False
                st.session_state.invoice_view_state = 'list'
                st.rerun()
            if c2.button("No, Keep Editing", use_container_width=True, key="keep_editing_invoice"):
                st.session_state.show_cancel_confirm_invoice = False
                st.rerun()
        return

    if st.session_state.show_delete_confirm_invoice and invoice:
        with st.container(border=True):
            st.error(f"Are you sure you want to permanently delete invoice **{invoice.invoice_number}**? This cannot be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Delete Permanently", type="primary", use_container_width=True, key="confirm_delete_invoice"):
                with SessionLocal() as t_db:
                    t_db.delete(t_db.query(Invoice).filter(Invoice.id == invoice.id).one())
                    t_db.commit()
                st.success(f"Invoice {invoice.invoice_number} deleted.")
                st.session_state.show_delete_confirm_invoice = False
                st.session_state.invoice_view_state = 'list'
                st.rerun()
            if c2.button("No, Go Back", use_container_width=True, key="keep_invoice"):
                st.session_state.show_delete_confirm_invoice = False
                st.rerun()
        return

    # --- Main Form ---
    if is_edit_mode and invoice:
        st.subheader(f"Edit Invoice: {invoice.invoice_number}")
    else:
        st.subheader("Create New Sales Invoice")

    customers = db.query(Customer).filter(Customer.user_id == user.id).all()
    customer_map = {c.name: c.id for c in customers}
    products = db.query(Product).filter(Product.user_id == user.id).all()
    product_map = {p.product_name: p for p in products}

    with st.form("invoice_form"):
        c1, c2, c3 = st.columns(3)
        cust_names = list(customer_map.keys())
        def_cust_idx = cust_names.index(invoice.customer_ref.name) if is_edit_mode and invoice and invoice.customer_ref else 0
        customer_name = c1.selectbox("Customer*", cust_names, index=def_cust_idx)
        invoice_date = c2.date_input("Invoice Date", value=invoice.invoice_date if is_edit_mode and invoice else datetime.date.today())
        due_date = c3.date_input("Due Date", value=invoice.due_date if is_edit_mode and invoice else datetime.date.today() + datetime.timedelta(days=30))
        invoice_number = st.text_input("Invoice Number", value=invoice.invoice_number if is_edit_mode and invoice else get_next_invoice_number(db, user.id))
        
        st.markdown("---")
        st.markdown("#### Line Items")
        line_items_data = [{"Product": item.product_ref.product_name if item.product_ref else None, "Description": item.description, "Quantity": float(item.quantity), "Unit Price": float(item.unit_price), "VAT %": float(item.vat_rate_percent)} for item in invoice.line_items] if is_edit_mode and invoice else [{"Product": None, "Description": "", "Quantity": 1.0, "Unit Price": 0.0, "VAT %": 23.0}]
        edited_df = st.data_editor(pd.DataFrame(line_items_data), num_rows="dynamic", use_container_width=True, hide_index=True, key="line_items_editor", column_config={"Product": st.column_config.SelectboxColumn("Product", options=list(product_map.keys()), required=False), "Description": st.column_config.TextColumn("Description*", required=True), "Quantity": st.column_config.NumberColumn("Quantity*", min_value=0, format="%.2f"), "Unit Price": st.column_config.NumberColumn("Unit Price (€)*", min_value=0, format="%.2f"), "VAT %": st.column_config.NumberColumn("VAT %", min_value=0, default=23.0, format="%.1f")})
        
        subtotal = sum(Decimal(str(row.get("Quantity", 0))) * Decimal(str(row.get("Unit Price", 0))) for _, row in edited_df.iterrows())
        vat = sum((Decimal(str(r.get("Quantity",0))) * Decimal(str(r.get("Unit Price",0)))) * (Decimal(str(r.get("VAT %",0))) / 100) for _, r in edited_df.iterrows())
        total = subtotal + vat
        
        st.markdown("---")
        tc1, tc2, tc3 = st.columns(3)
        tc1.metric("Subtotal", f"€{subtotal:,.2f}")
        tc2.metric("Total VAT", f"€{vat:,.2f}")
        tc3.metric("Total Amount", f"€{total:,.2f}")
        notes = st.text_area("Notes", value=invoice.notes if is_edit_mode and invoice else "")
        
        submitted = st.form_submit_button("Save", type="primary")
        if submitted:
            with SessionLocal() as transaction_db:
                try:
                    target = transaction_db.query(Invoice).filter(Invoice.id == st.session_state.invoice_to_edit_id).one() if is_edit_mode else Invoice(user_id=user.id, status=InvoiceStatus.DRAFT)
                    if not is_edit_mode: transaction_db.add(target)
                    target.invoice_number=invoice_number; target.invoice_date=invoice_date; target.due_date=due_date; target.customer_id=customer_map[customer_name]; target.notes=notes;
                    target.subtotal=subtotal; target.vat_amount=vat; target.total_amount=total;
                    transaction_db.flush()
                    transaction_db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == target.id).delete()
                    for _, row in edited_df.iterrows():
                        if row['Description']:
                            prod_obj = product_map.get(row["Product"])
                            transaction_db.add(InvoiceLineItem(invoice_id=target.id, product_id=prod_obj.id if prod_obj else None, description=row["Description"], quantity=Decimal(str(row["Quantity"])), unit_price=Decimal(str(row["Unit Price"])), vat_rate_percent=Decimal(str(row["VAT %"])), line_total=Decimal(str(row["Quantity"])) * Decimal(str(row["Unit Price"]))))
                    transaction_db.commit()
                    st.success(f"Invoice {invoice_number} saved!")
                    st.session_state.invoice_view_state = 'list'
                    st.rerun()
                except Exception as e:
                    transaction_db.rollback()
                    st.error(f"Error saving: {e}")

    # --- Action Buttons (outside the form) ---
    c1, c2, _ = st.columns([1, 1, 5])
    if c1.button("✖️ Cancel", use_container_width=True):
        st.session_state.show_cancel_confirm_invoice = True
        st.rerun()
        
    if is_edit_mode and invoice:
        if c2.button("🗑️ Delete", use_container_width=True):
            st.session_state.show_delete_confirm_invoice = True
            st.rerun()

def render(db: Session, user: User, is_mobile: bool):
    """Main render function for the sales invoices page."""
    initialize_state()
    st.header("🧾 Sales Invoices")
    if st.session_state.invoice_view_state in ['create', 'edit']:
        render_form_view(db, user)
    else:
        render_list_view(db, user)
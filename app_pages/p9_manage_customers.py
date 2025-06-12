# app_pages/p9_manage_customers.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import SessionLocal, User, Customer

def initialize_state():
    """Initializes session state variables for the customer page."""
    if 'customer_view_state' not in st.session_state:
        st.session_state.customer_view_state = 'list'
    if 'customer_to_edit_id' not in st.session_state:
        st.session_state.customer_to_edit_id = None
    # State for confirmation dialogs
    if 'show_cancel_confirm_customer' not in st.session_state:
        st.session_state.show_cancel_confirm_customer = False
    if 'show_delete_confirm_customer' not in st.session_state:
        st.session_state.show_delete_confirm_customer = False

def render_customer_form(db: Session, user: User):
    """Renders the form for creating or editing a customer, including confirmation dialogs."""
    is_edit_mode = st.session_state.customer_view_state == 'edit'
    customer = None
    if is_edit_mode and st.session_state.customer_to_edit_id:
        customer = db.query(Customer).filter(Customer.id == st.session_state.customer_to_edit_id).first()
        if not customer:
            st.error("Customer not found. Returning to list.")
            st.session_state.customer_view_state = 'list'
            st.rerun()

    # --- Confirmation Dialog Logic ---
    if st.session_state.show_cancel_confirm_customer:
        with st.container(border=True):
            st.warning("Are you sure you want to cancel? All unsaved changes will be lost.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Cancel", use_container_width=True, key="confirm_cancel_cust"):
                st.session_state.show_cancel_confirm_customer = False
                st.session_state.customer_view_state = 'list'
                st.rerun()
            if c2.button("No, Keep Editing", use_container_width=True, key="keep_editing_cust"):
                st.session_state.show_cancel_confirm_customer = False
                st.rerun()
        return

    if st.session_state.show_delete_confirm_customer and customer:
        with st.container(border=True):
            st.error(f"Are you sure you want to permanently delete customer **'{customer.name}'**? This cannot be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Delete Permanently", type="primary", use_container_width=True, key="confirm_delete_cust"):
                try:
                    with SessionLocal() as t_db:
                        cust_to_delete = t_db.query(Customer).filter(Customer.id == customer.id).one()
                        t_db.delete(cust_to_delete)
                        t_db.commit()
                    st.success(f"Customer '{customer.name}' deleted.")
                    st.session_state.show_delete_confirm_customer = False
                    st.session_state.customer_view_state = 'list'
                    st.rerun()
                except IntegrityError:
                    st.error(f"Cannot delete '{customer.name}' as they are linked to existing invoices. Please remove associated invoices first.")
                    st.session_state.show_delete_confirm_customer = False
                    st.rerun()
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    st.session_state.show_delete_confirm_customer = False
                    st.rerun()

            if c2.button("No, Go Back", use_container_width=True, key="keep_cust"):
                st.session_state.show_delete_confirm_customer = False
                st.rerun()
        return

    # --- Main Form ---
    if is_edit_mode and customer:
        st.subheader(f"Edit Customer: {customer.name}")
    else:
        st.subheader("Add New Customer")

    with st.form("customer_form"):
        name = st.text_input("Customer Name*", value=customer.name if customer else "")
        contact_email = st.text_input("Contact Email", value=customer.contact_email if customer else "")
        address = st.text_area("Address", value=customer.address if customer else "")
        vat_number = st.text_input("VAT Number", value=customer.vat_number if customer else "")
        
        submitted = st.form_submit_button("💾 Save", type="primary")
        if submitted:
            if not name:
                st.error("Customer Name is a required field.")
            else:
                with SessionLocal() as transaction_db:
                    try:
                        target_customer = transaction_db.query(Customer).filter(Customer.id == st.session_state.customer_to_edit_id).one() if is_edit_mode else Customer(user_id=user.id)
                        if not is_edit_mode: transaction_db.add(target_customer)
                        target_customer.name = name
                        target_customer.contact_email = contact_email
                        target_customer.address = address
                        target_customer.vat_number = vat_number
                        transaction_db.commit()
                        st.success(f"Customer '{name}' saved successfully!")
                        st.session_state.customer_view_state = 'list'
                        st.rerun()
                    except IntegrityError:
                        transaction_db.rollback()
                        st.error(f"A customer named '{name}' already exists.")
                    except Exception as e:
                        transaction_db.rollback()
                        st.error(f"An error occurred: {e}")

    # --- Action Buttons (outside the form) ---
    c1, c2, _ = st.columns([1, 1, 5])
    if c1.button("✖️ Cancel", use_container_width=True):
        st.session_state.show_cancel_confirm_customer = True
        st.rerun()

    if is_edit_mode and customer:
        if c2.button("🗑️ Delete", use_container_width=True):
            st.session_state.show_delete_confirm_customer = True
            st.rerun()

def render_customer_list(db: Session, user: User):
    """Displays the list of existing customers and handles creation/selection."""
    st.subheader("Existing Customer Records")
    if st.button("➕ Add New Customer", type="primary"):
        st.session_state.customer_view_state = 'create'
        st.session_state.customer_to_edit_id = None
        st.rerun()

    customers = db.query(Customer).filter(Customer.user_id == user.id).order_by(Customer.name).all()
    if not customers:
        st.info("No customers found. Use the button above to add one.")
        return

    df_data = [{"id": c.id, "Name": c.name, "Email": c.contact_email, "VAT Number": c.vat_number} for c in customers]
    df = pd.DataFrame(df_data)
    
    selection = st.dataframe(df, on_select="rerun", selection_mode="single-row", hide_index=True, use_container_width=True, column_config={"id": None})
    
    if selection.selection.rows:
        st.session_state.customer_to_edit_id = int(df.iloc[selection.selection.rows[0]]["id"])
        st.session_state.customer_view_state = 'edit'
        st.rerun()

def render(db: Session, user: User, is_mobile: bool):
    """Main render function for the customer management page."""
    initialize_state()
    st.header("👥 Manage Customers")
    if st.session_state.customer_view_state in ['create', 'edit']:
        render_customer_form(db, user)
    else:
        render_customer_list(db, user)
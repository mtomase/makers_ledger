# main_app.py
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import os
import datetime
from streamlit_js_eval import streamlit_js_eval

# --- Model and Utility Imports ---
# FIX: Import UserLayoutEnumDef to correctly handle new user creation
from models import get_db, User, SessionLocal, UserLayoutEnumDef

# --- Page Imports ---
from app_pages import (
    p1_manage_ingredients,
    p1b_manage_ingredient_types,
    p2_manage_suppliers,
    p3_manage_employees,
    p4_manage_tasks,
    p5_global_costs,
    p6_manage_products,
    p7_stock_management,
    p8_batch_records,
    p9_manage_customers,
    p10_sales_invoices,
    p11_financial_settings,
    p12_transaction_ledger,
    p13_revenue_reports,
    p15_user_settings 
)


# --- MODIFICATION: Page Configuration at the Top ---
# This logic runs at the beginning of every script rerun.
# It checks if a user is already logged in to set their preferred layout.
def get_user_layout():
    # Default to wide if no one is logged in yet.
    layout = "wide"
    if st.session_state.get("authentication_status"):
        try:
            db = SessionLocal()
            user = db.query(User).filter(User.username == st.session_state.get("username")).first()
            if user and user.layout_preference:
                layout = user.layout_preference.value
        finally:
            db.close()
    return layout

# st.set_page_config() must be the first Streamlit command.
st.set_page_config(
    page_title="Maker's Ledger", 
    page_icon="📓", 
    layout=get_user_layout()
)


# --- Screen Width Detection ---
if 'screen_width' not in st.session_state:
    st.session_state.screen_width = streamlit_js_eval(js_expressions='window.innerWidth', key='INIT_SCR_WIDTH_FETCH_STREAMLIT_MAIN_V5')
if st.session_state.screen_width is None or st.session_state.screen_width == 0:
    st.session_state.screen_width = 1024
    if 'initial_rerun_for_width_done_streamlit_main_v5' not in st.session_state:
        st.session_state.initial_rerun_for_width_done_streamlit_main_v5 = True
        st.rerun()
MOBILE_BREAKPOINT = 768
IS_MOBILE = st.session_state.screen_width < MOBILE_BREAKPOINT

# --- Configuration and Authenticator Setup ---
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, 'config.yaml')
    with open(CONFIG_FILE_PATH, 'r') as file:
        config_auth = yaml.load(file, Loader=SafeLoader)
except Exception as e:
    st.error(f"❌ CRITICAL ERROR: Could not load configuration file. {e}")
    st.stop()

authenticator = stauth.Authenticate(
    config_auth['credentials'],
    config_auth['cookie']['name'],
    config_auth['cookie']['key'],
    config_auth['cookie']['expiry_days']
)

# --- Main Application Flow ---
def main():
    authenticator.login()

    if st.session_state.get("authentication_status"):
        db_session = next(get_db())
        try:
            username = st.session_state["username"]
            current_user = db_session.query(User).filter(User.username == username).first()
            if not current_user:
                st.error(f"User '{username}' found in authenticator but not in the database. Please contact support.")
                st.stop()

            with st.sidebar:
                st.success(f"Welcome, **{current_user.name}**!")
                authenticator.logout("Logout", "sidebar", key='sidebar_logout_button')
                st.markdown("---")

                financials_pages = [
                    "Manage Customers",
                    "Sales Invoices",
                    "Transaction Ledger",
                    "Financial Settings",
                ]
                if current_user.country_code == 'IE':
                    financials_pages.insert(3, "Revenue Reports")

                menu_groups = {
                    "Setup & Configuration": [
                        "Manage Ingredients", 
                        "Manage Ingredient Types",
                        "Manage Suppliers", 
                        "Manage Employees", 
                        "Manage Tasks", 
                        "Global Costs"
                    ],
                    "Operations & Analysis": [
                        "Manage Products", 
                        "Stock Management", 
                        "Batch Records"
                    ],
                    "Financials": financials_pages,
                    "Application & User": ["User Settings"]
                }

                if 'active_page' not in st.session_state or st.session_state.active_page not in [p for pages in menu_groups.values() for p in pages]:
                    st.session_state.active_page = "Manage Products"

                def set_active_page(page):
                    st.session_state.active_page = page

                for group_name, pages in menu_groups.items():
                    is_expanded = any(page == st.session_state.active_page for page in pages)
                    with st.expander(group_name, expanded=is_expanded):
                        for page in pages:
                            button_type = "primary" if st.session_state.active_page == page else "secondary"
                            st.button(
                                page, 
                                on_click=set_active_page, 
                                args=(page,), 
                                key=f"btn_{page.replace(' ', '_')}", 
                                use_container_width=True, 
                                type=button_type
                            )

            active_page = st.session_state.active_page
            st.title(f"🧮 {active_page}")

            page_router = {
                "Manage Ingredients": p1_manage_ingredients.render,
                "Manage Ingredient Types": p1b_manage_ingredient_types.render,
                "Manage Suppliers": p2_manage_suppliers.render,
                "Manage Employees": p3_manage_employees.render,
                "Manage Tasks": p4_manage_tasks.render,
                "Global Costs": p5_global_costs.render,
                "Manage Products": p6_manage_products.render,
                "Stock Management": p7_stock_management.render,
                "Batch Records": p8_batch_records.render,
                "Manage Customers": p9_manage_customers.render,
                "Sales Invoices": p10_sales_invoices.render,
                "Financial Settings": p11_financial_settings.render,
                "Transaction Ledger": p12_transaction_ledger.render,
                "Revenue Reports": p13_revenue_reports.render,
                "User Settings": p15_user_settings.render,
            }

            render_function = page_router.get(active_page, lambda **kwargs: st.warning("Page not found."))
            
            if active_page == "User Settings":
                 render_function(db=db_session, user=current_user, authenticator=authenticator, config=config_auth, config_path=CONFIG_FILE_PATH, is_mobile=IS_MOBILE)
            else:
                render_function(db=db_session, user=current_user, is_mobile=IS_MOBILE)

        finally:
            if db_session:
                db_session.close()

    elif st.session_state["authentication_status"] is False:
        st.error('Username/password is incorrect')
    elif st.session_state["authentication_status"] is None:
        st.warning("Please enter your username and password to login, or register if you are a new user.")
        try:
            # --- FIX: Pass the list of preauthorized emails from the config file ---
            email_of_registered_user, username_of_registered_user, name_of_registered_user = authenticator.register_user(
                pre_authorized=config_auth['preauthorized']['emails']
            )
            if email_of_registered_user:
                st.success('User registered successfully in authenticator. Adding to application database...')
                db = next(get_db())
                try:
                    hashed_password = config_auth['credentials']['usernames'][username_of_registered_user]['password']
                    db_user = User(
                        username=username_of_registered_user, 
                        email=email_of_registered_user, 
                        name=name_of_registered_user, 
                        hashed_password=hashed_password,
                        country_code='IE',
                        # --- FIX: Use the Enum member, not a string, for the default layout ---
                        layout_preference=UserLayoutEnumDef.WIDE
                    )
                    db.add(db_user)
                    db.commit()
                    st.success("User added to application database. Please login to continue.")
                    with open(CONFIG_FILE_PATH, 'w') as file:
                        yaml.dump(config_auth, file, default_flow_style=False)
                    st.rerun()
                except Exception as db_error:
                    db.rollback()
                    st.error(f"Error saving new user to the database: {db_error}")
                finally:
                    db.close()

        except Exception as e:
            st.error(f"An error occurred during registration: {e}")

if __name__ == "__main__":
    main()
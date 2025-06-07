# main_app.py
import streamlit as st
import streamlit_authenticator as stauth
from streamlit_option_menu import option_menu
import yaml
from yaml.loader import SafeLoader
import os
import datetime
from streamlit_js_eval import streamlit_js_eval

# --- CORRECTED IMPORTS ---
from app_pages import (
    page_01_ingredients, page_02_employees, page_03_tasks, 
    page_04_global_costs, page_05_products, page_06_cost_breakdown,
    page_07_user_settings
)
# --- END CORRECTION ---

from models import get_db, User
from utils.auth_helpers import sync_stauth_user_to_db
from main_app_functions import calculate_cost_breakdown

# --- Page Configuration ---
st.set_page_config(page_title="Product Cost Calculator", layout="wide", initial_sidebar_state="expanded")

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
    config_auth['cookie']['expiry_days'],
    pre_authorized=config_auth.get('preauthorized', {}).get('emails', [])
)

# --- Main Application Flow ---
def main():
    authenticator.login()

    if st.session_state.get("authentication_status"):
        db_session = next(get_db())
        try:
            username = st.session_state["username"]
            name = st.session_state["name"]
            email = config_auth['credentials']['usernames'][username]['email']
            current_user = sync_stauth_user_to_db(db=db_session, username=username, email=email, name=name)
            
            with st.sidebar:
                st.success(f"Welcome, **{current_user.name}**!")
                authenticator.logout("Logout", "sidebar", key='sidebar_logout_button')
                st.markdown("---")
                
                menu_titles = [
                    "Manage Ingredients", "Manage Employees", "Manage Tasks", 
                    "Global Costs/Salaries", "Manage Products", "Product Cost Breakdown", 
                    "User Guide", "User Settings"
                ]
                menu_icons = ["bi-basket3-fill", "bi-people-fill", "bi-tools", "bi-globe2", "bi-box-seam-fill", "bi-bar-chart-line-fill", "bi-book-half", "bi-gear-fill"]
                
                default_index = menu_titles.index(st.session_state.get('main_menu_selected', "Manage Ingredients"))
                
                selected_option = option_menu(
                    menu_title="🛠️ Main Menu", options=menu_titles, icons=menu_icons, 
                    menu_icon="bi-list-task", default_index=default_index,
                    orientation="vertical", key="main_menu_option_selector"
                )

                if selected_option != st.session_state.get('main_menu_selected'):
                    st.session_state.main_menu_selected = selected_option
                    if selected_option not in ["Manage Products", "Product Cost Breakdown"]:
                        st.session_state.selected_product_id = None
                    st.rerun()

            choice = st.session_state.get('main_menu_selected', menu_titles[0])
            st.title(f"🧮 Product Cost Calculator: {choice}")

            page_router = {
                "Manage Ingredients": page_01_ingredients.render,
                "Manage Employees": page_02_employees.render,
                "Manage Tasks": page_03_tasks.render,
                "Global Costs/Salaries": page_04_global_costs.render,
                "Manage Products": page_05_products.render,
                "Product Cost Breakdown": page_06_cost_breakdown.render,
                "User Settings": page_07_user_settings.render,
            }

            if choice in page_router:
                if choice == "User Settings":
                    page_router[choice](authenticator=authenticator, config=config_auth, config_path=CONFIG_FILE_PATH)
                else:
                    page_router[choice](db=db_session, user=current_user, is_mobile=IS_MOBILE)
            elif choice == "User Guide":
                render_user_guide()

        finally:
            if db_session:
                db_session.close()

    elif st.session_state["authentication_status"] is False:
        st.error('Username/password is incorrect')
    elif st.session_state["authentication_status"] is None:
        st.warning("Please enter your username and password to login, or register if you are a new user.")
        try:
            if authenticator.register_user(pre_authorized=config_auth.get('preauthorized', {}).get('emails', [])):
                st.success('User registered successfully, please login.')
                with open(CONFIG_FILE_PATH, 'w') as file:
                    yaml.dump(config_auth, file, default_flow_style=False)
                # Create the user in the DB upon registration
                db_session_reg = next(get_db())
                try:
                    reg_username = st.session_state.get('username')
                    reg_name = st.session_state.get('name')
                    reg_email = config_auth['credentials']['usernames'][reg_username]['email']
                    sync_stauth_user_to_db(db=db_session_reg, username=reg_username, email=reg_email, name=reg_name)
                finally:
                    db_session_reg.close()
                st.rerun()
        except Exception as e:
            st.error(e)

def render_user_guide():
    st.markdown("## 📖 User Guide: Product Cost Calculator")
    st.markdown("Welcome! This guide explains how to use the app and the key concepts behind the calculations.")
    st.markdown("---")
    
    def read_guide_file(file_name):
        try:
            guide_path = os.path.join(SCRIPT_DIR, 'guides', file_name)
            with open(guide_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"**Error:** Could not read guide file `{file_name}`. Reason: {e}"

    with st.expander("🚀 Getting Started & Navigation", expanded=True):
        st.markdown(read_guide_file("01_getting_started.md"), unsafe_allow_html=True)
    with st.expander("🗃️ Core Data Management Sections", expanded=False):
        st.markdown(read_guide_file("02_core_data.md"), unsafe_allow_html=True)
    with st.expander("📦 Manage Products (The Core Engine!)", expanded=False):
        st.markdown(read_guide_file("03_manage_products.md"), unsafe_allow_html=True)
    with st.expander("📈 Product Cost Breakdown Analysis", expanded=False):
        st.markdown(read_guide_file("04_cost_breakdown.md"), unsafe_allow_html=True)
    with st.expander("⚙️ User Settings & Profile", expanded=False):
        st.markdown(read_guide_file("05_user_settings.md"), unsafe_allow_html=True)
    
    st.markdown("---")
    st.success("🎉 You've reached the end of the User Guide!")

if __name__ == "__main__":
    main()
    st.markdown("---")
    st.markdown(f"<div style='text-align: center; color: grey;'>Product Cost Calculator © {datetime.date.today().year}</div>", unsafe_allow_html=True)
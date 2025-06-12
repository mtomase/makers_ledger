# app_pages/p15_user_settings.py
import streamlit as st
import yaml
from sqlalchemy.orm import Session
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# --- FIX: Import the correct Enum name 'UserLayoutEnumDef' from your models.py ---
from models import User, SessionLocal, UserLayoutEnumDef

# --- A simple list of countries for the dropdown ---
COUNTRY_CODES = {
    "Ireland": "IE", "United Kingdom": "GB", "United States": "US", 
    "Canada": "CA", "Australia": "AU", "Germany": "DE", "France": "FR",
    # Add more countries as needed
}
COUNTRY_NAMES = list(COUNTRY_CODES.keys())

def render(db: Session, user: User, authenticator, config, config_path, **kwargs):
    """
    This is the function that main_app.py calls to render this page.
    It receives the authenticator instance and config directly from main_app.
    """
    st.header("⚙️ User Settings")
    st.write("Manage your user profile and application settings.")
    
    st.subheader("Profile Information")
    
    with st.form("user_profile_form"):
        st.write(f"**Username:** `{user.username}`")
        
        new_name = st.text_input("Name:", value=user.name or "")
        new_email = st.text_input("Email:", value=user.email or "")

        current_country_name = next((n for n, c in COUNTRY_CODES.items() if c == user.country_code), None)
        country_index = COUNTRY_NAMES.index(current_country_name) if current_country_name in COUNTRY_NAMES else 0
        country = st.selectbox("Country (for tax localization)", options=COUNTRY_NAMES, index=country_index)

        st.markdown("#### Page Layout Preference")
        # Use the .value of the enum to match the string from the radio button options
        current_layout_value = user.layout_preference.value if user.layout_preference else 'wide'
        layout_index = 0 if current_layout_value == 'wide' else 1
        layout = st.radio("Layout", ["wide", "centered"], index=layout_index, horizontal=True)

        if st.form_submit_button("💾 Save User Details", type="primary"):
            if not new_name.strip() or not new_email.strip():
                st.error("Name and Email cannot be empty.")
            else:
                try:
                    with SessionLocal() as transaction_db:
                        user_to_update = transaction_db.query(User).filter(User.id == user.id).one()

                        user_to_update.name = new_name.strip()
                        user_to_update.email = new_email.strip()
                        user_to_update.country_code = COUNTRY_CODES[country]
                        # --- FIX: Convert the string 'wide'/'centered' to the correct ENUM member ---
                        user_to_update.layout_preference = UserLayoutEnumDef(layout)
                        
                        config['credentials']['usernames'][user.username]['name'] = user_to_update.name
                        config['credentials']['usernames'][user.username]['email'] = user_to_update.email
                        
                        transaction_db.commit()

                        with open(config_path, 'w') as file:
                            yaml.dump(config, file, default_flow_style=False)
                        
                        st.session_state['name'] = user_to_update.name
                        
                        st.success("User details updated successfully!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error updating details: {e}")

    st.markdown("---")
    st.subheader("Update Password")
    try:
        if authenticator.reset_password(username=user.username, location='main'):
            new_hashed_password = config['credentials']['usernames'][user.username]['password']
            
            try:
                with SessionLocal() as transaction_db:
                    user_to_update = transaction_db.query(User).filter(User.id == user.id).one()
                    user_to_update.hashed_password = new_hashed_password
                    transaction_db.commit()
                st.success('Password updated in database successfully!')
            except Exception as e:
                st.error(f"Error saving new password to the database: {e}")

    except Exception as e:
        st.error(f"An error occurred during password reset: {e}")
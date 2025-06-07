# pages/page_07_user_settings.py
import streamlit as st
import yaml

def render(authenticator, config: dict, config_path: str):
    st.header("⚙️ User Settings")
    st.write("Manage your user profile and application settings.")
    
    username = st.session_state.get("username")
    if not username:
        st.error("Could not determine current user.")
        return

    st.subheader("Profile Information")
    user_credentials = config['credentials']['usernames'].get(username, {})
    current_name = user_credentials.get('name', '')
    current_email = user_credentials.get('email', '')
    
    st.write(f"**Username:** `{username}`")
    new_name = st.text_input("Name:", value=current_name, key="update_user_name_input")
    new_email = st.text_input("Email:", value=current_email, key="update_user_email_input")
    
    if st.button("Save User Details", key="save_user_details_button_key", type="primary"):
        if not new_name.strip():
            st.error("Name cannot be empty.")
        elif not new_email.strip():
            st.error("Email cannot be empty.")
        else:
            try:
                config['credentials']['usernames'][username]['name'] = new_name.strip()
                config['credentials']['usernames'][username]['email'] = new_email.strip()
                st.session_state['name'] = new_name.strip()
                with open(config_path, 'w') as file:
                    yaml.dump(config, file, default_flow_style=False, allow_unicode=True)
                st.success("User details updated successfully!")
                st.rerun() 
            except Exception as e:
                st.error(f"Error updating details: {e}")

    st.markdown("---")
    st.subheader("Update Password")
    try:
        if authenticator.reset_password(username=username, location='main'): 
            st.success('Password reset successfully! Saving to config file.')
            with open(config_path, 'w') as file:
                yaml.dump(config, file, default_flow_style=False, allow_unicode=True)
    except Exception as e:
        st.error(f"Error during password reset widget: {e}")
"""Authentication view component for Chef Streamlit UI."""

import uuid
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import streamlit as st

from app.domain.models import UserSettings
from app.services.auth import authenticate_user, register_user
from app.services.container import Container


def render_auth_view(container: Container) -> None:
    """Render the login and registration portal before granting access to chat and memory features."""
    col_left, col_center, col_right = st.columns([1, 2, 1])

    with col_center:
        st.markdown(
            """
            <div style="text-align: center; margin-top: 1.5rem; margin-bottom: 2rem;">
                <h1 style="margin-bottom: 0.2rem;">🍳 Chef</h1>
                <p style="color: #6c757d; font-size: 1.05rem;">
                    Sign in to access your culinary assistant, personalized memory, and recipes.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab_login, tab_register = st.tabs(["🔑 Sign In", "✨ Create Account"])

        # ====================================================================
        # 1. SIGN IN TAB
        # ====================================================================
        with tab_login:
            st.subheader("Welcome Back")
            with st.form("login_form", clear_on_submit=False):
                login_email = st.text_input(
                    "Email Address",
                    placeholder="chef@example.com",
                    key="login_email_input",
                ).strip()
                login_password = st.text_input(
                    "Password",
                    type="password",
                    placeholder="••••••••",
                    key="login_password_input",
                )
                submit_login = st.form_submit_button("Sign In", type="primary", use_container_width=True)

            if submit_login:
                if not login_email or not login_password:
                    st.error("Please enter both email and password.")
                else:
                    user_repo = getattr(container.repository, "user_repo", container.repository)
                    try:
                        user = authenticate_user(
                            user_repo=user_repo,
                            email=login_email,
                            password=login_password,
                        )
                        if user:
                            st.session_state.authenticated = True
                            st.session_state.current_user_id = user.user_id
                            st.session_state.auth_user = user
                            st.session_state.current_session_id = f"session_{uuid.uuid4().hex[:8]}"
                            st.session_state.messages = []
                            st.session_state.last_response = None
                            print(f"[AUTH] 🔑 Login successful: {user.user_id} ({user.email})", flush=True)
                            st.success(f"Welcome back, {user.display_name}!")
                            st.rerun()
                        else:
                            print(f"[AUTH] ❌ Login failed for email: {login_email}", flush=True)
                            st.error("Invalid email or password. Please verify your credentials or sign up.")
                    except (ServerSelectionTimeoutError, ConnectionFailure) as err:
                        st.error(
                            "🔌 Unable to connect to MongoDB Atlas (Connection / SSL Handshake Error). "
                            "Please check that your current public IP address is whitelisted in your MongoDB Atlas Network Access settings (or allow 0.0.0.0/0)."
                        )
                    except Exception as exc:
                        st.error(f"Sign in error: {exc}")

        # ====================================================================
        # 2. CREATE ACCOUNT TAB
        # ====================================================================
        with tab_register:
            st.subheader("New to Chef?")
            with st.form("register_form", clear_on_submit=False):
                reg_name = st.text_input(
                    "Full Name",
                    placeholder="Gordon Ramsay",
                    key="reg_name_input",
                ).strip()
                reg_email = st.text_input(
                    "Email Address",
                    placeholder="chef@example.com",
                    key="reg_email_input",
                ).strip()
                reg_handle = st.text_input(
                    "User Handle (optional)",
                    placeholder="chef_gordon",
                    help="Unique username handle. If omitted, it will be automatically derived from your email.",
                    key="reg_handle_input",
                ).strip()
                reg_password = st.text_input(
                    "Password",
                    type="password",
                    placeholder="At least 6 characters",
                    key="reg_password_input",
                )
                reg_confirm = st.text_input(
                    "Confirm Password",
                    type="password",
                    placeholder="Re-enter password",
                    key="reg_confirm_input",
                )
                reg_units = st.selectbox(
                    "Preferred Units",
                    options=["metric", "imperial"],
                    index=0,
                    key="reg_units_input",
                )
                submit_register = st.form_submit_button("Create Account", type="primary", use_container_width=True)

            if submit_register:
                if not reg_name or not reg_email or not reg_password:
                    st.error("Please fill in your name, email, and password.")
                elif "@" not in reg_email or "." not in reg_email:
                    st.error("Please enter a valid email address.")
                elif len(reg_password) < 6:
                    st.error("Password must be at least 6 characters long.")
                elif reg_password != reg_confirm:
                    st.error("Passwords do not match. Please re-type your password.")
                else:
                    user_repo = getattr(container.repository, "user_repo", container.repository)
                    try:
                        user = register_user(
                            user_repo=user_repo,
                            email=reg_email,
                            password=reg_password,
                            display_name=reg_name,
                            user_id=reg_handle or None,
                            settings=UserSettings(units=reg_units, memory_enabled=True),
                        )
                        st.session_state.authenticated = True
                        st.session_state.current_user_id = user.user_id
                        st.session_state.auth_user = user
                        st.session_state.current_session_id = f"session_{uuid.uuid4().hex[:8]}"
                        st.session_state.messages = []
                        st.session_state.last_response = None
                        print(f"[AUTH] ✨ Account created: {user.user_id} ({user.email})", flush=True)
                        st.success("Account created successfully!")
                        st.rerun()
                    except ValueError as err:
                        st.error(str(err))
                    except (ServerSelectionTimeoutError, ConnectionFailure) as err:
                        st.error(
                            "🔌 Unable to connect to MongoDB Atlas (Connection / SSL Handshake Error). "
                            "Please check that your current public IP address is whitelisted in your MongoDB Atlas Network Access settings (or allow 0.0.0.0/0)."
                        )
                    except Exception as exc:
                        st.error(f"Failed to create account: {exc}")

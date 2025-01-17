import sqlite3
from datetime import datetime
import time
import streamlit as st

# Connect to SQLite databases
def connect_to_db(db_path):
    """
    Connect to SQLite database with Write-Ahead Logging (WAL) enabled.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode for concurrency
    conn.execute("PRAGMA synchronous=NORMAL;")  # Reduce synchronous overhead
    return conn

users_conn = connect_to_db('users.db')
income_conn = connect_to_db('income.db')

# Initialize session state
if "user" not in st.session_state:
    st.session_state["user"] = None
if "username" not in st.session_state:
    st.session_state["username"] = None

# Helper functions
def execute_with_retry(conn, query, params=()):
    """
    Execute a query with retry logic to handle database locks, ensuring proper cursor handling.
    """
    for _ in range(5):  # Retry up to 5 times
        try:
            cur = conn.cursor()  # Open the cursor manually
            cur.execute(query, params)
            conn.commit()
            cur.close()  # Explicitly close the cursor
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(0.1)  # Wait for 100ms before retrying
            else:
                raise
        finally:
            try:
                cur.close()  # Ensure the cursor is closed in case of exceptions
            except:
                pass
    raise sqlite3.OperationalError("Database is locked after multiple retries.")

def get_sources(owner):
    """
    Fetch income sources for a given owner.
    """
    query = "SELECT id, name FROM sources WHERE owner = ?"
    cur = income_conn.cursor()  # Open the cursor manually
    try:
        return cur.execute(query, (owner,)).fetchall()
    finally:
        cur.close()  # Explicitly close the cursor

def edit_source(source_id, new_name):
    """
    Edit an existing income source.
    """
    query = "UPDATE sources SET name = ? WHERE id = ?"
    execute_with_retry(income_conn, query, (new_name, source_id))

def add_source(name, owner):
    """
    Add a new income source for the owner.
    """
    query = "INSERT INTO sources (name, owner) VALUES (?, ?)"
    execute_with_retry(income_conn, query, (name, owner))

def add_income(owner, amount, source, date, description):
    """
    Add a new income record.
    """
    query = "INSERT INTO income (owner, amount, source, date, description) VALUES (?, ?, ?, ?, ?)"
    execute_with_retry(income_conn, query, (owner, amount, source, date, description))

def validate_old_password(old_password, username):
    """
    Validate the old password provided by the user.
    """
    query = "SELECT password FROM users WHERE username = ?"
    cur = users_conn.cursor()
    try:
        stored_password = cur.execute(query, (username,)).fetchone()
        return stored_password and stored_password[0] == old_password
    finally:
        cur.close()

def update_user(name, username, email, new_password, old_username):
    """
    Update the user profile with new details, using explicit cursor handling.
    """
    # If no new password is provided, retain the old password
    if not new_password:
        query = "SELECT password FROM users WHERE username = ?"
        cur = users_conn.cursor()
        try:
            current_password = cur.execute(query, (old_username,)).fetchone()[0]
        finally:
            cur.close()
        new_password = current_password

    # Perform the update
    query = "UPDATE users SET name = ?, username = ?, email = ?, password = ? WHERE username = ?"
    cur = users_conn.cursor()
    try:
        cur.execute(query, (name, username, email, new_password, old_username))
        users_conn.commit()
        st.session_state["user"] = name
        st.session_state["username"] = username
    finally:
        cur.close()

# Profile Page
def profile_page():
    if "username" not in st.session_state or not st.session_state["username"]:
        st.warning("You must log in to access this page.")
        return

    owner = st.session_state["username"]
    st.title(f"Welcome, {st.session_state['user']}!")
    st.header("User Profile")

    # Edit Profile
    st.subheader("Update Profile")
    with st.form("edit_profile_form"):
        name = st.text_input("Full Name", value=st.session_state["user"])
        username = st.text_input("Username", value=st.session_state["username"])
        email = st.text_input("Email")
        old_password = st.text_input("Current Password", type="password")  # Old password for verification
        new_password = st.text_input("New Password", type="password")
        submitted = st.form_submit_button("Update Profile")

        if submitted:
            if not old_password:
                st.error("Please provide your current password to update your profile.")
            elif validate_old_password(old_password, st.session_state["username"]):
                update_user(name, username, email, new_password, st.session_state["username"])
                st.success("Profile updated successfully! Please refresh for changes to reflect.")
            else:
                st.error("Current password is incorrect. Please try again.")

    st.divider()

    # Manage Income Sources
    st.subheader("Income Sources")
    sources = get_sources(owner)

    # Display existing sources and edit functionality
    if sources:
        st.write("Your income sources:")
        for source_id, source_name in sources:
            col1, col2 = st.columns([3, 1])
            with col1:
                new_name = st.text_input(f"Edit Source (ID: {source_id})", value=source_name, key=f"edit_{source_id}")
            if col2.button("Save", key=f"save_{source_id}"):
                if new_name.strip():
                    edit_source(source_id, new_name)
                    st.success("Source updated successfully!")
                    st.rerun()
                else:
                    st.error("Source name cannot be empty.")

    # Add a new source
    with st.form("add_source_form"):
        new_source = st.text_input("Add New Source")
        add_source_btn = st.form_submit_button("Add Source")
        if add_source_btn:
            if new_source.strip():
                add_source(new_source, owner)
                st.success("Source added successfully!")
                st.rerun()
            else:
                st.error("Source name cannot be empty.")

    st.divider()

    # Add Income
    st.subheader("Add Income")
    with st.form("add_income_form"):
        amount = st.number_input("Amount", min_value=0.0, step=0.01)
        source = st.selectbox("Source", [src[1] for src in sources])
        description = st.text_area("Description")
        date = st.date_input("Date", max_value=datetime.now().date())
        add_income_btn = st.form_submit_button("Add Income")
        if add_income_btn:
            add_income(owner, amount, source, date, description)
            st.success("Income added successfully!")

# Call the profile page
profile_page()

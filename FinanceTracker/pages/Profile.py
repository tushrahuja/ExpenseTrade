import sqlite3
from datetime import datetime
import time
import streamlit as st
import pandas as pd

# Ensure user is logged in
if "user" not in st.session_state or st.session_state["user"] is None:
    st.warning("Please log in to access this page.")
    st.stop()

with st.sidebar:
    st.image("expense.png", use_container_width=True)
    if st.session_state["user"]:
        if st.button("Logout"):
            st.session_state["user"] = None
            st.rerun()

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
if "email" not in st.session_state:
    st.session_state["email"] = ""  # Default to empty string

# Helper functions
def execute_with_retry(conn, query, params=()):
    """
    Execute a query with retry logic to handle database locks, ensuring proper cursor handling.
    """
    for _ in range(5):  # Retry up to 5 times
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            conn.commit()
            cur.close()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(0.1)  # Wait for 100ms before retrying
            else:
                raise
        finally:
            try:
                cur.close()
            except:
                pass
    raise sqlite3.OperationalError("Database is locked after multiple retries.")

def get_user_email(username):
    """Fetch the email of the logged-in user from the database."""
    query = "SELECT email FROM users WHERE username = ?"
    cur = users_conn.cursor()
    try:
        result = cur.execute(query, (username,)).fetchone()
        return result[0] if result else ""  # Return email or empty string if not found
    finally:
        cur.close()

def get_sources(owner):
    """
    Fetch income sources for a given owner.
    """
    query = "SELECT id, name FROM sources WHERE owner = ?"
    cur = income_conn.cursor()
    try:
        return cur.execute(query, (owner,)).fetchall()
    finally:
        cur.close()

def add_source(owner, name):
    """
    Add a new income source for the user.
    """
    query = "INSERT INTO sources (owner, name) VALUES (?, ?)"
    execute_with_retry(income_conn, query, (owner, name))

def add_income(owner, amount, source, date, description):
    """
    Add a new income record.
    """
    query = "INSERT INTO income (owner, amount, source, date, description) VALUES (?, ?, ?, ?, ?)"
    execute_with_retry(income_conn, query, (owner, amount, source, date, description))

def get_incomes(owner):
    """
    Fetch all income records for a given owner.
    """
    query = "SELECT id, amount, source, date, description FROM income WHERE owner = ?"
    cur = income_conn.cursor()
    try:
        return cur.execute(query, (owner,)).fetchall()
    finally:
        cur.close()

def edit_income(income_id, new_amount, new_source, new_date, new_description):
    """
    Edit an existing income record.
    """
    query = """
    UPDATE income 
    SET amount = ?, source = ?, date = ?, description = ? 
    WHERE id = ?
    """
    execute_with_retry(income_conn, query, (new_amount, new_source, new_date, new_description, income_id))

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
    Update the user profile with new details.
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
    execute_with_retry(users_conn, query, (name, username, email, new_password, old_username))
    st.session_state["user"] = name
    st.session_state["username"] = username
    st.session_state["email"] = email  # Update email in session state

# Profile Page
def profile_page():
    if "username" not in st.session_state or not st.session_state["username"]:
        st.warning("You must log in to access this page.")
        return

    owner = st.session_state["username"]

    # Fetch email from the database if it's not already set
    if not st.session_state.get("email"):
        fetched_email = get_user_email(owner)
        if fetched_email:
            st.session_state["email"] = fetched_email  # Store the email in session state

    st.title(f"Welcome, {st.session_state['user']}!")
    st.header("User Profile")

    # Edit Profile Section
    st.subheader("Update Profile")
    with st.form("edit_profile_form"):
        name = st.text_input("Full Name", value=st.session_state["user"])
        username = st.text_input("Username", value=st.session_state["username"])
        email = st.text_input("Email", value=st.session_state["email"])
        old_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        submitted = st.form_submit_button("Update Profile")

        if submitted:
            if not old_password:
                st.error("Please provide your current password to update your profile.")
            elif validate_old_password(old_password, st.session_state["username"]):
                update_user(name, username, email, new_password, st.session_state["username"])
                st.success("Profile updated successfully!")
            else:
                st.error("Current password is incorrect. Please try again.")

    st.divider()

    # Add Source Section
    st.subheader("Add Income Source")
    with st.form("add_source_form"):
        new_source = st.text_input("New Source Name")
        submitted = st.form_submit_button("Add Source")
        if submitted:
            if new_source.strip():
                add_source(owner, new_source)
                st.success("Source added successfully!")
                st.rerun()
            else:
                st.error("Source name cannot be empty.")

    st.divider()

    # Add Income Section
    st.subheader("Add Income")
    sources = get_sources(owner)
    if sources:
        with st.form("add_income_form"):
            amount = st.number_input("Amount", min_value=0.0, step=0.01)
            source = st.selectbox("Source", [src[1] for src in sources])
            description = st.text_area("Description")
            date = st.date_input("Date", max_value=datetime.now().date())
            add_income_btn = st.form_submit_button("Add Income")
            if add_income_btn:
                add_income(owner, amount, source, date, description)
                st.success("Income added successfully!")
    else:
        st.info("No sources available. Please add an income source above.")

    st.divider()

    # View and Edit Income Section
    st.subheader("Your Incomes")
    incomes = get_incomes(owner)

    if incomes:
        # Display incomes in a table with serial numbers
        income_df = pd.DataFrame(
            incomes,
            columns=["ID", "Amount", "Source", "Date", "Description"]
        ).reset_index()
        income_df.rename(columns={"index": "Sr. No"}, inplace=True)
        income_df["Sr. No"] += 1  # Start Sr. No from 1
        st.table(income_df[["Sr. No", "Amount", "Source", "Date", "Description"]])

        with st.form("edit_income_form"):
            # Select income to edit by serial number
            serial_number = st.number_input(
                "Enter the Sr. No of the income you want to edit:", 
                min_value=1, 
                max_value=len(income_df), 
                step=1
            )
            selected_income = income_df.loc[serial_number - 1]

            st.write("Editing Income:")
            new_amount = st.number_input("New Amount", value=float(selected_income["Amount"]), step=0.01)
            new_source = st.text_input("New Source", value=selected_income["Source"])
            new_date = st.date_input("New Date", value=datetime.strptime(selected_income["Date"], "%Y-%m-%d").date())
            new_description = st.text_area("New Description", value=selected_income["Description"])

            submit_edit = st.form_submit_button("Save Changes")
            if submit_edit:
                edit_income(
                    selected_income["ID"], 
                    new_amount, 
                    new_source, 
                    new_date, 
                    new_description
                )
                st.success("Income record updated successfully!")
                st.rerun()
    else:
        st.info("No income records found.")

# Call the profile page
profile_page()

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib
from streamlit_option_menu import option_menu
import plotly.express as px
import bcrypt

# Set up page configuration
st.set_page_config(page_title="ExpenseTrade", page_icon="\U0001F512", layout="wide")

# Connect to SQLite databases
users_conn = sqlite3.connect('users.db', check_same_thread=False)
users_cur = users_conn.cursor()

expenses_conn = sqlite3.connect('expenses.db', check_same_thread=False)
expenses_cur = expenses_conn.cursor()

income_conn = sqlite3.connect('income.db', check_same_thread=False)
income_cur = income_conn.cursor()

# Create Users table if it doesn't exist
users_cur.execute('''
CREATE TABLE IF NOT EXISTS users (
    name TEXT,
    username TEXT PRIMARY KEY,
    email TEXT,
    password TEXT
)
''')
users_conn.commit()

# Create Expenses table if it doesn't exist
expenses_cur.execute('''
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT,
    amount REAL,
    date DATE,
    category TEXT,
    description TEXT,
    FOREIGN KEY (owner) REFERENCES users(username)
)
''')
expenses_conn.commit()

# Create Income table if it doesn't exist
income_cur.execute('''
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT,
    amount REAL,
    source TEXT,
    date DATE,
    description TEXT,
    FOREIGN KEY (owner) REFERENCES users(username)
)
''')
income_conn.commit()

# Set default expense limit
DEFAULT_EXPENSE_LIMIT = 500

# Helper functions
def hash_password(password):
    """Hash a password for storing."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    """Check a hashed password against the user input."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def register_user(name, username, email, password):
    try:
        hashed_password = hash_password(password)
        users_cur.execute('''
        INSERT INTO users (name, username, email, password)
        VALUES (?, ?, ?, ?)
        ''', (name, username, email, hashed_password))
        users_conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def login_user(username, password):
    users_cur.execute('''
    SELECT name, username, password FROM users WHERE username = ?
    ''', (username,))
    user = users_cur.fetchone()
    if user and check_password(password, user[2]):
        return user[:2]  # Return name and username
    return None

# Load dataset and train model (once per session)
@st.cache_resource
def load_and_train_model():
    # Load dataset
    df = pd.read_csv("categories_dataset.csv")

    # Data preparation
    X = df['description']
    y = df['category']

    # Text vectorization
    vectorizer = TfidfVectorizer()
    X_vec = vectorizer.fit_transform(X)

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(X_vec, y, test_size=0.2, random_state=42)

    # Train model
    model = RandomForestClassifier()
    model.fit(X_train, y_train)

    # Save vectorizer and model for later use
    joblib.dump(vectorizer, "vectorizer.pkl")
    joblib.dump(model, "model.pkl")

    return vectorizer, model

vectorizer, model = load_and_train_model()

# Initialize session state
if "user" not in st.session_state:
    st.session_state["user"] = None

# Sidebar for navigation
with st.sidebar:
    st.image("expense.png", use_container_width=True)
    if st.session_state["user"]:
        if st.button("Logout"):
            st.session_state["user"] = None
            st.rerun()
    else:
        selected_action = option_menu(
            menu_title="Navigation",
            options=["Home", "Sign Up", "Login"],
            icons=["house", "person-plus", "box-arrow-in-right"],
            default_index=0,
        )

# Main Content
if not st.session_state["user"]:
    if selected_action == "Sign Up":
        st.header("Create a New Account")
        with st.form("sign_up_form", clear_on_submit=True):
            name = st.text_input("Full Name")
            username = st.text_input("Username")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")

            if st.form_submit_button("Sign Up"):
                if password != confirm_password:
                    st.error("Passwords do not match. Please try again.")
                elif register_user(name, username, email, password):
                    st.success("Account created successfully! Please log in.")
                else:
                    st.error("Username already exists. Please choose another.")

    elif selected_action == "Login":
        st.header("Login to Your Account")
        with st.form("login_form", clear_on_submit=True):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")

            if st.form_submit_button("Login"):
                user = login_user(username, password)
                if user:
                    st.session_state["user"] = user[0]
                    st.session_state["username"] = user[1]
                    st.success(f"Welcome back, {user[0]}!")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    else:
        st.header("Welcome to ExpenseTrade")
        st.write("Use the navigation menu on the left to sign up or log in.")

else:
    st.header(f"Welcome, {st.session_state['user']}!")
    st.header("This is your Dashboard!")
    st.divider()

    try:
        # Fetch income and expense data for the logged-in user
        username = st.session_state["username"]

        # Fetch income data from income.db
        income_data = income_cur.execute("SELECT date, amount, source, description FROM income WHERE owner = ?", (username,)).fetchall()

        # Fetch expense data from expenses.db
        expense_data = expenses_cur.execute("SELECT date, amount, category, description FROM expenses WHERE owner = ?", (username,)).fetchall()

        # Calculate total income, total expense, and remaining balance
        total_income = sum(data[1] for data in income_data)
        total_expense = sum(data[1] for data in expense_data)
        remaining = total_income - total_expense

        # Display income, expense, and remaining balance
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Income:", f"{total_income} INR")
        col2.metric("Total Expense:", f"{total_expense:,.1f} INR")
        col3.metric("Total Remaining:", f"{remaining:,.1f} INR")

        # Convert fetched data into pandas DataFrame for processing
        income_df = pd.DataFrame(income_data, columns=["Date", "Income", "Source", "Description"])
        expense_df = pd.DataFrame(expense_data, columns=["Date", "Expense", "Category", "Description"])

        # Merge income and expense data
        merged_df = pd.concat([income_df, expense_df], axis=0)

        # Extract month from the date for grouping
        merged_df["Month"] = pd.to_datetime(merged_df["Date"]).dt.month_name()

        # Group by month and sum the amounts
        grouped_df = merged_df.groupby("Month").sum().reset_index()

        # Define the order for months
        month_order = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

        # Set the "Month" column as a categorical variable with the specified order
        merged_df["Month"] = pd.Categorical(merged_df["Month"], categories=month_order, ordered=True)

        # Create line chart for income and expense trends over months
        fig = px.line(grouped_df, x='Month', y=['Income', 'Expense'], title='Income and Expense over Months')
        fig.update_layout(xaxis_title='Month', yaxis_title='Amount (INR)', template='plotly_dark')

        # Group income by source for the bar plot
        income_grouped = income_df.groupby("Source").sum().reset_index()

        # Bar plot for total income by source
        fig2 = px.bar(income_grouped, x='Source', y='Income', title='Total Income by Source', color='Source')
        fig2.update_layout(xaxis_title='Source', yaxis_title='Total Income (INR)', template='plotly_dark')

        # Group expense by category for the bar plot
        expense_grouped = expense_df.groupby("Category").sum().reset_index()

        # Bar plot for total expenses by category
        fig3 = px.bar(expense_grouped, x='Category', y='Expense', title='Total Expenses by Category', color='Category')
        fig3.update_layout(xaxis_title='Category', yaxis_title='Total Expenses (INR)', template='plotly_dark')

        # Scatter plot for Income vs Expense by Category
        income_expense_grouped = merged_df.groupby(["Month", "Category"]).sum().reset_index()

        # Stacked bar chart: Income and Expense by Month and Category
        fig4 = px.bar(
            income_expense_grouped,
            x="Month",
            y=["Income", "Expense"],
            color="Category",
            title="Income and Expense by Month and Category",
            barmode="stack",
            labels={"value": "Amount (INR)", "variable": "Type", "Month": "Month"},
        )
        fig4.update_layout(xaxis_title="Month", yaxis_title="Total Amount (INR)", template="plotly_dark")
        
        # Layout for the charts: Using columns to split them nicely
        col1, col2 = st.columns(2)

        with col1:
            st.plotly_chart(fig)  # Line chart: Income vs Expense over months

        with col2:
            st.plotly_chart(fig2)  # Bar chart: Total Income by Source

        with col1:
            st.plotly_chart(fig3)  # Bar chart: Total Expenses by Category

        with col2:
            st.plotly_chart(fig4)  # Scatter plot: Income vs Expense by Category

    except Exception as e:
        st.error("Dashboard cannot be loaded when your TOTAL EXPENSE is NOT set(0.00)")

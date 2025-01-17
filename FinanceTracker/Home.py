import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib
import plotly.express as px
from streamlit_option_menu import option_menu

# Set up page configuration
st.set_page_config(page_title="ExpenseTrade", page_icon="🔐", layout="wide")

# Connect to SQLite database
conn = sqlite3.connect('users.db', check_same_thread=False)
cur = conn.cursor()

# Create Users table if it doesn't exist
cur.execute('''
CREATE TABLE IF NOT EXISTS users (
    name TEXT,
    username TEXT PRIMARY KEY,
    email TEXT,
    password TEXT
)
''')
conn.commit()

# Create Expenses table if it doesn't exist
expenses_conn = sqlite3.connect('expenses.db', check_same_thread=False)
expenses_cur = expenses_conn.cursor()
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

# Set default expense limit
DEFAULT_EXPENSE_LIMIT = 500

# Helper functions
def register_user(name, username, email, password):
    try:
        cur.execute('''
        INSERT INTO users (name, username, email, password)
        VALUES (?, ?, ?, ?)
        ''', (name, username, email, password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def login_user(username, password):
    cur.execute('''
    SELECT name, username FROM users WHERE username = ? AND password = ?
    ''', (username, password))
    return cur.fetchone()

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
# Sidebar for navigation
with st.sidebar:
    st.image("expense.png", use_container_width=True)
    st.title("User Authentication")
    if st.session_state["user"]:
        st.write(f"Logged in as {st.session_state['user']}")
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
    st.write("You are now logged in.")
    st.divider()

    # Tabs for dashboard, adding expenses, and expense history
    tab1, tab2, tab3 = st.tabs(["Dashboard", "Add Expense", "Expense History"])

    # Tab2: Add Expense
    with tab2:
        st.title("Add Expense")

        with st.form("expense_form"):
            amount = st.number_input("Amount", min_value=0.0, step=0.01)
            description = st.text_area("Description", placeholder="Enter expense details")
            predicted_category = ""

            if description:
                description_vec = vectorizer.transform([description])
                predicted_category = model.predict(description_vec)[0]

            category = st.selectbox("Category", [predicted_category] + ["Food", "Transport", "Entertainment", "Bills", "Others"], index=0)
            expense_date = st.date_input("Expense Date", max_value=datetime.now().date())

            submitted = st.form_submit_button("Add Expense")

            if submitted:
                if not amount or not description:
                    st.error("Amount and Description are required.")
                elif amount > DEFAULT_EXPENSE_LIMIT:
                    st.error(f"Expense exceeds the limit of {DEFAULT_EXPENSE_LIMIT} INR.")
                else:
                    try:
                        # Insert expense into the database
                        query = '''
                        INSERT INTO expenses (owner, amount, date, category, description)
                        VALUES (?, ?, ?, ?, ?)
                        '''
                        expenses_cur.execute(query, (st.session_state["username"], amount, expense_date, category, description))
                        expenses_conn.commit()

                        st.success("Expense added successfully!")
                    except sqlite3.Error as e:
                        st.error(f"An error occurred: {e}")

    # Tab3: Expense History
    with tab3:
        st.title("Expense History")

        # Fetch expenses for the logged-in user
        query = '''
        SELECT id, amount, date, category, description
        FROM expenses
        WHERE owner = ?
        '''
        expenses = expenses_cur.execute(query, (st.session_state["username"],)).fetchall()

        # Convert data to a pandas DataFrame
        columns = ["ID", "Amount", "Date", "Category", "Description"]
        expenses_df = pd.DataFrame(expenses, columns=columns)

        # Sorting
        sort_order = st.selectbox("Sort by:", ["Date (Newest First)", "Date (Oldest First)", "Amount (High to Low)", "Amount (Low to High)"])
        if "Date" in sort_order:
            expenses_df = expenses_df.sort_values(by="Date", ascending="Oldest" in sort_order)
        elif "Amount" in sort_order:
            expenses_df = expenses_df.sort_values(by="Amount", ascending="Low" in sort_order)

        # Display paginated table
        page_size = 5
        total_pages = len(expenses_df) // page_size + (len(expenses_df) % page_size > 0)
        page = st.number_input("Page", min_value=1, max_value=total_pages, step=1)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        st.table(expenses_df.iloc[start_idx:end_idx])

        # Edit Expense
        selected_expense_id = st.selectbox("Select Expense to Edit:", expenses_df["ID"])
        if selected_expense_id:
            expense_details = expenses_df[expenses_df["ID"] == selected_expense_id].iloc[0]

            with st.form("edit_expense_form"):
                st.write(f"Editing Expense ID: {selected_expense_id}")
                amount = st.number_input("Amount", value=expense_details["Amount"], min_value=0.0, step=0.01)
                category = st.text_input("Category", value=expense_details["Category"])
                description = st.text_area("Description", value=expense_details["Description"])
                expense_date = st.date_input("Date", value=datetime.strptime(expense_details["Date"], "%Y-%m-%d").date())

                submitted = st.form_submit_button("Update Expense")
                if submitted:
                    try:
                        update_query = '''
                        UPDATE expenses
                        SET amount = ?, date = ?, category = ?, description = ?
                        WHERE id = ?
                        '''
                        expenses_cur.execute(update_query, (amount, expense_date, category, description, selected_expense_id))
                        expenses_conn.commit()
                        st.success("Expense updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

    with tab1:
        st.title("My Dashboard")

        # Finance Data
        username = st.session_state["username"]
        conn = sqlite3.connect('data.db', check_same_thread=False)
        cur = conn.cursor()

        income_data = cur.execute("SELECT period, amount, category FROM finance_data WHERE type = 'Income' AND username = ?", (username,)).fetchall()
        expense_data = cur.execute("SELECT period, amount, category FROM finance_data WHERE type = 'Expense' AND username = ?", (username,)).fetchall()

        total_income = sum(data[1] for data in income_data)
        total_expense = sum(data[1] for data in expense_data)
        remaining = total_income - total_expense

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Income:", f"{total_income} INR")
        col2.metric("Total Expense:", f"{total_expense} INR")
        col3.metric("Total Remaining:", f"{remaining} INR")

        # Convert fetched data into pandas DataFrame
        income_df = pd.DataFrame(income_data, columns=["Period", "Income", "Category"])
        expense_df = pd.DataFrame(expense_data, columns=["Period", "Expense", "Category"])

        # Concatenate income and expense data
        merged_df = pd.concat([income_df, expense_df])

        # Extract month and year from the period
        merged_df["Month"] = merged_df["Period"].str.split("_").str[1]

        # Group by month and sum the amounts
        grouped_df = merged_df.groupby("Month").sum().reset_index()

        # Create a line chart for income and expense
        month_order = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

        # Convert the "Month" column to categorical data type with the specified order
        merged_df["Month"] = pd.Categorical(merged_df["Month"], categories=month_order, ordered=True)

        neon_colors = ['#FF005E', '#F30476', '#E7098E', '#DC0DA6', '#D011BD', '#C416D5', '#B81AED', '#4361ee', '#4895ef', '#4cc9f0']
        neon_green_palette = ['#2b9348', '#3eaf7c', '#57cc99', '#64dfdf', '#72efdd', '#64dfdf', '#72efdd', '#64dfdf', '#50c9c3', '#40b3a2']

        # Create a line chart for income and expense
        fig = px.line(grouped_df, x='Month', y=['Income', 'Expense'], title='Income and Expense over Months')
        fig.update_layout(xaxis_title='Month', yaxis_title='Amount (INR)')

        # Group by category and sum the income for each category
        income_grouped = income_df.groupby("Category").sum().reset_index()

        # Create a bar plot for total income by category
        fig2 = px.bar(income_grouped, x='Category', y='Income', title='Total Income by Category',color='Category', color_discrete_sequence=neon_green_palette)
        fig2.update_layout(xaxis_title='Category', yaxis_title='Total Income (INR)')

        # Group by category and sum the income for each category
        expense_grouped = expense_df.groupby("Category").sum().reset_index()

        # Create a bar plot for total income by category
        fig3 = px.bar(expense_grouped, x='Category', y='Expense', title='Total Expenses by Category', color='Category', color_discrete_sequence=neon_colors)
        fig3.update_layout(xaxis_title='Category', yaxis_title='Total Expenses (INR)')

        fig4 = px.scatter(merged_df, x='Income', y='Expense', color='Category', 
                 title='Income vs Expense by Category', 
                 labels={'Income': 'Total Income (INR)', 'Expense': 'Total Expense (INR)'})
        fig4.update_layout(xaxis_title='Total Income (INR)', yaxis_title='Total Expense (INR)')

        col1, col2 = st.columns(2)

        with col1:
            st.plotly_chart(fig)  # Replace fig1 with the chart variable for the first chart

        with col2:
            st.plotly_chart(fig2)  # Replace fig2 with the chart variable for the second chart

        with col1:
            st.plotly_chart(fig3)  # Replace fig3 with the chart variable for the third chart
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import joblib

# Connect to the shared SQLite database (data.db)
conn = sqlite3.connect('data.db', check_same_thread=False)
cur = conn.cursor()

# conn = sqlite3.connect('expenses.db', check_same_thread=False)
# cur = conn.cursor()
 
 

# Load vectorizer and model
vectorizer = joblib.load("vectorizer.pkl")
model = joblib.load("model.pkl")

# Check if user is logged in
if "user" not in st.session_state or not st.session_state["user"]:
    st.error("Please log in to access this page.")
    st.stop()

# Main content of expense.py
tab1, tab2 = st.tabs(["Add Expense", "Expense History"])

# Tab 1: Add Expense
with tab1:
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
            else:
                try:
                    # Insert expense into the data.db database
                    query = '''
                    INSERT INTO finance_data (username, amount, period, category, type)
                    VALUES (?, ?, ?, ?, ?)
                    '''
                    cur.execute(query, (
                        st.session_state["username"],
                        amount,
                        expense_date.strftime("%Y_%B"),  # Store period as 'Year_Month'
                        category,
                        "Expense"
                    ))
                    conn.commit()

                    st.success("Expense added successfully!")
                except sqlite3.Error as e:
                    st.error(f"An error occurred: {e}")

# Tab 2: Expense History
with tab2:
    
    st.title("Expense History")

    # Fetch expenses for the logged-in user
    query = '''
    SELECT id, amount, period, category, description
    FROM finance_data
    WHERE username = ? AND type = "Expense"
    '''
    expenses = cur.execute(query, (st.session_state["username"],)).fetchall()

    # Convert data to a pandas DataFrame
    columns = ["ID", "Amount", "Period", "Category", "Description"]
    expenses_df = pd.DataFrame(expenses, columns=columns)

    if not expenses_df.empty:
        # Add a Serial Number column for user-specific indexing
        expenses_df["Sr No"] = range(1, len(expenses_df) + 1)

        # Drop the ID column to hide it from the user
        display_df = expenses_df.drop(columns=["ID"])
        display_df = display_df[["Sr No", "Amount", "Period", "Category", "Description"]]
        display_df = display_df.reset_index(drop=True)

        # Sorting
        sort_order = st.selectbox(
            "Sort by:", 
            ["Period (Newest First)", "Period (Oldest First)", "Amount (Low to High)", "Amount (High to Low)", "Sr No (Ascending)", "Sr No (Descending)"]
        )

        # Handle sorting
        if "Period" in sort_order:
            display_df = display_df.sort_values(by="Period", ascending="Oldest" in sort_order)
        elif "Amount" in sort_order:
            display_df = display_df.sort_values(by="Amount", ascending="Low to High" in sort_order)
        elif "Sr No" in sort_order:
            display_df = display_df.sort_values(by="Sr No", ascending="Ascending" in sort_order)

        # Display paginated table
        page_size = 5
        total_pages = len(display_df) // page_size + (len(display_df) % page_size > 0)
        page = st.number_input("Page", min_value=1, max_value=total_pages, step=1)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        # Use st.write() to display the table without index
        st.write(display_df.iloc[start_idx:end_idx].to_html(index=False, escape=False), unsafe_allow_html=True)
    else:
        st.write("No expenses recorded yet.")

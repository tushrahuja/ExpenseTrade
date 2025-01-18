import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib

# Connect to SQLite database
expenses_conn = sqlite3.connect('expenses.db', check_same_thread=False)
expenses_cur = expenses_conn.cursor()

# Create Expenses table if it doesn't exist
expenses_cur.execute('''
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT,
    amount REAL,
    date DATE,
    category TEXT,
    description TEXT
)
''')
expenses_conn.commit()

# Set default expense limit
DEFAULT_EXPENSE_LIMIT = 500

# Load dataset and train model
@st.cache_resource
def load_and_train_model():
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

# Main function to render tabs
def main():
    tab_1, tab_2 = st.tabs(["Add Expense", "Expense History"])

    with tab_1:
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
                        expenses_cur.execute(query, (st.session_state.get("username", "guest"), amount, expense_date, category, description))
                        expenses_conn.commit()

                        st.success("Expense added successfully!")
                    except sqlite3.Error as e:
                        st.error(f"An error occurred: {e}")

    with tab_2:
        st.title("Expense History")

        # Fetch expenses for the logged-in user
        query = '''
        SELECT id, amount, date, category, description
        FROM expenses
        WHERE owner = ?
        '''
        expenses = expenses_cur.execute(query, (st.session_state.get("username", "guest"),)).fetchall()

        # Convert data to a pandas DataFrame
        columns = ["ID", "Amount", "Date", "Category", "Description"]
        expenses_df = pd.DataFrame(expenses, columns=columns)

        # Add a Serial Number column for user-specific indexing
        expenses_df["Sr No"] = range(1, len(expenses_df) + 1)

        # Drop the ID column to hide it from the user
        display_df = expenses_df.drop(columns=["ID"])
        display_df = display_df[["Sr No", "Amount", "Date", "Category", "Description"]]
        display_df = display_df.reset_index(drop=True)

        # Sorting
        sort_order = st.selectbox(
            "Sort by:", 
            ["Date (Newest First)", "Date (Oldest First)", "Amount (Low to High)", "Amount (High to Low)", "Sr No (Ascending)", "Sr No (Descending)"]
        )

        # Handle sorting
        if "Date" in sort_order:
            display_df = display_df.sort_values(by="Date", ascending="Oldest" in sort_order)
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
        st.subheader("Edit an Expense")
        selected_serial_number = st.selectbox("Select Serial Number to Edit:", display_df["Sr No"])
        if selected_serial_number:
            # Map the serial number to the actual expense entry
            expense_details = expenses_df[expenses_df["Sr No"] == selected_serial_number].iloc[0]

            with st.form("edit_expense_form"):
                st.write(f"Editing Expense with Serial Number: {selected_serial_number}")
                # Display editable fields
                amount = st.number_input("Amount", value=expense_details["Amount"], min_value=0.0, step=0.01)
                category = st.text_input("Category", value=expense_details["Category"])
                description = st.text_area("Description", value=expense_details["Description"])
                expense_date = st.date_input("Date", value=datetime.strptime(expense_details["Date"], "%Y-%m-%d").date())

                # Submit button to update the expense
                submitted = st.form_submit_button("Update Expense")
                if submitted:
                    try:
                        # Update the selected expense in the database
                        update_query = '''
                        UPDATE expenses
                        SET amount = ?, date = ?, category = ?, description = ?
                        WHERE id = ?
                        '''
                        expenses_cur.execute(update_query, (amount, expense_date, category, description, expense_details["ID"]))
                        expenses_conn.commit()
                        st.success("Expense updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()

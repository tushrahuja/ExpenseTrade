import streamlit as st
import sqlite3
import pandas as pd
import calendar
from datetime import datetime
from streamlit_option_menu import option_menu
import plotly.express as px
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib

# Connect to SQLite database
if "user" not in st.session_state or st.session_state["user"] is None:
    st.warning("Please log in to access this page.")
    st.stop()
    
expenses_conn = sqlite3.connect('expenses.db', check_same_thread=False)
expenses_cur = expenses_conn.cursor()

income_conn = sqlite3.connect('income.db', check_same_thread=False)
income_cur = income_conn.cursor()

# Create Expenses table if it doesn't exist
expenses_cur.execute(''' 
CREATE TABLE IF NOT EXISTS expenses ( 
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    owner TEXT, 
    amount REAL, 
    date DATE, 
    category TEXT, 
    description TEXT 
) ''')
expenses_conn.commit()

# Create Income table if it doesn't exist
income_cur.execute(''' 
CREATE TABLE IF NOT EXISTS income ( 
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    owner TEXT, 
    amount REAL, 
    date DATE, 
    source TEXT, 
    description TEXT 
) ''')
income_conn.commit()

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

# Helper function to check if user has added income
def has_income(owner):
    query = "SELECT COUNT(*) FROM income WHERE owner = ?"
    try:
        result = income_cur.execute(query, (owner,)).fetchone()
        return result[0] > 0
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return False

# Main function to render tabs
def main():
    # Check if user has income
    owner = st.session_state.get("username", "guest")
    if not has_income(owner):
        st.warning("Please add income in your profile before managing expenses.")
        return

    tab_1, tab_2, tab_3 = st.tabs(["Manage Expense", "Expense History", "Expense Summary"])

    with tab_1:
        st.title("Manage Expense")

        menu_action = option_menu(
            menu_title=None,
            options=["Add Expense", "Edit Expense"],
            icons=["plus-circle", "edit"],
            orientation="horizontal",
        )

        if menu_action == "Add Expense":
            st.subheader("Add Expense")

            with st.form("expense_form"):
                amount = st.number_input("Amount", min_value=0.0, step=0.01)
                description = st.text_area("Description")
                predicted_category = ""

                if description:
                    description_vec = vectorizer.transform([description])
                    predicted_category = model.predict(description_vec)[0]

                category = st.selectbox(
                    "Category", [predicted_category] + ["Food", "Transport", "Entertainment", "Bills", "Others"], index=0
                )
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
                            expenses_cur.execute(query, (owner, amount, expense_date, category, description))
                            expenses_conn.commit()

                            st.success("Expense added successfully!")
                        except sqlite3.Error as e:
                            st.error(f"An error occurred: {e}")

        elif menu_action == "Edit Expense":
            st.subheader("Edit Expense")

            # Fetch all expenses for the logged-in user
            query = '''
            SELECT id, amount, date, category, description
            FROM expenses
            WHERE owner = ?
            '''
            expenses = expenses_cur.execute(query, (owner,)).fetchall()

            if not expenses:
                st.warning("No expenses available to edit.")
            else:
                # Display expenses with their IDs in a select box for editing
                expense_ids = [f"Sr No: {i+1} - {exp[4]} ({exp[1]} INR)" for i, exp in enumerate(expenses)]
                expense_ids_map = {f"Sr No: {i+1} - {exp[4]} ({exp[1]} INR)": exp[0] for i, exp in enumerate(expenses)}

                selected_expense_sr_no = st.selectbox("Select Expense to Edit", expense_ids)

                if selected_expense_sr_no:
                    # Get the corresponding expense ID using Sr No
                    expense_id = expense_ids_map[selected_expense_sr_no]

                    # Get the selected expense's details from the database
                    expense_details = expenses_cur.execute(
                        "SELECT amount, date, category, description FROM expenses WHERE id = ?", (expense_id,)
                    ).fetchone()

                    if expense_details:
                        amount, expense_date, category, description = expense_details

                        with st.form("edit_expense_form"):
                            # Fill in the current values in the form fields
                            amount = st.number_input("Amount", value=amount, min_value=0.0, step=0.01)
                            category = st.text_input("Category", value=category)
                            description = st.text_area("Description", value=description)
                            expense_date = st.date_input("Date", value=datetime.strptime(expense_date, "%Y-%m-%d").date())

                            submitted = st.form_submit_button("Update Expense")

                            if submitted:
                                with st.spinner('Updating expense...'):
                                    try:
                                        # Update the expense in the database using the expense ID
                                        update_query = '''
                                        UPDATE expenses
                                        SET amount = ?, date = ?, category = ?, description = ?
                                        WHERE id = ?
                                        '''
                                        expenses_cur.execute(update_query, (amount, expense_date, category, description, expense_id))
                                        expenses_conn.commit()
                                        st.success("Expense updated successfully!")
                                        st.rerun()  # Rerun the app to reflect changes
                                    except Exception as e:
                                        st.error(f"An error occurred: {e}")

    with tab_2:
        st.title("Expense History")

        query = '''
        SELECT id, amount, date, category, description
        FROM expenses
        WHERE owner = ?
        '''
        expenses = expenses_cur.execute(query, (owner,)).fetchall()

        if not expenses:
            st.warning("No expenses found.")
        else:
            columns = ["ID", "Amount", "Date", "Category", "Description"]
            expenses_df = pd.DataFrame(expenses, columns=columns)

            # Add serial numbers
            expenses_df["Sr No"] = range(1, len(expenses_df) + 1)
            display_df = expenses_df.drop(columns=["ID"])

            # Sorting
            sort_order = st.selectbox(
                "Sort by:",
                ["Date (Newest First)", "Date (Oldest First)", "Amount (High to Low)", "Amount (Low to High)", "Sr No"],
            )

            if "Date" in sort_order:
                display_df = display_df.sort_values(by="Date", ascending="Oldest" in sort_order)
            elif "Amount" in sort_order:
                display_df = display_df.sort_values(by="Amount", ascending="Low to High" in sort_order)

            st.table(display_df)

    with tab_3:
        st.title("Expense Summary")

        income_periods = income_cur.execute(
            "SELECT DISTINCT strftime('%Y-%m', date) FROM income WHERE owner = ?",
            (owner,)
        ).fetchall()
        expense_periods = expenses_cur.execute(
            "SELECT DISTINCT strftime('%Y-%m', date) FROM expenses WHERE owner = ?",
            (owner,)
        ).fetchall()

        periods = sorted(set([p[0] for p in income_periods] + [p[0] for p in expense_periods]))

        with st.form("saved_periods"):
            selected_period = st.selectbox("Select Period (YYYY-MM):", periods)
            submitted = st.form_submit_button("Plot Period")

            if submitted:
                start_date = f"{selected_period}-01"
                end_date = f"{selected_period}-{calendar.monthrange(int(selected_period[:4]), int(selected_period[5:7]))[1]}"

                income_cur.execute(''' 
                    SELECT i.amount, i.source, i.date, i.description 
                    FROM income i 
                    WHERE i.owner = ? AND i.date BETWEEN ? AND ? 
                ''', (owner, start_date, end_date))
                income_data = income_cur.fetchall()

                expenses_cur.execute(''' 
                    SELECT amount, category, date, description 
                    FROM expenses 
                    WHERE owner = ? AND date BETWEEN ? AND ? 
                ''', (owner, start_date, end_date))
                expense_data = expenses_cur.fetchall()

                incomes = {data[1]: data[0] for data in income_data}
                expenses = {data[1]: data[0] for data in expense_data}

                total_income = sum(incomes.values())
                total_expense = sum(expenses.values())
                remaining = total_income - total_expense

                col1, col2, col3 = st.columns(3)
                col1.metric("Total Income:", f"{total_income:,} INR")
                col2.metric("Total Expense:", f"{total_expense:,} INR")
                col3.metric("Total Remaining:", f"{remaining:,} INR")

                income_df = pd.DataFrame.from_dict(incomes, orient='index', columns=['Amount']).reset_index()
                income_df.rename(columns={'index': 'Source'}, inplace=True)

                expense_df = pd.DataFrame.from_dict(expenses, orient='index', columns=['Amount']).reset_index()
                expense_df.rename(columns={'index': 'Category'}, inplace=True)

                fig1 = px.pie(income_df, values='Amount', names='Source', title="Income Breakdown")
                fig2 = px.pie(expense_df, values='Amount', names='Category', title="Expense Breakdown")

                st.plotly_chart(fig1)
                st.plotly_chart(fig2)

                st.subheader("Detailed Income Data")
                st.table(income_df)

                st.subheader("Detailed Expense Data")
                st.table(expense_df)

if __name__ == "__main__":
    main()

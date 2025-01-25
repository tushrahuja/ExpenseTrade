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
import numpy as np
from sklearn.linear_model import LinearRegression

# Connect to SQLite database
if "user" not in st.session_state or st.session_state["user"] is None:
    st.warning("Please log in to access this page.")
    st.stop()

expenses_conn = sqlite3.connect('Main/data/expenses.db', check_same_thread=False)
expenses_cur = expenses_conn.cursor()

income_conn = sqlite3.connect('Main/data/income.db', check_same_thread=False)
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
DEFAULT_EXPENSE_LIMIT = 1000

# Load dataset and train model
@st.cache_resource
def load_and_train_model():
    df = pd.read_csv("Main/data/categories_dataset.csv")

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
    joblib.dump(vectorizer, "Main/models/vectorizer.pkl")
    joblib.dump(model, "Main/models/model.pkl")

    return vectorizer, model

vectorizer, model = load_and_train_model()

with st.sidebar:
    st.image("Main/assets/expense.png", use_container_width=True)
    if st.session_state["user"]:
        if st.button("Logout"):
            st.session_state["user"] = None
            st.rerun()

# Helper function to check if user has added income
def has_income(owner):
    query = "SELECT COUNT(*) FROM income WHERE owner = ?"
    try:
        result = income_cur.execute(query, (owner,)).fetchone()
        return result[0] > 0
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return False

# Helper function to fetch historical expense data
def fetch_expense_data(owner):
    query = '''
    SELECT date, SUM(amount) AS total_expense
    FROM expenses
    WHERE owner = ?
    GROUP BY date
    ORDER BY date
    '''
    return expenses_cur.execute(query, (owner,)).fetchall()

# Helper function to forecast expenses
def forecast_expenses(expense_data):
    if not expense_data:
        return None, None

    df = pd.DataFrame(expense_data, columns=["Date", "Total Expense"])
    df['Date'] = pd.to_datetime(df['Date'])
    df['Month'] = df['Date'].dt.to_period('M').astype(str)
    df_grouped = df.groupby('Month')['Total Expense'].sum().reset_index()
    df_grouped['Month Index'] = np.arange(len(df_grouped))

    X = df_grouped[['Month Index']]
    y = df_grouped['Total Expense']
    model = LinearRegression()
    model.fit(X, y)

    future_indices = np.arange(len(df_grouped), len(df_grouped) + 3).reshape(-1, 1)
    future_expenses = model.predict(future_indices)

    future_months = pd.date_range(df_grouped['Month'].iloc[-1], periods=4, freq='M')[1:].strftime('%Y-%m').tolist()

    forecast_df = pd.DataFrame({"Month": future_months, "Predicted Expense": future_expenses})

    return df_grouped, forecast_df

# Main function to render tabs
def main():
    # Check if user has income
    owner = st.session_state.get("username", "guest")
    if not has_income(owner):
        st.warning("Please add income in your profile before managing expenses.")
        return

    tab_1, tab_2, tab_3, tab_4 = st.tabs(["Manage Expense", "Expense History", "Expense Summary", "Expense Forecast"])

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
                    "Category", [predicted_category] + ["Food", "Transport", "Entertainment", "Bills", "Others"] if predicted_category else ["  ","Food", "Transport", "Entertainment", "Bills", "Others"],
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
            expenses_df.insert(0, "Sr No", range(1, len(expenses_df) + 1))
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
                
            
            st.write(display_df.to_html(index=False), unsafe_allow_html=True)

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
                    SELECT SUM(i.amount), i.source 
                    FROM income i 
                    WHERE i.owner = ? AND i.date BETWEEN ? AND ?
                    GROUP BY i.source
                ''', (owner, start_date, end_date))
                income_data = income_cur.fetchall()

                expenses_cur.execute(''' 
                    SELECT SUM(amount), category 
                    FROM expenses 
                    WHERE owner = ? AND date BETWEEN ? AND ?
                    GROUP BY category
                ''', (owner, start_date, end_date))
                expense_data = expenses_cur.fetchall()

                total_income = sum([data[0] for data in income_data])
                total_expense = sum([data[0] for data in expense_data])
                remaining = total_income - total_expense

                col1, col2, col3 = st.columns(3)
                col1.metric("Total Income:", f"{total_income:,} INR")
                col2.metric("Total Expense:", f"{total_expense:,.1f} INR")
                col3.metric("Total Remaining:", f"{remaining:,.1f} INR")

                income_df = pd.DataFrame(income_data, columns=['Amount', 'Source'])
                expense_df = pd.DataFrame(expense_data, columns=['Amount', 'Category'])

                fig1 = px.pie(income_df, values='Amount', names='Source', title="Income Breakdown")
                fig2 = px.pie(expense_df, values='Amount', names='Category', title="Expense Breakdown")

                st.plotly_chart(fig1)
                st.plotly_chart(fig2)

                st.subheader("Detailed Income Data")
                st.table(income_df)

                st.subheader("Detailed Expense Data")
                st.table(expense_df)

    with tab_4:
        st.title("Expense Forecast")
        expense_data = fetch_expense_data(owner)
        historical_data, forecast_data = forecast_expenses(expense_data)
        if forecast_data is not None:
            st.table(forecast_data)
            fig = px.line(pd.concat([historical_data, forecast_data]), x="Month", y="Predicted Expense", title="Expense Forecast")
            st.plotly_chart(fig)
        else:
            st.warning("Not enough data for forecasting.")

if __name__ == "__main__":
    main()

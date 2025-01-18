import streamlit as st
import yfinance as yf
import pandas as pd
import sqlite3
from datetime import datetime
import calendar
from streamlit_option_menu import option_menu
import plotly.express as px

st.set_page_config(layout="wide")

# Ensure the user is logged in
if "user" not in st.session_state or st.session_state["user"] is None:
    st.warning("Please log in to access this page.")
    st.stop()

# Connect to SQLite databases
expenses_conn = sqlite3.connect('expenses.db', check_same_thread=False)
expenses_cur = expenses_conn.cursor()

income_conn = sqlite3.connect('income.db', check_same_thread=False)
income_cur = income_conn.cursor()

# Create expenses and income tables if they don't exist
expenses_cur.execute('''
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT,
    date DATE,
    amount REAL,
    category TEXT,
    description TEXT
)
''')
expenses_conn.commit()

income_cur.execute('''
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT,
    date DATE,
    amount REAL,
    source INTEGER,
    description TEXT,
    FOREIGN KEY (source) REFERENCES sources (id)
)
''')
income_cur.execute('''
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    owner TEXT
)
''')
income_conn.commit()

# Add or update income and expense data
def add_or_update_income(owner, date, amount, source, description):
    income_cur.execute('''
        INSERT INTO income (owner, date, amount, source, description)
        VALUES (?, ?, ?, ?, ?)
    ''', (owner, date, amount, source, description))
    income_conn.commit()

def add_or_update_expense(owner, date, amount, category, description):
    expenses_cur.execute('''
        INSERT INTO expenses (owner, date, amount, category, description)
        VALUES (?, ?, ?, ?, ?)
    ''', (owner, date, amount, category, description))
    expenses_conn.commit()

# Fetch sources for income
def get_sources(owner):
    income_cur.execute("SELECT id, name FROM sources WHERE owner = ?", (owner,))
    return income_cur.fetchall()

# Fetch income and expense data
def get_income_data(owner, period):
    formatted_period = period.replace("_", "-")  # Convert period to YYYY-MM format
    income_cur.execute('''
        SELECT i.amount, s.name AS source, i.date, i.description 
        FROM income i 
        JOIN sources s ON i.source = s.id 
        WHERE i.owner = ? AND strftime('%Y-%m', i.date) = ?''', (owner, formatted_period))
    return income_cur.fetchall()

def get_expense_data(owner, period):
    formatted_period = period.replace("_", "-")  # Convert period to YYYY-MM format
    expenses_cur.execute('''
        SELECT amount, category, date, description 
        FROM expenses 
        WHERE owner = ? AND strftime('%Y-%m', date) = ?''', (owner, formatted_period))
    return expenses_cur.fetchall()

# Get the logged-in user's username
username = st.session_state["username"]

# Create tabs
tab1, tab2 = st.tabs(["Stock Prices", "Finance Tracker"])

with tab1:
    st.title("Stock Prices")
    excel_file = r"./FinanceTracker/Ticker_Company.xlsx"
    company_data = pd.read_excel(excel_file)

    company_names = company_data["Company_Name"].tolist()
    ticker_symbols = company_data["Symbol"].tolist()

    selected_company = st.selectbox("Select a Company", company_names)
    selected_ticker_symbol = ticker_symbols[company_names.index(selected_company)]

    st.write("Selected Ticker Symbol:", selected_ticker_symbol)

    if selected_ticker_symbol:
        tickerData = yf.Ticker(selected_ticker_symbol)
        tickerDf = tickerData.history(period='1d', start='2024-01-01', end=datetime.today())

        if not tickerDf.empty:
            st.line_chart(tickerDf.Close)
            st.caption('Chart for Closing Prices.')
            st.line_chart(tickerDf.Volume)
            st.caption('Chart for Stock Volume.')
        else:
            st.warning("No data available for the entered symbol. Please try again.")

with tab2:
    st.title("Income and Expense Tracker")
    incomes = get_sources(username)
    expenses = ["Rent", "Utilities", "Groceries", "Car", "Insurance", "Savings", "Miscellaneous"]
    currency = "INR"

    years = [datetime.today().year, datetime.today().year + 1]
    months = list(calendar.month_name[1:])

    selected = option_menu(
        menu_title=None,
        icons=["pencil-fill", "bar-chart-fill"],
        options=["Data Entry", "Data Visualization"], orientation="horizontal",
    )

    if selected == "Data Entry":
        with st.form("entry_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            month = col1.selectbox("Select Month", months, key='month')
            year = col2.selectbox("Select Year", years, key='year')

            with st.expander("Income"):
                for income in incomes:
                    st.number_input(f"{income[1]}:", min_value=0, format="%i", step=100, key=f"income_{income[0]}")
            with st.expander("Expenses"):
                for expense in expenses:
                    st.number_input(f"{expense}:", min_value=0, format="%i", step=100, key=f"expense_{expense}")
            with st.expander("Remarks"):
                comment = st.text_area("", placeholder="Enter Remarks")

            submitted = st.form_submit_button("Save Data")

            if submitted:
                period = f"{year}_{month}"
                for income in incomes:
                    amount = st.session_state[f"income_{income[0]}"]
                    if amount > 0:
                        add_or_update_income(username, f"{year}-{str(month).zfill(2)}-01", amount, income[0], comment)

                for expense in expenses:
                    amount = st.session_state[f"expense_{expense}"]
                    if amount > 0:
                        add_or_update_expense(username, f"{year}-{str(month).zfill(2)}-01", amount, expense, comment)

                st.success("Data Saved")

    elif selected == "Data Visualization":
        st.header("Data Visualization")

        # Fetch unique months with income or expenses
        income_periods = income_cur.execute(
            "SELECT DISTINCT strftime('%Y-%m', date) FROM income WHERE owner = ?",
            (username,)
        ).fetchall()
        expense_periods = expenses_cur.execute(
            "SELECT DISTINCT strftime('%Y-%m', date) FROM expenses WHERE owner = ?",
            (username,)
        ).fetchall()

        # Combine and sort unique periods
        periods = sorted(set([p[0] for p in income_periods] + [p[0] for p in expense_periods]))

        with st.form("saved_periods"):
            selected_period = st.selectbox("Select Period (YYYY-MM):", periods)
            submitted = st.form_submit_button("Plot Period")

            if submitted:
                # Adjust the date range for the entire selected month
                start_date = f"{selected_period}-01"
                end_date = f"{selected_period}-{calendar.monthrange(int(selected_period[:4]), int(selected_period[5:7]))[1]}"

                # Fetch all income and expenses for the month
                income_cur.execute('''
                    SELECT i.amount, i.source, i.date, i.description 
                    FROM income i 
                    WHERE i.owner = ? AND i.date BETWEEN ? AND ?
                ''', (username, start_date, end_date))
                income_data = income_cur.fetchall()

                expenses_cur.execute('''
                    SELECT amount, category, date, description 
                    FROM expenses 
                    WHERE owner = ? AND date BETWEEN ? AND ?
                ''', (username, start_date, end_date))
                expense_data = expenses_cur.fetchall()

                # Process fetched data
                incomes = {data[1]: data[0] for data in income_data}  # Source: Amount
                expenses = {data[1]: data[0] for data in expense_data}  # Category: Amount

                # Calculate total income, expenses, and remaining balance
                total_income = sum(incomes.values())
                total_expense = sum(expenses.values())
                remaining = total_income - total_expense

                # Display metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Income:", f"{total_income:,} {currency}")
                col2.metric("Total Expense:", f"{total_expense:,} {currency}")
                col3.metric("Total Remaining:", f"{remaining:,} {currency}")

                # Prepare dataframes for visualization
                income_df = pd.DataFrame.from_dict(incomes, orient='index', columns=['Amount']).reset_index()
                income_df.rename(columns={'index': 'Source'}, inplace=True)

                expense_df = pd.DataFrame.from_dict(expenses, orient='index', columns=['Amount']).reset_index()
                expense_df.rename(columns={'index': 'Category'}, inplace=True)

                # Plot pie charts for income and expenses
                fig1 = px.pie(income_df, values='Amount', names='Source', title="Income Breakdown")
                fig2 = px.pie(expense_df, values='Amount', names='Category', title="Expense Breakdown")

                st.plotly_chart(fig1)
                st.plotly_chart(fig2)

                # Display detailed tables
                st.subheader("Detailed Income Data")
                st.table(income_df)

                st.subheader("Detailed Expense Data")
                st.table(expense_df)

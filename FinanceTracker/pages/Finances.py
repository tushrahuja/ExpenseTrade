from matplotlib import pyplot as plt
import streamlit as st
import yfinance as yf
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
from streamlit_option_menu import option_menu

st.set_page_config(layout="wide")

# Ensure the user is logged in
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
expenses_cur.execute('''
CREATE TABLE IF NOT EXISTS stock_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT,
    stock_symbol TEXT,
    stock_name TEXT,
    purchase_date DATE,
    quantity INTEGER,
    purchase_price REAL
)
''')
income_conn.commit()
expenses_conn.commit()

# Add or update stock purchases
def add_stock_purchase(owner, stock_symbol, stock_name, purchase_date, quantity, purchase_price):
    expenses_cur.execute('''
        INSERT INTO stock_purchases (owner, stock_symbol, stock_name, purchase_date, quantity, purchase_price)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (owner, stock_symbol, stock_name, purchase_date, quantity, purchase_price))
    expenses_conn.commit()

# Fetch income, expense, and stock data
def get_income_data(owner):
    income_cur.execute("SELECT date, amount, source, description FROM income WHERE owner = ?", (owner,))
    return income_cur.fetchall()

def get_expense_data(owner):
    expenses_cur.execute("SELECT date, amount, category, description FROM expenses WHERE owner = ?", (owner,))
    return expenses_cur.fetchall()

def get_stock_data(owner):
    expenses_cur.execute('''
        SELECT stock_symbol, stock_name, purchase_date, quantity, purchase_price 
        FROM stock_purchases 
        WHERE owner = ?''', (owner,))
    return expenses_cur.fetchall()

@st.cache_resource
def fetch_stock_prices(symbols):
    symbols = [symbol for symbol in symbols if isinstance(symbol, str)]
    with st.spinner("Fetching stock data, please wait..."):
        data = yf.download(tickers=symbols, period="1d", group_by="ticker")
    stock_prices = {}
    for symbol in symbols:
        try:
            stock_prices[symbol] = data[symbol]["Close"].iloc[-1] if not data[symbol].empty else None
        except KeyError:
            stock_prices[symbol] = None
    return stock_prices

# Load the tailored dataset for NSE
@st.cache_data
def load_company_data():
    file_path = r"C:\CodingT\ExpenseTrade\FinanceTracker\Ticker_Company.xlsx"
    return pd.read_excel(file_path)


company_data = load_company_data()
ticker_symbols = company_data["Symbol"].tolist()

# Get the logged-in user's username
username = st.session_state["username"]

# Create tabs
tab1, tab2 = st.tabs(["Stock Prices", "Savings & Predictions"])

with tab1:
    st.title("Stock Prices")

    company_names = company_data["Company_Name"].tolist()
    selected_company = st.selectbox("Select a Company", company_names)
    selected_ticker_symbol = company_data.loc[company_data["Company_Name"] == selected_company, "Symbol"].iloc[0]

    st.write("Selected Ticker Symbol:", selected_ticker_symbol)

    if selected_ticker_symbol:
        tickerData = yf.Ticker(selected_ticker_symbol)
        tickerDf = tickerData.history(period='1d', start='2024-01-01', end=datetime.today())

        if not tickerDf.empty:
            st.metric("Closing Price", f"{tickerDf['Close'].iloc[-1]:.2f}")
            st.metric("Volume", f"{tickerDf['Volume'].iloc[-1]:,.0f}")
            fig_close = px.line(tickerDf, x=tickerDf.index, y="Close", title="Closing Prices", color_discrete_sequence=["green"])
            fig_volume = px.line(tickerDf, x=tickerDf.index, y="Volume", title="Stock Volume", color_discrete_sequence=["orange"])
            st.plotly_chart(fig_close)
            st.plotly_chart(fig_volume)
        else:
            st.warning("No data available for the entered symbol. Please try again.")

with tab2:
    st.title("Savings & Stock Predictions")
    selected_option = option_menu(
        menu_title=None,
        options=["View Savings", "Predict Stocks"],
        icons=["wallet", "graph-up"],
        orientation="horizontal",
    )

    income_data = get_income_data(username)
    expense_data = get_expense_data(username)

    total_income = sum(data[1] for data in income_data)
    total_expense = sum(data[1] for data in expense_data)
    remaining = total_income - total_expense

    if selected_option == "View Savings":
        st.metric("Total Savings", f"{remaining:,} INR")

    elif selected_option == "Predict Stocks":
        st.write("Based on your savings, consider the following top 10 cheapest stocks:")

        # Fetch stock prices
        stock_prices = fetch_stock_prices(ticker_symbols)

        suggested_stocks = []
        for _, row in company_data.iterrows():
            ticker_price = stock_prices.get(row['Symbol'])
            if ticker_price and ticker_price <= remaining:
                suggested_stocks.append({
                    'Company_Name': row['Company_Name'],
                    'Symbol': row['Symbol'],
                    'Price': ticker_price
                })

        suggested_stocks_df = pd.DataFrame(suggested_stocks)

        if not suggested_stocks_df.empty:
            suggested_stocks_df = suggested_stocks_df.sort_values(by="Price").head(10)
            for _, stock in suggested_stocks_df.iterrows():
                st.write(f"{stock['Company_Name']} ({stock['Symbol']}) - Price: {stock['Price']:.2f}")

            selected_stock = st.selectbox("Select a stock to purchase:", suggested_stocks_df['Symbol'].tolist())
            quantity = st.number_input("Enter quantity:", min_value=1, step=1)

            if st.button("Purchase Stock"):
                stock_name = suggested_stocks_df[suggested_stocks_df['Symbol'] == selected_stock]['Company_Name'].iloc[0]
                stock_price = suggested_stocks_df[suggested_stocks_df['Symbol'] == selected_stock]['Price'].iloc[0]
                add_stock_purchase(username, selected_stock, stock_name, datetime.today().strftime("%Y-%m-%d"), quantity, stock_price)
                st.success("Stock purchased successfully!")
        else:
            st.warning("No stocks match your savings amount.")

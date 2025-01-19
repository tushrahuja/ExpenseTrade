from matplotlib import pyplot as plt
import streamlit as st
import yfinance as yf
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import numpy as np
from sklearn.linear_model import LinearRegression
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

# Create stock_purchases table if it doesn't exist
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
expenses_conn.commit()

# Add or update stock purchases
def add_stock_purchase(owner, stock_symbol, stock_name, purchase_date, quantity, purchase_price):
    expenses_cur.execute('''
        INSERT INTO stock_purchases (owner, stock_symbol, stock_name, purchase_date, quantity, purchase_price)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (owner, stock_symbol, stock_name, purchase_date, quantity, purchase_price))
    expenses_conn.commit()

# Fetch income and expense data
def get_income_data(owner):
    return income_cur.execute(
        "SELECT date, amount, source, description FROM income WHERE owner = ?", (owner,)
    ).fetchall()

def get_expense_data(owner):
    return expenses_cur.execute(
        "SELECT date, amount, category, description FROM expenses WHERE owner = ?", (owner,)
    ).fetchall()

# Fetch stock purchases
def get_stock_data(owner):
    return expenses_cur.execute('''
        SELECT stock_symbol, stock_name, purchase_date, quantity, purchase_price 
        FROM stock_purchases 
        WHERE owner = ?''', (owner,)).fetchall()

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

@st.cache_resource
def load_company_data():
    file_path = r"C:\CodingT\ExpenseTrade\FinanceTracker\Ticker_Company.xlsx"
    return pd.read_excel(file_path)

company_data = load_company_data()
ticker_symbols = company_data["Symbol"].tolist()

# Get the logged-in user's username
username = st.session_state["username"]

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(["Stock Prices", "Savings & Predictions", "Stock Purchase", "Stock Forecast"])

# Tab 1: Stock Prices
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

# Tab 2: Savings & Stock Predictions
suggested_stocks = []  # To share between tabs
with tab2:
    st.title("Savings & Stock Predictions")
    selected_option = option_menu(
        menu_title=None,
        options=["View Savings", "Predict Stocks"],
        icons=["wallet", "graph-up"],
        orientation="horizontal",
    )

    # Fetch income and expense data to calculate remaining balance
    income_data = get_income_data(username)
    expense_data = get_expense_data(username)

    total_income = sum(data[1] for data in income_data)
    total_expense = sum(data[1] for data in expense_data)
    remaining = total_income - total_expense

    if selected_option == "View Savings":
        st.metric("Total Savings", f"{remaining:,} INR")

    elif selected_option == "Predict Stocks":
        st.write("Based on your savings, consider the following top 10 cheapest stocks:")

        if remaining <= 0:
            st.warning("Your savings are insufficient to purchase stocks. Consider increasing your income or reducing expenses.")
        else:
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
                # Sort by price and suggest top 10 stocks
                suggested_stocks_df = suggested_stocks_df.sort_values(by="Price").head(10)

                for _, stock in suggested_stocks_df.iterrows():
                    st.write(f"{stock['Company_Name']} ({stock['Symbol']}) - Price: {stock['Price']:.2f}")
            else:
                st.warning("No stocks match your savings amount.")

# Tab 3: Stock Purchase
with tab3:
    st.title("Stock Purchase")
    st.header("Add a New Stock Purchase")

    # Dropdown for suggested stocks
    if suggested_stocks:
        stock_options = [stock['Symbol'] for stock in suggested_stocks]
        selected_stock = st.selectbox("Select a predicted stock:", stock_options)

        # Auto-fill stock details
        if selected_stock:
            selected_stock_details = next(stock for stock in suggested_stocks if stock['Symbol'] == selected_stock)
            stock_name = selected_stock_details['Company_Name']
            stock_price = selected_stock_details['Price']
    else:
        st.warning("No predicted stocks available. Please check the 'Predict Stocks' section.")
        stock_name = ""
        stock_price = 0.0

    # Input fields
    st.text_input("Stock Symbol:", value=selected_stock if suggested_stocks else "", key="symbol", disabled=True)
    st.text_input("Stock Name:", value=stock_name, key="name", disabled=True)
    st.number_input("Purchase Price per Stock:", value=stock_price, key="price", disabled=True)
    quantity = st.number_input("Quantity:", min_value=1, step=1)

    # Add the stock purchase
    if st.button("Add Purchase"):
        add_stock_purchase(username, selected_stock, stock_name, datetime.today().strftime("%Y-%m-%d"), quantity, stock_price)
        st.success(f"Successfully added {quantity} of {stock_name} ({selected_stock}) to your purchases!")

    # Display existing purchases
    st.header("Your Stock Purchases")
    stock_data = get_stock_data(username)
    stock_df = pd.DataFrame(stock_data, columns=["Symbol", "Name", "Purchase Date", "Quantity", "Purchase Price"])

    if not stock_df.empty:
        st.table(stock_df)
    else:
        st.warning("No stock purchases found.")

# Tab 4: Stock Forecast
with tab4:
    st.title("Stock Forecast")

    # Fetch only purchased stocks for forecasting
    purchased_stocks = get_stock_data(username)
    purchased_symbols = [stock[0] for stock in purchased_stocks]

    if purchased_symbols:
        selected_forecast_stock = st.selectbox("Select a purchased stock to forecast:", purchased_symbols)

        if selected_forecast_stock:
            ticker = yf.Ticker(selected_forecast_stock)
            hist_data = ticker.history(period="1y")

            if not hist_data.empty:
                # Prepare data for forecasting
                hist_data['Date'] = hist_data.index
                hist_data['Date_Ordinal'] = hist_data['Date'].map(lambda x: x.toordinal())
                X = hist_data[['Date_Ordinal']]
                y = hist_data['Close']

                # Train linear regression
                model = LinearRegression()
                model.fit(X, y)

                # Predict future values (next 6 months)
                future_dates = [datetime.today() + timedelta(days=30 * i) for i in range(1, 7)]
                future_ordinals = [[date.toordinal()] for date in future_dates]
                future_predictions = model.predict(future_ordinals)

                # Create a dataframe for future predictions
                future_df = pd.DataFrame({
                    'Date': future_dates,
                    'Predicted Price': future_predictions
                })

                # Combine historical and future data for plotting
                combined_df = pd.concat([hist_data[['Date', 'Close']].rename(columns={'Close': 'Price'}), future_df.rename(columns={'Predicted Price': 'Price'})])

                # Plot the data
                fig = px.line(combined_df, x='Date', y='Price', title=f"Forecast for {selected_forecast_stock}", labels={'Price': 'Stock Price'})
                st.plotly_chart(fig)
            else:
                st.warning("No data available for this stock.")
    else:
        st.warning("No purchased stocks available for forecasting.")

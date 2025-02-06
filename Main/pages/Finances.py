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
from prophet import Prophet

# Streamlit page setup
st.set_page_config(layout="wide")

# Ensure the user is logged in
if "user" not in st.session_state or st.session_state["user"] is None:
    st.warning("Please log in to access this page.")
    st.stop()

with st.sidebar:
    st.image("Main/assets/expense.png", use_container_width=True)
    if st.session_state["user"]:
        if st.button("Logout"):
            st.session_state["user"] = None
            st.rerun()

# Connect to SQLite databases
expenses_conn = sqlite3.connect('Main/data/expenses.db', check_same_thread=False)
expenses_cur = expenses_conn.cursor()

income_conn = sqlite3.connect('Main/data/income.db', check_same_thread=False)
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
    purchase_price REAL,
    sold INTEGER DEFAULT 0,
    sell_price REAL,
    sell_date DATE
)
''')
expenses_conn.commit()

# Add or update stock purchases
# Add or update stock purchases
def add_stock_purchase(owner, stock_symbol, stock_name, purchase_date, quantity, purchase_price):
    # Insert into stock_purchases table
    expenses_cur.execute('''
        INSERT INTO stock_purchases (owner, stock_symbol, stock_name, purchase_date, quantity, purchase_price)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (owner, stock_symbol, stock_name, purchase_date, quantity, purchase_price))
    expenses_conn.commit()
    
    # Calculate total purchase cost
    total_cost = quantity * purchase_price

    # Add to expenses table
    expenses_cur.execute('''
        INSERT INTO expenses (owner, date, amount, category, description)
        VALUES (?, ?, ?, ?, ?)
    ''', (owner, purchase_date, total_cost, "Stocks", stock_name))
    expenses_conn.commit()


def sell_stock(stock_id, sell_price, sell_date):
    expenses_cur.execute('''
        UPDATE stock_purchases
        SET sold = 1, sell_price = ?, sell_date = ?
        WHERE id = ?
    ''', (sell_price, sell_date, stock_id))
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

def get_stock_data(owner):
    return expenses_cur.execute('''
        SELECT stock_symbol, stock_name, purchase_date, quantity, purchase_price
        FROM stock_purchases
        WHERE owner = ?
    ''', (owner,)).fetchall()

# Fetch and cache stock prices
@st.cache_data(ttl=3600)
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

# Load company data
@st.cache_data
def load_company_data():
    file_path = r"./Main/data/Ticker_Company.xlsx"
    return pd.read_excel(file_path)

company_data = load_company_data()
ticker_symbols = company_data["Symbol"].tolist()

# Get the logged-in user's username
username = st.session_state["username"]

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(["Stock Prices", "Savings & Suggestions", "Stock Purchase", "Stock Forecast"])

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
            fig_close = px.line(tickerDf, x=tickerDf.index, y="Close", title="Closing Prices", color_discrete_sequence=["green"])
            st.plotly_chart(fig_close)
            tickerDf['Daily Return'] = tickerDf['Close'].pct_change() * 100

            fig_daily_return = px.line(tickerDf, x=tickerDf.index, y="Daily Return", 
                                    title="Daily Returns (%)", color_discrete_sequence=["blue"])
            st.plotly_chart(fig_daily_return)

            tickerDf['20_MA'] = tickerDf['Close'].rolling(window=20).mean()
            tickerDf['Upper_Band'] = tickerDf['20_MA'] + 2 * tickerDf['Close'].rolling(window=20).std()
            tickerDf['Lower_Band'] = tickerDf['20_MA'] - 2 * tickerDf['Close'].rolling(window=20).std()

            fig_bbands = px.line(tickerDf, x=tickerDf.index, y=["Close", "Upper_Band", "Lower_Band"], 
                                title="Bollinger Bands")
            st.plotly_chart(fig_bbands)

            support_level = tickerDf['Close'].min()

            # prediction model (e.g., linear regression)
            X = np.arange(len(tickerDf)).reshape(-1, 1)
            y = tickerDf['Close'].values
            model = LinearRegression().fit(X, y)
            future_days = 30
            future_X = np.arange(len(tickerDf) + future_days).reshape(-1, 1)
            predicted_prices = model.predict(future_X)

            tickerDf['Predicted'] = model.predict(X)
            fig_prediction = px.line(tickerDf, x=tickerDf.index, y=["Close", "Predicted"], 
                                    title="Price Prediction (Linear Regression)")
            st.plotly_chart(fig_prediction)



        else:
            st.warning("No data available for the entered symbol. Please try again.")

# Tab 2: Savings & Stock Predictions
with tab2:
    st.title("Savings & Stock Suggestions")
    
    # Fetch income and expense data to calculate remaining balance
    income_data = get_income_data(username)
    expense_data = get_expense_data(username)

    total_income = sum(data[1] for data in income_data)
    total_expense = sum(data[1] for data in expense_data)
    remaining = total_income - total_expense

    # Display total savings
    st.metric("Total Savings", f"{remaining:,.1f} INR")

    # Stock prediction section
    st.write("### Stock Suggestions")
    st.write("Based on your savings, consider the following top 5 cheapest stocks:")

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
            # Sort by price and suggest top 5 stocks
            suggested_stocks_df = suggested_stocks_df.sort_values(by="Price").head(5)
            suggested_stocks_df['Savings Usage (%)'] = (suggested_stocks_df['Price'] / remaining) * 100
            st.write(suggested_stocks_df.style.format({"Price": "₹{:.2f}", "Savings Usage (%)": "{:.2f}%"}))
        else:
            st.warning("No stocks match your savings amount.")


# Tab 3: Stock Purchase
with tab3:
    st.title("Stock Purchase")
    st.header("Add a New Stock Purchase")

    # Dropdown for suggested stocks
    suggested_stocks = []
    stock_prices = fetch_stock_prices(ticker_symbols)
    for _, row in company_data.iterrows():
        ticker_price = stock_prices.get(row['Symbol'])
        if ticker_price and ticker_price <= remaining:
            suggested_stocks.append({
                'Company_Name': row['Company_Name'],
                'Symbol': row['Symbol'],
                'Price': ticker_price
            })

    if suggested_stocks:
        suggested_stocks_df = pd.DataFrame(suggested_stocks)
        suggested_stocks_df = suggested_stocks_df.sort_values(by="Price").head(5)
        stock_options = [f"{stock['Company_Name']} ({stock['Symbol']}) - ₹{stock['Price']:.2f}" for stock in suggested_stocks_df.to_dict('records')]
        selected_stock = st.selectbox("Select a predicted stock:", stock_options)

        # Auto-fill stock details
        if selected_stock:
            selected_stock_details = next(
                stock for stock in suggested_stocks_df.to_dict('records') if f"{stock['Company_Name']} ({stock['Symbol']})" in selected_stock
            )
            stock_name = selected_stock_details['Company_Name']
            stock_symbol = selected_stock_details['Symbol']
            stock_price = selected_stock_details['Price']
    else:
        st.warning("No predicted stocks available. Please check the 'Predict Stocks' section.")
        stock_name, stock_symbol, stock_price = "", "", 0.0

    # Input fields
    st.text_input("Stock Symbol:", value=stock_symbol, key="symbol", disabled=True)
    st.text_input("Stock Name:", value=stock_name, key="name", disabled=True)
    st.number_input("Purchase Price per Stock:", value=stock_price, key="price", disabled=True)
    quantity = st.number_input("Quantity:", min_value=1, step=1)

    # Add the stock purchase
    if st.button("Add Purchase"):
        if stock_symbol and quantity > 0:
            add_stock_purchase(
                username, stock_symbol, stock_name,
                datetime.today().strftime("%Y-%m-%d"), quantity, stock_price
            )
            st.success(f"Successfully added {quantity} of {stock_name} ({stock_symbol}) to your purchases!")
        else:
            st.error("Please select a valid stock and quantity.")

    # Display existing purchases
    st.header("Your Stock Purchases")
    stock_data = get_stock_data(username)
    stock_df = pd.DataFrame(
        stock_data, 
        columns=["Symbol", "Name", "Purchase Date", "Quantity", "Purchase Price"]
    )
    if not stock_df.empty:
        st.table(stock_df)
    else:
        st.warning("No stock purchases found.")

# Tab 4: Stock Forecast
with tab4:
    st.title("Stock Forecast")

    # Fetch purchased stock symbols
    stock_data = get_stock_data(username)
    purchased_symbols = [stock[0] for stock in stock_data]  # Extract stock symbols

    if purchased_symbols:
        selected_stock = st.selectbox("Select a stock to forecast:", purchased_symbols)

        if selected_stock:
            ticker = yf.Ticker(selected_stock)
            hist_data = ticker.history(period="1y")

            if not hist_data.empty:
                # Prepare data for forecasting
                hist_data.reset_index(inplace=True)
                hist_data["ds"] = hist_data["Date"].dt.tz_localize(None)  # Remove timezone
                hist_data["y"] = hist_data["Close"]

                # Fit Prophet model
                model = Prophet()
                model.fit(hist_data[["ds", "y"]])

                # Predict future stock prices (next 6 months)
                future = model.make_future_dataframe(periods=180)
                forecast = model.predict(future)

                # Plot the forecast
                fig = px.line(
                    forecast, x="ds", y="yhat",
                    labels={"ds": "Date", "yhat": "Predicted Price"},
                    title=f"Forecast for {selected_stock}"
                )
                st.plotly_chart(fig)

                # Display forecast summary
                st.subheader(f"Based on historical data, the price of {selected_stock} is predicted to be ₹{forecast['yhat'].iloc[-1]:.2f} in next few months.")
            else:
                st.warning("No historical data available for this stock.")
    else:
        st.warning("No purchased stocks available for forecasting.")

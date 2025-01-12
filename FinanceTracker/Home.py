import streamlit as st
import sqlite3
import yfinance as yf
import pandas as pd
from datetime import datetime
import calendar
from streamlit_option_menu import option_menu
import plotly.express as px
import plotly.graph_objects as go
import geocoder
import requests

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

# Initialize session state
if "user" not in st.session_state:
    st.session_state["user"] = None

# Sidebar for navigation
with st.sidebar:
    st.image("expense.png", caption="App Logo", use_container_width=True)
    st.title("User Authentication")
    if st.session_state["user"]:
        st.write(f"Logged in as *{st.session_state['user']}*")
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

    # Dashboard Content
    tabs = st.tabs(["My Dashboard"])

    # My Dashboard Tab
    with tabs[0]:
        st.title("My Dashboard")

        # Function to get user's location based on IP address
        def get_user_location():
            ip = geocoder.ip('me').ip
            location = geocoder.ip(ip)
            return location

        # Function to fetch weather data from OpenWeatherMap API
        def get_weather(city, api_key):
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
            response = requests.get(url)
            data = response.json()
            return data

        def get_icon_url(icon_code):
            return f"http://openweathermap.org/img/wn/{icon_code}.png"

        # Weather Section
        location = get_user_location()
        if location:
            api_key = "8bdbd2e318823265106ee07bf92c3007"
            weather_data = get_weather(location.city, api_key)

            if weather_data["cod"] == 200:
                icon_code = weather_data['weather'][0]['icon']
                icon_url = get_icon_url(icon_code)

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.image(icon_url)
                with col2:
                    st.write(f"🌤️ {weather_data['main']['temp']}°C with {weather_data['weather'][0]['description']}")
                with col3:
                    st.write(f"📍 {location.city}")

            else:
                st.write("Error fetching weather data. Please try again.")
        else:
            st.write("Error fetching location. Please try again.")

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

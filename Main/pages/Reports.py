import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
from prophet import Prophet
import base64
from fpdf import FPDF
import io
import os

# Ensure user is logged in
if "user" not in st.session_state or st.session_state["user"] is None:
    st.warning("Please log in to access this page.")
    st.stop()

with st.sidebar:
    st.image("Main/assets/expense.png", use_container_width=True)
    if st.session_state["user"]:
        if st.button("Logout"):
            st.session_state["user"] = None
            st.rerun()

# Database connections
expenses_conn = sqlite3.connect('Main/data/expenses.db', check_same_thread=False)
income_conn = sqlite3.connect('Main/data/income.db', check_same_thread=False)

def get_data(owner, start_date, end_date):
    """Fetch expense and income data for the specified period"""
    # Fetch expenses
    expenses_query = """
    SELECT date, amount, category, description 
    FROM expenses 
    WHERE owner = ? AND date BETWEEN ? AND ?
    """
    expenses_df = pd.read_sql_query(
        expenses_query, 
        expenses_conn, 
        params=(owner, start_date, end_date)
    )
    
    # Fetch income
    income_query = """
    SELECT date, amount, source as category, description 
    FROM income 
    WHERE owner = ? AND date BETWEEN ? AND ?
    """
    income_df = pd.read_sql_query(
        income_query, 
        income_conn, 
        params=(owner, start_date, end_date)
    )
    
    return expenses_df, income_df

def generate_forecast(data, periods=30):
    """Generate forecast using Prophet"""
    if len(data) < 5:  # Need minimum data points for forecasting
        return None
    
    # Prepare data for Prophet
    df = data.copy()
    df['ds'] = pd.to_datetime(df['date'])
    df['y'] = df['amount']
    
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=True,
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0
    )
    model.fit(df)
    
    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)
    
    return forecast

def create_pdf_report(owner, start_date, end_date, expenses_df, income_df, expense_forecast, income_forecast):
    """Generate PDF report"""
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, 'Financial Report', 0, 1, 'C')
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    # Create PDF object
    pdf = PDF()
    pdf.add_page()
    
    # Report Information
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Period: {start_date} to {end_date}', 0, 1, 'C')
    pdf.cell(0, 10, f'Generated for: {owner}', 0, 1, 'C')
    pdf.ln(10)
    
    # Executive Summary
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Executive Summary', 0, 1, 'L')
    pdf.set_font('Arial', '', 12)
    total_income = income_df['amount'].sum()
    total_expenses = expenses_df['amount'].sum()
    balance = total_income - total_expenses
    savings_rate = (balance / total_income * 100) if total_income > 0 else 0
    
    summary_text = (
        f'During this period, your total income was Rs. {total_income:,.2f} and total expenses '
        f'were Rs. {total_expenses:,.2f}, resulting in a net balance of Rs. {balance:,.2f}. '
        f'Your savings rate for this period was {savings_rate:.1f}%. '
    )
    
    if savings_rate >= 20:
        summary_text += "This is an excellent savings rate! Keep up the good financial habits."
    elif savings_rate >= 10:
        summary_text += "This is a good savings rate, but there might be room for improvement."
    else:
        summary_text += "Consider reviewing your expenses to increase your savings rate."
    
    pdf.multi_cell(0, 10, summary_text)
    pdf.ln(5)
    
    # Income Analysis
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Income Analysis', 0, 1, 'L')
    pdf.set_font('Arial', '', 12)
    income_by_category = income_df.groupby('category')['amount'].sum()
    top_income_source = income_by_category.idxmax() if not income_by_category.empty else "N/A"
    
    income_text = (
        f'Your primary source of income is {top_income_source}, contributing '
        f'Rs. {income_by_category.max():,.2f} ({income_by_category.max()/total_income*100:.1f}% of total income).\n\n'
        'Detailed breakdown by source:\n'
    )
    pdf.multi_cell(0, 10, income_text)
    
    for category, amount in income_by_category.items():
        percentage = (amount / total_income) * 100
        pdf.cell(0, 10, f'- {category}: Rs. {amount:,.2f} ({percentage:.1f}%)', 0, 1, 'L')
    pdf.ln(5)
    
    # Expense Analysis
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Expense Analysis', 0, 1, 'L')
    pdf.set_font('Arial', '', 12)
    expense_by_category = expenses_df.groupby('category')['amount'].sum()
    top_expense = expense_by_category.idxmax() if not expense_by_category.empty else "N/A"
    
    expense_text = (
        f'Your highest expense category is {top_expense}, accounting for '
        f'Rs. {expense_by_category.max():,.2f} ({expense_by_category.max()/total_expenses*100:.1f}% of total expenses).\n\n'
        'Detailed breakdown by category:\n'
    )
    pdf.multi_cell(0, 10, expense_text)
    
    for category, amount in expense_by_category.items():
        percentage = (amount / total_expenses) * 100
        pdf.cell(0, 10, f'- {category}: Rs. {amount:,.2f} ({percentage:.1f}%)', 0, 1, 'L')
    pdf.ln(5)
    
    # Financial Health Indicators
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Financial Health Indicators', 0, 1, 'L')
    pdf.set_font('Arial', '', 12)
    
    # Calculate monthly averages
    days_in_period = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
    monthly_income = total_income * 30 / days_in_period
    monthly_expenses = total_expenses * 30 / days_in_period
    
    health_text = (
        f'Monthly Average Income: Rs. {monthly_income:,.2f}\n'
        f'Monthly Average Expenses: Rs. {monthly_expenses:,.2f}\n'
        f'Monthly Average Savings: Rs. {(monthly_income - monthly_expenses):,.2f}\n\n'
    )
    
    # Add financial health assessment
    expense_to_income = total_expenses / total_income if total_income > 0 else 0
    if expense_to_income <= 0.5:
        health_text += "Your expense-to-income ratio is excellent! This indicates strong financial health and good saving habits."
    elif expense_to_income <= 0.7:
        health_text += "Your expense-to-income ratio is good, but there's room for improvement in savings."
    else:
        health_text += "Your expense-to-income ratio is high. Consider ways to reduce expenses or increase income."
    
    pdf.multi_cell(0, 10, health_text)
    pdf.ln(5)
    
    # Forecast Analysis
    if expense_forecast is not None and income_forecast is not None:
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, 'Future Financial Outlook (30-Day Forecast)', 0, 1, 'L')
        pdf.set_font('Arial', '', 12)
        
        # Expense forecast analysis
        last_expense = expense_forecast["yhat"].iloc[-1]
        avg_expense = expense_forecast["yhat"].mean()
        expense_trend = "increasing" if expense_forecast["yhat"].iloc[-1] > expense_forecast["yhat"].iloc[-2] else "decreasing"
        expense_confidence = expense_forecast["yhat_upper"].iloc[-1] - expense_forecast["yhat_lower"].iloc[-1]
        
        forecast_text = (
            'Expense Forecast:\n'
            f'- Projected monthly expenses: Rs. {last_expense:,.2f}\n'
            f'- Average projected expenses: Rs. {avg_expense:,.2f}\n'
            f'- Trend: Your expenses are {expense_trend}\n'
            f'- Forecast range: Rs. {expense_forecast["yhat_lower"].iloc[-1]:,.2f} to '
            f'Rs. {expense_forecast["yhat_upper"].iloc[-1]:,.2f}\n\n'
        )
        
        # Income forecast analysis
        last_income = income_forecast["yhat"].iloc[-1]
        avg_income = income_forecast["yhat"].mean()
        income_trend = "increasing" if income_forecast["yhat"].iloc[-1] > income_forecast["yhat"].iloc[-2] else "decreasing"
        
        forecast_text += (
            'Income Forecast:\n'
            f'- Projected monthly income: Rs. {last_income:,.2f}\n'
            f'- Average projected income: Rs. {avg_income:,.2f}\n'
            f'- Trend: Your income is {income_trend}\n'
            f'- Forecast range: Rs. {income_forecast["yhat_lower"].iloc[-1]:,.2f} to '
            f'Rs. {income_forecast["yhat_upper"].iloc[-1]:,.2f}\n\n'
        )
        
        # Add recommendations
        forecast_text += 'Recommendations based on forecast:\n'
        if expense_trend == "increasing" and income_trend != "increasing":
            forecast_text += "- Your expenses are rising while income isn't keeping pace. Consider reviewing and optimizing your spending patterns.\n"
        if income_trend == "increasing":
            forecast_text += "- With increasing income, consider allocating the additional funds to savings or investments.\n"
        if expense_confidence > avg_expense * 0.5:
            forecast_text += "- Your expense patterns show high variability. Creating a budget might help in maintaining more consistent spending.\n"
        
        pdf.multi_cell(0, 10, forecast_text)
    
    # Final Recommendations
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Action Items and Recommendations', 0, 1, 'L')
    pdf.set_font('Arial', '', 12)
    
    recommendations = [
        "- Review your highest expense categories and identify potential areas for reduction.",
        f"- Aim to maintain or improve your current savings rate of {savings_rate:.1f}%.",
        "- Consider diversifying income sources to increase financial stability.",
        "- Set up an emergency fund if you haven't already.",
        "- Review your financial goals regularly and adjust your spending patterns accordingly."
    ]
    
    for rec in recommendations:
        pdf.cell(0, 10, rec, 0, 1, 'L')
    
    return pdf.output(dest='S').encode('latin-1')

def main():
    st.title("Financial Reports")
    
    # Time period selection
    st.subheader("Select Report Period")
    
    col1, col2 = st.columns(2)
    with col1:
        report_type = st.selectbox(
            "Report Type",
            ["Custom Period", "Last 30 Days", "Last 3 Months", "Last 6 Months", "Last Year"]
        )
    
    # Calculate date range based on selection
    today = datetime.now().date()
    if report_type == "Custom Period":
        with col2:
            start_date = st.date_input(
                "Start Date",
                value=today - timedelta(days=30),
                max_value=today
            )
            end_date = st.date_input(
                "End Date",
                value=today,
                min_value=start_date,
                max_value=today
            )
    else:
        days_map = {
            "Last 30 Days": 30,
            "Last 3 Months": 90,
            "Last 6 Months": 180,
            "Last Year": 365
        }
        end_date = today
        start_date = end_date - timedelta(days=days_map[report_type])
    
    # Fetch data
    owner = st.session_state["username"]
    expenses_df, income_df = get_data(owner, start_date, end_date)
    
    if expenses_df.empty and income_df.empty:
        st.warning("No data available for the selected period.")
        return
    
    # Generate forecasts
    expense_forecast = generate_forecast(expenses_df) if not expenses_df.empty else None
    income_forecast = generate_forecast(income_df) if not income_df.empty else None
    
    # Display summary
    st.subheader("Summary")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Income", f"₹{income_df['amount'].sum():,.2f}")
    with col2:
        st.metric("Total Expenses", f"₹{expenses_df['amount'].sum():,.2f}")
    with col3:
        st.metric("Net Balance", f"₹{income_df['amount'].sum() - expenses_df['amount'].sum():,.2f}")
    
    # Visualizations
    st.subheader("Expense Breakdown")
    if not expenses_df.empty:
        fig_expenses = px.pie(
            expenses_df,
            values='amount',
            names='category',
            title='Expenses by Category'
        )
        st.plotly_chart(fig_expenses)
    
    # Income breakdown
    st.subheader("Income Sources")
    if not income_df.empty:
        fig_income = px.pie(
            income_df,
            values='amount',
            names='category',
            title='Income by Source'
        )
        st.plotly_chart(fig_income)
    
    # Time series analysis
    st.subheader("Income vs Expenses Over Time")
    expenses_df['type'] = 'Expense'
    income_df['type'] = 'Income'
    combined_df = pd.concat([expenses_df, income_df])
    
    fig_timeline = px.line(
        combined_df,
        x='date',
        y='amount',
        color='type',
        title='Income and Expenses Over Time'
    )
    st.plotly_chart(fig_timeline)

    # Enhanced forecast visualizations with analysis
    if expense_forecast is not None and income_forecast is not None:
        st.subheader("Forecasts")
        
        # Expense Forecast
        fig_expense_forecast = px.line(
            expense_forecast,
            x='ds',
            y=['yhat', 'yhat_lower', 'yhat_upper'],
            title='Expense Forecast'
        )
        fig_expense_forecast.update_traces(
            line_color='red',
            selector=dict(name='yhat')
        )
        fig_expense_forecast.add_scatter(
            x=expenses_df['date'],
            y=expenses_df['amount'],
            mode='markers',
            name='Historical Data',
            marker=dict(color='blue', size=8)
        )
        fig_expense_forecast.update_layout(
            xaxis_title="Date",
            yaxis_title="Amount (₹)",
            showlegend=True,
            hovermode='x unified'
        )
        st.plotly_chart(fig_expense_forecast)
        
        # Expense forecast analysis
        st.markdown("### Expense Forecast Analysis")
        last_expense = expense_forecast["yhat"].iloc[-1]
        avg_expense = expense_forecast["yhat"].mean()
        trend = "increasing" if expense_forecast["yhat"].iloc[-1] > expense_forecast["yhat"].iloc[-2] else "decreasing"
        
        st.write(f"""
        Based on your historical expense patterns:
        - Projected expense for the next month: ₹{last_expense:,.2f}
        - Average projected expense: ₹{avg_expense:,.2f}
        - Trend: Your expenses are {trend}
        - Confidence interval: ₹{expense_forecast["yhat_lower"].iloc[-1]:,.2f} to ₹{expense_forecast["yhat_upper"].iloc[-1]:,.2f}
        
        This forecast suggests that your spending patterns are likely to {trend}. Consider {'budgeting more carefully' if trend == 'increasing' else 'maintaining your current spending habits'}.
        """)
        
        # Income Forecast
        fig_income_forecast = px.line(
            income_forecast,
            x='ds',
            y=['yhat', 'yhat_lower', 'yhat_upper'],
            title='Income Forecast'
        )
        fig_income_forecast.update_traces(
            line_color='green',
            selector=dict(name='yhat')
        )
        fig_income_forecast.add_scatter(
            x=income_df['date'],
            y=income_df['amount'],
            mode='markers',
            name='Historical Data',
            marker=dict(color='blue', size=8)
        )
        fig_income_forecast.update_layout(
            xaxis_title="Date",
            yaxis_title="Amount (₹)",
            showlegend=True,
            hovermode='x unified'
        )
        st.plotly_chart(fig_income_forecast)
        
        # Income forecast analysis
        st.markdown("### Income Forecast Analysis")
        last_income = income_forecast["yhat"].iloc[-1]
        avg_income = income_forecast["yhat"].mean()
        trend = "increasing" if income_forecast["yhat"].iloc[-1] > income_forecast["yhat"].iloc[-2] else "decreasing"
        
        st.write(f"""
        Based on your historical income patterns:
        - Projected income for the next month: ₹{last_income:,.2f}
        - Average projected income: ₹{avg_income:,.2f}
        - Trend: Your income is {trend}
        - Confidence interval: ₹{income_forecast["yhat_lower"].iloc[-1]:,.2f} to ₹{income_forecast["yhat_upper"].iloc[-1]:,.2f}
        
        This forecast indicates that your income is likely to {trend}. {'This is a positive trend - consider increasing your savings!' if trend == 'increasing' else 'Consider exploring additional income sources or reviewing your financial strategy.'}
        """)

    # Export to PDF
    if st.button("Generate PDF Report"):
        try:
            pdf_bytes = create_pdf_report(
                owner,
                start_date,
                end_date,
                expenses_df,
                income_df,
                expense_forecast,
                income_forecast
            )
            
            # Create download button
            b64_pdf = base64.b64encode(pdf_bytes).decode()
            href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="financial_report.pdf">Download PDF Report</a>'
            st.markdown(href, unsafe_allow_html=True)
            st.success("Report generated successfully!")
        except Exception as e:
            st.error(f"Error generating report: {str(e)}")

if __name__ == "__main__":
    main() 
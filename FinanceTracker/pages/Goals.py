import sqlite3
import streamlit as st
import pandas as pd
from streamlit_option_menu import option_menu

# Establish database connection for goals
conn = sqlite3.connect('expenses.db', check_same_thread=False)
cur = conn.cursor()

if "user" not in st.session_state or st.session_state["user"] is None:
    st.warning("Please log in to access this page.")
    st.stop()

# Function to create the goals table if not already present
def create_goals_table(cur):
    create_table_query = '''
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner TEXT NOT NULL,
        goal_amount REAL NOT NULL,
        saved_amount REAL DEFAULT 0.0,
        description TEXT NOT NULL
    );
    '''
    cur.execute(create_table_query)

# Function to handle the goals page
def goals_page(cur, conn):
    create_goals_table(cur)

    st.header("My Savings Goals")

    # Option menu for navigation
    selected = option_menu(
        menu_title=None,
        icons=["eye", "plus-circle"],
        options=["View Goals", "Set New Goal"],
        orientation="horizontal",
    )

    if selected == "View Goals":
        st.subheader("Your Current Goals")

        # Fetch goals from the database for the logged-in user
        try:
            goals_query = '''
            SELECT id, goal_amount, saved_amount, description
            FROM goals
            WHERE owner = ?;
            '''
            goals = cur.execute(goals_query, (st.session_state.get("username", ""),)).fetchall()
        except Exception:
            goals = []

        if goals:
            # Convert goals to DataFrame
            goals_df = pd.DataFrame(goals, columns=["ID", "Goal Amount", "Saved Amount", "Description"])
            goals_df.insert(0, "Serial", range(1, len(goals_df) + 1))  # Add serial column
            goals_df["Progress (%)"] = (goals_df["Saved Amount"] / goals_df["Goal Amount"] * 100).round(2)

            # Display goals in a table
            st.write(goals_df.drop(columns=["ID"]).to_html(index=False), unsafe_allow_html=True)

            # Update Saved Amount Section
            st.subheader("Update Saved Amount")
            selected_goal_id = st.selectbox("Select Goal to Update:", goals_df["ID"])
            if selected_goal_id:
                selected_goal = goals_df[goals_df["ID"] == selected_goal_id].iloc[0]

                with st.form("update_goal_form"):
                    st.write(f"Updating Goal: {selected_goal['Description']}")
                    new_saved_amount = st.number_input(
                        "Update Saved Amount",
                        min_value=0.0,
                        max_value=selected_goal["Goal Amount"],
                        value=selected_goal["Saved Amount"],
                        step=0.01,
                    )
                    submitted = st.form_submit_button("Update")
                    if submitted:
                        try:
                            # Update the saved amount in the database
                            update_query = '''
                            UPDATE goals
                            SET saved_amount = ?
                            WHERE id = ?
                            '''
                            cur.execute(update_query, (new_saved_amount, selected_goal_id))
                            conn.commit()
                            st.success("Saved amount updated successfully!")
                            st.rerun()
                        except Exception:
                            st.error("You have no savings goals set yet.")
        else:
            st.write("You have no savings goals set yet.")

    elif selected == "Set New Goal":
        st.subheader("Set a New Savings Goal")
        with st.form("set_goal_form", clear_on_submit=True):
            goal_amount = st.number_input("Goal Amount", min_value=0.0, step=0.01)
            goal_description = st.text_area("Goal Description", placeholder="Enter a description for your savings goal.")

            submitted = st.form_submit_button("Set Goal")
            if submitted:
                if goal_amount <= 0:
                    st.error("Goal amount must be greater than zero.")
                elif not goal_description.strip():
                    st.error("Please provide a description for your goal.")
                else:
                    try:
                        # Insert goal into the database
                        insert_query = '''
                        INSERT INTO goals (owner, goal_amount, description)
                        VALUES (?, ?, ?)
                        '''
                        cur.execute(insert_query, (st.session_state.get("username", ""), goal_amount, goal_description))
                        conn.commit()
                        st.success("Goal set successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

# Run the goals page
goals_page(cur, conn)
"""Streamlit interface for SpaceShare account access."""

from pathlib import Path

import streamlit as st

import db
from logic import create_listing, register_user, verify_user_password


DATABASE_PATH = Path("spaceshare.sqlite3")


def get_connection():
    """Open a database connection for the current Streamlit run."""
    return db.connect(DATABASE_PATH)


def show_registration(connection):
    st.subheader("Create an account")
    with st.form("registration_form"):
        email = st.text_input("Email address", key="registration_email")
        password = st.text_input(
            "Password", type="password", key="registration_password"
        )
        submitted = st.form_submit_button("Register")

    if submitted:
        try:
            register_user(connection, email, password)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Account created. You can now log in.")


def show_login(connection):
    st.subheader("Log in")
    with st.form("login_form"):
        email = st.text_input("Email address", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        try:
            valid_password = verify_user_password(connection, email, password)
        except ValueError as error:
            st.error(str(error))
        else:
            if valid_password:
                st.session_state["user_email"] = email.strip().lower()
                st.rerun()
            else:
                st.error("Invalid email or password.")


def show_listing_form(connection, user_email):
    user = db.get_user_by_email(connection, user_email)
    if user is None:
        st.error("The logged-in account could not be found.")
        return

    st.subheader("Create a storage listing")
    with st.form("listing_form"):
        title = st.text_input("Title")
        city = st.text_input("City")
        description = st.text_area("Description")
        size_sqm = st.number_input("Size in m²", min_value=0.0, step=1.0)
        price = st.number_input("Price per month in €", min_value=0.0, step=1.0)
        available_from = st.date_input("Available from")
        minimum_days = st.number_input(
            "Minimum rental duration in days", min_value=0, step=1
        )
        submitted = st.form_submit_button("Create listing")

    if submitted:
        try:
            create_listing(
                connection,
                user["id"],
                title,
                city,
                description,
                size_sqm,
                price,
                available_from.isoformat(),
                minimum_days,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Listing created.")


def show_listings(connection):
    st.subheader("Available storage listings")
    listings = db.get_listings(connection)
    if not listings:
        st.info("No listings yet.")
        return

    for listing in listings:
        with st.container(border=True):
            st.markdown(f"### {listing['title']}")
            st.write(f"**City:** {listing['city']}")
            st.write(listing["description"])
            st.write(
                f"**Size:** {listing['size_sqm']} m²  |  "
                f"**Price:** €{listing['price_per_month_eur']:.2f} per month"
            )
            st.write(
                f"**Available from:** {listing['available_from']}  |  "
                f"**Minimum rental duration:** {listing['minimum_rental_days']} days"
            )


def main():
    st.set_page_config(page_title="SpaceShare", page_icon="📦")
    st.title("SpaceShare")
    st.write("Find and offer storage space.")

    connection = get_connection()
    try:
        user_email = st.session_state.get("user_email")

        if user_email:
            st.success(f"Welcome, {user_email}!")
            show_listing_form(connection, user_email)
            show_listings(connection)
            if st.button("Log out"):
                del st.session_state["user_email"]
                st.rerun()
            return

        register_tab, login_tab = st.tabs(["Register", "Log in"])
        with register_tab:
            show_registration(connection)
        with login_tab:
            show_login(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()

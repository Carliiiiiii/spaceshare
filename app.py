"""Streamlit interface for browsing and managing SpaceShare listings."""

from pathlib import Path
from datetime import date

import streamlit as st

import db
from logic import (
    create_rental_request,
    create_listing,
    delete_listing,
    register_user,
    update_listing,
    verify_user_password,
    update_rental_request_status,
)


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
        available_until = st.date_input("Available until (optional)", value=None)
        uploaded_photo = st.file_uploader(
            "Photo (optional, JPG or PNG, max 5 MB)",
            type=["jpg", "jpeg", "png"],
        )
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
                available_until.isoformat() if available_until else None,
                uploaded_photo.getvalue() if uploaded_photo else None,
                uploaded_photo.type if uploaded_photo else None,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Listing created.")


def show_listings(connection):
    st.subheader("Available storage listings")
    filter_columns = st.columns(4)
    with filter_columns[0]:
        city = st.text_input(
            "City",
            placeholder="Any city",
            key="listing_filter_city",
        )
    with filter_columns[1]:
        minimum_size_sqm = st.number_input(
            "Minimum size in m²",
            min_value=0.0,
            value=None,
            step=1.0,
            placeholder="Any size",
            key="listing_filter_minimum_size",
        )
    with filter_columns[2]:
        maximum_price_per_month_eur = st.number_input(
            "Maximum monthly price in €",
            min_value=0.0,
            value=None,
            step=1.0,
            placeholder="Any price",
            key="listing_filter_maximum_price",
        )
    with filter_columns[3]:
        available_on = st.date_input(
            "Available on",
            value=None,
            help="Show spaces available on the selected date.",
            key="listing_filter_available_on",
        )

    listings = db.get_listings(
        connection,
        city=city,
        minimum_size_sqm=minimum_size_sqm,
        maximum_price_per_month_eur=maximum_price_per_month_eur,
        available_on=available_on.isoformat() if available_on else None,
    )
    if not listings:
        has_filters = any(
            (
                city.strip(),
                minimum_size_sqm is not None,
                maximum_price_per_month_eur is not None,
                available_on is not None,
            )
        )
        st.info(
            "No listings match these filters."
            if has_filters
            else "No listings yet."
        )
        return

    st.caption(f"{len(listings)} listing{'s' if len(listings) != 1 else ''} found")
    for listing in listings:
        with st.container(border=True):
            st.markdown(f"### {listing['title']}")
            if listing["photo_data"]:
                st.image(listing["photo_data"], caption=listing["title"])
            else:
                st.info("No photo available.")
            st.write(f"**City:** {listing['city']}")
            st.write(listing["description"])
            st.write(
                f"**Size:** {listing['size_sqm']} m²  |  "
                f"**Price:** €{listing['price_per_month_eur']:.2f} per month"
            )
            st.write(
                f"**Available from:** {listing['available_from']}  |  "
                f"**Available until:** {listing['available_until'] or 'Unlimited'}  |  "
                f"**Minimum rental duration:** {listing['minimum_rental_days']} days"
            )
            if st.session_state.get("user_email"):
                with st.form(f"request_listing_{listing['id']}"):
                    request_start = st.date_input("Rental start date", key=f"request_start_{listing['id']}")
                    request_end = st.date_input("Rental end date", key=f"request_end_{listing['id']}")
                    request_submitted = st.form_submit_button("Send rental request")
                if request_submitted:
                    user = db.get_user_by_email(connection, st.session_state["user_email"])
                    try:
                        create_rental_request(connection, listing["id"], user["id"], request_start.isoformat(), request_end.isoformat())
                    except (ValueError, PermissionError) as error:
                        st.error(str(error))
                    else:
                        st.success("Rental request sent.")


def show_rental_requests(connection, user_id):
    st.subheader("Rental requests")
    requests = db.get_rental_requests_for_user(connection, user_id)
    if not requests:
        st.info("No rental requests yet.")
        return
    for request in requests:
        role = "Incoming" if request["owner_id"] == user_id else "Sent"
        st.write(f"**{role}:** {request['title']} — {request['start_date']} to {request['end_date']} — **{request['status']}**")
        if request["owner_id"] == user_id and request["status"] == "pending":
            columns = st.columns(2)
            for column, status in zip(columns, ("accepted", "rejected")):
                with column:
                    if st.button(status.title(), key=f"request_{request['id']}_{status}"):
                        try:
                            update_rental_request_status(connection, request["id"], user_id, status)
                        except (ValueError, PermissionError) as error:
                            st.error(str(error))
                        else:
                            st.rerun()


def show_my_listings(connection, owner_id):
    st.subheader("My listings")
    listings = db.get_listings_by_owner(connection, owner_id)
    if not listings:
        st.info("You have no listings yet.")
        return

    for listing in listings:
        with st.expander(listing["title"]):
            with st.form(f"edit_listing_{listing['id']}"):
                title = st.text_input("Title", value=listing["title"])
                city = st.text_input("City", value=listing["city"])
                description = st.text_area(
                    "Description", value=listing["description"]
                )
                size_sqm = st.number_input(
                    "Size in m²", min_value=0.0, value=float(listing["size_sqm"]), step=1.0
                )
                price = st.number_input(
                    "Price per month in €",
                    min_value=0.0,
                    value=float(listing["price_per_month_eur"]),
                    step=1.0,
                )
                available_from = st.date_input(
                    "Available from", value=date.fromisoformat(listing["available_from"])
                )
                available_until = st.date_input(
                    "Available until (optional)",
                    value=(
                        date.fromisoformat(listing["available_until"])
                        if listing["available_until"]
                        else None
                    ),
                )
                if listing["photo_data"]:
                    st.image(listing["photo_data"], caption="Current photo")
                uploaded_photo = st.file_uploader(
                    "Replace photo (optional)",
                    type=["jpg", "jpeg", "png"],
                    key=f"photo_upload_{listing['id']}",
                )
                remove_photo = st.checkbox(
                    "Remove current photo",
                    key=f"photo_remove_{listing['id']}",
                )
                minimum_days = st.number_input(
                    "Minimum rental duration in days",
                    min_value=0,
                    value=int(listing["minimum_rental_days"]),
                    step=1,
                )
                update_submitted = st.form_submit_button("Save changes")

            if update_submitted:
                try:
                    update_listing(
                        connection,
                        owner_id,
                        listing["id"],
                        title,
                        city,
                        description,
                        size_sqm,
                        price,
                        available_from.isoformat(),
                        minimum_days,
                        available_until.isoformat() if available_until else None,
                        (
                            uploaded_photo.getvalue()
                            if uploaded_photo
                            else listing["photo_data"]
                        )
                        if not remove_photo
                        else None,
                        (
                            uploaded_photo.type
                            if uploaded_photo
                            else listing["photo_mime_type"]
                        )
                        if not remove_photo
                        else None,
                    )
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.success("Listing updated.")

            with st.form(f"delete_listing_{listing['id']}"):
                confirmed = st.checkbox("I understand that this cannot be undone.")
                delete_submitted = st.form_submit_button("Delete listing")

            if delete_submitted:
                if not confirmed:
                    st.error("Please confirm the deletion first.")
                else:
                    try:
                        delete_listing(connection, owner_id, listing["id"])
                    except PermissionError as error:
                        st.error(str(error))
                    else:
                        st.success("Listing deleted.")
                        st.rerun()
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
            user = db.get_user_by_email(connection, user_email)
            if user is not None:
                show_my_listings(connection, user["id"])
                show_rental_requests(connection, user["id"])
            show_listings(connection)
            if st.button("Log out"):
                del st.session_state["user_email"]
                st.rerun()
            return

        browse_tab, register_tab, login_tab = st.tabs(
            ["Browse listings", "Register", "Log in"]
        )
        with browse_tab:
            show_listings(connection)
        with register_tab:
            show_registration(connection)
        with login_tab:
            show_login(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()

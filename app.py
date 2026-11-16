"""Streamlit interface for browsing and managing SpaceShare listings."""

import html
from datetime import date, datetime
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

import db
from logic import (
    PUBLIC_LOCATION_DECIMAL_PLACES,
    create_rental_request,
    create_listing,
    delete_listing,
    get_messages,
    register_user,
    send_message,
    update_listing,
    verify_user_password,
    update_rental_request_status,
    validate_public_location,
)


DATABASE_PATH = Path("spaceshare.sqlite3")
DEFAULT_MAP_CENTER = (38.7223, -9.1393)


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


def show_public_location_picker(
    key_prefix, public_latitude=None, public_longitude=None
):
    """Let an owner select a deliberately approximate public map location."""
    latitude_key = f"{key_prefix}_latitude"
    longitude_key = f"{key_prefix}_longitude"

    if latitude_key not in st.session_state:
        st.session_state[latitude_key] = public_latitude
    if longitude_key not in st.session_state:
        st.session_state[longitude_key] = public_longitude

    selected_latitude = st.session_state[latitude_key]
    selected_longitude = st.session_state[longitude_key]
    has_selected_location = (
        selected_latitude is not None and selected_longitude is not None
    )
    map_center = (
        (float(selected_latitude), float(selected_longitude))
        if has_selected_location
        else DEFAULT_MAP_CENTER
    )
    location_map = folium.Map(
        location=map_center,
        zoom_start=13 if has_selected_location else 10,
        control_scale=True,
    )
    if has_selected_location:
        folium.CircleMarker(
            location=map_center,
            radius=8,
            color="#ff385c",
            fill=True,
            fill_color="#ff385c",
            fill_opacity=0.9,
            tooltip="Approximate public location",
        ).add_to(location_map)

    map_state = st_folium(
        location_map,
        key=f"{key_prefix}_map",
        height=320,
        use_container_width=True,
        returned_objects=["last_clicked"],
    ) or {}
    clicked_location = map_state.get("last_clicked")
    if isinstance(clicked_location, dict):
        try:
            picked_latitude, picked_longitude = validate_public_location(
                clicked_location.get("lat"), clicked_location.get("lng")
            )
        except ValueError:
            st.error("The selected map position is invalid. Please try again.")
        else:
            st.session_state[latitude_key] = picked_latitude
            st.session_state[longitude_key] = picked_longitude

    selected_latitude = st.session_state[latitude_key]
    selected_longitude = st.session_state[longitude_key]
    if selected_latitude is None:
        st.caption("Click the map to select an approximate public location.")
    else:
        st.caption(
            "Selected approximate location: "
            f"{selected_latitude:.{PUBLIC_LOCATION_DECIMAL_PLACES}f}, "
            f"{selected_longitude:.{PUBLIC_LOCATION_DECIMAL_PLACES}f}"
        )

    return selected_latitude, selected_longitude


def _public_listing_locations(listings):
    """Return listings that have valid public map points."""
    locations = []
    for listing in listings:
        try:
            latitude, longitude = validate_public_location(
                listing["public_latitude"], listing["public_longitude"]
            )
        except ValueError:
            continue
        if latitude is not None:
            locations.append((listing, latitude, longitude))
    return locations


def show_listing_map(listings):
    """Render the public, filtered listings on a map beside the list."""
    st.markdown("#### Map")
    locations = _public_listing_locations(listings)
    if not locations:
        st.info(
            "None of the matching listings has an approximate public map "
            "location yet."
        )
        return

    _, first_latitude, first_longitude = locations[0]
    listing_map = folium.Map(
        location=(first_latitude, first_longitude),
        zoom_start=13,
        control_scale=True,
    )
    for listing, latitude, longitude in locations:
        title = html.escape(str(listing["title"]))
        city = html.escape(str(listing["city"]))
        price = float(listing["price_per_month_eur"])
        size_sqm = float(listing["size_sqm"])
        marker_html = (
            '<div style="background: #ff385c; border: 2px solid white; '
            'border-radius: 18px; box-shadow: 0 1px 4px #555; color: white; '
            'font-size: 12px; font-weight: 700; padding: 5px 8px; '
            'text-align: center; white-space: nowrap;">'
            f"€{price:.0f}</div>"
        )
        popup_html = (
            f"<strong>{title}</strong><br>"
            f"{city}<br>€{price:.2f} per month · {size_sqm:g} m²"
        )
        folium.Marker(
            location=(latitude, longitude),
            icon=folium.DivIcon(
                html=marker_html,
                icon_size=(64, 32),
                icon_anchor=(32, 16),
            ),
            tooltip=f"€{price:.2f} per month",
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(listing_map)

    if len(locations) > 1:
        listing_map.fit_bounds(
            [(latitude, longitude) for _, latitude, longitude in locations],
            padding=(30, 30),
        )

    st_folium(
        listing_map,
        key="public_listing_map",
        height=580,
        use_container_width=True,
        returned_objects=[],
    )
    st.caption(
        "Map pins are approximate public locations, not exact addresses. "
        f"{len(locations)} matching listing"
        f"{'s' if len(locations) != 1 else ''} shown on the map."
    )


def show_listing_form(connection, user_email):
    user = db.get_user_by_email(connection, user_email)
    if user is None:
        st.error("The logged-in account could not be found.")
        return

    st.subheader("Create a storage listing")
    location_choice = st.radio(
        "Show an approximate location on the public map?",
        ("No, do not show a pin", "Yes, add a public pin"),
        horizontal=True,
        key="new_listing_public_location_choice",
    )
    public_latitude = None
    public_longitude = None
    if location_choice == "Yes, add a public pin":
        st.caption(
            "Use an approximate location, not your exact address. The saved "
            "point is rounded before it becomes public."
        )
        public_latitude, public_longitude = show_public_location_picker(
            "new_listing_public_location"
        )

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
                public_latitude=public_latitude,
                public_longitude=public_longitude,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Listing created.")


def show_listings(connection):
    st.subheader("Available storage listings")
    filter_columns = st.columns(5)
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
        requested_start = st.date_input(
            "Desired rental start",
            value=None,
            key="listing_filter_requested_start",
        )
    with filter_columns[4]:
        requested_end = st.date_input(
            "Desired rental end",
            value=None,
            key="listing_filter_requested_end",
        )

    if (requested_start is None) != (requested_end is None):
        st.error("Select both rental dates to filter by availability.")
        return
    if requested_start is not None and requested_end <= requested_start:
        st.error("Rental end must be after rental start.")
        return

    listings = db.get_listings(
        connection,
        city=city,
        minimum_size_sqm=minimum_size_sqm,
        maximum_price_per_month_eur=maximum_price_per_month_eur,
        requested_start=(
            requested_start.isoformat() if requested_start else None
        ),
        requested_end=requested_end.isoformat() if requested_end else None,
    )

    if not listings:
        has_filters = any(
            (
                city.strip(),
                minimum_size_sqm is not None,
                maximum_price_per_month_eur is not None,
                requested_start is not None,
            )
        )
        st.info(
            "No listings match these filters."
            if has_filters
            else "No listings yet."
        )
        return

    st.caption(f"{len(listings)} listing{'s' if len(listings) != 1 else ''} found")

    listing_column, map_column = st.columns((3, 2), gap="large")
    with listing_column:
        st.markdown("#### Listings")
        for listing in listings:
            show_listing_card(connection, listing)
    with map_column:
        show_listing_map(listings)


def show_listing_card(connection, listing):
    """Render one public listing card in the list half of the browse view."""
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
            f"**Minimum rental duration:** "
            f"{listing['minimum_rental_days']} days"
        )

        if st.session_state.get("user_email"):
            with st.form(f"request_listing_{listing['id']}"):
                request_start = st.date_input(
                    "Rental start date",
                    key=f"request_start_{listing['id']}",
                )
                request_end = st.date_input(
                    "Rental end date",
                    key=f"request_end_{listing['id']}",
                )
                request_submitted = st.form_submit_button(
                    "Send rental request"
                )

            if request_submitted:
                user = db.get_user_by_email(
                    connection,
                    st.session_state["user_email"],
                )
                try:
                    create_rental_request(
                        connection,
                        listing["id"],
                        user["id"],
                        request_start.isoformat(),
                        request_end.isoformat(),
                    )
                except (ValueError, PermissionError) as error:
                    st.error(str(error))
                else:
                    st.success("Rental request sent.")


def show_rental_requests(connection, user_id):
    st.subheader("My requests")
    requests = db.get_rental_requests_for_user(connection, user_id)
    if not requests:
        st.info("No rental requests yet.")
        return

    sent_requests = [request for request in requests if request["owner_id"] != user_id]
    incoming_requests = [request for request in requests if request["owner_id"] == user_id]

    st.markdown("#### Requests I sent")
    if not sent_requests:
        st.info("You have not sent any rental requests.")
    for request in sent_requests:
        st.write(
            f"**{request['title']}** — {request['start_date']} to "
            f"{request['end_date']} — **Status: {request['status']}**"
        )
        show_request_chat(connection, user_id, request)

    st.markdown("#### Requests for my listings")
    if not incoming_requests:
        st.info("No one has requested your listings yet.")
    for request in incoming_requests:
        st.write(
            f"**{request['title']}** — {request['start_date']} to "
            f"{request['end_date']} — **Status: {request['status']}**"
        )
        show_request_chat(connection, user_id, request)
        if request["owner_id"] == user_id and request["status"] == "pending":
            columns = st.columns(2)
            for column, status, label in zip(
                columns,
                ("accepted", "rejected"),
                ("Accept", "Reject"),
            ):
                with column:
                    if st.button(label, key=f"request_{request['id']}_{status}"):
                        try:
                            update_rental_request_status(connection, request["id"], user_id, status)
                        except (ValueError, PermissionError) as error:
                            st.error(str(error))
                        else:
                            st.rerun()


def show_request_chat(connection, user_id, request):
    with st.expander("Open chat"):
        messages = get_messages(connection, request["id"], user_id)
        if messages:
            for message in messages:
                sender_role = (
                    "Renter" if message["sender_id"] == message["requester_id"]
                    else "Listing owner"
                )
                try:
                    sent_at = datetime.fromisoformat(message["sent_at"])
                    formatted_time = sent_at.strftime("%d %b %Y, %H:%M UTC")
                except ValueError:
                    formatted_time = message["sent_at"]
                with st.container(border=True):
                    st.markdown(f"**{sender_role}**")
                    st.caption(formatted_time)
                    st.write(message["message"])
        else:
            st.info("No messages yet.")

        with st.form(f"message_form_{request['id']}"):
            message_text = st.text_area(
                "Message",
                max_chars=1000,
                key=f"message_text_{request['id']}",
            )
            send_submitted = st.form_submit_button("Send message")
        if send_submitted:
            try:
                send_message(connection, request["id"], user_id, message_text)
            except (ValueError, PermissionError) as error:
                st.error(str(error))
            else:
                st.success("Message sent.")

        if st.button("Refresh messages", key=f"refresh_messages_{request['id']}"):
            st.rerun()


def show_my_listings(connection, owner_id):
    st.subheader("My listings")
    listings = db.get_listings_by_owner(connection, owner_id)
    if not listings:
        st.info("You have no listings yet.")
        return

    for listing in listings:
        with st.expander(listing["title"]):
            has_public_location = (
                listing["public_latitude"] is not None
                and listing["public_longitude"] is not None
            )
            st.caption(
                "An approximate public map location is set."
                if has_public_location
                else "No public map location is set."
            )
            public_latitude = None
            public_longitude = None
            if has_public_location:
                location_action = st.radio(
                    "What would you like to do with the public map pin?",
                    ("Keep current pin", "Change pin", "Remove pin"),
                    horizontal=True,
                    key=f"edit_listing_location_action_{listing['id']}_set",
                )
            else:
                location_action = st.radio(
                    "Show an approximate location on the public map?",
                    ("No, do not show a pin", "Yes, add a public pin"),
                    horizontal=True,
                    key=f"edit_listing_location_action_{listing['id']}_empty",
                )

            update_public_location = location_action in {
                "Change pin",
                "Remove pin",
                "Yes, add a public pin",
            }
            if location_action in {"Change pin", "Yes, add a public pin"}:
                st.caption(
                    "Use an approximate location, not your exact address. The "
                    "saved point is rounded before it becomes public."
                )
                public_latitude, public_longitude = show_public_location_picker(
                    f"edit_listing_{listing['id']}_public_location",
                    listing["public_latitude"],
                    listing["public_longitude"],
                )
            elif location_action == "Remove pin":
                st.session_state[
                    f"edit_listing_{listing['id']}_public_location_latitude"
                ] = None
                st.session_state[
                    f"edit_listing_{listing['id']}_public_location_longitude"
                ] = None
                st.caption("The public map pin will be removed when you save.")

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
                        public_latitude=public_latitude,
                        public_longitude=public_longitude,
                        update_public_location=update_public_location,
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
            user = db.get_user_by_email(connection, user_email)
            if user is None:
                st.error("The logged-in account could not be found.")
            else:
                find_tab, list_tab, requests_tab = st.tabs(
                    ["Find storage", "List a space", "My requests"]
                )
                with find_tab:
                    show_listings(connection)
                with list_tab:
                    show_listing_form(connection, user_email)
                    show_my_listings(connection, user["id"])
                with requests_tab:
                    show_rental_requests(connection, user["id"])
            if st.button("Log out"):
                del st.session_state["user_email"]
                st.rerun()
            return

        find_tab, register_tab, login_tab = st.tabs(
            ["Find storage", "Register", "Log in"]
        )
        with find_tab:
            show_listings(connection)
        with register_tab:
            show_registration(connection)
        with login_tab:
            show_login(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()

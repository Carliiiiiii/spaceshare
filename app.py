"""Streamlit interface for browsing and managing SpaceShare listings."""

import html
from datetime import date, datetime
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium
from extra_streamlit_components import CookieManager

from auth_session import COOKIE_NAME, SESSION_TTL_SECONDS, create_session, read_session
import db
from supabase_backend import create_supabase_client
from logic import (
    PUBLIC_LOCATION_DECIMAL_PLACES,
    cancel_rental_request,
    create_rental_request,
    create_listing,
    delete_listing,
    expire_pending_rental_requests,
    get_listing_conversation_messages,
    get_listing_conversations,
    get_messages,
    get_pending_incoming_rental_request_count,
    get_unread_message_count,
    mark_listing_conversation_messages_read,
    mark_messages_read,
    register_user,
    send_listing_conversation_message,
    send_listing_question,
    send_message,
    update_listing,
    verify_user_password,
    update_rental_request_status,
    validate_public_location,
)


DATABASE_PATH = Path("spaceshare.sqlite3")
LOGO_PATH = Path(__file__).parent / "assets" / "spaceshare-logo.svg"
DEFAULT_MAP_CENTER = (38.7223, -9.1393)
LISTING_SORT_OPTIONS = (
    "Newest",
    "Price: low to high",
    "Price: high to low",
    "Size: largest first",
    "Size: smallest first",
)
RENTAL_REQUEST_STATUS_LABELS = {
    "accepted": "Booking confirmed",
    "cancelled": "Cancelled by requester",
    "expired": "Expired",
    "rejected": "Rejected",
}


def get_connection():
    """Open a database connection for the current Streamlit run."""
    try:
        has_supabase_settings = (
            "SUPABASE_URL" in st.secrets
            and "SUPABASE_SERVICE_ROLE_KEY" in st.secrets
        )
    except FileNotFoundError:
        # Streamlit raises this when no local secrets file exists. Supabase is
        # optional, so local development continues with the SQLite backend.
        return db.connect(DATABASE_PATH)
    except Exception as error:
        st.error(f"Online database configuration error: {error}")
        st.stop()

    if has_supabase_settings:
        try:
            return create_supabase_client(st.secrets)
        except Exception as error:
            st.error(f"Online database configuration error: {error}")
            st.stop()
    return db.connect(DATABASE_PATH)


def get_cookie_manager():
    """Return the browser-cookie component used for the signed session token."""
    return CookieManager(key="spaceshare_session_cookie")


def restore_logged_in_user(connection, cookie_manager):
    """Restore a user from a valid signed cookie, or clear an expired one."""
    current_email = st.session_state.get("user_email")
    if current_email:
        return current_email
    # CookieManager receives browser cookies through a component iframe. On a
    # fresh Streamlit run, give that iframe one rerun to return its first value.
    if not st.session_state.get("session_cookie_initialized"):
        st.session_state["session_cookie_initialized"] = True
        st.rerun()
    token = cookie_manager.get(COOKIE_NAME)
    email = read_session(token, st.secrets)
    if email is None:
        if token:
            cookie_manager.delete(COOKIE_NAME)
        return None
    if db.get_user_by_email(connection, email) is None:
        cookie_manager.delete(COOKIE_NAME)
        return None
    st.session_state["user_email"] = email
    return email


def show_brand_header(show_login_button=False, connection=None, cookie_manager=None):
    """Show the responsive SpaceShare brand header."""
    st.markdown(
        """
        <style>
        .spaceshare-logo { width: min(100%, 260px); height: auto; margin: 0 0 0.4rem 0; }
        [data-testid="stAppViewContainer"] { background: #F8FCFE; }
        [data-testid="stHeader"] { background: #F8FCFE; }
        [data-testid="stMainBlockContainer"] { max-width: 1800px; padding-left: 2rem; padding-right: 2rem; }
        h1, h2, h3 { color: #17324D; }
        [data-testid="stForm"] { border-color: #BFE8F8; border-radius: 0.75rem; }
        [data-testid="stVerticalBlockBorderWrapper"] { border-color: #BFE8F8; border-radius: 1rem; background: #FFFFFF; }
        .listing-meta { color: #17324D; font-size: 0.95rem; }
        .listing-price { color: #D95F1E; font-size: 1.2rem; font-weight: 700; }
        div.stButton > button[kind="primary"], div.stFormSubmitButton > button { background: #F77B32; color: white; border: 0; }
        div.stButton > button[kind="primary"]:hover, div.stFormSubmitButton > button:hover { background: #D95F1E; color: white; }
        .spaceshare-header { align-items: center; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    logo_column, _, action_column = st.columns((3, 6, 1), gap="small")
    with logo_column:
        st.image(str(LOGO_PATH), width=260)
    if show_login_button:
        with action_column:
            if st.button(
                "Register & Log in",
                type="primary",
                key="header_login_button",
            ):
                st.session_state["show_auth_panel"] = True
                st.rerun()


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


def show_login(connection, cookie_manager):
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
                normalized_email = email.strip().lower()
                st.session_state["user_email"] = normalized_email
                cookie_manager.set(
                    COOKIE_NAME,
                    create_session(normalized_email, st.secrets),
                    key="set_session_cookie",
                    max_age=SESSION_TTL_SECONDS,
                    secure=False,
                    same_site="lax",
                )
                st.success("Logged in. Refresh the page to continue.")
                st.stop()
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


def _sort_listings(listings, sort_option):
    """Return listings in the selected browse order."""
    if sort_option == "Price: low to high":
        return sorted(
            listings,
            key=lambda listing: (
                float(listing["price_per_month_eur"]),
                -int(listing["id"]),
            ),
        )
    if sort_option == "Price: high to low":
        return sorted(
            listings,
            key=lambda listing: (
                -float(listing["price_per_month_eur"]),
                -int(listing["id"]),
            ),
        )
    if sort_option == "Size: largest first":
        return sorted(
            listings,
            key=lambda listing: (-float(listing["size_sqm"]), -int(listing["id"])),
        )
    if sort_option == "Size: smallest first":
        return sorted(
            listings,
            key=lambda listing: (float(listing["size_sqm"]), -int(listing["id"])),
        )
    return sorted(listings, key=lambda listing: int(listing["id"]), reverse=True)


def _listing_id_for_map_point(locations, clicked_point):
    """Return a listing ID for one uniquely clicked public map point."""
    if not isinstance(clicked_point, dict):
        return None
    try:
        clicked_latitude = float(clicked_point["lat"])
        clicked_longitude = float(clicked_point["lng"])
    except (KeyError, TypeError, ValueError):
        return None

    matches = [
        listing["id"]
        for listing, latitude, longitude in locations
        if abs(latitude - clicked_latitude) < 0.000001
        and abs(longitude - clicked_longitude) < 0.000001
    ]
    return matches[0] if len(matches) == 1 else None


def _rental_request_status_label(request):
    """Return a human-readable status, including the response deadline."""
    if request["status"] != "pending":
        return RENTAL_REQUEST_STATUS_LABELS.get(
            request["status"], request["status"].title()
        )
    try:
        deadline = datetime.fromisoformat(
            request["expires_at"].replace("Z", "+00:00")
        )
    except (AttributeError, ValueError):
        return "Pending"
    return f"Pending — response due {deadline.strftime('%d %b %Y, %H:%M UTC')}"


def show_listing_map(
    listings,
    *,
    map_key="public_listing_map",
    is_detail_view=False,
    interactive=False,
):
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

    map_state = st_folium(
        listing_map,
        key=map_key,
        height=580,
        use_container_width=True,
        returned_objects=["last_object_clicked"] if interactive else [],
    ) or {}
    if is_detail_view:
        st.caption("This is an approximate public location, not an exact address.")
    else:
        st.caption(
            "Map pins are approximate public locations, not exact addresses. "
            f"{len(locations)} matching listing"
            f"{'s' if len(locations) != 1 else ''} shown on the map."
        )

    if interactive:
        selected_listing_id = _listing_id_for_map_point(
            locations, map_state.get("last_object_clicked")
        )
        if selected_listing_id is not None:
            st.session_state["selected_listing_id"] = selected_listing_id
            st.rerun()


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
            "Photo (optional — drag and drop or browse; JPG/PNG, max 5 MB)",
            type=["jpg", "jpeg", "png"],
            help="Drag and drop one image here or choose it from your device.",
            max_upload_size=5,
            width="stretch",
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


def show_listings(connection, *, include_map=True):
    selected_listing_id = st.session_state.get("selected_listing_id")
    if selected_listing_id is not None:
        selected_listing = db.get_listing_by_id(connection, selected_listing_id)
        if selected_listing is not None:
            show_listing_detail(connection, selected_listing)
            return []
        st.session_state.pop("selected_listing_id", None)
        st.warning("This listing is no longer available.")

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
        return []
    if requested_start is not None and requested_end <= requested_start:
        st.error("Rental end must be after rental start.")
        return []

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
        return []

    sort_column, view_column = st.columns((2, 2))
    with sort_column:
        sort_option = st.selectbox(
            "Sort by",
            LISTING_SORT_OPTIONS,
            key="listing_sort_option",
        )
    with view_column:
        view_mode = st.radio(
            "Show as",
            ("List", "Map"),
            horizontal=True,
            key="listing_view_mode",
        )
    listings = _sort_listings(listings, sort_option)
    st.caption(f"{len(listings)} listing{'s' if len(listings) != 1 else ''} found")

    if view_mode == "List":
        st.markdown("#### Listings")
        for listing in listings:
            show_listing_card(listing)
    elif include_map:
        show_listing_map(listings, interactive=True)
    return listings


def show_listing_card(listing):
    """Render one compact listing card for the browse view."""
    photo_url = listing["photo_url"]
    photo_data = listing["photo_data"]
    with st.container(border=True):
        media_column, details_column = st.columns((1, 2), gap="large")
        with media_column:
            if photo_url:
                st.image(photo_url)
            elif photo_data:
                st.image(photo_data)
            else:
                st.info("No photo available.")
        with details_column:
            st.markdown(f"### {listing['title']}")
            st.markdown(
                "<hr style='margin: -0.35rem 0 0.75rem 0; border: 0; "
                "border-top: 2px solid #D9E2E8;'>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**{listing['city']}**")
            description = str(listing["description"]).strip()
            summary = (
                description
                if len(description) <= 160
                else f"{description[:157].rstrip()}…"
            )
            st.write(summary)
            st.markdown(
                f"<div class='listing-price'>€{listing['price_per_month_eur']:.2f} / month</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='listing-meta'><b>{listing['size_sqm']} m²</b> · "
                f"Available {listing['available_from']} – "
                f"{listing['available_until'] or 'unlimited'}<br>"
                f"Minimum stay: {listing['minimum_rental_days']} days</div>",
                unsafe_allow_html=True,
            )

        if st.button("View details", key=f"listing_details_{listing['id']}"):
            st.session_state["selected_listing_id"] = listing["id"]
            st.rerun()


def show_listing_detail(connection, listing):
    """Render the complete listing information and its contact actions."""
    if st.button("← Back to listings", key="back_to_listing_results"):
        st.session_state.pop("selected_listing_id", None)
        st.rerun()

    st.subheader(listing["title"])
    photo_url = listing["photo_url"]
    photo_data = listing["photo_data"]
    media_column, details_column = st.columns((1, 2), gap="large")
    with media_column:
        if photo_url:
            st.image(photo_url, caption=listing["title"])
        elif photo_data:
            st.image(photo_data, caption=listing["title"])
        else:
            st.info("No photo available.")
    with details_column:
        st.markdown(f"**City:** {listing['city']}")
        st.markdown(
            f"<div class='listing-price'>€{listing['price_per_month_eur']:.2f} / month</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='listing-meta'><b>{listing['size_sqm']} m²</b><br>"
            f"Minimum stay: {listing['minimum_rental_days']} days</div>",
            unsafe_allow_html=True,
        )

    st.markdown("#### Description")
    st.write(listing["description"])
    st.markdown("#### Availability")
    st.write(f"Available from: {listing['available_from']}")
    st.write(f"Available until: {listing['available_until'] or 'Unlimited'}")
    show_listing_map(
        [listing],
        map_key=f"listing_detail_map_{listing['id']}",
        is_detail_view=True,
    )
    show_listing_contact_actions(connection, listing)


def show_listing_contact_actions(connection, listing):
    """Show chat and rental-request controls for one non-owner visitor."""
    st.markdown("#### Contact and request")
    if not st.session_state.get("user_email"):
        st.caption("Log in to ask a question or send a rental request.")
        return

    user = db.get_user_by_email(connection, st.session_state["user_email"])
    if user is None:
        st.error("The logged-in account could not be found.")
        return

    if db.is_listing_owner(connection, listing["id"], user["id"]):
        st.caption("This is your listing. You can edit it in My listings.")
        return

    question_form_key = f"listing_question_open_{listing['id']}"
    if st.button("Chat about this listing", key=f"chat_listing_{listing['id']}"):
        st.session_state[question_form_key] = True

    if st.session_state.get(question_form_key):
        with st.form(f"question_listing_{listing['id']}"):
            question_text = st.text_area(
                "Ask the listing owner a question",
                max_chars=1000,
                key=f"listing_question_text_{listing['id']}",
            )
            question_submitted = st.form_submit_button("Send question")

        if question_submitted:
            try:
                send_listing_question(
                    connection,
                    listing["id"],
                    user["id"],
                    question_text,
                )
            except (ValueError, PermissionError) as error:
                st.error(str(error))
            else:
                st.session_state[question_form_key] = False
                st.success("Question sent. Continue the conversation in Chats.")

    with st.form(f"request_listing_{listing['id']}"):
        earliest_request_start = date.fromisoformat(listing["available_from"])
        earliest_request_end = earliest_request_start + timedelta(
            days=int(listing["minimum_rental_days"])
        )
        request_start = st.date_input(
            "Rental start date",
            value=earliest_request_start,
            min_value=earliest_request_start,
            key=f"request_start_{listing['id']}",
        )
        request_end = st.date_input(
            "Rental end date",
            value=earliest_request_end,
            min_value=earliest_request_end,
            key=f"request_end_{listing['id']}",
        )
        request_submitted = st.form_submit_button("Send rental request")

    if request_submitted:
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
            st.success("Rental request sent. It expires in 7 days unless answered.")


def show_rental_requests(connection, user_id):
    st.subheader("Requests")
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
            f"{request['end_date']} — **{_rental_request_status_label(request)}**"
        )
        if request["status"] == "pending":
            if st.button("Cancel request", key=f"cancel_request_{request['id']}"):
                try:
                    cancel_rental_request(connection, request["id"], user_id)
                except PermissionError as error:
                    st.error(str(error))
                else:
                    st.rerun()

    st.markdown("#### Requests for my listings")
    if not incoming_requests:
        st.info("No one has requested your listings yet.")
    for request in incoming_requests:
        st.write(
            f"**{request['title']}** — {request['start_date']} to "
            f"{request['end_date']} — **{_rental_request_status_label(request)}**"
        )
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


def show_chats(connection, user_id):
    st.subheader("Chats")
    requests = db.get_rental_requests_for_user(connection, user_id)
    listing_conversations = get_listing_conversations(connection, user_id)
    if not requests and not listing_conversations:
        st.info("No chats yet. Ask a question on a listing or send a rental request.")
        return

    if listing_conversations:
        st.markdown("#### Questions about listings")
        for conversation in listing_conversations:
            role = (
                "Question about your listing"
                if conversation["owner_id"] == user_id
                else "Your question"
            )
            st.markdown(f"**{role}: {conversation['title']}**")
            show_listing_conversation_chat(connection, user_id, conversation)

    if requests:
        st.markdown("#### Rental-request chats")
        sent_requests = [
            request for request in requests if request["owner_id"] != user_id
        ]
        incoming_requests = [
            request for request in requests if request["owner_id"] == user_id
        ]
        chat_requests = sent_requests + incoming_requests

        for request in chat_requests:
            role = (
                "Sent request"
                if request["owner_id"] != user_id
                else "Request for my listing"
            )
            st.markdown(
                f"**{role}: {request['title']}** · "
                f"Status: {_rental_request_status_label(request)}"
            )
            show_request_chat(connection, user_id, request)


def show_listing_conversation_chat(connection, user_id, conversation):
    with st.expander("Open chat"):
        messages = get_listing_conversation_messages(
            connection, conversation["id"], user_id
        )
        mark_listing_conversation_messages_read(
            connection, conversation["id"], user_id
        )
        if messages:
            for message in messages:
                is_current_user = message["sender_id"] == user_id
                sender_role = "You" if is_current_user else (
                    "Interested user"
                    if message["sender_id"] == message["participant_id"]
                    else "Listing owner"
                )
                try:
                    sent_at = datetime.fromisoformat(message["sent_at"])
                    formatted_time = sent_at.strftime("%d %b %Y, %H:%M UTC")
                except ValueError:
                    formatted_time = message["sent_at"]
                with st.chat_message("user" if is_current_user else "assistant"):
                    st.markdown(f"**{sender_role}**")
                    st.caption(formatted_time)
                    st.write(message["message"])
        else:
            st.info("No messages yet.")

        with st.form(f"listing_conversation_message_form_{conversation['id']}"):
            message_text = st.text_area(
                "Message",
                max_chars=1000,
                key=f"listing_conversation_message_text_{conversation['id']}",
            )
            send_submitted = st.form_submit_button("Send message")
        if send_submitted:
            try:
                send_listing_conversation_message(
                    connection, conversation["id"], user_id, message_text
                )
            except (ValueError, PermissionError) as error:
                st.error(str(error))
            else:
                st.success("Message sent.")

        if st.button(
            "Refresh messages",
            key=f"refresh_listing_conversation_{conversation['id']}",
        ):
            st.rerun()


def show_request_chat(connection, user_id, request):
    with st.expander("Open chat"):
        messages = get_messages(connection, request["id"], user_id)
        mark_messages_read(connection, request["id"], user_id)
        if messages:
            for message in messages:
                is_current_user = message["sender_id"] == user_id
                sender_role = "You" if is_current_user else (
                    "Renter" if message["sender_id"] == message["requester_id"]
                    else "Listing owner"
                )
                try:
                    sent_at = datetime.fromisoformat(message["sent_at"])
                    formatted_time = sent_at.strftime("%d %b %Y, %H:%M UTC")
                except ValueError:
                    formatted_time = message["sent_at"]
                with st.chat_message("user" if is_current_user else "assistant"):
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
                photo_url = listing["photo_url"]
                photo_data = listing["photo_data"]
                if photo_url:
                    st.image(photo_url, caption="Current photo")
                elif photo_data:
                    st.image(photo_data, caption="Current photo")
                edit_photo = st.checkbox(
                    "Edit photo", key=f"photo_edit_{listing['id']}"
                )
                uploaded_photo = None
                remove_photo = False
                if edit_photo:
                    uploaded_photo = st.file_uploader(
                        "New photo (drag and drop or browse; JPG/PNG, max 5 MB)",
                        type=["jpg", "jpeg", "png"],
                        key=f"photo_upload_{listing['id']}",
                        help="Drag and drop one image here or choose it from your device.",
                        max_upload_size=5,
                        width="stretch",
                    )
                    remove_photo = st.checkbox(
                        "Remove photo instead",
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
                if edit_photo and not uploaded_photo and not remove_photo:
                    st.error("Choose a new photo or select Remove photo instead.")
                else:
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
                        st.rerun()

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

    connection = get_connection()
    cookie_manager = get_cookie_manager()
    try:
        expire_pending_rental_requests(connection)
        user_email = restore_logged_in_user(connection, cookie_manager)
        show_brand_header(
            show_login_button=not user_email,
            connection=connection,
            cookie_manager=cookie_manager,
        )

        if user_email:
            st.success(f"Welcome, {user_email}!")
            user = db.get_user_by_email(connection, user_email)
            if user is None:
                st.error("The logged-in account could not be found.")
            else:
                pending_request_count = get_pending_incoming_rental_request_count(
                    connection, user["id"]
                )
                requests_label = "Requests"
                if pending_request_count:
                    requests_label += " ①"
                unread_count = get_unread_message_count(connection, user["id"])
                chats_label = "Chats"
                if unread_count:
                    chats_label += " ①"
                find_tab, list_tab, my_listings_tab, requests_tab, chats_tab = st.tabs(
                    [
                        "Find storage",
                        "List a space",
                        "My listings",
                        requests_label,
                        chats_label,
                    ]
                )
                with find_tab:
                    show_listings(connection)
                with list_tab:
                    show_listing_form(connection, user_email)
                with my_listings_tab:
                    show_my_listings(connection, user["id"])
                with requests_tab:
                    show_rental_requests(connection, user["id"])
                with chats_tab:
                    show_chats(connection, user["id"])
            if st.button("Log out"):
                cookie_manager.delete(COOKIE_NAME)
                del st.session_state["user_email"]
                st.rerun()
            return

        search_column, right_column = st.columns((4, 2), gap="large")
        with search_column:
            st.subheader("Find storage")
            listings = show_listings(connection, include_map=False)
        with right_column:
            if st.session_state.get("show_auth_panel"):
                register_tab, login_tab = st.tabs(["Register", "Log in"])
                with register_tab:
                    show_registration(connection)
                with login_tab:
                    show_login(connection, cookie_manager)
                if st.button("Close", key="close_auth_panel"):
                    st.session_state["show_auth_panel"] = False
                    st.rerun()
            if listings:
                show_listing_map(listings)
    finally:
        connection.close()


if __name__ == "__main__":
    main()

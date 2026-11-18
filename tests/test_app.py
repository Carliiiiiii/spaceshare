"""Tests for the Streamlit application's local startup behavior."""

import app


class _StreamlitWithoutSecrets:
    class _Secrets:
        def __contains__(self, key):
            raise FileNotFoundError("No local Streamlit secrets file")

    secrets = _Secrets()


def test_get_connection_falls_back_to_sqlite_without_streamlit_secrets(monkeypatch):
    connection = object()
    monkeypatch.setattr(app, "st", _StreamlitWithoutSecrets())
    monkeypatch.setattr(app.db, "connect", lambda path: connection)

    assert app.get_connection() is connection


def test_sort_listings_supports_price_size_and_newest_orders():
    listings = [
        {"id": 1, "price_per_month_eur": 80, "size_sqm": 8},
        {"id": 3, "price_per_month_eur": 50, "size_sqm": 12},
        {"id": 2, "price_per_month_eur": 50, "size_sqm": 20},
    ]

    assert [listing["id"] for listing in app._sort_listings(listings, "Newest")] == [
        3,
        2,
        1,
    ]
    assert [
        listing["id"]
        for listing in app._sort_listings(listings, "Price: low to high")
    ] == [3, 2, 1]
    assert [
        listing["id"]
        for listing in app._sort_listings(listings, "Size: largest first")
    ] == [2, 3, 1]


def test_listing_id_for_map_point_selects_only_one_matching_marker():
    garage = {"id": 1}
    basement = {"id": 2}
    locations = [(garage, 38.72, -9.14), (basement, 38.73, -9.15)]

    assert app._listing_id_for_map_point(
        locations, {"lat": 38.72, "lng": -9.14}
    ) == 1
    assert app._listing_id_for_map_point(
        locations, {"lat": 38.7, "lng": -9.1}
    ) is None
    assert app._listing_id_for_map_point(
        [(garage, 38.72, -9.14), (basement, 38.72, -9.14)],
        {"lat": 38.72, "lng": -9.14},
    ) is None


def test_rental_request_status_labels_show_confirmed_booking_and_deadline():
    assert app._rental_request_status_label({"status": "accepted"}) == "Booking confirmed"
    assert app._rental_request_status_label(
        {
            "status": "pending",
            "expires_at": "2026-12-08T15:30:00+00:00",
        }
    ) == "Pending — response due 08 Dec 2026, 15:30 UTC"

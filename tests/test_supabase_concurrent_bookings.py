"""Optional integration tests for the PostgreSQL booking constraint.

Run these only against a disposable Supabase test project after applying the
atomic booking migration. They are skipped for normal local test runs.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

import db
from logic import create_listing, create_rental_request, register_user, update_rental_request_status
from supabase_backend import create_supabase_client


TEST_URL = os.getenv("SPACESHARE_TEST_SUPABASE_URL")
TEST_KEY = os.getenv("SPACESHARE_TEST_SUPABASE_SERVICE_ROLE_KEY")
pytestmark = pytest.mark.skipif(
    not TEST_URL or not TEST_KEY,
    reason="Set disposable Supabase test-project credentials to run PostgreSQL concurrency tests.",
)


def _setup_requests(start_dates):
    connection = create_supabase_client(
        {
            "SUPABASE_URL": TEST_URL,
            "SUPABASE_SERVICE_ROLE_KEY": TEST_KEY,
        }
    )
    suffix = uuid4().hex
    owner_id = register_user(connection, f"owner-{suffix}@example.com", "test-password")
    requester_id = register_user(
        connection, f"requester-{suffix}@example.com", "test-password"
    )
    listing_id = create_listing(
        connection,
        owner_id,
        "Concurrency test garage",
        "Lisbon",
        "Disposable integration-test listing",
        10,
        50,
        "2026-12-01",
        1,
        "2027-02-01",
    )
    request_ids = [
        create_rental_request(connection, listing_id, requester_id, start, end)
        for start, end in start_dates
    ]
    return connection, owner_id, requester_id, listing_id, request_ids


def _cleanup(connection, owner_id, requester_id, listing_id, request_ids):
    connection.client.table("rental_requests").delete().in_("id", request_ids).execute()
    connection.client.table("listings").delete().eq("id", listing_id).execute()
    connection.client.table("users").delete().eq("id", owner_id).execute()
    connection.client.table("users").delete().eq("id", requester_id).execute()


def test_supabase_concurrent_overlapping_acceptances_allow_exactly_one():
    connection, owner_id, requester_id, listing_id, request_ids = _setup_requests(
        [("2026-12-01", "2027-01-01"), ("2026-12-15", "2027-01-15")]
    )
    try:
        def accept(request_id):
            independent_connection = create_supabase_client(
                {
                    "SUPABASE_URL": TEST_URL,
                    "SUPABASE_SERVICE_ROLE_KEY": TEST_KEY,
                }
            )
            try:
                update_rental_request_status(
                    independent_connection, request_id, owner_id, "accepted"
                )
                return "accepted"
            except ValueError:
                return "pending"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(accept, request_ids))

        assert sorted(results) == ["accepted", "pending"]
    finally:
        _cleanup(connection, owner_id, requester_id, listing_id, request_ids)


def test_supabase_adjacent_acceptances_are_allowed():
    connection, owner_id, requester_id, listing_id, request_ids = _setup_requests(
        [("2026-12-01", "2027-01-01"), ("2027-01-01", "2027-02-01")]
    )
    try:
        update_rental_request_status(connection, request_ids[0], owner_id, "accepted")
        update_rental_request_status(connection, request_ids[1], owner_id, "accepted")
        rows = (
            connection.client.table("rental_requests")
            .select("status")
            .in_("id", request_ids)
            .execute()
            .data
        )
        assert [row["status"] for row in rows].count("accepted") == 2
    finally:
        _cleanup(connection, owner_id, requester_id, listing_id, request_ids)

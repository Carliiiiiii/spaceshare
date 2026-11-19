"""SQLite storage for SpaceShare accounts."""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from supabase_backend import SupabaseConnection


RENTAL_REQUEST_EXPIRY_DAYS = 7


def connect(database_path: Path) -> sqlite3.Connection:
    """Open the database and create required tables if they do not exist."""
    # Streamlit may run script reruns in different threads.
    connection = sqlite3.connect(str(database_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            bio TEXT NOT NULL DEFAULT '',
            verification_status TEXT NOT NULL DEFAULT 'unverified',
            profile_photo_data BLOB,
            profile_photo_mime_type TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            city TEXT NOT NULL,
            description TEXT NOT NULL,
            size_sqm REAL NOT NULL,
            price_per_month_eur REAL NOT NULL,
            available_from TEXT NOT NULL,
            available_until TEXT,
            photo_data BLOB,
            photo_mime_type TEXT,
            public_latitude REAL,
            public_longitude REAL,
            minimum_rental_days INTEGER NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rental_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            requester_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (listing_id) REFERENCES listings (id),
            FOREIGN KEY (requester_id) REFERENCES users (id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rental_request_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            FOREIGN KEY (rental_request_id) REFERENCES rental_requests (id),
            FOREIGN KEY (sender_id) REFERENCES users (id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS message_reads (
            rental_request_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            last_read_message_id INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (rental_request_id, user_id),
            FOREIGN KEY (rental_request_id) REFERENCES rental_requests (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(listing_id, participant_id),
            FOREIGN KEY (listing_id) REFERENCES listings (id),
            FOREIGN KEY (participant_id) REFERENCES users (id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES listing_conversations (id),
            FOREIGN KEY (sender_id) REFERENCES users (id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_conversation_reads (
            conversation_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            last_read_message_id INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (conversation_id, user_id),
            FOREIGN KEY (conversation_id) REFERENCES listing_conversations (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_favorites (
            user_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, listing_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (listing_id) REFERENCES listings (id) ON DELETE CASCADE
        )
        """
    )
    listing_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(listings)")
    }
    user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
    if "display_name" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
    if "bio" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN bio TEXT NOT NULL DEFAULT ''")
    if "verification_status" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'unverified'")
    if "profile_photo_data" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN profile_photo_data BLOB")
    if "profile_photo_mime_type" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN profile_photo_mime_type TEXT")
    if "available_until" not in listing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN available_until TEXT")
    if "photo_data" not in listing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN photo_data BLOB")
    if "photo_mime_type" not in listing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN photo_mime_type TEXT")
    if "public_latitude" not in listing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN public_latitude REAL")
    if "public_longitude" not in listing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN public_longitude REAL")
    rental_request_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(rental_requests)")
    }
    if "created_at" not in rental_request_columns:
        connection.execute("ALTER TABLE rental_requests ADD COLUMN created_at TEXT")
    if "expires_at" not in rental_request_columns:
        connection.execute("ALTER TABLE rental_requests ADD COLUMN expires_at TEXT")
    now = datetime.now(timezone.utc)
    connection.execute(
        "UPDATE rental_requests SET created_at = ? WHERE created_at IS NULL",
        (now.isoformat(timespec="seconds"),),
    )
    connection.execute(
        "UPDATE rental_requests SET expires_at = ? WHERE expires_at IS NULL",
        (
            (now + timedelta(days=RENTAL_REQUEST_EXPIRY_DAYS)).isoformat(
                timespec="seconds"
            ),
        ),
    )
    connection.commit()
    return connection


def create_user(connection: sqlite3.Connection, email: str, password_hash: str, display_name: str = "Storage user") -> int:
    """Store one account and return its id."""
    if isinstance(connection, SupabaseConnection):
        try:
            response = (
                connection.client.table("users")
                .insert({"email": email, "password_hash": password_hash, "display_name": display_name})
                .execute()
            )
        except Exception as error:
            raise ValueError("An account with this email already exists.") from error
        if not response.data:
            raise ValueError("The account could not be created.")
        return int(response.data[0]["id"])
    try:
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
            (email, password_hash, display_name),
        )
        connection.commit()
    except sqlite3.IntegrityError as error:
        raise ValueError("An account with this email already exists.") from error
    return int(cursor.lastrowid)


def get_user_by_email(
    connection: sqlite3.Connection, email: str
) -> Optional[sqlite3.Row]:
    """Return an account by normalized email, or None if it does not exist."""
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("users")
            .select("id,email,password_hash,display_name,bio,verification_status,profile_photo_url")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    return connection.execute(
        "SELECT id, email, password_hash, display_name, bio, verification_status, profile_photo_data, profile_photo_mime_type FROM users WHERE email = ?",
        (email,),
    ).fetchone()


def get_public_user_profile(connection, user_id):
    """Return only the profile fields that may be shown to other users."""
    fields = "id,display_name,bio,verification_status,profile_photo_url"
    if isinstance(connection, SupabaseConnection):
        response = connection.client.table("users").select(fields).eq("id", user_id).limit(1).execute()
        return response.data[0] if response.data else None
    return connection.execute(
        "SELECT id, display_name, bio, verification_status, profile_photo_data FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def update_user_display_name(connection, user_id, display_name: str) -> None:
    """Update a user's public display name without exposing their email."""
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("users")
            .update({"display_name": display_name})
            .eq("id", user_id)
            .execute()
        )
        if not response.data:
            raise ValueError("The display name could not be updated.")
        return
    cursor = connection.execute(
        "UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id)
    )
    connection.commit()
    if cursor.rowcount != 1:
        raise ValueError("The display name could not be updated.")


def update_user_profile(connection, user_id, display_name, bio, verification_status, photo_data, photo_mime_type):
    """Update the public profile fields owned by one user."""
    if isinstance(connection, SupabaseConnection):
        payload = {"display_name": display_name, "bio": bio, "verification_status": verification_status}
        if photo_data:
            path = f"profiles/{user_id}/{uuid.uuid4().hex}"
            connection.client.storage.from_(connection.settings.storage_bucket).upload(path, photo_data, {"content-type": photo_mime_type, "upsert": "true"})
            payload["profile_photo_path"] = path
            payload["profile_photo_url"] = connection.client.storage.from_(connection.settings.storage_bucket).get_public_url(path)
        response = connection.client.table("users").update(payload).eq("id", user_id).execute()
        if not response.data:
            raise ValueError("The profile could not be updated.")
        return
    connection.execute("UPDATE users SET display_name=?, bio=?, verification_status=?, profile_photo_data=COALESCE(?, profile_photo_data), profile_photo_mime_type=COALESCE(?, profile_photo_mime_type) WHERE id=?", (display_name, bio, verification_status, photo_data, photo_mime_type, user_id))
    connection.commit()


def create_listing(
    connection: sqlite3.Connection,
    owner_id: int,
    title: str,
    city: str,
    description: str,
    size_sqm: float,
    price_per_month_eur: float,
    available_from: str,
    minimum_rental_days: int,
    available_until: Optional[str] = None,
    photo_data: Optional[bytes] = None,
    photo_mime_type: Optional[str] = None,
    *,
    public_latitude: Optional[float] = None,
    public_longitude: Optional[float] = None,
) -> int:
    """Store one storage listing and return its id."""
    if isinstance(connection, SupabaseConnection):
        payload = {
            "owner_id": owner_id,
            "title": title,
            "city": city,
            "description": description,
            "size_sqm": size_sqm,
            "price_per_month_eur": price_per_month_eur,
            "available_from": available_from,
            "available_until": available_until,
            "photo_data": None,
            "photo_mime_type": photo_mime_type,
            "public_latitude": public_latitude,
            "public_longitude": public_longitude,
            "minimum_rental_days": minimum_rental_days,
        }
        response = connection.client.table("listings").insert(payload).execute()
        if not response.data:
            raise ValueError("The listing could not be created.")
        listing_id = int(response.data[0]["id"])
        if photo_data:
            path = f"listings/{listing_id}/{uuid.uuid4().hex}"
            connection.client.storage.from_(connection.settings.storage_bucket).upload(
                path, photo_data, {"content-type": photo_mime_type, "upsert": "true"}
            )
            photo_url = connection.client.storage.from_(connection.settings.storage_bucket).get_public_url(path)
            connection.client.table("listings").update({"photo_path": path, "photo_url": photo_url}).eq("id", listing_id).execute()
        return listing_id
    cursor = connection.execute(
        """
        INSERT INTO listings (
            owner_id, title, city, description, size_sqm,
            price_per_month_eur, available_from, available_until,
            photo_data, photo_mime_type, public_latitude, public_longitude,
            minimum_rental_days
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_id,
            title,
            city,
            description,
            size_sqm,
            price_per_month_eur,
            available_from,
            available_until,
            photo_data,
            photo_mime_type,
            public_latitude,
            public_longitude,
            minimum_rental_days,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def get_listings(
    connection: sqlite3.Connection,
    *,
    city: Optional[str] = None,
    minimum_size_sqm: Optional[float] = None,
    maximum_price_per_month_eur: Optional[float] = None,
    available_on: Optional[str] = None,
    requested_start: Optional[str] = None,
    requested_end: Optional[str] = None,
) -> list:
    """Return public listing fields, optionally limited by browse filters."""
    if isinstance(connection, SupabaseConnection):
        try:
            response = (
                connection.client.table("listings")
                .select(
                    "id,title,city,description,size_sqm,price_per_month_eur,"
                    "available_from,available_until,photo_mime_type,"
                    "photo_path,photo_url,public_latitude,public_longitude,"
                    "minimum_rental_days"
                )
                .order("id", desc=True)
                .execute()
            )
        except Exception:
            response = (
                connection.client.table("listings")
                .select(
                    "id,title,city,description,size_sqm,price_per_month_eur,"
                    "available_from,available_until,minimum_rental_days"
                )
                .order("id", desc=True)
                .execute()
            )
        rows = response.data or []
        for row in rows:
            row.setdefault("photo_data", None)
            row.setdefault("photo_mime_type", None)
            row.setdefault("photo_url", None)
            row.setdefault("public_latitude", None)
            row.setdefault("public_longitude", None)
        if city and city.strip():
            needle = city.strip().lower()
            rows = [row for row in rows if needle in row["city"].lower()]
        if minimum_size_sqm is not None:
            rows = [row for row in rows if row["size_sqm"] >= minimum_size_sqm]
        if maximum_price_per_month_eur is not None:
            rows = [
                row for row in rows
                if row["price_per_month_eur"] <= maximum_price_per_month_eur
            ]
        if available_on is not None:
            rows = [
                row for row in rows
                if row["available_from"] <= available_on
                and (row["available_until"] is None or row["available_until"] >= available_on)
            ]
        if (requested_start is None) != (requested_end is None):
            raise ValueError("Select both rental dates to filter by availability.")
        if requested_start is not None and requested_end <= requested_start:
            raise ValueError("Rental end must be after rental start.")
        if requested_start is not None:
            accepted = (
                connection.client.table("rental_requests")
                .select("listing_id,start_date,end_date")
                .eq("status", "accepted")
                .execute()
                .data
                or []
            )
            blocked = {
                row["listing_id"]
                for row in accepted
                if row["start_date"] < requested_end and row["end_date"] > requested_start
            }
            rows = [row for row in rows if row["id"] not in blocked]
            rows = [
                row for row in rows
                if row["available_from"] <= requested_start
                and (row["available_until"] is None or row["available_until"] >= requested_end)
            ]
            # Date strings are ISO dates; calculate the duration without relying
            # on database-specific date functions.
            from datetime import date as _date
            requested_days = (_date.fromisoformat(requested_end) - _date.fromisoformat(requested_start)).days
            rows = [row for row in rows if requested_days >= row["minimum_rental_days"]]
        return rows
    if (requested_start is None) != (requested_end is None):
        raise ValueError("Select both rental dates to filter by availability.")
    if requested_start is not None and requested_end <= requested_start:
        raise ValueError("Rental end must be after rental start.")

    filters = []
    parameters = []

    if city is not None and city.strip():
        filters.append("LOWER(city) LIKE ?")
        parameters.append(f"%{city.strip().lower()}%")
    if minimum_size_sqm is not None:
        filters.append("size_sqm >= ?")
        parameters.append(minimum_size_sqm)
    if maximum_price_per_month_eur is not None:
        filters.append("price_per_month_eur <= ?")
        parameters.append(maximum_price_per_month_eur)
    if available_on is not None:
        filters.append(
            "available_from <= ? "
            "AND (available_until IS NULL OR available_until >= ?)"
        )
        parameters.extend((available_on, available_on))
    if requested_start is not None and requested_end is not None:
        filters.append(
            "available_from <= ? "
            "AND (available_until IS NULL OR available_until >= ?) "
            "AND NOT EXISTS ("
            "SELECT 1 FROM rental_requests AS accepted_request "
            "WHERE accepted_request.listing_id = listings.id "
            "AND accepted_request.status = 'accepted' "
            "AND accepted_request.start_date < ? "
            "AND accepted_request.end_date > ?"
            ")"
        )
        parameters.extend(
            (requested_start, requested_end, requested_end, requested_start)
        )

    query = """
        SELECT id, title, city, description, size_sqm,
               price_per_month_eur, available_from, available_until,
               photo_data, photo_mime_type, NULL AS photo_url,
               public_latitude, public_longitude,
               minimum_rental_days
        FROM listings
    """
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY id DESC"
    return connection.execute(query, parameters).fetchall()


def get_listing_by_id(connection, listing_id):
    """Return one public listing by ID, or None when it no longer exists."""
    if isinstance(connection, SupabaseConnection):
        fields = (
            "id,title,city,description,size_sqm,price_per_month_eur,"
            "available_from,available_until,photo_mime_type,"
            "photo_path,photo_url,public_latitude,public_longitude,"
            "minimum_rental_days"
        )
        try:
            response = (
                connection.client.table("listings")
                .select(fields)
                .eq("id", listing_id)
                .limit(1)
                .execute()
            )
        except Exception:
            response = (
                connection.client.table("listings")
                .select(
                    "id,title,city,description,size_sqm,price_per_month_eur,"
                    "available_from,available_until,minimum_rental_days"
                )
                .eq("id", listing_id)
                .limit(1)
                .execute()
            )
        if not response.data:
            return None
        listing = response.data[0]
        listing.setdefault("photo_data", None)
        listing.setdefault("photo_mime_type", None)
        listing.setdefault("photo_url", None)
        listing.setdefault("public_latitude", None)
        listing.setdefault("public_longitude", None)
        return listing
    return connection.execute(
        """
        SELECT id, title, city, description, size_sqm,
               price_per_month_eur, available_from, available_until,
               photo_data, photo_mime_type, NULL AS photo_url,
               public_latitude, public_longitude,
               minimum_rental_days
        FROM listings
        WHERE id = ?
        """,
        (listing_id,),
    ).fetchone()


def get_favorite_listing_ids(connection, user_id) -> list[int]:
    """Return a user's saved listing IDs, most recently saved first."""
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("listing_favorites")
            .select("listing_id")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [int(row["listing_id"]) for row in (response.data or [])]
    rows = connection.execute(
        """SELECT listing_id FROM listing_favorites
           WHERE user_id = ? ORDER BY created_at DESC, listing_id DESC""",
        (user_id,),
    ).fetchall()
    return [int(row["listing_id"]) for row in rows]


def toggle_listing_favorite(connection, user_id, listing_id, created_at) -> bool:
    """Save a listing when absent, otherwise remove it; return its new state."""
    if isinstance(connection, SupabaseConnection):
        existing = (
            connection.client.table("listing_favorites")
            .select("listing_id")
            .eq("user_id", user_id)
            .eq("listing_id", listing_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            (
                connection.client.table("listing_favorites")
                .delete()
                .eq("user_id", user_id)
                .eq("listing_id", listing_id)
                .execute()
            )
            return False
        response = (
            connection.client.table("listing_favorites")
            .insert(
                {
                    "user_id": user_id,
                    "listing_id": listing_id,
                    "created_at": created_at,
                }
            )
            .execute()
        )
        if not response.data:
            raise ValueError("The listing could not be saved.")
        return True

    existing = connection.execute(
        """SELECT 1 FROM listing_favorites
           WHERE user_id = ? AND listing_id = ?""",
        (user_id, listing_id),
    ).fetchone()
    if existing:
        connection.execute(
            "DELETE FROM listing_favorites WHERE user_id = ? AND listing_id = ?",
            (user_id, listing_id),
        )
        connection.commit()
        return False
    connection.execute(
        """INSERT INTO listing_favorites (user_id, listing_id, created_at)
           VALUES (?, ?, ?)""",
        (user_id, listing_id, created_at),
    )
    connection.commit()
    return True


def get_listings_by_owner(connection: sqlite3.Connection, owner_id: int) -> list:
    """Return listings owned by one account."""
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("listings")
            .select(
                "id,title,city,description,size_sqm,price_per_month_eur,"
                "available_from,available_until,photo_mime_type,"
                "photo_path,photo_url,public_latitude,public_longitude,"
                "minimum_rental_days"
            )
            .eq("owner_id", owner_id)
            .order("id", desc=True)
            .execute()
        )
        rows = response.data or []
        for row in rows:
            row.setdefault("photo_data", None)
            row.setdefault("photo_mime_type", None)
            row.setdefault("photo_url", None)
            row.setdefault("public_latitude", None)
            row.setdefault("public_longitude", None)
        return rows
    return connection.execute(
        """
        SELECT id, title, city, description, size_sqm,
               price_per_month_eur, available_from, available_until,
               photo_data, photo_mime_type, NULL AS photo_url,
               public_latitude, public_longitude,
               minimum_rental_days
        FROM listings
        WHERE owner_id = ?
        ORDER BY id DESC
        """,
        (owner_id,),
    ).fetchall()


def update_listing(
    connection: sqlite3.Connection,
    listing_id: int,
    owner_id: int,
    title: str,
    city: str,
    description: str,
    size_sqm: float,
    price_per_month_eur: float,
    available_from: str,
    minimum_rental_days: int,
    available_until: Optional[str] = None,
    photo_data: Optional[bytes] = None,
    photo_mime_type: Optional[str] = None,
    *,
    public_latitude: Optional[float] = None,
    public_longitude: Optional[float] = None,
    update_public_location: bool = False,
) -> None:
    """Update a listing only when the supplied owner owns it."""
    if isinstance(connection, SupabaseConnection):
        old = (
            connection.client.table("listings")
            .select("photo_path")
            .eq("id", listing_id)
            .eq("owner_id", owner_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not old:
            raise PermissionError("You do not own this listing.")
        payload = {
            "title": title,
            "city": city,
            "description": description,
            "size_sqm": size_sqm,
            "price_per_month_eur": price_per_month_eur,
            "available_from": available_from,
            "available_until": available_until,
            "photo_data": None,
            "photo_mime_type": photo_mime_type,
            "minimum_rental_days": minimum_rental_days,
        }
        if update_public_location:
            payload.update(
                public_latitude=public_latitude,
                public_longitude=public_longitude,
            )
        response = (
            connection.client.table("listings")
            .update(payload)
            .eq("id", listing_id)
            .eq("owner_id", owner_id)
            .execute()
        )
        if not response.data:
            raise PermissionError("You do not own this listing.")
        if photo_data:
            path = f"listings/{listing_id}/{uuid.uuid4().hex}"
            connection.client.storage.from_(connection.settings.storage_bucket).upload(
                path, photo_data, {"content-type": photo_mime_type, "upsert": "true"}
            )
            connection.client.table("listings").update({
                "photo_path": path,
                "photo_url": connection.client.storage.from_(connection.settings.storage_bucket).get_public_url(path),
            }).eq("id", listing_id).eq("owner_id", owner_id).execute()
            if old[0].get("photo_path") and old[0]["photo_path"] != path:
                connection.client.storage.from_(connection.settings.storage_bucket).remove([old[0]["photo_path"]])
        return
    assignments = [
        "title = ?",
        "city = ?",
        "description = ?",
        "size_sqm = ?",
        "price_per_month_eur = ?",
        "available_from = ?",
        "available_until = ?",
        "photo_data = ?",
        "photo_mime_type = ?",
        "minimum_rental_days = ?",
    ]
    parameters = [
        title,
        city,
        description,
        size_sqm,
        price_per_month_eur,
        available_from,
        available_until,
        photo_data,
        photo_mime_type,
        minimum_rental_days,
    ]
    if update_public_location:
        assignments.extend(("public_latitude = ?", "public_longitude = ?"))
        parameters.extend((public_latitude, public_longitude))

    parameters.extend((listing_id, owner_id))
    cursor = connection.execute(
        "UPDATE listings SET "
        + ", ".join(assignments)
        + " WHERE id = ? AND owner_id = ?",
        parameters,
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise PermissionError("You do not own this listing.")
    connection.commit()


def delete_listing(
    connection: sqlite3.Connection, listing_id: int, owner_id: int
) -> None:
    """Delete a listing only when the supplied owner owns it."""
    if isinstance(connection, SupabaseConnection):
        existing = (
            connection.client.table("listings")
            .select("photo_path")
            .eq("id", listing_id)
            .eq("owner_id", owner_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not existing:
            raise PermissionError("You do not own this listing.")
        response = (
            connection.client.table("listings")
            .delete()
            .eq("id", listing_id)
            .eq("owner_id", owner_id)
            .execute()
        )
        if not response.data:
            raise PermissionError("You do not own this listing.")
        if existing[0].get("photo_path"):
            connection.client.storage.from_(connection.settings.storage_bucket).remove([existing[0]["photo_path"]])
        return
    cursor = connection.execute(
        "DELETE FROM listings WHERE id = ? AND owner_id = ?",
        (listing_id, owner_id),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise PermissionError("You do not own this listing.")
    connection.commit()


def create_rental_request(
    connection,
    listing_id,
    requester_id,
    start_date,
    end_date,
    created_at,
    expires_at,
):
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("rental_requests")
            .insert({
                "listing_id": listing_id,
                "requester_id": requester_id,
                "start_date": start_date,
                "end_date": end_date,
                "status": "pending",
                "created_at": created_at,
                "expires_at": expires_at,
            })
            .execute()
        )
        if not response.data:
            raise ValueError("The rental request could not be created.")
        return int(response.data[0]["id"])
    cursor = connection.execute(
        """INSERT INTO rental_requests
           (listing_id, requester_id, start_date, end_date, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (listing_id, requester_id, start_date, end_date, created_at, expires_at),
    )
    connection.commit()
    return int(cursor.lastrowid)


def expire_pending_rental_requests(connection, now):
    """Mark every pending request past its response deadline as expired."""
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("rental_requests")
            .update({"status": "expired"})
            .eq("status", "pending")
            .lte("expires_at", now)
            .execute()
        )
        return len(response.data or [])
    cursor = connection.execute(
        """UPDATE rental_requests SET status = 'expired'
           WHERE status = 'pending' AND expires_at <= ?""",
        (now,),
    )
    connection.commit()
    return cursor.rowcount


def cancel_rental_request(connection, request_id, requester_id):
    """Let only the requester withdraw a still-pending rental request."""
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("rental_requests")
            .update({"status": "cancelled"})
            .eq("id", request_id)
            .eq("requester_id", requester_id)
            .eq("status", "pending")
            .execute()
        )
        if not response.data:
            raise PermissionError("You cannot cancel this rental request.")
        return
    cursor = connection.execute(
        """UPDATE rental_requests SET status = 'cancelled'
           WHERE id = ? AND requester_id = ? AND status = 'pending'""",
        (request_id, requester_id),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise PermissionError("You cannot cancel this rental request.")
    connection.commit()


def get_listing_for_request(connection, listing_id):
    """Return the fields needed to validate a rental request."""
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("listings")
            .select("owner_id,available_from,available_until,minimum_rental_days")
            .eq("id", listing_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    return connection.execute(
        "SELECT owner_id, available_from, available_until, minimum_rental_days FROM listings WHERE id = ?",
        (listing_id,),
    ).fetchone()


def get_confirmed_booking_periods(connection, listing_id):
    """Return confirmed half-open booking periods for one listing."""
    if isinstance(connection, SupabaseConnection):
        response = connection.client.table("rental_requests").select("start_date,end_date").eq("listing_id", listing_id).eq("status", "accepted").execute()
        return response.data or []
    return connection.execute(
        "SELECT start_date, end_date FROM rental_requests WHERE listing_id = ? AND status = 'accepted' ORDER BY start_date",
        (listing_id,),
    ).fetchall()


def has_accepted_rental_request_overlap(
    connection: sqlite3.Connection,
    listing_id: int,
    start_date: str,
    end_date: str,
) -> bool:
    """Return whether an accepted request overlaps the half-open period."""
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("rental_requests")
            .select("id,start_date,end_date")
            .eq("listing_id", listing_id)
            .eq("status", "accepted")
            .execute()
        )
        return any(
            row["start_date"] < end_date and row["end_date"] > start_date
            for row in (response.data or [])
        )
    return connection.execute(
        """SELECT 1
           FROM rental_requests
           WHERE listing_id = ? AND status = 'accepted'
             AND start_date < ? AND end_date > ?
           LIMIT 1""",
        (listing_id, end_date, start_date),
    ).fetchone() is not None


def get_rental_requests_for_user(connection, user_id):
    expire_pending_rental_requests(
        connection, datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    if isinstance(connection, SupabaseConnection):
        listings = (
            connection.client.table("listings")
            .select("id,title,owner_id")
            .eq("owner_id", user_id)
            .execute()
            .data
            or []
        )
        owned_ids = {row["id"] for row in listings}
        sent = (
            connection.client.table("rental_requests")
            .select(
                "id,listing_id,requester_id,start_date,end_date,status,"
                "created_at,expires_at"
            )
            .eq("requester_id", user_id)
            .execute()
            .data
            or []
        )
        incoming = []
        if owned_ids:
            incoming = (
                connection.client.table("rental_requests")
                .select(
                    "id,listing_id,requester_id,start_date,end_date,status,"
                    "created_at,expires_at"
                )
                .in_("listing_id", list(owned_ids))
                .execute()
                .data
                or []
            )
        by_id = {row["id"]: row for row in listings}
        result = []
        for request in {row["id"]: row for row in sent + incoming}.values():
            listing = by_id.get(request["listing_id"])
            if listing is None:
                listing = (
                    connection.client.table("listings")
                    .select("id,title,owner_id")
                    .eq("id", request["listing_id"])
                    .limit(1)
                    .execute()
                    .data
                    or [{}]
                )[0]
            owner = (
                connection.client.table("users")
                .select("display_name")
                .eq("id", listing.get("owner_id"))
                .limit(1)
                .execute()
                .data
                or [{}]
            )[0].get("display_name")
            requester = (
                connection.client.table("users")
                .select("display_name")
                .eq("id", request.get("requester_id"))
                .limit(1)
                .execute()
                .data
                or [{}]
            )[0].get("display_name")
            result.append({**request, "title": listing.get("title"), "owner_id": listing.get("owner_id"),
                           "owner_name": owner, "requester_name": requester})
        return sorted(result, key=lambda row: row["id"], reverse=True)
    return connection.execute(
        """SELECT requests.id, requests.listing_id, requests.requester_id,
                  requests.start_date, requests.end_date, requests.status,
                  requests.created_at, requests.expires_at,
                  listings.title, listings.owner_id,
                  owner.display_name AS owner_name,
                  requester.display_name AS requester_name
           FROM rental_requests AS requests
           JOIN listings ON listings.id = requests.listing_id
           JOIN users AS owner ON owner.id = listings.owner_id
           JOIN users AS requester ON requester.id = requests.requester_id
           WHERE requests.requester_id = ? OR listings.owner_id = ?
           ORDER BY requests.id DESC""",
        (user_id, user_id),
    ).fetchall()


def get_pending_incoming_rental_request_count(connection, user_id):
    """Count pending requests received for listings owned by a user."""
    expire_pending_rental_requests(
        connection, datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    if isinstance(connection, SupabaseConnection):
        listings = (
            connection.client.table("listings")
            .select("id")
            .eq("owner_id", user_id)
            .execute()
            .data
            or []
        )
        owned_ids = [listing["id"] for listing in listings]
        if not owned_ids:
            return 0
        requests = (
            connection.client.table("rental_requests")
            .select("id")
            .in_("listing_id", owned_ids)
            .eq("status", "pending")
            .execute()
            .data
            or []
        )
        return len(requests)
    return connection.execute(
        """SELECT COUNT(*)
           FROM rental_requests AS requests
           JOIN listings ON listings.id = requests.listing_id
           WHERE listings.owner_id = ? AND requests.status = 'pending'""",
        (user_id,),
    ).fetchone()[0]


def update_rental_request_status(connection, request_id, owner_id, status):
    expire_pending_rental_requests(
        connection, datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    if isinstance(connection, SupabaseConnection):
        if status == "accepted":
            try:
                connection.client.rpc(
                    "accept_rental_request",
                    {
                        "p_request_id": request_id,
                        "p_owner_id": owner_id,
                    },
                ).execute()
            except Exception as error:
                error_text = str(error)
                if (
                    "accepted_rental_requests_no_overlap" in error_text
                    or "exclusion constraint" in error_text
                ):
                    raise ValueError(
                        "This rental period overlaps an accepted request. "
                        "The request remains pending."
                    ) from error
                if "You cannot change this rental request." in error_text:
                    raise PermissionError(
                        "You cannot change this rental request."
                    ) from error
                raise
            return
        request = (
            connection.client.table("rental_requests")
            .select("id,listing_id,start_date,end_date,status")
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not request:
            raise PermissionError("You cannot change this rental request.")
        request = request[0]
        listing = (
            connection.client.table("listings")
            .select("owner_id")
            .eq("id", request["listing_id"])
            .limit(1)
            .execute()
            .data
            or []
        )
        if not listing or listing[0]["owner_id"] != owner_id or request["status"] != "pending":
            raise PermissionError("You cannot change this rental request.")
        if status == "accepted" and has_accepted_rental_request_overlap(
            connection, request["listing_id"], request["start_date"], request["end_date"]
        ):
            raise ValueError("This rental period overlaps an accepted request. The request remains pending.")
        response = (
            connection.client.table("rental_requests")
            .update({"status": status})
            .eq("id", request_id)
            .eq("status", "pending")
            .execute()
        )
        if not response.data:
            raise PermissionError("You cannot change this rental request.")
        return
    if status == "accepted":
        conflicting_request = connection.execute(
            """SELECT 1
               FROM rental_requests AS candidate
               JOIN rental_requests AS accepted
                 ON accepted.listing_id = candidate.listing_id
                AND accepted.status = 'accepted'
                AND candidate.id <> accepted.id
                AND candidate.start_date < accepted.end_date
                AND candidate.end_date > accepted.start_date
               JOIN listings ON listings.id = candidate.listing_id
               WHERE candidate.id = ? AND listings.owner_id = ?""",
            (request_id, owner_id),
        ).fetchone()
        if conflicting_request is not None:
            raise ValueError(
                "This rental period overlaps an accepted request. "
                "The request remains pending."
            )
    cursor = connection.execute(
        """UPDATE rental_requests SET status = ?
           WHERE id = ? AND listing_id IN
           (SELECT id FROM listings WHERE owner_id = ?) AND status = 'pending'""",
        (status, request_id, owner_id),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise PermissionError("You cannot change this rental request.")
    connection.commit()


def _user_is_request_participant(connection, request_id, user_id) -> bool:
    if isinstance(connection, SupabaseConnection):
        request = (
            connection.client.table("rental_requests")
            .select("requester_id,listing_id")
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not request:
            return False
        owner = (
            connection.client.table("listings")
            .select("owner_id")
            .eq("id", request[0]["listing_id"])
            .limit(1)
            .execute()
            .data
            or []
        )
        return bool(owner and (request[0]["requester_id"] == user_id or owner[0]["owner_id"] == user_id))
    return connection.execute(
        """SELECT 1 FROM rental_requests
           JOIN listings ON listings.id = rental_requests.listing_id
           WHERE rental_requests.id = ?
             AND (rental_requests.requester_id = ? OR listings.owner_id = ?)""",
        (request_id, user_id, user_id),
    ).fetchone() is not None


def create_message(connection, request_id, sender_id, message, sent_at):
    if not _user_is_request_participant(connection, request_id, sender_id):
        raise PermissionError("Only the renter and listing owner can send messages.")
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("messages")
            .insert({
                "rental_request_id": request_id,
                "sender_id": sender_id,
                "message": message,
                "sent_at": sent_at,
            })
            .execute()
        )
        if not response.data:
            raise ValueError("The message could not be sent.")
        return int(response.data[0]["id"])
    cursor = connection.execute(
        "INSERT INTO messages (rental_request_id, sender_id, message, sent_at) VALUES (?, ?, ?, ?)",
        (request_id, sender_id, message, sent_at),
    )
    connection.commit()
    return int(cursor.lastrowid)


def get_messages(connection, request_id, user_id):
    if not _user_is_request_participant(connection, request_id, user_id):
        raise PermissionError("Only the renter and listing owner can read messages.")
    if isinstance(connection, SupabaseConnection):
        request = (
            connection.client.table("rental_requests")
            .select("requester_id,listing_id")
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        owner = (
            connection.client.table("listings")
            .select("owner_id")
            .eq("id", request[0]["listing_id"])
            .limit(1)
            .execute()
            .data
            or []
        ) if request else []
        response = (
            connection.client.table("messages")
            .select("id,message,sent_at,sender_id")
            .eq("rental_request_id", request_id)
            .order("sent_at")
            .order("id")
            .execute()
        )
        return [
            {**row, "requester_id": request[0]["requester_id"], "owner_id": owner[0]["owner_id"]}
            for row in (response.data or [])
        ]
    return connection.execute(
        """SELECT messages.id, messages.message, messages.sent_at,
                  messages.sender_id, rental_requests.requester_id,
                  listings.owner_id
           FROM messages
           JOIN rental_requests ON rental_requests.id = messages.rental_request_id
           JOIN listings ON listings.id = rental_requests.listing_id
           WHERE messages.rental_request_id = ?
           ORDER BY messages.sent_at ASC, messages.id ASC""",
        (request_id,),
    ).fetchall()


def get_unread_message_count(connection, user_id):
    """Count messages from other participants that the user has not read."""
    if isinstance(connection, SupabaseConnection):
        requests = get_rental_requests_for_user(connection, user_id)
        total = 0
        for request in requests:
            messages = get_messages(connection, request["id"], user_id)
            read = (
                connection.client.table("message_reads")
                .select("last_read_message_id")
                .eq("rental_request_id", request["id"])
                .eq("user_id", user_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            last_read = read[0]["last_read_message_id"] if read else 0
            total += sum(1 for message in messages if message["id"] > last_read and message["sender_id"] != user_id)
        return total + get_unread_listing_conversation_message_count(
            connection, user_id
        )
    rental_message_count = connection.execute(
        """SELECT COUNT(*) FROM messages
           JOIN rental_requests ON rental_requests.id = messages.rental_request_id
           JOIN listings ON listings.id = rental_requests.listing_id
           LEFT JOIN message_reads
             ON message_reads.rental_request_id = messages.rental_request_id
            AND message_reads.user_id = ?
           WHERE (rental_requests.requester_id = ? OR listings.owner_id = ?)
             AND messages.sender_id <> ?
             AND messages.id > COALESCE(message_reads.last_read_message_id, 0)""",
        (user_id, user_id, user_id, user_id),
    ).fetchone()[0]
    return rental_message_count + get_unread_listing_conversation_message_count(
        connection, user_id
    )


def mark_messages_read(connection, request_id, user_id):
    """Mark all current messages in a request as read for a participant."""
    if not _user_is_request_participant(connection, request_id, user_id):
        raise PermissionError("Only the renter and listing owner can read messages.")
    if isinstance(connection, SupabaseConnection):
        messages = get_messages(connection, request_id, user_id)
        latest = messages[-1]["id"] if messages else 0
        connection.client.table("message_reads").upsert({
            "rental_request_id": request_id,
            "user_id": user_id,
            "last_read_message_id": latest,
        }).execute()
        return
    latest = connection.execute(
        "SELECT COALESCE(MAX(id), 0) FROM messages WHERE rental_request_id = ?",
        (request_id,),
    ).fetchone()[0]
    connection.execute(
        """INSERT INTO message_reads (rental_request_id, user_id, last_read_message_id)
           VALUES (?, ?, ?)
           ON CONFLICT(rental_request_id, user_id)
           DO UPDATE SET last_read_message_id = excluded.last_read_message_id""",
        (request_id, user_id, latest),
    )
    connection.commit()


def _get_listing_owner_id(connection, listing_id):
    if isinstance(connection, SupabaseConnection):
        listing = (
            connection.client.table("listings")
            .select("owner_id")
            .eq("id", listing_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return listing[0]["owner_id"] if listing else None
    row = connection.execute(
        "SELECT owner_id FROM listings WHERE id = ?", (listing_id,)
    ).fetchone()
    return row["owner_id"] if row else None


def is_listing_owner(connection, listing_id, user_id):
    """Return whether a user owns the specified listing."""
    return _get_listing_owner_id(connection, listing_id) == user_id


def get_or_create_listing_conversation(
    connection, listing_id, participant_id, created_at
):
    """Return the direct conversation for a listing and interested user."""
    owner_id = _get_listing_owner_id(connection, listing_id)
    if owner_id is None:
        raise ValueError("Listing not found.")
    if owner_id == participant_id:
        raise PermissionError("You cannot start a chat about your own listing.")

    if isinstance(connection, SupabaseConnection):
        existing = (
            connection.client.table("listing_conversations")
            .select("id")
            .eq("listing_id", listing_id)
            .eq("participant_id", participant_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            return int(existing[0]["id"])
        try:
            response = (
                connection.client.table("listing_conversations")
                .insert(
                    {
                        "listing_id": listing_id,
                        "participant_id": participant_id,
                        "created_at": created_at,
                    }
                )
                .execute()
            )
        except Exception as error:
            existing = (
                connection.client.table("listing_conversations")
                .select("id")
                .eq("listing_id", listing_id)
                .eq("participant_id", participant_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            if existing:
                return int(existing[0]["id"])
            raise ValueError("The conversation could not be started.") from error
        if not response.data:
            raise ValueError("The conversation could not be started.")
        return int(response.data[0]["id"])

    connection.execute(
        """INSERT INTO listing_conversations (listing_id, participant_id, created_at)
           VALUES (?, ?, ?)
           ON CONFLICT(listing_id, participant_id) DO NOTHING""",
        (listing_id, participant_id, created_at),
    )
    connection.commit()
    return connection.execute(
        """SELECT id FROM listing_conversations
           WHERE listing_id = ? AND participant_id = ?""",
        (listing_id, participant_id),
    ).fetchone()["id"]


def _get_listing_conversation(connection, conversation_id):
    if isinstance(connection, SupabaseConnection):
        conversation = (
            connection.client.table("listing_conversations")
            .select("id,listing_id,participant_id,created_at")
            .eq("id", conversation_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not conversation:
            return None
        listing = (
            connection.client.table("listings")
            .select("owner_id,title")
            .eq("id", conversation[0]["listing_id"])
            .limit(1)
            .execute()
            .data
            or []
        )
        if not listing:
            return None
        return {
            **conversation[0],
            "owner_id": listing[0]["owner_id"],
            "title": listing[0]["title"],
        }
    return connection.execute(
        """SELECT conversations.id, conversations.listing_id,
                  conversations.participant_id, conversations.created_at,
                  listings.owner_id, listings.title
           FROM listing_conversations AS conversations
           JOIN listings ON listings.id = conversations.listing_id
           WHERE conversations.id = ?""",
        (conversation_id,),
    ).fetchone()


def _user_is_listing_conversation_participant(connection, conversation_id, user_id):
    conversation = _get_listing_conversation(connection, conversation_id)
    return bool(
        conversation
        and (
            conversation["participant_id"] == user_id
            or conversation["owner_id"] == user_id
        )
    )


def get_listing_conversations_for_user(connection, user_id):
    """Return direct listing conversations visible to the current user."""
    if isinstance(connection, SupabaseConnection):
        owned_listings = (
            connection.client.table("listings")
            .select("id,title,owner_id")
            .eq("owner_id", user_id)
            .execute()
            .data
            or []
        )
        listings_by_id = {listing["id"]: listing for listing in owned_listings}
        participant_conversations = (
            connection.client.table("listing_conversations")
            .select("id,listing_id,participant_id,created_at")
            .eq("participant_id", user_id)
            .execute()
            .data
            or []
        )
        incoming_conversations = []
        if listings_by_id:
            incoming_conversations = (
                connection.client.table("listing_conversations")
                .select("id,listing_id,participant_id,created_at")
                .in_("listing_id", list(listings_by_id))
                .execute()
                .data
                or []
            )
        conversations = {
            conversation["id"]: conversation
            for conversation in participant_conversations + incoming_conversations
        }.values()
        result = []
        for conversation in conversations:
            listing = listings_by_id.get(conversation["listing_id"])
            if listing is None:
                listing_result = (
                    connection.client.table("listings")
                    .select("id,title,owner_id")
                    .eq("id", conversation["listing_id"])
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if not listing_result:
                    continue
                listing = listing_result[0]
            participant = (
                connection.client.table("users")
                .select("display_name")
                .eq("id", conversation["participant_id"])
                .limit(1)
                .execute()
                .data
                or [{}]
            )[0].get("display_name")
            owner = (
                connection.client.table("users")
                .select("display_name")
                .eq("id", listing["owner_id"])
                .limit(1)
                .execute()
                .data
                or [{}]
            )[0].get("display_name")
            result.append(
                {
                    **conversation,
                    "title": listing["title"],
                    "owner_id": listing["owner_id"],
                    "participant_name": participant,
                    "owner_name": owner,
                }
            )
        return sorted(
            result,
            key=lambda conversation: (
                conversation["created_at"],
                conversation["id"],
            ),
            reverse=True,
        )
    return connection.execute(
        """SELECT conversations.id, conversations.listing_id,
                  conversations.participant_id, conversations.created_at,
                  listings.title, listings.owner_id,
                  participant.display_name AS participant_name,
                  owner.display_name AS owner_name
           FROM listing_conversations AS conversations
           JOIN listings ON listings.id = conversations.listing_id
           JOIN users AS participant ON participant.id = conversations.participant_id
           JOIN users AS owner ON owner.id = listings.owner_id
           WHERE conversations.participant_id = ? OR listings.owner_id = ?
           ORDER BY conversations.created_at DESC, conversations.id DESC""",
        (user_id, user_id),
    ).fetchall()


def create_listing_conversation_message(
    connection, conversation_id, sender_id, message, sent_at
):
    """Store a message only when its sender participates in the conversation."""
    if not _user_is_listing_conversation_participant(
        connection, conversation_id, sender_id
    ):
        raise PermissionError(
            "Only the interested user and listing owner can send messages."
        )
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("listing_conversation_messages")
            .insert(
                {
                    "conversation_id": conversation_id,
                    "sender_id": sender_id,
                    "message": message,
                    "sent_at": sent_at,
                }
            )
            .execute()
        )
        if not response.data:
            raise ValueError("The message could not be sent.")
        return int(response.data[0]["id"])
    cursor = connection.execute(
        """INSERT INTO listing_conversation_messages
           (conversation_id, sender_id, message, sent_at)
           VALUES (?, ?, ?, ?)""",
        (conversation_id, sender_id, message, sent_at),
    )
    connection.commit()
    return int(cursor.lastrowid)


def get_listing_conversation_messages(connection, conversation_id, user_id):
    """Return direct conversation messages only to either participant."""
    if not _user_is_listing_conversation_participant(
        connection, conversation_id, user_id
    ):
        raise PermissionError(
            "Only the interested user and listing owner can read messages."
        )
    conversation = _get_listing_conversation(connection, conversation_id)
    if isinstance(connection, SupabaseConnection):
        response = (
            connection.client.table("listing_conversation_messages")
            .select("id,message,sent_at,sender_id")
            .eq("conversation_id", conversation_id)
            .order("sent_at")
            .order("id")
            .execute()
        )
        return [
            {
                **message,
                "participant_id": conversation["participant_id"],
                "owner_id": conversation["owner_id"],
            }
            for message in (response.data or [])
        ]
    return connection.execute(
        """SELECT messages.id, messages.message, messages.sent_at,
                  messages.sender_id, conversations.participant_id,
                  listings.owner_id
           FROM listing_conversation_messages AS messages
           JOIN listing_conversations AS conversations
             ON conversations.id = messages.conversation_id
           JOIN listings ON listings.id = conversations.listing_id
           WHERE messages.conversation_id = ?
           ORDER BY messages.sent_at ASC, messages.id ASC""",
        (conversation_id,),
    ).fetchall()


def get_unread_listing_conversation_message_count(connection, user_id):
    """Count unread direct-listing messages from the other participant."""
    if isinstance(connection, SupabaseConnection):
        total = 0
        for conversation in get_listing_conversations_for_user(connection, user_id):
            messages = get_listing_conversation_messages(
                connection, conversation["id"], user_id
            )
            read = (
                connection.client.table("listing_conversation_reads")
                .select("last_read_message_id")
                .eq("conversation_id", conversation["id"])
                .eq("user_id", user_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            last_read = read[0]["last_read_message_id"] if read else 0
            total += sum(
                1
                for message in messages
                if message["id"] > last_read and message["sender_id"] != user_id
            )
        return total
    return connection.execute(
        """SELECT COUNT(*)
           FROM listing_conversation_messages AS messages
           JOIN listing_conversations AS conversations
             ON conversations.id = messages.conversation_id
           JOIN listings ON listings.id = conversations.listing_id
           LEFT JOIN listing_conversation_reads AS reads
             ON reads.conversation_id = messages.conversation_id
            AND reads.user_id = ?
           WHERE (conversations.participant_id = ? OR listings.owner_id = ?)
             AND messages.sender_id <> ?
             AND messages.id > COALESCE(reads.last_read_message_id, 0)""",
        (user_id, user_id, user_id, user_id),
    ).fetchone()[0]


def mark_listing_conversation_messages_read(connection, conversation_id, user_id):
    """Mark all direct-listing messages currently visible to a user as read."""
    if not _user_is_listing_conversation_participant(
        connection, conversation_id, user_id
    ):
        raise PermissionError(
            "Only the interested user and listing owner can read messages."
        )
    if isinstance(connection, SupabaseConnection):
        messages = get_listing_conversation_messages(
            connection, conversation_id, user_id
        )
        latest = messages[-1]["id"] if messages else 0
        connection.client.table("listing_conversation_reads").upsert(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "last_read_message_id": latest,
            }
        ).execute()
        return
    latest = connection.execute(
        """SELECT COALESCE(MAX(id), 0)
           FROM listing_conversation_messages WHERE conversation_id = ?""",
        (conversation_id,),
    ).fetchone()[0]
    connection.execute(
        """INSERT INTO listing_conversation_reads
           (conversation_id, user_id, last_read_message_id)
           VALUES (?, ?, ?)
           ON CONFLICT(conversation_id, user_id)
           DO UPDATE SET last_read_message_id = excluded.last_read_message_id""",
        (conversation_id, user_id, latest),
    )
    connection.commit()

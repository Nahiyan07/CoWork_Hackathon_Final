from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import ACCESS_TOKEN_EXPIRE_SECONDS, JWT_ALGORITHM, JWT_SECRET
from app.database import Base, engine
from app.main import app
from app.services import ratelimit


def z(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ratelimit.reset()
    yield
    Base.metadata.drop_all(bind=engine)
    ratelimit.reset()


@pytest.fixture
def client():
    return TestClient(app)


def register(client: TestClient, org="acme", username="alice", password="pass123"):
    return client.post("/auth/register", json={"org_name": org, "username": username, "password": password})


def login(client: TestClient, org="acme", username="alice", password="pass123"):
    res = client.post("/auth/login", json={"org_name": org, "username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def create_room(client: TestClient, tokens: dict, name="Blue", rate=1000):
    res = client.post("/rooms", headers=auth(tokens), json={"name": name, "capacity": 4, "hourly_rate_cents": rate})
    assert res.status_code == 201, res.text
    return res.json()


def create_booking(client: TestClient, tokens: dict, room_id: int, start: datetime, hours=1):
    return client.post(
        "/bookings",
        headers=auth(tokens),
        json={"room_id": room_id, "start_time": z(start), "end_time": z(start + timedelta(hours=hours))},
    )


def setup_org_room(client: TestClient, org="acme", admin="admin", member="member", rate=1000):
    reg_admin = register(client, org, admin)
    assert reg_admin.status_code == 201
    admin_tokens = login(client, org, admin)
    room = create_room(client, admin_tokens, rate=rate)
    reg_mem = register(client, org, member)
    assert reg_mem.status_code == 201
    member_tokens = login(client, org, member)
    return admin_tokens, member_tokens, room


def test_registration_admin_member_and_duplicate_username(client):
    first = register(client, "org1", "alice")
    assert first.status_code == 201
    assert first.json()["role"] == "admin"
    second = register(client, "org1", "bob")
    assert second.status_code == 201
    assert second.json()["role"] == "member"
    dup = register(client, "org1", "alice")
    assert dup.status_code == 409
    assert dup.json()["code"] == "USERNAME_TAKEN"
    other_org_same_name = register(client, "org2", "alice")
    assert other_org_same_name.status_code == 201


def test_login_invalid_credentials(client):
    register(client)
    bad = client.post("/auth/login", json={"org_name": "acme", "username": "alice", "password": "wrong"})
    assert bad.status_code == 401
    assert bad.json()["code"] == "INVALID_CREDENTIALS"


def test_access_expiry_claim_duration_refresh_single_use_and_logout(client):
    register(client)
    tokens = login(client)
    payload = jwt.decode(tokens["access_token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["exp"] - payload["iat"] == ACCESS_TOKEN_EXPIRE_SECONDS
    required = {"sub", "org", "role", "jti", "iat", "exp", "type"}
    assert required.issubset(payload.keys())

    refreshed = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    reused = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401

    logout = client.post("/auth/logout", headers=auth(tokens))
    assert logout.status_code == 200
    after = client.get("/rooms", headers=auth(tokens))
    assert after.status_code == 401


def test_room_creation_admin_only_and_cross_org_room_access(client):
    admin_a, member_a, room_a = setup_org_room(client, "a", "admina", "mema")
    member_create = client.post("/rooms", headers=auth(member_a), json={"name": "x", "capacity": 1, "hourly_rate_cents": 100})
    assert member_create.status_code == 403
    assert member_create.json()["code"] == "FORBIDDEN"

    register(client, "b", "adminb")
    admin_b = login(client, "b", "adminb")
    cross = create_booking(client, admin_b, room_a["id"], datetime.now(timezone.utc) + timedelta(days=1), 1)
    assert cross.status_code == 404
    assert cross.json()["code"] == "ROOM_NOT_FOUND"


def test_valid_booking_datetime_conversion_and_price(client):
    _admin, member, room = setup_org_room(client, rate=1234)
    start_local = (datetime.now(timezone.utc) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    payload_start = start_local.astimezone(timezone(timedelta(hours=6))).isoformat()
    payload_end = (start_local + timedelta(hours=2)).astimezone(timezone(timedelta(hours=6))).isoformat()
    res = client.post("/bookings", headers=auth(member), json={"room_id": room["id"], "start_time": payload_start, "end_time": payload_end})
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["price_cents"] == 2468
    assert data["start_time"].endswith("Z")
    assert data["end_time"].endswith("Z")


def test_invalid_booking_windows(client):
    _admin, member, room = setup_org_room(client)
    now = datetime.now(timezone.utc)
    cases = [
        (now - timedelta(hours=1), 1),
        (now + timedelta(hours=2), -1),
        (now + timedelta(hours=2), 0.5),
        (now + timedelta(hours=2), 9),
    ]
    for start, hours in cases:
        end = start + timedelta(hours=hours)
        res = client.post("/bookings", headers=auth(member), json={"room_id": room["id"], "start_time": z(start), "end_time": z(end)})
        assert res.status_code == 400, res.text
        assert res.json()["code"] == "INVALID_BOOKING_WINDOW"


def test_double_booking_conflict_and_back_to_back_allowed(client):
    _admin, member, room = setup_org_room(client)
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=2)
    assert create_booking(client, member, room["id"], start, 2).status_code == 201
    conflict = create_booking(client, member, room["id"], start + timedelta(hours=1), 1)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "ROOM_CONFLICT"
    back_to_back = create_booking(client, member, room["id"], start + timedelta(hours=2), 1)
    assert back_to_back.status_code == 201


def test_quota_limit_across_rooms(client):
    admin, member, room1 = setup_org_room(client)
    room2 = create_room(client, admin, "Green")
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
    for i in range(3):
        room = room1 if i % 2 == 0 else room2
        res = create_booking(client, member, room["id"], base + timedelta(hours=i * 2), 1)
        assert res.status_code == 201, res.text
    fourth = create_booking(client, member, room2["id"], base + timedelta(hours=8), 1)
    assert fourth.status_code == 409
    assert fourth.json()["code"] == "QUOTA_EXCEEDED"


def test_rate_limit_counts_failed_requests(client):
    _admin, member, _room = setup_org_room(client)
    bad_payload = {"room_id": 99999, "start_time": z(datetime.now(timezone.utc) + timedelta(days=1)), "end_time": z(datetime.now(timezone.utc) + timedelta(days=1, hours=1))}
    for _ in range(20):
        res = client.post("/bookings", headers=auth(member), json=bad_payload)
        assert res.status_code == 404
    over = client.post("/bookings", headers=auth(member), json=bad_payload)
    assert over.status_code == 429
    assert over.json()["code"] == "RATE_LIMITED"


def test_member_and_admin_booking_visibility(client):
    admin, member1, room = setup_org_room(client, member="member1")
    register(client, "acme", "member2")
    member2 = login(client, "acme", "member2")
    start = datetime.now(timezone.utc) + timedelta(days=3)
    booking = create_booking(client, member1, room["id"], start, 1).json()
    hidden = client.get(f"/bookings/{booking['id']}", headers=auth(member2))
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "BOOKING_NOT_FOUND"
    admin_view = client.get(f"/bookings/{booking['id']}", headers=auth(admin))
    assert admin_view.status_code == 200
    assert admin_view.json()["id"] == booking["id"]


def test_cancellation_refunds_duplicate_prevention_and_refund_log(client):
    _admin, member, room = setup_org_room(client, rate=1001)
    start = datetime.now(timezone.utc) + timedelta(hours=36)
    booking = create_booking(client, member, room["id"], start, 1).json()
    cancel = client.post(f"/bookings/{booking['id']}/cancel", headers=auth(member))
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["refund_percent"] == 50
    assert cancel.json()["refund_amount_cents"] == 501
    duplicate = client.post(f"/bookings/{booking['id']}/cancel", headers=auth(member))
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "ALREADY_CANCELLED"
    detail = client.get(f"/bookings/{booking['id']}", headers=auth(member)).json()
    assert len(detail["refunds"]) == 1
    assert detail["refunds"][0]["amount_cents"] == 501


def test_cancellation_zero_and_full_refund(client):
    _admin, member, room = setup_org_room(client, org="refunds", admin="ra", member="rm", rate=1000)
    b1 = create_booking(client, member, room["id"], datetime.now(timezone.utc) + timedelta(hours=50), 1).json()
    c1 = client.post(f"/bookings/{b1['id']}/cancel", headers=auth(member))
    assert c1.json()["refund_percent"] == 100
    b2 = create_booking(client, member, room["id"], datetime.now(timezone.utc) + timedelta(hours=3), 1).json()
    c2 = client.post(f"/bookings/{b2['id']}/cancel", headers=auth(member))
    assert c2.json()["refund_percent"] == 0
    assert c2.json()["refund_amount_cents"] == 0


def test_usage_report_includes_zero_booking_rooms_availability_sorting_and_stats(client):
    admin, member, room1 = setup_org_room(client, rate=1500)
    room2 = create_room(client, admin, "Empty")
    day = (datetime.now(timezone.utc) + timedelta(days=5)).date()
    start2 = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=14)
    start1 = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=9)
    b2 = create_booking(client, member, room1["id"], start2, 1)
    b1 = create_booking(client, member, room1["id"], start1, 1)
    assert b1.status_code == 201 and b2.status_code == 201
    avail = client.get(f"/rooms/{room1['id']}/availability?date={day.isoformat()}", headers=auth(member))
    assert avail.status_code == 200
    busy = avail.json()["busy"]
    assert [x["start_time"] for x in busy] == sorted(x["start_time"] for x in busy)
    stats = client.get(f"/rooms/{room1['id']}/stats", headers=auth(member)).json()
    assert stats["total_confirmed_bookings"] == 2
    assert stats["total_revenue_cents"] == 3000
    report = client.get(f"/admin/usage-report?from={day.isoformat()}&to={day.isoformat()}", headers=auth(admin))
    assert report.status_code == 200, report.text
    rooms = {r["room_id"]: r for r in report.json()["rooms"]}
    assert rooms[room1["id"]]["confirmed_bookings"] == 2
    assert rooms[room2["id"]]["confirmed_bookings"] == 0


def test_pagination_ordering_no_skip_or_repeat(client):
    _admin, member, room = setup_org_room(client)
    base_day = (datetime.now(timezone.utc) + timedelta(days=7)).date()
    times = [
        datetime.combine(base_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12),
        datetime.combine(base_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=9),
        datetime.combine(base_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=15),
    ]
    for start in times:
        assert create_booking(client, member, room["id"], start, 1).status_code == 201
    p1 = client.get("/bookings?page=1&limit=2", headers=auth(member)).json()
    p2 = client.get("/bookings?page=2&limit=2", headers=auth(member)).json()
    ids = [b["id"] for b in p1["items"] + p2["items"]]
    starts = [b["start_time"] for b in p1["items"] + p2["items"]]
    assert p1["total"] == 3 and p2["total"] == 3
    assert len(ids) == len(set(ids)) == 3
    assert starts == sorted(starts)

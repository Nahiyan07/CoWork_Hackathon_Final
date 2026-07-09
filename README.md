# CoWork: Multi-Tenant Coworking Space Booking API

A FastAPI backend for managing coworking-space organizations, rooms, bookings, cancellations, refunds, usage reports, room availability, and room statistics in a multi-tenant environment.

This repository is prepared for the **IUT 12th ICT Fest Bdapps Agentic AI Hackathon Preliminary Round**. The challenge is a bug-fix task: the original backend contained hidden bugs, and the goal was to fix them while preserving the existing API contract exactly.

## Hackathon Context

CoWork is evaluated by a black-box grader that interacts with the application only through the public HTTP API. Because of that, the implementation preserves:

- Endpoint paths
- Request schemas
- Response JSON field names
- Status codes
- Required error codes
- Existing API behavior outside the required fixes

The project focuses on correctness, concurrency safety, multi-tenancy isolation, authentication behavior, and contract-compatible responses.

## Tech Stack

- Python 3.11
- FastAPI
- SQLAlchemy
- SQLite
- JWT authentication with HS256
- Pytest
- Docker support

## Key Features

- Multi-tenant organization support
- Admin and member roles
- Room management by organization admins
- Booking creation with validation, pricing, quota checks, and conflict prevention
- Booking cancellation with refund calculation
- JWT access and refresh authentication
- Single-use refresh tokens
- Logout token invalidation
- Usage report for organization admins
- Room availability lookup
- Room booking statistics
- CSV export for bookings
- Pagination for booking lists
- Contract-compatible application error responses

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | No | Service health check |
| `POST` | `/auth/register` | No | Register a user and organization membership |
| `POST` | `/auth/login` | No | Login and receive access/refresh tokens |
| `POST` | `/auth/refresh` | No | Rotate refresh token and receive new tokens |
| `POST` | `/auth/logout` | Yes | Invalidate the presented access token |
| `GET` | `/rooms` | Yes | List rooms in the caller's organization |
| `POST` | `/rooms` | Admin | Create a room |
| `GET` | `/rooms/{id}/availability` | Yes | Get busy intervals for a room on a UTC date |
| `GET` | `/rooms/{id}/stats` | Yes | Get current confirmed-booking count and revenue for a room |
| `POST` | `/bookings` | Yes | Create a booking |
| `GET` | `/bookings` | Yes | List visible bookings with pagination |
| `GET` | `/bookings/{id}` | Yes | Get a single visible booking including refunds |
| `POST` | `/bookings/{id}/cancel` | Yes | Cancel a booking and calculate refund |
| `GET` | `/admin/usage-report` | Admin | Get per-room usage and revenue for a date/time range |
| `GET` | `/admin/export` | Admin | Export bookings as CSV |

## Business Rules Summary

### Datetime Handling

- All API datetimes are ISO 8601.
- Inputs with a UTC offset are converted to UTC before storage/comparison.
- Naive datetimes are treated as UTC.
- Response datetimes are returned in UTC with an explicit `Z` designator.

### Booking Duration and Pricing

- End time must be strictly after start time.
- Start time must be strictly in the future at request time.
- Duration must be a whole number of hours.
- Minimum duration is 1 hour.
- Maximum duration is 8 hours.
- Price is calculated as:

```text
price_cents = hourly_rate_cents × duration_hours
```

Invalid booking windows return `400 INVALID_BOOKING_WINDOW`.

### Double-Booking Prevention

Two confirmed bookings overlap when:

```text
existing.start < new.end AND new.start < existing.end
```

Back-to-back bookings are allowed. Conflicts return `409 ROOM_CONFLICT`.

### Booking Quota

A member may hold at most 3 confirmed bookings with start time in:

```text
(now, now + 24h]
```

The quota is counted across all rooms in the user's organization. Violations return `409 QUOTA_EXCEEDED`.

### Rate Limiting

`POST /bookings` is limited to 20 requests per rolling 60 seconds per user. All attempts count, including failed requests. Excess requests return `429 RATE_LIMITED`.

### Refund Policy

Refund amount is based on cancellation notice:

| Notice Before Start | Refund |
|---|---:|
| `>= 48 hours` | 100% |
| `>= 24 hours` and `< 48 hours` | 50% |
| `< 24 hours` | 0% |

Cancelling an already cancelled booking returns `409 ALREADY_CANCELLED`. Each cancelled booking has exactly one refund log.

### Multi-Tenancy Isolation

- Users can only access data from their own organization.
- Cross-organization room IDs behave as not found: `404 ROOM_NOT_FOUND`.
- Cross-organization booking IDs behave as not found: `404 BOOKING_NOT_FOUND`.
- Members can only read and cancel their own bookings.
- Admins can read and cancel bookings in their own organization.

### Pagination and Ordering

`GET /bookings` supports:

- `page`, default `1`
- `limit`, default `10`, maximum `100`

Bookings are sorted by ascending start time, then ascending ID. The response includes `total`.

## Error Response Format

Application errors follow this shape:

```json
{
  "detail": "Error message",
  "code": "ERROR_CODE"
}
```

Required application error codes include:

| Code | Status |
|---|---:|
| `USERNAME_TAKEN` | 409 |
| `INVALID_CREDENTIALS` | 401 |
| `ROOM_CONFLICT` | 409 |
| `QUOTA_EXCEEDED` | 409 |
| `RATE_LIMITED` | 429 |
| `ALREADY_CANCELLED` | 409 |
| `BOOKING_NOT_FOUND` | 404 |
| `ROOM_NOT_FOUND` | 404 |
| `FORBIDDEN` | 403 |
| `INVALID_BOOKING_WINDOW` | 400 |

Missing, invalid, expired, or blacklisted tokens return `401`.

## Installation

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd ICT_Fest_Hackathon_Preliminary
```

### 2. Create a Virtual Environment

Use Python 3.11.

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Run the Application

```bash
python -m uvicorn app.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

Health check:

```text
http://127.0.0.1:8000/health
```

Expected health response:

```json
{
  "status": "ok"
}
```

## Docker

If Docker is available, run:

```bash
docker compose up --build
```

The service will be exposed on:

```text
http://127.0.0.1:8000
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./cowork.db` | SQLAlchemy database URL |
| `JWT_SECRET` | `change-me-for-local-dev-secret-32-bytes-minimum` | Secret used to sign JWT tokens |
| `SQLITE_TIMEOUT_SECONDS` | `30` | SQLite busy timeout for concurrent access |

For production-like environments, set a strong `JWT_SECRET`.

Example:

```bash
export JWT_SECRET="replace-with-a-strong-secret"
```

Windows PowerShell:

```powershell
$env:JWT_SECRET="replace-with-a-strong-secret"
```

## Example API Usage

### Register

The first user in a new organization becomes an admin.

```bash
curl -X POST "http://127.0.0.1:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"org_name":"acme","username":"alice","password":"pass123"}'
```

Example response:

```json
{
  "id": 1,
  "org_id": 1,
  "username": "alice",
  "role": "admin"
}
```

### Login

```bash
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"org_name":"acme","username":"alice","password":"pass123"}'
```

Example response:

```json
{
  "access_token": "<access-token>",
  "refresh_token": "<refresh-token>",
  "token_type": "bearer"
}
```

### Use Bearer Token

Protected endpoints require:

```text
Authorization: Bearer <access-token>
```

### Create Room

```bash
curl -X POST "http://127.0.0.1:8000/rooms" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access-token>" \
  -d '{"name":"Meeting Room A","capacity":8,"hourly_rate_cents":1000}'
```

Example response:

```json
{
  "id": 1,
  "org_id": 1,
  "name": "Meeting Room A",
  "capacity": 8,
  "hourly_rate_cents": 1000
}
```

### Create Booking

Use a future UTC datetime.

```bash
curl -X POST "http://127.0.0.1:8000/bookings" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access-token>" \
  -d '{"room_id":1,"start_time":"2099-01-01T10:00:00Z","end_time":"2099-01-01T12:00:00Z"}'
```

Example response:

```json
{
  "id": 1,
  "reference_code": "BK-7F8A2C9D",
  "room_id": 1,
  "user_id": 1,
  "start_time": "2099-01-01T10:00:00Z",
  "end_time": "2099-01-01T12:00:00Z",
  "status": "confirmed",
  "price_cents": 2000,
  "created_at": "2099-01-01T09:00:00Z"
}
```

## Testing

Run the test suite:

```bash
python -m pytest -q
```

The included tests cover major parts of the official API contract, including authentication, registration behavior, booking validation, room conflicts, quota, rate limiting, visibility, refunds, reports, availability, stats, and pagination.

## Bug Fixing Summary

This submission fixes contract-breaking bugs according to the hackathon business rules while keeping the API stable. The fixes focus on:

- Correct UTC datetime parsing, storage, comparison, and serialization
- Booking window validation and price calculation
- Conflict detection and back-to-back booking behavior
- Booking quota enforcement
- Rolling rate limiting
- Refund calculation and duplicate cancellation prevention
- JWT claim correctness, expiry durations, logout invalidation, and refresh rotation
- Multi-tenant access isolation
- Member/admin booking visibility
- Live usage reports, availability, and room stats without stale cache behavior
- Pagination ordering and total count correctness
- SQLite-safe handling for concurrency-sensitive paths

No hidden grader score is claimed. The project is prepared to match the documented API contract.

## Project Structure

```text
app/
├── main.py                 # FastAPI application entrypoint
├── config.py               # Environment and configuration values
├── database.py             # SQLAlchemy engine/session setup
├── models.py               # Database models
├── schemas.py              # Request schemas
├── serializers.py          # Response serialization helpers
├── auth.py                 # JWT, password hashing, auth dependencies
├── errors.py               # Application error handling
├── timeutils.py            # UTC datetime parsing/formatting helpers
├── cache.py                # Cache module kept for compatibility
├── locks.py                # Process-level critical-section locks
├── routers/
│   ├── auth.py             # Auth endpoints
│   ├── rooms.py            # Room endpoints
│   ├── bookings.py         # Booking endpoints
│   ├── admin.py            # Admin report/export endpoints
│   └── health.py           # Health endpoint
└── services/
    ├── ratelimit.py        # Booking rate limiter
    ├── refunds.py          # Refund calculation
    ├── reference.py        # Booking reference generation
    ├── stats.py            # Statistics helpers
    ├── export.py           # CSV export helper
    └── notifications.py    # Notification stub

tests/
└── test_contract.py        # Contract-focused pytest tests

requirements.txt
Dockerfile
docker-compose.yml
bug_report.md
README.md
```

## Submission Notes

- API contract was preserved.
- Endpoint paths were not changed.
- Response field names were not changed.
- Required application error format was preserved.
- `bug_report.md` is included for manual review and tie-breaking support.
- Local database files, virtual environments, cache folders, and temporary files should not be included in the final submission zip.

## License

For hackathon submission purposes only.

---

## Hackathon Project Metadata

**Team Name:** Ek_Bar_Dhokha_Kha_Chuka_Hun_Dobara_Nahi_Khaunga  
**Team Lead:** Munshi Nahiyan Amin  
**Institution:** University of Liberal Arts Bangladesh (ULAB)  
**Registration Code:** 02-50670

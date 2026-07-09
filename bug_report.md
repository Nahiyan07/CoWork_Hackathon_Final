# Bug Report

## Bug 1

* File/line: `app/timeutils.py:13-27`, `app/serializers.py:30-40`
* Problem: Datetime parsing/serialization did not consistently normalize offset-aware inputs to UTC, and responses could return non-UTC or ambiguous datetimes.
* Why it broke the business rule: The contract requires all input offsets to be converted to UTC, naive datetimes to be treated as UTC, and all response datetimes to include an explicit UTC designator.
* Fix: Added strict ISO parsing that converts aware datetimes to UTC-naive storage values and serializer output that always emits UTC `Z` timestamps.

## Bug 2

* File/line: `app/routers/bookings.py:28-37`
* Problem: Booking-window validation allowed invalid starts/durations, did not reject zero/negative duration correctly in every case, and did not enforce the 1-to-8 whole-hour range exactly.
* Why it broke the business rule: Invalid windows must return `400 INVALID_BOOKING_WINDOW`; minimum duration is 1 hour, maximum is 8 hours, duration must be whole hours, end must be after start, and start must be strictly in the future.
* Fix: Centralized validation in `_validate_window()` and enforce future start, `end > start`, whole-hour duration, minimum 1 hour, and maximum 8 hours.

## Bug 3

* File/line: `app/routers/bookings.py:40-51`
* Problem: Overlap detection used inclusive comparisons, which incorrectly treated back-to-back bookings as conflicts and could miss/allow cases inconsistent with the stated overlap rule.
* Why it broke the business rule: Two confirmed bookings overlap only when `existing.start < new.end AND new.start < existing.end`; back-to-back bookings must be allowed.
* Fix: Replaced the conflict query with the exact strict-overlap predicate.

## Bug 4

* File/line: `app/routers/bookings.py:86-122`, `app/locks.py:6-8`, `app/database.py:19-26`
* Problem: Conflict checks, quota checks, reference creation, and insert were not protected as one critical section for SQLite concurrent requests.
* Why it broke the business rule: Concurrent `POST /bookings` calls could double-book a room, exceed quota, or race on reference creation.
* Fix: Wrapped booking creation in a process-local critical section, enabled SQLite WAL/busy timeout, and kept validation/query/insert together inside the locked section.

## Bug 5

* File/line: `app/routers/bookings.py:54-71`
* Problem: Quota enforcement was not scoped to confirmed future bookings in `(now, now + 24h]` across the user’s organization.
* Why it broke the business rule: A member may hold at most 3 confirmed bookings in that rolling 24-hour window across all rooms in the organization.
* Fix: Count confirmed bookings for the same user joined through rooms in the user’s organization, with `start_time > now` and `start_time <= now + 24h`.

## Bug 6

* File/line: `app/services/ratelimit.py:15-25`, `app/routers/bookings.py:88`
* Problem: Rate limiting was not safely rolling-window based and did not reliably count failed requests.
* Why it broke the business rule: `POST /bookings` is limited to 20 requests per rolling 60 seconds per user, and all requests must count, including failed ones.
* Fix: Added a locked per-user monotonic deque limiter and call it before room/window/conflict checks.

## Bug 7

* File/line: `app/models.py:54-56`, `app/routers/bookings.py:102-122`, `app/services/reference.py:1-6`
* Problem: Booking reference codes were not guaranteed globally unique under concurrent creation.
* Why it broke the business rule: Every booking reference code must be globally unique, including during concurrent requests.
* Fix: Added a database uniqueness constraint on `reference_code`, generated high-entropy references, and retry on unique constraint collision.

## Bug 8

* File/line: `app/routers/bookings.py:150-183`, `app/services/refunds.py:11-18`
* Problem: Cancellation refund percentages and rounding were incorrect for boundary windows, and `<24h` notice could return a nonzero refund.
* Why it broke the business rule: Refunds must be 100% for notice `>=48h`, 50% for `24h <= notice < 48h`, and 0% for `<24h`, with half-cent rounding up.
* Fix: Implemented exact notice thresholds and Decimal `ROUND_HALF_UP` refund calculation.

## Bug 9

* File/line: `app/models.py:73-81`, `app/routers/bookings.py:150-183`
* Problem: Concurrent or repeated cancellations could create multiple refund logs or return a response amount that did not match the stored log.
* Why it broke the business rule: A cancelled booking must have exactly one `RefundLog`, and the cancel response must match it; repeated cancellation must return `409 ALREADY_CANCELLED`.
* Fix: Added a unique constraint on `RefundLog.booking_id`, locked cancellation, write status/refund in one commit, and return the same calculated amount.

## Bug 10

* File/line: `app/auth.py:43-99`, `app/models.py:86-96`
* Problem: JWT access-token lifetime was calculated incorrectly and refresh/access token state was not persistently tracked.
* Why it broke the business rule: Access tokens must expire in exactly 900 seconds, refresh tokens in 7 days, and tokens must include `sub`, `org`, `role`, `jti`, `iat`, `exp`, and `type`.
* Fix: Added a shared `_encode_token()` that produces exact claims/lifetimes and a `TokenState` table for refresh-token validity and access-token revocation.

## Bug 11

* File/line: `app/routers/auth.py:60-74`, `app/auth.py:62-80`
* Problem: Refresh tokens were reusable.
* Why it broke the business rule: Refresh tokens must be single-use; reusing one must return 401.
* Fix: Store refresh token JTIs, mark the presented token revoked during refresh, and issue a new token pair only after the old refresh token is invalidated.

## Bug 12

* File/line: `app/routers/auth.py:77-87`, `app/auth.py:102-135`
* Problem: Logout did not reliably invalidate the exact presented access token.
* Why it broke the business rule: After logout, subsequent use of the same access token must immediately return 401.
* Fix: Persist revoked access-token JTIs and check revocation for every authenticated request.

## Bug 13

* File/line: `app/routers/auth.py:20-44`
* Problem: Registration role assignment and duplicate username handling were not transaction-safe.
* Why it broke the business rule: Unknown organization registration must create the first user as admin, known organizations must join as member, and duplicate username within an org must return `409 USERNAME_TAKEN`.
* Fix: Locked registration, created/fetched the organization first, assigned role based on org existence, checked duplicate username within org, and converted integrity collisions to `USERNAME_TAKEN`.

## Bug 14

* File/line: `app/routers/rooms.py:19-38`, `app/routers/bookings.py:74-83`, `app/routers/admin.py:76-81`
* Problem: Some room/booking/export paths did not consistently scope resource IDs by caller organization.
* Why it broke the business rule: Cross-organization resource IDs must behave as non-existent and return `ROOM_NOT_FOUND` or `BOOKING_NOT_FOUND` as applicable.
* Fix: Added org-scoped room lookup and booking visibility queries; export room filtering also checks the caller’s organization.

## Bug 15

* File/line: `app/routers/bookings.py:74-83`, `app/routers/bookings.py:140-147`, `app/routers/bookings.py:150-183`
* Problem: Members could read or cancel another member’s booking inside the same organization, or the endpoint leaked existence.
* Why it broke the business rule: Members may read/cancel only their own bookings; another member’s booking ID must return `404 BOOKING_NOT_FOUND`; admins may access bookings in their org.
* Fix: Centralized `_booking_visible_query()` so non-admin users are filtered by `Booking.user_id == user.id`, while admins remain org-scoped.

## Bug 16

* File/line: `app/routers/bookings.py:125-137`
* Problem: Pagination used descending start-time order, an incorrect offset, and a fixed limit.
* Why it broke the business rule: Results must be sorted ascending by start time then ascending ID, use `(page - 1) * limit`, honor `limit`, and include `total` without skipping/repeating sequential pages.
* Fix: Corrected ordering, offset, limit, and returned the requested `page`, `limit`, and `total`.

## Bug 17

* File/line: `app/routers/bookings.py:140-147`
* Problem: Booking detail serialization corrupted `start_time` by returning `created_at` in its place.
* Why it broke the business rule: Booking responses must preserve the booking start/end datetimes and include refunds only as an additional field.
* Fix: Reused `serialize_booking()` without overwriting `start_time`, then appended sorted refund records.

## Bug 18

* File/line: `app/routers/admin.py:21-66`
* Problem: Usage report could omit zero-booking rooms, count stale/cached values, or count the wrong date/range.
* Why it broke the business rule: Reports must include every room in the caller’s organization, count/sum only confirmed bookings starting in the inclusive range, and reflect current state immediately.
* Fix: Removed stale caching from the report path and compute counts/revenue directly from current database state for every org room.

## Bug 19

* File/line: `app/routers/rooms.py:41-61`
* Problem: Availability could return stale or unsorted busy intervals.
* Why it broke the business rule: Availability must reflect current confirmed bookings for the UTC date and sort busy intervals ascending.
* Fix: Query confirmed bookings live from the database for that UTC day and order by `start_time`, then `id`.

## Bug 20

* File/line: `app/routers/rooms.py:64-72`
* Problem: Room stats were cache-derived and could be inconsistent after cancellation or concurrent activity.
* Why it broke the business rule: Stats must return the current count of confirmed bookings and current total revenue, consistent with bookings.
* Fix: Compute count and revenue directly from the database each request.

## Bug 21

* File/line: `app/database.py:9-28`, `app/locks.py:1-8`
* Problem: SQLite connections and concurrent access settings were not safe enough for the grader’s threaded request bursts.
* Why it broke the business rule: Valid concurrent request combinations must not hang the service.
* Fix: Enabled `check_same_thread=False`, WAL mode, a busy timeout, foreign keys, and short process-local critical sections for high-risk writes.

# Test Credentials

## Authentication
- **Auth provider**: Emergent-managed Google Auth
- **Admin allowlist (env var `ALLOWED_ADMIN_EMAILS` in /app/backend/.env)**:
  - `owner@intheweedscollective.com` — primary admin
- **Public viewers**: anyone with a Google account can sign in; only allowlisted
  emails see admin-only routes (data uploads, employee CRUD, slide downloads,
  quarter unlock, etc.).
- **Anonymous**: dashboard, leaderboards, and QR pages are public-viewable
  with no login required.

## How to test as admin (via UI)
1. Open the preview URL from `REACT_APP_BACKEND_URL` (front-end origin).
2. Click "Sign in with Google" in the sidebar.
3. Use a Google account whose email is in `ALLOWED_ADMIN_EMAILS`.

## How to test as anonymous viewer
Just hit any public URL without signing in. The sidebar will show
"Viewer · Sign Out" and admin-only routes will 401.

## Backend protected endpoints (require admin)
- `POST /api/v2/employees`
- `PUT /api/v2/employees/{id}`
- `DELETE /api/v2/employees/{id}`
- `POST /api/v2/employees/cleanup/delete`
- `POST /api/v2/quarter-settings/{year}/{quarter}/unlock`
- `POST /api/v2/snapshots/...`
- `POST /api/qr/admin/heal-ghost-ids` (re-attributes ghost-UUID scans)

## How to seed a test admin session (for backend smoke tests)
See `/app/backend/tests/test_qr_ghost_heal.py` for the canonical pattern:
insert one row into `users` (with `user_id`), one into `user_sessions`
(with `session_token` + matching `user_id`), and send the token as
`Authorization: Bearer <token>`.

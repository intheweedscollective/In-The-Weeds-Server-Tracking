# Auth Testing Playbook (Emergent-managed Google Auth)

This file is read by the testing agent before running auth flows.

## Allowed identity (production whitelist)
- `owner@intheweedscollective.com`

## What's protected
- All POST/PUT/DELETE under `/api/v2/*` (snapshot create/finalize, employee edits, POS/CV/RT uploads, audit recalc/sync, quarter-settings save, DAR, merge).
- GET endpoints remain PUBLIC (anonymous users can view rankings/snapshots/leaderboards).

## Test User & Session (mongosh)
```
mongosh --eval "
use('staff_score_db');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'owner@intheweedscollective.com',
  name: 'Owner Test',
  picture: 'https://via.placeholder.com/150',
  is_admin: true,
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
"
```

## Curl tests
```
# Public — should succeed without auth
curl -s "https://staff-score-engine.preview.emergentagent.com/api/v2/full-rankings/2026/Q2"

# Protected — should 401 without auth
curl -s -X POST "https://staff-score-engine.preview.emergentagent.com/api/v2/audit/recalculate-all?quarter=Q2&year=2026"

# Protected — should succeed with cookie
curl -s -X POST "https://staff-score-engine.preview.emergentagent.com/api/v2/audit/recalculate-all?quarter=Q2&year=2026" \
  -H "Cookie: session_token=YOUR_SESSION_TOKEN"

# Auth identity — should return user
curl -s "https://staff-score-engine.preview.emergentagent.com/api/auth/me" \
  -H "Cookie: session_token=YOUR_SESSION_TOKEN"
```

## Browser smoke test
1. Visit `/login` while signed out → splash page with both logos + "Sign in with Google" button.
2. Click button → routed to `https://auth.emergentagent.com/?redirect=...`.
3. After Google auth → land on `/dashboard#session_id=...` → cookie established → app shell shows "Sign out" button.
4. Try clicking "Save" on a quarter-setting change while signed out → toast: "Sign in to save changes" → redirect to `/login`.

## Cleanup
```
mongosh --eval "use('staff_score_db'); db.users.deleteMany({email: /test/}); db.user_sessions.deleteMany({session_token: /test_session/});"
```

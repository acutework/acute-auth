# acute-auth

Mobile-OTP authentication and authorisation for Acute.

A user signs in with a mobile number. The service sends an OTP, verifies it,
and then either returns JWTs (the number has an account) or a short-lived
registration token (it does not), so the client knows to show a signup screen.

## Run it

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload            # in-memory, no infra needed
```

With Postgres and Redis:

```bash
docker compose up -d          # Postgres on 5433, Redis on 6380
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The ports are offset from the defaults so they cannot collide with another
Postgres or Redis already running on your machine.

Interactive docs: http://localhost:8000/docs

## Try the flow

The default OTP provider is fake: it sends nothing, always accepts `4732`,
and returns the code as `debug_code` so you can complete the flow without a
phone. `919999999999` is seeded as an existing user **when running in memory**; with
Postgres the table starts empty, so every number is new until it registers.

Mobile numbers are `<countrycode><number>`, digits only - the same form
acute-api uses. A leading `+` is accepted on input and stripped.

```bash
# 1. Ask for an OTP
curl -s localhost:8000/auth/otp/request \
  -H 'content-type: application/json' \
  -d '{"mobile": "919999999999"}'
# -> {"request_id": "...", "expires_in": 300, "debug_code": "4732"}

# 2. Verify it
curl -s localhost:8000/auth/otp/verify \
  -H 'content-type: application/json' \
  -d '{"request_id": "<from step 1>", "mobile": "919999999999", "code": "4732"}'
# existing user -> {"is_new_user": false, "access_token": "...", "refresh_token": "...", "user": {...}}
# new user      -> {"is_new_user": true, "registration_token": "..."}

# 3. New user only: create the account
curl -s localhost:8000/auth/register \
  -H 'content-type: application/json' \
  -H 'Authorization: Bearer <registration_token>' \
  -d '{"name": "Asha"}'
```

## Endpoints

| Method | Path                 | Auth                       | Purpose                          |
|--------|----------------------|----------------------------|----------------------------------|
| POST   | `/auth/otp/request`  | none                       | Send an OTP to a mobile number   |
| POST   | `/auth/otp/verify`   | none                       | Check the OTP, issue tokens      |
| POST   | `/auth/otp/resend`   | none                       | Re-deliver the OTP (SMS or voice)|
| POST   | `/auth/register`     | Bearer registration token  | Create the account, issue tokens |
| POST   | `/auth/refresh`      | refresh token in body      | Get a fresh token pair           |
| POST   | `/auth/logout`       | refresh token in body      | Revoke the refresh token         |
| GET    | `/auth/me`           | Bearer access token        | The signed-in user               |
| GET    | `/health`            | none                       | Liveness                         |

### Onboarding

Everything below is scoped to the signed-in user, taken from the access token.
No endpoint accepts a user id, so one worker can never read another's data.

| Method | Path                            | Purpose                                  |
|--------|---------------------------------|------------------------------------------|
| GET    | `/onboarding`                   | What is saved, and where to resume       |
| PUT    | `/onboarding/profile`           | Role and profile (app screens 1-2)       |
| PUT    | `/onboarding/workplace`         | Join or go individual (screen 3)         |
| POST   | `/onboarding/permissions-seen`  | Records screen 4 was shown                |
| POST   | `/onboarding/complete`          | Finishes onboarding (screen 5)           |
| GET    | `/places`                       | Saved places                             |
| POST   | `/places`                       | Add a place                              |
| PUT    | `/places/{id}`                  | Edit a place                             |
| DELETE | `/places/{id}`                  | Remove a place                           |
| GET    | `/places/search?q=`             | Address autocomplete (proxied)           |
| GET    | `/places/details/{id}`          | Address plus coordinates                 |
| GET    | `/catalog`                      | Every picker option list                 |
| GET    | `/catalog/{kind}`               | One option list                          |

**Profile completion** is returned with every `GET /onboarding` as
`completion.percent` plus the items behind it, and drives the ring on the app's
profile avatar. It counts only optional detail the person can finish on their
own - an email address, a second saved place, and an employee ID for those who
joined an organisation - so it can always reach 100%. Required fields are not
counted: onboarding already enforces them.

Pass `?advance=false` to `PUT /onboarding/profile` when editing an
already-onboarded profile, so saving a detail does not re-drive the flow.

**Self-declared, always.** Degrees, specialties and licence numbers are stored
exactly as entered. Nothing is verified, no certificate or identity document is
ever requested, and `ProfileOut.is_verified` is hard-coded `false` so no client
has to guess.

**Joining is a request, not a grant.** `PUT /onboarding/workplace` in join mode
always writes `status: pending`. Only the organisation can approve it.

**Per-role rules** are in `app/onboarding/service.py` and answer 422 listing
what is missing:

| Role | Required beyond a display name |
|---|---|
| Doctor | ≥1 degree, ≥1 specialty, medical council registration number |
| Nurse | ≥1 qualification, ≥1 specialty, nursing council registration number |
| Paramedic | Certification level |
| Other staff | A role description |
| Front desk, Security | Nothing |

An individual (not joining an organisation) must save at least one place first -
with no organisation to alert, a saved place is the only thing an SOS can point
responders at.

## Address lookup

Google Places is proxied rather than called from the app, so the API key stays
in this service's environment and never ships inside an app binary.

```bash
PLACES_PROVIDER=google
GOOGLE_PLACES_API_KEY=...
```

Blank `PLACES_PROVIDER` disables search; `/places/search` then answers 501 and
the app falls back to a typed address, which always works.

**Swapping provider** is the same two steps as the OTP provider: implement
`PlaceSearchProvider` in `app/places/base.py`, add a line to
`app/places/registry.py`. Every saved place stores its own `latitude`,
`longitude`, `provider` and `provider_place_id`, so a move to a free provider
(Nominatim, Photon, self-hosted Pelias) leaves existing data intact and an SOS
can still match the nearest saved place with no lookup at all.

Pass a `session_token` through a typing run and its details call, and the
provider bills the whole run as one session rather than per keystroke.

## Storage

Both stores are optional. Leave the URL blank and the service falls back to an
in-memory equivalent, which is what makes `uv run uvicorn app.main:app` work
with no infrastructure at all.

| Setting | Unset | Set |
|---|---|---|
| `DATABASE_URL` | users in a dict, lost on restart | Postgres via SQLAlchemy |
| `REDIS_URL` | per-process counters, single instance only | Redis, shared across instances |

The service logs a warning at startup for each one that is missing.

### What Redis holds

| Key | Purpose |
|---|---|
| `otp:challenge:<request_id>` | live challenges for self-hosted providers, expired by Redis. MSG91 needs none of this - it holds the OTP itself. |
| `ratelimit:otp:send:<mobile>` | OTP sends per number per window |
| `ratelimit:otp:verify:<mobile>` | verify attempts per number per window |
| `token:revoked:<jti>` | revoked refresh tokens, expiring when the token would have |

Attempt counting uses `HINCRBY` and rate limiting uses `INCR` + `EXPIRE NX`, so
concurrent requests cannot both read a stale count, and a steady stream of
requests cannot keep pushing a window's expiry out.

### Migrations

```bash
uv run alembic upgrade head                            # apply
uv run alembic revision --autogenerate -m "what changed"   # after editing a model
uv run alembic downgrade -1                            # step back
```

Alembic reads `DATABASE_URL` from the same settings the app does, so there is
one source of truth for where the database lives.

## Tokens

HS256 JWTs. Every token carries a `type` claim that is checked on use, so a
registration or refresh token can never stand in for an access token, and a
`jti` so a refresh token can be revoked by id.

| Type           | Lifetime | Used for                        |
|----------------|----------|---------------------------------|
| `access`       | 15 min   | Calling protected endpoints     |
| `refresh`      | 30 days  | Getting a new access token      |
| `register`     | 10 min   | Completing signup after the OTP |

Refresh tokens **rotate**: using one revokes it and issues a new pair, so a
stolen copy stops working as soon as the real client refreshes. `/auth/logout`
revokes one outright. An access token is never revoked by `jti` - it simply
expires within minutes, which is the trade-off stateless access tokens buy.

### Staying signed in

Every OTP costs an SMS, so a session is built to survive. The refresh token
lasts a year **and slides** - each refresh issues a fresh one - so anyone who
opens the app at all stays signed in indefinitely. The only things that end a
session are the user's own logout and a deliberate forced sign-out.

### Forcing a sign-out

Every token carries a `ver` claim matching the user's `token_version`, checked
on every authenticated request. Bumping the column invalidates everything that
user holds, immediately:

```sql
-- One account: a lost phone, or a support request.
UPDATE users SET token_version = token_version + 1 WHERE mobile = '919999999999';

-- Everyone: a release that must re-authenticate the whole user base.
UPDATE users SET token_version = token_version + 1;
```

Affected clients get `401 session_superseded` and are sent back to sign-in.

## Layout

```
app/
  main.py          FastAPI app, domain-error -> HTTP mapping
  config.py        Settings from the environment
  deps.py          Wiring: which store, which OTP provider
  api/             Routes and request/response schemas
  core/            JWT service, domain errors, mobile normalisation
  otp/             provider contract, signed handles, fake + MSG91, registry
  users/           User model, repository contract, in-memory store
  services/        AuthService - the flow itself, no HTTP
```

`AuthService` depends only on the `OtpProvider` and `UserRepository` contracts,
so storage and OTP vendors swap without touching it.

## Using MSG91

```bash
OTP_PROVIDER=msg91
MSG91_AUTHKEY=...
MSG91_OTP_TEMPLATE_ID=...
```

Nothing else changes - the endpoints, tokens and responses are identical.
Missing credentials fail at startup, not on the first user's login.

`debug_code` is absent under MSG91, so the real OTP is never exposed.

### How it maps onto the contract

MSG91 keys an OTP by mobile number alone and hands back no identifier, while
this API gives the client a `request_id`. The provider therefore issues a
**signed stateless handle**: a short HMAC-signed token carrying the mobile
number and issue time (`app/otp/challenge.py`). On verify it checks the
signature, the mobile match and the age *before* spending a call on MSG91, so
forged, mismatched or stale handles never leave the process. Because it is
signed rather than stored, it survives restarts and works across instances.

MSG91 owns code generation, expiry and attempt counting, so the provider keeps
no OTP state of its own and passes MSG91's own `message` through on rejection.

| MSG91 outcome              | This API           |
|----------------------------|--------------------|
| `type: success`            | 200                |
| `type: error` on send/retry| 502 `otp_send_failed` |
| `type: error` on verify    | 400 `invalid_otp`  |
| transport error or non-2xx | 502 `otp_provider_unavailable` |

## Plugging in another OTP provider

1. Implement the contract in `app/otp/base.py` (see `app/otp/msg91.py` for a
   worked example):

   ```python
   class TwilioOtpProvider(OtpProvider):
       async def send(self, mobile: str) -> OtpChallenge: ...
       async def verify(self, request_id: str, mobile: str, code: str) -> None: ...
   ```

   `verify` returns `None` on success and raises `InvalidOtp`, `OtpExpired`,
   `TooManyAttempts`, `UnknownOtpRequest` or `OtpProviderUnavailable`
   otherwise. Never populate `debug_code`.

   Add `OtpResender` too if the vendor can retry a live OTP. Providers that
   don't implement it make `/auth/otp/resend` answer 501 - no stub needed.

2. Register it in `app/otp/registry.py`:

   ```python
   _PROVIDERS["twilio"] = lambda settings, codec: TwilioOtpProvider(...)
   ```

3. Set `OTP_PROVIDER=twilio`. Nothing else changes.

## Configuration

See `.env.example`. Every value has a development default, so the service runs
with no configuration at all — but `JWT_SECRET` must be set in any real
deployment, and the service logs a warning while it is not.

## Tests

```bash
uv run pytest                    # 130 tests, no infrastructure, ~0.4s
uv run pytest -m integration     # 28 more, against real Postgres and Redis
```

Integration tests skip themselves when the services are not reachable, so the
default run never needs Docker. They truncate the `users` table before and
after each test, and use Redis db 15 rather than the app's own.

## Layout additions

```
app/
  catalog/         picker option lists (seeded by a migration)
  onboarding/      domain, repositories and the per-role rules
  places/          address provider contract, Google, registry
  db/              engine, session factory, Redis client, declarative Base
  models/          SQLAlchemy tables (Alembic autogenerates from these)
  ratelimit/       RateLimiter: in-memory and Redis
  tokens/          TokenDenylist: in-memory and Redis
  otp/store.py     OtpChallengeStore: in-memory and Redis
alembic/           migrations
docker-compose.yml Postgres + Redis for local work
```

## Known limits

- **Rate limiting is per number, not per caller.** Someone cycling through many
  numbers is not slowed down. Add a per-IP rule in `AuthService.request_otp`
  when this faces the public internet.
- **The window is fixed, not sliding.** A caller can spend a full budget at the
  end of one window and again at the start of the next.
- **No admin path to revoke every session for a user.** Revocation is per
  refresh token. Doing it per user needs a token-version column on `users` that
  the JWT carries and `_decode_live` checks.
- **`get_settings` is cached and `deps` builds its service at import time.** A
  running process cannot be repointed at another database without a restart.

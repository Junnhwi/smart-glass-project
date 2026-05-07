# Google OAuth Local Setup

## Goal

Enable real Google sign-in for the current local stack.

This project already has the Google OAuth flow implemented in code. To make it
actually usable, you need to finish the environment and Google Console setup.

## What Already Exists

- backend start endpoint: `POST /auth/oauth/google/start`
- backend callback endpoint: `GET /auth/oauth/google/callback`
- backend handoff exchange endpoint: `POST /auth/oauth/google/exchange`
- Expo app scheme: `smart-glass-client://oauth`
- web login flow from the existing `LoginScreen`

## Recommended First Test Path

Test on `web` first.

Why:

- the local backend callback already uses `http://localhost:8002/...`
- the web client returns to the same browser tab after Google login
- native custom-scheme login is easier to test after the web path works

## Required `.env` Values

Set these in the repository root `.env`:

```env
API_CAPTURE_DATABASE_URL=postgresql://...
API_AUTH_JWT_SECRET=replace-with-a-long-random-secret
API_AUTH_GOOGLE_CLIENT_ID=...
API_AUTH_GOOGLE_CLIENT_SECRET=...
API_AUTH_GOOGLE_CALLBACK_URL=http://localhost:8002/auth/oauth/google/callback
API_AUTH_OAUTH_REDIRECT_ALLOWLIST=smart-glass-client://oauth,http://localhost:8081/,http://127.0.0.1:8081/
```

Optional but useful:

```env
API_AUTH_ENABLE_DEMO_TOKENS=1
```

For the Expo client, set this in `apps/smart-glass-client/.env.local` or in the
shell before starting Expo:

```env
EXPO_PUBLIC_API_BASE_URL=http://localhost:8002
```

## Google Cloud Console Setup

Create or open a Google Cloud project, then:

1. Go to `APIs & Services > OAuth consent screen`
2. Configure the consent screen
3. Add your test account under `Test users` if the app is in testing mode
4. Go to `APIs & Services > Credentials`
5. Create an OAuth client
6. Choose `Web application`
7. Add this exact redirect URI:

```text
http://localhost:8002/auth/oauth/google/callback
```

Use the resulting values for:

- `API_AUTH_GOOGLE_CLIENT_ID`
- `API_AUTH_GOOGLE_CLIENT_SECRET`

## Local Run Order

From the repository root:

1. Copy and edit `.env`

```powershell
Copy-Item .env.example .env
```

2. Create the client env file

```powershell
Copy-Item apps/smart-glass-client/.env.example apps/smart-glass-client/.env.local
```

3. Start the backend stack

```powershell
docker compose -f infra/compose/docker-compose.local.yml up -d --build
```

4. Confirm backend readiness

```powershell
Invoke-RestMethod -Uri http://localhost:8002/health/ready | ConvertTo-Json -Depth 6
```

5. Start the Expo web app

```powershell
cd apps/smart-glass-client
npx expo start --web
```

6. Open the shown web URL
7. On the login screen, enter a `Device ID`
8. Click `Continue with Google`
9. Complete the Google sign-in flow

`API_AUTH_OAUTH_REDIRECT_ALLOWLIST` should include only trusted client return
targets. For local web testing, keep `http://localhost:8081/` in the list. For
native testing, keep `smart-glass-client://oauth`.

## Expected Successful Flow

After a successful login:

- Google redirects to the backend callback
- backend redirects back to the client with an OAuth handoff code
- client exchanges the handoff code for JWT + refresh token
- backend registers the provided `deviceId` to the authenticated user
- the app signs in with `authProvider = google`

## Native Testing Note

For native deep-link testing, prefer an Expo development build or a standalone
build.

The app scheme is already configured as:

```text
smart-glass-client://oauth
```

That means the backend can redirect to the app, but `Expo Go` is not the most
reliable way to validate a custom-scheme OAuth round trip.

## Quick Validation

You can run the local checker from the repository root:

```powershell
python scripts/check-google-oauth-setup.py
```

It will tell you:

- whether the required `.env` values exist
- which callback URI must be registered in Google Console
- whether the current config is ready for a web test

## Common Failures

### `API_AUTH_GOOGLE_CLIENT_ID is required`

Your `.env` is missing Google OAuth credentials.

### `OAuth state is invalid or already used`

The login tab was refreshed or the callback was reused. Start the flow again.

### Google shows `redirect_uri_mismatch`

The Google Console OAuth client does not include:

```text
http://localhost:8002/auth/oauth/google/callback
```

### Login button opens Google but never returns to the app

For web:

- make sure the browser returns to the same tab
- make sure backend callback URL is reachable on `localhost:8002`

For native:

- use a development build instead of relying on Expo Go

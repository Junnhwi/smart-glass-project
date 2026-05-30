# Admin Access

The production admin account is created or updated by the `admin-bootstrap`
service in `infra/compose/docker-compose.prod.yml`.

Set these values in the root `.env` file before deployment:

```env
ADMIN_BOOTSTRAP_EMAIL=team-admin@smartglass.local
ADMIN_BOOTSTRAP_PASSWORD=replace-with-a-private-password
ADMIN_BOOTSTRAP_USER_ID=team-admin
ADMIN_BOOTSTRAP_DISPLAY_NAME=Team Admin
```

Do not commit the real password. The bootstrap container updates the account
role to `admin`, activates it, rotates the password, and revokes existing
refresh sessions on repeated deployment.

Admin console:

- Production URL: `http://<NCP_SERVER_IP>:8080`
- Local Vite URL: `http://127.0.0.1:5173`
- API route from the production console: `/api`

The console can review users, device pairing requests, device activation state,
recent memory search/chat logs, and run image upload/inference polling with an
active registered device.

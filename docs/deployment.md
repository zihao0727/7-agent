# Agent7 deployment

## Architecture

- `web`: public Next.js UI used by browsers and the Electron client.
- `api`: public FastAPI service. Model keys and all database access stay here.
- `mongo`, `mysql`, `redis`: private server-side services with persistent volumes.
- Electron: loads `web`, connects only to `api`, and executes approved local capabilities.
- `lark-cli`: installed per OS user under Electron `userData`; CLI profiles are further
  separated by the authenticated Agent7 user id.

The API currently runs with one Uvicorn worker because desktop capability connections are
held in memory. Scale-out requires moving the client-runtime broker to Redis pub/sub before
increasing the worker or replica count.

## Server

1. Copy `.env.server.example` to `.env.server` and replace every placeholder.
   Generate `CREDENTIAL_ENCRYPTION_KEY` once and keep it in the server secret manager;
   losing or rotating it without migration makes stored Lark credentials unreadable.
2. Put the Web and API services behind an HTTPS reverse proxy. The proxy must also
   forward WebSocket `Upgrade`/`Connection` headers for `/api/client-runtime/ws`.
3. Set `PUBLIC_API_URL` to the public API URL and `CORS_ORIGINS` to a JSON array containing
   the public Web origin.
4. Start the stack with `docker compose --env-file .env.server -f docker-compose.server.yml up -d --build`.
5. Verify `GET https://api.example.com/api/health` before distributing the client.

MongoDB, MySQL, and Redis do not publish host ports in the Compose file. Back up the four
named volumes before upgrades.

## Desktop

The desktop client reads configuration from either environment variables or
`%APPDATA%/Agent7/config.json`:

```json
{
  "appUrl": "https://app.example.com",
  "apiUrl": "https://api.example.com",
  "autoUpdateLarkCli": true
}
```

Build the Windows installer from `desktop` with `npm ci` and `npm run dist`. Production
installers should be code-signed before distribution.

At sign-in, Electron opens an authenticated WebSocket to the API. Server-side Agent tools
send Lark CLI requests only to that user's connected client. The client runs a fixed
`@larksuite/cli` entrypoint; it does not expose a general shell to the Web renderer.

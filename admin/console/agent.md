# Admin Console Runtime

Start the console with python -m admin.console.backend.main. Uvicorn serves the FastAPI API and the built frontend. create_app() serves runtime and test creation.

## Console results

- The application owns PostgreSQL, Redis, definition, credential, and observability clients.
- API routes report dependency state through HTTP status codes.
- PostgreSQL stores credentials with Argon2 password hashes.
- Redis stores authenticated sessions.
- The auth module owns session cookies and session checks.
- Personality data comes from mounted AI definitions.
- Memory views read PostgreSQL documents and summaries.
- The SSO helper provides the Kubernetes Dashboard shortcut.

## Configuration and build

PanelConfig uses the PANEL_ prefix. The frontend source is in admin/console/frontend. Run npm ci and npm run build to create dist. The backend image serves the generated files.

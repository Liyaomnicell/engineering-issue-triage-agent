# Angular frontend

See the project README.md for PostgreSQL setup, data migration and Docker deployment.

Install and build:

    pnpm install --frozen-lockfile
    pnpm build

For development, run the Python API on port 8765, then run pnpm start here.
The Angular development server proxies /api using proxy.conf.json.
Production assets are emitted to dist/frontend/browser and served by app.py.

The production build keeps CSS external to comply with the API's CSP.
Backend and PostgreSQL tests are in ../tests; Angular templates and TypeScript
are checked by the production build and browser verification.

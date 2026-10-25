# primer-blank

The smallest product on the fixed stack of Primer: FastAPI, SQLAlchemy
(async), Postgres, alembic and Vue 3. The deploy machine `pridem` installs it
from `primer.yaml`; a new project starts as a copy of it.

- `primer.yaml` -- what the machine installs: one stack, edition `core`, the
  sources of its environment, routes for the frontend and the API.
- `backend/` -- the API. `primer_report/` serves `/health` and `/ready` and
  writes JSON logs (TZ section 11); `app/main.py` mounts it.
- `frontend/` -- the page. It reads `/config.json`, which its container
  renders from `API_BASE_URL` at start; the image carries no instance value.
- `probes/` -- checks of the built images; they need docker.

CI (`.github/workflows/ci.yml`) runs four jobs: backend, frontend, image and
check (`primer.yaml` through the machine's loader).

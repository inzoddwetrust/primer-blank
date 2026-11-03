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
  Its colors, fonts and logo are CSS custom properties (`src/theme.css`, the
  built-in theme). Its texts are built in for its two languages,
  `src/texts/en.json` and `src/texts/ru.json`: these files are the product's
  languages. The page speaks the first of the browser's languages it has,
  else English; which languages an instance turns on comes from the passport
  later (`languages`, not yet known to the machine).
- `packages` of `primer.yaml` -- the slots `skin` and `texts` of an instance,
  applied at run time: the machine mounts the packages the passport names at
  `/srv/skin` and `/srv/texts`, read-only. `frontend/nginx/package.js` serves
  them as `/skin.css` (the DTCG tokens as custom properties) and `/texts.json`
  (`ui/<language>.json` of the package, by language; a text it does not give is
  the built-in one of that language); with no package mounted the page keeps
  its own. `validate-skin <dir>` and
  `validate-texts <dir>` (`frontend/nginx/validate.js`) check a package in the
  frontend's image before the machine switches to it. The published packages:
  `primer-blank-skin` and `primer-blank-texts`, each slot on its own
  versions, and `primer-blank-brand`, both slots at one tag by `subpath` --
  public repositories of the owner `PACKAGES_OWNER` in CI names; their READMEs
  give the format.
- `probes/` -- checks of the built images; they need docker.

CI (`.github/workflows/ci.yml`) runs four jobs: backend, frontend, image and
check (`primer.yaml` through the machine's loader, and `pridem check` of the
repository with the published packages).

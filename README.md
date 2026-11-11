# primer-blank

The smallest product on the fixed stack of Primer: FastAPI, SQLAlchemy
(async), Postgres, alembic and Vue 3. The deploy machine `pridem` installs it
from `primer.yaml`; a new project starts as a copy of it.

- `primer.yaml` -- what the machine installs: the stack `primer-blank`,
  edition `core`, the sources of its environment, routes for the frontend and
  the API; and `primer-blank-files` (`deploy/files-compose.yml`), the files of
  the instance's people: `persistent: true`, its volume `files` outlives
  `destroy` and `reinstall`, only `destroy --all` wipes it.
- `verbs` of `primer.yaml` -- the project's verbs, run by the machine in their
  service (`pridem verb <name> <arg>=<value> ...`): `set-setting key=<k>
  value=<v>` in `app` (`python -m app.cli`, `backend/app/cli.py`), destructive
  -- it asks `--confirm <server.name>`; `count-settings` in `postgres`, on the
  role `test` only.
- `dependencies` of `primer.yaml` -- the machine's test service
  `primer-blank-service`, in every edition: the product takes three seams of
  it (`SERVICE_API_URL`, `SERVICE_TOKEN`, `SERVICE_KEY`), gives it
  `PRODUCT_WEBHOOK_URL` (`POST /internal/service/webhook`) and the data
  `profile/`; `primer.lock` pins its tag and commit. Its address is the
  `file://` mirror tier 3 of `pridem` keeps: the blank exists for that tier.
- `backend/` -- the API. `primer_report/` serves `/health` and `/ready` and
  writes JSON logs (TZ section 11); `app/main.py` mounts it.
- `frontend/` -- the page. It reads `/config.json`, which its container
  renders from `API_BASE_URL`, `LANGUAGES` and `DEFAULT_LANGUAGE` at start;
  the image carries no instance value. Its colors, fonts and logo are CSS
  custom properties (`src/theme.css`, the built-in theme). Its texts are built
  in for its two languages, `src/texts/en.json` and `src/texts/ru.json`: these
  files are the product's languages, declared as `languages: [en, ru]` in
  `primer.yaml`. An instance turns some of them on in its passport
  (`languages`, `default_language`); the machine checks them against the
  product's and gives them as `LANGUAGES` (codes by commas, the passport's
  order) and `DEFAULT_LANGUAGE`. The page speaks the first of the browser's
  languages the instance turns on, else the instance's default; a list or a
  default that is not the product's is an error the page shows.
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
check (`primer.yaml` through the machine's loader, `pridem check` of the
repository with the published packages, and the pins of the images of both
compose files).

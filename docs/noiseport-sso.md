# Noiseport single sign-on

noisebins signs people in with **OpenID Connect** (authorization code flow with PKCE). Someone who is
already signed in to Noiseport clicks **Sign in with Noiseport** and comes straight back signed in to
noisebins, with no password prompt. The resulting session cookie works for pages, the browser forms,
and same-origin calls to `/api/v1/...`. API clients can keep using `Authorization: Bearer <jwt>`.

The same code works against either Noisebridge identity provider; only the issuer changes:

| Provider | `NOISEPORT_ISSUER` | Notes |
| --- | --- | --- |
| Noiseport ([noisebridge/noiseport](https://github.com/noisebridge/noiseport), a Spaceport fork) | `https://api.<portal-host>/openid` | Built-in `django-oidc-provider`. Needs the small patch below. |
| Noisebridge Keycloak ("Noisebridge SSO", already used by donate-portal) | `https://<sso-host>/realms/<realm>` | Create a confidential OIDC client; no code changes. |

## How it works

1. `GET /auth/noiseport/login?next=/b/ABC` stores a signed, 10-minute state cookie (state, PKCE
   verifier, `next`) and redirects to the provider's `authorization_endpoint`.
2. Noiseport's `/openid/authorize` hands off to its web client's `/oidc` page. If the member already
   has a Noiseport session it approves immediately; otherwise they log in to Noiseport first.
3. `GET /auth/noiseport/callback` checks the state, exchanges the code (client secret + PKCE verifier),
   reads `/userinfo`, then finds or creates the noisebins user by the provider's `sub`
   (`oauth_account` table). It sets the `noisebins_session` cookie and redirects to `next`.
4. `POST /auth/logout` ends the noisebins session. The Noiseport session is left alone, so the next
   **Sign in** is again a single click.

Account linking rules:

- A returning member is matched by `sub`, never by email.
- A first-time member is merged into an existing email/password noisebins account **only** if the
  provider says `email_verified: true` (Keycloak can; Noiseport does not verify emails). Otherwise the
  sign-in is refused with 409 rather than letting anyone who typed that email into Noiseport take
  over the account.
- If the provider releases no email, the user gets a stable placeholder
  `noiseport-<sub>@sso.noisebins.noisebridge.net`.
- Provider access tokens are not stored.

`next` only accepts same-site paths (`/...`), so the login link cannot be turned into an open redirect.
The session cookie is `HttpOnly`, `SameSite=Lax` (so cross-site form posts don't carry it), and
`Secure` whenever `PUBLIC_BASE_URL` is `https://`.

## Configuration

```env
PUBLIC_BASE_URL=https://bins.noisebridge.net
NOISEPORT_OAUTH_ENABLED=true
NOISEPORT_DISPLAY_NAME=Noiseport        # label on the sign-in link
NOISEPORT_ISSUER=https://api.<portal-host>/openid
NOISEPORT_CLIENT_ID=...
NOISEPORT_CLIENT_SECRET=...
NOISEPORT_SCOPES=openid profile email
```

Endpoints are discovered from `${NOISEPORT_ISSUER}/.well-known/openid-configuration`.
`NOISEPORT_AUTHORIZE_URL`, `NOISEPORT_TOKEN_URL` and `NOISEPORT_USERINFO_URL` override discovery.

## Using the Noisebridge Keycloak (current production plan)

Production login starts on the Noisebridge Keycloak ("Noisebridge SSO", the same realm donate-portal
uses). Noiseport can replace it later by changing only the issuer and client credentials.

A Noisebridge Keycloak admin creates the client in the realm:

- **Client type:** OpenID Connect, **Client authentication: on** (confidential client), standard flow
  only (direct access grants and implicit flow off).
- **Client ID:** `noisebins` (any value works; it goes in `NOISEPORT_CLIENT_ID`).
- **Valid redirect URIs:** `${PUBLIC_BASE_URL}/auth/noiseport/callback`, for example
  `https://bins.noisebridge.net/auth/noiseport/callback`.
- **Web origins:** `${PUBLIC_BASE_URL}`.
- **Client scopes:** the default `profile` and `email` scopes, so `/userinfo` returns `email`,
  `email_verified` and `name`.
- Copy the client secret from the **Credentials** tab into `NOISEPORT_CLIENT_SECRET`.

Then configure noisebins (the variables keep their `NOISEPORT_` prefix; only the label changes):

```env
NOISEPORT_OAUTH_ENABLED=true
NOISEPORT_DISPLAY_NAME="Noisebridge SSO"   # header shows "Sign in with Noisebridge SSO"
NOISEPORT_ISSUER=https://<sso-host>/realms/<realm>
NOISEPORT_CLIENT_ID=noisebins
NOISEPORT_CLIENT_SECRET=...
```

Because Keycloak reports `email_verified`, members whose email Keycloak has verified are merged into
an existing email/password noisebins account with the same address on first sign-in.

## Registering noisebins in Noiseport

Noiseport currently runs Spaceport's code unchanged, which needs three small changes before any new
OIDC client works:

1. `OIDCAuthView` (`apiserver/apiserver/api/views.py`) only lets through clients named `vikunja`,
   `wiki`, `wiki_dev` and `opswiki`. Every other client fails with a 500, so add `noisebins`.
2. `LOGIN_URL` (`apiserver/apiserver/settings.py`) is hardcoded to Protospace hosts. Read it from an
   `OIDC_LOGIN_URL` environment variable (`https://<portal-host>/oidc`).
3. Without an `OIDC_USERINFO` function, `/openid/userinfo` releases only `sub`. Add one that fills
   `preferred_username`, `name`, and `email` (`email_verified: false`).

Then in Noiseport's Django admin, add an **OIDC Provider > Client**:

- Name: `noisebins` (must match the allowlist above)
- Client type: confidential; Response type: `code`
- Redirect URIs: `${PUBLIC_BASE_URL}/auth/noiseport/callback`
- JWT algorithm: RS256; Require consent: no; Reuse consent: yes
- Scopes: `openid profile email`

Copy the client ID and secret into the noisebins environment. Run `python manage.py creatersakey`
once if the portal has never issued OIDC tokens.

## Running the whole thing locally

This is how the flow was verified end to end against a real Noiseport checkout. Noiseport's
`apiserver` needs Python 3.8 (Django 3.1); its `webclient` is Create React App 3.

```sh
# Noiseport API on :8000
git clone https://github.com/noisebridge/noiseport && cd noiseport/apiserver
uv venv -p 3.8 env && echo "setuptools<58" > /tmp/bc.txt
VIRTUAL_ENV=env uv pip install --build-constraint /tmp/bc.txt -r requirements.txt
cp apiserver/secrets.py.example apiserver/secrets.py
export DEBUG=true BINDALL=true OIDC_LOGIN_URL=http://localhost:3000/oidc
env/bin/python manage.py makemigrations && env/bin/python manage.py makemigrations api
env/bin/python manage.py migrate && env/bin/python manage.py creatersakey
env/bin/python manage.py shell < seed.py      # see below
env/bin/python manage.py runserver 0.0.0.0:8000

# Noiseport web client on :3000 (it calls the API on :8000)
cd ../webclient && npx yarn@1 install --frozen-lockfile --ignore-engines
CI=true BROWSER=none NODE_OPTIONS=--openssl-legacy-provider npx react-scripts start

# noisebins on :8100
NOISEPORT_OAUTH_ENABLED=true NOISEPORT_ISSUER=http://localhost:8000/openid \
NOISEPORT_CLIENT_ID=noisebins-local NOISEPORT_CLIENT_SECRET=noisebins-local-secret \
PUBLIC_BASE_URL=http://localhost:8100 uvicorn noisebins.main:app --port 8100
```

`seed.py` creates a demo member and the noisebins client:

```python
from django.contrib.auth.models import User
from oidc_provider.models import Client, ResponseType
from apiserver.api import models

user, _ = User.objects.get_or_create(username="ada.lovelace", defaults={"email": "ada@noisebridge.example"})
user.set_password("noisebridge-demo")
user.save()
models.Member.objects.get_or_create(
    user=user, defaults=dict(first_name="Ada", last_name="Lovelace", preferred_name="Ada")
)

client, _ = Client.objects.get_or_create(client_id="noisebins-local", defaults=dict(name="noisebins"))
client.client_type = "confidential"
client.client_secret = "noisebins-local-secret"
client.redirect_uris = ["http://localhost:8100/auth/noiseport/callback"]
client.jwt_alg = "RS256"
client.require_consent = False
client.reuse_consent = True
client._scope = "openid profile email"
client.save()
client.response_types.set(ResponseType.objects.filter(value="code"))
```

Log in at http://localhost:3000 as `ada.lovelace` / `noisebridge-demo`, open http://localhost:8100,
and click **Sign in with Noiseport**.

## Deploying to Noisebridge Kubernetes (noisegarden)

Noisebridge's cluster config lives in the `noisegarden` repo on Forgejo (`git.noisegarden.nexus`),
not on GitHub. donate-portal is the closest example: Forgejo Actions build an image to
`git.noisegarden.nexus/noisebridge/<app>:<sha>`, and `infra/clusters/root/infra/<app>/deployment.yaml`
pins that sha. For noisebins that means:

- Build the `Dockerfile` in this repo (it runs `alembic upgrade head`, then uvicorn with proxy headers).
- Provide Postgres and set `DATABASE_URL`, `SECRET_KEY`, `USERS_JWT_SECRET`, `PUBLIC_BASE_URL`
  (https), and the `NOISEPORT_*` values from a Secret.
- Give `LOCAL_STORAGE_PATH` (default `/app/data/blobs`) a persistent volume until object storage lands.
- Register the client in whichever provider is live (Keycloak first, see above; Noiseport later)
  with the production callback URL.

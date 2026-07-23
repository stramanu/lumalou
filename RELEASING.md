# Releasing

Both packages are published from CI on a version tag. Versions are independent.

## One-time setup

### PyPI (Trusted Publishing — no token)
1. Create the `lumalou` project on PyPI (a first manual upload, or reserve the name).
2. PyPI → project → *Publishing* → add a **GitHub trusted publisher**:
   - Owner: `stramanu` · Repository: `lumalou`
   - Workflow: `release-python.yml` · Environment: `pypi`
3. In GitHub → repo → *Settings → Environments* → create environment `pypi`.

### npm (Trusted Publishing — no token)
Do **not** create a bypass-2FA automation token. Use Trusted Publishing (OIDC), like PyPI:

1. Claim the name with one manual publish (creates the package and makes you the owner):
   ```bash
   cd packages/js && npm install && npm run build
   npm publish --access public       # asks for your normal 2FA in the browser
   ```
2. npmjs.com → the `lumalou` package → *Settings → Trusted Publisher* → **GitHub Actions**:
   - Organization/user: `stramanu` · Repository: `lumalou`
   - Workflow filename: `release-js.yml`
3. From then on, releases publish from CI over OIDC — no token, provenance is automatic.

## Cut a release

Bump the version in the package, commit, then push a tag:

```bash
# Python  (packages/python/pyproject.toml -> version)
git tag py-v0.1.0 && git push origin py-v0.1.0

# JS/TS   (packages/js/package.json -> version)
git tag js-v0.1.0 && git push origin js-v0.1.0
```

The matching workflow builds, tests and publishes.

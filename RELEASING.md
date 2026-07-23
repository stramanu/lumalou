# Releasing

Both packages are published from CI on a version tag. Versions are independent.

## One-time setup

### PyPI (Trusted Publishing — no token)
1. Create the `lumalou` project on PyPI (a first manual upload, or reserve the name).
2. PyPI → project → *Publishing* → add a **GitHub trusted publisher**:
   - Owner: `stramanu` · Repository: `lumalou`
   - Workflow: `release-python.yml` · Environment: `pypi`
3. In GitHub → repo → *Settings → Environments* → create environment `pypi`.

### npm (automation token)
1. Create an npm **automation** token (npmjs.com → Access Tokens).
2. GitHub → repo → *Settings → Secrets and variables → Actions* → add secret `NPM_TOKEN`.

## Cut a release

Bump the version in the package, commit, then push a tag:

```bash
# Python  (packages/python/pyproject.toml -> version)
git tag py-v0.1.0 && git push origin py-v0.1.0

# JS/TS   (packages/js/package.json -> version)
git tag js-v0.1.0 && git push origin js-v0.1.0
```

The matching workflow builds, tests and publishes.

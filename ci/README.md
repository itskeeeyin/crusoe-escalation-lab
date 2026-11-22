# Offline tests and GitHub Actions

Run the tests without a Crusoe key:

```bash
python -m unittest discover -s tests -v
```

`github-actions.yml` is the workflow that runs those tests on push and pull request, with `CRUSOE_API_KEY` unset. To enable it on GitHub, copy this file to `.github/workflows/ci.yml` in the repo (creating that path requires the `workflow` scope, so it may need to be added from a local machine).

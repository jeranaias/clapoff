# Packaging status

Honest accounting of where clapoff can be installed from, and what's actually blocking
the rest. Nothing in here pretends to work before it does.

| Channel | Status | What's needed |
| --- | --- | --- |
| `pip install git+https://github.com/jeranaias/clapoff` | **works today** | nothing |
| GitHub Releases (wheel + sdist) | **ready** | push a `v*` tag; `release.yml` builds and attaches them |
| PyPI | **ready, unpublished** | a trusted publisher for `jeranaias/clapoff` on PyPI, then a tag |
| Homebrew | **blocked on PyPI** | see `clapoff.rb` — the resource stanzas can't be generated until an sdist exists |
| winget | **not started** | winget wants a real `.exe`/`.msi` installer; a Python CLI isn't one. Would need PyInstaller plus an installer build. Deliberately not faked. |

## Cutting a release

```bash
git tag v0.1.0 && git push --tags
```

That builds the wheel and sdist, attaches both to a GitHub release, and — once the
PyPI trusted publisher exists — publishes. Until then the `pypi` job is the only one
that fails and the release still goes out.

## Homebrew

`clapoff.rb` is written against a PyPI sdist that doesn't exist yet. After the first
release:

```bash
brew update-python-resources packaging/clapoff.rb   # fills in the resource stanzas
```

Then it belongs in a tap, not this repo.

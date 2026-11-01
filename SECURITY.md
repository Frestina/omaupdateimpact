# Security

## Reporting a problem

Please report it privately, not in a public issue. Use
[Report a vulnerability](https://github.com/Frestina/omaupdateimpact/security/advisories/new)
on the repository's Security tab.

Say which version you used, from `omaupdateimpact --version`, and how to reproduce
it. Leave out real config and tokens. A fictional example is enough.

This is a personal project, so there is no bounty and a reply may take a while.

Only the latest release gets fixes.

## What counts

The tool promises these things. Anything that breaks one is a security problem.

- Nothing from a release is run. Its files are only read as text.
- Nothing changes outside the tool's own cache, unless you ran `install.sh`.
- Nothing leaves the machine except GET requests to GitHub.
- `GITHUB_TOKEN` goes to `api.github.com` and nowhere else, and is never printed.

So a release, tag or archive that gets code run or files written elsewhere counts.
So does a check that shows as clear when it didn't run, if a release can cause that
on purpose.

## What doesn't count

- A finding that is wrong by accident. Open an issue for that.
- What Omarchy itself does during an update. Report that to Omarchy.
- What a package, plugin or command on your machine does when you run it.

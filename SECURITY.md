# Security

HomePool switches a real pump and a salt chlorinator. A flaw that lets someone
run them, stop them or turn off freeze protection without permission is a
safety problem, not only a software one.

## Reporting a vulnerability

Please report it privately, not in a public issue:

- On GitHub, open the repository's **Security** tab and choose **Report a
  vulnerability**. Only the maintainers see the report.
- Say which version you tested, what a person could do that they should not,
  and the steps to reproduce it. A test on a pool you own is welcome; never
  test against someone else's Home Assistant.

You should get a reply within a week. Once a fix is released, the release notes
credit you, unless you would rather not be named.

## Supported versions

Only the latest release gets security fixes. Update through HACS.

## What counts

- A Home Assistant user without control permission who can drive the pool
  through a `homepool.*` service or an entity.
- Readings or text that crash the integration, or that reach the card and run
  there.
- Personal data (location, names) leaking into diagnostics, logs or
  notifications.

Not in scope: weaknesses of Home Assistant itself, or of the switches and
sensors HomePool drives. Report those to their own projects.

The card has its own repository,
[domotk/homepool-card](https://github.com/domotk/homepool-card); report its
issues there the same way.

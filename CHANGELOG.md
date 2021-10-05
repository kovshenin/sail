# Changelog

## [Unreleased]

## [0.9.15] - 2021-10-05

* Added: New `profile` command group for performance profiling
* Added: New `gmail-dns.yaml` blueprint to add Google Mail / Workspace MX records
* Changed: Remove associated sailed.io DNS record on destroy

## [0.9.14] - 2021-09-22

* Added: New `mailgun.yaml` and `mailgun-dns.yaml` blueprints to deploy a [working Mailgun configuration](https://konstantin.blog/2021/mailgun-wordpress-sail-cli/)
* Added: New `postfix` blueprint component and postfix.yaml default BP
* Added: New `fail2ban` blueprint component and fail2ban.yaml default BP
* Added: A new `type` attribute to `vars` in blueprints, supports bool, int, float, str
* Added: New `--postfix` or `--mail` flags to `sail logs` to query postfix items in syslog
* Added: New `dns` blueprint component to add DNS records to your application domains
* Fixed: Plugin activation error when no custom plugins specified
* Fixed: Theme activation mismatch in blueprints, when custom theme above wporg themes

## [0.9.13] - 2021-09-17

* Added: Blueprints are here! `sail blueprint path/to/blueprint.yaml` to apply
* Added: End-to-end tests around blueprints, tweaked testing a bit, added GitHub workflows to run tests on push/PR
* Changed: Fixed system journal requiring a restart for `sail logs` to work
* Changed: Fixed .com.br and .com.tr now treated as TLDs when working with domains
* Changed: Make sure new Droplet is assigned an actual IP address prior to using it
* Changed: Updated readme to reflect BPs, added push-to-deploy links

## [0.9.12] - 2021-09-12

* Added: New `--skip-dns` flag for `domain add` and `domain delete` which skips making any DNS changes
* Added: Long-awaited `sail restore` command, to restore complete site backups to production
* Added: New `--skip-replace` argument for `domain make-primary`, to skip the search-replace ops
* Added: Sparse deploys via an optional `path` argument for `deploy`, to specify one or more subtrees to process
* Added: Sparse downloads, similar to deploys with optional `path` argument for `download`
* Changed: `deploy` now prepares the new release directory with a copy from the live release
* Changed: Added a new `util.rsync()` function to standardize usage across all commands
* Changed: End-to-end test now includes multiple scenarios for `deploy` and `download` routines
* Changed: Slight refactoring, regrouping of commands, simpler ones went to a new misc.py instead of their own files
* Removed: `--delete` argument from `deploy` since it was not really implemented (in a correct way) anyway

## [0.9.11] - 2021-09-06

* Added: New `destroy` command to shutdown and delete a droplet
* Added: First couple unit tests and a short end-to-end test
* Added: New `--dry-run` flag for `deploy` and `download` commands
* Added: New `db export` and `db import` commands
* Changed: Renamed `mysql` command to `db` group, shell with `sail db cli` now
* Changed: Lots of moving files around and reorganizing code
* Changed: Shorthand `-v` flag to display version
* Changed: The `backup` command now uses a database export routine similar to `db export`

## [0.9.10] - 2021-09-03

* Added: New rollback command to quickly fix failed deployments
* Changed: Some housekeeping and various small fixes and typos

## [0.9.9] - 2021-09-03

* Added: First public release on Homebrew

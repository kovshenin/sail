# Changelog

## [Unreleased]

* Added: New `destroy` command to shutdown and delete a droplet
* Added: First couple unit tests and a short end-to-end test
* Added: New `--dry-run` flag for `deploy` and `download` commands
* Added: New `db export` and `db import` commands
* Changed: Renamed `mysql` command to `db` group, shell with `sail db cli` now
* Changed: Lots of moving files around and reorganizing code
* Changed: Shorthand `-v` flag to display version
* Changed: The `backup` command now uses a database export routine similar to `db export`

## [0.9.9] - 2020-09-03

* Added: New rollback command to quickly fix failed deployments
* Changed: Some housekeeping and various small fixes and typos

## [0.9.9] - 2020-09-03

* Added: First public release on Homebrew

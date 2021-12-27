# Changelog

## [Unreleased]

## [0.10.3] - 2021-12-27

* Added: A default.yaml blueprint, with Surge cache and fail2ban pre-insalled
* Added: Quite a few colors to most of the Sail commands, better output formatting, output utils
* Changed: Increased default upload/post max size from 2/8M to 128M in PHP
* Changed: Increased client_max_body_size from 32M to 128M in Nginx
* Changed: `sail backup` is now an alias to `sail backup create`, `sail restore` is an alias to `sail backup restore`
* Changed: Added a `quiet` argument to `ssh key add` to suppress output
* Changed: Updated various dependencies
* Changed: Better error handling in install.sh
* Changed: Cleaned README.md, moved remaining tutorials to the [knowledgebase](https://sailed.io/kb/)
* Fixed: Installer will no longer fail silently on missing python3-venv module
* Fixed: Error in postfix unable to read the main.cf configuration file
* Added: Managed backups `sail backup` (automatic daily and on-demand) via Sail Premium
* Added: Uptime and health monitoring `sail monitor` with e-mail/SMS alerts via Sail Premium
* Added: Image optimization and WebP via Sail Premium

## [0.10.2] - 2021-12-13

* Added: New `sail cron` commands to add, remove and view system cron entries
* Added: Default fastcgi_cache configuration, compatible with most advanced-cache.php-based caching plugins
* Added: A `--json` flag to the `sail db export` command for easier integration with third-party scripts
* Changed: Update xhprof.so for profiling, adds labels to do_shortcode_tag
* Changed: Nginx server configuration template now adds http2 support by default
* Changed: Increased various timeouts in `init`
* Changed: .ico requests can now be served by PHP/WordPress
* Fixed: ufw now properly configured during provision
* Fixed: Redirects in `sail profile` will no longer be followed

## [0.10.1] - 2021-11-19

* Changed: Postfix and postfix-related blueprints now support namespaces under the hood
* Changed: `sail destroy` will now delete DNS records for all associated domains, use `--skip-dns` to bypass
* Changed: `sail domain delete` will no longer delete orphaned subdomains when given a parent domain
* Changed: `sail domain delete` will now attempt to delete the DNS zone only if no more records exist in that zone
* Changed: `sail domain delete` now accepts a `--zone` flag which forces a DNS zone delete (and orphaned subdomains form config.json)
* Added: Support for the Mailgun EU region in `mailgun.yaml` blueprint
* Added: Support for a `.deployignore` file to remove certain patters from deployment

## [0.10.0] - 2021-11-10

* Added: Namespaces and environments to run multiple applications in the same environment. Use `--namespace` and `--environment` with `init`.
* Added: New `pre-deploy` hooks in .sail, these will run every time deploy is invoked
* Added: New `sail diff` command, shortcut for `sail deploy --dry-run` and `sail download --dry-run`
* Added: A new `install.sh` script to install and update Sail CLI
* Changed: New `--skip-hooks` or `--no-verify` options to `sail deploy` to skip running hooks
* Changed: Blueprints now fully client-side
* Changed: Provision and destroy are mostly client-side (API calls only to control justsailed.io DNS)
* Changed: Sizes and regions now client-side
* Changed: Domains, primary and HTTPS fully client-side, domains settings in .sail/config.json
* Changed: Provision now uses cloud-config instead of a Docker image, removed `--host` option from ssh commands

## [0.9.18] - 2021-10-26

* Added: New `sail ssh run` command
* Added: New `apt` section for blueprints
* Added: New `site-verification.yaml` blueprint to add TXT records
* Changed: Deploys, rollbacks and release-tracking are now 100% client-side
* Changed: Split `--host` and `--root` arguments for `sail ssh shell`
* Changed: Use Fabric instead of SSH subprocess in db and full backups
* Changed: Some overall refactoring

## [0.9.17] - 2021-10-13

* Added: New `sail ssh key` group of commands to list, add and delete SSH keys
* Added: `sail info` command to show some basic project information
* Change: Add a default 1G swap file for new provisions
* Fixed: Rsync/SSH not working on project paths with spaces

## [0.9.16] - 2021-10-07

* Added: New `profile clean` command to delete local and remove profiling data
* Added: `php-xml` and `php-zip` packages to the core image
* Added: Support for the newer justsailed.io internal subdomains
* Fixed: When deleting a parent domain orphaned subdomains were not deleted
* Fixed: Poor performance navigating the profile browser with > 5k entries

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

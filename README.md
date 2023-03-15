# Deploy WordPress to DigitalOcean with Sail

[Sail](https://sailed.io) is a free CLI tool to deploy, manage and scale WordPress applications
in the DigitalOcean cloud. Visit [our knowledgebase](https://sailed.io/kb/) for the complete
documentation. For support and announcements [join our Slack](https://join.slack.com/t/sailed/shared_invite/zt-vgnf8dfb-oPH1ZY1IwFSg_WyECYh5ow).

![Unit Tests](https://github.com/kovshenin/sail/actions/workflows/unit-tests.yml/badge.svg)
![End-to-End Tests](https://github.com/kovshenin/sail/actions/workflows/end2end-tests.yml/badge.svg)
![Stars](https://img.shields.io/github/stars/kovshenin/sail?style=social)

![Sail CLI Demo](https://user-images.githubusercontent.com/108344/147114001-409080ba-e5c6-4f01-81ff-2bd40c6980a5.png)

## Installation

To download and install Sail CLI on Linux, macOS or Windows (via WSL), run the
following command in your terminal:

```
curl -sSLf https://sailed.io/install.sh | bash
```

If you're looking for other ways to install Sail, checkout the
[installing section](https://sailed.io/kb/install/) in the Sail Knowledgebase.

## Documentation

Visit [our knowledgebase](https://sailed.io/kb/) for detailed setup and usage
instructions. Community support is available in [our Slack workspace](https://join.slack.com/t/sailed/shared_invite/zt-vgnf8dfb-oPH1ZY1IwFSg_WyECYh5ow).

Commands:

	admin      Open your default web browser to wp-admin. Logs in automatically if supported
	backup     Create, restore and manage application backups
	blueprint  Run a blueprint file against your application
	config     Set reusable config variables
	cron       Add, delete, view and execute system cron jobs
	db         Import and export MySQL databases, or spawn an interactive shell
	deploy     Deploy your working copy to production.
	destroy    Destroy an application namespace and/or the environment
	diff       Show file changes between your local copy and production.
	domain     Add, remove and update domains associated with your site
	download   Download files from production to your working copy
	info       Show current sail information
	init       Initialize and provision a new project
	logs       Query and follow logs from the production server
	profile    Run the profiler to find application performance bottlenecks
	rebuild    Rebuild an application environment.
	regions    Get available deployment regions
	restore    Restore your application files, uploads and database from a file
	rollback   Rollback production to a previous release
	sftp       Manage SFTP access on this server
	sizes      Get available droplet sizes
	ssh        Open an SSH shell, manage SSH keys and more
	wp         Run a WP-CLI command on the production host

Run `sail <command> --help` for usage instructions.

## License and Contributing

The Sail CLI client is free and open source, distributed under the GNU General
Public License version 3. Feel free to contribute by opening an issue or pull
request on our [GitHub project](https://github.com/kovshenin/sail).

The Sail API server is proprietary and runs on the sailed.io/justsailed.io domains.

### Legal

This software is provided **as is**, without warranty of any kind. Sail authors and contributors are **not responsible** for any loss of content, profits, revenue, cost savings, data, or content, or any other direct or indirect damages that may result from using the software or services provided by sailed.io.

Sail is not affiliated with DigitalOcean LLC.

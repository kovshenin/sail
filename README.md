# Deploy WordPress to DigitalOcean with Sail

[Sail](https://sailed.io) is a free CLI tool to deploy, manage and scale WordPress applications
in the DigitalOcean cloud. Visit [our knowledgebase](https://sailed.io/kb/) for the complete
documentation. For support and announcements [join our Slack](https://join.slack.com/t/sailed/shared_invite/zt-vgnf8dfb-oPH1ZY1IwFSg_WyECYh5ow).

![Unit Tests](https://github.com/kovshenin/sail/actions/workflows/unit-tests.yml/badge.svg)
![End-to-End Tests](https://github.com/kovshenin/sail/actions/workflows/end2end-tests.yml/badge.svg)

Contents:

* [Installing Sail](#installing-sail)
	+ [Using Homebrew (Linux, MacOS, WSL on Windows)](#using-homebrew-linux-macos-wsl-on-windows)
	+ [From PyPI](#from-pypi)
	+ [From Source](#from-source)
* [Getting a DigitalOcean API Token](#getting-a-digitalocean-api-token)
	+ [Account](#account)
	+ [API Token](#api-token)
* [Creating a New Sail Project](#creating-a-new-sail-project)
	+ [Selecting a Droplet Size and Region](#selecting-a-droplet-size-and-region)
* [Domains and DNS](#domains-and-dns)
	+ [SSL and HTTPS](#ssl-and-https)
	+ [Primary Domains](#primary-domains)
* [Deploying Changes](#deploying-changes)
	+ [Rolling Back](#rolling-back)
	+ [Downloading Changes from Production](#downloading-changes-from-production)
* [Creating a Backup](#creating-a-backup)
	* [Restoring a Backup](#restoring-a-backup)
	+ [Exporting and Importing the Database](#exporting-and-importing-the-database)
* [Accessing the Server and Application](#accessing-the-server-and-application)
* [Accessing Logs](#accessing-logs)
* [Integrating with Git](#integrating-with-git)
* [Blueprints](#blueprints)
* [Profiling](#profiling)
* [Migrating existing projects to Sail](#migrating-existing-projects-to-sail)
* [Support](#support)
* [License and Contributing](#license-and-contributing)

## Installing Sail

### Using Homebrew (Linux, MacOS, WSL on Windows)

The easiest and preferred way to install Sail and keep it up to date, is through
the [Homebrew](https://brew.sh/) package manager. It works on MacOS, Linux, and
Windows (via WSL):

```
brew install sail
```

If you're new to Howebrew, [installing it](https://brew.sh/) is quite a breeze as well.

### From PyPI

If you already use Python and pip, you can obtain the latest version of Sail
from PyPI:

```
pip3 install sailed.io
```

### From Source

You will need Python 3.6+ with `pip` and `setuptools` available. Download
the source files from GitHub, install dependencies and run the Sail installation:

```
pip3 install -r requirements.txt
python3 setup.py install
```

Consider installing Sail in a virtual environment, to make sure dependencies
aren't broken for other Python software on the system:

```
python3 -m venv .env
.env/bin/pip install -r requirements.txt
.env/bin/python setup.py install
ln -s .env/bin/sail /usr/local/bin/sail
```

## Getting a DigitalOcean API Token

Sail uses the DigitalOcean API to interact with cloud services, for which you'll need
a DigitalOcean account, as well as a read-write API token.

### Account

If you don't already have an account, you can sign up for DigitalOcean
using [our affiliate link](https://m.do.co/c/e56ab924a5b6) which grants you
$100 in free credits, and a small commission to our project account. If you would
rather not sign up using an affiliate link, just browse to `www.digitalocean.com`

### API Token

To create a DigitalOcean API token, sign in to your account, browse to
**API > Tokens/Keys**, and hit the **Generate New Token** button. Give it a
descriptive name, for example "sail", and make sure both **Read** and **Write**
scopes are selected.

After generating the token, it'll show up in the list of personal access tokens,
you'll see the token itself directly below the token name. **Copy** that token
and store it in a safe place.

## Creating a New Sail Project

Create an empty directory for your new project, and from there run:

```
sail init --provider-token=<YOUR_TOKEN> --email=<ADMIN_EMAIL>
```

This will initialize your project, provision services, and download your first
working copy of your new WordPress application. Once successful, you'll see
the URL and the wp-admin credentials.

If you're planning to use Sail for multiple projects, you should consider saving
your provider token and admin e-mail address to `sail config` as defaults:

```
sail config provider-token <YOUR_TOKEN>
sail config email <ADMIN_EMAIL>
```

This way you can simply:

```
sail init
```

If you'd like to migrate an existing WordPress application into a Sail-powered
project, you'll still need to provision a new project first. For more information
take a look at [Migrating existing projects to Sail](#migrating-existing-projects-to-sail).

### Selecting a Droplet Size and Region

By default Sail will deploy a small `s-1vcpu-1gb-intel` droplet in
the `ams3` (Amsterdam 3) region. You can change these with the `--size` and
`--region` arguments respectively:

```
sail init --size=s-2vcpu-4gb-amd --region=sfo2
```

You can grab a list of valid sizes and regions with `sail sizes` and
`sail regions` respectively.

## Domains and DNS

Sail provisions your new site with a `random-hash.sailed.io` subdomain. This is
used internally by Sail and Sail Services. You can add your own custom domains
to your application with Sail:

```
sail domain add example.org
```

This will create a DNS record on your DigitalOcean account, pointing to your
application droplet. You can add multiple domains and subdomains by providing
a space-separated list.

When the records are added, you'll need to change the name server
records for your domain, at your domain registrar, to point to DigitalOcean:

* ns1.digitalocean.com
* ns2.digitalocean.com
* ns3.digitalocean.com

Here's [a tutorial](https://www.digitalocean.com/community/tutorials/how-to-point-to-digitalocean-nameservers-from-common-domain-registrars)
on how to do that for common domain registrars.

**Note**: When moving DNS from another provider to DigitalOcean, don't forget to
copy all existing records from that provider, including MX, TXT and CNAME records.

If you fail to do this, you may break some third-party services, such as e-mail,
transactional mail, Google search console verification, and others.

While not officially supported, you can add a subdomain to your Sail application
while leaving your DNS hosted elsewhere. To do this, add a CNAME record for your
subdomain at your DNS provider, and point it to your .sailed.io subdomain.

### SSL and HTTPS

After the name server records are updated and your domain is pointing to your
WordPress application, you can ask Sail to request and install a free SSL certificate
from Let's Encrypt:

```
sail domain make-https example.org www.example.org
```

Issued certificates will be installed and renewed automatically on your droplet.

### Primary Domains

After the domains have been added and SSL'd, you can change the primary domain
of your WordPress application with Sail:

```
sail domain make-primary example.org
```

## Deploying Changes

Any change that you make to your local working copy of a Sail project, can be
deployed to production with `sail deploy`:

```
sail deploy
```

By default this will omit the wp-content/uploads directory, but could be included
with the `--with-uploads` flag. This is particularly useful when importing
existing applications to Sail.

You can run deploy with the `--dry-run` flag to get a list of file changes, which
will be written to the production server during the deploy.

### Rolling Back

In most failed deployment situations, it often makes sense to correct the mistake
in your working copy and deploy again. However, sometimes you working copy might
be dirty or in an unknown state, in which case the easiest and fastest way to
resolve the problem would be a rollback.

A rollback simply changes the web root symlink on the production server to point to a
release deployed earlier. This means that your working copy does not need to
be transferred to production at all.

```
sail rollback <release>
```

To get a list of available releases, use:

```
sail rollback --releases
```

Sail keeps the last five releases on your production server, and deletes the older
ones every time you deploy. These can be found in the /var/www/releases directory
on your droplet.

Note that after a successful rollback, the production data will most likely be
different from your working copy, so it might be a good idea to save the state
of your working copy to your source repository, then download the live application
files from production, as explained in the next section.

### Downloading Changes from Production

In some cases your production code could be altered, for example when you update
WordPress core, a theme or plugin. You can pull these changes down do your
local copy with `sail download`:

```
sail download
```

Similar to deploying, if you would like to pull down all of wp-content/uploads
as well, just add the `--with-uploads` flag.

By default, downloading with Sail will not delete files from your working
copy, which do not exist on your production server. If a plugin or theme is
deleted in production, you'll have to use the `--delete` flag to pull
those changes back to your working copy.

Similar to deploy, the `--dry-run` flag will display a list of file changes that
will occur during a download.

## Creating a Backup

You can backup your WordPress application with Sail:

```
sail backup
```

This will download all your application files, your uploads, as well as a full
dump of your MySQL database tables, compress and archive them to your
local `.backups` directory.

Don't forget to backup your backups.

### Restoring a Backup

Backup files created by Sail can easily be restored back to production:

```
sail restore .backups/backup-filename.tar.gz
```

Note that this is not an atomic operation (like deploy) as it restores files
directly to the public folder on production. Uploads and the database are also
restored from the backup archive, these can be skipped with `--skip-uploads`
and `--skip-db` respectively.

A restored backup will not appear as a new release, so it can't easily be rolled
back. It also does not affect the local working copy, which can become dirty as
a result of this operation. It is recommended to use `sail download` after each
restore.

### Exporting and Importing the Database

Download a full database dump from production:

```
sail db export
```

This will write a compressed .sql.gz file to your .backups directory. Such files
can be imported back to production:

```
sail db import .backups/filename.sql.gz
```

Regular .sql files can be imported too.

## Accessing the Server and Application

You have **full root access** to every server you provision with Sail. There is
no password for security reasons, but your root SSH key is saved to `.sail/ssh.key`
after provisioning your application.

You can use this key directly with SSH or GUI SFTP software. Sail provides a
handful of useful commands too:

Open an interactive SSH shell to your application:

```
sail ssh
```

This will open a session as the `www-data` user, inside the application container
on the `/var/www/public` directory. If you'd rather open a root session on your
host droplet, just add `--root` or `--host` to the command.

The host server will contain the original `/var/www` directory, with all your
application releases, as well as your SSH service configuration in /etc/ssh. So
it's not all that useful, though you can use it to reboot your server for example.

The remaining services run inside a container named `sail`, which you can access
from the host droplet with Docker:

```
docker exec -it sail bash
```

There you will have access to /etc/nginx, /etc/php, /etc/mysql and everything
else. Remember: with great power comes great responsibility.

Here are a few other useful things you can do with Sail.

Run a WP-CLI command or spawn a WP-CLI interactive shell:

```
sail wp option get home
sail wp shell
```

Spawn an interactive MySQL shell:

```
sail db cli
```

Open your browser to your application's wp-login.php location:

```
sail admin
```

## Accessing Logs

You can query your Nginx, PHP, mail and system logs directly from Sail:

```
sail logs
sail logs --nginx
sail logs --php
sail logs --postfix
```

Add `--follow` or `-f` to tail-follow the logs, really useful while debugging.

## Integrating with Git

It is always a great idea to use Git or other modern source code management systems
when working with WordPress applications. Sail does not depend on any particular
flavor, nor does it require the use of one at all.

However, if you do choose to work with one, make sure you ignore
the `.sail` and `.backups` directories from source control. It's a good idea to
ignore all dot-files anyway. You will probably not want your `wp-content/uploads`
directory in source control either.

Here's an example .gitignore file:

```
.*
wp-content/uploads
wp-content/upgrade
```

Note, that during a deploy, **everything** in your working copy, except dot files
and uploads, will be shipped to your production server's public directory, even
files that are not under source control.

If you're looking for **push-to-deploy** with Git and GitHub Actions, check out
[this simple tutorial](https://konstantin.blog/2021/sail-push-to-deploy-github-actions/)
or [this video](https://youtu.be/6JkD8ekkAy8?t=4563).

## Blueprints

Blueprints in Sail are YAML files, which define the environment, where the WordPress
application is provisioned. This can include things like non-default plugins, themes,
options, constants, as well as additional server software and configuration.

To apply a blueprint, simply run:

```
sail blueprint path/to/blueprint.yaml
```

You can apply a blueprint during an `init` as well:

```
sail init --blueprint path/to/blueprint.yaml
```

Blueprints allow developers to define custom variables. Sail will either prompt
for these variables, or look for them on the command line interface. For example:

```
options:
  blogname: ${{ blogname }}

vars:
- name: blogname
  prompt: What is your site name
  option: --blogname
  default: Just another WordPress site
```

This will cause an interactive prompt when applying the blueprint, unless
the value for that variable is passed in using the `--blogname` option on
the command line:

```
sail blueprint path/to/blueprint.yaml --blogname="My New Blog"
```

**Note**: Some blueprints will create files and directories on your production
server. It is highly recommend to `sail download` to make sure your working
copy is in sync.

### Default Blueprints

Sail ships with some sample and common blueprints, available in the blueprints
directory:

* **fail2ban.yaml**: This installs and configures fail2ban with the default sshd
  jail, as well as a few custom WordPress jails to protect against password
  bruteforce attacks and XML-RPC pingback flood attacks. It also includes a
  WordPress mu-plugin that logs auth and XML-RPC attempts to syslog.
* **postfix.yaml**: Installs and configures a Postfix server to queue messages
  locally and relay them to an external SMTP service. Great for Mailgun, Gmail SMTP
  and other mail delivery services.
* **mailgun.yaml** and **mailgun-dns.yaml**: DNS validation and full Postifx
  configuration for Mailgun transactional e-mail service.
* **sample.yaml**: This file contains all available blueprint components with
  some usage examples and comments. Don't actually apply this file.

## Profiling

Sail ships with a built-in performance profiler for WordPress. It will help you
spot performance bottlenecks in your application code. To generate a profile run:

```
sail profile https://example.org
```

This will perform an HTTP request to the specified URL, gather and store all
profiling data, download the data to your local working copy, and open it in
the profile browser.

Learn more about [profiling WordPress with Sail CLI](https://sailed.io/kb/profile/)
in our knowledgebase.

## Migrating existing projects to Sail

Provisioning new sites with Sail is great, but often times you'll want to
migrate an existing WordPress application to DigitalOcean with Sail. Here's
a useful checklist to help you out.

1. Provision a new application with Sail
1. Download a full backup from your current provider
1. Copy the application files and wp-content/uploads, but **not your wp-config.php** to your new Sail working copy
1. Merge the wp-config.php file by hand, database credentials should remain the ones provided by Sail, everything else is up to you
1. Import the database .sql file from your local computer with `sail db import path/to/database.sql`
1. Use `sail deploy --with-uploads` to push your application files and uploads to production
1. Add your domains and select a primary one with `sail domain add` and `sail domain make-primary`

If everything is looking good, you should point your domain to Sail as described
in the [Domains and DNS](#domains-and-dns) section. After DNS propagation is complete
you should be able to request and install new SSL certificates for your application.

## Support

[Our knowledgebase](https://sailed.io/kb/) should be your primary source for help and support.
Community support is available in [our Slack workspace](https://join.slack.com/t/sailed/shared_invite/zt-vgnf8dfb-oPH1ZY1IwFSg_WyECYh5ow).
If you do not use Slack, feel free to open an issue here on GitHub.

## License and Contributing

The Sail CLI client is free and open source, distributed under the GNU General Public License version 3. Feel free to contribute by opening an issue or pull request on our [GitHub project](https://github.com/kovshenin/sail).

The Sail API server is proprietary and runs on the sailed.io domain. It is used by most core Sail CLI commands and features, including but not limited to provisioning, deploying, domain management and more.

### Legal

This software is provided **as is**, without warranty of any kind. Sail authors and contributors are **not responsible** for any loss of content, profits, revenue, cost savings, data, or content, or any other direct or indirect damages that may result from using the software or services provided by sailed.io. DigitalOcean terms of service can be found [here](https://www.digitalocean.com/legal/terms-of-service-agreement/). DigitalOcean is a trademark of DigitalOcean, LLC.

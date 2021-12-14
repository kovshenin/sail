# Deploy WordPress to DigitalOcean with Sail

[![Join the chat at https://gitter.im/kovshenin/sail](https://badges.gitter.im/kovshenin/sail.svg)](https://gitter.im/kovshenin/sail?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

[Sail](https://sailed.io) is a free CLI tool to deploy, manage and scale WordPress applications
in the DigitalOcean cloud. Visit [our knowledgebase](https://sailed.io/kb/) for the complete
documentation. For support and announcements [join our Slack](https://join.slack.com/t/sailed/shared_invite/zt-vgnf8dfb-oPH1ZY1IwFSg_WyECYh5ow).

![Unit Tests](https://github.com/kovshenin/sail/actions/workflows/unit-tests.yml/badge.svg)
![End-to-End Tests](https://github.com/kovshenin/sail/actions/workflows/end2end-tests.yml/badge.svg)
![Stars](https://img.shields.io/github/stars/kovshenin/sail?style=social)

Contents:

* [Getting Started](#getting-started)
* [Domains and DNS](#domains-and-dns)
* [SSL Certificates and HTTPS](#ssl-certificates-and-https)
* [Deploying Changes](#deploying-changes)
* [Downloading Changes from Production](#downloading-changes-from-production)
* [Working with Backups](#working-with-backups)
* [SSH Access](#ssh-access)
* [Logs](#logs)
* [Blueprints](#blueprints)
* [Profiling](#profiling)
* [Support](#support)
* [License and Contributing](#license-and-contributing)

## Getting Started

To download and install Sail CLI on Linux, macOS or Windows (via WSL), run the
following command in your terminal:

```
curl -sSLf https://sailed.io/install.sh | bash
```

If you've already installed Sail. If you're looking for other ways to install
Sail, checkout the [installing section](https://sailed.io/kb/install/) in the
Sail Knowledgebase.

Next, you'll to set up [your DigitalOcean API token](https://sailed.io/kb/digitalocean-api-token/),
and an e-mail address used for the default admin account:

```
sail config provider-token <YOUR_API_TOKEN>
sail config email <ADMIN_EMAIL>
```

Finally, create an empty directory and run:

```
sail init
```

This will initialize your project, provision services, and download your first
working copy of your new WordPress application. Once successful, you'll see
the URL and the wp-admin credentials.

If you'd like to migrate an existing WordPress application into a Sail-powered
project, you'll still need to provision a new project first. For more information
take a look at [Migrating existing projects to Sail](https://sailed.io/kb/migrating/).

If you would like to host multiple WordPress sites on a single server, consider
using [namespaces](https://sailed.io/kb/namespaces/), which allow you to provision
additional applications within the same provisioned environment. You can also
select a Droplet [size and region](https://sailed.io/kb/sizes-regions/) during init.

## Domains and DNS

Sail provisions your new site with a `random-hash.justsailed.io` subdomain. This is
used internally by Sail and Sail Services. You can add your own custom domains
to your application with Sail:

```
sail domain add example.org
```

This will create a DNS record on your DigitalOcean account. You can find more
information on adding domains to your Sail project in [our knowledgebase](https://sailed.io/kb/domain/).

## SSL Certificates and HTTPS

After the name server records are updated and your domain is pointing to your
WordPress application, you can ask Sail to request and install a free SSL certificate
from Let's Encrypt:

```
sail domain make-https example.org www.example.org
```

Issued certificates will be installed and renewed automatically on your droplet.
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

You can run deploy with the `--dry-run` flag to get a list of file changes, which
will be written to the production server during the deploy.

You can add pre-deploy hooks to your Sail project. These are useful to run PHP linter,
PHPCS and other tools prior to deploying to production. Here's a [quick guide](https://sailed.io/kb/pre-deploy-phpcs/)
using a simple pre-deploy hook to lint PHP files and run them through the
WordPress Coding Standards check.

If you're looking for **push-to-deploy** with Git and GitHub Actions, check out
[this simple tutorial](https://konstantin.blog/2021/sail-push-to-deploy-github-actions/)
or [this video](https://youtu.be/6JkD8ekkAy8?t=4563).

You can learn more about [deploying with Sail CLI here](https://sailed.io/kb/deploy/).

## Downloading Changes from Production

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

## Working with Backups

You can backup your WordPress application with Sail:

```
sail backup
```

This will download all your application files, your uploads, as well as a full
dump of your MySQL database tables, compress and archive them to your
local `.backups` directory.

Don't forget to backup your backups!

You can learn more about creating and restoring application and database
backups [in the Sail knowledgebase](https://sailed.io/kb/backup/).

## SSH Access

You have **full root access** to every server you provision with Sail. There is
no password for security reasons, but your root SSH key is saved to `.sail/ssh.key`
after provisioning your application. You can [add/remove your own SSH keys](https://sailed.io/kb/ssh-key/) too.

You can use this key directly with SSH or GUI SFTP software. Sail provides a
handful of useful commands too:

Open an interactive SSH shell to your application:

```
sail ssh
```

This will open a session as the `www-data` user in the `/var/www/public` directory.
If you'd rather open a root session, just add `--root` to the command.

## Logs

You can query your Nginx, PHP, mail and system logs directly from Sail:

```
sail logs
sail logs --nginx
sail logs --php
sail logs --postfix
```

Add `--follow` or `-f` to tail-follow the logs, really useful while debugging.

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
* **gmail-dns.yaml** Add DNS records for Google Mail.
* **site-verification.yaml** Add a TXT record for site verification in Google
  Search Console and other services.
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

## Support

[Our knowledgebase](https://sailed.io/kb/) should be your primary source for help and support.
Community support is available in [our Slack workspace](https://join.slack.com/t/sailed/shared_invite/zt-vgnf8dfb-oPH1ZY1IwFSg_WyECYh5ow).
If you do not use Slack, feel free to open an issue here on GitHub.

## License and Contributing

The Sail CLI client is free and open source, distributed under the GNU General
Public License version 3. Feel free to contribute by opening an issue or pull
request on our [GitHub project](https://github.com/kovshenin/sail).

The Sail API server is proprietary and runs on the sailed.io/justsailed.io
domains and usage statistics.

### Legal

This software is provided **as is**, without warranty of any kind. Sail authors and contributors are **not responsible** for any loss of content, profits, revenue, cost savings, data, or content, or any other direct or indirect damages that may result from using the software or services provided by sailed.io. DigitalOcean terms of service can be found [here](https://www.digitalocean.com/legal/terms-of-service-agreement/). DigitalOcean is a trademark of DigitalOcean, LLC.

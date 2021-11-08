from sail import cli, util

import requests, json, os, subprocess, time, io
import click
import tldextract
import digitalocean
import urllib
import shlex

@cli.group()
def domain():
	'''Add, remove and update domains associated with your site'''
	pass

@domain.command()
def list():
	'''List domains associated with your site'''
	config = util.config()

	click.echo('# Domains')
	for domain in config['domains']:
		flags = []
		for flag in ['internal', 'https', 'primary']:
			if domain.get(flag, None):
				flags.append(flag)

		sflags = ''
		if flags:
			sflags = ' (%s)' % ', '.join(flags)

		click.echo('- ' + domain['name'] + sflags)

@domain.command()
@click.argument('domain', nargs=1)
@click.option('--force', is_flag=True, help='Make primary again, even if the domain is already set as the primary one')
@click.option('--skip-replace', is_flag=True, help='Skip running search-replace routines for home, siteurl, and other URLs')
def make_primary(domain, force, skip_replace):
	'''Set a domain as primary, update siteurl/home, search-replace all links'''
	config = util.config()

	click.echo('# Updating primary domain')

	if domain not in [d['name'] for d in config['domains']]:
		raise click.ClickException('Can not make primary, domain does not exist')

	domain = [d for d in config['domains'] if d['name'] == domain][0]
	if domain['primary'] and not force:
		raise click.ClickException('Domain %s already set as primary. Use --force to force' % domain['name'])

	c = util.connection()
	wp = 'sudo -u www-data wp --path=%s --skip-themes --skip-plugins ' % util.remote_path('/public/')

	home = c.run(wp + 'option get home').stdout.strip()
	current = urllib.parse.urlparse(home).netloc
	proto = 'https://' if domain['https'] else 'http://'
	click.echo('- Current primary domain: %s' % current)

	if skip_replace:
		click.echo('- Skipping search-replace')
	else:
		click.echo('- Running search-replace')

		for sproto in ['https://', 'http://']:
			c.run(wp + shlex.join([
				'search-replace',
				sproto + current,
				proto + domain['name'],
				'--all-tables',
			]))

		# Flush object cache
		click.echo('- Flushing object cache')
		c.run(wp + 'cache flush')

	# Update config.json
	click.echo('- Updating .sail/config.json')
	for i, d in enumerate(config['domains']):
		config['domains'][i]['primary'] = d['name'] == domain['name']

	util.update_config(config)

	if config['namespace'] == 'default':
		click.echo('- Renaming droplet')
		droplet = digitalocean.Droplet(token=config['provider_token'], id=config['droplet_id'])
		droplet.rename(domain['name'])

	click.echo('- Primary domain updated successfully')

@domain.command()
@click.argument('domains', nargs=-1)
@click.option('--agree-tos', is_flag=True)
def make_https(domains, agree_tos):
	'''Request and install SSL certificates for domains'''
	root = util.find_root()
	config = util.config()

	if not agree_tos:
		click.echo('Let\'s Encrypt ToS: https://community.letsencrypt.org/tos')
		click.confirm('Do you agree to the Let\'s Encrypt ToS?', abort=True)

	if not domains:
		raise click.ClickException('At least one domain is required')

	groups = []
	domains, subdomains = _parse_domains(domains)

	click.echo('# Requesting and installing SSL for domains')

	for domain in domains + subdomains:
		if domain.fqdn not in [d['name'] for d in config['domains']]:
			raise click.ClickException('Domain %s does not exist, please add it first' % domain.fqdn)

	for domain in domains:
		if domain.fqdn not in groups:
			groups.append(domain.fqdn)

	for subdomain in subdomains:
		if subdomain.fqdn in groups or subdomain.registered_domain in groups:
			continue

		# Parent domain exists
		if subdomain.registered_domain in [d['name'] for d in config['domains']]:
			groups.append(subdomain.registered_domain)
		else:
			groups.append(subdomain.fqdn)

	c = util.connection()
	_doms, _subs = _parse_domains([d['name'] for d in config['domains'] if d['internal'] != True])

	for group in groups:
		names = []
		names.extend([d.fqdn for d in _doms if d.fqdn == group])
		names.extend([s.fqdn for s in _subs if s.registered_domain == group or s.fqdn == group])

		click.echo('- Generating Nginx config for %s' % group)
		c.put(io.StringIO(util.template('nginx.server.conf',
			{'server_names': names})),'/etc/nginx/conf.d/%s.conf' % group)

		click.echo('- Requesting SSL certificate for group %s' % group)
		args = ['certbot', '-n', '-m', config['email'], '--redirect', '--expand',
			'--agree-tos', '--nginx',
		]

		for name in names:
			args.append('-d')
			args.append(name)

		try:
			c.run(shlex.join(args))
		except Exception as e:
			util.dlog(e)
			raise click.ClickException('Could not obtain SSL certificate for %s. Use --debug for more info.' % group)

		# Update .sail/config.json
		for i, d in enumerate(config['domains']):
			if d['name'] in names:
				config['domains'][i]['https'] = True

		util.update_config(config)

	click.echo('- SSL certificates installed')
	click.echo('- Don\'t forget to: sail domain make-primary')

@domain.command()
@click.option('--skip-dns', is_flag=True, help='Do not add or update DNS records')
@click.argument('domains', nargs=-1)
def add(domains, skip_dns):
	'''Add a new domain, with DNS records pointing to your site'''
	config = util.config()

	if not domains:
		raise click.ClickException('At least one domain is required')

	domains, subdomains = _parse_domains(domains)

	click.echo('# Adding domains')

	# Add all domains and subs to config.json
	for domain in domains + subdomains:
		if domain.fqdn not in [d['name'] for d in config['domains']]:
			config['domains'].append({
				'name': domain.fqdn,
				'internal': False,
				'primary': False,
				'https': False,
			})

			util.update_config(config)
			click.echo('- Adding %s to .sail/config.json' % domain.fqdn)
		else:
			click.echo('- Domain %s already exists is .sail/config.json' % domain.fqdn)

	# Bail early if skipping
	if skip_dns:
		click.echo('- Skipping updating DNS records')
		return

	manager = digitalocean.Manager(token=config['provider_token'])
	existing = manager.get_all_domains()

	# Add or update real domains first.
	for domain in domains:
		if domain.fqdn not in [d.name for d in existing]:
			do_domain = digitalocean.Domain(
				token=config['provider_token'],
				name=domain.fqdn,
				ip_address=config['ip']
			)

			try:
				do_domain.create()
				existing.append(do_domain)
				click.echo('- Creating DNS zone and record for %s' % domain.fqdn)
			except:
				raise click.ClickException('- Could not create DNS zone for %s' % domain.fqdn)

			continue

		# DNS zone exists, try and update it
		click.echo('- Updating DNS records for %s' % domain.fqdn)
		do_domain = digitalocean.Domain(token=config['provider_token'], name=domain.fqdn)
		records = do_domain.get_records()
		exists = False

		for r in records:
			if r.name != '@' or r.type != 'A':
				continue

			if r.data == config['ip']:
				click.echo('- DNS record for %s exists and is correct' % domain.fqdn)
				exists = True
				continue

			# Delete the remaining records.
			r.destroy()
			click.echo('- Deleting DNS record for %s, incorrect existing record' % domain.fqdn)

		if not exists:
			click.echo('- Adding new DNS record for %s' % domain.fqdn)
			do_domain.create_new_domain_record(name='@', type='A', data=config['ip'])

	# Add all subdomains
	for subdomain in subdomains:
		# TODO: Add support for orphaned subdomains
		if subdomain.registered_domain not in [d.name for d in existing]:
			click.echo('- Skipping DNS for %s, zone not found' % subdomain.fqdn)
			continue

		do_domain = digitalocean.Domain(token=config['provider_token'], name=subdomain.registered_domain)
		records = do_domain.get_records()
		exists = False

		for r in records:
			if r.name != subdomain.subdomain or r.type not in ['A', 'CNAME']:
				continue

			if r.type == 'A' and r.data == config['ip']:
				click.echo('- Skipping DNS record for %s, existing record is correct' % subdomain.fqdn)
				exists = True
				continue

			# Delete the remaining records.
			r.destroy()
			click.echo('- Deleting DNS record for %s, incorrect exesting record' % subdomain.fqdn)

		if not exists:
			click.echo('- Adding new DNS record for %s' % subdomain.fqdn)
			do_domain.create_new_domain_record(name=subdomain.subdomain, type='A', data=config['ip'])

@domain.command()
@click.option('--skip-dns', is_flag=True, help='Do not delete DNS records')
@click.argument('domains', nargs=-1)
def delete(domains, skip_dns):
	'''Delete a domain and all DNS records'''
	config = util.config()

	if not domains:
		raise click.ClickException('At least one domain is required')

	domains, subdomains = _parse_domains(domains)

	click.echo('# Deleting domains')

	# Remove all domains and subs from config.json
	for domain in domains + subdomains:
		if domain.fqdn in [d['name'] for d in config['domains']]:
			config['domains'] = [d for d in config['domains'] if d['name'] != domain.fqdn]
			util.update_config(config)
			click.echo('- Deleting %s from .sail/config.json' % domain.fqdn)
		else:
			click.echo('- Domain %s does not exist in .sail/config.json' % domain.fqdn)

	# Bail early if skipping
	if skip_dns:
		click.echo('- Skipping updating DNS records')
		return

	manager = digitalocean.Manager(token=config['provider_token'])
	existing = manager.get_all_domains()

	# Remove subdomains first
	for subdomain in subdomains:
		if subdomain.registered_domain not in [d.name for d in existing]:
			click.echo('- Skipping DNS for %s, zone not found' % subdomain.fqdn)
			continue

		do_domain = digitalocean.Domain(token=config['provider_token'], name=subdomain.registered_domain)
		records = do_domain.get_records()
		exists = False

		for r in records:
			if r.name != subdomain.subdomain or r.type != 'A':
				continue

			if r.data == config['ip']:
				exists = True
				click.echo('- Deleting A record for %s' % subdomain.fqdn)
				r.destroy()

		if not exists:
			click.echo('- No A records to delete for %s' % subdomain.fqdn)

	# Remove domains
	for domain in domains:
		if domain.fqdn not in [d.name for d in existing]:
			click.echo('- Skipping DNS for %s, zone not found' % domain.fqdn)
			continue

		try:
			do_domain = digitalocean.Domain(token=config['provider_token'], name=domain.fqdn)
			do_domain.destroy()
			click.echo('- Deleting DNS zone for %s' % domain.fqdn)
		except:
			click.echo('- Could not delete DNS zone for %s' % domain.fqdn)

		_, _subs = _parse_domains([d['name'] for d in config['domains'] if d['internal'] != True])
		for _sub in _subs:
			if _sub.registered_domain == domain.fqdn:
				click.echo('- Deleting orphaned subdomain %s from .sail/config.json' % _sub.fqdn)
				config['domains'] = [d for d in config['domains'] if d['name'] != _sub.fqdn]
				util.update_config(config)

# Parse list into registered domains and subdomains
def _parse_domains(input_domains):
	subdomains = []
	domains = []

	for domain in input_domains:
		ex = tldextract.extract(domain, include_psl_private_domains=True)
		if not ex.domain or not ex.suffix:
			raise click.ClickException('Bad domain: %s' % domain)

		# No internal domains
		if ex.domain in ['sailed', 'justsailed'] and ex.suffix == 'io':
			raise click.ClickException('Bad domain: %s' % domain)

		if ex.subdomain:
			subdomains.append(ex)
			continue

		domains.append(ex)

	return domains, subdomains

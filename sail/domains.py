from sail import cli, util

import requests, json, os, subprocess, time, io
import click
import tldextract
import digitalocean
import urllib
import shlex
import re

@cli.group()
def domain():
	'''Add, remove and update domains associated with your site'''
	pass

@domain.command(name='list')
def listcmd():
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
			c.run(wp + util.join([
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

		click.echo('- Requesting SSL certificate for %s' % group)
		args = ['certbot', '-n', 'certonly', '-m', config['email'], '--agree-tos',
			'--standalone', '--http-01-port', '8088', '--expand',
		]

		for name in names:
			args.append('-d')
			args.append(name)

		try:
			c.run(util.join(args))
		except Exception as e:
			util.dlog(e)
			raise click.ClickException('Could not obtain SSL certificate for %s. Use --debug for more info.' % group)

		# Update .sail/config.json
		for i, d in enumerate(config['domains']):
			if d['name'] in names:
				config['domains'][i]['https'] = True

		util.update_config(config)

	_update_nginx_config()

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

	_update_nginx_config()

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
@click.option('--zone', is_flag=True, help='Force delete a DNS zone, even if other records exist in the zone.')
@click.argument('domains', nargs=-1)
def delete(domains, skip_dns, zone):
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

	_update_nginx_config()
	# TODO: Maybe delete SSL certs for this domain

	# Bail early if skipping
	if skip_dns:
		click.echo('- Skipping updating DNS records')
		return

	# Delete orphans if the entire zone is going to be deleted.
	if zone:
		for domain in domains:
			_, _subs = _parse_domains([d['name'] for d in config['domains'] if d['internal'] != True])
			for _sub in _subs:
				if _sub.registered_domain == domain.fqdn:
					click.echo('- Deleting orphaned subdomain %s from .sail/config.json' % _sub.fqdn)
					config['domains'] = [d for d in config['domains'] if d['name'] != _sub.fqdn]
					util.update_config(config)

	_delete_dns_records(domains, subdomains, force_delete_zones=zone)

def _delete_dns_records(domains, subdomains, force_delete_zones=False):
	config = util.config()
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
			records = do_domain.get_records()
			exists = False
			delete_zone = True

			if force_delete_zones:
				click.echo('- Deleting DNS zone for %s, forced' % domain.fqdn)
				do_domain.destroy()
				continue

			for r in records:
				if r.name == '@' and r.type == 'A' and r.data == config['ip']:
					exists = True
					click.echo('- Deleting A record for %s' % domain.fqdn)
					r.destroy()
					continue

				if r.name == '@' and r.type == 'NS':
					continue

				if r.name == '@' and r.type == 'SOA':
					continue

				# There are more records, don't delete the zone
				delete_zone = False

			if not exists:
				click.echo('- No A records to delete for %s' % domain.fqdn)

			if delete_zone:
				do_domain.destroy()
				click.echo('- Deleting DNS zone for %s' % domain.fqdn)
			else:
				click.echo('- Skipping deleting DNS zone for %s, other records exist' % domain.fqdn)
		except:
			click.echo('- Could not delete DNS zone for %s' % domain.fqdn)

def _update_nginx_config():
	config = util.config()
	domains = config['domains']
	c = util.connection()

	server_names = [d['name'] for d in domains]

	certificates = []
	https_names = []

	result = c.run('certbot certificates -n', warn=True)
	matches = re.findall(r'Certificate Name:.+?Private Key Path:.+?$', result.stdout, re.MULTILINE | re.DOTALL)
	for match in matches:
		cert = {}
		cert['name'] = re.search(r'Certificate Name: (.+)$', match, re.MULTILINE).group(1).strip()
		cert['cert'] = re.search(r'Certificate Path: (.+)$', match, re.MULTILINE).group(1).strip()
		cert['key'] = re.search(r'Private Key Path: (.+)$', match, re.MULTILINE).group(1).strip()

		domains = re.search(r'Domains: (.+)$', match, re.MULTILINE).group(1).strip()
		domains = domains.split(' ')
		cert['domains'] = []

		for domain in domains:
			if domain in server_names:
				cert['domains'].append(domain)

		if len(cert['domains']) < 1:
			continue

		certificates.append(cert)
		https_names.extend(cert['domains'])

	http_names = list(set(server_names).difference(set(https_names)))

	click.echo('- Generating nginx configuration')
	c.put(io.StringIO(util.template('nginx.server.conf', {
		'certificates': certificates,
		'https_names': https_names,
		'http_names': http_names,
		'root': util.remote_path('/public'),
	})),'/etc/nginx/conf.d/%s.conf' % config['namespace'])

	c.run('systemctl reload nginx')

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

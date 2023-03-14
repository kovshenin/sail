from sail import cli, util

import requests, json, os, subprocess, time, io, re
import click
import tldextract
import digitalocean
import urllib, pathlib, hashlib, shutil
import shlex

from datetime import datetime

@cli.group()
def domain():
	'''Add, remove and update domains associated with your site'''
	pass

@domain.command(name='list')
@click.option('--json', 'as_json', is_flag=True, help='Get list of domains as JSON')
def listcmd(as_json):
	'''List domains associated with your site'''
	config = util.config()

	if as_json:
		click.echo(json.dumps(config['domains']))
		return

	util.heading('Domains')
	click.echo()

	for domain in config['domains']:
		flags = []
		for flag in ['internal', 'https', 'primary']:
			if domain.get(flag, None):
				flags.append(flag)

		sflags = ''
		if flags:
			sflags = ' (%s)' % ', '.join(flags)

		click.echo('  ' + domain['name'] + sflags)

	click.echo()

@domain.command()
@click.argument('domain', nargs=1)
@click.option('--force', is_flag=True, help='Make primary again, even if the domain is already set as the primary one')
@click.option('--skip-replace', is_flag=True, help='Skip running search-replace routines for home, siteurl, and other URLs')
def make_primary(domain, force, skip_replace):
	'''Set a domain as primary, update siteurl/home, search-replace all links'''
	config = util.config()

	util.heading('Updating primary domain')

	if domain not in [d['name'] for d in config['domains']]:
		raise util.SailException('Can not make primary, domain does not exist')

	domain = [d for d in config['domains'] if d['name'] == domain][0]
	if domain['primary'] and not force:
		raise util.SailException('Domain %s already set as primary. Use --force to force' % domain['name'])

	c = util.connection()
	wp = 'sudo -u www-data wp --path=%s --skip-themes --skip-plugins ' % util.remote_path('/public/')

	home = c.run(wp + 'option get home').stdout.strip()
	current = urllib.parse.urlparse(home).netloc
	proto = 'https://' if domain['https'] else 'http://'
	util.item('Current primary domain: %s' % current)

	if skip_replace:
		util.item('Skipping search-replace')
	else:
		util.item('Running search-replace')

		for sproto in ['https://', 'http://']:
			c.run(wp + util.join([
				'search-replace',
				sproto + current,
				proto + domain['name'],
				'--all-tables',
			]))

		# Flush object cache
		util.item('Flushing object cache')
		c.run(wp + 'cache flush')

	# Update config.json
	util.item('Updating .sail/config.json')
	for i, d in enumerate(config['domains']):
		config['domains'][i]['primary'] = d['name'] == domain['name']

	util.update_config(config)

	if config['namespace'] == 'default':
		util.item('Renaming droplet')
		droplet = digitalocean.Droplet(token=config['provider_token'], id=config['droplet_id'])
		droplet.rename(domain['name'])

	util.success('Primary domain updated successfully')

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
		raise util.SailException('At least one domain is required')

	domains, subdomains = _parse_domains(domains)

	util.heading('Requesting and installing SSL for domains')

	for domain in domains + subdomains:
		if domain.fqdn not in [d['name'] for d in config['domains']]:
			raise util.SailException('Domain %s does not exist, please add it first' % domain.fqdn)

	groups = _get_groups(domains, subdomains)

	c = util.connection()
	_doms, _subs = _parse_domains([d['name'] for d in config['domains'] if d['internal'] != True])

	for group in groups:
		names = []
		names.extend([d.fqdn for d in _doms if d.fqdn == group])
		names.extend([s.fqdn for s in _subs if s.registered_domain == group or s.fqdn == group])

		util.item('Requesting certificate for %s' % group)
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
			raise util.SailException('Could not obtain SSL certificate for %s. Use --debug for more info.' % group)

		# Update .sail/config.json
		for i, d in enumerate(config['domains']):
			if d['name'] in names:
				config['domains'][i]['https'] = True

		util.update_config(config)

	util.item('Generating nginx configuration')
	_update_nginx_config()

	util.success('SSL certificates installed. Don\'t forget to: sail domain make-primary')

@domain.command()
@click.option('--skip-dns', is_flag=True, help='Do not add or update DNS records')
@click.argument('domains', nargs=-1)
def add(domains, skip_dns, quiet_success=False):
	'''Add a new domain, with DNS records pointing to your site'''
	config = util.config()

	if not domains:
		raise util.SailException('At least one domain is required')

	domains, subdomains = _parse_domains(domains)

	util.heading('Adding domains')

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
			util.item('Adding %s to .sail/config.json' % domain.fqdn)
		else:
			util.item('Domain %s already exists is .sail/config.json' % domain.fqdn)

	util.item('Generating nginx configuration')
	_update_nginx_config()

	# Bail early if skipping
	if skip_dns:
		util.item('Skipping updating DNS records')
		util.success('Domain name added')
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
				util.item('Creating DNS zone and record for %s' % domain.fqdn)
			except:
				raise util.SailException('- Could not create DNS zone for %s' % domain.fqdn)

			continue

		# DNS zone exists, try and update it
		util.item('Updating DNS records for %s' % domain.fqdn)
		do_domain = digitalocean.Domain(token=config['provider_token'], name=domain.fqdn)
		records = do_domain.get_records()
		exists = False

		for r in records:
			if r.name != '@' or r.type != 'A':
				continue

			if r.data == config['ip']:
				util.item('DNS record for %s exists and is correct' % domain.fqdn)
				exists = True
				continue

			# Delete the remaining records.
			r.destroy()
			util.item('Deleting DNS record for %s, incorrect existing record' % domain.fqdn)

		if not exists:
			util.item('Adding new DNS record for %s' % domain.fqdn)
			do_domain.create_new_domain_record(name='@', type='A', data=config['ip'])

	# Add all subdomains
	for subdomain in subdomains:
		# TODO: Add support for orphaned subdomains
		if subdomain.registered_domain not in [d.name for d in existing]:
			util.item('Skipping DNS for %s, zone not found' % subdomain.fqdn)
			continue

		do_domain = digitalocean.Domain(token=config['provider_token'], name=subdomain.registered_domain)
		records = do_domain.get_records()
		exists = False

		for r in records:
			if r.name != subdomain.subdomain or r.type not in ['A', 'CNAME']:
				continue

			if r.type == 'A' and r.data == config['ip']:
				util.item('Skipping DNS record for %s, existing record is correct' % subdomain.fqdn)
				exists = True
				continue

			# Delete the remaining records.
			r.destroy()
			util.item('Deleting DNS record for %s, incorrect exesting record' % subdomain.fqdn)

		if not exists:
			util.item('Adding new DNS record for %s' % subdomain.fqdn)
			do_domain.create_new_domain_record(name=subdomain.subdomain, type='A', data=config['ip'])

	# Can be invoked from another context, avoid blending multiple
	# success messages together.
	if not quiet_success:
		util.success('Domain name(s) added')

@domain.command()
@click.option('--skip-dns', is_flag=True, help='Do not delete DNS records')
@click.option('--zone', is_flag=True, help='Force delete a DNS zone, even if other records exist in the zone.')
@click.argument('domains', nargs=-1)
def delete(domains, skip_dns, zone):
	'''Delete a domain and all DNS records'''
	config = util.config()

	if not domains:
		raise util.SailException('At least one domain is required')

	domains, subdomains = _parse_domains(domains)

	util.heading('Deleting domains')

	# Remove all domains and subs from config.json
	for domain in domains + subdomains:
		if domain.fqdn in [d['name'] for d in config['domains']]:
			config['domains'] = [d for d in config['domains'] if d['name'] != domain.fqdn]
			util.update_config(config)
			util.item('Deleting %s from .sail/config.json' % domain.fqdn)
		else:
			util.item('Domain %s does not exist in .sail/config.json' % domain.fqdn)

	util.item('Generating nginx configuration')
	_update_nginx_config()
	# TODO: Maybe delete SSL certs for this domain

	# Bail early if skipping
	if skip_dns:
		util.item('Skipping updating DNS records')
		util.success('Domain deleted')
		return

	# Delete orphans if the entire zone is going to be deleted.
	if zone:
		for domain in domains:
			_, _subs = _parse_domains([d['name'] for d in config['domains'] if d['internal'] != True])
			for _sub in _subs:
				if _sub.registered_domain == domain.fqdn:
					util.item('Deleting orphaned subdomain %s from .sail/config.json' % _sub.fqdn)
					config['domains'] = [d for d in config['domains'] if d['name'] != _sub.fqdn]
					util.update_config(config)

	_delete_dns_records(domains, subdomains, force_delete_zones=zone)

	util.success('Domain deleted')

@domain.command()
def export():
	'''Export domain configuration and SSL certificates to a local archive.'''
	root = util.find_root()
	config = util.config()
	c = util.connection()

	rsync_args = ['-rtl']
	backups_dir = pathlib.Path(root + '/.backups')
	backups_dir.mkdir(parents=True, exist_ok=True)
	filename = datetime.now().strftime('%Y-%m-%d-%H%M%S.domains.tar.gz')
	target = pathlib.Path(backups_dir / filename)

	progress_dir = pathlib.Path(backups_dir / ('.%s.progress' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]))
	progress_dir.mkdir()
	(progress_dir / 'live').mkdir()
	(progress_dir / 'renewal').mkdir()

	# Get all non-internal domains, split into registered domains and subdomains.
	# Then split into groups as this is how we register them with Certbot.
	domains = [d for d in config['domains'] if not d['internal']]
	_domains, _subdomains = _parse_domains([d['name'] for d in domains])
	groups = _get_groups(_domains, _subdomains)

	if len(domains) < 1 or len(groups) < 1:
		raise util.SailException('Could not find any domains to export.')

	util.heading('Exporting domains')

	# Available certificates.
	certs = c.run('ls /etc/letsencrypt/live/').stdout.split()

	for group in groups:
		if not group in certs:
			util.item('Skipping group without certificate: %s' % group)
			continue

		# Copy certificates and renewal configuration for group.
		util.item('Copying /etc/letsencrypt/live/%s' % group)

		source = 'root@%s:/etc/letsencrypt/live/%s' % (config['hostname'], group)
		destination = '%s/live/' % progress_dir
		returncode, stdout, stderr = util.rsync(rsync_args, source, destination, default_filters=False)

		if returncode != 0:
			shutil.rmtree(progress_dir)
			raise util.SailException('An error occurred during export. Please try again.')

		util.item('Copying /etc/letsencrypt/renewal/%s.conf' % group)

		source = 'root@%s:/etc/letsencrypt/renewal/%s.conf' % (config['hostname'], group)
		destination = '%s/renewal/' % progress_dir
		returncode, stdout, stderr = util.rsync(rsync_args, source, destination, default_filters=False)

		if returncode != 0:
			shutil.rmtree(progress_dir)
			raise util.SailException('An error occurred during export. Please try again.')

	# The account is configured in renewals so make sure to bring it over.
	util.item('Copying /etc/letsencrypts/accounts')

	source = 'root@%s:/etc/letsencrypt/accounts' % config['hostname']
	destination = '%s/' % progress_dir
	returncode, stdout, stderr = util.rsync(rsync_args, source, destination, default_filters=False)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred during export. Please try again.')

	# Dump domains configuration to a JSON file.
	util.item('Writing configuration to domains.json')
	with open('%s/domains.json' % progress_dir, 'w+') as f:
		json.dump(domains, f, indent='\t')

	util.item('Archiving and compressing files')

	p = subprocess.Popen([
		'tar', ('-cvzf' if util.debug() else '-czf'), target.resolve(), '-C', progress_dir.resolve(), '.'
	])

	while p.poll() is None:
		pass

	if p.returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred during export. Please try again.')

	shutil.rmtree(progress_dir)

	util.success('Export completed at .backups/%s' % filename)

@domain.command(name='import')
@click.argument('path', nargs=1, required=True)
@click.pass_context
def import_cmd(ctx, path):
	'''Import domains and SSL certificates from an export archive.'''
	root = util.find_root()
	config = util.config()
	c = util.connection()

	path = pathlib.Path(path).resolve()
	if not path.exists():
		raise util.SailException('File does not exist')

	if not path.name.endswith('.domains.tar.gz'):
		raise util.SailException('This does not look like a .domains.tar.gz file')

	util.heading('Importing domains and SSL certificates')

	rsync_args = ['-rtl']
	backups_dir = pathlib.Path(root + '/.backups')
	backups_dir.mkdir(parents=True, exist_ok=True)
	progress_dir = pathlib.Path(backups_dir / ('.%s.progress' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]))
	progress_dir.mkdir()

	util.item('Extracting domain export files')

	p = subprocess.Popen([
		'tar', ('-xzvf' if util.debug() else '-xzf'), path.resolve(), '--directory', progress_dir.resolve()
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred during backup. Please try again.')

	for x in progress_dir.iterdir():
		if x.name not in ['domains.json', 'live', 'renewal', 'accounts']:
			shutil.rmtree(progress_dir)
			raise util.SailException('Unexpected file in domains export: %s' % x.name)

	util.item('Reading domains.json configuration')
	with open('%s/domains.json' % progress_dir, 'r') as f:
		domains = json.load(f)

	_domains, _subdomains = _parse_domains([d['name'] for d in domains])
	groups = _get_groups(_domains, _subdomains)
	certs = [i.name for i in (progress_dir / 'live').iterdir()]

	for group in groups:
		if not group in certs:
			util.item('Skipping group without certificate: %s' % group)
			continue

		# Copy certificates and renewal configuration for group.
		util.item('Writing /etc/letsencrypt/live/%s' % group)

		source = '%s/live/%s' % (progress_dir, group)
		destination = 'root@%s:/etc/letsencrypt/live/%s' % (config['hostname'], group)
		returncode, stdout, stderr = util.rsync(rsync_args, source, destination, default_filters=False)

		if returncode != 0:
			shutil.rmtree(progress_dir)
			raise util.SailException('An error occurred during import. Please try again.')

		util.item('Writing /etc/letsencrypt/renewal/%s.conf' % group)

		source = '%s/renewal/%s.conf' % (progress_dir, group)
		destination = 'root@%s:/etc/letsencrypt/renewal/%s.conf' % (config['hostname'], group)
		returncode, stdout, stderr = util.rsync(rsync_args, source, destination, default_filters=False)

		if returncode != 0:
			shutil.rmtree(progress_dir)
			raise util.SailException('An error occurred during import. Please try again.')

	util.item('Writing /etc/letsencrypts/accounts')
	source = '%s/accounts' % progress_dir
	destination = 'root@%s:/etc/letsencrypt/accounts' % config['hostname']
	returncode, stdout, stderr = util.rsync(rsync_args, source, destination, default_filters=False)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred during import. Please try again.')

	names = [d['name'] for d in domains]
	ctx.invoke(add, domains=names, quiet_success=True)

	util.heading('Cleaning up')

	# The add command will set https to False by default for any
	# new domains, but we may have existing SSL certificates for these.
	util.item('Setting HTTPS flags')
	https_names = [d['name'] for d in domains if d['https']]
	config = util.config()
	config_modified = False

	for i, domain in enumerate(config['domains']):
		if not domain['https'] and domain['name'] in https_names:
			config['domains'][i]['https'] = True
			config_modified = True

	if config_modified:
		util.update_config(config)

	# TODO: Invoke make_primary if current primary is internal.

	util.item('Removing temporary files')
	shutil.rmtree(progress_dir)

	util.success('Domains and SSL certificates have been imported.')

def _delete_dns_records(domains, subdomains, force_delete_zones=False):
	config = util.config()
	manager = digitalocean.Manager(token=config['provider_token'])
	existing = manager.get_all_domains()

	# Remove subdomains first
	for subdomain in subdomains:
		if subdomain.registered_domain not in [d.name for d in existing]:
			util.item('Skipping DNS for %s, zone not found' % subdomain.fqdn)
			continue

		do_domain = digitalocean.Domain(token=config['provider_token'], name=subdomain.registered_domain)
		records = do_domain.get_records()
		exists = False

		for r in records:
			if r.name != subdomain.subdomain or r.type != 'A':
				continue

			if r.data == config['ip']:
				exists = True
				util.item('Deleting A record for %s' % subdomain.fqdn)
				r.destroy()

		if not exists:
			util.item('No A records to delete for %s' % subdomain.fqdn)

	# Remove domains
	for domain in domains:
		if domain.fqdn not in [d.name for d in existing]:
			util.item('Skipping DNS for %s, zone not found' % domain.fqdn)
			continue

		try:
			do_domain = digitalocean.Domain(token=config['provider_token'], name=domain.fqdn)
			records = do_domain.get_records()
			exists = False
			delete_zone = True

			if force_delete_zones:
				util.item('Deleting DNS zone for %s, forced' % domain.fqdn)
				do_domain.destroy()
				continue

			for r in records:
				if r.name == '@' and r.type == 'A' and r.data == config['ip']:
					exists = True
					util.item('Deleting A record for %s' % domain.fqdn)
					r.destroy()
					continue

				if r.name == '@' and r.type == 'NS':
					continue

				if r.name == '@' and r.type == 'SOA':
					continue

				# There are more records, don't delete the zone
				delete_zone = False

			if not exists:
				util.item('No A records to delete for %s' % domain.fqdn)

			if delete_zone:
				do_domain.destroy()
				util.item('Deleting DNS zone for %s' % domain.fqdn)
			else:
				util.item('Skipping deleting DNS zone for %s, other records exist' % domain.fqdn)
		except:
			util.item('Could not delete DNS zone for %s' % domain.fqdn)

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
			raise util.SailException('Bad domain: %s' % domain)

		# No internal domains
		if ex.domain in ['sailed', 'justsailed'] and ex.suffix == 'io':
			raise util.SailException('Bad domain: %s' % domain)

		if ex.subdomain:
			subdomains.append(ex)
			continue

		domains.append(ex)

	return domains, subdomains

def _get_groups(domains, subdomains):
	'''Returns a list of domains and subdomains grouped by their registered domain (if any)'''
	config = util.config()
	groups = []

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

	return groups
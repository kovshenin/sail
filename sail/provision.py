from sail import cli, util, deploy, domains, blueprints, cron, __version__

import sail
import json
import subprocess, os
import click
import shutil
import digitalocean
import re, secrets, string
import shlex, time, io, pathlib, jinja2
import packaging.version

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from prettytable import PrettyTable

@cli.command()
@click.option('--provider-token', help='Your DigitalOcean API token, must be read-write. You can set a default token with: sail config provider-token <token>')
@click.option('--size', default='s-1vcpu-1gb-intel', help='The Droplet size, defaults to s-1vcpu-1gb-intel. To get a full list of available sizes and pricing run: sail sizes')
@click.option('--region', default='ams3', help='The region to deploy to, defaults to ams3. For a full list of available regions run: sail regions')
@click.option('--email', help='The admin e-mail address. You can set the default e-mail address with: sail config email <email>')
@click.option('--namespace', default='default', help='The namespace to use for the new application')
@click.option('--environment', help='Initialize the application into an existing environment')
@click.option('--blueprint', 'blueprint', default='default.yaml', help='Apply a blueprint after init, defaults to: default.yaml')
@click.option('--force', '-f', is_flag=True)
@click.pass_context
def init(ctx, provider_token, email, size, region, force, namespace, environment, blueprint):
	'''Initialize and provision a new project'''
	root = util.find_root()

	if root and os.path.exists(root + '/.sail'):
		raise util.SailException('This ship has already sailed. Pick another one or remove the .sail directory.')

	files = os.listdir(path='.')
	if files and not force:
		raise util.SailException('This project directory is not empty, can not init here. Override with --force, can destroy existing files.')

	if namespace and not re.match(r'^[a-zA-Z0-9_.-]+$', namespace):
		raise util.SailException('Invalid namespace. Namespaces can be alpha-numeric and contain the following characters: _.-')

	namespace = namespace.lower()

	if environment:
		environment = pathlib.Path(environment) / '.sail'
		if not environment.is_dir():
			raise util.SailException('Not a valid Sail environment: %s' % environment.resolve())

		if not (environment / 'config.json').is_file():
			raise util.SailException('Not a valid Sail environment: %s' % environment.resolve())

		if not (environment / 'ssh.key').is_file() or not (environment / 'ssh.key.pub').is_file():
			raise util.SailException('Could not read SSH keys from: %s' % environment.resolve())

		with (environment / 'config.json').open('r') as f:
			env_config = json.load(f)

		if packaging.version.parse(env_config.get('version')) < packaging.version.parse('0.10.0'):
			raise util.SailException('The target environment version is lower than the supported minimum. Please upgrade the environment first.')

		if env_config.get('namespace', 'default').lower() == namespace:
			raise util.SailException('The "%s" namespace is already in use in the target environment. Please use a different namespace.' % namespace)

		if not env_config.get('provider_token'):
			raise util.SailException('Could not find a provider token in the target environment.')

		# Force the same provider token
		provider_token = env_config.get('provider_token')

	if not provider_token:
		provider_token = util.get_sail_default('provider-token')

	if not provider_token:
		raise util.SailException('You need to provide a DigitalOcean API token with --provider-token, or set a default one with: sail config provider-token <token>')

	# Make sure the provider token works
	try:
		account = digitalocean.Account(token=provider_token)
		account.load()
		if account.status != 'active':
			raise util.SailException('This DigitalOcean account is not active.')
		if not account.email_verified:
			raise util.SailException('This DigitalOcean account e-mail is not verified.')
	except:
		raise util.SailException('Invalid prodiver token.')

	if not email:
		email = util.get_sail_default('email')

	if not email:
		raise util.SailException('You need to provide an admin e-mail address with --email, or set a default one with: sail config email <e-mail>')

	util.heading('Initializing')

	response = util.request('/init/', json={
		'email': email,
		'version': __version__,
	}, anon=True)

	app_id = response['app_id']
	secret = response['secret']
	hostname = response['hostname']

	util.item('Claimed application id: %s' % app_id)

	os.mkdir('.sail')
	root = util.find_root()

	util.item('Writing .sail/config.json')
	config = {
		'app_id': app_id,
		'secret': secret,
		'hostname': hostname,
		'provider_token': provider_token,
		'email': email,
		'domains': [],
		'profile_key': ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(32)),
		'namespace': namespace,
		'version': __version__,
	}

	if environment:
		config['profile_key'] = env_config['profile_key']
		config['ip'] = env_config['ip']
		config['droplet_id'] = env_config['droplet_id']
		config['key_id'] = env_config['key_id']

	util.update_config(config)

	passwords = {}
	for key in ['mysql', 'wp']:
		passwords[key] = ''.join(secrets.choice(string.ascii_letters
			+ string.digits) for i in range(48))

	# Provision a new environment or copy existing
	if not environment:
		_provision(provider_token, size, region)
		_configure()
	else:
		_copy_environment(environment)

	# Run the installs
	_install(passwords)

	# Add the default WP cron schedule.
	ctx.invoke(cron.add, schedule='*/5', command=('wp cron event run --due-now',), quiet=True)

	# Run a default blueprint
	if blueprint and blueprint != 'no' and blueprint != 'none':
		try:
			ctx.invoke(blueprints.blueprint, path=[blueprint], doing_init=True)
		except:
			util.item('Could not apply blueprint')

	# Download files from production
	ctx.invoke(deploy.download, yes=True, doing_init=True)

	# Create a local empty wp-contents/upload directory
	content_dir = '%s/wp-content/uploads' % root
	if not os.path.exists(content_dir):
		os.mkdir(content_dir)

	primary_url = util.primary_url()

	# Automatically enable premium if it's been set up
	premium_license = util.get_sail_default('premium')
	premium_email = util.get_sail_default('email')
	if premium_license and premium_email:
		try:
			ctx.invoke(sail.premium.enable, doing_init=True)
		except:
			util.item('Could not initialize Premium')

	util.heading('Initialization successful')
	util.item('The ship has sailed!')
	click.echo()

	util.label_width(10)

	label = util.label('URL:')
	click.echo(f'{label} {primary_url}')

	label = util.label('Login:')
	click.echo(f'{label} {primary_url}/wp-login.php')

	label = util.label('Username:')
	click.echo(f'{label} {email}')

	label = util.label('Password:')
	password = passwords['wp']
	click.echo(f'{label} {password}')

	click.echo()

	label = util.label('SSH Host:')
	hostname = config['hostname']
	click.echo(f'{label} {hostname}')

	label = util.label('SSH Port:')
	click.echo(f'{label} 22')

	label = util.label('Username:')
	click.echo(f'{label} root')

	label = util.label('SSH Key:')
	click.echo(f'{label} .sail/ssh.key')

	label = util.label('App root:')
	app_root = util.remote_path()
	click.echo(f'{label} {app_root}')

	click.echo()
	click.echo('To open an interactive shell run: sail ssh')
	click.echo('For support and documentation visit sailed.io')
	click.echo()

def _copy_environment(environment):
	root = util.find_root()
	config = util.config()

	util.item('Copying environment')

	shutil.copy(environment / 'ssh.key', '%s/.sail/ssh.key' % root)
	os.chmod('%s/.sail/ssh.key' % root, 0o600)
	shutil.copy(environment / 'ssh.key.pub', '%s/.sail/ssh.key.pub' % root)
	os.chmod('%s/.sail/ssh.key.pub' % root, 0o644)

	util.item('Requesting DNS record')
	response = util.request('/ip/', json={
		'ip': config['ip'],
	})

	util.item('Checking SSH connection')
	c = util.connection()

	try:
		c.run('hostname')
	except Exception as e:
		raise e
		raise util.SailException('Could not connect via SSH. Make sure the environment is healthy.')

	try:
		remote_config = json.loads(c.run('cat /etc/sail/config.json').stdout)
	except:
		raise util.SailException('Could not read /etc/sail/config.json')

	if not remote_config.get('namespaces'):
		raise util.SailException('Could not find any namespaces data in the remote config. This environment looks broken.')

	# Make sure our new namespace is unique
	if config['namespace'] in remote_config['namespaces']:
		raise util.SailException('The "%s" namespace already exists in this environment.' % config['namespace'])

	remote_config['namespaces'].append(config['namespace'])
	c.put(io.StringIO(json.dumps(remote_config)), '/etc/sail/config.json')

	util.item('Writing server keys to .sail/known_hosts')
	with open('%s/.sail/known_hosts' % root, 'w+') as f:
		r = subprocess.run(['ssh-keyscan', '-t', 'rsa,ecdsa', '-H', config['ip'],
			config['hostname']], stdout=f, stderr=subprocess.DEVNULL)

def _provision(provider_token, size, region):
	root = util.find_root()
	config = util.config()

	util.item('Provisioning servers')

	# Generate a key pair.
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	private_key = key.private_bytes(
		serialization.Encoding.PEM,
		serialization.PrivateFormat.TraditionalOpenSSL,
		serialization.NoEncryption()
	).decode('utf8')

	public_key = key.public_key().public_bytes(
		serialization.Encoding.OpenSSH,
		serialization.PublicFormat.OpenSSH
	).decode('utf8')

	util.item('Writing SSH keys to .sail/ssh.key')
	with open('%s/.sail/ssh.key' % root, 'w+') as f:
		f.write(private_key)
	os.chmod('%s/.sail/ssh.key' % root, 0o600)

	with open('%s/.sail/ssh.key.pub' % root, 'w+') as f:
		f.write(public_key)
	os.chmod('%s/.sail/ssh.key.pub' % root, 0o644)

	util.item('Uploading SSH key to DigitalOcean')

	key = digitalocean.SSHKey(
		token=provider_token,
		name=config['app_id'],
		public_key=public_key
	)

	try:
		key.create()
		key.load()
	except Exception as e:
		print(e)
		raise util.SailException('Could not upload SSH key. Make sure token is RW.')

	util.item('Creating a new Droplet')

	with open(sail.TEMPLATES_PATH + '/cloud-config.yaml', 'r') as f:
		cloud_config = f.read()

	droplet = digitalocean.Droplet(
		token=provider_token,
		name=config['hostname'],
		region=region,
		image=sail.DEFAULT_IMAGE,
		size_slug=size,
		monitoring=True,
		ssh_keys=[key.id],
		backups=False,
		user_data=cloud_config
	)

	try:
		droplet.create()
	except Exception as e:
		raise util.SailException('Cloud not create new droplet. Please try again later.')

	util.item('Waiting for Droplet to boot')

	completed = False
	while not completed:
		time.sleep(3)
		actions = droplet.get_actions()
		for action in actions:
			action.load()
			if 'completed' == action.status:
				completed = True
				break

	util.item('Waiting for IP address')

	def wait_for_ip():
		droplet.load()
		if droplet.ip_address:
			return True
		return False

	util.wait(wait_for_ip, timeout=120, interval=10)

	util.item('Droplet up and running, requesting DNS record')
	response = util.request('/ip/', json={
		'ip': droplet.ip_address,
	})

	config['ip'] = droplet.ip_address
	config['droplet_id'] = droplet.id
	config['key_id'] = key.id
	util.update_config(config)

	util.item('Waiting for SSH')
	c = util.connection()

	def wait_for_ssh():
		try:
			c.run('hostname')
			return True
		except Exception as e:
			util.dlog(repr(e))
			return False

	util.wait(wait_for_ssh, timeout=120, interval=10)

	util.item('Writing server keys to .sail/known_hosts')
	with open('%s/.sail/known_hosts' % root, 'w+') as f:
		r = subprocess.run(['ssh-keyscan', '-t', 'rsa,ecdsa', '-H', config['ip'],
			config['hostname']], stdout=f, stderr=subprocess.DEVNULL)

def _configure():
	config = util.config()
	c = util.connection()

	util.item('Configuring software')

	# Generate an /etc/sail/config.json
	config_json = {
		'app_id': config['app_id'],
		'profile_key': config['profile_key'],
		'namespaces': [config['namespace']],
	}

	c.run('mkdir /etc/sail')
	c.put(io.StringIO(json.dumps(config_json)), '/etc/sail/config.json')

	def wait_for_cloud_init():
		try:
			r = c.run('cloud-init status -l')
			return 'status: done' in r.stdout
		except:
			pass

		return False

	util.item('Waiting for cloud-init to complete')
	util.wait(wait_for_cloud_init, timeout=900, interval=10)

	c.run('mkdir -p /etc/nginx/conf.d/extras')
	c.put(sail.TEMPLATES_PATH + '/nginx.main.conf', '/etc/nginx/nginx.conf')
	c.put(sail.TEMPLATES_PATH + '/nginx.shared.conf', '/etc/nginx/conf.d/extras/sail.conf')
	c.put(sail.TEMPLATES_PATH + '/nginx.certbot.conf', '/etc/nginx/conf.d/extras/certbot.conf')
	c.put(sail.TEMPLATES_PATH + '/prepend.php', '/etc/sail/prepend.php')
	c.put(sail.TEMPLATES_PATH + '/php.ini', '/etc/php/7.4/fpm/php.ini')
	c.put(sail.TEMPLATES_PATH + '/php.ini', '/etc/php/7.4/cli/php.ini')

	# Make sure certbot.conf is in action.
	c.run('systemctl reload nginx')

	# Get xhprof
	c.run('curl -L https://github.com/kovshenin/xhprof/releases/download/0.10.2-sail/xhprof.so.gz -o /tmp/xhprof.so.gz')
	c.run('gunzip /tmp/xhprof.so.gz && mv /tmp/xhprof.so /usr/lib/php/20190902/xhprof.so')

	# Get dhparams
	c.run('curl -L https://raw.githubusercontent.com/certbot/certbot/4abd81e2186eddc67551d61a8260440bd177d18d/certbot/certbot/ssl-dhparams.pem -o /etc/nginx/conf.d/extras/ssl-dhparams.pem')

	# Permissions
	c.run('chown -R www-data. /var/www')

def _install(passwords):
	config = util.config()
	c = util.connection()

	# Request an SSL cert
	util.item('Requesting SSL certificate')

	retry = 3
	https = False
	while retry:
		retry -= 1
		try:
			c.run('certbot -n certonly --register-unsafely-without-email --agree-tos --standalone --http-01-port 8088 -d %s' % config['hostname'])
			https = True
			break
		except:
			if retry:
				util.item('Certbot failed, retrying')
				time.sleep(10)
			else:
				util.item('Certbot failed, skipping SSL')

	# Update the domains config.
	config['domains'].append({
		'name': config['hostname'],
		'internal': True,
		'https': https,
		'primary': True
	})
	util.update_config(config)

	# Update nginx configs with cert data.
	util.item('Generating nginx configuration')
	domains._update_nginx_config()

	# Prepare release directories
	remote_path = util.remote_path()
	c.run('mkdir -p %s/releases/1337' % remote_path)
	c.run('mkdir -p %s/uploads' % remote_path)
	c.run('mkdir -p %s/profiles' % remote_path)
	c.run('chown -R www-data. %s' % remote_path)

	# Create a MySQL database
	util.item('Setting up the MySQL database')

	c.run('mysql -e "CREATE DATABASE \\`wordpress_%s\\`;"' % config['namespace'])
	c.run('mysql -e "CREATE USER \\`wordpress_%s\\`@localhost IDENTIFIED BY \'%s\'"' % (config['namespace'], passwords['mysql']))
	c.run('mysql -e "GRANT ALL PRIVILEGES ON \\`wordpress_%s\\`.* TO \\`wordpress_%s\\`@localhost;"' % (config['namespace'], config['namespace']))

	util.item('Downloading and installing WordPress')
	wp = 'sudo -u www-data wp --path=%s/releases/1337 ' % remote_path

	c.run(wp + 'core download')
	c.run(wp + util.join([
		'config', 'create',
		'--dbname=wordpress_%s' % config['namespace'],
		'--dbuser=wordpress_%s' % config['namespace'],
		'--dbpass=%s' % passwords['mysql']
	]))
	c.run(wp + util.join([
		'core', 'install',
		'--url=%s' % util.primary_url(),
		'--title=Sailed',
		'--admin_user=%s' % config['email'],
		'--admin_password=%s' % passwords['wp'],
		'--admin_email=%s' % config['email'],
		'--skip-email'
	]))
	c.run(wp + util.join([
		'rewrite', 'structure', '/%postname%/'
	]))

	# Disable standard wp-cron (will spawn via system cron).
	c.run(wp + util.join([
		'config', 'set', 'DISABLE_WP_CRON', 'true', '--raw'
	]))

	# Run any outstanding events (like the cron check).
	c.run(wp + util.join([
		'cron', 'event', 'run', '--due-now'
	]))

	# Do da deploy.
	util.item('Cleaning up')
	c.run('rm -rf %s/public' % remote_path)
	c.run('ln -sfn %s/releases/1337 %s/public' % (remote_path, remote_path))
	c.run('rm -rf %s/public/wp-content/uploads && ln -sfn %s/uploads %s/public/wp-content/uploads' % (
		remote_path, remote_path, remote_path))

	# Reload services
	c.run('systemctl reload nginx.service')
	c.run('systemctl reload php7.4-fpm.service')

@cli.command()
@click.option('--yes', '-y', is_flag=True, help='Force yes on the are-you-sure prompt')
@click.option('--environment', is_flag=True, help='Force destroy environment, even if other namespaces exist')
@click.option('--skip-dns', is_flag=True, help='Do not attempt to delete DNS records for associated domains')
def destroy(yes, environment, skip_dns):
	'''Destroy an application namespace and/or the environment'''
	root = util.find_root()
	config = util.config()

	if not yes:
		click.confirm('All application data will be scrubbed and irretrievable. Are you sure?', abort=True)

	util.heading('Destroying application')

	namespaces = []
	try:
		c = util.connection()
		remote_config = json.loads(c.run('cat /etc/sail/config.json').stdout)
		namespaces = remote_config.get('namespaces', [])
	except:
		pass

	# It's the only namespace, destoy the environment
	if len(namespaces) < 1 or namespaces == [config['namespace']]:
		environment = True
	elif not environment and config['namespace'] == 'default':
		raise util.SailException('You asked to destroy the default namespace, but other namespaces exist in this environment. Use --environment to destroy the entire environment.')

	try:
		util.item('Releasing .justsailed.io subdomain')
		data = util.request('/destroy/', method='DELETE')
	except:
		pass

	if not skip_dns:
		util.item('Removing DNS records')
		_domains = [d['name'] for d in config.get('domains', []) if not d['internal']]
		_domains, _subdomains = domains._parse_domains(_domains)
		domains._delete_dns_records(_domains, _subdomains)

	if environment:
		util.item('Destroying environment')
		_destroy_environment()
	else:
		util.item('Destroying namespace')
		_destroy_namespace()

	util.item('Removing .sail/*')
	shutil.rmtree(root + '/.sail')

	util.success('Destroyed successfully')

def _destroy_namespace():
	config = util.config()
	c = util.connection()

	namespace = config['namespace']

	c.run('rm -rf /var/www/_%s' % namespace)
	c.run('rm -rf /etc/nginx/conf.d/%s.conf' % namespace)
	c.run('mysql -e "DROP DATABASE \\`wordpress_%s\\`;"' % namespace)
	c.run('mysql -e "DROP USER \\`wordpress_%s\\`@localhost"' % namespace)

	# Update the remote config.
	remote_config = json.loads(c.run('cat /etc/sail/config.json').stdout)
	remote_config['namespaces'].remove(config['namespace'])
	c.put(io.StringIO(json.dumps(remote_config)), '/etc/sail/config.json')

	# TODO: Maybe revoke/delete SSL certificates for this namespace

	c.run('systemctl reload nginx')

def _destroy_environment():
	config = util.config()
	try:
		droplet = digitalocean.Droplet(
			token=config['provider_token'],
			id=config['droplet_id']
		)
		droplet.destroy()
		util.item('Droplet destroyed successfully')
	except Exception as e:
		util.item('Error destroying droplet')

	try:
		key = digitalocean.SSHKey(
			token=config['provider_token'],
			id=config['key_id']
		)
		key.destroy()
		util.item('SSH key destroyed successfully')
	except:
		util.item('Error destroying SSH key')

@cli.command()
@click.option('--provider-token', help='Your DigitalOcean API token, must be read-write. You can set a default token with: sail config provider-token <token>')
def sizes(provider_token):
	'''Get available droplet sizes'''
	root = util.find_root()

	# Try and get a provider token from .sail/config.json
	if not provider_token and root:
		config = util.config()
		provider_token = config.get('provider_token')

	if not provider_token:
		provider_token = util.get_sail_default('provider-token')

	if not provider_token:
		raise util.SailException('You need to provide a DigitalOcean API token with --provider-token, or set a default one with: sail config provider-token <token>')

	click.echo('# Getting available droplet sizes')

	manager = digitalocean.Manager(token=provider_token)
	sizes = manager.get_all_sizes()
	t = PrettyTable(['Size', 'Price', 'Description'])

	for size in sizes:
		if size.available:
			t.add_row([size.slug, size.price_monthly, size.description])

	t.align = 'l'
	t.sortby = 'Price'
	click.echo(t.get_string())

@cli.command()
@click.option('--provider-token', help='Your DigitalOcean API token, must be read-write. You can set a default token with: sail config provider-token <token>')
def regions(provider_token):
	'''Get available deployment regions'''
	root = util.find_root()

	# Try and get a provider token from .sail/config.json
	if not provider_token and root:
		config = util.config()
		provider_token = config.get('provider_token')

	if not provider_token:
		provider_token = util.get_sail_default('provider-token')

	if not provider_token:
		raise util.SailException('You need to provide a DigitalOcean API token with --provider-token, or set a default one with: sail config provider-token <token>')

	click.echo('# Getting available regions')

	t = PrettyTable(['Slug', 'Name'])

	manager = digitalocean.Manager(token=provider_token)
	regions = manager.get_all_regions()

	for region in regions:
		if region.available:
			t.add_row([region.slug, region.name])

	t.align = 'l'
	click.echo(t.get_string())

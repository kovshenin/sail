from sail import cli, util, deploy, __version__

import sail
import json
import subprocess, os
import click
import shutil
import digitalocean
import re, secrets, string
import shlex, time, io, pathlib, jinja2

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from prettytable import PrettyTable

@cli.command()
@click.option('--provider-token', help='Your DigitalOcean API token, must be read-write. You can set a default token with: sail config provider-token <token>')
@click.option('--size', default='s-1vcpu-1gb-intel', help='The Droplet size, defaults to s-1vcpu-1gb-intel. To get a full list of available sizes and pricing run: sail sizes')
@click.option('--region', default='ams3', help='The region to deploy to, defaults to ams3. For a full list of available regions run: sail regions')
@click.option('--email', help='The admin e-mail address. You can set the default e-mail address with: sail config email <email>')
@click.option('--force', '-f', is_flag=True)
@click.pass_context
def init(ctx, provider_token, email, size, region, force):
	'''Initialize and provision a new project'''
	root = util.find_root()

	if root and os.path.exists(root + '/.sail'):
		raise click.ClickException('This ship has already sailed. Pick another one or remove the .sail directory.')

	files = os.listdir(path='.')
	if files and not force:
		raise click.ClickException('This project directory is not empty, can not init here. Override with --force, can destroy existing files.')

	if not provider_token:
		provider_token = util.get_sail_default('provider-token')

	if not provider_token:
		raise click.ClickException('You need to provide a DigitalOcean API token with --provider-token, or set a default one with: sail config provider-token <token>')

	# Make sure the provider token works
	try:
		account = digitalocean.Account(token=provider_token)
		account.load()
		if account.status != 'active':
			raise click.ClickException('This DigitalOcean account is not active.')
		if not account.email_verified:
			raise click.ClickException('This DigitalOcean account e-mail is not verified.')
	except:
		raise click.ClickException('Invalid prodiver token.')

	if not email:
		email = util.get_sail_default('email')

	if not email:
		raise click.ClickException('You need to provide an admin e-mail address with --email, or set a default one with: sail config email <e-mail>')

	click.echo('# Initializing')

	response = util.request('/init/', json={
		'email': email,
		'version': __version__,
	}, anon=True)

	app_id = response['app_id']
	secret = response['secret']
	hostname = response['hostname']

	click.echo('- Claimed application id: %s' % app_id)

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

	os.mkdir('.sail')
	root = util.find_root()

	click.echo('- Writing SSH keys to .sail/ssh.key')
	with open('%s/.sail/ssh.key' % root, 'w+') as f:
		f.write(private_key)
	os.chmod('%s/.sail/ssh.key' % root, 0o600)

	with open('%s/.sail/ssh.key.pub' % root, 'w+') as f:
		f.write(public_key)
	os.chmod('%s/.sail/ssh.key.pub' % root, 0o644)

	click.echo('- Writing .sail/config.json')
	config = {
		'app_id': app_id,
		'secret': secret,
		'hostname': hostname,
		'provider_token': provider_token,
		'email': email,
		'domains': [],
		'profile_key': ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(32)),
		'version': __version__,
	}
	with open('%s/.sail/config.json' % root, 'w+') as f:
		json.dump(config, f, indent='\t')

	click.echo('- Provisioning servers')
	click.echo('- Uploading SSH key to DigitalOcean')

	key = digitalocean.SSHKey(
		token=provider_token,
		name=app_id,
		public_key=public_key
	)

	try:
		key.create()
		key.load()
	except Exception as e:
		print(e)
		raise click.ClickException('Could not upload SSH key. Make sure token is RW.')

	click.echo('- Creating a new Droplet')

	with open(sail.TEMPLATES_PATH + '/cloud-config.yaml', 'r') as f:
		cloud_config = f.read()

	droplet = digitalocean.Droplet(
		token=provider_token,
		name=hostname,
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
		raise click.ClickException('Cloud not create new droplet. Please try again later.')

	click.echo('- Waiting for Droplet to boot')

	completed = False
	while not completed:
		time.sleep(3)
		actions = droplet.get_actions()
		for action in actions:
			action.load()
			if 'completed' == action.status:
				completed = True
				break

	click.echo('- Waiting for IP address')

	def wait_for_ip():
		droplet.load()
		if droplet.ip_address:
			return True
		return False

	util.wait(wait_for_ip, timeout=60, interval=10)

	click.echo('- Droplet up and running, requesting DNS record')

	response = util.request('/ip/', json={
		'ip': droplet.ip_address,
	})

	config['ip'] = droplet.ip_address
	config['droplet_id'] = droplet.id
	config['key_id'] = key.id

	with open('%s/.sail/config.json' % root, 'w+') as f:
		json.dump(config, f, indent='\t')

	click.echo('- Waiting for SSH')
	c = util.connection()

	def wait_for_ssh():
		try:
			c.run('hostname')
			return True
		except Exception as e:
			util.dlog(repr(e))
			return False

	util.wait(wait_for_ssh, timeout=60, interval=10)

	click.echo('- Writing server keys to .sail/known_hosts')
	with open('%s/.sail/known_hosts' % root, 'w+') as f:
		r = subprocess.run(['ssh-keyscan', '-t', 'rsa,ecdsa', '-H', config['ip'],
			hostname], stdout=f, stderr=subprocess.DEVNULL)

	click.echo('- Configuring software')

	# Generate an /etc/sail/config.json
	config_json = {
		'app_id': config['app_id'],
		'profile_key': config['profile_key']
	}

	c.run('mkdir /etc/sail')
	c.put(io.StringIO(json.dumps(config_json)), '/etc/sail/config.json')

	# Prepare release directories
	c.run('mkdir -p /var/www/releases/1337')
	c.run('mkdir -p /var/www/uploads')
	c.run('mkdir -p /var/www/profiles')
	c.run('chown -R www-data. /var/www')

	passwords = {}
	for key in ['mysql', 'wp']:
		passwords[key] = ''.join(secrets.choice(string.ascii_letters
			+ string.digits) for i in range(48))

	def wait_for_cloud_init():
		try:
			r = c.run('cloud-init status -l')
			return 'status: done' in r.stdout
		except:
			pass

		return False

	click.echo('- Waiting for cloud-init to complete')
	util.wait(wait_for_cloud_init, timeout=300, interval=10)

	c.run('mkdir -p /etc/nginx/conf.d/shared')
	c.put(sail.TEMPLATES_PATH + '/nginx.main.conf', '/etc/nginx/nginx.conf')
	c.put(sail.TEMPLATES_PATH + '/nginx.shared.conf', '/etc/nginx/conf.d/shared/sail.conf')

	# Generate default server config and install cert.
	click.echo('- Installing default SSL certificate')
	c.put(io.StringIO(util.template('nginx.server.conf',
		{'server_names': [hostname]})),'/etc/nginx/conf.d/%s.conf' % hostname)

	retry = 3
	https = False
	while retry:
		retry -= 1
		try:
			c.run('certbot -n --register-unsafely-without-email --agree-tos --nginx --redirect -d %s' % hostname)
			https = True
			break
		except:
			if retry:
				click.echo('- Certbot failed, retrying')
				time.sleep(10)
			else:
				click.echo('- Certbot failed, skipping SSL')

	# Update the domains config.
	config['domains'].append({'name': hostname, 'internal': True, 'https': https, 'primary': True})
	with open('%s/.sail/config.json' % root, 'w+') as f:
		json.dump(config, f, indent='\t')

	# Create a MySQL database
	click.echo('- Setting up the MySQL database')

	c.run('mysql -e "CREATE DATABASE wordpress;"')
	c.run('mysql -e "CREATE USER wordpress@localhost IDENTIFIED BY \'%s\'"' % passwords['mysql'])
	c.run('mysql -e "GRANT ALL PRIVILEGES ON wordpress.* TO wordpress@localhost;"')

	click.echo('- Downloading and installing WordPress')
	wp = 'sudo -u www-data wp --path=/var/www/releases/1337 '
	url = ('https://' if https else 'http://') + hostname

	c.run(wp + 'core download')
	c.run(wp + shlex.join([
		'config', 'create',
		'--dbname=wordpress',
		'--dbuser=wordpress',
		'--dbpass=%s' % passwords['mysql']
	]))
	c.run(wp + shlex.join([
		'core', 'install',
		'--url=%s' % url,
		'--title=Sailed',
		'--admin_user=%s' % email,
		'--admin_password=%s' % passwords['wp'],
		'--admin_email=%s' % email,
		'--skip-email'
	]))
	c.run(wp + shlex.join([
		'rewrite', 'structure', '/%postname%/'
	]))

	# Do da deploy.
	click.echo('- Cleaning up')
	c.run('rm -rf /var/www/public')
	c.run('ln -sfn /var/www/releases/1337 /var/www/public')
	c.run('rm -rf /var/www/public/wp-content/uploads && ln -sfn /var/www/uploads /var/www/public/wp-content/uploads')

	# Download files from production
	ctx.invoke(deploy.download, yes=True)

	# Create a local empty wp-contents/upload directory
	content_dir = '%s/wp-content/uploads' % root
	if not os.path.exists(content_dir):
		os.mkdir(content_dir)

	click.echo()
	click.echo('# Success. The ship has sailed!')

	click.echo()
	click.echo('- URL: %s' % url)
	click.echo('- Login: %s/wp-login.php' % url)
	click.echo('- Username: %s' % email)
	click.echo('- Password: %s (change me!)' % passwords['wp'])

	click.echo()
	click.echo('- SSH/SFTP Access Details')
	click.echo('- Host: %s' % hostname)
	click.echo('- Port: 22')
	click.echo('- Username: root')
	click.echo('- SSH Key: .sail/ssh.key')
	click.echo('- To open an interactive shell run: sail ssh')

	click.echo()
	click.echo('For support and documentation visit sailed.io')

@click.argument('path', nargs=-1, required=True)
@cli.command(context_settings=dict(ignore_unknown_options=True))
def blueprint(path):
	'''Run a blueprint file against your application'''
	import re
	import yaml
	import pathlib
	import json

	root = util.find_root()
	config = util.config()

	_args = path
	arguments = []
	options = {}
	flags = []

	for arg in _args:
		if not arg.startswith('-'):
			arguments.append(arg)
			continue

		# option or flag
		if '=' in arg:
			k, v = arg.split('=')
			options[k] = v
		else:
			flags.append(arg)

	path = arguments[0] # TODO: Support multiple paths
	path = pathlib.Path(path)

	# Try Sail's internal library of BPs
	if not path.exists() and path.parent == pathlib.Path('.'):
		path = pathlib.Path(__file__).parent / 'blueprints' / path.name

	if not path.exists():
		raise click.ClickException('File does not exist')

	if not path.name.endswith('.yml') and not path.name.endswith('.yaml'):
		raise click.ClickException('Blueprint files must be .yml or .yaml')

	with path.open() as f:
		s = f.read()

	def _parse_variables(match):
		name = match.group(1).strip()
		if name in vars:
			return json.dumps(vars[name])
		return None

	# Load user variables and fill from command line arguments if possible.
	y = yaml.safe_load(s)
	vars = {}
	for var in y.get('vars', []):
		option = var.get('option')
		_type = str

		_map = {
			'str': str,
			'string': str,
			'int': int,
			'integer': int,
			'float': float,
			'bool': bool,
			'boolean': bool,
		}

		if var.get('type') and var.get('type') in _map.keys():
			_type = _map[var.get('type')]

		if options.get(option):
			value = options.get(option)
		else:
			value = click.prompt(var['prompt'], default=var.get('default', None), type=_type)

		if _type == bool and type(value) is not bool:
			truthy = ['yes', 'y', 'true', '1', 'affirmative']
			value = True if value.lower() in truthy else False

		elif _type == int or _type == float:
			try:
				value = _type(value)
			except ValueError:
				raise click.ClickException('Could not convert %s to %s' % (repr(value), repr(_type)))

		vars[var['name']] = value

	# Reload with substitutions.
	s = re.sub(r'\${{([^}]+?)}}', _parse_variables, s)
	y = yaml.safe_load(s)

	click.echo('# Applying blueprint: %s' % path.name)
	response = util.request('/blueprint/', method='POST', json={'blueprint': y})
	task_id = response['task_id']

	util.wait_for_task(task_id, timeout=600, interval=5)

	click.echo('- Blueprint applied successfully')

@cli.command()
@click.option('--yes', '-y', is_flag=True, help='Force Y on overwriting local copy')
def destroy(yes):
	'''Shutdown and destroy the production droplet'''
	root = util.find_root()
	config = util.config()

	if not yes:
		click.confirm('All droplet data will be scrubbed and irretrievable. Are you sure?', abort=True)

	click.echo('# Destroying application')

	data = util.request('/destroy/', method='DELETE')

	try:
		droplet = digitalocean.Droplet(
			token=config['provider_token'],
			id=config['droplet_id']
		)
		droplet.destroy()
		click.echo('- Droplet destroyed successfully')
	except Exception as e:
		click.echo('- Error destroying droplet')

	try:
		key = digitalocean.SSHKey(
			token=config['provider_token'],
			id=config['key_id']
		)
		key.destroy()
		click.echo('- SSH key destroyed successfully')
	except:
		click.echo('- Error destroying SSH key')

	click.echo('- Removing .sail/*')
	shutil.rmtree(root + '/.sail')

@cli.command()
def sizes():
	'''Get available droplet sizes'''
	click.echo()
	click.echo('# Getting available droplet sizes')

	data = util.request('/sizes/', anon=True)
	t = PrettyTable(['Size', 'Price', 'Description'])

	for slug, size in data.items():
		t.add_row([slug, size['price_monthly'], size['description']])

	t.align = 'l'
	t.sortby = 'Price'
	click.echo(t.get_string())

@cli.command()
def regions():
	'''Get available deployment regions'''
	click.echo()
	click.echo('# Getting available regions')

	data = util.request('/regions/', anon=True)
	t = PrettyTable(['Slug', 'Name'])

	for slug, region in data.items():
		t.add_row([slug, region['name']])

	t.align = 'l'
	click.echo(t.get_string())

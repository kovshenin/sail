from sail import cli, util

import sail
import click
import digitalocean
import re
import shlex, io
import re
import yaml
import pathlib
import json
import invoke

@click.argument('path', nargs=-1, required=True)
@cli.command(context_settings=dict(ignore_unknown_options=True))
def blueprint(path):
	'''Run a blueprint file against your application'''
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
	blueprint = yaml.safe_load(s)

	click.echo('# Applying blueprint: %s' % path.name)

	for section, data in blueprint.items():
		if section == 'plugins' or section == 'themes':
			try:
				_bp_install_wp_products(section, data)
			except invoke.exceptions.UnexpectedExit as e:
				raise click.ClickException(e.result.stderr)

		elif section == 'options':
			try:
				_bp_update_options(data)
			except invoke.exceptions.UnexpectedExit as e:
				raise click.ClickException(e.result.stderr)
			continue

		elif section == 'define':
			try:
				_bp_define_constants(data)
			except invoke.exceptions.UnexpectedExit as e:
				raise click.ClickException(e.result.stderr)

		elif section == 'fail2ban':
			_bp_fail2ban(data)

		elif section == 'postfix':
			_bp_postfix(data)

		elif section == 'dns':
			_bp_dns(data)

		elif section == 'apt':
			_bp_apt(data)

	click.echo('- Blueprint applied successfully')

def _bp_apt(items):
	c = util.connection()

	if 'selections' in items:
		click.echo('- Setting debconf selections')
		selections = items['selections']
		for line in selections:
			command = util.join(['echo', line]) + ' | debconf-set-selections'
			c.run(command)

	if 'install' in items:
		wait = 'while fuser /var/{lib/{dpkg,apt/lists},cache/apt/archives}/{lock,lock-frontend} >/dev/null 2>&1; do sleep 1; done && '
		click.echo('- Updating package lists')
		c.run(wait + 'DEBIAN_FRONTEND=noninteractive apt update', timeout=300)

		click.echo('- Installing packages')
		packages = items['install']
		command = wait + util.join(['DEBIAN_FRONTEND=noninteractive', 'apt', 'install', '-y'] + packages)

		try:
			c.run(command, timeout=300)
		except invoke.exceptions.UnexpectedExit as e:
			err = e.result.stderr
			err = err.replace('WARNING: apt does not have a stable CLI interface. Use with caution in scripts.', '')
			err = err.strip()
			raise click.ClickException('Error: %s' % err)
		except invoke.exceptions.CommandTimedOut as e:
			raise click.ClickException('Timeout')

def _bp_dns(records):
	config = util.config()

	# group records by domain
	domains = {}
	for record in records:
		if record['domain'] not in domains:
			domains[record['domain']] = []

		domains[record['domain']].append(record)

	# Make sure all domains exist
	for domain, records in domains.items():
		if domain not in [d['name'] for d in config['domains']]:
			raise click.ClickException('This domain does not exist. To add use: sail domain add')

	for domain, records in domains.items():
		do_domain = digitalocean.Domain(token=config['provider_token'], name=domain)
		do_records = do_domain.get_records()

		for record in records:
			exists = False
			for do_record in do_records:
				if (do_record.name.lower() == record['name'].lower()
					and do_record.type.lower() == record['type'].lower()):
					exists = True
					continue

			if exists:
				click.echo('- Skipping %s record for %s.%s, already exists' %
					(record['type'], record['name'], record['domain']))
				continue

			click.echo('- Creating %s record for %s.%s' %
				(record['type'], record['name'], record['domain']))

			try:
				if record['type'].upper() == 'MX':
					do_domain.create_new_domain_record(
						name=record['name'],
						type=record['type'],
						data=record['value'],
						priority=record['priority']
					)
				else:
					do_domain.create_new_domain_record(
						name=record['name'],
						type=record['type'],
						data=record['value']
					)
			except Exception as e:
				raise click.ClickException(str(e))

def _bp_postfix(data):
	config = util.config()
	namespace = config['namespace']
	c = util.connection()

	mode = data.get('mode')
	if mode != 'relay':
		raise click.ClickException('Unsupported mode')

	relay_host = data.get('host')
	if not relay_host:
		raise click.ClickException('Invalid relay host')

	wait = 'while fuser /var/{lib/{dpkg,apt/lists},cache/apt/archives}/{lock,lock-frontend} >/dev/null 2>&1; do sleep 1; done && '
	status = c.run('dpkg -s postfix', warn=True)
	if not status or status.stdout.find('Status: install ok installed') < 0:
		click.echo('- Installing postfix')
		c.run('debconf-set-selections <<< \'postfix postfix/main_mailer_type select Satellite system\'')
		c.run('debconf-set-selections <<< \'postfix postfix/mailname string %s\'' % config['hostname'])
		c.run('debconf-set-selections <<< \'postfix postfix/relayhost string %s\'' % relay_host)
		c.run(wait + 'apt update && DEBIAN_FRONTEND=noninteractive apt install -y postfix libsasl2-modules', timeout=300)
		c.run('usermod -a -G mail www-data', warn=True)

	click.echo('- Configuring postfix')

	try:
		postfix_config = json.loads(c.run('cat /etc/sail/postfix.json').stdout)
		click.echo('- Updating existing /etc/sail/postfix.json')
	except:
		click.echo('- Creating new /etc/sail/postfix.json')
		postfix_config = {}

	postfix_config[namespace] = {
		'namespace': namespace,
		'smtp_sender': data.get('from_email'),
		'smtp_host': data.get('host'),
		'smtp_port': data.get('port', 578),
		'smtp_username': data.get('username'),
		'smtp_password': data.get('password'),
	}

	c.put(io.StringIO(json.dumps(postfix_config)), '/etc/sail/postfix.json')
	c.run('chmod 0600 /etc/sail/postfix.json')

	sasl_passwd = []
	relay_hosts = []
	for entry in postfix_config.values():
		sasl_passwd.append(f"{entry['smtp_sender']} {entry['smtp_username']}:{entry['smtp_password']}")
		relay_hosts.append(f"{entry['smtp_sender']} {entry['smtp_host']}:{entry['smtp_port']}")

	sasl_passwd = '\n'.join(sasl_passwd)
	relay_hosts = '\n'.join(relay_hosts)

	c.put(io.StringIO(sasl_passwd), '/etc/postfix/sasl_passwd')
	c.put(io.StringIO(relay_hosts), '/etc/postfix/relay_hosts')
	c.run('chmod 0600 /etc/postfix/sasl_passwd')
	c.run('postmap /etc/postfix/sasl_passwd')
	c.run('postmap /etc/postfix/relay_hosts')

	c.put(io.StringIO(util.template('postfix/main.cf', {'hostname': config['hostname']})), '/etc/postfix/main.cf')
	c.run('chmod 0640 /etc/postfix/main.cf && chown root.mail /etc/postfix/main.cf')
	c.run('systemctl restart postfix.service')

	# Set the from name/email in a mu-plugin
	if data.get('from_name') and data.get('from_email'):
		context = {
			'name': json.dumps(data.get('from_name')),
			'email': json.dumps(data.get('from_email')),
		}

		remote_path = util.remote_path()

		c.run('sudo -u www-data mkdir -p %s/public/wp-content/mu-plugins/' % remote_path)
		c.put(io.StringIO(util.template('postfix/1-sail-mail-from.php', context)),
			'%s/public/wp-content/mu-plugins/1-sail-mail-from.php' % remote_path)
		c.run('chown www-data. %s/public/wp-content/mu-plugins/1-sail-mail-from.php' % remote_path)

def _bp_fail2ban(jails):
	c = util.connection()
	remote_path = util.remote_path()

	wait = 'while fuser /var/{lib/{dpkg,apt/lists},cache/apt/archives}/{lock,lock-frontend} >/dev/null 2>&1; do sleep 1; done && '
	status = c.run('dpkg -s fail2ban', warn=True)
	if not status or status.stdout.find('Status: install ok installed') < 0:
		click.echo('- Installing fail2ban')
		c.run(wait + 'apt update && apt install -y fail2ban', timeout=300)

	click.echo('- Configuring fail2ban rules')
	# Make sure mu-plugins exists
	c.run('sudo -u www-data mkdir -p %s/public/wp-content/mu-plugins/' % remote_path)

	c.put(sail.TEMPLATES_PATH + '/fail2ban/wordpress-auth.conf', '/etc/fail2ban/filter.d/wordpress-auth.conf')
	c.put(sail.TEMPLATES_PATH + '/fail2ban/wordpress-pingback.conf', '/etc/fail2ban/filter.d/wordpress-pingback.conf')
	c.put(sail.TEMPLATES_PATH + '/fail2ban/nginx-deny.conf', '/etc/fail2ban/action.d/nginx-deny.conf')
	c.put(sail.TEMPLATES_PATH + '/fail2ban/0-sail-auth-syslog.php', '%s/public/wp-content/mu-plugins/0-sail-auth-syslog.php' % remote_path)
	c.put(io.StringIO(util.template('fail2ban/jail.local', {'jails': jails})), '/etc/fail2ban/jail.local')

	# Make sure configs directory exists and permissions ok
	c.run('chown www-data. %s/public/wp-content/mu-plugins/0-sail-auth-syslog.php' % remote_path)
	c.run('sudo -u www-data mkdir -p /var/www/configs')
	c.run('fail2ban-client reload')

def _bp_define_constants(constants):
	c = util.connection()

	click.echo('- Updating wp-config.php constants')
	wp = 'sudo -u www-data wp --path=%s --skip-themes --skip-plugins ' % util.remote_path('/public')

	for name, value in constants.items():
		if type(value) not in [str, float, int, bool]:
			raise click.ClickException('Invalid data type for %s' % name)

		raw = []

		if type(value) is bool:
			value = 'true' if value else 'false'
			raw = ['--raw']

		elif type(value) in [int, float]:
			value = str(value)
			raw = ['--raw']

		c.run(wp + util.join(['config', 'set', name, value] + raw), timeout=30)

def _bp_update_options(options):
	c = util.connection()

	click.echo('- Applying options')
	wp = 'sudo -u www-data wp --path=%s --skip-themes --skip-plugins ' % util.remote_path('/public')

	for option_name, data in options.items():
		# Scalars
		option_value = None
		format = []
		autoload = None
		delete = None

		if type(data) == dict:
			format = ['--format=json'] if data.get('type') == 'json' else []
			delete = data.get('delete', False)

			if data.get('autoload') is not None:
				autoload = bool(data.get('autoload'))

			option_value = data.get('value')
		else:
			option_value = data

		if not delete and type(option_value) not in [str, int, float]:
			raise click.ClickException('Invalid value type for %s' % option_name)

		if type(option_value) is str:
			option_value = option_value.strip('\n')

		if delete:
			c.run(wp + util.join(['option', 'delete', option_name]), timeout=30)
		else:
			c.run(wp + util.join(['option', 'update', option_name,
				option_value] + format), timeout=30)

			# Set the autoload flag
			if autoload is not None:
				c.run(wp + util.join([
					'eval', "update_option( %s, get_option( %s ), %s );" %
					(json.dumps(option_name), json.dumps(option_name), 'true' if autoload else 'false')
				]))

def _bp_install_wp_products(what, products):
	wporg = {}
	custom = {}

	# what = plugins/themes
	for slug, data in products.items():
		if type(data) in [str, int, float]:
			wporg[slug] = data
			continue

		if type(data) == dict:
			if not data.get('url'):
				raise click.ClickException('Could not find %s: %s' % (what[:-1], slug))

			custom[slug] = data
			continue

		raise click.ClickException('Unknown %s specification: %s' % (what[:-1], slug))

	if not wporg and not custom:
		return

	c = util.connection()
	wp = 'sudo -u www-data wp --path=%s ' % util.remote_path('/public')

	click.echo('- Installing %s' % what)

	for slug, version in wporg.items():
		click.echo('- wporg/%s=%s' % (slug, version))
		_version = ['--version=%s' % version] if version != 'latest' else []
		r = c.run(wp + util.join([what[:-1], 'install', '--force', slug] + _version), timeout=30)

	for slug, data in custom.items():
		url = data.get('url')
		click.echo('thirdparty/%s' % slug)
		c.run(wp + util.join([what[:-1], 'install', '--force', url]), timeout=30)

	if what == 'plugins':
		click.echo('- Activating plugins')

		if wporg:
			c.run(wp + util.join(['plugin', 'activate'] + list(wporg.keys())), timeout=60)

		if custom:
			c.run(wp + util.join(['plugin', 'activate'] + list(custom.keys())), timeout=60)

	else: # themes
		click.echo('- Activating theme')
		last = list(products.keys())[-1]
		c.run(wp + util.join(['theme', 'activate', last]), timeout=60)

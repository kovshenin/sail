from sail import cli, util

import click, pathlib, json
import os, shlex, subprocess, io
import webbrowser

@cli.command('config')
@click.argument('name', required=True, nargs=1)
@click.argument('value', required=False)
@click.option('--delete', is_flag=True)
def config(name, value=None, delete=False):
	'''Set reusable config variables'''
	valid_names = [
		'provider-token',
		'email',
		'api-base',
		'keep',
		'premium',
	]

	if name not in valid_names:
		raise util.SailException('Invalid config name: %s' % name)

	filename = (pathlib.Path.home() / '.sail-defaults.json').resolve()
	data = {}

	try:
		with open(filename) as f:
			data = json.load(f)
	except:
		pass

	if not value and not delete:
		if name not in data:
			raise util.SailException('The option is not set')

		click.echo(data[name])
		return

	if value and delete:
		raise util.SailException('The --delete flag does not expect an option value')

	if delete and name not in data:
		raise util.SailException('The option is not set, nothing to delete')

	if delete:
		del data[name]
		click.echo('Option %s deleted' % name)
	else:
		data[name] = value
		click.echo('Option %s set' % name)

	with open(filename, 'w+') as f:
		json.dump(data, f, indent='\t')

@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument('command', nargs=-1)
def wp(command):
	'''Run a WP-CLI command on the production host'''
	root = util.find_root()
	config = util.config()

	command = util.join(command)

	os.execlp('ssh', 'ssh', '-tt',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile="%s/.sail/known_hosts"' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile="%s/.sail/ssh.key"' % root,
		'-o', 'LogLevel=QUIET',
		'root@%s' % config['hostname'],
		'sudo -u www-data bash -c "cd %s; wp %s"' % (util.remote_path('/public'), command)
	)

@cli.command()
def admin():
	'''Open your default web browser to wp-admin. Logs in automatically if supported'''
	config = util.config()
	c = util.connection()

	util.heading('Logging in to wp-admin')

	primary = [d for d in config['domains'] if d['primary']]
	if len(primary) < 1:
		raise util.SailException('Could not find primary domain')

	primary = primary[0]
	url = ('https://' if primary.get('https') else 'http://') + primary['name']
	email = config['email']

	util.item('Running remote-login')
	command = ['wp', 'sail', 'remote-login', '--email=%s' % email]
	try:
		r = c.run('sudo -u www-data bash -c "cd %s; %s"' % (util.remote_path('/public'), util.join(command)))
		r = json.loads(r.stdout.strip())
		url = url + '/?_sail_remote_login=%s&id=%d' % (r['key'], r['id'])
	except:
		util.item('Remote login failed')
		url = url + '/wp-login.php'
		util.item('Login URL: %s' % url)

		if webbrowser.open(url):
			util.success('Browser window opened at wp-login.')
		else:
			util.item('Could not open browser window')
			util.item('Login URL: %s' % url)
			click.echo()

		return

	util.item('Remote login success')
	if webbrowser.open(url):
		util.success('Browser window opened at wp-admin.')
	else:
		util.item('Could not open browser window')
		util.item('Login URL (valid for 30s): %s' % url)
		click.echo()

@cli.command()
@click.option('--nginx', is_flag=True)
@click.option('--php', is_flag=True)
@click.option('--nginx-access', is_flag=True)
@click.option('--nginx-error', '--nginx-errors', is_flag=True)
@click.option('--php-error', '--php-errors', is_flag=True)
@click.option('--postfix', '--mail', is_flag=True)
@click.option('--mysql', '--mariadb', is_flag=True)
@click.option('--follow', '-f', is_flag=True)
@click.option('--lines', '-n', type=int)
def logs(nginx, php, nginx_access, nginx_error, php_error, postfix, mysql, follow, lines):
	'''Query and follow logs from the production server'''
	root = util.find_root()
	config = util.config()

	# Global settings
	settings = []
	width, height = os.get_terminal_size()

	if follow:
		settings.append('--follow')
	elif lines:
		settings.append('--lines %d' % lines)
	else:
		settings.append('--lines %d' % int(height - 1))

	# Journald settings
	if postfix:
		settings.append('-t postfix/qmgr')
		settings.append('-t postfix/pickup')
		settings.append('-t postfix/master')
		settings.append('-t postfix/smtp')
		settings.append('-t postfix/cleanup')
		settings.append('-t postfix/postsuper')
		settings.append('-t postfix/postqueue')

	if php_error or php:
		settings.append('-t php')

	journald_settings = ' '.join(settings)
	command = 'journalctl --no-hostname --directory=/var/log/journal %s' % journald_settings

	# Non-journald logs.
	if nginx_access or nginx:
		command = 'tail /var/log/nginx/access.log %s' % ' '.join(settings)
		if '--follow' not in settings:
			command += ' | less -S +G'

	if nginx_error:
		command = 'tail /var/log/nginx/error.log %s' % ' '.join(settings)
		if '--follow' not in settings:
			command += ' | less -S +G'

	if mysql:
		command = 'tail /var/log/mysql/mariadb-slow.log %s' % ' '.join(settings)
		if '--follow' not in settings:
			command += ' | less -S +G'

	os.execlp('ssh', 'ssh', '-tt',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile="%s/.sail/known_hosts"' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile="%s/.sail/ssh.key"' % root,
		'-o', 'LogLevel=QUIET',
		'root@%s' % config['hostname'],
		command
	)

@cli.command('info')
@click.option('--json', 'as_json', is_flag=True, help='Output as a JSON string')
def info(as_json):
	'''Show current sail information'''
	config = util.config()

	util.label_width(12)

	labels = {
		'app_id': 'App ID',
		'namespace': 'Namespace',
		'hostname': 'Hostname',
		'ip': 'IP Address',
		'version': 'Version',
	}

	if as_json:
		data = {}
		for key in labels:
			data[key] = config[key]

		return click.echo(json.dumps(data))

	click.echo()

	for key, label in labels.items():
		label = util.label(f'{label}:')
		value = config[key]
		click.echo(f'{label} {value}')

	click.echo()

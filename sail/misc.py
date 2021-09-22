from sail import cli, util

import click, pathlib, json
import os, shlex, subprocess
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
	]

	if name not in valid_names:
		raise click.ClickException('Invalid config name: %s' % name)

	filename = (pathlib.Path.home() / '.sail-defaults.json').resolve()
	data = {}

	try:
		with open(filename) as f:
			data = json.load(f)
	except:
		pass

	if not value and not delete:
		if name not in data:
			raise click.ClickException('The option is not set')

		click.echo(data[name])
		return

	if value and delete:
		raise click.ClickException('The --delete flag does not expect an option value')

	if delete and name not in data:
		raise click.ClickException('The option is not set, nothing to delete')

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
	sail_config = util.get_sail_config()

	command = shlex.join(command)

	click.echo('Spawning SSH and running WP-CLI on %s.sailed.io' % sail_config['app_id'], err=True)

	os.execlp('ssh', 'ssh', '-tt',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'docker exec -it sail sudo -u www-data bash -c "cd ~/public; wp %s"' % command
	)

@cli.command()
def admin():
	'''Open your default web browser to the wp-login.php location of your site'''
	root = util.find_root()
	sail_config = util.get_sail_config()
	webbrowser.open(sail_config['login_url'])

@cli.command()
@click.option('--nginx', is_flag=True)
@click.option('--php', is_flag=True)
@click.option('--nginx-access', is_flag=True)
@click.option('--nginx-error', '--nginx-errors', is_flag=True)
@click.option('--php-error', '--php-errors', is_flag=True)
@click.option('--postfix', '--mail', is_flag=True)
@click.option('--follow', '-f', is_flag=True)
@click.option('--lines', '-n', type=int)
def logs(nginx, php, nginx_access, nginx_error, php_error, postfix, follow, lines):
	'''Query and follow logs from the production server'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	click.echo('Querying logs on %s.sailed.io' % sail_config['app_id'])

	settings = []
	if nginx_access or nginx:
		settings.append('-t nginx_access')
	if nginx_error or nginx:
		settings.append('-t nginx_error')
	if php_error or php:
		settings.append('-t php')

	if follow:
		settings.append('--follow')
	elif lines:
		settings.append('--lines %d' % lines)
	else:
		settings.append('--lines 30')

	if postfix:
		settings.append('-t postfix/qmgr')
		settings.append('-t postfix/pickup')
		settings.append('-t postfix/master')
		settings.append('-t postfix/smtp')
		settings.append('-t postfix/cleanup')
		settings.append('-t postfix/postsuper')
		settings.append('-t postfix/postqueue')

	settings = ' '.join(settings)

	os.execlp('ssh', 'ssh', '-tt',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'journalctl --no-hostname --directory=/var/log/journal %s' % settings
	)

@cli.command()
@click.option('--root', '--host', is_flag=True, help='Login to the host (not the container) as the root user')
def ssh(root):
	'''Open an interactive SSH shell to the production container or host'''
	as_root = root
	root = util.find_root()
	sail_config = util.get_sail_config()

	# Container as www-data, or host as root
	command = ''
	if not as_root:
		command = 'docker exec -it sail sudo -u www-data bash -c "cd ~/public; bash"'

	click.echo('Spawning an interactive SSH shell for %s.sailed.io' % sail_config['app_id'])

	os.execlp('ssh', 'ssh', '-tt',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		command
	)

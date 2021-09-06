from sail import cli, util

import os, subprocess
import click

@cli.command()
@click.option('--nginx', is_flag=True)
@click.option('--php', is_flag=True)
@click.option('--nginx-access', is_flag=True)
@click.option('--nginx-error', '--nginx-errors', is_flag=True)
@click.option('--php-error', '--php-errors', is_flag=True)
@click.option('--follow', '-f', is_flag=True)
@click.option('--lines', '-n', type=int)
def logs(nginx, php, nginx_access, nginx_error, php_error, follow, lines):
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

	settings = ' '.join(settings)

	os.execlp('ssh', 'ssh', '-t',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'journalctl --no-hostname %s' % settings
	)

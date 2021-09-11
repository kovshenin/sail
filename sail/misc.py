from sail import cli, util

import click, pathlib, json
import os, shlex

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

	os.execlp('ssh', 'ssh', '-t',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'docker exec -it sail sudo -u www-data bash -c "cd ~/public; wp %s"' % command
	)

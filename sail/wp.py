from sail import cli, util

import os, subprocess
import click, shlex

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

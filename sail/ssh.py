from sail import cli, util

import os, subprocess
import click

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

	os.execlp('ssh', 'ssh', '-t',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		command
	)

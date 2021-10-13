from sail import cli, util

import click, pathlib, json
import os, shlex, subprocess, io
import requests

@cli.group(invoke_without_command=True)
@click.option('--root', '--host', is_flag=True, help='Login to the host (not the container) as the root user')
@click.pass_context
def ssh(ctx, root):
	'''Open an SSH shell, manage SSH keys and more'''
	# Default subcommand for back-compat
	if not ctx.invoked_subcommand:
		ctx.forward(shell)

@ssh.group()
def key():
	pass

@key.command()
@click.argument('path', nargs=1)
def add(path):
	'''Add an SSH key to the production server by filename or GitHub URL'''
	c = util.connection()

	if path.startswith('https://github.com/'):
		r = requests.get(path)
		if not r.ok:
			raise click.ClickException('Could not fetch keys from GitHub')

		keys = r.text.strip().split('\n')
	else:
		path = pathlib.Path(path)
		if not path.exists() or not path.is_file():
			raise click.ClickException('Provided public key file does not exist')

		with path.open('r') as f:
			keys = [f.read().strip()]

	to_add = {}

	for _key in keys:
		items = _key.split()
		if items[0] not in ['ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521'
			'ssh-ed25519', 'ssh-dss', 'ssh-rsa']:
			raise click.ClickException('Unsupported key type: %s' % items[0])

		type = items[0]
		key = items[1]

		try:
			r = c.run(shlex.join(['ssh-keygen', '-E', 'md5', '-lf', '/dev/stdin'])
				+ ' <<<' + shlex.join([_key]), hide=True)

			size, fp, _ = r.stdout.split(maxsplit=2)
		except:
			raise click.ClickException('Provided public key is invalid')

		to_add[fp] = _key

	existing = _list(c)

	click.echo('# Adding SSH keys:')
	for fingerprint, key in to_add.items():
		if fingerprint in existing:
			click.echo('- Skipped %s (already exists)' % fingerprint)
			continue

		click.echo('- Added %s' % fingerprint)
		c.run(shlex.join(['echo', key]) + ' >> /root/.ssh/authorized_keys', hide=True)

def _list(c):
	keys = io.BytesIO()
	c.get('/root/.ssh/authorized_keys', keys)

	data = {}

	keys.seek(0)
	for line in keys.readlines():
		line = line.decode('utf8').strip()
		items = line.split()

		if items[0] not in ['ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521'
			'ssh-ed25519', 'ssh-dss', 'ssh-rsa']:
			continue

		type = items[0]
		key = items[1]
		try:
			r = c.run(shlex.join(['ssh-keygen', '-E', 'md5', '-lf', '/dev/stdin'])
				+ ' <<<' + shlex.join([line]), hide=True)

			size, fp, _ = r.stdout.split(maxsplit=2)
		except:
			continue

		data[fp] = {'fingerprint': fp, 'key': line}

	return data

@key.command('list')
@click.option('--json', 'as_json', is_flag=True, help='Output in JSON format')
def listcmd(as_json):
	'''List currently authorized SSH keys on the production server'''
	c = util.connection()
	data = _list(c)

	if as_json:
		click.echo(json.dumps(data.keys()))
		return

	click.echo('# SSH Keys:')
	for fingerprint, key in data.items():
		click.echo('- ' + fingerprint)

@key.command()
@click.argument('hash', nargs=1)
def delete(hash):
	'''Delete an authorized SSH key from the production server'''
	root = util.find_root()
	with open('%s/.sail/ssh.key.pub' % root, 'r') as f:
		sail_pub_key = f.read()

	c = util.connection()
	try:
		r = c.run(shlex.join(['ssh-keygen', '-E', 'md5', '-lf', '/dev/stdin'])
			+ ' <<<' + shlex.join([sail_pub_key]), hide=True)

		_, sail_fp, _ = r.stdout.split(maxsplit=2)
	except:
		raise click.ClickException('Could not compute hash of local Sail key')

	if hash.lower() == sail_fp.lower():
		raise click.ClickException('This looks like the Sail SSH key, will not delete')

	existing = _list(c)
	index = [k.lower() for k in existing.keys()].index(hash.lower())

	if not index:
		raise click.ClickException('Could not find key with this fingerprint')

	fp = list(existing.keys())[index]
	key = existing[fp]['key']

	regex = key.replace('/', '\/')
	c.run(shlex.join(['sed', '-i', '/^%s/d' % regex, '/root/.ssh/authorized_keys']), hide=True)
	click.echo('Removed SSH key %s' % fp)

@ssh.command()
@click.option('--root', '--host', is_flag=True, help='Login to the host (not the container) as the root user')
def shell(root):
	'''Open an interactive SSH shell to the production container or host'''
	as_root = root
	root = util.find_root()
	sail_config = util.get_sail_config()

	# Container as www-data, or host as root
	command = ''
	if not as_root:
		command = 'docker exec -it sail sudo -u www-data bash -c "cd ~/public; bash"'

	click.echo('Spawning an interactive SSH shell for %s' % sail_config['hostname'])

	os.execlp('ssh', 'ssh', '-tt',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile="%s/.sail/known_hosts"' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile="%s/.sail/ssh.key"' % root,
		'root@%s' % sail_config['hostname'],
		command
	)

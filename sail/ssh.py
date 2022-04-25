from sail import cli, util

import click, pathlib, json
import os, shlex, subprocess, io, time
import requests, hashlib, base64

from datetime import datetime

@cli.group(invoke_without_command=True)
@click.option('--root', is_flag=True, help='Login as the root user')
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
@click.option('--label', help='Provide an optional label for this key')
def add(path, label=None, quiet=False):
	'''Add an SSH key to the production server by filename or GitHub URL'''
	config = util.config()

	if not quiet: util.heading('Adding SSH keys')

	c = util.connection()

	if path.startswith('https://github.com/'):
		if not quiet: util.item('Fetching keys from GitHub')

		r = requests.get(path)
		if not r.ok:
			raise util.SailException('Could not fetch keys from GitHub')

		keys = r.text.strip().split('\n')
		if not label:
			label = path
	else:
		path = pathlib.Path(path)
		if not path.exists() or not path.is_file():
			raise util.SailException('Provided public key file does not exist')

		with path.open('r') as f:
			keys = [f.read().strip()]

	to_add = {}

	for line in keys:
		items = line.split()
		if items[0] not in ['ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521'
			'ssh-ed25519', 'ssh-dss', 'ssh-rsa']:
			raise util.SailException('Unsupported key type: %s' % items[0])

		try:
			fp = _fingerprint(line)
		except:
			raise util.SailException('Provided public key is invalid')

		to_add[fp] = line

	existing = _list(c)

	for fingerprint, key in to_add.items():
		if fingerprint in existing:
			if not quiet: util.item('Skipped %s (already exists)' % fingerprint)
			continue

		if not quiet: util.item('Added %s' % fingerprint)
		c.run(util.join(['echo', key]) + ' >> /root/.ssh/authorized_keys', hide=True)

		config['ssh_key_meta'][fingerprint] = {
			'created': int(time.time()),
			'label': label,
			'protected': False,
		}

	if not quiet: util.item('Updating .sail/config.json')
	util.update_config(config)

	if not quiet: util.success('Done')

def _list(c):
	config = util.config()
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

		try:
			fp = _fingerprint(line)
		except:
			continue

		data[fp] = {'fingerprint': fp, 'key': line, 'label': None}

		if config['ssh_key_meta'].get(fp):
			data[fp]['label'] = config['ssh_key_meta'][fp]['label']

	return data

@key.command('list')
@click.option('--json', 'as_json', is_flag=True, help='Output in JSON format')
def listcmd(as_json):
	'''List currently authorized SSH keys on the production server'''
	config = util.config()

	if not as_json:
		util.heading('Listing SSH keys')
		util.item('Gathering remote SSH keys')

	c = util.connection()
	data = _list(c)

	if as_json:
		click.echo(json.dumps(data))
		return

	click.echo()
	util.label_width(8)

	for fingerprint, key in data.items():
		key_label = 'None'
		key_created = 'Unknown'
		if config['ssh_key_meta'].get(fingerprint):
			key_label = config['ssh_key_meta'][fingerprint]['label']
			key_created = datetime.fromtimestamp(config['ssh_key_meta'][fingerprint]['created'])

		label = util.label('Hash:')
		click.echo(f'{label} {fingerprint}')

		label = util.label('Label:')
		click.echo(f'{label} {key_label}')

		label = util.label('Added:')
		click.echo(f'{label} {key_created}')

		click.echo()

@key.command()
@click.argument('hash', nargs=1)
def delete(hash):
	'''Delete an authorized SSH key from the production server'''
	config = util.config()

	root = util.find_root()
	with open('%s/.sail/ssh.key.pub' % root, 'r') as f:
		sail_pub_key = f.read()

	util.heading('Deleting SSH key')
	util.item('Computing key hash')

	c = util.connection()
	try:
		sail_fp = _fingerprint(sail_pub_key)
	except:
		raise util.SailException('Could not compute hash of local Sail key')

	if hash.lower() == sail_fp.lower():
		raise util.SailException('This looks like the Sail SSH key, will not delete')

	util.item('Fetching existing keys')
	existing = _list(c)

	try:
		index = [k.lower() for k in existing.keys()].index(hash.lower())
		if not index:
			raise Exception()
	except:
		raise util.SailException('Could not find key with this fingerprint')

	fp = list(existing.keys())[index]
	key = existing[fp]['key']

	regex = key.replace('/', '\/')
	c.run(util.join(['sed', '-i', '/^%s/d' % regex, '/root/.ssh/authorized_keys']), hide=True)

	if config['ssh_key_meta'].get(fp):
		del config['ssh_key_meta'][fp]
		util.item('Updating .sail/config.json')
		util.update_config(config)

	util.success('Removed key: %s' % fp)

@ssh.command()
@click.option('--root', is_flag=True, help='Login as the root user')
def shell(root):
	'''Open an interactive SSH shell to the production host'''
	as_root = root
	root = util.find_root()
	config = util.config()

	command = ''
	if not as_root:
		command = 'sudo -u www-data bash -c "cd %s; bash"' % util.remote_path('/public')

	extra_args = '-vtt' if util.debug() else '-tt'

	os.execlp('ssh', 'ssh', extra_args,
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile="%s/.sail/known_hosts"' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile="%s/.sail/ssh.key"' % root,
		'-o', 'LogLevel=QUIET',
		'root@%s' % config['hostname'],
		command
	)

@ssh.command(context_settings=dict(ignore_unknown_options=True))
@click.argument('command', nargs=-1)
@click.option('--root', is_flag=True, help='Login as the root user')
def run(command, root):
	'''Run a command via SSH and return the results'''
	as_root = root
	root = util.find_root()
	config = util.config()

	if len(command) > 1:
		command = util.join(command)
	else:
		command = ''.join(command)

	if not as_root:
		command = util.join(['sudo', '-u', 'www-data', 'bash', '-c', command])

	extra_args = '-vtt' if util.debug() else '-tt'

	os.execlp('ssh', 'ssh', extra_args,
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile="%s/.sail/known_hosts"' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile="%s/.sail/ssh.key"' % root,
		'-o', 'LogLevel=QUIET',
		'root@%s' % config['hostname'],
		command
	)

def _fingerprint(line):
	key = base64.b64decode(line.strip().split()[1].encode('ascii'))
	fp_plain = hashlib.md5(key).hexdigest()
	return 'MD5:' + ':'.join(a+b for a,b in zip(fp_plain[::2], fp_plain[1::2]))

from sail import cli, util, __version__

import json
import subprocess, os
import click
import shutil
from prettytable import PrettyTable

@cli.command()
@click.option('--provider-token', help='Your DigitalOcean API token, must be read-write. You can set a default token with: sail config provider-token <token>')
@click.option('--size', default='s-1vcpu-1gb-intel', help='The Droplet size, defaults to s-1vcpu-1gb-intel. To get a full list of available sizes and pricing run: sail sizes')
@click.option('--region', default='ams3', help='The region to deploy to, defaults to ams3. For a full list of available regions run: sail regions')
@click.option('--email', help='The admin e-mail address. You can set the default e-mail address with: sail config email <email>')
@click.option('--force', '-f', is_flag=True)
def init(provider_token, email, size, region, force):
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

	if not email:
		email = util.get_sail_default('email')

	if not email:
		raise click.ClickException('You need to provide an admin e-mail address with --email, or set a default one with: sail config email <e-mail>')

	click.echo()
	click.secho('# Initializing', bold=True)

	app = util.request('/init/', json={
		'provider_token': provider_token,
		'size': size,
		'email': email,
		'region': region,
	}, anon=True)

	app_id = app['app_id']
	private_key = app['private_key']
	public_key = app['public_key']

	click.echo('- Init successful, application id: %s' % app_id)
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
	with open('%s/.sail/config.json' % root, 'w+') as f:
		json.dump({
			'app_id': app_id,
			'secret': app['secret'],
			'url': app['url'],
			'login_url': app['login_url'],
			'version': __version__,
		}, f, indent='\t')

	click.echo()
	click.secho('# Provisioning servers', bold=True)

	response = util.request('/provision/', method='POST')
	task_id = response['task_id']

	click.echo('- Provision scheduled successfully, waiting...')

	try:
		data = util.wait_for_task(task_id, 600, 5)
		if data['status'] != 'ready':
			raise Exception()
	except:
		raise click.ClickException('Provisioning failed. Please try again later.')

	click.echo('- Writing server keys to .sail/known_hosts')
	f = open('%s/.sail/known_hosts' % root, 'w+')
	r = subprocess.run(['ssh-keyscan', '-t', 'rsa,ecdsa', '-H', '%s.sailed.io' % app_id], stdout=f, stderr=subprocess.DEVNULL)
	f.close()

	click.echo()
	click.secho('# Downloading files from production', bold=True)

	# Download files FROM production
	p = subprocess.Popen([
		'rsync', ('-rv' if util.debug() else '-r'),
		'-e', 'ssh -i %s/.sail/ssh.key -o UserKnownHostsFile=%s/.sail/known_hosts -o IdentitiesOnly=yes -o IdentityFile=%s/.sail/ssh.key' % (root, root, root),
		'--filter', '- .*', # Exclude all dotfiles
		'--filter', '- wp-content/debug.log',
		'--filter', '- wp-content/uploads',
		'root@%s.sailed.io:/var/www/public/' % app_id,
		'%s/' % root,
	])

	# ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	# TODO: Add a --debug flag to hide/show these

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		raise click.ClickException('An error occurred during download. Please try again.')

	click.echo('- Files download completed')

	# Create a local empty wp-contents/upload directory
	content_dir = '%s/wp-content/uploads' % root
	if not os.path.exists(content_dir):
		os.mkdir(content_dir)

	click.echo()
	click.secho('# Success. The ship has sailed!', bold=True)

	click.echo()
	click.echo('- URL: %s' % app['url'])
	click.echo('- Login: %s' % app['login_url'])
	click.echo('- Username: %s' % app['credentials']['username'])
	click.echo('- Password: %s (change me!)' % app['credentials']['password'])

	click.echo()
	click.echo('- SSH/SFTP Access Details')
	click.echo('- Host: %s.sailed.io' % app_id)
	click.echo('- Port: 22')
	click.echo('- Username: root')
	click.echo('- SSH Key: .sail/ssh.key')
	click.echo('- To open an interactive shell run: sail ssh')

	click.echo()
	click.echo('For support and documentation visit sailed.io')

@cli.command()
@click.option('--yes', '-y', is_flag=True, help='Force Y on overwriting local copy')
def destroy(yes):
	'''Shutdown and destroy the production droplet'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	if not yes:
		click.confirm('All droplet data will be scrubbed and irretrievable. Are you sure?', abort=True)

	app_id = sail_config['app_id']

	click.echo()
	click.echo('# Destroying application')

	data = util.request('/destroy/', method='DELETE')

	click.echo('- Droplet destroyed successfully')
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

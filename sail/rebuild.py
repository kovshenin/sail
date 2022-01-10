from sail import cli, util, domains, provision, blueprints, cron, __version__

import sail
import json
import subprocess, os
import click
import shutil
import digitalocean
import pathlib, hashlib, glob
import secrets, string

@cli.command()
@click.option('--yes', '-y', is_flag=True, help='Force yes on AYS prompts')
@click.option('--skip-snapshot', is_flag=True, help='Do not create a snapshot before rebuild')
@click.pass_context
def rebuild(ctx, yes, skip_snapshot):
	'''Rebuild an application environment.'''
	root = util.find_root()
	config = util.config()

	if not yes:
		click.confirm('Rebuilding will wipe the server and re-provision it from scratch. Continue?', abort=True)

	if config['namespace'] != 'default':
		raise util.SailException('Rebuild requires the default namespace. Current namespace: %s' % config['namespace'])

	c = util.connection()

	namespaces = []
	try:
		remote_config = json.loads(c.run('cat /etc/sail/config.json').stdout)
		namespaces = remote_config.get('namespaces', [])
	except:
		pass

	if len(namespaces) > 1 and not yes:
		click.confirm('This environment has multiple namespaces: %s. Wipe them all?' % ', '.join(namespaces), abort=True)

	util.heading('Rebuilding environment')

	util.item('Getting droplet data')
	try:
		droplet = digitalocean.Droplet(token=config['provider_token'], id=config['droplet_id'])
		droplet.load()
	except:
		raise util.SailException('Could not get droplet data')

	def wait_for_ssh():
		try:
			c.run('hostname')
			return True
		except Exception as e:
			util.dlog(repr(e))
			return False

	if not skip_snapshot:
		util.item('Creating a snapshot')
		action = droplet.take_snapshot(
			snapshot_name='sail-rebuild-%s' % hashlib.sha256(os.urandom(32)).hexdigest()[:8],
			return_dict=False,
			power_off=True,
		)

		if not action.wait(update_every_seconds=10, repeat=60):
			droplet.power_on() # Attempt to power-on the droplet before exit
			raise util.SailException('Could not complete snapshot action. Status: %s' % action.status)

		util.item('Waiting for power on')
		action = droplet.power_on(return_dict=False)

		if not action.wait(update_every_seconds=1, repeat=60):
			raise util.SailException('Could not power on the droplet. Status: %s' % action.status)

		util.item('Waiting for SSH')
		util.wait(wait_for_ssh, timeout=120, interval=10)

	util.item('Rebuilding droplet')

	try:
		action = droplet.rebuild(image_id=sail.DEFAULT_IMAGE, return_dict=False)
	except:
		raise util.SailException('Could not schedule rebuild action')

	util.item('Waiting for rebuild to complete')
	if not action.wait(update_every_seconds=1, repeat=60):
		raise util.SailException('Could not complete rebuild action. Status: %s' % action.status)

	util.item('Deleting .sail/known_hosts')
	try:
		pathlib.Path('%s/.sail/known_hosts' % root).unlink()
	except:
		util.item('Could not delete .sail/known_hosts')

	# Claim new application ID
	response = util.request('/init/', json={
		'email': config['email'],
		'version': __version__,
	}, anon=True)

	app_id = response['app_id']
	secret = response['secret']
	hostname = response['hostname']

	util.item('Claimed application id: %s' % app_id)

	util.item('Updating .sail/config.json')
	updated_config = {
		'app_id': app_id,
		'secret': secret,
		'hostname': hostname,
		'provider_token': config['provider_token'],
		'email': config['email'],
		'domains': [],
		'profile_key': ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(32)),
		'namespace': config['namespace'],
		'version': __version__,

		'ip': config['ip'],
		'droplet_id': config['droplet_id'],
		'key_id': config['key_id'],
	}

	config = updated_config
	util.update_config(config)

	util.item('Requesting DNS record')
	response = util.request('/ip/', json={
		'ip': config['ip'],
	})

	# With empty known_hosts
	c = util.connection()
	util.item('Waiting for SSH')
	util.wait(wait_for_ssh, timeout=120, interval=10)

	util.item('Writing server keys to .sail/known_hosts')
	with open('%s/.sail/known_hosts' % root, 'w+') as f:
		r = subprocess.run(['ssh-keyscan', '-t', 'rsa,ecdsa', '-H', config['ip'],
			config['hostname']], stdout=f, stderr=subprocess.DEVNULL)

	# With new known_hosts
	c = util.connection()
	provision._configure()

	passwords = {}
	for key in ['mysql', 'wp']:
		passwords[key] = ''.join(secrets.choice(string.ascii_letters
			+ string.digits) for i in range(48))

	# Run the installs
	provision._install(passwords)

	# Add the default WP cron schedule.
	ctx.invoke(cron.add, schedule='*/5', command=('wp cron event run --due-now',), quiet=True)

	# Run a default blueprint
	try:
		ctx.invoke(blueprints.blueprint, path=['default.yaml'], doing_init=True)
	except:
		util.item('Could not apply blueprint')

	# Create a local empty wp-contents/upload directory
	content_dir = '%s/wp-content/uploads' % root
	if not os.path.exists(content_dir):
		os.mkdir(content_dir)

	# Automatically enable premium if it's been set up
	premium_license = util.get_sail_default('premium')
	premium_email = util.get_sail_default('email')
	if premium_license and premium_email:
		try:
			ctx.invoke(sail.premium.enable, doing_init=True)
		except:
			util.item('Could not initialize Premium')

	util.heading('Rebuild successful')
	provision._success(passwords['wp'])

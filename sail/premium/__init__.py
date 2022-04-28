import sail

from sail import cli, util, ssh

from . import monitor

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

import click, os

def premium_init():
	'''Initialize premium modules if in a premium-enabled application'''
	try:
		is_premium = util.premium()
		if not is_premium:
			raise Exception('Not premium, nothing to init.')

		_premium_force_init()
	except:
		pass

def _premium_force_init():
	from sail.premium import backups, monitor

@cli.group()
def premium():
	'''Enable or disable Sail Premium for your application'''
	pass

@premium.command()
@click.option('--force', is_flag=True, help='Force enable routine, even if already premium.')
@click.option('--email', help='The admin e-mail address. You can set the default e-mail address with: sail config email <email>')
@click.option('--license', help='The premium license key. You can set a default key with: sail config premium <license>')
@click.pass_context
def enable(ctx, force, email, license, doing_init=False):
	'''Provision premium features for this application.'''
	config = util.config()
	root = util.find_root()

	if not license:
		license = util.get_sail_default('premium')

	if not email:
		email = util.get_sail_default('email')

	util.heading('Setting up Sail Premium')

	if config.get('premium') and not force:
		raise util.SailException('Premium features have already been enabled for this application.')

	if not license:
		raise util.SailException('Premium license key not found. Set one with: sail config premium LICENSE_KEY')

	if not email:
		raise util.SailException('Premium requires an e-mail configuration. Set one with: sail config email EMAIL_ADDRESS')

	util.item('Verifying license key')
	response = util.request('/premium/check/', json={
		'email': email,
		'license': license,
	})

	if not response:
		raise util.SailException('Could not verify the premium license key.')

	util.item('Generating SSH keys')

	# Generate a key pair.
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	private_key = key.private_bytes(
		serialization.Encoding.PEM,
		serialization.PrivateFormat.TraditionalOpenSSL,
		serialization.NoEncryption()
	).decode('utf8')

	public_key = key.public_key().public_bytes(
		serialization.Encoding.OpenSSH,
		serialization.PublicFormat.OpenSSH
	).decode('utf8')

	with open('%s/.sail/premium.key.pub' % root, 'w+') as f:
		f.write(public_key)
	os.chmod('%s/.sail/premium.key.pub' % root, 0o644)

	# Updates config
	ctx.invoke(ssh.add, path='%s/.sail/premium.key.pub' % root, label='.sail/premium.key', quiet=True)
	config = util.config() # Reload it after update

	util.item('Verifying connection')
	response = util.request('/premium/enable/', json={
		'email': email,
		'license': license,
		'private_key': private_key,
		'namespace': config['namespace'],
	})

	c = util.connection()

	util.item('Updating remote configuration files')

	# Updated main/shared configs for <= 0.10.2.
	c.put(sail.TEMPLATES_PATH + '/nginx.main.conf', '/etc/nginx/nginx.conf')
	c.put(sail.TEMPLATES_PATH + '/nginx.shared.conf', '/etc/nginx/conf.d/extras/sail.conf')
	c.put(sail.TEMPLATES_PATH + '/prepend.php', '/etc/sail/prepend.php')

	# Premium configs.
	c.put(sail.TEMPLATES_PATH + '/nginx.main.premium.conf', '/etc/nginx/conf.d/extras/sail.main.premium.conf')
	c.put(sail.TEMPLATES_PATH + '/nginx.premium.conf', '/etc/nginx/conf.d/extras/sail.premium.conf')
	c.put(sail.TEMPLATES_PATH + '/premium.php', '/etc/sail/premium.php')

	# Make sure updated configs are live.
	c.run('systemctl reload nginx')

	util.item('Updating .sail/config.json')
	config['premium'] = license
	util.update_config(config)

	try:
		util.item('Enabling monitoring')
		ctx.invoke(monitor.enable, quiet=True)
	except:
		util.item('Monitoring could not be enabled!')

	# Don't show success during provision/init.
	if not doing_init:
		util.success('Premium has been enabled successfully')

from sail import cli, util

import os, subprocess
import click
import hashlib
import pathlib
from datetime import datetime

@cli.group()
def db():
	'''Import and export MySQL databases, or spawn an interactive shell'''
	pass

@db.command()
def cli():
	'''Open an interactive MySQL shell on the production host'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	click.echo('Spawning an interactive MySQL shell at %s.sailed.io' % sail_config['app_id'])

	os.execlp('ssh', 'ssh', '-t',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'docker exec -it sail sudo -u www-data wp --path=/var/www/public db cli'
	)

@db.command(name='import')
@click.argument('path', nargs=1, required=True)
def import_cmd(path):
	'''Import a local .sql or .sql.gz file to the production MySQL database'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	path = pathlib.Path(path).resolve()
	if not path.exists():
		raise click.ClickException('File does not exist')

	if not path.name.endswith('.sql') and not path.name.endswith('.sql.gz'):
		raise click.ClickException('This does not look like a .sql or .sql.gz file')

	temp_name = '%s.%s' % (hashlib.sha256(os.urandom(32)).hexdigest()[:8], path.name)
	is_gz = path.name.endswith('.sql.gz')

	click.echo('# Importing WordPress database')
	click.echo('- Uploading database file to production')

	args = ['-t']
	source = path
	destination = 'root@%s.sailed.io:/var/www/%s' % (sail_config['app_id'], temp_name)
	returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

	if returncode != 0:
		raise click.ClickException('An error occurred in rsync. Please try again.')

	# TODO: Maybe do an atomic import which deletes tables that no longer exist
	# by doing a rename.

	click.echo('- Importing database into MySQL')
	cat_bin = 'zcat' if is_gz else 'cat'

	p = subprocess.Popen(['ssh',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'docker exec sail bash -c "%s /var/www/%s | mysql -uroot wordpress"' % (cat_bin, temp_name)
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		raise click.ClickException('An error occurred in SSH. Please try again.')

	click.echo('- Cleaning up production')

	p = subprocess.Popen(['ssh',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'docker exec sail rm /var/www/%s' % temp_name
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		raise click.ClickException('An error occurred in SSH. Please try again.')

	click.echo('- Database imported')

@db.command()
def export():
	'''Export the production database to a local .sql.gz file'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	backups_dir = pathlib.Path(root + '/.backups')
	backups_dir.mkdir(parents=True, exist_ok=True)
	filename = datetime.now().strftime('%Y-%m-%d-%H%M%S.sql.gz')

	click.echo('# Exporting WordPress database')

	p = subprocess.Popen(['ssh',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'docker exec sail bash -c "mysqldump --quick --single-transaction --default-character-set=utf8mb4 -uroot wordpress | gzip -c9 > /var/www/%s"' % filename
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		raise click.ClickException('An error occurred in SSH. Please try again.')

	click.echo('- Export completed, downloading')

	args = ['-t']
	source = 'root@%s.sailed.io:/var/www/%s' % (sail_config['app_id'], filename)
	destination = '%s/%s' % (backups_dir, filename)
	returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

	if returncode != 0:
		raise click.ClickException('An error occurred in rsync. Please try again.')

	click.echo('- Cleaning up production')

	p = subprocess.Popen(['ssh',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'docker exec sail rm /var/www/%s' % filename
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		raise click.ClickException('An error occurred in SSH. Please try again.')

	click.echo('- Database export saved to .backups/%s' % filename)

from sail import cli, util

import requests, json, os, subprocess, time
import click, hashlib, pathlib, shutil
from datetime import datetime

@cli.command()
@click.argument('path', nargs=1, required=True)
@click.option('--yes', '-y', is_flag=True, help='Skip the AYS message and force yes')
@click.option('--skip-db', is_flag=True, help='Do not import the database')
@click.option('--skip-uploads', is_flag=True, help='Do not import uploads')
def restore(path, yes, skip_db, skip_uploads):
	'''Restore your application files, uploads and database from a backup file'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	path = pathlib.Path(path)
	if not path.exists():
		raise click.ClickException('File does not exist')

	if path.name.endswith('.sql.gz') or path.name.endswith('.sql'):
		raise click.ClickException('Looks like a database-only backup. Try: sail db import')

	if not path.name.endswith('.tar.gz'):
		raise click.ClickException('Doesn\'t look like a backup file')

	if not yes:
		click.confirm('This will restore a full backup to production. Continue?', abort=True)

	click.echo('# Restoring backup')

	app_id = sail_config['app_id']
	backups_dir = pathlib.Path(root + '/.backups')
	backups_dir.mkdir(parents=True, exist_ok=True)
	progress_dir = pathlib.Path(backups_dir / ('.%s.progress' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]))
	progress_dir.mkdir()

	database_filename = 'database.%s.sql.gz' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]

	click.echo('- Extracting backup files')

	p = subprocess.Popen([
		'tar', ('-xzvf' if util.debug() else '-xzf'), path.resolve(), '--directory', progress_dir.resolve()
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		shutil.rmtree(progress_dir)
		raise click.ClickException('An error occurred during backup. Please try again.')

	for x in progress_dir.iterdir():
		if x.name not in ['www', 'database.sql.gz', 'uploads']:
			shutil.rmtree(progress_dir)
			raise click.ClickException('Unexpected file in backup archive: %s' % x.name)

	if skip_uploads:
		click.echo('- Skipping uploads')
	else:
		click.echo('- Importing uploads')

		args = ['-rtl', '--delete', '--rsync-path', 'sudo -u www-data rsync']
		source = '%s/uploads/' % progress_dir
		destination = 'root@%s.sailed.io:/var/www/uploads/' % app_id
		returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

		if returncode != 0:
			shutil.rmtree(progress_dir)
			raise click.ClickException('An error occurred during restore. Please try again.')

	click.echo('- Importing application files')

	args = ['-rtl', '--delete', '--rsync-path', 'sudo -u www-data rsync']
	source = '%s/www/' % progress_dir
	destination = 'root@%s.sailed.io:/var/www/public/' % app_id
	returncode, stdout, stderr = util.rsync(args, source, destination)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise click.ClickException('An error occurred during restore. Please try again.')

	if skip_db:
		click.echo('- Skipping database import')
	else:
		click.echo('- Uploading database backup')

		args = ['-t']
		source = '%s/database.sql.gz' % progress_dir
		destination = 'root@%s.sailed.io:/var/www/%s' % (app_id, database_filename)
		returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

		if returncode != 0:
			shutil.rmtree(progress_dir)
			raise click.ClickException('An error occurred in rsync. Please try again.')

		click.echo('- Importing database into MySQL')

		# TODO: Maybe do an atomic import which deletes tables that no longer exist
		# by doing a rename.
		p = subprocess.Popen(['ssh',
			'-i', '%s/.sail/ssh.key' % root,
			'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
			'-o', 'IdentitiesOnly=yes',
			'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
			'root@%s.sailed.io' % sail_config['app_id'],
			'docker exec sail bash -c "zcat /var/www/%s | mysql -uroot wordpress"' % database_filename,
		])

		while p.poll() is None:
			util.loader()

		if p.returncode != 0:
			shutil.rmtree(progress_dir)
			raise click.ClickException('An error occurred in SSH. Please try again.')

		click.echo('- Cleaning up production')

		p = subprocess.Popen(['ssh',
			'-i', '%s/.sail/ssh.key' % root,
			'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
			'-o', 'IdentitiesOnly=yes',
			'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
			'root@%s.sailed.io' % sail_config['app_id'],
			'docker exec sail rm /var/www/%s' % database_filename
		])

		while p.poll() is None:
			util.loader()

		if p.returncode != 0:
			shutil.rmtree(progress_dir)
			raise click.ClickException('An error occurred in SSH. Please try again.')

	shutil.rmtree(progress_dir)
	click.echo('- Backup restored successfully. Your local copy may be out of date.')

@cli.command()
def backup():
	'''Backup your production files and database to your local .backups directory'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	click.echo('# Backing up')

	app_id = sail_config['app_id']
	backups_dir = pathlib.Path(root + '/.backups')
	backups_dir.mkdir(parents=True, exist_ok=True)
	progress_dir = pathlib.Path(backups_dir / ('.%s.progress' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]))
	(progress_dir / 'www').mkdir(parents=True)
	(progress_dir / 'uploads').mkdir()

	database_filename = 'database.%s.sql.gz' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]

	click.echo('- Downloading application files')

	args = ['-rtl', '--copy-dest', '%s/' % root]
	source = 'root@%s.sailed.io:/var/www/public/' % app_id
	destination = '%s/www/' % progress_dir
	returncode, stdout, stderr = util.rsync(args, source, destination)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise click.ClickException('An error occurred during backup. Please try again.')

	click.echo('- Downloading uploads')

	args = ['-rtl', '--copy-dest', '%s/wp-content/uploads/' % root]
	source = 'root@%s.sailed.io:/var/www/uploads/' % app_id
	destination = '%s/uploads/' % progress_dir
	returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise click.ClickException('An error occurred during backup. Please try again.')

	click.echo('- Exporting WordPress database')

	p = subprocess.Popen(['ssh',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'docker exec sail bash -c "mysqldump --quick --single-transaction --default-character-set=utf8mb4 -uroot wordpress | gzip -c9 > /var/www/%s"' % database_filename
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		shutil.rmtree(progress_dir)
		raise click.ClickException('An error occurred in SSH. Please try again.')

	click.echo('- Export completed, downloading database')

	args = ['-t']
	source = 'root@%s.sailed.io:/var/www/%s' % (sail_config['app_id'], database_filename)
	destination = '%s/database.sql.gz' % progress_dir
	returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise click.ClickException('An error occurred in rsync. Please try again.')

	click.echo('- Cleaning up production')

	p = subprocess.Popen(['ssh',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile=%s/.sail/known_hosts' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile=%s/.sail/ssh.key' % root,
		'root@%s.sailed.io' % sail_config['app_id'],
		'docker exec sail rm /var/www/%s' % database_filename
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		shutil.rmtree(progress_dir)
		raise click.ClickException('An error occurred in SSH. Please try again.')

	timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S.tar.gz')
	target = pathlib.Path(backups_dir / timestamp)

	click.echo('- Archiving and compressing backup files')

	p = subprocess.Popen([
		'tar', ('-cvzf' if util.debug() else '-czf'), target.resolve(), '-C', progress_dir.resolve(), '.'
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		shutil.rmtree(progress_dir)
		raise click.ClickException('An error occurred during backup. Please try again.')

	shutil.rmtree(progress_dir)

	click.echo('- Backup completed at .backups/%s' % timestamp)

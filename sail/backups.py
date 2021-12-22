from sail import cli, util

import requests, json, os, subprocess, time
import click, hashlib, pathlib, shutil
from datetime import datetime

@cli.group(invoke_without_command=True)
@click.pass_context
def backup(ctx):
	'''Create, restore and manage application backups'''
	# Default subcommand for back-compat
	if not ctx.invoked_subcommand:
		return ctx.forward(create)

@cli.command(name='restore')
@click.argument('path', nargs=1, required=True)
@click.option('--yes', '-y', is_flag=True, help='Skip the AYS message and force yes')
@click.option('--skip-db', is_flag=True, help='Do not import the database')
@click.option('--skip-uploads', is_flag=True, help='Do not import uploads')
@click.pass_context
def restore_compat(ctx, path, yes, skip_db, skip_uploads):
	'''Restore your application files, uploads and database from a backup file'''
	return ctx.forward(restore)

@backup.command()
@click.argument('path', nargs=1, required=True)
@click.option('--yes', '-y', is_flag=True, help='Skip the AYS message and force yes')
@click.option('--skip-db', is_flag=True, help='Do not import the database')
@click.option('--skip-uploads', is_flag=True, help='Do not import uploads')
def restore(path, yes, skip_db, skip_uploads):
	'''Restore your application files, uploads and database from a backup file'''
	root = util.find_root()
	config = util.config()
	c = util.connection()

	path = pathlib.Path(path)
	if not path.exists():
		raise util.SailException('File does not exist')

	if path.name.endswith('.sql.gz') or path.name.endswith('.sql'):
		raise util.SailException('Looks like a database-only backup. Try: sail db import')

	if not path.name.endswith('.tar.gz'):
		raise util.SailException('Doesn\'t look like a backup file')

	if not yes:
		click.confirm('This will restore a full backup to production. Continue?', abort=True)

	util.heading('Restoring local backup')

	app_id = config['app_id']
	backups_dir = pathlib.Path(root + '/.backups')
	backups_dir.mkdir(parents=True, exist_ok=True)
	progress_dir = pathlib.Path(backups_dir / ('.%s.progress' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]))
	progress_dir.mkdir()
	remote_path = util.remote_path()

	database_filename = 'database.%s.sql.gz' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]

	util.item('Extracting backup files')

	p = subprocess.Popen([
		'tar', ('-xzvf' if util.debug() else '-xzf'), path.resolve(), '--directory', progress_dir.resolve()
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred during backup. Please try again.')

	for x in progress_dir.iterdir():
		if x.name not in ['www', 'database.sql.gz', 'uploads']:
			shutil.rmtree(progress_dir)
			raise util.SailException('Unexpected file in backup archive: %s' % x.name)

	if skip_uploads:
		util.item('Skipping uploads')
	else:
		util.item('Importing uploads')

		args = ['-rtl', '--delete', '--rsync-path', 'sudo -u www-data rsync']
		source = '%s/uploads/' % progress_dir
		destination = 'root@%s:%s/uploads/' % (config['hostname'], remote_path)
		returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

		if returncode != 0:
			shutil.rmtree(progress_dir)
			raise util.SailException('An error occurred during restore. Please try again.')

	util.item('Importing application files')

	args = ['-rtl', '--delete', '--rsync-path', 'sudo -u www-data rsync']
	source = '%s/www/' % progress_dir
	destination = 'root@%s:%s/public/' % (config['hostname'], remote_path)
	returncode, stdout, stderr = util.rsync(args, source, destination)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred during restore. Please try again.')

	if skip_db:
		util.item('Skipping database import')
	else:
		util.item('Uploading database backup')

		args = ['-t']
		source = '%s/database.sql.gz' % progress_dir
		destination = 'root@%s:%s/%s' % (config['hostname'], remote_path, database_filename)
		returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

		if returncode != 0:
			shutil.rmtree(progress_dir)
			raise util.SailException('An error occurred in rsync. Please try again.')

		util.item('Importing database into MySQL')

		# TODO: Maybe do an atomic import which deletes tables that no longer exist
		# by doing a rename.
		try:
			c.run('zcat %s/%s | mysql -uroot "wordpress_%s"' % (remote_path, database_filename, config['namespace']))
		except:
			shutil.rmtree(progress_dir)
			raise util.SailException('An error occurred in SSH. Please try again.')

		util.item('Cleaning up production')

		try:
			c.run('rm %s/%s' % (remote_path, database_filename)) # TODO: Move to /tmp maybe, or /root
		except:
			shutil.rmtree(progress_dir)
			raise util.SailException('An error occurred in SSH. Please try again.')

	shutil.rmtree(progress_dir)

	util.success('Backup restored successfully. Local copy may be out of date.')

@backup.command()
def create():
	'''Backup your production files and database to your local .backups directory'''
	root = util.find_root()
	config = util.config()
	c = util.connection()

	util.heading('Creating a local backup')

	app_id = config['app_id']
	backups_dir = pathlib.Path(root + '/.backups')
	backups_dir.mkdir(parents=True, exist_ok=True)
	progress_dir = pathlib.Path(backups_dir / ('.%s.progress' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]))
	(progress_dir / 'www').mkdir(parents=True)
	(progress_dir / 'uploads').mkdir()
	remote_path = util.remote_path()

	database_filename = 'database.%s.sql.gz' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]

	util.item('Downloading application files')

	args = ['-rtl', '--copy-dest', '%s/' % root]
	source = 'root@%s:%s/public/' % (config['hostname'], remote_path)
	destination = '%s/www/' % progress_dir
	returncode, stdout, stderr = util.rsync(args, source, destination)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred during backup. Please try again.')

	util.item('Downloading uploads')

	args = ['-rtl', '--copy-dest', '%s/wp-content/uploads/' % root]
	source = 'root@%s:%s/uploads/' % (config['hostname'], remote_path)
	destination = '%s/uploads/' % progress_dir
	returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred during backup. Please try again.')

	util.item('Exporting WordPress database')

	try:
		c.run('mysqldump --quick --single-transaction --default-character-set=utf8mb4 -uroot "wordpress_%s" | gzip -c9 > %s/%s' % (config['namespace'], remote_path, database_filename))
	except:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred in SSH. Please try again.')

	util.item('Export completed, downloading database')

	args = ['-t']
	source = 'root@%s:%s/%s' % (config['hostname'], remote_path, database_filename)
	destination = '%s/database.sql.gz' % progress_dir
	returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

	if returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred in rsync. Please try again.')

	util.item('Cleaning up production')

	try:
		c.run('rm %s/%s' % (remote_path, database_filename))
	except:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred in SSH. Please try again.')

	timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S.tar.gz')
	target = pathlib.Path(backups_dir / timestamp)

	util.item('Archiving and compressing backup files')

	p = subprocess.Popen([
		'tar', ('-cvzf' if util.debug() else '-czf'), target.resolve(), '-C', progress_dir.resolve(), '.'
	])

	while p.poll() is None:
		pass

	if p.returncode != 0:
		shutil.rmtree(progress_dir)
		raise util.SailException('An error occurred during backup. Please try again.')

	shutil.rmtree(progress_dir)

	util.success('Backup completed at .backups/%s' % timestamp)

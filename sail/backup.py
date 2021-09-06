from sail import cli, util

import requests, json, os, subprocess, time
import click, hashlib, pathlib, shutil
from datetime import datetime

@cli.command()
def backup():
	'''Backup your production files and database to your local .backups directory'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	click.echo()
	click.echo('# Backing up')

	app_id = sail_config['app_id']
	backups_dir = pathlib.Path(root + '/.backups')
	backups_dir.mkdir(parents=True, exist_ok=True)
	progress_dir = pathlib.Path(backups_dir / ('.%s.progress' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]))
	(progress_dir / 'www').mkdir(parents=True)
	(progress_dir / 'uploads').mkdir()

	database_filename = 'database.%s.sql.gz' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]

	click.echo('- Downloading application files')

	# Download files FROM production
	p = subprocess.Popen([
		'rsync', ('-rtlv' if util.debug() else '-rtl'),
		'-e', 'ssh -i %s/.sail/ssh.key -o UserKnownHostsFile=%s/.sail/known_hosts -o IdentitiesOnly=yes -o IdentityFile=%s/.sail/ssh.key' % (root, root, root),
		'--filter', '- .*', # Exclude all dotfiles
		'--filter', '- wp-content/debug.log',
		'--filter', '- wp-content/uploads',
		'--filter', '- wp-content/cache',
		'--copy-dest', '%s/' % root,
		'root@%s.sailed.io:/var/www/public/' % app_id,
		'%s/www/' % progress_dir,
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		shutil.rmtree(progress_dir)
		raise click.ClickException('An error occurred during backup. Please try again.')

	click.echo('- Downloading uploads')

	# Download files FROM production
	p = subprocess.Popen([
		'rsync', ('-rtlv' if util.debug() else '-rtl'),
		'-e', 'ssh -i %s/.sail/ssh.key -o UserKnownHostsFile=%s/.sail/known_hosts -o IdentitiesOnly=yes -o IdentityFile=%s/.sail/ssh.key' % (root, root, root),
		'--filter', '- .*', # Exclude all dotfiles
		'--copy-dest', '%s/wp-content/uploads/' % root,
		'root@%s.sailed.io:/var/www/uploads/' % app_id,
		'%s/uploads/' % progress_dir,
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
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

	p = subprocess.Popen([
		'rsync', ('-tv' if util.debug() else '-t'),
		'-e', 'ssh -i %s/.sail/ssh.key -o UserKnownHostsFile=%s/.sail/known_hosts -o IdentitiesOnly=yes -o IdentityFile=%s/.sail/ssh.key' % (root, root, root),
		'root@%s.sailed.io:/var/www/%s' % (sail_config['app_id'], database_filename),
		'%s/database.sql.gz' % progress_dir
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
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

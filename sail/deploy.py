from sail import cli, util

import subprocess, time
import click

@cli.command()
@click.option('--with-uploads', is_flag=True, help='Include the wp-content/uploads directory')
@click.option('--delete', is_flag=True, help='Delete files from production that do not exist in your working copy')
@click.option('--dry-run', is_flag=True, help='Show changes about to be deployed to production')
def deploy(with_uploads, delete, dry_run):
	'''Deploy your working copy to production'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	app_id = sail_config['app_id']
	release_name = str(int(time.time()))

	if dry_run:
		click.echo('# Comparing files')

		destination = 'root@%s.sailed.io:/var/www/public/' % app_id
		source = '%s/' % root
		files = _diff(source, destination)
		empty = True

		colors = {'created': 'green', 'deleted': 'red', 'updated': 'yellow'}
		labels = {'created': 'New', 'deleted': 'Delete', 'updated': 'Update'}
		for op in ['created', 'updated', 'deleted']:
			for filename in files[op]:
				empty = False
				click.secho('- %s: %s' % (labels[op], filename), fg=colors[op])

		if empty:
			click.echo('- No changes')

		return

	click.echo('# Deploying to production')

	rsync_args = ['rsync', ('-rtlv' if util.debug() else '-rtl')]
	if delete:
		rsync_args.extend(['--delete'])
	rsync_args.extend(['--rsync-path', 'sudo -u www-data rsync'])
	rsync_args.extend(['-e', 'ssh -i %s/.sail/ssh.key -o UserKnownHostsFile=%s/.sail/known_hosts -o IdentitiesOnly=yes -o IdentityFile=%s/.sail/ssh.key' % (root, root, root)])

	click.echo('- Uploading application files to production')

	# Ship some files to production.
	p = subprocess.Popen(rsync_args + [
		'--filter', '- .*', # Exclude all dotfiles
		'--filter', '- wp-content/debug.log',
		'--filter', '- wp-content/uploads',
		'--filter', '- wp-content/cache',
		'--copy-dest', '/var/www/public/',
		'%s/' % root,
		'root@%s.sailed.io:/var/www/releases/%s' % (app_id, release_name)
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		raise click.ClickException('An error occurred during upload. Please try again.')

	if with_uploads:
		click.echo('- Uploading wp-content/uploads')

		# Send uploads to production
		p = subprocess.Popen(rsync_args + [
			'%s/wp-content/uploads/' % root,
			'root@%s.sailed.io:/var/www/uploads/' % app_id
		])

		while p.poll() is None:
			util.loader()

		if p.returncode != 0:
			raise click.ClickException('An error occurred during upload. Please try again.')

	click.echo('- Requesting Sail API to deploy: %s' % release_name)

	data = util.request('/deploy/', json={'release': release_name})
	task_id = data.get('task_id')

	if not task_id:
		raise click.ClickException('Could not obain a deploy task_id.')

	click.echo('- Scheduled successfully, waiting for deploy')

	try:
		data = util.wait_for_task(task_id, timeout=300, interval=5)
	except:
		raise click.ClickException('Deploy failed')

	click.echo('- Successfully deployed %s' % release_name)

@cli.command()
@click.argument('release', required=False, type=int, nargs=1)
@click.option('--releases', is_flag=True, help='Get a list of valid releases to rollback to')
def rollback(release=None, releases=False):
	'''Rollback production to a previous release'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	if releases or not release:
		data = util.request('/rollback')
		click.echo('# Available releases:')
		if data.get('releases', []):
			for r in data.get('releases', []):
				flags = '(current)' if r == data.get('current_release') else ''
				click.echo('- %s %s' % (r, flags))

			click.echo()
			click.echo('Rollback with: sail rollback <release>')
		else:
			click.echo('- No releases found, perhaps you should deploy something')

		return

	if release:
		release = str(release)

	click.echo()
	click.echo('# Rolling back')

	if release:
		click.echo('- Requesting Sail API to rollback: %s' % release)
	else:
		click.echo('- Requesting Sail API to rollback')

	data = util.request('/rollback/', json={'release': release})
	task_id = data.get('task_id')
	rollback_release = data.get('release')

	if not task_id:
		raise click.ClickException('Could not obain a rollback task_id.')

	click.echo('- Scheduled successfully, waiting for rollback')

	try:
		data = util.wait_for_task(task_id, timeout=300, interval=5)
	except:
		raise click.ClickException('Rollback failed')

	click.echo('- Successfully rolled back to %s' % rollback_release)

@cli.command()
@click.option('--yes', '-y', is_flag=True, help='Force Y on overwriting local copy')
@click.option('--with-uploads', is_flag=True, help='Include the wp-content/uploads directory')
@click.option('--delete', is_flag=True, help='Delete files from local copy that do not exist on production')
@click.option('--dry-run', is_flag=True, help='Show changes about to be downloaded to the working copy')
def download(yes, with_uploads, delete, dry_run):
	'''Download files from production to your working copy'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	if not yes and not dry_run:
		click.confirm('Downloading files from production may overwrite '
			+ 'your local copy. Continue?',
			abort=True
		)

	app_id = sail_config['app_id']

	if dry_run:
		click.echo('# Comparing files')

		source = 'root@%s.sailed.io:/var/www/public/' % app_id
		destination = '%s/' % root
		files = _diff(source, destination)
		empty = True

		colors = {'created': 'green', 'deleted': 'red', 'updated': 'yellow'}
		labels = {'created': 'New', 'deleted': 'Delete', 'updated': 'Update'}
		for op in ['created', 'updated', 'deleted']:
			for filename in files[op]:
				empty = False
				click.secho('- %s: %s' % (labels[op], filename), fg=colors[op])

		if empty:
			click.echo('- No changes')

		return

	click.echo('# Downloading application files from production')

	rsync_args = ['rsync', ('-rtlv' if util.debug() else '-rtl')]
	if delete:
		rsync_args.extend(['--delete'])
	rsync_args.extend(['-e', 'ssh -i %s/.sail/ssh.key -o UserKnownHostsFile=%s/.sail/known_hosts -o IdentitiesOnly=yes -o IdentityFile=%s/.sail/ssh.key' % (root, root, root)])

	# Download files FROM production
	p = subprocess.Popen(rsync_args + [
		'--filter', '- .*', # Exclude all dotfiles
		'--filter', '- wp-content/debug.log',
		'--filter', '- wp-content/uploads',
		'--filter', '- wp-content/cache',
		'root@%s.sailed.io:/var/www/public/' % app_id,
		'%s/' % root,
	])

	while p.poll() is None:
		util.loader()

	if p.returncode != 0:
		raise click.ClickException('An error occurred during download. Please try again.')

	if with_uploads:
		click.echo('- Downloading wp-content/uploads')

		# Download uploads from production
		p = subprocess.Popen(rsync_args + [
			'root@%s.sailed.io:/var/www/uploads/' % app_id,
			'%s/wp-content/uploads/' % root,
		])

		while p.poll() is None:
			util.loader()

		if p.returncode != 0:
			raise click.ClickException('An error occurred during download. Please try again.')

	click.echo('- Files download completed')

def _diff(source, destination):
	'''Compare application files between environments'''
	root = util.find_root()

	if source == destination:
		raise click.ClickException('Can not compare apples to apples')

	rsync_args = ['rsync', ('-rlciv' if util.debug() else '-rlci'), '--delete', '--dry-run']
	rsync_args.extend(['-e', 'ssh -i %s/.sail/ssh.key -o UserKnownHostsFile=%s/.sail/known_hosts -o IdentitiesOnly=yes -o IdentityFile=%s/.sail/ssh.key' % (root, root, root)])

	# Download files FROM production
	p = subprocess.Popen(rsync_args + [
		'--filter', '- .*', # Exclude all dotfiles
		'--filter', '- wp-content/debug.log',
		'--filter', '- wp-content/uploads', # TODO: Maybe allow to skip/include uploads
		'--filter', '- wp-content/cache',
		'--filter', '- wp-content/upgrade',
		source, destination,
	], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf8')

	stdout, stderr = p.communicate()

	if p.returncode != 0:
		raise click.ClickException('An error occurred in rsync. Please try again.')

	files = {
		'created': [],
		'deleted': [],
		'updated': [],
	}

	if util.debug():
		util.dlog(stdout)

	for line in stdout.splitlines():
		change = line[:11]
		path = line[12:]

		if len(change) < 11:
			continue

		# See --itemize-changes https://linux.die.net/man/1/rsync
		# Deleted
		if change.strip() == '*deleting':
			files['deleted'].append(path)
			continue

		# Newly created file.
		if change == '<f+++++++++' or change == '>f+++++++++':
			files['created'].append(path)
			continue

		# Newly created directory.
		if change == 'cd+++++++++':
			files['created'].append(path)
			continue

		# Checksum different.
		if change[:3] == '<fc' or change[:3] == '>fc':
			files['updated'].append(path)
			continue

		# Permission change
		if change[5] == 'p':
			files['updated'].append(path)
			continue

	return files

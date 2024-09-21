from sail import cli, util

import subprocess, time
import click, pathlib
import re, shlex, os, stat

from glob import glob

def _get_extend_filters(paths, prefix=None):
	root = util.find_root()

	extend_filters = []
	if not paths:
		return []

	if prefix:
		prefixed_root = root.rstrip('/') + '/' + prefix.strip('/')

	for entry in paths:
		_entry = pathlib.Path(entry)

		# Requested root directory, remove all filters.
		if str(_entry.resolve()) == root:
			return []

		try:
			relative = _entry.resolve().relative_to(root)
		except ValueError:
			raise util.SailException('Could not resolve path: %s' % entry)

		if prefix:
			try:
				relative = _entry.resolve().relative_to(prefixed_root)
			except ValueError:
				continue # The item is in root, but not in relative root, skip

			if str(relative) == '.':
				continue

		for parent in reversed(relative.parents):
			if str(parent) == '.':
				continue
			extend_filters.append('+ /%s' % parent)

		if _entry.is_dir():
			extend_filters.append('+ /%s/***' % relative)
		else:
			extend_filters.append('+ /%s' % relative)

	# Skip everything else.
	if len(extend_filters) > 0:
		extend_filters.append('- *')

	return extend_filters

def _get_deployignore_filters():
	root = util.find_root()
	p = pathlib.Path(root) / '.deployignore'

	filters = []
	negates = []

	if not p.is_file():
		return filters

	with p.open('r') as f:
		lines = f.readlines()

	for line in lines:
		line = line.strip()
		if re.match(r'^\s*#', line):
			continue

		negate = re.match(r'^\s*!(.+)', line)
		if negate:
			negates.append('+ %s' % negate.group(1))
			continue

		filters.append('- %s' % line)

	# Negates have to come first for rsync.
	filters = negates + filters
	return filters

@cli.command()
@click.argument('path', nargs=-1, required=False)
@click.option('--with-uploads', is_flag=True, help='Include the wp-content/uploads directory')
@click.option('--dry-run', is_flag=True, help='Show changes about to be deployed to production')
@click.option('--skip-hooks', '--no-verify', is_flag=True, help='Do not run pre-deploy hooks')
@click.option('--redeploy', is_flag=True, help='Redeploy to an existing release directory')
@click.pass_context
def deploy(ctx, with_uploads, dry_run, path, skip_hooks, redeploy):
	'''Deploy your working copy to production. If path is not specified then all application files are deployed.'''
	root = util.find_root()
	config = util.config()

	release = str(int(time.time()))

	if dry_run:
		return ctx.invoke(diff, path=path)

	util.heading('Deploying to production')

	hooks = []
	failed = []

	if not skip_hooks:
		hooks = glob(root + '/.sail/pre-deploy') + glob(root + '/.sail/pre-deploy.*')

	if len(hooks) > 0:
		util.item('Running pre-deploy hooks')

	for hook in hooks:
		f = pathlib.Path(hook)
		if not os.access(f, os.X_OK):
			f.chmod(f.stat().st_mode | stat.S_IEXEC)

		p = subprocess.Popen(str(f), encoding='utf8', shell=True)
		p.communicate()
		if p.returncode > 0:
			failed.append(f)

	if len(failed) > 0:
		util.item('One or more pre-deploy hooks failed. Aborting deploy.')
		for f in failed:
			util.item('Failed: %s' % f)

		exit()

	c = util.connection()
	remote_path = util.remote_path()

	if redeploy:
		try:
			_current = c.run('readlink %s/public' % remote_path).stdout.strip().split('/')[-1]
			if not _current:
				raise Exception()
		except:
			raise util.SailException('Could not determine current release')

		util.item(f'Overwriting existing release: {_current}')
		release = _current

	else:
		util.item('Preparing release directory')
		c.run('mkdir -p %s/releases/%s' % (remote_path, release))
		c.run('rsync -rogtl %s/public/ %s/releases/%s' % (remote_path, remote_path, release))

	util.item('Uploading application files to production')

	# Parse .deployignore.
	filters = _get_deployignore_filters()
	filters += _get_extend_filters(path)

	returncode, stdout, stderr = util.rsync(
		args=['-rtl', '--rsync-path', 'sudo -u www-data rsync',
			'--copy-dest', '%s/public/' % remote_path, '--delete'],
		source='%s/' % root,
		destination='root@%s:%s/releases/%s' % (config['hostname'], remote_path, release),
		extend_filters=filters
	)

	if returncode != 0:
		raise util.SailException('An error occurred during upload. Please try again.')

	if with_uploads:
		util.item('Uploading wp-content/uploads')

		# Send uploads to production
		returncode, stdout, stderr = util.rsync(
			args=['-rtl', '--rsync-path', 'sudo -u www-data rsync', '--delete'],
			source='%s/wp-content/uploads/' % root,
			destination='root@%s:%s/uploads/' % (config['hostname'], remote_path),
			default_filters=False,
			extend_filters=_get_extend_filters(path, 'wp-content/uploads')
		)

		if returncode != 0:
			raise util.SailException('An error occurred during upload. Please try again.')

	util.item('Deploying release: %s' % release)

	if not redeploy:
		util.item('Updating symlinks')
		c.run('sudo -u www-data ln -sfn %s/uploads %s/releases/%s/wp-content/uploads' % (remote_path, remote_path, release))
		c.run('sudo -u www-data ln -sfn %s/releases/%s %s/public' % (remote_path, release, remote_path))

		util.item('Reloading services')
		c.run('nginx -s reload')

		php_config = pathlib.Path(c.run('php -r "echo PHP_CONFIG_FILE_PATH;"').stdout).parent # /etc/php/8.1
		php_version = php_config.name
		c.run(f'kill -s USR2 $(cat /var/run/php/php{php_version}-fpm.pid)')
	else:
		util.item('Nothing to update/reload in redeploy')

	releases = c.run('ls %s/releases' % remote_path)
	releases = re.findall(r'\d+', releases.stdout)
	releases = [int(i) for i in releases]

	keep = util.get_sail_default('keep')
	if not keep:
		keep = 5

	keep = int(keep)
	keep = max(keep, 2)
	keep = min(keep, 30)

	if len(releases) > keep:
		util.item('Removing outdated releases')
		remove = sorted(releases)[:len(releases)-keep]
		for key in remove:
			c.run(util.join(['rm', '-rf', '%s/releases/%s' % (remote_path, key)]))

	util.success('Successfully deployed %s' % release)

@cli.command()
@click.argument('release', required=False, type=int, nargs=1)
@click.option('--releases', is_flag=True, help='Get a list of valid releases to rollback to')
def rollback(release=None, releases=False):
	'''Rollback production to a previous release'''
	sail = util.config()
	c = util.connection()
	remote_path = util.remote_path()

	if releases or not release:
		util.heading('Fetching available releases')

		_releases = c.run('ls %s/releases' % remote_path)
		_releases = re.findall(r'\d+', _releases.stdout)

		if len(_releases) < 1:
			raise util.SailException('Could not find any releases')

		try:
			util.item('Determining current release')
			_current = c.run('readlink %s/public' % remote_path).stdout.strip().split('/')[-1]
		except:
			_current = '0'

		click.echo()

		for r in _releases:
			flags = '(current)' if r == _current else ''
			click.secho('  %s %s' % (r, flags))

		click.echo()
		click.echo('Rollback: sail rollback <release>')
		click.echo()
		return

	if release:
		release = str(release)

	util.heading('Rolling back to %s' % release)

	util.item('Fetching releases')
	_releases = c.run('ls %s/releases' % remote_path).stdout.strip().split('\n')
	if release not in _releases:
		raise util.SailException('Invalid release. To get a list run: sail rollback --releases')

	util.item('Updating symlinks')
	c.run('ln -sfn %s/releases/%s %s/public' % (remote_path, release, remote_path))

	util.item('Reloading services')
	c.run('nginx -s reload')

	php_config = pathlib.Path(c.run('php -r "echo PHP_CONFIG_FILE_PATH;"').stdout).parent # /etc/php/8.1
	php_version = php_config.name
	c.run(f'kill -s USR2 $(cat /var/run/php/php{php_version}-fpm.pid)')

	util.success('Successfully rolled back to %s' % release)

@cli.command()
@click.argument('path', nargs=-1, required=False)
@click.option('--yes', '-y', is_flag=True, help='Force Y on overwriting local copy')
@click.option('--with-uploads', is_flag=True, help='Include the wp-content/uploads directory')
@click.option('--delete', is_flag=True, help='Delete files from local copy that do not exist on production')
@click.option('--dry-run', is_flag=True, help='Show changes about to be downloaded to the working copy')
@click.pass_context
def download(ctx, path, yes, with_uploads, delete, dry_run, doing_init=False):
	'''Download files from production to your working copy'''
	root = util.find_root()
	config = util.config()

	if not yes and not dry_run:
		click.confirm('Downloading files from production may overwrite '
			+ 'your local copy. Continue?',
			abort=True
		)

	delete = ['--delete'] if delete else []

	if dry_run:
		return ctx.invoke(diff, path=path, reverse=True)

	util.heading('Downloading production data')
	util.item('Downloading application files from production')

	returncode, stdout, stderr = util.rsync(
		args=['-rtl'] + delete,
		source='root@%s:%s' % (config['hostname'], util.remote_path('/public/')),
		destination='%s/' % root,
		extend_filters=_get_extend_filters(path)
	)

	if returncode != 0:
		raise util.SailException('An error occurred during download. Please try again.')

	if with_uploads:
		util.item('Downloading wp-content/uploads')

		# Download uploads from production
		returncode, stdout, stderr = util.rsync(
			args=['-rtl'] + delete,
			source='root@%s:%s' % (config['hostname'], util.remote_path('/uploads/')),
			destination='%s/wp-content/uploads/' % root,
			default_filters=False,
			extend_filters=_get_extend_filters(path, 'wp-content/uploads')
		)

		if returncode != 0:
			raise util.SailException('An error occurred during download. Please try again.')

	util.item('All download tasks completed')

	# Don't show success during provision/init.
	if not doing_init:
		util.success('Files download completed')

@cli.command()
@click.argument('path', nargs=-1, required=False)
@click.option('--reverse', is_flag=True, help='Reverse the file comparison direction (production to local)')
@click.option('--raw', is_flag=True, help='Show the list of changes in raw format')
def diff(path, reverse, raw):
	'''Show file changes between your local copy and production.'''
	root = util.find_root()
	config = util.config()

	if raw:
		util.loader(suspend=True)
	else:
		util.heading('Comparing files')

	destination = 'root@%s:%s' % (config['hostname'], util.remote_path('/public/'))
	source = '%s/' % root

	if reverse:
		destination, source = source, destination

	filters = _get_deployignore_filters()
	filters += _get_extend_filters(path)
	files = _diff(source, destination, filters)
	empty = True

	colors = {'created': 'green', 'deleted': 'red', 'updated': 'yellow'}
	labels = {'created': 'New', 'deleted': 'Delete', 'updated': 'Update'}
	for op in ['created', 'updated', 'deleted']:
		for filename in files[op]:
			if empty:
				empty = False
				click.echo()

			if raw:
				click.echo(filename)
			else:
				click.secho('  %s: %s' % (labels[op], filename), fg=colors[op])

	# TODO: Compare uploads if requested --with-uploads

	if empty and not raw:
		util.item('No changes')

	if not raw:
		click.echo()

def _diff(source, destination, extend_filters=[]):
	'''Compare application files between environments'''
	root = util.find_root()

	if source == destination:
		raise util.SailException('Can not compare apples to apples')

	args = ['-rlci', '--delete', '--dry-run']
	returncode, stdout, stderr = util.rsync(args, source, destination, extend_filters=extend_filters)

	if returncode != 0:
		raise util.SailException('An error occurred in rsync. Please try again.')

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

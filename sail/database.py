from sail import cli, util

import os, subprocess
import click
import hashlib
import pathlib
import json, re
import secrets, string

from datetime import datetime

@cli.group()
def db():
	'''Import and export MySQL databases, or spawn an interactive shell'''
	pass

@db.command()
def cli():
	'''Open an interactive MySQL shell on the production host'''
	root = util.find_root()
	config = util.config()

	os.execlp('ssh', 'ssh', '-t',
		'-i', '%s/.sail/ssh.key' % root,
		'-o', 'UserKnownHostsFile="%s/.sail/known_hosts"' % root,
		'-o', 'IdentitiesOnly=yes',
		'-o', 'IdentityFile="%s/.sail/ssh.key"' % root,
		'root@%s' % config['hostname'],
		'sudo -u www-data wp --path=%s db cli' % util.remote_path('/public')
	)

@db.command(name='import')
@click.argument('path', nargs=1, required=True)
@click.option('--partial', is_flag=True, help='Do not wipe production database and perform a partial import')
def import_cmd(path, partial):
	'''Import a local .sql or .sql.gz file to the production MySQL database'''
	root = util.find_root()
	config = util.config()
	c = util.connection()
	remote_path = util.remote_path()
	namespace = config['namespace']

	path = pathlib.Path(path).resolve()
	if not path.exists():
		raise util.SailException('File does not exist')

	if not path.name.endswith('.sql') and not path.name.endswith('.sql.gz'):
		raise util.SailException('This does not look like a .sql or .sql.gz file')

	temp_filename = '%s.%s' % (hashlib.sha256(os.urandom(32)).hexdigest()[:8], path.name)
	is_gz = path.name.endswith('.sql.gz')

	util.heading('Importing WordPress database')
	util.item('Uploading database file to production')

	args = ['-t']
	source = path
	destination = 'root@%s:%s/%s' % (config['hostname'], remote_path, temp_filename)
	returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

	if returncode != 0:
		raise util.SailException('An error occurred in rsync. Please try again.')

	cat_bin = 'zcat' if is_gz else 'cat'
	temp_name = 'import_%s' % hashlib.sha256(os.urandom(32)).hexdigest()[:8]

	try:
		# A partial import, no temp table, no replacements
		# Run as is on production db.
		if partial:
			util.item('Importing database into MySQL')
			c.run(f'{cat_bin} {remote_path}/{temp_filename} | mysql -uroot "wordpress_{namespace}"')

		# Full import. Try to clean it up as much as possible.
		else:
			util.item('Creating temporary database')
			c.run(f'mysql -uroot -e "CREATE DATABASE \\`{temp_name}\\`;"')

			util.item('Importing into temporary database')
			c.run(f'{cat_bin} {remote_path}/{temp_filename} | mysql -uroot "{temp_name}"')

			# Fetch all tables and determine table prefix
			tables = c.run(f'mysql -uroot "{temp_name}" --skip-column-names -e "SHOW TABLES;"').stdout.splitlines()
			core_tables = ['commentmeta', 'comments', 'links', 'options', 'postmeta',
				'posts', 'term_relationships', 'term_taxonomy', 'termmeta', 'terms',
				'usermeta', 'users'
			]

			prefixes = []

			for table in tables:
				prefix = re.search(r'^(.+?)(?:\d+_)?(?:%s)$' % '|'.join(core_tables), table)
				if prefix:
					prefixes.append(prefix.group(1))

			# Convert to set and make unique
			prefixes = set(prefixes)
			if len(prefixes) == 1:
				prefix = prefixes.pop()
				util.item(f'Determined table prefix: {prefix}')
			else:
				prefix = None

			clean_tables = []

			# Rename
			if prefix and prefix != 'wp_':
				for table in tables:
					if table[:len(prefix)] != prefix:
						clean_tables.append(table)
						continue

					table = table[len(prefix):]
					util.item(f'Renaming {prefix}{table} to wp_{table}')
					c.run(f'mysql -uroot "{temp_name}" -e "RENAME TABLE \\`{prefix}{table}\\` TO \\`wp_{table}\\`;"')
					clean_tables.append(f'wp_{table}')

				tables = clean_tables

				util.item(f'Updating prefix in wp_options, wp_usermeta')
				meta_keys = ['capabilities', 'user_level']
				option_names = ['user_roles']

				for meta_key in meta_keys:
					c.run(f'mysql -uroot "{temp_name}" -e "UPDATE \\`wp_usermeta\\` SET meta_key = \'wp_{meta_key}\' WHERE meta_key = \'{prefix}{meta_key}\';"')

				for option_name in option_names:
					c.run(f'mysql -uroot "{temp_name}" -e "UPDATE \\`wp_options\\` SET option_name = \'wp_{option_name}\' WHERE option_name = \'{prefix}{option_name}\';"')

			util.item('Dropping live database, moving temporary to live')
			c.run(f'mysql -uroot -e "DROP DATABASE \\`wordpress_{namespace}\\`; CREATE DATABASE \\`wordpress_{namespace}\\`;"')
			for table in tables:
				c.run(f'mysql -uroot -e "RENAME TABLE \\`{temp_name}\\`.\\`{table}\\` TO \\`wordpress_{namespace}\\`.\\`{table}\\`;"')

			util.item('Dropping temporary database')
			c.run(f'mysql -uroot -e "DROP DATABASE \\`{temp_name}\\`;"')

	except Exception as e:
		util.dlog(str(e))
		c.run(f'mysql -uroot -e "DROP DATABASE \\`{temp_name}\\`;"', warn=True)
		raise util.SailException('An error occurred in SSH. Please try again.')

	util.item('Cleaning up production')

	try:
		c.run(f'rm {remote_path}/{temp_filename}')
	except:
		raise util.SailException('An error occurred in SSH. Please try again.')

	util.success('Database imported')

@db.command()
@click.option('--json', 'as_json', is_flag=True, help='Output in JSON format')
def export(as_json):
	'''Export the production database to a local .sql.gz file'''
	root = util.find_root()
	config = util.config()
	c = util.connection()
	remote_path = util.remote_path()

	if as_json:
		util.loader(suspend=True)

	backups_dir = pathlib.Path(root + '/.backups')
	backups_dir.mkdir(parents=True, exist_ok=True)
	filename = datetime.now().strftime('%Y-%m-%d-%H%M%S.sql.gz')

	if not as_json:
		util.heading('Exporting WordPress database')

	try:
		c.run('mysqldump --quick --single-transaction --default-character-set=utf8mb4 -uroot "wordpress_%s" | gzip -c9 > %s/%s' % (config['namespace'], remote_path, filename))
	except:
		raise util.SailException('An error occurred in SSH. Please try again.')

	if not as_json:
		util.item('Export completed, downloading')

	args = ['-t']
	source = 'root@%s:%s/%s' % (config['hostname'], remote_path, filename)
	destination = '%s/%s' % (backups_dir, filename)
	returncode, stdout, stderr = util.rsync(args, source, destination, default_filters=False)

	if returncode != 0:
		raise util.SailException('An error occurred in rsync. Please try again.')

	if not as_json:
		util.item('Cleaning up production')

	try:
		c.run('rm %s/%s' % (remote_path, filename))
	except:
		raise util.SailException('An error occurred in SSH. Please try again.')

	if not as_json:
		util.success('Database export saved to .backups/%s' % filename)
	else:
		click.echo(json.dumps(destination))

@db.command()
def reset_password():
	'''Reset the WordPress database password and update wp-config.php'''
	root = util.find_root()
	config = util.config()

	util.heading('Resetting database password')
	util.item('Generating new password')
	password = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(48))
	c = util.connection()

	util.item('Updating database password')
	c.run('mysql -e "ALTER USER \\`wordpress_%s\\`@localhost IDENTIFIED BY \'%s\'"' % (config['namespace'], password))

	util.item('Updating DB_PASSWORD in wp-config.php')
	wp = 'sudo -u www-data wp --path=%s --skip-themes --skip-plugins ' % util.remote_path('public')
	c.run(wp + util.join(['config', 'set', 'DB_PASSWORD', password]))

	util.item('Verifying DB_USER/DB_NAME')
	for name in ['DB_USER', 'DB_NAME']:
		value = c.run(wp + util.join(['config', 'get', name])).stdout.strip()
		expected = 'wordpress_%s' % config['namespace']
		if value != expected:
			util.item(f'Updating {name} in wp-config.php')
			c.run(wp + util.join(['config', 'set', name, expected]))

	util.success('Database password reset. Sync with: sail download wp-config.php')

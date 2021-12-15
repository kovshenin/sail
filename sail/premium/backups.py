import sail

from sail import cli, util

import requests, json, os, subprocess, time
import click, hashlib, pathlib, shutil
from datetime import datetime
from prettytable import PrettyTable

@cli.group(invoke_without_command=True)
@click.pass_context
def backup(ctx):
	'''Create, restore and manage remote and local application backups'''
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
	'''Restore your application files, uploads and database from a local or remote backup'''
	return ctx.forward(restore)

@backup.command()
@click.argument('path', nargs=1, required=True)
@click.option('--yes', '-y', is_flag=True, help='Skip the AYS message and force yes')
@click.option('--skip-db', is_flag=True, help='Do not import the database')
@click.option('--skip-uploads', is_flag=True, help='Do not import uploads')
def restore(path, yes, skip_db, skip_uploads):
	'''Restore your application files, uploads and database from a local or remote backup'''
	config = util.config()

	if not path.isnumeric() or pathlib.Path(path).exists():
		return ctx.invoke(sail.backups.restore)

	click.echo('# Restoring a remote backup')

	request = util.request('/premium/backups/restore/', method='POST', json={
		'timestamp': path,
		'skip_db': skip_db,
		'skip_uploads': skip_uploads,
	})

	task_id = request['task_id']

	click.echo('- Waiting for task to complete')
	data = util.wait_for_task(task_id, 3600, 10)

	click.echo('- Remote backup restored successfully. Your local copy may be out of date!')

@backup.command()
@click.option('--local', is_flag=True, help='Force a local backup instead of remote')
@click.option('--description', help='Provide an optional description for this backup')
@click.pass_context
def create(ctx, local, description):
	'''Backup your production files and database to a remote or local location.'''
	config = util.config()

	if local and description:
		raise click.ClickException('Descriptions are only supported for remote backups.')

	# Invoke the local backup command if asked for --local
	if local:
		return ctx.invoke(sail.backups.create)

	click.echo('# Scheduling a remote backup task')

	request = util.request('/premium/backups/create/', method='POST', json={
		'description': description,
	})

	task_id = request['task_id']

	click.echo('- Waiting for task to complete')
	data = util.wait_for_task(task_id, 3600, 10)

	click.echo('- Remote backup completed')

@backup.command(name='list')
def list_cmd():
	'''List available managed backups'''
	if not util.premium():
		raise click.ClickException('Premium features are not enabled for this application. Learn more: https://sailed.io/premium/')

	backups = util.request('/premium/backups/list/')

	t = PrettyTable(['Timestamp', 'Date/Time', 'Size', 'Description'])

	for backup in backups:
		size = util.sizeof_fmt(int(backup['size']))
		date = datetime.fromtimestamp(int(backup['timestamp']))
		t.add_row([backup['timestamp'], date, size, backup['description']])

	t.align = 'l'
	t.sortby = 'Timestamp'
	click.echo(t.get_string())
	click.echo('Restore with: sail backup restore TIMESTAMP')

@backup.command()
@click.argument('timestamp', nargs=1, required=True)
@click.pass_context
def export(ctx, timestamp):
	'''Export a remote backup to a downloadable .tar.gz archive'''
	config = util.config()

	click.echo('# Exporting a remote backup')

	request = util.request('/premium/backups/export/', method='POST', json={
		'timestamp': timestamp,
	})

	task_id = request['task_id']

	click.echo('- Waiting for task to complete')
	data = util.wait_for_task(task_id, 3600, 10)

	click.echo('- Export completed')
	click.echo()

	ctx.invoke(info, timestamp=timestamp)

@backup.command()
@click.argument('timestamp', nargs=1, required=True)
@click.option('--json', 'as_json', is_flag=True, help='Return results as a JSON object')
def info(timestamp, as_json):
	'''Get information about a remote backup'''
	config = util.config()

	backup = util.request('/premium/backups/info/', method='POST', json={
		'timestamp': timestamp,
	})

	if as_json:
		click.echo(json.dumps(backup))
		return

	click.echo('# Backup %s' % backup['timestamp'])
	click.echo('- Description: %(description)s' % backup)
	click.echo('- Status: %(status)s' % backup)
	click.echo('- Date/Time: %s' % datetime.fromtimestamp(int(backup['timestamp'])))
	click.echo('- Size: %s' % util.sizeof_fmt(int(backup['size'])))

	if backup.get('export') == 'pending':
		click.echo('- Export: pending')
	elif backup.get('export'):
		click.echo('- Export URL: %s' % backup['export']['url'])
		click.echo('- Export Expires: %s' % datetime.fromtimestamp(int(backup['export']['expires'])))

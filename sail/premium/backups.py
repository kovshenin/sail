import sail

from sail import cli, util

import json, os
import click, pathlib

from datetime import datetime

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

	click.echo()
	click.echo('Restoring backup')
	click.secho('  Requesting remote backup restore', fg='bright_black')

	request = util.request('/premium/backups/restore/', method='POST', json={
		'timestamp': path,
		'skip_db': skip_db,
		'skip_uploads': skip_uploads,
	})

	task_id = request['task_id']

	click.secho('  Request received, waiting for task to complete', fg='bright_black')
	data = util.wait_for_task(task_id, 3600, 10)

	click.secho('  Task completed successfully', fg='bright_black')

	click.echo()
	util.success('Remote backup restored. Local copy may be out of date!')
	click.echo()

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

	click.echo()
	click.echo('Creating a backup')
	click.secho('  Requesting remote backup create', fg='bright_black')

	request = util.request('/premium/backups/create/', method='POST', json={
		'description': description,
	})

	task_id = request['task_id']

	click.secho('  Request received, waiting for task to complete', fg='bright_black')
	data = util.wait_for_task(task_id, 3600, 10)

	click.secho('  Task completed successfully', fg='bright_black')

	click.echo()
	util.success('Remote backup created successfully')
	click.echo()

@backup.command(name='list')
def list_cmd():
	'''List available managed backups'''
	if not util.premium():
		raise click.ClickException('Premium features are not enabled for this application. Learn more: https://sailed.io/premium/')

	backups = util.request('/premium/backups/list/')

	width, height = os.get_terminal_size()
	i = 0

	for backup in backups:
		timestamp = int(backup['timestamp'])

		ts = timestamp
		description = backup['description']
		size = util.sizeof_fmt(int(backup['size']))
		date = datetime.fromtimestamp(timestamp)

		# Truncate description
		maxlength = width - len(f'{ts} {size} {date}') - 4
		if len(description) > maxlength:
			description = description[:maxlength-5] + '...'

		dots_n = len(f'{ts} {description}') + len(f'{size} {date}')
		dots_n = width - dots_n - 4

		ts = click.style(ts, fg='green')
		dots = click.style('-'*dots_n, fg='bright_black')
		size = click.style(size, fg='bright_black')
		date = click.style(date, fg='bright_black')

		if i % (height / 2) == 0:
			click.echo()
			left = ' Timestamp  Description'
			right = 'Size           Date/Time '.rjust(width - len(left))
			click.secho(left + right, fg='bright_black')
			click.echo()

		click.echo(f' {ts} {description} {dots} {size} {date}')
		i += 1

	j = 11

	click.echo()
	label = util.label('Info:', j)
	click.echo(f'{label} sail backup info <timestamp>')

	label = util.label('Restore:', j)
	click.echo(f'{label} sail backup restore <timestamp>')

	label = util.label('Export:', j)
	click.echo(f'{label} sail backup export <timestamp>')
	click.echo()

@backup.command()
@click.argument('timestamp', nargs=1, required=True)
@click.pass_context
def export(ctx, timestamp):
	'''Export a remote backup to a downloadable .tar.gz archive'''
	config = util.config()

	click.echo()
	click.echo('Exporting backup')
	click.secho('  Requesting remote backup export', fg='bright_black')

	request = util.request('/premium/backups/export/', method='POST', json={
		'timestamp': timestamp,
	})

	task_id = request['task_id']

	click.secho('  Request received, waiting for task to complete', fg='bright_black')
	data = util.wait_for_task(task_id, 3600, 10)

	click.secho('  Task completed successfully', fg='bright_black')
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

	j = 13
	timestamp = int(backup['timestamp'])

	click.echo()

	label = util.label('Backup:', j)
	click.echo(f'{label} {timestamp}')

	label = util.label('Description:', j)
	description = backup['description']
	click.echo(f'{label} {description}')

	label = util.label('Status:', j)
	status = backup['status']
	click.echo(f'{label} {status}')

	label = util.label('Date/Time:', j)
	dt = datetime.fromtimestamp(timestamp)
	click.echo(f'{label} {dt}')

	label = util.label('Size:', j)
	size = util.sizeof_fmt(int(backup['size']))
	click.echo(f'{label} {size}')

	click.echo()
	label = util.label('Restore:', j)
	click.echo(f'{label} sail backup restore {timestamp}')

	if backup.get('export') == 'pending':
		label = util.label('Export:', j)
		click.echo(f'{label} pending')
	elif backup.get('export'):
		label = util.label('Exported:', j)
		export_url = backup['export']['url']
		click.echo(f'{label} {export_url}')

		label = util.label('Until:', j)
		export_expires = datetime.fromtimestamp(int(backup['export']['expires']))
		click.echo(f'{label} {export_expires}')
	else:
		label = util.label('Export:', j)
		click.echo(f'{label} sail backup export {timestamp}')

	click.echo()

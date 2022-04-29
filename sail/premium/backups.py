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
@click.option('--nowait', is_flag=True, help='Do not wait for the remote task to complete and exit early')
@click.pass_context
def restore_compat(ctx, path, yes, skip_db, skip_uploads, nowait):
	'''Restore your application files, uploads and database from a local or remote backup'''
	return ctx.forward(restore)

@backup.command()
@click.argument('path', nargs=1, required=True)
@click.option('--yes', '-y', is_flag=True, help='Skip the AYS message and force yes')
@click.option('--skip-db', is_flag=True, help='Do not import the database')
@click.option('--skip-uploads', is_flag=True, help='Do not import uploads')
@click.option('--nowait', is_flag=True, help='Do not wait for the remote task to complete and exit early')
@click.pass_context
def restore(ctx, path, yes, skip_db, skip_uploads, nowait):
	'''Restore your application files, uploads and database from a local or remote backup'''
	config = util.config()

	if not path.isnumeric() or pathlib.Path(path).exists():
		return ctx.forward(sail.backups.restore)

	util.heading('Restoring backup')
	util.item('Requesting remote backup restore')

	request = util.request('/premium/backups/restore/', method='POST', json={
		'timestamp': path,
		'skip_db': skip_db,
		'skip_uploads': skip_uploads,
	})

	task_id = request['task_id']

	if nowait:
		util.success('Request received, exiting (nowait)')
		return

	util.item('Request received, waiting for task to complete')
	data = util.wait_for_task(task_id, 3600, 10)

	util.item('Task completed successfully')
	util.success('Remote backup restored. Local copy may be out of date!')

@backup.command()
@click.option('--local', is_flag=True, help='Force a local backup instead of remote')
@click.option('--description', help='Provide an optional description for this backup')
@click.option('--nowait', is_flag=True, help='Do not wait for the remote task to complete and exit early')
@click.pass_context
def create(ctx, local, description, nowait):
	'''Backup your production files and database to a remote or local location.'''
	config = util.config()

	if local and description:
		raise util.SailException('Descriptions are only supported for remote backups.')

	# Invoke the local backup command if asked for --local
	if local:
		return ctx.invoke(sail.backups.create)

	util.heading('Creating a backup')
	util.item('Requesting remote backup create')

	request = util.request('/premium/backups/create/', method='POST', json={
		'description': description,
	})

	task_id = request['task_id']

	if nowait:
		util.success('Request received, exiting (nowait)')
		return

	util.item('Request received, waiting for task to complete')
	data = util.wait_for_task(task_id, 3600, 10)

	util.item('Task completed successfully')
	util.success('Remote backup created successfully')

@backup.command(name='list')
@click.option('--json', 'as_json', is_flag=True, help='Return results as a JSON object')
def list_cmd(as_json):
	'''List available managed backups'''
	if not util.premium():
		raise util.SailException('Premium features are not enabled for this application. Learn more: https://sailed.io/premium/')

	backups = util.request('/premium/backups/list/')

	if as_json:
		click.echo(json.dumps(backups))
		return

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

	util.label_width(11)

	click.echo()
	label = util.label('Info:')
	click.echo(f'{label} sail backup info <timestamp>')

	label = util.label('Restore:')
	click.echo(f'{label} sail backup restore <timestamp>')

	label = util.label('Export:')
	click.echo(f'{label} sail backup export <timestamp>')
	click.echo()

@backup.command()
@click.argument('timestamp', nargs=1, required=True)
@click.option('--nowait', is_flag=True, help='Do not wait for the remote task to complete and exit early')
@click.pass_context
def export(ctx, timestamp, nowait):
	'''Export a remote backup to a downloadable .tar.gz archive'''
	config = util.config()

	util.heading('Exporting backup')
	util.item('Requesting remote backup export')

	request = util.request('/premium/backups/export/', method='POST', json={
		'timestamp': timestamp,
	})

	task_id = request['task_id']

	if nowait:
		util.success('Request received, exiting (nowait)')
		return

	util.item('Request received, waiting for task to complete')
	data = util.wait_for_task(task_id, 3600, 10)

	util.item('Task completed successfully')
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

	util.label_width(13)
	timestamp = int(backup['timestamp'])

	click.echo()

	label = util.label('Backup:')
	click.echo(f'{label} {timestamp}')

	label = util.label('Description:')
	description = backup['description']
	click.echo(f'{label} {description}')

	label = util.label('Status:')
	status = backup['status']
	click.echo(f'{label} {status}')

	label = util.label('Date/Time:')
	dt = datetime.fromtimestamp(timestamp)
	click.echo(f'{label} {dt}')

	label = util.label('Size:')
	size = util.sizeof_fmt(int(backup['size']))
	click.echo(f'{label} {size}')

	click.echo()
	label = util.label('Restore:')
	click.echo(f'{label} sail backup restore {timestamp}')

	if backup.get('export') == 'pending':
		label = util.label('Export:')
		click.echo(f'{label} pending')
	elif backup.get('export'):
		label = util.label('Exported:')
		export_url = backup['export']['url']
		click.echo(f'{label} {export_url}')

		label = util.label('Until:')
		export_expires = datetime.fromtimestamp(int(backup['export']['expires']))
		click.echo(f'{label} {export_expires}')
	else:
		label = util.label('Export:')
		click.echo(f'{label} sail backup export {timestamp}')

	click.echo()

from sail import cli, util

import click
import re, os
import json, time

from datetime import datetime, timedelta
from prettytable import PrettyTable
from math import floor

@cli.group(invoke_without_command=True)
@click.pass_context
def monitor(ctx):
	'''Monitor your WordPress application uptime and health'''
	# Default subcommand for back-compat
	if not ctx.invoked_subcommand:
		return ctx.forward(status)

@monitor.command()
@click.option('--json', 'as_json', is_flag=True, help='Output results as a JSON object')
def status(as_json):
	'''Show the uptime and health of your application'''
	status = util.request('/premium/monitor/status/')

	if as_json:
		click.echo(json.dumps(status))
		return

	j = 11
	click.echo()

	# Status
	duration = status['reason']['duration']
	if duration < 0:
		duration = 0

	duration = format(str(timedelta(seconds=duration)))
	st_code = status['reason']['code']

	label = util.label('Status:', j)
	label_r = util.label('Reason:', j)

	if status['status'] == 'up':
		st_string = click.style('  UP  ', bg='green')
		click.echo(f'{label} {st_string} HTTP/{st_code} for {duration}')
	elif status['status'] == 'down':
		st_string = click.style(' DOWN ', bg='red')
		st_reason_description = click.style(f'HTTP/{st_code} ' + status['reason']['description'], fg='red')
		click.echo(f'{label} {st_string} for {duration}')
		click.echo(f'{label_r} {st_reason_description}')
	else:
		st_string = click.style(' UNKNOWN ', bg='bright_black')
		click.echo(f'{label} {st_string} for {duration}')

	def _uptime_color(v):
		if v == 0:
			return 'bright_black'
		if v >= 99.95:
			return 'white'
		if v >= 99.00:
			return 'yellow'
		return 'red'

	# Uptime
	intervals = ['24h', '7d', '30d']
	uptime = {}
	for i in intervals:
		v = floor(status['uptime'][i] * 100) / 100
		uptime[i] = click.style('{0:.2f}%'.format(v), fg=_uptime_color(v))

	label = util.label('Uptime:', j)
	uptime_24h, uptime_7d, uptime_30d = uptime['24h'], uptime['7d'], uptime['30d']
	click.echo(f'{label} {uptime_24h} in 24h, {uptime_7d} in 7d, {uptime_30d} in 30d')

	def _get_response_time_color(v):
		if v <= 0:
			return 'bright_black'
		if v <= 500:
			return 'white'
		if v < 1000:
			return 'yellow'
		return 'red'

	# Response Time
	response_time = status.get('response_time')
	response_time = click.style('{:,} ms'.format(response_time), fg=_get_response_time_color(response_time))
	label = util.label('Avg. Resp:', j)
	click.echo(f'{label} {response_time}')

	# Alerts/contacts
	state = click.style(status['alerts']['state'].title(), fg=_status_color(status['alerts']['status']))
	contacts = status['alerts']['contacts']
	unverified = status['alerts']['unverified']
	label = util.label('Alerts:', j)

	if unverified > 0:
		click.echo(f'{label} {state} ({contacts} contacts, {unverified} unverified)')
	else:
		click.echo(f'{label} {state} ({contacts} contacts)')

	# Render health-check results
	click.echo()
	_render_health(status, j)

	click.echo()

def _status_color(s):
	if s == 'ok':
		return 'white'
	elif s == 'warn':
		return 'yellow'
	elif s == 'critical':
		return 'red'
	else:
		return 'bright_black'

def _render_health(status, j):
	timestamp = status.get('health_timestamp', None)
	if not timestamp:
		for label in ['Core:', 'Plugins:', 'Themes:', 'Server:', 'Disk:', 'Updated:']:
			label = util.label(label, j)
			value = click.style('pending', fg=_status_color('unknown'))
			click.echo(f'{label} {value}')

		return

	# Core
	core_version = status['core']['version']
	latest_core_version = status['core']['latest']
	core_version_s = click.style(core_version, fg=_status_color(status['core']['status']))
	label = util.label('Core:', j)

	if core_version == latest_core_version:
		click.echo(f'{label} {core_version_s} (latest)')
	else:
		click.echo(f'{label} {core_version_s} (latest: {latest_core_version})')

	# Plugins
	total = status['plugins']['total']
	updates = status['plugins']['updates']
	uptodate = total - updates
	output = click.style(f'{uptodate}/{total} plugins', fg=_status_color(status['plugins']['status']))
	label = util.label('Plugins:', j)
	click.echo(f'{label} {output} up to date')

	# Themes
	total = status['themes']['total']
	updates = status['themes']['updates']
	uptodate = total - updates
	output = click.style(f'{uptodate}/{total} themes', fg=_status_color(status['themes']['status']))
	label = util.label('Themes:', j)
	click.echo(f'{label} {output} up to date')

	# Server
	updates = status['packages']['updates']
	updates = click.style(f'{updates} packages', fg=_status_color(status['packages']['status']))
	label = util.label('Server:', j)
	click.echo(f'{label} {updates} with updates')

	used = status['disk']['used']
	total = status['disk']['total']
	percent = used / total

	percent = click.style(f'{percent:.0%} used', fg=_status_color(status['disk']['status']))
	label = util.label('Disk:', j)

	used = util.sizeof_fmt(used)
	total = util.sizeof_fmt(total)

	click.echo(f'{label} {percent}, {used} of {total}')

	updated = datetime.fromtimestamp(timestamp)
	label = util.label('Updated:', j)
	click.echo(f'{label} {updated}')

@monitor.command()
@click.argument('minutes', nargs=1, required=True)
def snooze(minutes):
	'''Snooze alerts for a period of time'''
	timestamp = int(time.time())
	map = {'s': 1, 'm': 60, 'h': 60*60, 'd': 60*60*24}
	search = re.search(r'^(\d+)(s|h|m|d)?$', minutes)

	if not search:
		raise click.ClickException('Invalid snooze format.')

	value = int(search.group(1))
	unit = search.group(2)
	if not unit:
		unit = 'm'

	timestamp += value * map[unit]

	click.echo()
	click.echo('Snoozing monitor')
	click.secho('  Requesting remote monitor to snooze', fg='bright_black')

	util.request('/premium/monitor/snooze/', method='POST', json={
		'timestamp': timestamp,
	})

	click.secho('  Snooze acknowledged', fg='bright_black')

	click.echo()
	util.success('Monitor snoozed')
	click.echo()

@monitor.command()
def unsnooze():
	'''Unsnooze monitoring alerts'''

	click.echo()
	click.echo('Unsnoozing monitor')
	click.secho('  Requesting remote monitor to unsnooze', fg='bright_black')

	util.request('/premium/monitor/snooze/', method='DELETE')

	click.secho('  Unsnooze acknowledged', fg='bright_black')

	click.echo()
	util.success('Monitor unsnoozed')
	click.echo()


@monitor.command()
def enable():
	'''Enable monitoring for this application'''

	click.echo()
	click.echo('Enabling monitoring')
	click.secho('  Requesting remote monitor enable', fg='bright_black')

	util.request('/premium/monitor/enable/', method='POST')

	click.secho('  Request acknowledged', fg='bright_black')

	click.echo()
	util.success('Monitoring enabled. Status: sail monitor status')
	click.echo()

@monitor.command()
@click.option('--yes', '-y', is_flag=True, help='Force yes on the AYS message')
def disable(yes):
	'''Disable monitoring for this application'''
	if not yes:
		click.confirm('All monitoring and uptime data will be deleted. Are you sure?', abort=True)

	click.echo()
	click.echo('Disabling monitoring')
	click.secho('  Requesting remote monitor disable', fg='bright_black')

	util.request('/premium/monitor/disable/', method='POST')

	click.secho('  Request acknowledged', fg='bright_black')

	click.echo()
	util.success('Monitoring disabled.')
	click.echo()

@monitor.group(invoke_without_command=True)
@click.pass_context
def contact(ctx):
	'''Manage contacts for monitoring alerts'''
	if not ctx.invoked_subcommand:
		return ctx.forward(list)

@contact.command()
def list():
	'''List existing contacts for monitoring alerts'''
	contacts = util.request('/premium/monitor/contacts/')

	if len(contacts) < 1:
		click.echo()
		util.failure('No contacts found')
		click.echo('Add contacts using: sail monitor contact add <subject>')
		click.echo()
		return

	j = 9
	has_pending = False

	click.echo()
	for contact in contacts:
		label = util.label('Subject:', j)
		subject = contact['subject']
		click.echo(f'{label} {subject}')

		label = util.label('Added:', j)
		added = datetime.fromtimestamp(contact['created'])
		click.echo(f'{label} {added}')

		label = util.label('Status:', j)
		status = contact['status']

		if status != 'ready':
			has_pending = True
			status = click.style(status, fg='red')

		click.echo(f'{label} {status}')
		click.echo()

	if has_pending:
		click.echo('Some contacts are pending verification!')
		click.echo('Verify with: sail monitor contact verify <subject> <code>')
		click.echo()

@contact.command()
@click.argument('subject', nargs=1, required=True)
def add(subject):
	'''Add a new contact for monitoring alerts'''
	request = util.request('/premium/monitor/contacts/', method='POST', json={
		'subject': subject,
	})

	if request['status'] == 'pending':
		click.echo()
		util.success('Contact added, pending verification')
		click.echo('Verify using: sail monitor contact verify %s <code>' % subject)
		click.echo()
	elif request['status'] == 'ready':
		util.success('Contact added sucessfully, pre-verified')
	else:
		util.failure('Could not add this contact')

@contact.command()
@click.argument('subject', nargs=1, required=True)
def delete(subject):
	'''Delete a monitoring contact'''
	request = util.request('/premium/monitor/contacts/', method='Delete', json={
		'subject': subject,
	})

	util.success('Contact deleted successfully')

@contact.command()
@click.argument('subject', nargs=1, required=True)
@click.argument('code', nargs=1, required=True)
def verify(subject, code):
	'''Verify a monitoring contact'''
	request = util.request('/premium/monitor/contacts/verify/', method='POST', json={
		'subject': subject,
		'code': code,
	})

	util.success('Contact verified successfully')

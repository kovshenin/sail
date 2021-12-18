from sail import cli, util

import click
import re

from datetime import datetime
from prettytable import PrettyTable

@cli.group(invoke_without_command=True)
@click.pass_context
def monitor(ctx):
	'''Monitor your WordPress application uptime and health'''
	# Default subcommand for back-compat
	if not ctx.invoked_subcommand:
		return ctx.forward(status)

@monitor.command()
def status():
	'''Show the uptime and health of your application'''
	click.echo('Just a status')

@monitor.command()
def snooze():
	'''Snooze alerts for a period of time'''

@monitor.command()
def enable():
	'''Enable monitoring for this application'''

@monitor.command()
def disable():
	'''Disable monitoring for this application'''

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
		click.echo('No contacts found')
		click.echo('Add contacts using: sail monitor contact add SUBJECT')
		exit()

	t = PrettyTable(['Subject', 'Status'])

	for contact in contacts:
		t.add_row([contact['subject'], contact['status']])

	t.align = 'l'
	click.echo(t.get_string())

@contact.command()
@click.argument('subject', nargs=1, required=True)
def add(subject):
	'''Add a new contact for monitoring alerts'''
	request = util.request('/premium/monitor/contacts/', method='POST', json={
		'subject': subject,
	})

	if request['status'] == 'pending':
		click.echo('Contact added, pending verification')
		click.echo('Verify using: sail monitor contact verify %s CODE' % subject)
	elif request['status'] == 'ready':
		click.echo('Contact added sucessfully, pre-verified')
	else:
		click.echo('Could not add this contact')

@contact.command()
@click.argument('subject', nargs=1, required=True)
def delete(subject):
	'''Delete a monitoring contact'''
	request = util.request('/premium/monitor/contacts/', method='Delete', json={
		'subject': subject,
	})

	click.echo('Contact deleted successfully')

@contact.command()
@click.argument('subject', nargs=1, required=True)
@click.argument('code', nargs=1, required=True)
def verify(subject, code):
	'''Verify a monitoring contact'''
	request = util.request('/premium/monitor/contacts/verify/', method='POST', json={
		'subject': subject,
		'code': code,
	})

	click.echo('Contact verified successfully')

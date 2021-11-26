from sail import cli, util

import click, uuid, io, json
import shlex

@cli.group()
def cron():
	'''Add, delete, view and execute system cron jobs'''
	pass

@cron.command()
@click.option('--json', 'as_json', is_flag=True, help='Output in JSON format')
def list(as_json):
	'''Get a list of active cron jobs'''
	config = util.config()

	cron_data = config.get('cron', {})

	if as_json:
		click.echo(json.dumps(cron_data))
		return

	if len(cron_data) < 1:
		click.echo('No cron entries found')
		return

	click.echo('# System Cron Entries')
	for id, entry in cron_data.items():
		click.echo('- id: %s' % id)
		click.echo('  user: %s' % ('www-data' if not entry['root'] else 'root'))
		click.echo('  schedule: %s' % entry['schedule'])
		click.echo('  command: %s' % entry['command'])
		click.echo()

@cron.command()
@click.argument('id', nargs=1)
def delete(id):
	'''Delete a cron job by its id'''
	config = util.config()
	c = util.connection()

	cron_data = config.get('cron', {})

	if id not in cron_data:
		raise click.ClickException('Could not find cron entry by id.')

	del cron_data[id]
	config['cron'] = cron_data

	click.echo('- Updating .sail/config.json')
	util.update_config(config)

	click.echo('- Generating /etc/cron.d/sail-%s' % config['namespace'])
	_generate_cron()

@cron.command()
@click.argument('schedule', nargs=1)
@click.argument('command', nargs=-1)
@click.option('--root', is_flag=True, help='Run command as root')
def add(schedule, command, root):
	'''Add a new system cron job'''
	config = util.config()
	c = util.connection()

	if len(command) < 1:
		raise click.ClickException('Invalid cron command.')

	command = ' '.join(command)

	schedules = {
		'hourly': '0 * * * *',
		'twicedaily': '0 */12 * * *',
		'daily': '0 0 * * *',
		'weekly': '0 0 * * 0',
	}

	if schedules.get(schedule):
		schedule = schedules.get(schedule)

	# Verify schedule
	parts = schedule.split(' ')
	if len(parts) > 5:
		raise click.ClickException('Invalid schedule.')

	# Extend short-hand */1
	if len(parts) < 5:
		parts.extend(['*'] * (5 - len(parts)))

	schedule = ' '.join(parts)

	cron_data = config.get('cron', {})

	id = str(uuid.uuid4())
	if cron_data.get(id):
		raise click.ClickException('UUID collision, try again.')

	cron_data[id] = {
		'root': root,
		'schedule': schedule,
		'command': command,
	}

	config['cron'] = cron_data
	click.echo('- Updating .sail/config.json')
	util.update_config(config)

	click.echo('- Generating /etc/cron.d/sail-%s' % config['namespace'])
	_generate_cron()

def _generate_cron():
	config = util.config()
	c = util.connection()

	cron_data = config.get('cron', {})

	if len(cron_data) < 1:
		c.run('rm /etc/cron.d/sail-%s' % config['namespace'])
		return

	contents = []
	contents.append('SHELL=/bin/sh')
	contents.append('PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin')

	for id, entry in cron_data.items():
		schedule = entry['schedule']
		user = 'www-data' if not entry['root'] else 'root'
		command = 'cd %s && %s' % (util.remote_path('public'), entry['command'])
		contents.append(f'{schedule} {user} {command}')

	# Cron needs an empty line before EOF.
	contents.append('')

	c.put(io.StringIO('\n'.join(contents)), '/etc/cron.d/sail-%s' % config['namespace'])
	c.run('chmod 0600 /etc/cron.d/sail-%s' % config['namespace'])

@cron.command()
@click.argument('id', nargs=1)
def run(id):
	'''Run a system cron job by id'''
	config = util.config()
	c = util.connection()

	cron_data = config.get('cron', {})

	if id not in cron_data:
		raise click.ClickException('Could not find cron entry by id.')

	entry = cron_data[id]
	user = 'root' if entry['root'] else 'www-data'

	command = shlex.join(['PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin',
		'cd', util.remote_path('public')])
	command += ' && ' + entry['command']

	result = c.run(shlex.join(['sudo', '-u', user, 'env', '-i', '/bin/sh', '-c', command]))

	if result.stderr:
		click.echo(result.stderr, err=True, nl=False)

	if result.stdout:
		click.echo(result.stdout, nl=False)

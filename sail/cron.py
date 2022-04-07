from sail import cli, util

import click, uuid, io, json
import shlex, hashlib

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

	util.label_width(10)

	click.echo()
	for id, entry in cron_data.items():
		label = util.label('Id:')
		click.echo(f'{label} {id}')

		label = util.label('User:')
		user = ('www-data' if not entry['root'] else 'root')
		click.echo(f'{label} {user}')

		label = util.label('Schedule:')
		schedule = entry['schedule']
		click.echo(f'{label} {schedule}')

		label = util.label('Command:')
		command = entry['command']
		click.echo(f'{label} {command}')
		click.echo()

@cron.command()
@click.argument('id', nargs=1)
def delete(id):
	'''Delete a cron job by its id'''
	config = util.config()
	c = util.connection()

	cron_data = config.get('cron', {})

	if id not in cron_data:
		raise util.SailException('Could not find cron entry by id.')

	del cron_data[id]
	config['cron'] = cron_data

	util.heading('Deleting cron job')
	util.item('Updating .sail/config.json')
	util.update_config(config)

	util.item('Generating /etc/cron.d entry')
	_generate_cron()

	util.success('Cron job delete successfully')

@cron.command()
@click.argument('schedule', nargs=1)
@click.argument('command', nargs=-1)
@click.option('--root', is_flag=True, help='Run command as root')
@click.option('--quiet', '-q', is_flag=True, help='Suppress output')
def add(schedule, command, root, quiet):
	'''Add a new system cron job'''
	config = util.config()
	c = util.connection()

	if len(command) < 1:
		raise util.SailException('Invalid cron command.')

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
		raise util.SailException('Invalid schedule.')

	# Extend short-hand */1
	if len(parts) < 5:
		parts.extend(['*'] * (5 - len(parts)))

	schedule = ' '.join(parts)

	cron_data = config.get('cron', {})

	id = str(uuid.uuid4())
	if cron_data.get(id):
		raise util.SailException('UUID collision, try again.')

	cron_data[id] = {
		'root': root,
		'schedule': schedule,
		'command': command,
	}

	config['cron'] = cron_data

	if not quiet:
		util.heading('Adding a cron job')
		util.item('Updating .sail/config.json')

	util.update_config(config)

	if not quiet:
		util.item('Generating /etc/cron.d entry')

	_generate_cron()

	if not quiet:
		util.success('Cron job added successfully')

def _generate_cron():
	config = util.config()
	c = util.connection()

	cron_data = config.get('cron', {})

	c.run('rm /etc/cron.d/sail-%s' % config['namespace'], warn=True) # back-compat
	filename = 'sail-%s-%s' % (config['namespace'].replace('.', '_'), hashlib.md5(config['namespace'].encode('utf8')).hexdigest()[:8])

	if len(cron_data) < 1:
		c.run(f'rm /etc/cron.d/{filename}', warn=True)
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

	c.put(io.StringIO('\n'.join(contents)), f'/etc/cron.d/{filename}')
	c.run(f'chmod 0600 /etc/cron.d/{filename}')

@cron.command()
@click.argument('id', nargs=1)
def run(id):
	'''Run a system cron job by id'''
	config = util.config()
	c = util.connection()

	cron_data = config.get('cron', {})

	if id not in cron_data:
		raise util.SailException('Could not find cron entry by id.')

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

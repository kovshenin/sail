import sail

import time, pathlib, os
import json, click, requests

_debug = False
def debug(set=None):
	'''Get or set debug mode'''
	global _debug

	if set is None:
		return _debug

	_debug = set
	return _debug

def dlog(line):
	'''Print debug output'''
	if not debug():
		return

	click.secho('(debug) %s' % line, fg='yellow')

def request(endpoint, **kwargs):
	'''Request the Sail API endpoint'''

	method = kwargs.get('method')
	params = kwargs.get('params', {})
	json = kwargs.get('json', {})
	anon = kwargs.get('anon', False)

	api_base = get_sail_default('api-base')
	if not api_base:
		api_base = sail.API_BASE

	headers = {}

	if not anon:
		sail_config = get_sail_config()
		headers = {
			'X-App-Id': sail_config['app_id'],
			'X-App-Secret': sail_config['secret'],
		}

	if not method:
		method = 'POST' if json else 'GET'

	url = '%s/%s' % (api_base.rstrip('/'), endpoint.lstrip('/'))

	if debug():
		safe_headers = headers.copy()
		if 'X-App-Secret' in safe_headers:
			safe_headers['X-App-Secret'] = '*'*8

		dlog('Requesting: [%s] %s' % (method, url))
		dlog('Request headers: %s' % repr(safe_headers))
		dlog('Request params: %s' % repr(params))
		dlog('Request json: %s' % repr(json))

	request = requests.Request(method, url, headers=headers, params=params)

	if method == 'POST' or json:
		request.json = json

	request = request.prepare()
	session = requests.Session()

	try:
		response = session.send(request)
	except Exception as e:
		dlog('Exception: %s' % repr(e))
		raise click.ClickException('Could not contact the Sail API. Try again later.')

	dlog('Response: [%d] %s' % (response.status_code, repr(response.text)))

	try:
		data = response.json()
	except Exception as e:
		dlog('Exception: %s' % repr(e))
		raise click.ClickException('Invalid response from the Sail API. Try again later.')

	if not response.ok:
		raise click.ClickException('API error: %s' % data.get('error'))

	return data

def wait_for_task(task_id, timeout=30, interval=1):
	feedback_processed = []
	data = {}

	def _wait():
		nonlocal data

		data = request('/status/%s/' % task_id)
		feedback = data.get('feedback', [])
		if feedback:
			for line in feedback:
				if line in feedback_processed:
					continue

				feedback_processed.append(line)
				click.echo('- %s' % line)

		if data.get('task_state') == 'failure':
			raise click.ClickException('Task state failure')

		return data.get('task_state') == 'success'

	wait(_wait, timeout=timeout, interval=interval)
	return data

def wait(condition, timeout=30, interval=1, *args):
	'''Wait for condition every interval or timeout.'''
	start = time.time()
	while not condition(*args):
		if time.time() - start > timeout:
			raise Exception('Timeout in util.wait()')

		time.sleep(interval)

def find_root():
	p = pathlib.Path()
	p = p.resolve()

	while p.parent and str(p) != '/':
		for x in p.iterdir():
			if x.stem == '.sail':
				return str(p)

		p = p.parent

def get_sail_config():
	root = find_root()

	if not root:
		raise click.ClickException('Could not parse .sail/config.json. If this is a new project run: sail init')

	with open(root + '/.sail/config.json') as f:
		config = json.load(f)

	if not config:
		raise click.ClickException('Could not parse .sail/config.json. If this is a new project run: sail init')

	return config

loader_i = 0

def loader():
	global loader_i

	frames = [
		"   ",
		".  ",
		".. ",
		"...",
	]

	click.echo(frames[loader_i % len(frames)] + '\r', nl=False)
	loader_i += 1
	time.sleep(.2)

def get_sail_default(name):
	'''Get a sail default config variable'''
	import pathlib, json
	filename = (pathlib.Path.home() / '.sail-defaults.json').resolve()
	data = {}

	try:
		with open(filename) as f:
			data = json.load(f)
			return data[name]
	except:
		return None

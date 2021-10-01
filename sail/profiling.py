from sail import cli, util

import click, pathlib, json
import os
import webbrowser

from curses import wrapper, curs_set
import curses
import textwrap
from random import randrange

@cli.command('profile')
@click.argument('path', nargs=1)
def profile(path):
	path = pathlib.Path(path)
	if not path.exists() or not path.is_file():
		raise click.ClickException('Invalid file')

	with path.open('r') as f:
		xhprof_data = json.load(f)

	totals = {'ct': 0, 'wt': 0, 'ut': 0, 'st': 0, 'cpu': 0, 'mu': 0, 'pmu': 0, 'samples': 0,
		'queries': 0, 'http_reqs': 0}

	metrics = []
	for key in totals.keys():
		if key in xhprof_data['main()']:
			metrics.append(key)

	data = {}

	# Compute inclusive times
	for func, info in xhprof_data.items():
		try:
			parent, child = func.split('==>')
		except:
			child = func
			parent = None

		if child not in data:
			data[child] = {'ct': 0, 'wt': 0, 'ut': 0, 'st': 0, 'cpu': 0,
				'mu': 0, 'pmu': 0, 'samples': 0, 'parents': [], 'children': []}

		for metric in metrics:
			data[child][metric] += info[metric]

		# More counts
		func = child.split('#', 1)[0]
		if func in ['mysqli_query', 'mysql_query', 'mysqli::query']:
			totals['queries'] += data[child]['ct']
		elif func in ['curl_exec']:
			totals['http_reqs'] += data[child]['ct']

	for metric in metrics:
		totals[metric] = data['main()'][metric]

	# Reset the calls, we'll count them again
	totals['ct'] = 0

	for child, info in data.items():
		totals['ct'] += info['ct']
		for metric in metrics:
			data[child]['excl_' + metric] = info[metric]

	for func, info in xhprof_data.items():
		try:
			parent, child = func.split('==>')
		except:
			child = func
			parent = None

		if not parent:
			continue

		data[child]['parents'].append(parent)
		data[parent]['children'].append(child)

		for metric in metrics:
			data[parent]['excl_' + metric] -= info[metric]

	os.environ.setdefault('ESCDELAY', '10')
	wrapper(_profile, data=data, totals=totals)

def _render_summary(pad, totals):
	pad.addstr(0, 0, 'Run: ', curses.color_pair(1))
	pad.addstr('#12448', curses.color_pair(2))
	pad.addstr(' Wall Time: ', curses.color_pair(1))
	pad.addstr('{:,} ms'.format(totals['wt']), curses.color_pair(2))
	pad.addstr(' Peak Memory: ', curses.color_pair(1))
	pad.insstr('{:,.2f} mb'.format(totals['pmu']/1024/1024), curses.color_pair(2))

	pad.addstr(1, 0, 'URL: ', curses.color_pair(1))
	pad.addstr(1, 5, '/wp-admin/admin-ajax.php?_doing_cron=123781293712&_t=1991299921&action=none&cache-buster=chuck-norris', curses.color_pair(2))

	pad.addstr(2, 0, 'Method: ', curses.color_pair(1))
	pad.addstr('POST', curses.color_pair(2))

	pad.addstr(' Function Calls: ', curses.color_pair(1))
	pad.addstr('{:,}'.format(totals['ct']), curses.color_pair(2))
	pad.addstr(' Queries: ', curses.color_pair(1))
	pad.addstr('{:,}'.format(totals['queries']), curses.color_pair(2))
	pad.addstr(' HTTP Reqs: ', curses.color_pair(1))
	pad.addstr('{:,}'.format(totals['http_reqs']), curses.color_pair(2))

def _render_listview(pad, columns, data, cols, selected = 0):
	y = -1
	for entry in data:
		y += 1

		if y == selected:
			pad.attron(curses.color_pair(4) if curses.has_colors() else curses.A_REVERSE)
		else:
			pad.attroff(curses.color_pair(4) if curses.has_colors() else curses.A_REVERSE)

		if 'header' in entry:
			pad.attron(curses.color_pair(3) if curses.has_colors() else curses.A_REVERSE)
			pad.hline(y, 0, ' ', cols)
			pad.addstr(y, 0, '  ' + entry['header'])
			pad.attroff(curses.color_pair(3) if curses.has_colors() else curses.A_REVERSE)
			continue

		if 'space' in entry:
			pad.hline(y, 0, ' ', cols)
			continue

		if 'meta' in entry:
			if y != selected:
				pad.attron(curses.color_pair(5))
			pad.hline(y, 0, ' ', cols)
			pad.insstr(y, 0, '  ' + entry['meta'])
			if y != selected:
				pad.attroff(curses.color_pair(5))

			continue

		label = entry['label']
		args = entry.get('args')

		pad.hline(y, 0, ' ', cols)
		pad.addstr(y, 0, '  ' + label)
		if args:
			if y != selected:
				pad.attron(curses.color_pair(5))
			pad.insstr(' => ' + args)
			if y != selected:
				pad.attroff(curses.color_pair(5))
		for column in reversed(columns):
			pad.insstr(y, cols - sum([i['width'] for i in columns]) - 2, '{:,}'.format(entry[column['key']]).rjust(column['width']))

		pad.insstr(y, cols-2, '  ')

def _render_footer(pad, selected, max, cols):
	max -= 1 # selected is 0-based
	pad.attron(curses.color_pair(1))
	pad.hline(0, 0, '-', cols)
	label = ' %d/%d %d%% ' % (selected, max, selected/max * 100)
	pad.insstr(0, cols - len(label) - 1, label )
	pad.attroff(curses.color_pair(1))

def _render_sticky_header(pad, columns, data, cols, offset_y):
	header = None
	i = offset_y
	while not header and i >= 0:
		if 'header' in data[i]:
			header = data[i]

		i -= 1

	if not header:
		return

	pad.attron(curses.color_pair(3) if curses.has_colors() else curses.A_REVERSE)
	pad.hline(0, 0, ' ', cols)
	# pad.addstr(0, 0, 'Off: %d, sel: %d, i: %d' % (offset_y, selected, i))
	pad.addstr(0, 0, '  ' + header['header'])

	for column in reversed(columns):
		label = column['label']
		if 'sort' in column:
			label = '>' + label
		else:
			label = ' ' + label

		pad.insstr(0, cols - sum([i['width'] for i in columns]) - 2, label.rjust(column['width']))

	pad.attroff(curses.color_pair(3) if curses.has_colors() else curses.A_REVERSE)

def _render_view_symbol(stdscr, data, totals, symbol, selected=1, sort=2):
	rows, cols = stdscr.getmaxyx()

	columns = _columns();
	for column in columns:
		column['width'] = max(len(column['label']), len('{:,}'.format(max([i[column['key']] for _, i in data.items()])))) + 2

	sort_key = columns[sort]['key']
	columns[sort]['sort'] = True
	listview_data = [{'header': 'Function'}]

	entry = data[symbol]

	item = {'function': symbol, 'label': symbol}

	meta = None
	expand_meta_for = [
		'mysqli_query',
		'mysql_query',
		'curl_exec',
		'mysqli::query',
		'{closure}',
	]

	if '#' in symbol:
		item['label'], args = symbol.split('#', 1)

		if item['label'] in expand_meta_for:
			meta = []
			for line in textwrap.wrap(args, cols - 4):
				meta.append({'meta': line})
		else:
			item['args'] = args

	for col in columns:
		item[col['key']] = entry[col['key']]

	listview_data.append(item)
	if meta:
		listview_data.append({'space': ''})
		listview_data.extend(meta)

	if len(set(entry['parents'])):
		listview_data.append({'space': ''})
		listview_data.append({'header': 'Parent functions'})
		parents = []

		for parent in entry['parents']:
			item = {'function': parent, 'label': parent}

			if '#' in parent:
				item['label'], item['args'] = parent.split('#', 1)

			for col in columns:
				item[col['key']] = data[parent][col['key']]

			parents.append(item)

		listview_data.extend(sorted(parents, key=lambda x: x[sort_key], reverse=True))

	if len(set(entry['children'])):
		listview_data.append({'space': ''})
		listview_data.append({'header': 'Child functions'})
		children = []

		for child in entry['children']:
			item = {'function': child, 'label': child}

			if '#' in child:
				item['label'], item['args'] = child.split('#', 1)

			for col in columns:
				item[col['key']] = data[child][col['key']]

			children.append(item)

		listview_data.extend(sorted(children, key=lambda x: x[sort_key], reverse=True))

	summary = curses.newpad(3, cols)
	listview = curses.newpad(len(listview_data), cols)
	sticky_header = curses.newpad(1, cols)
	footer = curses.newpad(1, cols)

	_render_summary(summary, totals)
	summary.refresh(0,0, 0,0, 4, cols - 1)

	visible = rows - 6
	offset_y = 0
	refresh = True

	while True:
		if selected > visible + offset_y:
			offset_y = selected - visible
		elif selected <= offset_y:
			offset_y = selected - 1

		if refresh:
			_render_listview(listview, columns, listview_data, cols, selected)
			listview.refresh(offset_y,0, 4,0, rows - 2, cols - 1)

			_render_sticky_header(sticky_header, columns, listview_data, cols, offset_y)
			sticky_header.refresh(0,0, 4,0, 6, cols -1)

			_render_footer(footer, selected, len(listview_data), cols)
			footer.refresh(0,0, rows-1,0, rows-1,cols-1)

		c = stdscr.getch()
		selected, refresh = _handle_scroll(c, listview_data, visible, selected, refresh)

		# Sorting
		if c == curses.KEY_RIGHT or c == ord('>'):
			next = min(sort + 1, len(columns) - 1)
			if next == sort:
				continue

			return ('sort', next)

		elif c == curses.KEY_LEFT or c == ord('<'):
			prev = max(sort - 1, 0)
			if prev == sort:
				continue

			return ('sort', prev)

		elif c == 27:
			return 'view_main'

		elif c == curses.KEY_BACKSPACE or c == 127 or c == '\b':
			return 'pop' # previous symbol or main

		elif c == curses.KEY_ENTER or c == 13 or c == 10:
			if 'function' not in listview_data[selected]:
				continue

			# First item is the function itself, don't select it.
			if selected == 1:
				continue

			return ('view_symbol', listview_data[selected]['function'], selected)

		elif c == ord('q'):
			return 'exit'

		elif c == curses.KEY_RESIZE:
			return 'resize'

def _render_view_main(stdscr, data, totals, selected=1, sort=2):
	rows, cols = stdscr.getmaxyx()

	columns = _columns()
	for column in columns:
		column['width'] = max(len(column['label']), len('{:,}'.format(max([i[column['key']] for _, i in data.items()])))) + 2

	listview_data = [
		{'header': 'Functions'},
	]

	sort_key = columns[sort]['key']
	columns[sort]['sort'] = True

	for func, info in sorted(data.items(), key=lambda x: x[1][sort_key], reverse=True):
		item = {'function': func, 'label': func}

		if '#' in func:
			item['label'], item['args'] = func.split('#', 1)

		for col in columns:
			item[col['key']] = info[col['key']]

		listview_data.append(item)

	summary = curses.newpad(3, cols)
	listview = curses.newpad(len(listview_data), cols)
	sticky_header = curses.newpad(1, cols)
	footer = curses.newpad(1, cols)

	_render_summary(summary, totals)
	summary.refresh(0,0, 0,0, 4, cols - 1)

	offset_y = 0
	visible = rows - 6
	refresh = True

	while True:
		if selected > visible + offset_y:
			offset_y = selected - visible
		elif selected <= offset_y:
			offset_y = selected - 1

		if refresh:
			_render_listview(listview, columns, listview_data, cols, selected)
			listview.refresh(offset_y,0, 4,0, rows-2,cols-1)

			_render_sticky_header(sticky_header, columns, listview_data, cols, offset_y)
			sticky_header.refresh(0,0, 4,0, 6,cols-1)

			_render_footer(footer, selected, len(listview_data), cols)
			footer.refresh(0,0, rows-1,0, rows-1,cols-1)
			refresh = False

		c = stdscr.getch()
		selected, refresh = _handle_scroll(c, listview_data, visible, selected, refresh)

		# Sorting
		if c == curses.KEY_RIGHT or c == ord('>'):
			next = min(sort + 1, len(columns) - 1)
			if next == sort:
				continue

			return ('sort', next)

		elif c == curses.KEY_LEFT or c == ord('<'):
			prev = max(sort - 1, 0)
			if prev == sort:
				continue

			return ('sort', prev)

		elif c == curses.KEY_ENTER or c == 13 or c == 10:
			if 'header' in listview_data[selected] or 'space' in listview_data[selected]:
				continue

			return ('view_symbol', listview_data[selected]['function'], selected)

		elif c == ord('q'):
			return 'exit'

		elif c == curses.KEY_RESIZE:
			return 'resize'

def _profile(stdscr, data, totals):
	try:
		curs_set(False)
	except curses.error:
		pass

	current_view = _render_view_main
	args = [stdscr, data, totals]
	kwargs = {'selected': 1}
	sort = 2
	view_stack = []

	if curses.has_colors():
		curses.init_pair(1, 247, curses.COLOR_BLACK)
		curses.init_pair(2, 255, curses.COLOR_BLACK)
		curses.init_pair(3, 0, 245)
		curses.init_pair(4, 0, 255)
		curses.init_pair(5, 247, curses.COLOR_BLACK)

	while True:
		stdscr.refresh()
		kwargs['sort'] = sort

		try:
			r = current_view(*args, **kwargs)
		except curses.error:
			continue

		# Exit
		if r == 'exit' or r is None:
			print('\n')
			stdscr.erase()
			break

		# Escape back to main view
		if r == 'view_main':
			stdscr.erase()

			if view_stack:
				current_view, args, kwargs = view_stack.pop(0)
				view_stack = []
				continue

			current_view = _render_view_main
			args = [stdscr, data, totals]
			kwargs = {}
			continue

		if r == 'pop':
			stdscr.erase()

			# Pop back to the main view
			if len(view_stack) < 1:
				current_view = _render_view_main
				args = [stdscr, data, totals]
				continue

			# Pop back to the previous symbol
			current_view, args, kwargs = view_stack.pop()
			continue

		if r == 'resize':
			stdscr.erase()
			continue

		if r[0] == 'sort':
			_, sort = r
			kwargs['selected'] = 1
			continue

		# Enter symbol view
		if r[0] == 'view_symbol':
			view, symbol, selected = r

			# Push current settings to the stack
			kwargs['selected'] = selected
			view_stack.append((current_view, args, kwargs))

			current_view = _render_view_symbol
			args = [stdscr, data, totals]
			kwargs = {'symbol': symbol}
			stdscr.erase()
			continue

		stdscr.clear()
		stdscr.addstr(0, 0, repr(r))
		stdscr.refresh()
		stdscr.getch()
		break

def _columns():
	return [
		{'key': 'ct', 'label': 'Count', 'width': 10},
		{'key': 'wt', 'label': 'iWT', 'width': 10},
		{'key': 'excl_wt', 'label': 'eWT', 'width': 10},
		{'key': 'mu', 'label': 'iMEM', 'width': 10},
		{'key': 'excl_mu', 'label': 'eMEM', 'width': 10},
	]

def _is_valid(items, i):
	return 'header' not in items[i] and 'space' not in items[i]

def _closest_valid(items, current, step=1):
	i = current
	while True:
		i += step

		if i > len(items) - 1 or i < 0:
			return current

		if _is_valid(items, i):
			return i

def _handle_scroll(c, listview_data, visible, selected, refresh):
	_refresh = refresh

	if c == curses.KEY_UP:
		prev = _closest_valid(listview_data, selected, -1)
		_refresh = prev != selected
		selected = prev
	elif c == curses.KEY_DOWN:
		next = _closest_valid(listview_data, selected, +1)
		_refresh = next != selected
		selected = next
	elif c == curses.KEY_PPAGE:
		prev = max([selected - visible, 0])
		if not _is_valid(listview_data, prev):
			prev = _closest_valid(listview_data, prev, +1)
		_refresh = prev != selected
		selected = prev
	elif c == curses.KEY_NPAGE:
		next = min([selected + visible, len(listview_data) - 1])
		if not _is_valid(listview_data, next):
			next = _closest_valid(listview_data, next, -1)
		_refresh = next != selected
		selected = next
	elif c == curses.KEY_HOME:
		home = 0
		if not _is_valid(listview_data, home):
			home = _closest_valid(listview_data, home, +1)
		_refresh = home != selected
		selected = home
	elif c == curses.KEY_END:
		end = len(listview_data) - 1
		if not _is_valid(listview_data, end):
			end = _closest_valid(listview_data, end, -1)
		_refresh = end != selected
		selected = end

	return selected, refresh or _refresh

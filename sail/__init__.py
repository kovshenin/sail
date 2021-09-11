from .__version__ import __version__, __title__, __description__, __url__
from .__version__ import __author__, __author_email__, __license__, __copyright__

API_BASE = 'https://sailed.io/api/1.0'

from sail import util

import click

@click.group()
@click.version_option(__version__, '--version', '-v', message='%(version)s')
@click.option('--debug', '-d', is_flag=True, help='Enable verbose debug logging')
def cli(debug):
	util.debug(debug)

# Command groups
from sail import provision, deploy, database, backups, domains, misc

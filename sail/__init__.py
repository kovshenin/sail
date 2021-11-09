import os

from .__version__ import __version__, __title__, __description__, __url__
from .__version__ import __author__, __author_email__, __license__, __copyright__

API_BASE = 'https://sailed.io/api/1.1'
DEFAULT_IMAGE = 'ubuntu-20-04-x64'
TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), 'templates')

from sail import util

import click

@click.group()
@click.version_option(__version__, '--version', '-v', message='%(version)s')
@click.option('--debug', '-d', is_flag=True, help='Enable verbose debug logging')
def cli(debug):
	util.debug(debug)

# Command groups
from sail import provision, deploy, database, backups, domains, misc, profiling
from sail import ssh, blueprints

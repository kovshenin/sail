from importlib import metadata

try:
    version = metadata.version('sailed.io')
except metadata.PackageNotFoundError:
    version = '0.0+unknown'

__title__ = 'sail'
__description__ = 'CLI tool to deploy and manage WordPress applications on DigitalOcean'
__version__ = version
__author__ = 'Konstantin Kovshenin'
__author_email__ = 'kovshenin@gmail.com'
__url__ = 'https://sailed.io'
__license__ = 'GPLv3'
__copyright__ = 'Copyright 2021-2023 Konstantin Kovshenin'

from setuptools import setup
from setuptools import find_packages
import os, pathlib

import sail

p = pathlib.Path(__file__)
p = p.parent.resolve()
requirements = str(p) + '/requirements.txt'

with open(requirements) as f:
	install_reqs = f.read().splitlines()

setup(
	name='sailed.io',
	version=sail.__version__,
	description=sail.__description__,
	author=sail.__author__,
	author_email=sail.__author_email__,
	url=sail.__url__,
	install_requires=install_reqs,
	include_package_data=True,
	packages=find_packages(),
	entry_points={
		'console_scripts': ['sail=sail:cli']
	},
)

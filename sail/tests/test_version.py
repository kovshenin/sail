from sail import cli, __version__

import unittest
from click.testing import CliRunner

class TestVersion(unittest.TestCase):
	def test_version(self):
		runner = CliRunner()
		result = runner.invoke(cli, ['--version'])
		self.assertEqual(result.exit_code, 0)
		self.assertEqual(result.output, __version__ + '\n')

	def test_version_short(self):
		runner = CliRunner()
		result = runner.invoke(cli, ['-v'])
		self.assertEqual(result.exit_code, 0)
		self.assertEqual(result.output, __version__ + '\n')

# Relative import
import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent.parent.resolve()))
from sail import cli

import io
import click
import unittest
import subprocess
import requests
from click.testing import CliRunner
from unittest.mock import Mock, patch

# Some commands use os.execlp to pass control to the
# child process, which stops test execution after the
# spawned process exits. We can mock it and just pipe
# to a regular subprocess.
def _execlp_side_effect(*args, **kwargs):
	print(subprocess.check_output(args[1:], encoding='utf8'))

_execlp = Mock(side_effect=_execlp_side_effect)

@patch('os.execlp', _execlp)
@unittest.skipIf(__name__ != '__main__', 'Slow test, must run explicitly')
class TestEnd2End(unittest.TestCase):
	def setUp(self):
		pass

	def test_end2end(self):
		runner = CliRunner(mix_stderr=False)

		with runner.isolated_filesystem():
			result = runner.invoke(cli, ['config', 'api-base', 'http://127.0.0.1:5000/api/1.0/'])
			self.assertEqual(result.exit_code, 0)
			self.assertIn('Option api-base set', result.output)

			# Init
			result = runner.invoke(cli, ['init'])
			print(result.output)
			self.assertIn('Success. The ship has sailed!', result.output)
			self.assertEqual(result.exit_code, 0)

			result = runner.invoke(cli, ['wp', 'option', 'get', 'home'])
			print(result.output)
			self.assertEqual(result.exit_code, 0)
			home = result.output.strip()

			# Import some media
			result = runner.invoke(cli, ['wp', 'media', 'import', 'https://s.w.org/style/images/wp-header-logo.png'])
			print(result.output)
			self.assertEqual(result.exit_code, 0)
			self.assertIn('Imported file', result.output)

			# Download
			result = runner.invoke(cli, ['download', '-y'])
			print(result.output)
			self.assertEqual(result.exit_code, 0)

			# Uploaded file shouldn't be here as we skip uploads by default
			found = subprocess.check_output(['find', '.', '-type', 'f', '-name', 'wp-header-logo.png'], encoding='utf8')
			self.assertNotIn('wp-header-logo.png', found)

			# With uploads now
			result = runner.invoke(cli, ['download', '-y', '--with-uploads'])
			print(result.output)
			self.assertEqual(result.exit_code, 0)

			# File should now be downloaded.
			found = subprocess.check_output(['find', '.', '-type', 'f', '-name', 'wp-header-logo.png'], encoding='utf8')
			self.assertIn('wp-header-logo.png', found)

			# Test PHP
			with open('test.php', 'w') as f:
				f.write('<?php\necho "%s";' % home)

			# Deploy the test file
			result = runner.invoke(cli, ['deploy'])
			print(result.output)
			self.assertEqual(result.exit_code, 0)

			response = requests.get('%s/test.php' % home)
			self.assertTrue(response.ok)
			self.assertEqual(home, response.text)

			# Clean up
			result = runner.invoke(cli, ['destroy', '-y'])
			print(result.output)
			self.assertEqual(result.exit_code, 0)

if __name__ == '__main__':
	unittest.main()

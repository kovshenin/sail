# Relative import
import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent.parent.resolve()))
from sail import cli

import io, os
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
	@classmethod
	def setUpClass(cls):
		cls.runner = CliRunner(mix_stderr=False)
		cls.fs = cls.runner.isolated_filesystem()
		cls.fs.__enter__()
		cls.home = None

	@classmethod
	def tearDownClass(cls):
		cls.fs.__exit__(None, None, None)

	def setUp(self):
		self.home = self.__class__.home

	def test_000_config(self):
		api_base = 'http://127.0.0.1:5000/api/1.0/'

		# Allows running this on the production API server if explicitly asked.
		if 'SAIL_API_BASE' in os.environ:
			api_base = os.environ['SAIL_API_BASE']

		result = self.runner.invoke(cli, ['config', 'api-base', api_base])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Option api-base set', result.output)

	def test_001_init(self):
		result = self.runner.invoke(cli, ['init'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Success. The ship has sailed!', result.output)

	def test_002_wp_home(self):
		result = self.runner.invoke(cli, ['wp', 'option', 'get', 'home'])
		self.assertEqual(result.exit_code, 0)
		self.__class__.home = result.output.strip()

	def test_003_wp_media_import(self):
		result = self.runner.invoke(cli, ['wp', 'media', 'import', 'https://s.w.org/style/images/wp-header-logo.png'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Imported file', result.output)

	def test_004_download(self):
		result = self.runner.invoke(cli, ['download', '-y'])
		self.assertEqual(result.exit_code, 0)

		# Uploaded file shouldn't be here as we skip uploads by default
		found = subprocess.check_output(['find', '.', '-type', 'f', '-name', 'wp-header-logo.png'], encoding='utf8')
		self.assertNotIn('wp-header-logo.png', found)

		# With uploads now
		result = self.runner.invoke(cli, ['download', '-y', '--with-uploads'])
		self.assertEqual(result.exit_code, 0)

		# File should now be downloaded.
		found = subprocess.check_output(['find', '.', '-type', 'f', '-name', 'wp-header-logo.png'], encoding='utf8')
		self.assertIn('wp-header-logo.png', found)

	def test_005_php(self):
		with open('test.php', 'w') as f:
			f.write('<?php\necho "%s";' % self.home)

		# Deploy the test file
		result = self.runner.invoke(cli, ['deploy'])
		self.assertEqual(result.exit_code, 0)

		response = requests.get('%s/test.php' % self.home)
		self.assertTrue(response.ok)
		self.assertEqual(self.home, response.text)

	def test_006_deploy(self):
		with open('test1.php', 'w') as f:
			f.write('1')
		with open('test2.php', 'w') as f:
			f.write('2')

		# Make sure dry-run is working
		result = self.runner.invoke(cli, ['deploy', '--dry-run'])
		self.assertEqual(result.exit_code, 0)
		self.assertFalse(requests.get('%s/test1.php' % self.home).ok)

		# Test partial deploys
		result = self.runner.invoke(cli, ['deploy', 'test2.php'])
		self.assertEqual(result.exit_code, 0)
		self.assertFalse(requests.get('%s/test1.php' % self.home).ok)
		self.assertTrue(requests.get('%s/test2.php' % self.home).ok)

		result = self.runner.invoke(cli, ['deploy', 'test1.php'])
		self.assertEqual(result.exit_code, 0)
		self.assertTrue(requests.get('%s/test1.php' % self.home).ok)

		os.unlink('test1.php')
		result = self.runner.invoke(cli, ['deploy'])
		self.assertEqual(result.exit_code, 0)
		self.assertFalse(requests.get('%s/test1.php' % self.home).ok)
		self.assertTrue(requests.get('%s/test2.php' % self.home).ok)

		with open('test3.php', 'w') as f:
			f.write('3')
		with open('wp-content/test3.php', 'w') as f:
			f.write('also 3')
		with open('wp-content/plugins/test3.php', 'w') as f:
			f.write('three here as well')

		result = self.runner.invoke(cli, ['deploy', 'wp-content'])
		self.assertEqual(result.exit_code, 0)
		self.assertFalse(requests.get('%s/test3.php' % self.home).ok)
		self.assertTrue(requests.get('%s/wp-content/test3.php' % self.home).ok)
		self.assertTrue(requests.get('%s/wp-content/plugins/test3.php' % self.home).ok)

		os.unlink('wp-content/plugins/test3.php')
		result = self.runner.invoke(cli, ['deploy', 'wp-content/plugins'])
		self.assertEqual(result.exit_code, 0)
		self.assertFalse(requests.get('%s/test3.php' % self.home).ok)
		self.assertTrue(requests.get('%s/wp-content/test3.php' % self.home).ok)
		self.assertFalse(requests.get('%s/wp-content/plugins/test3.php' % self.home).ok)

		# Test wp-content/upload deploys --with-uploads
		with open('wp-content/uploads/test4.txt', 'w') as f:
			f.write('4')
		with open('wp-content/uploads/test5.txt', 'w') as f:
			f.write('5')

		result = self.runner.invoke(cli, ['deploy'])
		self.assertEqual(result.exit_code, 0)
		self.assertFalse(requests.get('%s/wp-content/uploads/test4.txt' % self.home).ok)
		self.assertFalse(requests.get('%s/wp-content/uploads/test5.txt' % self.home).ok)

		result = self.runner.invoke(cli, ['deploy', 'wp-content/uploads'])
		self.assertEqual(result.exit_code, 0)
		self.assertFalse(requests.get('%s/wp-content/uploads/test4.txt' % self.home).ok)
		self.assertFalse(requests.get('%s/wp-content/uploads/test5.txt' % self.home).ok)

		result = self.runner.invoke(cli, ['deploy', 'wp-content/uploads/test4.txt'])
		self.assertEqual(result.exit_code, 0)
		self.assertFalse(requests.get('%s/wp-content/uploads/test4.txt' % self.home).ok)
		self.assertFalse(requests.get('%s/wp-content/uploads/test5.txt' % self.home).ok)

		result = self.runner.invoke(cli, ['deploy', 'wp-content/uploads/test4.txt', '--with-uploads'])
		self.assertEqual(result.exit_code, 0)
		self.assertTrue(requests.get('%s/wp-content/uploads/test4.txt' % self.home).ok)
		self.assertFalse(requests.get('%s/wp-content/uploads/test5.txt' % self.home).ok)

		result = self.runner.invoke(cli, ['deploy', 'wp-content/uploads', '--with-uploads'])
		self.assertEqual(result.exit_code, 0)
		self.assertTrue(requests.get('%s/wp-content/uploads/test4.txt' % self.home).ok)
		self.assertTrue(requests.get('%s/wp-content/uploads/test5.txt' % self.home).ok)

		# Test both app and uploads deploys
		with open('test6.txt', 'w') as f:
			f.write('6')
		with open('wp-content/uploads/test7.txt', 'w') as f:
			f.write('7')
		with open('test8.txt', 'w') as f:
			f.write('8')
		with open('wp-content/uploads/test9.txt', 'w') as f:
			f.write('9')

		result = self.runner.invoke(cli, ['deploy', '--with-uploads', 'test6.txt', 'wp-content/uploads/test7.txt'])
		self.assertEqual(result.exit_code, 0)
		self.assertTrue(requests.get('%s/test6.txt' % self.home).ok)
		self.assertTrue(requests.get('%s/wp-content/uploads/test7.txt' % self.home).ok)
		self.assertFalse(requests.get('%s/test8.txt' % self.home).ok)
		self.assertFalse(requests.get('%s/wp-content/uploads/test9.txt' % self.home).ok)

	def test_007_download(self):
		files = [
			'download-1.txt',
			'download-2.txt',
			'wp-content/download-3.txt',
			'wp-content/plugins/download-4.txt',
			'wp-content/themes/download-5.txt',
			'wp-content/uploads/download-6.txt',
		]

		for filename in files:
			with open(filename, 'w') as f:
				f.write(filename)

		result = self.runner.invoke(cli, ['deploy', '--with-uploads'])
		self.assertEqual(result.exit_code, 0)

		# Delete all local files
		for filename in files:
			os.unlink(filename)

		should_exist = []
		def _assert_exists(files, should_exist):
			for filename in files:
				if filename not in should_exist:
					self.assertFalse(os.path.exists(filename))
				else:
					self.assertTrue(os.path.exists(filename))

		result = self.runner.invoke(cli, ['download', '--dry-run'])
		self.assertEqual(result.exit_code, 0)
		_assert_exists(files, should_exist)

		result = self.runner.invoke(cli, ['download', '-y', 'wp-content/plugins'])
		print(result.output)
		print(result.stderr)
		self.assertEqual(result.exit_code, 0)
		should_exist.append('wp-content/plugins/download-4.txt')
		_assert_exists(files, should_exist)

		result = self.runner.invoke(cli, ['download', '-y', 'wp-content'])
		self.assertEqual(result.exit_code, 0)
		should_exist.append('wp-content/themes/download-5.txt')
		should_exist.append('wp-content/download-3.txt')
		_assert_exists(files, should_exist)

		result = self.runner.invoke(cli, ['download', '-y', 'wp-content', '--with-uploads'])
		self.assertEqual(result.exit_code, 0)
		should_exist.append('wp-content/uploads/download-6.txt')
		_assert_exists(files, should_exist)

		# Test --delete
		with open('download-7.txt', 'w') as f:
			f.write('7')
		with open('wp-content/uploads/download-8.txt', 'w') as f:
			f.write('8')

		# Without the --delete flag, 7 and 8 should remain intact
		result = self.runner.invoke(cli, ['download', '-y', '--with-uploads'])
		self.assertEqual(result.exit_code, 0)
		should_exist.append('download-1.txt')
		should_exist.append('download-2.txt')
		_assert_exists(files, should_exist)

		# These still exists
		self.assertTrue(os.path.exists('download-7.txt'))
		self.assertTrue(os.path.exists('wp-content/uploads/download-8.txt'))

		# Add the --delete now, should be gone.
		result = self.runner.invoke(cli, ['download', '-y', '--with-uploads', '--delete'])
		self.assertEqual(result.exit_code, 0)
		self.assertFalse(os.path.exists('download-7.txt'))
		self.assertFalse(os.path.exists('wp-content/uploads/download-8.txt'))

	def test_999_destroy(self):
		result = self.runner.invoke(cli, ['destroy', '-y'])
		self.assertEqual(result.exit_code, 0)

if __name__ == '__main__':
	unittest.main()

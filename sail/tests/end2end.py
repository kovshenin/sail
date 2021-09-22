# Relative import
import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent.parent.resolve()))
from sail import cli

import io, os
import click
import unittest
import subprocess
import requests
import json
from click.testing import CliRunner
from unittest.mock import Mock, patch

# Skip some tests if true
work_in_progress = False

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

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_002_wp_home(self):
		result = self.runner.invoke(cli, ['wp', 'option', 'get', 'home'])
		self.assertEqual(result.exit_code, 0)
		self.__class__.home = result.output.strip()

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_003_wp_media_import(self):
		result = self.runner.invoke(cli, ['wp', 'media', 'import', 'https://s.w.org/style/images/wp-header-logo.png'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Imported file', result.output)

	@unittest.skipIf(work_in_progress, 'Work in progress!')
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

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_005_php(self):
		with open('test.php', 'w') as f:
			f.write('<?php\necho "%s";' % self.home)

		# Deploy the test file
		result = self.runner.invoke(cli, ['deploy'])
		self.assertEqual(result.exit_code, 0)

		response = requests.get('%s/test.php' % self.home)
		self.assertTrue(response.ok)
		self.assertEqual(self.home, response.text)

	@unittest.skipIf(work_in_progress, 'Work in progress!')
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

	@unittest.skipIf(work_in_progress, 'Work in progress!')
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

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_008_blueprint_vars(self):
		result = self.runner.invoke(cli, ['blueprint', 'test_vars.yaml'], input='Simple\n\n\n\n')
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Test Simple', result.output)
		self.assertIn('Test Default [123]', result.output)
		self.assertIn('Test Type Boolean [True]', result.output)
		self.assertIn('Test Type Integer [123]', result.output)

		# Test command-line options
		result = self.runner.invoke(cli, ['blueprint', 'test_vars.yaml', '--test-simple=1',
			'--test-default=1', '--test-type-bool=yes', '--test-type-int=456'])

		self.assertEqual(result.exit_code, 0)
		self.assertNotIn('Test Simple', result.output)
		self.assertNotIn('Test Default', result.output)
		self.assertNotIn('Test Type Boolean', result.output)
		self.assertNotIn('Test Type Integer', result.output)

		result = self.runner.invoke(cli, ['wp', 'option', 'get', 'sail_vars_test', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		vars = json.loads(result.output)

		self.assertEqual(vars['test_simple'], '1')
		self.assertEqual(vars['test_default'], '1')
		self.assertEqual(vars['test_type_bool'], True)
		self.assertEqual(vars['test_type_int'], 456)

		result = self.runner.invoke(cli, ['blueprint', 'test_vars.yaml', '--test-simple=1',
			'--test-default=1', '--test-type-bool=nah', '--test-type-int=789'])

		self.assertEqual(result.exit_code, 0)
		self.assertNotIn('Test Simple', result.output)
		self.assertNotIn('Test Default', result.output)
		self.assertNotIn('Test Type Boolean', result.output)
		self.assertNotIn('Test Type Integer', result.output)

		result = self.runner.invoke(cli, ['wp', 'option', 'get', 'sail_vars_test', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		vars = json.loads(result.output)

		self.assertEqual(vars['test_simple'], '1')
		self.assertEqual(vars['test_default'], '1')
		self.assertEqual(vars['test_type_bool'], False)
		self.assertEqual(vars['test_type_int'], 789)

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_009_blueprint_define(self):
		result = self.runner.invoke(cli, ['blueprint', 'test_define.yaml'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Updating wp-config.php constants', result.output)

		# Test results
		result = self.runner.invoke(cli, ['wp', 'config', 'get', 'TEST_BOOLEAN', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('true', result.output)

		result = self.runner.invoke(cli, ['wp', 'config', 'get', 'TEST_INTEGER', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('123', result.output)

		result = self.runner.invoke(cli, ['wp', 'config', 'get', 'TEST_STRING', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('"This is a string"', result.output)

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_009_blueprint_plugins(self):
		result = self.runner.invoke(cli, ['blueprint', 'test_plugins.yaml'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Installing plugins', result.output)
		self.assertIn('wporg/debug-bar=latest', result.output)
		self.assertIn('wporg/classic-editor=latest', result.output)
		self.assertIn('thirdparty/hello-dolly', result.output)

		# Test results
		result = self.runner.invoke(cli, ['wp', 'plugin', 'list', '--skip-themes', '--skip-plugins', '--format=json'])
		self.assertEqual(result.exit_code, 0)

		plugins = json.loads(result.output)
		plugins = [(p['name'], p['status']) for p in plugins]

		self.assertIn(('hello-dolly', 'active'), plugins)
		self.assertIn(('classic-editor', 'active'), plugins)
		self.assertIn(('debug-bar', 'active'), plugins)

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_010_blueprint_themes(self):
		result = self.runner.invoke(cli, ['blueprint', 'test_themes.yaml'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Installing themes', result.output)
		self.assertIn('wporg/twentyten=latest', result.output)
		self.assertIn('wporg/twentyeleven=latest', result.output)
		self.assertIn('thirdparty/publish', result.output)

		# Test results
		result = self.runner.invoke(cli, ['wp', 'theme', 'list', '--skip-themes', '--skip-plugins', '--format=json'])
		self.assertEqual(result.exit_code, 0)

		themes = json.loads(result.output)
		themes = [(t['name'], t['status']) for t in themes]

		self.assertIn(('twentyten', 'inactive'), themes)
		self.assertIn(('twentyeleven', 'inactive'), themes)
		self.assertIn(('publish', 'active'), themes)

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_011_blueprint_options(self):
		# Set an option
		result = self.runner.invoke(cli, ['wp', 'option', 'update', 'test_delete_option', 'delete me'])
		self.assertEqual(result.exit_code, 0)

		result = self.runner.invoke(cli, ['blueprint', 'test_options.yaml'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Applying options', result.output)

		# Test results
		result = self.runner.invoke(cli, ['wp', 'option', 'get', 'blogname', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('"Blueprints Are Fun"', result.output)

		result = self.runner.invoke(cli, ['wp', 'option', 'get', 'blogdescription', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('"Don&#039;t forget to change your tagline!"', result.output)

		result = self.runner.invoke(cli, ['wp', 'option', 'get', 'some_custom_option', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('{"foo":"bar"}', result.output)

		# Never existed
		result = self.runner.invoke(cli, ['wp', 'option', 'get', 'test_delete_unknown_option'])
		self.assertEqual(result.exit_code, 1)

		# Should not exist
		result = self.runner.invoke(cli, ['wp', 'option', 'get', 'test_delete_option'])
		self.assertEqual(result.exit_code, 1)

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_012_blueprint_fail2ban(self):
		result = self.runner.invoke(cli, ['blueprint', 'test_fail2ban.yaml'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Installing fail2ban', result.output)
		self.assertIn('Configuring fail2ban rules', result.output)

		# Running again should not install.
		result = self.runner.invoke(cli, ['blueprint', 'test_fail2ban.yaml'])
		self.assertEqual(result.exit_code, 0)
		self.assertNotIn('Installing fail2ban', result.output)
		self.assertIn('Configuring fail2ban rules', result.output)

		# Make sure mu-plugin is installed
		result = self.runner.invoke(cli, ['wp', 'plugin', 'list', '--skip-themes', '--skip-plugins', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		plugins = json.loads(result.output)
		plugins = [(p['name'], p['status']) for p in plugins]
		self.assertIn(('0-sail-auth-syslog', 'must-use'), plugins)

		# TODO: Check active jails and dpkg status when we have ssh [command]

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_013_blueprint_postfix(self):
		result = self.runner.invoke(cli, ['blueprint', 'postfix.yaml',
			'--smtp-host=smtp.gmail.com',
			'--smtp-port=578',
			'--smtp-username=foo',
			'--smtp-password=bar',
			'--from-name=From',
			'--from-email=me@example.org',
		])

		self.assertEqual(result.exit_code, 0)
		self.assertIn('Installing postfix', result.output)
		self.assertIn('Configuring postfix', result.output)

		# Running again should not install.
		result = self.runner.invoke(cli, ['blueprint', 'postfix.yaml',
			'--smtp-host=smtp.gmail.com',
			'--smtp-port=578',
			'--smtp-username=foo',
			'--smtp-password=bar',
			'--from-name=A Unit Test',
			'--from-email=me@example.org',
		])

		self.assertEqual(result.exit_code, 0)
		self.assertNotIn('Installing postfix', result.output)
		self.assertIn('Configuring postfix', result.output)

		# Make sure mu-plugin is installed
		result = self.runner.invoke(cli, ['wp', 'plugin', 'list', '--skip-themes', '--skip-plugins', '--format=json'])
		self.assertEqual(result.exit_code, 0)
		plugins = json.loads(result.output)
		plugins = [(p['name'], p['status']) for p in plugins]
		self.assertIn(('1-sail-mail-from', 'must-use'), plugins)

		result = self.runner.invoke(cli, ['download', '-y', 'wp-content'])
		self.assertEqual(result.exit_code, 0)

		with open('wp-content/mu-plugins/1-sail-mail-from.php', 'r') as f:
			contents = f.read()

		self.assertIn('A Unit Test', contents)
		self.assertIn('me@example.org', contents)

		# TODO: Check configs and dpkg status when we have ssh [command]

	@unittest.skipIf(work_in_progress, 'Work in progress!')
	def test_014_blueprint_dns(self):
		# Make sure domain doesn't exist.
		result = self.runner.invoke(cli, ['domain', 'delete', 'saildemo.com'])

		result = self.runner.invoke(cli, ['blueprint', 'test_dns.yaml', '--domain=saildemo.com'])
		self.assertEqual(result.exit_code, 1)
		self.assertIn('domain does not exist', result.output)

		result = self.runner.invoke(cli, ['domain', 'add', 'saildemo.com'])
		self.assertEqual(result.exit_code, 0)

		result = self.runner.invoke(cli, ['blueprint', 'test_dns.yaml', '--domain=saildemo.com'])
		self.assertEqual(result.exit_code, 0)
		self.assertNotIn('domain does not exist', result.output)

		self.assertIn('Creating A record for foo.saildemo.com', result.output)
		self.assertIn('Creating A record for bar.saildemo.com', result.output)
		self.assertIn('Creating MX record for baz.saildemo.com', result.output)
		self.assertIn('Creating CNAME record for qux.saildemo.com', result.output)
		self.assertIn('Blueprint applied successfully', result.output)

		# Applying again should not alter the records.
		result = self.runner.invoke(cli, ['blueprint', 'test_dns.yaml', '--domain=saildemo.com'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Skipping A record for foo.saildemo.com', result.output)
		self.assertIn('Skipping A record for bar.saildemo.com', result.output)
		self.assertIn('Skipping MX record for baz.saildemo.com', result.output)
		self.assertIn('Skipping CNAME record for qux.saildemo.com', result.output)
		self.assertIn('Blueprint applied successfully', result.output)

	def test_999_destroy(self):
		result = self.runner.invoke(cli, ['destroy', '-y'])
		self.assertEqual(result.exit_code, 0)

if __name__ == '__main__':
	unittest.main()

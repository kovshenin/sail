from sail import cli, util

import re, shlex, unittest
from unittest.mock import Mock, patch
from click.testing import CliRunner
from tldextract.tldextract import ExtractResult

class TestMakeHttps(unittest.TestCase):
	def setUp(self):
		self.addCleanup(util.debug, util.debug())
		self.runner = CliRunner()
		self.domains = ['example.com', 'www.example.com']
		self.config = {
			'email': 'owner@example.com',
			'domains': [
				{'name': 'example.com', 'internal': False, 'https': False},
				{'name': 'www.example.com', 'internal': False, 'https': False},
			],
		}
		self.extracted = {
			'example.com': ExtractResult('', 'example', 'com', is_private=False),
			'www.example.com': ExtractResult('www', 'example', 'com', is_private=False),
		}
		self.failure = 'fixture certbot failure: issue 127'
		self.remote = Mock()
		self.remote.run.side_effect = RuntimeError(self.failure)
		self._patch('sail.util.find_root', return_value='/path/to/project')
		self._patch('sail.util.config', return_value=self.config)
		self.connection = self._patch('sail.util.connection', return_value=self.remote)
		self.confirm = self._patch('click.confirm', return_value=None)
		self.extract = self._patch('sail.domains.tldextract.extract', side_effect=self._extract)
		self.update_config = self._patch('sail.util.update_config')
		self.update_nginx = self._patch('sail.domains._update_nginx_config')
		self.guards = []
		for target in ['sail.util.get_sail_default', 'sail.util.request',
			'requests.sessions.Session.request', 'fabric.Connection', 'digitalocean.Manager']:
			self.guards.append(self._patch(target, side_effect=AssertionError(target)))

	def tearDown(self):
		for guard in self.guards:
			guard.assert_not_called()
		self.remote.put.assert_not_called()

	def _patch(self, target, **kwargs):
		patcher = patch(target, **kwargs)
		self.addCleanup(patcher.stop)
		return patcher.start()

	def _extract(self, domain, **kwargs):
		return self.extracted[domain]

	def _assert_certificate_request(self):
		self.connection.assert_called_once_with()
		self.confirm.assert_called_once_with('Do you agree to the Let\'s Encrypt ToS?', abort=True)
		self.remote.run.assert_called_once()
		command = shlex.split(self.remote.run.call_args.args[0])
		self.assertEqual(command[0], 'certbot')
		self.assertEqual(command[-4:], ['-d', 'example.com', '-d', 'www.example.com'])

	def _assert_certificate_failure(self, result):
		self.assertEqual(result.exit_code, 1, result.output)
		self.assertIn('Could not obtain SSL certificate for example.com.', result.output)
		self._assert_certificate_request()
		self.update_config.assert_not_called()
		self.update_nginx.assert_not_called()

	def _add_configured_domain(self, name, subdomain, domain, suffix, internal=False):
		self.config['domains'].append({'name': name, 'internal': internal, 'https': False})
		self.extracted[name] = ExtractResult(subdomain, domain, suffix, is_private=False)

	def _configure_certificate_groups(self):
		self._add_configured_domain('blog.example.com', 'blog', 'example', 'com')
		self._add_configured_domain('other.net', '', 'other', 'net')
		self._add_configured_domain('www.other.net', 'www', 'other', 'net')
		self._add_configured_domain('internal.justsailed.io', 'internal', 'justsailed', 'io', internal=True)
		self._add_configured_domain('untouched.org', '', 'untouched', 'org')
		self.snapshots = []
		self.update_config.side_effect = self._capture_config_update

	def _capture_config_update(self, config):
		self.snapshots.append(dict(config,
			domains=[domain.copy() for domain in config['domains']]))

	def test_certificate_groups_preserve_names_and_update_order(self):
		self._configure_certificate_groups()
		self.remote.run.side_effect = None
		events = Mock()
		events.attach_mock(self.remote.run, 'run')
		events.attach_mock(self.update_config, 'config')
		events.attach_mock(self.update_nginx, 'nginx')
		result = self.runner.invoke(cli, ['domain', 'make-https'] + self.domains + ['other.net'])
		self.assertEqual(result.exit_code, 0, result.output)
		self.connection.assert_called_once_with()
		self.assertEqual([event[0] for event in events.mock_calls],
			['run', 'config', 'run', 'config', 'nginx'])
		commands = [shlex.split(request.args[0]) for request in self.remote.run.call_args_list]
		self.assertEqual(commands[0][-6:],
			['-d', 'example.com', '-d', 'www.example.com', '-d', 'blog.example.com'])
		self.assertEqual(commands[1][-4:], ['-d', 'other.net', '-d', 'www.other.net'])
		self.assertEqual([domain['https'] for domain in self.snapshots[0]['domains']],
			[True, True, True, False, False, False, False])
		self.assertEqual([domain['https'] for domain in self.snapshots[1]['domains']],
			[True, True, True, True, True, False, False])

	def test_later_certificate_failure_preserves_prior_group_only(self):
		self._configure_certificate_groups()
		self.remote.run.side_effect = [None, RuntimeError(self.failure)]
		events = Mock()
		events.attach_mock(self.remote.run, 'run')
		events.attach_mock(self.update_config, 'config')
		events.attach_mock(self.update_nginx, 'nginx')
		result = self.runner.invoke(cli, ['--debug', 'domain', 'make-https'] + self.domains + ['other.net'])
		self.assertEqual(result.exit_code, 1, result.output)
		self.assertIn('Could not obtain SSL certificate for other.net.', result.output)
		self.assertIn('(debug) ' + self.failure, result.output)
		self.connection.assert_called_once_with()
		self.assertEqual([event[0] for event in events.mock_calls], ['run', 'config', 'run'])
		self.assertEqual(len(self.snapshots), 1)
		self.assertEqual([domain['https'] for domain in self.snapshots[0]['domains']],
			[True, True, True, False, False, False, False])
		self.assertEqual(self.config, self.snapshots[0])
		self.update_nginx.assert_not_called()

	def test_certificate_failure_guidance_can_be_replayed_with_debug(self):
		result = self.runner.invoke(cli, ['domain', 'make-https'] + self.domains)
		self._assert_certificate_failure(result)
		self.assertNotIn(self.failure, result.output)
		self.assertNotIn('(debug)', result.output)
		recovery = re.search(r"'(sail [^'\n]+)'", result.output)
		self.assertIsNotNone(recovery, 'No quoted recovery command in certificate failure output:\n' + result.output)
		command = shlex.split(recovery.group(1))
		self.assertEqual(command.pop(0), 'sail')
		self.remote.run.reset_mock()
		self.connection.reset_mock()
		self.confirm.reset_mock()
		result = self.runner.invoke(cli, command + self.domains)
		self._assert_certificate_failure(result)
		self.assertIn('(debug) ' + self.failure, result.output)

	def test_global_debug_reaches_certificate_failure(self):
		result = self.runner.invoke(cli, ['--debug', 'domain', 'make-https'] + self.domains)
		self._assert_certificate_failure(result)
		self.assertIn('(debug) ' + self.failure, result.output)

	def test_global_debug_allows_certificate_success(self):
		self.remote.run.side_effect = None
		result = self.runner.invoke(cli, ['--debug', 'domain', 'make-https'] + self.domains)
		self.assertEqual(result.exit_code, 0, result.output)
		self.assertTrue(util.debug())
		self._assert_certificate_request()
		self.update_config.assert_called_once_with(self.config)
		self.update_nginx.assert_called_once_with()
		self.assertTrue(self.config['domains'][0]['https'])
		self.assertTrue(self.config['domains'][1]['https'])
		self.assertIn('SSL certificates installed.', result.output)

	def test_trailing_debug_is_rejected_before_certificate_request(self):
		result = self.runner.invoke(cli, ['domain', 'make-https'] + self.domains + ['--debug'])
		self.assertEqual(result.exit_code, 2, result.output)
		self.assertIn('No such option: --debug', result.output)
		self.connection.assert_not_called()
		self.remote.run.assert_not_called()
		self.confirm.assert_not_called()
		self.extract.assert_not_called()
		self.update_config.assert_not_called()
		self.update_nginx.assert_not_called()

from sail import cli, util

import unittest
from unittest.mock import Mock, patch, call
from click.testing import CliRunner

_find_root = Mock(return_value='/path/to/project')
_util_config = Mock(return_value={
	"app_id": "foo",
	"secret": "bar",
	"hostname": "foobar.justsailed.io",
	"provider_token": "token",
	"droplet_id": 123,
	"key_id": 456,
	"version": "0.10.0",
})
_request = Mock()
_rmtree = Mock()
_droplet = Mock()
_sshkey = Mock()
_delete_dns_records = Mock()

@patch('sail.util.find_root', _find_root)
@patch('sail.util.config', _util_config)
@patch('sail.util.request', _request)
@patch('sail.domains._delete_dns_records', _delete_dns_records)
@patch('shutil.rmtree', _rmtree)
@patch('digitalocean.Droplet', _droplet)
@patch('digitalocean.SSHKey', _sshkey)
class TestDestroy(unittest.TestCase):
	def setUp(self):
		_find_root.reset_mock()
		_util_config.reset_mock()
		_request.reset_mock()
		_rmtree.reset_mock()
		_droplet.reset_mock()
		_sshkey.reset_mock()

	def test_confirm(self):
		runner = CliRunner()
		result = runner.invoke(cli, ['destroy'])
		self.assertEqual(result.exit_code, 1)
		self.assertIn('Are you sure?', result.output)
		self.assertIn('Aborted!', result.output)
		_request.assert_not_called()
		_rmtree.assert_not_called()

	def test_destroy_input(self):
		runner = CliRunner()
		result = runner.invoke(cli, ['destroy'], input='y')
		self.assertEqual(result.exit_code, 0)
		_request.assert_called_once_with('/destroy/', method='DELETE')

		config = util.config()
		provider_token = config['provider_token']
		droplet_id = config['droplet_id']
		key_id = config['key_id']

		self.assertEqual(_droplet.mock_calls,
			[call(token=provider_token, id=droplet_id), call().destroy()])

		self.assertEqual(_sshkey.mock_calls,
			[call(token=provider_token, id=key_id), call().destroy()])

		self.assertIn('Droplet destroyed successfully', result.output)
		self.assertIn('SSH key destroyed successfully', result.output)

		_rmtree.assert_called_once_with('/path/to/project/.sail')

	def test_destroy_y(self):
		runner = CliRunner()
		result = runner.invoke(cli, ['destroy', '-y'])
		self.assertEqual(result.exit_code, 0)
		_request.assert_called_once_with('/destroy/', method='DELETE')

		config = util.config()
		provider_token = config['provider_token']
		droplet_id = config['droplet_id']
		key_id = config['key_id']

		self.assertEqual(_droplet.mock_calls,
			[call(token=provider_token, id=droplet_id), call().destroy()])

		self.assertEqual(_sshkey.mock_calls,
			[call(token=provider_token, id=key_id), call().destroy()])

		self.assertIn('Droplet destroyed successfully', result.output)
		self.assertIn('SSH key destroyed successfully', result.output)

		_rmtree.assert_called_once_with('/path/to/project/.sail')

	def test_help(self):
		runner = CliRunner()
		result = runner.invoke(cli, ['destroy', '--help'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Usage:', result.output)
		_request.assert_not_called()
		_rmtree.assert_not_called()

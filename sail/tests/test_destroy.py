from sail import cli

import unittest
from unittest.mock import Mock, patch
from click.testing import CliRunner

_find_root = Mock(return_value='/path/to/project')
_get_sail_config = Mock(return_value={
	"app_id": "foo",
	"secret": "bar",
	"url": "https://foobar.sailed.io/",
	"login_url": "https://foobar.sailed.io/wp-login.php",
	"version": "0.9.8"
})
_request = Mock()
_rmtree = Mock()

@patch('sail.util.find_root', _find_root)
@patch('sail.util.get_sail_config', _get_sail_config)
@patch('sail.util.request', _request)
@patch('shutil.rmtree', _rmtree)
class TestDestroy(unittest.TestCase):
	def setUp(self):
		_find_root.reset_mock()
		_get_sail_config.reset_mock()
		_request.reset_mock()
		_rmtree.reset_mock()

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
		self.assertIn('destroyed successfully', result.output)
		_rmtree.assert_called_once_with('/path/to/project/.sail')

	def test_destroy_y(self):
		runner = CliRunner()
		result = runner.invoke(cli, ['destroy', '-y'])
		self.assertEqual(result.exit_code, 0)
		_request.assert_called_once_with('/destroy/', method='DELETE')
		self.assertIn('destroyed successfully', result.output)
		_rmtree.assert_called_once_with('/path/to/project/.sail')

	def test_help(self):
		runner = CliRunner()
		result = runner.invoke(cli, ['destroy', '--help'])
		self.assertEqual(result.exit_code, 0)
		self.assertIn('Usage:', result.output)
		_request.assert_not_called()
		_rmtree.assert_not_called()

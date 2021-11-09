<?php
/**
 * This mu-plugin logs unsuccessful WordPress login attempts to the syslog.
 */
defined( 'ABSPATH' ) || exit;

class Sail_Auth_Logger {
	public static $log = [];

	public static function load() {
		add_action( 'wp_login_failed', [ __CLASS__, 'login_failed' ] );
		add_action( 'application_password_failed_authentication', [ __CLASS__, 'login_failed' ] );
		add_action( 'shutdown', [ __CLASS__, 'shutdown' ] );
		add_action( 'xmlrpc_call', [ __CLASS__, 'xmlrpc_call' ], 10, 1 );
	}

	public static function login_failed() {
		self::$log['wp-login-failed'] = true;
	}

	public static function xmlrpc_call( $method ) {
		if ( $method === 'pingback.ping' ) {
			self::$log['wp-pingback'] = true;
		}
	}

	public static function shutdown() {
		foreach ( self::$log as $key => $value ) {
			syslog( LOG_WARNING, $key . ':' . $_SERVER['REMOTE_ADDR'] );
		}
	}
}

Sail_Auth_Logger::load();

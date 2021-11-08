<?php
class Sail_Profiler {
	private static $filename;
	private static $key;

	public static function init() {
		if ( ! empty( $_SERVER['HTTP_X_SAIL_PROFILE'] ) ) {
			self::$key = $_SERVER['HTTP_X_SAIL_PROFILE'];
		} elseif ( ! empty( $_REQUEST['SAIL_PROFILE'] ) ) {
			self::$key = $_REQUEST['SAIL_PROFILE'];
		}

		if ( empty( self::$key ) ) {
			return;
		}

		if ( ! function_exists( 'xhprof_enable' ) ) {
			return;
		}

		if ( ! file_exists( '/etc/sail/config.json' ) ) {
			return;
		}

		$config = json_decode( file_get_contents( '/etc/sail/config.json' ), true );
		if ( empty( $config ) || empty( $config['profile_key'] ) ) {
			return;
		}

		if ( hash_equals( $config['profile_key'], self::$key ) ) {
			self::start();
		}
	}

	public static function start() {
		xhprof_enable( XHPROF_FLAGS_CPU | XHPROF_FLAGS_MEMORY );
		register_shutdown_function( [ __CLASS__, 'shutdown' ] );

		$target = '/var/www/profiles';
		if ( ! empty( $_SERVER['DOCUMENT_ROOT'] ) ) {
			$target = dirname( $_SERVER['DOCUMENT_ROOT'] ) . '/profiles';
		}

		self::$filename = tempnam( $target, 'xhprof.' );
		header( 'X-Sail-Profile: ' . self::$filename );
	}

	public static function shutdown() {
		if ( empty( self::$filename ) ) {
			return;
		}

		$data = [
			'xhprof' => xhprof_disable(),
			'timestamp' => time(),
			'method' => $_SERVER['REQUEST_METHOD'],
			'host' => $_SERVER['HTTP_HOST'],
			'request_uri' => str_replace( 'SAIL_PROFILE=' . self::$key, '', $_SERVER['REQUEST_URI'] ),
		];

		$data = json_encode( $data, JSON_PARTIAL_OUTPUT_ON_ERROR );
		file_put_contents( self::$filename, $data, LOCK_EX );
		self::$filename = null;
	}
}

Sail_Profiler::init();

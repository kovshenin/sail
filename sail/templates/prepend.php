<?php
class Sail_Profiler {
	private static $filename;
	private static $key;

	public static function init() {
		// Load premium modules if any.
		if ( file_exists( __DIR__ . '/premium.php' ) ) {
			include_once( __DIR__ . '/premium.php' );
		}

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

class Sail_Remote_Login {
	public static function init() {
		$GLOBALS['wp_filter']['plugins_loaded'][10]['sail-remote-login-loader'] = [
			'function' => [ __CLASS__, 'plugins_loaded' ],
			'accepted_args' => 1,
		];
	}

	/**
	 * Runs during plugins_loaded.
	 */
	public static function plugins_loaded() {

		// Add CLI commands.
		add_action( 'cli_init', [ __CLASS__, 'cli_init' ] );

		// Return if key and user ID are not set.
		if ( empty( $_REQUEST['_sail_remote_login'] ) || empty( $_REQUEST['id'] ) ) {
			return;
		}

		// Make sure request isn't cached.
		nocache_headers();

		// Make sure the user exists.
		$user = get_user_by( 'id', absint( $_REQUEST['id'] ) );
		if ( ! $user ) {
			wp_die( 'Invalid credentials.' );
		}

		// Make sure an rlogin session exists.
		$data = get_user_meta( $user->ID, '_sail_remote_login', true );
		if ( empty( $data ) ) {
			wp_die( 'Invalid credentials.' );
		}

		// Make sure the session is still valid.
		if ( time() > ( $data['created'] + 30 ) ) {
			wp_die( 'Invalid credentials.' );
		}

		// Make sure the key is valid.
		if ( ! hash_equals( $data['hash'], wp_hash( $_REQUEST['_sail_remote_login'] ) ) ) {
			wp_die( 'Invalid credentials.' );
		}

		// Remove session and authenticate.
		delete_user_meta( $user->ID, '_sail_remote_login' );
		wp_set_auth_cookie( $user->ID );
		wp_safe_redirect( admin_url() );
		exit;
	}

	/**
	 * Runs during cli_init
	 */
	public static function cli_init() {
		WP_CLI::add_command( 'sail remote-login', [ __CLASS__, 'remote_login' ] );
	}

	/**
	 * The sail remote-login command
	 */
	public static function remote_login( $args, $assoc_args ) {
		if ( empty( $assoc_args['email'] ) ) {
			return WP_CLI::error( 'An --email has to be set.' );
		}

		// Verify e-mail is valid and user exists.
		if ( ! is_email( $assoc_args['email'] ) ) {
			return WP_CLI::error( 'The --email is not a valid address.' );
		}

		$user = get_user_by( 'email', $assoc_args['email'] );
		if ( ! $user ) {
			return WP_CLI::error( 'Could not find a user with this email.' );
		}

		// Generate a new login key and save this session.
		$key = wp_generate_password( 48, false, false );

		$data = [
			'hash' => wp_hash( $key ),
			'created' => time(),
		];

		update_user_meta( $user->ID, '_sail_remote_login', $data );

		// Output the key and user ID.
		WP_CLI::line( wp_json_encode( [
			'key' => $key,
			'id' => $user->ID,
		] ) );
	}
}

Sail_Profiler::init();
Sail_Remote_Login::init();

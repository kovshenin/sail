<?php
class Sail_Premium {
	public static function init() {
		// add_action( 'init', [ __CLASS__, 'init_action'] );
		$GLOBALS['wp_filter']['init'][10]['sail-premium-init'] = [
			'function' =>  [ __CLASS__, 'init_action' ],
			'accepted_args' => 1,
		];
	}

	public static function init_action() {
		if ( ! apply_filters( 'sail_resize_images', true ) ) {
			return;
		}

		add_filter( 'jetpack_photon_override_image_downsize', '__return_true' );
		add_filter( 'wp_get_attachment_metadata', [ __CLASS__, 'wp_get_attachment_metadata' ], 10, 2 );
		add_filter( 'render_block_core/image', [ __CLASS__, 'render_block_core_image' ], 10, 2 );
	}

	public static function render_block_core_image( $content, $block ) {
		if ( empty( $block['attrs']['sizeSlug'] ) || $block['attrs']['sizeSlug'] != 'full' ) {
			return $content;
		}

		if ( empty( $block['attrs']['id'] ) ) {
			return $content;
		}

		if ( empty( $GLOBALS['content_width'] ) ) {
			return $content;
		}

		$meta = wp_get_attachment_metadata( $block['attrs']['id'] );
		list( $width, $height ) = wp_constrain_dimensions( $meta['width'], $meta['height'], $GLOBALS['content_width'], 0 );
		$hw = image_hwstring( $width, $height );

		$replace = function( $matches ) {
			$url = add_query_arg( 'w', $GLOBALS['content_width'], $matches[1] );
			return str_replace( $matches[1], $url, $matches[0] );
		};

		$content = preg_replace_callback( '#src="([^"]+)"#', $replace, $content );
		$content = str_replace( '<img', "<img {$hw}", $content );
		return $content;
	}

	public static function wp_get_attachment_metadata( $data, $attachment_id ) {
		$mime_type = get_post_mime_type( $attachment_id );

		if ( substr( $mime_type, 0, 6 ) !== 'image/' ) {
			return $data;
		}

		$data['sizes'] = [];

		$sizes = wp_get_registered_image_subsizes();
		foreach ( $sizes as $key => $size ) {
			$filename = basename( $data['file'] );
			$width = $size['width'];
			$height = $size['height'];
			$op = 'resize';

			if ( ! $size['crop'] ) {
				list( $width, $height ) = wp_constrain_dimensions( $data['width'], $data['height'], $width, $height );
				$op = 'fit';
			}

			$filename = add_query_arg( $op, "{$width}x{$height}", $filename );

			$data['sizes'][ $key ] = [
				'file' => $filename,
				'width' => $width,
				'height' => $height,
				'mime-type' => $mime_type,
			];
		}

		return $data;
	}
}

Sail_Premium::init();

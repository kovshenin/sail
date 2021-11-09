<?php
/**
 * Set the From: header name and address for outgoing e-mails.
 */
defined( 'ABSPATH' ) || exit;

add_filter( 'wp_mail_from_name', function( $_ ) { return {{ name }}; } );
add_filter( 'wp_mail_from', function( $_ ) { return {{ email }}; } );

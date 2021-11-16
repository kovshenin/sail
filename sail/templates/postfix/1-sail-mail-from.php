<?php
/**
 * Set the From: header name and address for outgoing e-mails.
 */
defined( 'ABSPATH' ) || exit;

add_filter( 'wp_mail_from_name', function( $_ ) { return {{ name }}; } );
add_filter( 'wp_mail_from', function( $_ ) { return {{ email }}; } );
add_action( 'phpmailer_init', function( $m ) {
	// https://core.trac.wordpress.org/ticket/37736
	$m->Sender = $m->From;
} );

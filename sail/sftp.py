import sail

from sail import cli, util

import click

@cli.group()
def sftp():
	'''Manage SFTP access on this server'''
	pass

@sftp.command()
def enable():
	'''Enable SFTP access on this server'''
	config = util.config()
	c = util.connection()

	util.heading('Enabling SFTP access for www-data')

	util.item('Copying authorized_keys')
	c.run('mkdir -p /var/www/.ssh')
	c.run('cp /root/.ssh/authorized_keys /var/www/.ssh/authorized_keys')
	c.run('chown www-data. /var/www/.ssh/authorized_keys')
	c.run('chmod 0600 /var/www/.ssh/authorized_keys')

	util.item('Enabling shell')
	c.run('usermod -s /bin/bash www-data')

	click.echo()
	util.label_width(10)

	label = util.label('Hostname:')
	hostname = config['hostname']
	click.echo(f'{label} {hostname}')
	label = util.label('Username:')
	click.echo(f'{label} www-data')
	label = util.label('SSH Key:')
	click.echo(f'{label} .sail/ssh.key')
	label = util.label('Port:')
	click.echo(f'{label} 22')

	util.success('SFTP enabled successfully')

@sftp.command()
def disable():
	'''Disable SFTP access for the www-data user'''
	c = util.connection()

	util.heading('Disabling SFTP access for www-data')

	util.item('Deleting authorized_keys')
	c.run('rm -f /var/www/.ssh/authorized_keys')

	util.item('Disabling shell')
	c.run('usermod -s /sbin/nologin www-data')

	util.success('SFTP disabled successfully')

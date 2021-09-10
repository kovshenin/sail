from sail import cli, util

import requests, json, os, subprocess, time
import click

@cli.group()
def domain():
	'''Add, remove and update domains associated with your site'''
	pass

@domain.command()
def list():
	'''List domains associated with your site'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	response = util.request('/domains/')

	click.secho('# Domains', bold=True)
	for domain, data in response.items():
		flags = []
		for flag in ['internal', 'https', 'primary']:
			if data.get(flag, None):
				flags.append(flag)

		sflags = ''
		if flags:
			sflags = ' (%s)' % ', '.join(flags)

		click.echo('- ' + domain + sflags)

@domain.command()
@click.argument('domain', nargs=1)
@click.option('--force', is_flag=True, help='Make primary again, even if the domain is already set as the primary one')
@click.option('--skip-replace', is_flag=True, help='Skip running search-replace routines for home, siteurl, and other URLs')
def make_primary(domain, force, skip_replace):
	'''Set a domain as primary, update siteurl/home, search-replace all links'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	click.echo('# Updating primary domain')

	response = util.request('/domains/make-primary/', json={
		'domain': domain,
		'force': bool(force),
		'skip_replace': bool(skip_replace),
	})
	task_id = response['task_id']

	click.echo('- Scheduled make-primary for %s' % domain)
	click.echo('- Waiting for make-primary to complete')

	util.wait_for_task(task_id, timeout=300, interval=5)

	click.echo('- Primary domain updated successfully')

@domain.command()
@click.argument('domains', nargs=-1)
@click.option('--agree-tos', is_flag=True)
def make_https(domains, agree_tos):
	'''Request and install SSL certificates for domains'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	if not agree_tos:
		click.echo('Let\'s Encrypt ToS: https://community.letsencrypt.org/tos')
		click.confirm('Do you agree to the Let\'s Encrypt ToS?', abort=True)

	if not domains:
		raise click.ClickException('At least one domain is required')

	click.echo('# Requesting and installing SSL for domains')

	response = util.request('/domains/make-https/', json={'domains': domains})
	task_id = response['task_id']

	click.echo('- Scheduled make-https for %s' % ', '.join(domains))
	click.echo('- Waiting for make-https to complete')

	util.wait_for_task(task_id, timeout=300, interval=5)

	click.echo('- SSL certificates installed')
	click.echo('- Don\'t forget to: sail domain make-primary')

@domain.command()
@click.option('--skip-dns', is_flag=True, help='Do not add or update DNS records')
@click.argument('domains', nargs=-1)
def add(domains, skip_dns):
	'''Add a new domain, with DNS records pointing to your site'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	if not domains:
		raise click.ClickException('At least one domain is required')

	response = util.request('/domains/', json={'domains': domains, 'skip_dns': skip_dns})

	for domain, data in response['feedback'].items():
		click.echo()
		click.echo('# %s' % domain)
		for line in data:
			click.echo('- %s' % line)

@domain.command()
@click.option('--skip-dns', is_flag=True, help='Do not delete DNS records')
@click.argument('domains', nargs=-1)
def delete(domains, skip_dns):
	'''Delete a domain and all DNS records'''
	'''Add a new domain, with DNS records pointing to your site'''
	root = util.find_root()
	sail_config = util.get_sail_config()

	response = util.request('/domains/', json={'domains': domains, 'skip_dns': skip_dns}, method='DELETE')

	for domain, data in response['feedback'].items():
		click.echo()
		click.echo('# %s' % domain)
		for line in data:
			click.echo('- %s' % line)

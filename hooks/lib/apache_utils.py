#
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  James Page <james.page@ubuntu.com>
#

from lib.utils import (
    relation_ids,
    relation_list,
    relation_get,
    render_template,
    juju_log,
    config_get,
    install,
    get_host_ip,
    restart
    )
from lib.cluster_utils import https

import os
import subprocess
from base64 import b64decode, b64encode

APACHE_SITE_DIR = "/etc/apache2/sites-available"
SITE_TEMPLATE = "apache2_site.tmpl"
RELOAD_CHECK = "To activate the new configuration"


def enable_https(port_maps, namespace):
    '''
    For a given number of port mappings, configures apache2
    HTTPs local reverse proxying using certficates and keys provided in
    either configuration data (preferred) or relation data.  Assumes ports
    are not in use (calling charm should ensure that).

    port_maps: dict: external to internal port mappings
    namespace: str: name of charm
    '''
    juju_log('INFO', "Enabling HTTPS for port mappings: {}".format(port_maps))
    http_restart = False
    # allow overriding of keystone provided certs with those set manually
    # in config.
    cert = config_get('ssl_cert')
    key = config_get('ssl_key')
    ca_cert = None
    if not (cert and key):
        juju_log('INFO',
                 "Inspecting identity-service relations for SSL certificate.")
        cert = key = ca_cert = None
        for r_id in relation_ids('identity-service'):
            for unit in relation_list(r_id):
                if not cert:
                    cert = relation_get('ssl_cert', rid=r_id, unit=unit)
                if not key:
                    key = relation_get('ssl_key', rid=r_id, unit=unit)
                if not ca_cert:
                    ca_cert = relation_get('ca_cert', rid=r_id, unit=unit)
        if (not (cert and key and ca_cert) and
            config_get('use-https')):
            juju_log('INFO',
                     "Using self-signed SSL certificate.")
            (cert, key) = generate_cert()
    else:
        juju_log('INFO',
                 "Using SSL certificate provided in service config.")

    if cert:
        cert = b64decode(cert)
    if key:
        key = b64decode(key)
    if ca_cert:
        ca_cert = b64decode(ca_cert)
    # TODO: Implement check tosee if certs have changed

    if not cert and not key:
        juju_log('ERROR',
                 "Expected but could not find SSL certificate data, not "
                 "configuring HTTPS!")
        return False

    install('apache2')
    if RELOAD_CHECK in subprocess.check_output(['a2enmod', 'ssl',
                                                'proxy', 'proxy_http']):
        http_restart = True

    ssl_dir = os.path.join('/etc/apache2/ssl', namespace)
    if not os.path.exists(ssl_dir):
        os.makedirs(ssl_dir)
    with open(os.path.join(ssl_dir, 'cert'), 'w') as fcert:
        fcert.write(cert)
    with open(os.path.join(ssl_dir, 'key'), 'w') as fkey:
        fkey.write(key)
    os.chmod(os.path.join(ssl_dir, 'key'), 0600)
    if ca_cert:
        with open('/usr/local/share/ca-certificates/keystone_juju_ca_cert.crt',
                  'w') as crt:
            crt.write(ca_cert)
        subprocess.check_call(['update-ca-certificates', '--fresh'])

    sites_dir = '/etc/apache2/sites-available'
    for ext_port, int_port in port_maps.items():
        juju_log('INFO',
                 'Creating apache2 reverse proxy vhost'
                 ' for {}:{}'.format(ext_port,
                                     int_port))
        site = "{}_{}".format(namespace, ext_port)
        site_path = os.path.join(sites_dir, site)
        with open(site_path, 'w') as fsite:
            context = {
                "ext": ext_port,
                "int": int_port,
                "namespace": namespace,
                "private_address": get_host_ip()
                }
            fsite.write(render_template(SITE_TEMPLATE,
                                        context))

        if RELOAD_CHECK in subprocess.check_output(['a2ensite', site]):
            http_restart = True

    if http_restart:
        restart('apache2')

    return True


def disable_https(port_maps, namespace):
    '''
    Ensure HTTPS reverse proxying is disables for given port mappings

    port_maps: dict: of ext -> int port mappings
    namespace: str: name of chamr
    '''
    juju_log('INFO', 'Ensuring HTTPS disabled for {}'.format(port_maps))

    if (not os.path.exists('/etc/apache2') or
        not os.path.exists(os.path.join('/etc/apache2/ssl', namespace))):
        return

    http_restart = False
    for ext_port in port_maps.keys():
        if os.path.exists(os.path.join(APACHE_SITE_DIR,
                                       "{}_{}".format(namespace,
                                                      ext_port))):
            juju_log('INFO',
                     "Disabling HTTPS reverse proxy"
                     " for {} {}.".format(namespace,
                                          ext_port))
            if (RELOAD_CHECK in
                subprocess.check_output(['a2dissite',
                                         '{}_{}'.format(namespace,
                                                        ext_port)])):
                http_restart = True

    if http_restart:
        restart(['apache2'])


def setup_https(port_maps, namespace):
    '''
    Ensures HTTPS is either enabled or disabled for given port
    mapping.

    port_maps: dict: of ext -> int port mappings
    namespace: str: name of charm
    '''
    if not https:
        disable_https(port_maps, namespace)
    else:
        enable_https(port_maps, namespace)


def generate_cert():
    '''
    Generates a self signed certificate and key using the
    provided charm configuration data.

    returns: tuple of (cert, key)
    '''
    CERT = '/etc/swift/ssl.cert'
    KEY = '/etc/swift/ssl.key'
    if (not os.path.exists(CERT) and
        not os.path.exists(KEY)):
        subj = '/C=%s/ST=%s/L=%s/CN=%s' %\
            (config_get('country'), config_get('state'),
             config_get('locale'), config_get('common-name'))
        cmd = ['openssl', 'req', '-new', '-x509', '-nodes',
               '-out', CERT, '-keyout', KEY,
               '-subj', subj]
        subprocess.check_call(cmd)
    # Slurp as base64 encoded - makes handling easier up the stack
    with open(CERT, 'r') as cfile:
        ssl_cert = b64encode(cfile.read())
    with open(KEY, 'r') as kfile:
        ssl_key = b64encode(kfile.read())
    return (ssl_cert, ssl_key)

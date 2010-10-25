from __future__ import with_statement
from fabric.api import run, put, sudo, env, cd, local, prompt, settings
from fabric.colors import green
from fabric.contrib import files
from louis import conf


def update():
    """
    Updates package list and installs the ones that need updates.
    """
    # Activate Ubuntu's "Universe" repositories.
    files.uncomment('/etc/apt/sources.list', regex=r'deb.*universe',
                    use_sudo=True)
    sudo('apt-get update -y')
    sudo('apt-get upgrade -y')


def install_debconf_seeds():
    print(green('Installing debconf-utils'))
    sudo('apt-get -y install debconf-utils')
    for seed_file in conf.DEBCONF_SEEDS:
        directory, sep, seed_filename = seed_file.rpartition('/')
        print(green('Installing seed: %s' % seed_filename))
        put(seed_file, '/tmp/%s' % seed_filename)
        sudo('debconf-set-selections /tmp/%s' % seed_filename)


def install_basic_packages():
    """
    Installs basic packages as specified in louisconf.BASIC_PACKAGES
    """
    for pkg in conf.BASIC_PACKAGES:
        print(green('Installing %s' % pkg))
        sudo('apt-get -y install ' + pkg, shell=False)


def config_apticron():
    """
    Adds sysadmin emails to the apticron config.
    """
    emails = ' '.join(v['email'] for k,v in conf.SYSADMINS.items())
    files.sed('/etc/apticron/apticron.conf', '"root"', '"%s"' % emails, 
              limit="EMAIL=", use_sudo=True)


def config_sshd():
    """Disables password-based and root logins. Make sure that you have some
    users created with ssh keys before running this."""
    sshd_config = '/etc/ssh/sshd_config'
    files.sed(sshd_config, 'yes', 'no', limit='PermitRootLogin', use_sudo=True)
    files.sed(sshd_config, '#PasswordAuthentication yes', 'PasswordAuthentication no', use_sudo=True)
    sudo('/etc/init.d/ssh restart')


def install_apache():
    """
    Installs apache2, mod-wsgi, and mod-ssl.
    """
    pkgs = ('apache2', 'apache2-utils', 'libapache2-mod-wsgi', )
    for pkg in pkgs:
        sudo('apt-get -y install %s' % pkg)
    sudo('virtualenv --no-site-packages /var/www/virtualenv')
    sudo('echo "WSGIPythonHome /var/www/virtualenv" >> /etc/apache2/conf.d/wsgi-virtualenv')
    sudo('a2enmod ssl')
    files.append('ServerName localhost', '/etc/apache2/httpd.conf',
                 use_sudo=True)
    sudo('/etc/init.d/apache2 reload')


def install_postgres():
    """
    Installs postgres and python mxdatetime.
    """
    pkgs = ('postgresql', 'python-egenix-mxdatetime')
    for pkg in pkgs:
        sudo('apt-get -y install %s' % pkg)
    sudo('apt-get -y install postgresql')
    sudo('apt-get -y build-dep psycopg2')


def patch_virtualenv(user, package_path, virtualenv_path='env'):
    with settings(user=user):
        target = '/home/%s/%s/lib/python2.6/site-packages/' % (user, virtualenv_path)
        run('ln -s %s %s' % (package_path, target))



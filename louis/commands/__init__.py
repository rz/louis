from louis.commands.packages import *
from louis.commands.users import *
from louis.commands.projects import *
from louis.commands.databases import *
from louis.commands.solr import *
from louis import conf


def init_server(swap_size=None, apache=True, postgres=True):
    """
    Runs basic configuration of a virgin server.
    """
    setup_swap(swap_size)
    setup_hosts()
    update()
    set_timezone()
    install_debconf_seeds()
    install_basic_packages()
    config_apticron()
    create_sysadmins()
    config_sudo()
    if apache:
        install_apache()
    if postgres:
        install_postgres()
    config_sshd()


def setup_swap(size=None):
    """
    Creates swapfile and adds to fstab.  Size is in MB.
    """
    if size:
        size = size * 1024
        sudo('dd if=/dev/zero of=/swapfile bs=1024 count=%s' % size)
        sudo('mkswap /swapfile')
        sudo('chown root:root /swapfile')
        sudo('chmod 0600 /swapfile')
        sudo('swapon /swapfile')
        sudo('echo \"/swapfile swap swap defaults 0 0\" >>/etc/fstab')


def setup_hosts():
    """
    Configure /etc/hosts and /etc/hostname. Make sure that env.host is the
    server's IP address and that env.hostname is the server's hostname.
    """
    if not getattr(env, 'hostname', None):
        print "setup_hosts requires env.hostname. Skipping."
        return None
    ## the following stuff will only be necessary if we need to put entries
    ## like "1.2.3.4 lrz15" into /etc/hosts, but that may not be necessary.
    ## i'll leave the code for now, but i suspect we can delete it.
    ## sanity check: env.host is an IP address, not a hostname
    #import re
    #assert(re.search(r'^(\d{0,3}\.){3}\d{0,3}$', env.host) is not None)
    #files.append("%(host)s\t%(hostname)s" % env, '/etc/hosts', use_sudo=True)
    files.append('/etc/hosts', "127.0.1.1\t%s" % env.hostname, use_sudo=True)
    sudo("hostname %s" % env.hostname)
    sudo('echo "%s" > /etc/hostname' % env.hostname)


def set_timezone(tz_file_path='/usr/share/zoneinfo/Etc/UTC', tz_config_path='/etc/localtime'):
    if files.exists(tz_file_path):
        sudo('cp %s %s' %(tz_file_path, tz_config_path))

def apache_reload():
    """
    Do a graceful restart of Apache. Reloads the configuration files and the
    client app code without severing any active connections.
    """
    sudo('/etc/init.d/apache2 reload')


def apache_restart():
    """
    Restarts Apache2. Only use this command if you're modifying Apache itself
    in some way, such as installing a new module. Otherwise, use apache reload
    to do a graceful restart.
    """
    sudo('/etc/init.d/apache2 restart')



def make_fxn(name, ip):
    def fxn(user=None):
        env.hosts = [ip]
        env.hostname = name
        if user:
            env.user = user
    fxn.__doc__ = ("""Runs subsequent commands on %s. Takes optional user """
                  """argument.""" % name)
    return fxn


for ip, name in conf.HOSTS:
    if not globals().has_key(name):
        globals()[name] = make_fxn(name, ip)
globals().pop('make_fxn')

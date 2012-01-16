from __future__ import with_statement
from fabric.api import run, put, sudo, env, cd, local, prompt, settings
from fabric.contrib import files
from louis import conf


def add_ssh_keys(target_username, ssh_key_path):
    """
    cats the file at ssh_key_path (local) to the target username's authorized_keys.
    """
    with cd('/home/%s' % target_username):
        sudo('mkdir -p .ssh')
        put(ssh_key_path, 'keys', use_sudo=True)
        sudo('cat keys >> .ssh/authorized_keys')
        sudo('chown -R %s:%s .ssh/' % (target_username, target_username))
        sudo('rm -f keys')


def create_group(groupname):
    """Creates group if it doesn't already exist."""
    with settings(warn_only=True):
        check_group = sudo('grep -e "%s" /etc/group' % groupname)
        if check_group.return_code > 0:
            sudo('groupadd %s' % groupname)


def create_user(username, ssh_key_path, shell='bash', admin=False):
    """
    Creates a user. The ssh_key_path argument is required and should be an
    absolute path to a local key file. The file will be concatenated to
    authorized_keys, so it can contain multiple keys. Pass admin=True for new
    user to be an admin.
    """
    # TODO: check if user exists and return if so
    with settings(warn_only=True):
        if not sudo('grep "%s:" /etc/passwd' % username).failed:
            return
    if admin:
        create_group('admin')
        sudo('useradd -G admin -m -s `which %s` %s' % (shell, username))
    else:
        sudo('useradd -m -s' % (shell, username))
    add_ssh_keys(target_username=username, ssh_key_path=ssh_key_path)


def delete_user(username):
    """
    Deletes a user and the home directory.
    """
    sudo('userdel -r %s' % username)


def create_sysadmins():
    """Creates users for every entry in louisconf.SYSADMINS."""
    for u,s in conf.SYSADMINS.iteritems():
        create_user(u, s['ssh_key_path'], shell=s['shell'], admin=True)


def config_sudo():
    """Changes sudo configuration so that members of the admin group can gain
    root privileges without password."""
    txt = ['# Members of the admin group may gain root privileges',
           '# They can run any command as root with no password',
           '%admin ALL=(ALL) NOPASSWD: ALL']
    files.append(txt, '/etc/sudoers', use_sudo=True)



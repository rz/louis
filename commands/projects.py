from __future__ import with_statement

from fabric.api import run, put, sudo, env, cd, local, prompt, settings
from fabric.contrib import files
from fabric.colors import green, red
from louis import conf
import louis.commands
from louis.commands.users import add_ssh_keys



def setup_project_user(project_username):
    """
    Create a crippled user to hold project-specific files.
    """
    with settings(warn_only=True):
        check_user = sudo('grep -e "%s" /etc/passwd' % project_username)
    if not check_user.failed:
        return
    sudo('adduser --gecos %s --disabled-password %s' % ((project_username,)*2))
    sudo('usermod -a -G www-data %s' % project_username)
    for u, s in conf.SYSADMINS.items():
        add_ssh_keys(target_username=project_username, ssh_key_path=s['ssh_key_path'])
    with settings(user=project_username):
        run('mkdir -p .ssh')
        run('ssh-keygen -t rsa -f .ssh/id_rsa -N ""')
        # so that we don't get a yes/no prompt when checking out repos via ssh
        files.append(['Host *', 'StrictHostKeyChecking no'], '.ssh/config')
        run('mkdir log')


def setup_project_virtualenv(project_username, target_directory='env', site_packages=False):
    """
    Create a clean virtualenv for a project in the target directory. The target
    directory is relative to the project user's home dir and defaults to env ie
    the venv will be installed in /home/project/env/
    """
    with settings(user=project_username):
        with cd('/home/%s' % project_username):
            run('rm -rf %s' % target_directory)
            if site_packages:
                run('virtualenv %s' % target_directory)
            else:
                 run('virtualenv --no-site-packages %s' % target_directory)
            run('env/bin/easy_install -U setuptools')
            run('env/bin/easy_install pip')


def install_project_requirements(project_username, requirements_path=None, env_path='env'):
    """
    Installs a requirements file via pip.

    The requirements file path should be relative to the project user's home
    directory and it defaults to project_username/deploy/requirements.txt

    The env path should also be relative to the project user's home directory and
    defaults to env.
    """
    if not requirements_path:
        requirements_path = '%s/deploy/requirements.txt' % project_username
    with settings(user=project_username):
        with cd('/home/%s' % project_username):
            run('%s/bin/pip install -r %s' % (env_path, requirements_path))


def setup_project_code(project_username, git_url, target_directory=None, branch='master'):
    """
    Check out the project's code into its home directory. Target directory will
    be relative to project_username's home directory. target directory defaults
    to the value of project_username ie you'll end up with the code in
    /home/project/project/
    """
    if not target_directory:
        target_directory = project_username
    # if not branch:
    #     branch = 'master'
    with cd('/home/%s' % project_username):
        with settings(user=project_username):
            run('git clone %s %s' % (git_url, target_directory))
            # TODO: test this to make sure it works on projects that have
            # no submodules
            with cd('%s' % target_directory):
                #run('git submodule update --init') # --recursive')
                run('git submodule init')
                run('git submodule update')
                # checkout and update all remote branches, so that the deployment can be any one of them
                # all remote branches except HEAD and master
                branches = run('git branch -r').split('\n')
                for b in branches:
                    if 'master' in b or 'HEAD' in b:
                        continue
                    r, sep, branch_name = b.strip().rpartition('/')
                    run('git branch %s --track origin/%s' % (branch_name, branch_name))
                run('git checkout %s' % branch)


def setup_project_apache(project_username, media_directory=None, branch='master'):
    """
    Configure apache-related settings for the project. This will look for every 
    *.apache2 file in the project user's home dir and attempt to enable it.

    media_directory should be relative to the project user's home directory. It
    defaults to project_username/media ie you'd end up with
    /home/project/project/media/
    """
    if not media_directory:
        media_directory = '%s/media/' % project_username
    with cd('/home/%s' % project_username):
        # permissions for media/
        sudo('chgrp www-data -R %s' % media_directory)
        sudo('chmod g+w %s' % media_directory)
        # apache config
        for config_path in sudo('find $PWD -name "*.apache2"').split('\n'):
            d, sep, config_filename = config_path.rpartition('/')
            config_filename, dot, config_extension = config_filename.rpartition('.')
            config_filename = '%s-%s.%s' % (config_filename, branch, config_extension)
            print red(config_filename)
            with settings(warn_only=True):
                check_config_file = sudo('[ -f /etc/apache2/sites-available/%s ]' % config_filename)
            if check_config_file.failed:
                sudo('ln -s %s /etc/apache2/sites-available/%s' % (config_path, config_filename))
                sudo('a2ensite %s' % config_filename)
    with settings(warn_only=True):
        check_config = sudo('apache2ctl configtest')
    if check_config.failed:
        print(red('Invalid apache configuration! The requested configuration was installed, but there is a problem with it.'))
    else:
        louis.commands.apache_reload()


def delete_project_code(project_username, target_directory=None):
    """
    Deletes /home/project_username/target_directory/ target_directory defaults
    to project_username if not given ie /home/project/project/
    """
    if not target_directory:
        target_directory = project_username
    sudo('rm -rf /home/%s/%s' % (project_username, target_directory))


def update_project(project_username, target_directory=None, branch='master', wsgi_file_path=None):
    """
    Pull the latest source to a project deployed at target_directory. The
    target_directory is relative to project user's home dir. target_directory
    defaults to project_username ie /home/project/project/
    The wsgi path is relative to the target directory and defaults to
    deploy/project_username.wsgi.
    """
    if not target_directory:
        target_directory = project_username
    if not wsgi_file_path:
        wsgi_file_path = 'deploy/%s.wsgi' % project_username
    with settings(user=project_username):
        with cd('/home/%s/%s' % (project_username, target_directory)):
            run('git checkout %s' % branch)
            run('git pull')
            run('git submodule update')
            run('touch %s' % wsgi_file_path)


def setup_project(project_username, git_url, target_directory=None, branch='master'):
    """
    Creates a user for the project, checks out the code and does basic apache config.
    """
    setup_project_user(project_username)
    print(green("Here is the project user's public key:"))
    run('cat /home/%s/.ssh/id_rsa.pub' % project_username)
    print(green("This script will attempt a `git clone` next."))
    prompt(green("Press enter to continue."))
    setup_project_code(project_username, git_url, target_directory, branch)
    setup_project_virtualenv(project_username)
    install_project_requirements(project_username)
    if target_directory:
        media_directory = '%s/media/' % target_directory
        apache_config_path = '%s/deploy/%s.apache2' % (target_directory, project_username)
        setup_project_apache(project_username, media_directory, apache_config_path, branch)
    else:
        setup_project_apache(project_username, branch=branch)
    print(green("""Project setup complete. You may need to patch the virtualenv
    to install things like mx. You may do so with the patch_virtualenv command.
    """))

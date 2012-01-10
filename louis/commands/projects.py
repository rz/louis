from __future__ import with_statement

from datetime import datetime

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
        check_user = sudo('grep -e "%s:" /etc/passwd' % project_username)
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
        files.append('.ssh/config', ['Host *', 'StrictHostKeyChecking no'])
        run('mkdir log')
    with cd('/home/%s/' % project_username):
        sudo('chmod 770 log')
        sudo('chown %s:www-data log' % project_username)


def setup_project_virtualenv(project_username, target_directory='env', site_packages=False):
    """
    Create a clean virtualenv for a project in the target directory. The target
    directory is relative to the project user's home dir and defaults to env ie
    the venv will be installed in /home/project/env/
    """
    with settings(user=project_username):
        with cd('/home/%s' % project_username):
            if site_packages:
                run('virtualenv %s' % target_directory)
            else:
                 run('virtualenv --no-site-packages %s' % target_directory)
            run('env/bin/easy_install -U setuptools')
            run('env/bin/easy_install pip')


def install_project_requirements(project_username, requirements_path, env_path='env'):
    """
    Installs a requirements file via pip.

    The requirements file path should be relative to the project user's home

    directory and it defaults to project_username/deploy/requirements.txt
    The env path should also be relative to the project user's home directory and
    defaults to env.
    """
    with settings(user=project_username):
        with cd('/home/%s' % project_username):
            run('%s/bin/pip install -r %s' % (env_path, requirements_path))


def setup_project_code(project_name, project_username, git_url, branch='master'):
    """
    Check out the project's code into its home directory. Target directory will
    be relative to project_username's home directory. target directory defaults
    to the value of project_username ie you'll end up with the code in
    /home/project/project/
    """
    with cd('/home/%s' % project_username):
        with settings(user=project_username):
            if files.exists(project_name):
                print(red('Destination path already exists ie the repo has been cloned already.'))
                return
            run('git clone %s %s' % (git_url, project_name))
            with cd('%s' % project_name):
                #run('git submodule update --init') # --recursive')
                run('git submodule init')
                run('git submodule update')
                # checkout and update all remote branches, so that the deployment 
                # can be any one of them
                branches = run('git branch -r').split('\n')
                for b in branches:
                    if 'master' in b or 'HEAD' in b:
                        # all remote branches except HEAD and master since those
                        # by default
                        continue
                    r, sep, branch_name = b.strip().rpartition('/')
                    run('git branch %s --track origin/%s' % (branch_name, branch_name))
                run('git checkout %s' % branch)


def setup_project_apache(project_name, project_username, server_name, server_alias, django_settings, media_directory=None, branch='master'):
    """
    Configure apache-related settings for the project.
    
    This will render every  *.apache2 file in the current local directory as a
    template with project_name, project_username, branch, server_name and
    server_alias as context. It'll put the rendered template in apache
    sites-available.
    
    It will also render any *.wsgi file with the same context. It will put the
    rendered file in the project user's home directory.

    media_directory should be relative to the project user's home directory. It
    defaults to project_username/media ie you'd end up with
    /home/project/project/media/
    """
    if not media_directory:
        media_directory = '%s/media/' % project_name
    with cd('/home/%s' % project_username):
        # permissions for media/
        sudo('chgrp www-data -R %s' % media_directory)
        sudo('chmod g+w %s' % media_directory)
    context = {
        'project_name': project_name,
        'project_username': project_username,
        'server_name': server_name,
        'server_alias': server_alias,
        'django_settings': django_settings,
        'branch': branch,
    }
    # apache config
    apache_files = local('find . -name "*.apache2"', capture=True)
    for config_path in apache_files.split('\n'):
        d, sep, config_filename = config_path.rpartition('/')
        config_filename, dot, ext = config_filename.rpartition('.')
        config_filename = '%s-%s.%s' % (config_filename, branch, ext)
        dest_path = '/etc/apache2/sites-available/%s' % config_filename
        if not files.exists(dest_path, use_sudo=True):
            files.upload_template(config_path, dest_path, context=context, use_sudo=True)
            sudo('a2ensite %s' % config_filename)
    # wsgi file
    wsgi_files = local('find . -name "*.wsgi"', capture=True)
    for wsgi_path in wsgi_files.split('\n'):
        d, sep, wsgi_filename = wsgi_path.rpartition('/')
        wsgi_filename, dot, ext = wsgi_filename.rpartition('.')
        wsgi_filename = '%s-%s.%s' % (wsgi_filename, branch, ext)
        dest_path = '/home/%s/%s' % (project_username, wsgi_filename)
        if not files.exists(dest_path, use_sudo=True):
            files.upload_template(wsgi_path, dest_path, use_sudo=True, context=context)
            sudo('chown %s:%s %s' % (project_username, 'www-data', dest_path))
            sudo('chmod 755 %s' % dest_path)
    sudo('a2enmod rewrite')
    with settings(warn_only=True):
        check_config = sudo('apache2ctl configtest')
    if check_config.failed:
        print(red('Invalid apache configuration! The requested configuration was installed, but there is a problem with it.'))
    else:
        louis.commands.apache_reload()


def setup_project(project_name, git_url, apache_server_name, apache_server_alias, django_settings='production-settings', project_username=None, branch='master', requirements_path=None):
    """
    Creates a user for the project, checks out the code and does basic apache config.
    """
    local_user = local('whoami')
    if not project_username:
        project_username =  '%s-%s' % (project_name, branch)
    setup_project_user(project_username)
    print(green("Here is the project user's public key:"))
    run('cat /home/%s/.ssh/id_rsa.pub' % project_username)
    print(green("This script will attempt a `git clone` next."))
    prompt(green("Press enter to continue."))
    setup_project_code(project_name, project_username, git_url, branch)
    setup_project_virtualenv(project_username)
    if not requirements_path:
        requirements_path = '%s/deploy/requirements.txt' % project_name
    install_project_requirements(project_username, requirements_path)
    setup_project_apache(project_name, project_username, apache_server_name, apache_server_alias, django_settings, branch=branch)

    with cd('/home/%s/%s/deploy/logrotate/' % (project_username, project_name)):
        sudo('cat apache2 >> /etc/logrotate.d/apache2')

    sudo('chown -R %s:www-data /home/%s/log' % (project_username, project_username))
    sudo('chmod -R 770 /home/%s/log' % project_username)

    with cd('/home/%s/%s' % (project_username, project_name)):
        git_head = run('git rev-parse HEAD')
    with cd('/home/%s' % project_username):
        log_text = 'Initial deploy on %s by %s, HEAD: %s' % (datetime.now(), local_user, git_head)
        files.append('log/deploy.log', log_text, use_sudo=True)

    print(green("""Project setup complete. You may need to patch the virtualenv
    to install things like mx. You may do so with the patch_virtualenv command."""))


def delete_project_code(project_name, project_username):
    """
    Deletes /home/project_username/target_directory/ target_directory defaults
    to project_username if not given ie /home/project/project/
    """
    sudo('rm -rf /home/%s/%s' % (project_username, project_name))


def update_project(project_name, project_username=None, branch='master', wsgi_file_path=None, settings_module='production-settings', update_requirements=True):
    """
    Pull the latest source to a project deployed at target_directory. The
    target_directory is relative to project user's home dir. target_directory
    defaults to project_username ie /home/project/project/
    The wsgi path is relative to the target directory and defaults to
    deploy/project_username.wsgi.
    """
    local_user = local('whoami')
    if not project_username:
        project_username = '%s-%s' % (project_name, branch)
    if not wsgi_file_path:
        wsgi_file_path = '/home/%s/%s.wsgi' % (project_username, project_username)
    with settings(user=project_username):
        project_dir = '/home/%s/%s' % (project_username, project_name)
        with cd(project_dir):
            run('git checkout %s' % branch)
            run('git pull')
            run('git submodule update')
            run('/home/%s/env/bin/python manage.py migrate --merge --settings=%s' % (project_username, settings_module))
            if update_requirements:
                install_project_requirements(project_username, '%s/deploy/requirements.txt' % project_dir)
            run('touch %s' % wsgi_file_path)
            git_head = run('git rev-parse HEAD')
            run('crontab deploy/crontab')
        with cd('/home/%s' % project_username):
            log_text = 'Deploy on %s by %s. HEAD: %s' % (datetime.now(), local_user, git_head)
            files.append(log_text, 'log/deploy.log')

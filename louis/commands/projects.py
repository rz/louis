from __future__ import with_statement

from datetime import datetime

from fabric.api import run, put, sudo, env, cd, local, prompt, settings
from fabric.contrib import files
from fabric.colors import green, red

import pip

from louis import conf
from louis.utils import get_arg
import louis.commands
from louis.commands.users import add_ssh_keys


def setup_project_user(project_username=None):
    """
    Create a crippled user to hold project-specific files.
    """
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               'project-user')

    with settings(warn_only=True):
        check_user = sudo('grep -e "%s:" /etc/passwd' % project_username)
    if not check_user.failed:
        return
    sudo('adduser --gecos %s --disabled-password %s' % ((project_username,)*2))
    sudo('usermod -a -G www-data %s' % project_username)
    for u, s in conf.SYSADMINS.items():
        add_ssh_keys(target_username=project_username,
                     ssh_key_path=s['ssh_key_path'])
    with settings(user=project_username):
        run('mkdir -p .ssh')
        run('ssh-keygen -t rsa -f .ssh/id_rsa -N ""')
        # so that we don't get a yes/no prompt when checking out repos via ssh
        files.append('.ssh/config', ['Host *', 'StrictHostKeyChecking no'])
        run('mkdir -p log')
        run('chmod 770 log')
        run('chown %s:www-data log' % project_username)
        run('touch log/app.log')
        run('touch log/db.log')
        run('chmod 664 log/*.log')
        run('chown %s:www-data log/*.log' % project_username)


def setup_project_virtualenv(project_username=None, target_directory=None,
                             site_packages=None):
    """
    Create a clean virtualenv for a project in the target directory. The target
    directory is relative to the project user's home dir and defaults to env ie
    the venv will be installed in /home/project/env/
    """
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               'project-user')
    target_directory = get_arg(target_directory, 'TARGET_DIRECTORY', 'env')
    site_packages = get_arg(site_packages, 'SITE_PACKAGES', False)

    with settings(user=project_username):
        with cd('/home/%s' % project_username):
            if site_packages:
                run('virtualenv %s' % target_directory)
            else:
                 run('virtualenv --no-site-packages %s' % target_directory)
            run('env/bin/easy_install -U setuptools')
            run('env/bin/easy_install pip')


def install_project_requirements(project_username=None, requirements_path=None,
                                 env_path=None, update_packages=False):
    """
    Installs a requirements file via pip.

    The requirements file path should be relative to the project user's home
    directory and it defaults to project_username/deploy/requirements.txt
    The env path should also be relative to the project user's home directory
    and defaults to env.

    If update_packages is True, the packages already installed are updated if
    if necessary.
    """
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               'project-user')
    requirements_path = get_arg(requirements_path, 'REQUIREMENTS_PATH',
                                'deploy/requirements.txt')
    env_path = get_arg(env_path, 'ENV_PATH', 'env')

    with settings(user=project_username):
        with cd('/home/%s' % project_username):
            if update_packages:
                run('%s/bin/pip install --update -M -r %s' % \
                    (env_path, requirements_path))
            else:
                run('%s/bin/pip install -M -r %s' % (env_path, requirements_path))

def setup_project_code(git_url, project_name=None, project_username=None,
                       branch=None):
    """
    Check out the project's code into its home directory. Target directory will
    be relative to project_username's home directory. target directory defaults
    to the value of project_username ie you'll end up with the code in
    /home/project/project/
    """
    project_name = get_arg(project_name, 'PROJECT_NAME', 'project')
    branch = get_arg(branch, 'BRANCH', 'master')
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               '%s-%s' % (project_name, branch))
    git_url = get_arg(git_url, 'GIT_URL', None)

    with cd('/home/%s' % project_username):
        with settings(user=project_username):
            if files.exists(project_name):
                print(red('Destination path already exists ie the repo has '
                          'cloned already.'))
                return
            run('git clone %s %s' % (git_url, project_name))
            with cd('%s' % project_name):
                #run('git submodule update --init') # --recursive')
                run('git submodule init')
                run('git submodule update')
                # checkout and update all remote branches, so that the
                # deployment can be any one of them
                branches = run('git branch -r').split('\n')
                for b in branches:
                    if 'master' in b or 'HEAD' in b:
                        # all remote branches except HEAD and master since those
                        # by default
                        continue
                    r, sep, branch_name = b.strip().rpartition('/')
                    run('git branch %s --track origin/%s' %
                        (branch_name, branch_name))
                run('git checkout %s' % branch)


def setup_project_apache(project_name=None, project_username=None,
                         server_name=None, server_alias=None, admin_email=None,
                         settings_module=None, media_directory=None,
                         branch=None, git_head=None):
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
    project_name = get_arg(project_name, 'PROJECT_NAME', 'project')
    branch = get_arg(branch, 'BRANCH', 'master')
    git_head = get_arg(git_head, 'CURRENT_HEAD', '')
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               '%s-%s' % (project_name, branch))
    server_name = get_arg(server_name, 'SERVER_NAME', 'localhost')
    server_alias = get_arg(server_alias, 'SERVER_ALIAS',
                           'www.%s' % server_name)
    admin_email = get_arg(admin_email, 'ADMIN_EMAIL',
                          'root@%s' % server_name)
    settings_module = get_arg(settings_module, 'SETTINGS_MODULE', 'settings')
    media_directory = get_arg(media_directory, 'MEDIA_DIRECTORY',
                              '%s/media/' % project_name)

    # permissions for media/
    sudo('chgrp www-data -R /home/%s/%s' %
         (project_username, media_directory))
    sudo('chmod g+w /home/%s/%s' % (project_username, media_directory))

    context = {
        'project_name': project_name,
        'project_username': project_username,
        'admin_email': admin_email,
        'server_name': server_name,
        'server_alias': server_alias,
        'settings_module': settings_module,
        'branch': branch,
        'git_head': git_head,
    }
    # apache config
    apache_template = local('find . -name "template.apache2"',
                            capture=True).strip()
    apache_filename = '%s.apache2' % project_username
    dest_path = '/etc/apache2/sites-available/%s' % apache_filename
    files.upload_template(apache_template, dest_path, context=context,
                          use_sudo=True)
    with settings(warn_only=True):
        sudo('a2ensite %s' % apache_filename)

    # wsgi file
    wsgi_template = local('find . -name "template.wsgi"', capture=True).strip()
    wsgi_filename = '%s.wsgi' % project_username
    dest_path = '/home/%s/%s' % (project_username, wsgi_filename)
    files.upload_template(wsgi_template, dest_path, use_sudo=True,
                          context=context)
    sudo('chown %s:%s %s' % (project_username, 'www-data', dest_path))
    sudo('chmod 755 %s' % dest_path)
    with settings(warn_only=True):
        sudo('a2enmod rewrite')
        sudo('a2enmod headers')
    with settings(warn_only=True):
        check_config = sudo('apache2ctl configtest')
    if check_config.failed:
        print(red('Invalid apache configuration! The requested configuration '
                  'was installed, but there is a problem with it.'))
    else:
        louis.commands.apache_reload()


def setup_project_crontab(project_name=None, project_username=None,
                          settings_module=None, cron_email=None, install=None):
    """
    Install crontab under project_username
    """
    project_name = get_arg(project_name, 'PROJECT_NAME', 'project')
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               '%s-master' % project_name)
    settings_module = get_arg(settings_module, 'CRON_SETTINGS_MODULE',
                              'settings.py')
    cron_email = get_arg(cron_email, 'CRON_EMAIL', 'root@localhost')
    install = get_arg(install, 'INSTALL_CRONTAB', False)

    context = {
        'project_name': project_name,
        'project_username': project_username,
        'cron_email': cron_email,
        'settings_module': settings_module,
    }
    crontab_template = local('find . -name "template.crontab"',
                             capture=True).strip()
    project_dir = '/home/%s/%s' % (project_username, project_name)
    crontab_path = '%s/deploy/crontab' % (project_dir)
    with settings(user=project_username):
        files.upload_template(crontab_template, crontab_path, context=context,
                              use_sudo=False)
        if install:
            with cd(project_dir):
                run('crontab deploy/crontab')


def setup_project(project_name=None, git_url=None, apache_server_name=None,
                  apache_server_alias=None, admin_email=None,
                  settings_module=None, project_username=None, branch=None,
                  cron_settings_module=None, cron_email=None,
                  install_crontab=None, requirements_path=None):
    """
    Creates a user for the project, checks out the code and does basic apache
    config.
    """
    project_name = get_arg(project_name, 'PROJECT_NAME', 'project')
    git_url = get_arg(git_url, 'GIT_URL', None)
    apache_server_name = get_arg(apache_server_name, 'SERVER_NAME',
                                 'localhost')
    apache_server_alias = get_arg(apache_server_alias, 'SERVER_ALIAS',
                           'www.%s' % apache_server_name)
    admin_email = get_arg(admin_email, 'ADMIN_EMAIL',
                          'root@%s' % apache_server_name)
    settings_module = get_arg(settings_module, 'SETTINGS_MODULE', 'settings')
    branch = get_arg(branch, 'BRANCH', 'master')
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               '%s-%s' % (project_name, branch))
    requirements_path = get_arg(requirements_path, 'REQUIREMENTS_PATH',
                                '%s/deploy/requirements.txt' % project_name)
    cron_settings_module = get_arg(cron_settings_module,
                                   'CRON_SETTINGS_MODULE', settings_module)
    cron_email = get_arg(cron_email, 'CRON_EMAIL', 'root@localhost')
    cron_install = get_arg(install_crontab, 'INSTALL_CRONTAB', False)

    local_user = local('whoami', capture=True)
    setup_project_user(project_username)
    print(green("Here is the project user's public key:"))
    sudo('cat /home/%s/.ssh/id_rsa.pub' % project_username)
    print(green("This script will attempt a `git clone` next."))
    prompt(green("Press enter to continue."))
    setup_project_code(git_url, project_name, project_username, branch)
    setup_project_virtualenv(project_username)

    with cd('/home/%s/%s/deploy/logrotate/' % (project_username, project_name)):
        sudo('cat apache2 >> /etc/logrotate.d/apache2')
    update_project(project_name=project_name, project_username=project_username,
                   branch=branch, settings_module=settings_module,
                   cron_settings_module=cron_settings_module,
                   cron_email=cron_email, apache_server_name=apache_server_name,
                   apache_server_alias=apache_server_alias,
                   admin_email=admin_email,
                   initial_deployment=True)

    print(green("""Project setup complete. You may need to patch the """
                """virtualenv to install things like mx. You may do so with """
                """the patch_virtualenv command."""))


def delete_project_code(project_name=None, project_username=None):
    """
    Deletes /home/project_username/target_directory/
    """
    project_name = get_arg(project_name, 'PROJECT_NAME', 'project')
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               '%s-master' % project_name)

    sudo('rm -rf /home/%s/%s' % (project_username, project_name))


def update_project(project_name=None, project_username=None, branch=None,
                   settings_module=None,
                   cron_settings_module=None, cron_email=None,
                   apache_server_name=None, apache_server_alias=None,
                   do_update_apache=True,
                   admin_email=None,
                   initial_deployment=False,
                   do_migrate=False):
    """
    Pull the latest source to a project deployed at target_directory. Also
    update requirements, apache and wsgi files, and crontab.  The
    target_directory is relative to project user's home dir. target_directory
    defaults to project_username ie /home/project/project/
    """
    project_name = get_arg(project_name, 'PROJECT_NAME', 'project')
    branch = get_arg(branch, 'BRANCH', 'master')
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               '%s-%s' % (project_name, branch))
    settings_module = get_arg(settings_module, 'SETTINGS_MODULE', 'settings')
    cron_settings_module = get_arg(cron_settings_module,
                                   'CRON_SETTINGS_MODULE', settings_module)
    cron_email = get_arg(cron_email, 'CRON_EMAIL', 'root@localhost')
    apache_server_name = get_arg(apache_server_name, 'SERVER_NAME',
                                 'localhost')
    apache_server_alias = get_arg(apache_server_alias, 'SERVER_ALIAS',
                                  'www.%s' % apache_server_name)
    admin_email = get_arg(admin_email, 'ADMIN_EMAIL',
                          'root@%s' % apache_server_name)

    local_user = local('whoami', capture=True)

    project_dir = '/home/%s/%s' % (project_username, project_name)
    with cd(project_dir):
        with settings(user=project_username):
            run('git checkout %s' % branch)
            run('git pull')
            run('git submodule update')
            install_project_requirements(project_username,
                             '%s/deploy/requirements.txt' %
                             project_dir)
            if not initial_deployment and do_migrate:
                run('/home/%s/env/bin/python manage.py migrate '
                    '--merge --settings=%s' %
                    (project_username, settings_module))
        if do_update_apache:
            setup_project_apache(project_name, project_username,
                apache_server_name, apache_server_alias, admin_email,
                settings_module, branch=branch)
        setup_project_crontab(project_name, project_username,
                              cron_settings_module, cron_email)
        with settings(user=project_username):
            run('find -L . -name \'*.pyc\' | xargs -r rm')
            git_head = run('git rev-parse HEAD')
    with cd('/home/%s' % project_username):
        log_text = 'Deploy on %s by %s. HEAD: %s' % (datetime.now(),
                                                     local_user,
                                                     git_head)
        files.append('log/deploy.log', log_text, use_sudo=True)


def manage_project(command, project_name=None, project_username=None,
                   settings_module=None):
    """
    Call project's manage.py to peform command.
    """
    project_name = get_arg(project_name, 'PROJECT_NAME', 'project')
    project_username = get_arg(project_username, 'PROJECT_USERNAME',
                               '%s-master' % project_name)
    settings_module = get_arg(settings_module, 'SETTINGS_MODULE', 'settings')

    with settings(user=project_username):
        project_dir = '/home/%s/%s' % (project_username, project_name)
        with cd(project_dir):
            run('/home/%s/env/bin/python manage.py %s --settings=%s' %
                (project_username, command, settings_module))

import os

from fabric.api import run, put, sudo, env, cd, local, prompt, settings
from fabric.contrib.files import comment


def install_solr_schema(local_path='deploy/solr_home/conf/', dest_path='/etc/solr/conf/'):
    local_file = os.path.join(local_path, 'schema.xml')
    dest_file = os.path.join(dest_path, 'schema.xml')
    put(local_file, dest_file, use_sudo=True)

def config_jetty(local_path='deploy/jetty', dest_path='/etc/default/jetty'):
    put(local_path, dest_path, use_sudo=True)
    restart_jetty()

def restart_jetty():
    sudo('/etc/init.d/jetty stop')
    sudo('/etc/init.d/jetty start')

def build_solr_index():
    pass

def install_solr(build_index=True):
    install_solr_schema()
    config_jetty()
    if build_index:
        build_solr_index()
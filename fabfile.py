#! -*- coding: utf8 -*-
"""
Deployment script for tryton on ubuntu 12.04 LTS
Theoretically it can work on any apt-get based GNU/Linux distro
"""

from __future__ import with_statement

import os
import time

from fabric.api import (
        abort,
        cd,
        env,
        prefix,
        put,
        run,
        settings,
        sudo,
        task,
    )
from fabric.contrib.files import exists

#from fabric.contrib.console import confirm
from contextlib import contextmanager as _contextmanager

# Change this for your target HOSTS
env.hosts = ["root@localhost"]

env.directory = "/home/tryton/runtime"
env.virtualenv_directory = "/home/tryton/virtualenv"
env.modules_directory = "/home/tryton/virtualenv/lib/python2.7/site-packages/trytond/modules"
env.app_user = "tryton"
env.dev_file = "develop.txt"
env.bootstrap_script = "tryton_bootstrap.py"
env.requirements = "requirements.txt"
env.modules = "modules.txt"
env.develop_dir = "/home/tryton/develop"

system_dependences = [
        'python-setuptools',
        'python-virtualenv',
        'postgresql',
        'build-essential',
        'postgresql-server-dev-all',
        'python-dev',
        'libxml2-dev',
        'libxslt1-dev',
        'dtach',  # FIXME borrar cuando se demonize el proceso,
        'mercurial',
        'git-core',
        ]


@_contextmanager
def virtualenv():
    """Context manager to work inside a virtualenv"""
    with settings(sudo_user=env.app_user), \
            cd(env.directory), \
            prefix("source %s/bin/activate" % env.virtualenv_directory):
            yield


def create_tryton_user():
    """Create aplication user"""
    run('adduser %s' % env.app_user)


def create_app_dirs():
    """Create app dirs"""
    with settings(sudo_user=env.app_user):
        #FIXME usar una lista y un for
        sudo('mkdir -p %s' % env.directory)
        sudo('mkdir -p %s' % env.virtualenv_directory)
        sudo('mkdir -p %s' % env.develop_dir)


def create_virtualenv():
    with settings(sudo_user=env.app_user), cd(env.directory):
        sudo("virtualenv %s" % env.virtualenv_directory)


@task
def install_system_dependences():
    """Install apt-get based dependences"""
    run('apt-get -q update')
    run('apt-get -q install %s' % ' '.join(system_dependences))


@task
def install_python_dependences():
    """Install all python dependences using pip"""
    reqs = env.requirements
    put(reqs, env.directory)
    with virtualenv():
        sudo('pip install -r %s --log=%s/pip.log' % (reqs, env.directory))


@task
def bootstrap():
    """Creates a new tryton db, and activate all installed modules"""
    put(env.bootstrap_script, env.directory)
    put('trytond.conf', env.directory)
    with virtualenv():
        sudo('python %s' % env.bootstrap_script)


@task
def install_tryton_modules():
    """Install tryton modules using pip"""
    reqs = env.modules
    put(reqs, env.directory)
    with virtualenv():
        sudo('pip install -r %s --log=%s/pip.log' % (reqs, env.directory))


@task
def install_develop_modules():
    """Install git and hg modules in trytond"""
    PULL_DICT = {'git': 'git pull', 'hg': 'hg pull -u'}

    if os.path.isfile(env.dev_file):
        put(env.dev_file, env.directory)
        with virtualenv(), open(env.dev_file, 'r') as fh:
            for line in fh.readlines():
                line = line.replace('\n', '')
                command = None

                if line.startswith('git'):
                    command = 'git'
                elif line.startswith('hg'):
                    command = 'hg'

                if command:
                    with cd(env.develop_dir):
                        dir_name = line.split('/')[-1].split('.')[0]
                        if exists(dir_name):
                            with cd(dir_name):
                                sudo(PULL_DICT[command])
                        else:
                            sudo(line)

                        with cd(dir_name):
                            sudo('python setup.py install')


@task
def copy_module(module_path=None):
    """Copy a module inside trytond modules dir"""
    if not module_path:
        abort("You have to give a module path to upload")
    if module_path.endswith('/'):
        module_path = os.path.dirname(module_path)

    put(module_path, env.modules_directory)
    with cd(env.modules_directory):
        sudo("chown tryton.tryton -R %s" % os.path.basename(module_path))


def start_postgres():
    """Start DB"""
    run("/etc/init.d/postgresql start")


def create_postgres_user():
    """Creates tryton user on database"""
    with settings(sudo_user="postgres"):
        sudo('createuser --createdb --no-adduser -P tryton')


def start_tryton():
    """Start tryton server in a detached enviroment"""
    put('launcher.py', env.directory)
    put('trytond.conf', env.directory)
    put('tryton_start.sh', env.directory)
    with cd(env.directory), settings(sudo_user=env.user):
        sudo('dtach -n /tmp/trytond python launcher.py')


def stop_tryton():
    """Stop tryton daemon"""
    pidfile = "%s/pid" % env.directory
    run("kill  $(cat %s)" % pidfile)


def disable_ipv6():
    """Disable ipv6 on target host"""
    params = [
        "net.ipv6.conf.all.disable_ipv6 = 1",
        "net.ipv6.conf.default.disable_ipv6 = 1",
        "net.ipv6.conf.lo.disable_ipv6 = 1",
        ]

    for line in params:
        run("echo %s >> /etc/sysctl.conf" % line)

    run("sysctl -p")


@task
def deploy():
    """Run a complete deploy on a target server"""
    install_system_dependences()
    create_tryton_user()
    create_app_dirs()
    create_virtualenv()
    install_python_dependences()
    start_postgres()
    create_postgres_user()
    install_tryton_modules()
    install_develop_modules()
    bootstrap()
    start_tryton()


@task
def update():
    """Update system and python packages"""
    install_system_dependences()
    install_python_dependences()
    install_tryton_modules()
    install_develop_modules()
    bootstrap()


@task
def start():
    """Start an installed instance of trytond"""
    start_postgres()
    start_tryton()


@task
def stop():
    """Stop Execution"""
    stop_tryton()


@task
def restart():
    """Restart the instance"""
    stop()
    time.sleep(1)
    start()


@task
def drop_all():
    """Drop all databases in the instance"""
    stop()
    put('drop_all.py', env.directory)
    put('trytond.conf', env.directory)
    with cd(env.directory), settings(sudo_user=env.user):
        sudo('python drop_all.py')
    start()


@task
def update_all_modules():
    """Update all databases in the instance"""
    stop()
    put('updater.py', env.directory)
    put('trytond.conf', env.directory)
    with cd(env.directory), settings(sudo_user=env.user):
        sudo('python updater.py')

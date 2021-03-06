import os.path
import socket
import time
import urllib2

from chef import autoconfigure, Search
from fabric.api import env, put, sudo, task
import fabric.utils


PROJECT_NAME = '@@project_name@@'
DOC_DIR = '/var/www/docs/{0}'.format(PROJECT_NAME)


def _set_credentials():
    """Sets the credentials in the fabric env."""
    # Override credentials here if necessary
    if env.user == 'ubuntu':
        env.key_filename = [
            os.path.expanduser('~/.ssh/ubuntu-id_dsa')]
    env.abort_on_prompts = True
    env.disable_known_hosts = True
    env.use_shell = False


@task
def set_documentation_host():
    env.hosts = ['docs.colo.lair']


@task
def set_hosts(stage, role):
    api = autoconfigure()
    query = 'roles:{project_name}-python-{role}-node AND ' \
        'chef_environment:{stage}'.format(project_name=PROJECT_NAME,
                                          stage=stage, role=role)
    env.stage = stage
    env.hosts = [row.object.attributes.get_dotted('fqdn') for
                 row in Search('node', query, api=api)]


@task
def deploy_api(dist_file, apt_req_file):
    """Deploy the api package"""
    _set_credentials()
    provision()
    _deploy_apt_requirements(apt_req_file)
    _deploy_python_package(dist_file)
    _sighup_api()
    _verify_api_heartbeat()
    send_build_stat(PROJECT_NAME, env.stage)


def _verify_api_heartbeat(retry=True):
    """Tests the host /heartbeat and aborts on failure.

    Only a status of 200 returned by the heartbeat is considered a success.
    If the heartbeat fails and `retry` is ``True``, the heartbeat will be
    tried again after a sleep of 2 seconds. If the heartbeat fails and `retry`
    is ``False``, the task is aborted.

    """
    url = 'http://{0}/heartbeat'.format(env.host_string)
    try:
        resp = urllib2.urlopen(url)
        status_code = resp.getcode()
    except urllib2.HTTPError as error:
        print '[{0}] Error while testing API: {1}'.format(env.host_string,
                                                          error)
        print '[{0}] \t Received: {1}'.format(env.host_string, error.read())
        status_code = error.getcode()

    if status_code == 200:
        print '[{0}] API Test Succesful!'.format(env.host_string)
        return

    if not retry:
        fabric.utils.abort('Host: {0} API is not functioning properly'
                           .format(env.host_string))
    else:
        print '[{0}] Retrying heartbeat in 2 seconds...' \
            .format(env.host_string)
        time.sleep(2)
        _verify_api_heartbeat(retry=False)


@task
def deploy_worker(dist_file):
    """Deploy the worker package"""
    _set_credentials()
    provision()
    _deploy_python_package(dist_file)
    _reload_supervisor()


@task
def provision():
    """Provision the node with Chef"""
    sudo('chef-client')


@task
def deploy_docs(project_name, version):
    """Deploy the documentation"""

    _set_credentials()
    docs_base = '{0}/{1}'
    docs_path = docs_base.format(DOC_DIR, version)
    tar = '{0}_docs.tar.gz'.format(project_name)
    link_to_latest = False

    put(tar, '/tmp/', mode=0666)
    sudo('rm -rf {0}'.format(docs_path), user='www-data')
    sudo('mkdir -p {0}'.format(docs_path), user='www-data')
    sudo('tar zxf /tmp/{0} -C {1}'.format(tar, docs_path), user='www-data')

    if '-' not in version:
        link_to_latest = True
        docs_link = docs_base.format(DOC_DIR, 'production')
    else:
        docs_link = docs_base.format(DOC_DIR, 'staging')

    sudo('chmod -R 775 {0}'.format(docs_path), user='www-data')
    sudo('ln -snf {0} {1}'.format(docs_path, docs_link), user='www-data')
    if link_to_latest:
        latest_link = docs_base.format(DOC_DIR, 'latest')
        sudo('ln -snf {0} {1}'.format(docs_path, latest_link), user='www-data')


def _deploy_apt_requirements(apt_req_file):
    apt_requirements = open(apt_req_file).readlines()

    for apt_req in apt_requirements:
        sudo('apt-get -y install {0}'.format(apt_req))


def _deploy_python_package(dist_file):
    remote_path = '/tmp/{0}-latest.tar.gz'.format(PROJECT_NAME)

    sudo('rm -f {0}'.format(remote_path))
    put(dist_file, remote_path)

    pip_arguments = ' --timeout=2 --index-url=http://pypi.colo.lair/simple/'

    # Install all the deps first.
    sudo('pip install {0} {1}'.format(remote_path, pip_arguments))

    # Install the package even if it's an update with the same name. Pip will
    # not upgrade the package if the version matches the installed version.
    # Forcing an upgrade with dependencies will re-download and install all
    # dependencies.
    sudo('pip install -U {0} --no-deps {1}'.format(remote_path, pip_arguments))
    sudo('rm -f {0}'.format(remote_path))


def _reload_supervisor():
    sudo('supervisorctl reload')


def _sighup_api():
    pid = sudo('supervisorctl status api | '
               'awk \'/RUNNING.*pid/ { sub(/,/, " ", $4); print $4 }\'')
    if pid:
        # There is an API running, we have the right PID
        pid = int(pid)
        sudo('kill -HUP {0}'.format(pid))
    else:
        # There is no API started
        sudo('supervisorctl start api')


def send_build_stat(project_name, environment):
    """Send a metric to graphite that indicates a succesful build

    :param str project_name:
        The name of the project we deployed

    :param str environment:
        The stage where `project_name` was deployed. [staging, production]

    """
    timestamp = int(time.time())

    # In graphite we can draw a non-zero value as an vertical asymptote
    # The packet looks like: <metric> <value> <unix_timestamp>
    metric = 'applications.{0}.build 1 {1}\n'.format(project_name, timestamp)

    port = 2003
    for host in get_graphite_hosts(environment):
        try:
            sock = socket.create_connection((host, port), timeout=0.5)
            print 'Sending metric to {0}: "{1}"'.format(host, metric)
            sock.sendall(metric)
            sock.close()
            return
        except socket.error as error:
            print "ERROR: Unable to send metric to {host}: {error}" \
                .format(host=host, error=error)
            continue


def get_graphite_hosts(environment):
    """Retrieve the hostname for graphite.

    :param str environment:
        The environment in which to locate the graphite server

    """
    api = autoconfigure()
    query = 'roles:graphite-server AND ' \
            'chef_environment:{0}'.format(environment)
    result = Search('node', query, api=api)
    return [row.object.attributes.get_dotted('fqdn') for row in result]

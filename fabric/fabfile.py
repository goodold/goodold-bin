# -*- coding: utf-8 -*-
# Requires Fabric 1.3.3 or newer, http://fabfile.org.
# Install Fabric with e.g. ´sudo easy_install pip && sudo pip install fabric´
# Create a ~/.fabricrc and edit it:
#     cp ~/bin/goodold-bin/fabric/fabricrc.example ~/.fabricrc
# Add the following to your profile if your projects are not located in
# ~/Projects but in e.g ~/Sites (or optionally specify this in ~/.fabricrc):
#    export PROJECT_DIR='~/Sites'
"""
         .-.             .               .     .
   .--.`-'               /     .--.    .-/     /
  /  (_;  .-._..-._..-../     /    )`-' / .-../
 /       (   )(   )(   /     /    /    / (   /
(     --;-`-'  `-'  `-'-..  (    /   _/_.-`-'-..
 `.___.'                     `-.'

– It's fab!
"""

import os
import re
import urlparse
import subprocess
import json
import datetime
from getpass import getpass

from fabric.api import *
from fabric.contrib import console

@task
def db_pull(project=None, remote_name="live"):
  """Fetch a project's live db and import it."""
  project_dir = get_project_dir(project)

  local_site_root = get_local_site_root(project_dir)
  # Set user and host_string from git.
  set_env_from_git(remote_name, local_site_root=local_site_root)


  # Get remote database settings.
  rs = get_dbsettings(env.remote_site_root, remote = True)
  if rs:
    rs['dump'] = '{0}_{1:%Y-%m-%d}.sql.gz'.format(rs['database'], datetime.date.today())
    # Dump and gzip the remote database.
    run('mysqldump -h{host} -u{username} -p{password} {database} | gzip > {dump}'.format(**rs))
    # Download the remote dump to the project directory.
    get(rs['dump'], project_dir)
    # Delete dump from server.
    run('rm {dump}'.format(**rs))
  else:
    abort("Couldn't parse remote database settings.")

  # Get local database settings.
  ls =  get_dbsettings(local_site_root)
  if ls:
    if console.confirm('Do you want to backup your local database?'):
      ls['backup'] = os.path.join(project_dir, '{0}_{1:%Y-%m-%d}_backup.sql.gz'.format(ls['database'], datetime.date.today()))
      # Backup local database.
      local('mysqldump -h{host} -u{username} -p{password} {database} | gzip > {backup}'.format(**ls))

    # Unpack and import remote dump.
    ls['dump'] = os.path.join(project_dir, rs['dump'])
    local('gunzip < {dump} | mysql -h{host} -u{username} -p{password} {database}'.format(**ls))
    # TODO: Remove dump locally?
  else:
    abort("Couldn't parse local database settings.")

@task
def setup_remote(project=None, remote_name="live"):
  """Add and setup remote repo - defaults to live."""
  project_dir = get_project_dir(project)
  local_site_root = get_local_site_root(project_dir)

  if not 'host_string' in env:
    env.host_string = prompt('What is the SSH hostname?')
  if 'user' in env:
    env.user = prompt('What is the SSH user?', default='root')
  if not "remote_site_root" in env:
    env.remote_site_root = prompt('What is the absolute path of the remote repo?', default='/mnt/persist/www/docroot')

  with lcd(local_site_root):
    local('git remote add {remote_name} ssh://{user}@{host}{path}'.format(
        remote_name=remote_name,
        host=env.host_string,
        user=env.user,
        path=env.remote_site_root
        ))

  with cd(env.remote_site_root):
    # Initialize and switch repo to branch "live" since it's not possible to
    # push to a checked out branch. git checkout -b doesn't work on empty
    # repositories so use git-symbolic-ref. Note that the checked out branch
    # is always named "live" on the remote side.
    run('git init && git symbolic-ref HEAD refs/heads/live')

  local('git push {remote_name} master'.format(remote_name=remote_name))

  with cd(env.remote_site_root):
    run('git merge master')

  if console.confirm('Setup automatic merge on the remote git repo? This is useful during active development but should be disabled during production. Use "fab setup_post_receive:disable=True" to disable.'):
    setup_post_receive(remote_name=remote_name)

@task
def setup_post_receive(project=None, remote_name="live", disable=False):
  """Setup or disable setup_post_receive on push to remote git repo."""
  # Set user and host_string from git.
  set_env_from_git(remote_name, project)

  hooks_dir = os.path.join(env.remote_site_root, '.git', 'hooks')

  if disable:
    with cd(hooks_dir):
      run('rm post-receive')

  else:
    put(os.path.join(os.path.dirname(__file__), 'post-receive'), hooks_dir, mirror_local_mode=True)
    # Ask if clear cache command should be added if drush is installed and
    # it's a Drupal site.
    if 'drupal_version' in drush_status(env.remote_site_root, remote = True):
      if console.confirm("Should drush clear Drupal's cache after merge?"):
        with cd(hooks_dir):
          run('echo \'drush --root="$wd" cc all\' >> post-receive')

@task
def setup_local_site(sitename, repo=None):
  """Create a new local site from an existing repo."""
  projects_dir = get_projects_dir()
  tld = env.get('local_tld', env.local_user)
  dir_name = sitename if tld == '' else sitename + '.' + tld
  local_site_rote = os.path.join(projects_dir, dir_name, 'public_html')

  # Create directories and clone repo.
  local('mkdir -p {local_site_rote}'.format(**locals()))
  repo = repo if repo else 'git@github.com:goodold/{sitename}.git'.format(**locals())
  local('git clone {repo} {local_site_rote}'.format(**locals()))

  # Create database.
  db_user = env.get('local_db_user', 'root')
  if 'local_db_password' in env:
    db_pass = env.local_db_password
  else:
    db_pass = getpass('What is your local database password?')
  local('mysql -u{db_user} -h127.0.0.1 -p{db_pass} -e "CREATE DATABASE {sitename}"'.format(**locals()))

  # Create settings.php and files directory if this is Drupal.
  ds = drush_status(local_site_rote)
  if ds and 'drupal_version' in ds:
    with lcd(local_site_rote):
      local('drush-rewrite-settings --db-url=mysql://{db_user}:{db_pass}@127.0.0.1/{sitename} --db-prefix={db_prefix}'
          .format(**locals()))
      local('mkdir sites/default/files')
      local('sudo chown _www sites/default/files')

@task
def ssh(project=None, remote_name="live", dir=None):
  """Open an interactive shell using the a remotes config.
Defaults to the remotes git directory.
  """
  # Set user and host_string from git.
  set_env_from_git(remote_name, project)

  # Default to remote site root if dir is not specified.
  env.dir = dir if dir else env.remote_site_root

  # Open an interactive ssh shell and cd to the directory. -t is needed
  # to execute the cd command on the remote. bash at the end prevents it from
  # quiting the session.
  subprocess.call(['ssh', '-t', '{user}@{host_string}'.format(**env), 'cd {dir}; bash'.format(**env)])

def validate_public_key(input):
  # Input is ignored since it's captured from the clipboard instead.
  with hide('running'):
    key = local('pbpaste', capture = True)

  if key.find('ssh-') == 0:
    return key
  else:
    raise Exception("The clipboard doesn't contain a public key.")


def get_projects_dir():
  """Return the projects directory or abort if it doesn't exits.
  User can set their project directory in their shell profile. For example:
  export PROJECT_DIR='~/Sites' or in their .fabricrc
  Defaults to ~/Projects."""

  if 'projects_dir' in env:
    projects_dir = os.path.expanduser(env.projects_dir)
  else:
    projects_dir = os.path.expanduser(os.environ.get('PROJECT_DIR', '~/Projects'))

  if not os.path.exists(projects_dir):
    abort("Can't find project directory \"{projects_dir}\". Specify it in your bash profile by adding:\n\
      export PROJECT_DIR='path-to-project-dir'".format(projects_dir=projects_dir))

  return projects_dir

def get_project_dir(project):
  projects_dir = get_projects_dir()

  project_dir = None
  if project:
    # Find the project directory based on the specified project name.
    # Match by ignoring a possible domain suffix. E.g "drupal" mathes "drupal",
    # "drupal.local", "drupal.dev" etc.
    r = re.compile(r'%s\.?.*$' % project)

    for dir in os.listdir(projects_dir):
      if r.match(dir):
         project_dir = os.path.join(projects_dir, dir)
         break

    if not project_dir:
      abort('No project directory found for %s.' % project)

    return project_dir
  else:
    # Find the project directory based on the current working directory.
    cwd =  os.getcwd()
    # Make sure there is _one_ trailing "/" in the path used in the regex.
    parent = os.path.normpath(projects_dir) + os.sep
    try:
      # Match a subfolder of projects_dir in the current working directory.
      project_dir = re.match("(%s[^%s]*)" % (parent, os.sep), cwd).group(0)
    except:
      abort("This doesn't seem to be a project directory.")

  return project_dir

def get_local_site_root(project_dir):
  dir = os.path.join(project_dir, 'public_html')
  return dir if os.path.exists(dir) else project_dir

def set_env_from_git(remote_name="live", project= None, local_site_root = None):
  """Parse SSH settings from a remote. Supports ssh://USER@HOSTPATH and USER@HOST:PATH."""

  # Get local_site_root (git repo) if not specified
  if not local_site_root:
    local_site_root = get_local_site_root(get_project_dir(project))

  with lcd(local_site_root):
    # Get SSH info from the remote remote_name settings.
    ssh_settings = local('git config --get remote.{remote_name}.url'.format(remote_name=remote_name), True)

  if ssh_settings.find('ssh://') > -1:
    # ssh://USER@HOSTPATH
    # Work around limitation in urlparse.
    ssh_settings = ssh_settings.replace('ssh://', 'http://')
  else:
    # USER@HOST:PATH
    # Add "http://" and remove ':' to make it parsable with urlparse
    ssh_settings = 'http://' + ssh_settings
    ssh_settings.replace(':', '')

  # Parse the uri.
  ssh_settings = urlparse.urlparse(ssh_settings)
  # Set info that fabric uses to connect.
  env.user = ssh_settings.username
  env.host_string = ssh_settings.hostname
  # Set remote site root that can be used by tasks
  env.remote_site_root = ssh_settings.path

def get_dbsettings(site_root, remote = False):
  settings = None
  ds = drush_status(site_root, remote)
  if ds and 'database_name' in ds:
    settings = {
      'username': ds['database_username'],
      'host': ds['database_hostname'],
      'password': ds['database_password'],
      'database': ds['database_name']}
  else:
    # Fall back to retrieve db settings by calling dbsettings.php which supports
    # Drupal (without drush) and Wordpress.
    if remote:
      # Use bare ssh and not run() since we want to be able to pipe a
      # PHP-script.
      ssh_host = env.user + "@" + env.host_string
      proc = subprocess.Popen(["ssh", ssh_host, "php"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    else:
      # Here we could use local() but let's keep the same semantics as for remote.
      proc = subprocess.Popen(["php"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    f = open(os.path.join(os.path.dirname( __file__ ), 'dbsettings.php'), 'r');
    change_dir = '<?php chdir("' + site_root +'"); ?>'
    result = proc.communicate(change_dir + f.read())
    if result[0]:
      settings = json.loads(result[0])

  return settings

def drush_status(site_root, remote = False):
  status = None
  with settings(
      # Don't abort if drush is not installed and be quit.
      hide('warnings', 'running', 'stdout'),
      warn_only = True
    ):
    command = 'drush status --root={0} --show-passwords --pipe'.format(site_root)
    if remote:
      out = run(command)
    else:
      out = local(command, capture = True)
    if out.succeeded:
      # Parse drush status output.
      status = {}
      for line in out.splitlines():
        parts = line.partition('=')
        status[parts[0]] = parts[2]

  return status

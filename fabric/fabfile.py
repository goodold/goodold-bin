# -*- coding: utf-8 -*-
# Requires Fabric 1.3.3 or newer, http://fabfile.org.
# Install Fabric with e.g. ´sudo easy_install pip && sudo pip install fabric´
# echo "fabfile=~/bin/goodold-bin/fabric/fabfile.py" >> ~/.fabricrc

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

from fabric.api import *
from fabric.contrib import console

@task
def pulldb(project=None, branch="live"):
  """Fetch a project's live db and import it."""
  project_dir = get_project_dir(project)

  local_site_root = os.path.join(project_dir, 'public_html')
  # Set env attributes if not already available.
  if not env.host_string or not env.user or not env.remote_site_root:
    set_env_from_git(os.path.join(get_project_dir(project), 'public_html'), branch)


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
def setuplive(project=None, branch="live"):
  """Setup remote repo - usually called live."""
  env.host_string = prompt('What is the SSH hostname?')
  env.user = prompt('What is the SSH user?', default='root')
  env.remote_site_root = prompt('What is the absolute path of the remote repo?', default='/mnt/persist/www/docroot')
  local('git remote add {branch} ssh://{user}@{host}{path}'.format(
      branch=branch,
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

  local('git push {branch} master'.format(branch=branch))

  with cd(env.remote_site_root):
    run('git merge master')

  if console.confirm('Setup automatic merge on the remote git repo? This is useful during active development but should be disabled during production. Use "fab automerge:disable=True" to disable.'):
    automerge(branch=branch)

@task
def automerge(project=None, branch="live", disable=False):
  """Setup or disable automerge on push to remote git repo."""
  # Set env attributes if not already available.
  if not env.host_string or not env.user or not env.remote_site_root:
    set_env_from_git(os.path.join(get_project_dir(project), 'public_html'), branch)

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

def get_project_dir(project):
  # User can set their project directory in their shell profile. For example:
  # export PROJECT_DIR='~/Sites'
  # Defaults to ~/Projects.
  projects_dir = os.path.expanduser(os.environ.get('PROJECT_DIR', '~/Projects'))
  if project:
    # Find the project directory based on the specified project name.
    # Match by ignoring a possible domain suffix. E.g "drupal" mathes "drupal",
    # "drupal.local", "drupal.dev" etc.
    r = re.compile(r'%s\.?.*$' % project)
    project_dir = None

    for dir in os.listdir(projects_dir):
      if r.match(dir):
         project_dir = os.path.join(projects_dir, dir)
         break

    if not project_dir:
      abort('No project directory found for %s.' % project)
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

def set_env_from_git(local_site_root, branch="live"):
  with lcd(local_site_root):
    # Get SSH info from the remote branch settings.
    ssh_settings = local('git config --get remote.{branch}.url'.format(branch=branch), True)

  # Work around limitation in urlparse.
  ssh_settings = ssh_settings.replace('ssh://', 'http://')
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
  if 'database_name' in ds:
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
    f = open('/Users/anders/bin/goodold-bin/fabric/dbsettings.php', 'r');
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

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
def pulldb(project=None):
  """[:project] Fetch a project's live db and import it."""
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

  local_site_root = os.path.join(project_dir, 'public_html')

  with lcd(local_site_root):
    # Get ssh info from the remote named "live".
    ssh_settings = local('git config --get remote.live.url', True)

  # Work around limitation in urlparse.
  ssh_settings = ssh_settings.replace('ssh://', 'http://')
  # Parse the uri.
  ssh_settings = urlparse.urlparse(ssh_settings)
  # Set info that fabric uses to connect.
  env.user = ssh_settings.username
  env.host_string = ssh_settings.hostname

  # Get remote database settings.
  rs = get_dbsettings(ssh_settings.path, remote = True)

  rs['dump'] = '{0}_{1:%Y-%m-%d}.sql.gz'.format(rs['database'], datetime.date.today())
  # Dump and gzip the remote database.
  run('mysqldump -h{host} -u{username} -p{password} {database} | gzip > {dump}'.format(**rs))
  # Download the remote dump to the project directory.
  get(rs['dump'], project_dir)
  # Delete dump from server.
  run('rm {dump}'.format(**rs))

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

def get_dbsettings(site_root, remote = False):
  with settings(
      # Don't abort on warnings to handle drush not being installed gracefully.
      hide('warnings', 'running', 'stdout'),
      warn_only=True
    ):
    drush_status = 'drush status --root=%s --show-passwords --pipe' % site_root
    if remote:
      out = run(drush_status)
    else:
      out = local(drush_status, capture = True)
    if out.succeeded:
      # Parse drush status output.
      drush_status = {}
      for line in out.splitlines():
        parts = line.partition('=')
        drush_status[parts[0]] = parts[2]
      if 'database_name' in drush_status:
        return {
          'username': drush_status['database_username'],
          'host': drush_status['database_hostname'],
          'password': drush_status['database_password'],
          'database': drush_status['database_name']}

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
      return json.loads(result[0])

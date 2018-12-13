#!/usr/bin/env python3

import os
import logging
import subprocess
from time import sleep
from shlex import quote
from gvm_client import GVM_client

env_ov_passwd = 'OV_PASSWD'
db_path = '/var/lib/openvas/gvmd/gvmd.db'
gvm_socket = '/var/run/gvmd.sock'
ov_user = 'admin'

overrides_path = '/overrides'
reports_path = '/reports'
configs_path = '/configs'
targets_path = '/targets'
tasks_path = '/tasks'

gvmd_wait_secs = 6
gvmd_connect_tries = 10

loglevel = logging.INFO

def create_user(username, password):
  logging.log(logging.INFO, 'Creating user {}...'.format(username))
  command = 'gvmd -d {} --create-user {} --password={}'.format(db_path, quote(username), quote(password))
  os.system(command)

if __name__ == '__main__':
  logging.basicConfig(level=loglevel)

  admin_pass = os.environ.get(env_ov_passwd)
  if admin_pass != None:
    create_user(ov_user, admin_pass)
  else:
    print('Admin password hasn\'t specified')
    print('Please pass admin password via {} env variable'.format(env_ov_passwd))
    exit(1)
  
  supervisor_proc = subprocess.Popen(['supervisord','-n', '-c', '/etc/openvas-supervisor.conf'])

  try:
    processor = GVM_client(
      socket_path=gvm_socket, 
      user=ov_user,
      password=os.environ.get(env_ov_passwd),
      loglevel=loglevel)

    while not processor.connect():
      if processor.connection_errors <= gvmd_connect_tries:
        sleep(gvmd_wait_secs)
      else:
        raise Exception('Can\'t connect to gvmd for {} sec'.format(gvmd_connect_tries*gvmd_wait_secs))

    processor.import_configs(configs_path)
    processor.import_targets(targets_path)
    processor.import_tasks(tasks_path)

    processor.sync_wait()
    processor.import_reports(reports_path)
    processor.import_overrides(overrides_path)

  except Exception as ex:
    logging.log(logging.ERROR, 'GVM_client error: {}'.format(ex))
  
  supervisor_proc.wait()

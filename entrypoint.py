#!/usr/bin/env python3

import os
import subprocess
from shlex import quote

env_ov_passwd = 'OV_PASSWD'
db_path = '/var/lib/openvas/gvmd/gvmd.db'

def create_user(username, password):
  print('Creating user {}...'.format(username))
  command = 'gvmd -d {} --create-user {} --password={}'.format(db_path, quote(username), quote(password))
  os.system(command)

if __name__ == '__main__':
  admin_pass = os.environ.get(env_ov_passwd)
  if admin_pass != None:
    create_user('admin', admin_pass)
  else:
    print('Admin password hasn\'t specified')
    print('Please pass admin password via {} env variable'.format(env_ov_passwd))
    exit(1)
  subprocess.Popen(['supervisord','-n', '-c', '/etc/openvas-supervisor.conf']).wait()

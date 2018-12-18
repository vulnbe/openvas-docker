#!/usr/bin/env python3

import os
import logging
import subprocess
import argparse
from time import sleep
from shlex import quote
from gvm_client import GVM_client

env_ov_passwd = 'OV_PASSWD'
env_ov_run_tasks = 'OV_AUTORUN_TASKS'
env_ov_save_reports = 'OV_AUTOSAVE_REPORTS'
db_path = '/var/lib/openvas/gvmd/gvmd.db'
redis_conf = '/etc/openvas-redis.conf'
gvm_socket = '/var/run/gvmd.sock'
redis_socket = '/tmp/redis.sock'
ov_user = 'admin'

overrides_path = '/overrides'
reports_path = '/reports'
configs_path = '/configs'
targets_path = '/targets'
tasks_path = '/tasks'

gvmd_wait_secs = 6
gvmd_connect_tries = 10
task_wait_secs = 15

loglevel = logging.INFO

def create_user(username, password):
  logging.log(logging.INFO, 'Creating user {}...'.format(username))
  command = 'gvmd -d {} --create-user {} --password={}'.format(db_path, quote(username), quote(password))
  os.system(command)

def delete_user(username):
  logging.log(logging.INFO, 'Deleting user {}...'.format(username))
  command = 'gvmd -d {} --delete-user {}'.format(db_path, quote(username))
  os.system(command)

def ping_redis():
  try:
    response = subprocess.check_output(['redis-cli','-s', redis_socket, 'ping']).decode('utf-8')
    logging.info('Ping redis: {}'.format(response))
    return response == 'PONG\n'
  except Exception as ex:
    logging.error('Ping redis error: {}'.format(ex))
    return False

def shutdown_redis():
  try:
    logging.info('Shutdown redis: {}'.format(subprocess.check_output(['redis-cli','-s', redis_socket, 'SHUTDOWN', 'SAVE']).decode('utf-8')))
  except Exception as ex:
    logging.error('Shutdown redis error: {}'.format(ex))

if __name__ == '__main__':
  logging.basicConfig(level=loglevel)
  
  parser = argparse.ArgumentParser()
  parser.add_argument('--create-cache', dest='create_cache', default=False, action='store_true')
  parser.add_argument('--only-run-tasks', dest='only_run_tasks', default=False, action='store_true')
  args = parser.parse_args()

  if args.create_cache:
    admin_pass = 'cache'
    create_user(ov_user, admin_pass)
    
    redis_proc = subprocess.Popen(['redis-server', redis_conf])
    while not ping_redis():
      logging.info('Waiting for redis...')
      sleep(1)

    openvassd_proc = subprocess.Popen(['openvassd', '-f'])
    gvmd_proc = subprocess.Popen(['gvmd', '-f','-d', db_path])
    processor = GVM_client(
      socket_path=gvm_socket,
      user=ov_user,
      password=admin_pass,
      loglevel=loglevel)

    processor.wait_connection(connection_tries=gvmd_connect_tries, secs_before_attempt=gvmd_wait_secs)
    processor.wait_sync()

    shutdown_redis()
    delete_user(ov_user)
  else:
    admin_pass = os.environ.get(env_ov_passwd)
    logging.error('admin_pass')
    if not args.only_run_tasks:
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
        password=admin_pass,
        loglevel=loglevel)

      processor.wait_connection(connection_tries=gvmd_connect_tries, secs_before_attempt=gvmd_wait_secs)
      processor.wait_sync()

      if not args.only_run_tasks:
        processor.import_configs(configs_path)
        processor.import_targets(targets_path)
        processor.import_tasks(tasks_path)
        processor.import_reports(reports_path)
        processor.import_overrides(overrides_path)

      if os.environ.get(env_ov_run_tasks, ''):
        tasks = processor.get_tasks()
        for task in tasks:
          if task.status in ['New', 'Done', 'Stopped']:
            processor.run_task(task.id)
            logging.info('Waiting for task: {}'.format(task.name))
            while True:
              sleep(task_wait_secs)
              _task = processor.get_task(task.id)
              if _task.status == 'Done':
                if os.environ.get(env_ov_save_reports, '') and _task.last_report != None:
                  try:
                    processor.save_report(_task.last_report.id, reports_path)
                  except Exception as ex:
                    logging.error('Saving report error: {}'.format(ex))
                break
              elif _task.status == 'Stopped':
                logging.error('Ignoring stopped task: {}'.format(task.name))
                break

    except Exception as ex:
      logging.error('GVM_client error: {}'.format(ex))

    if not args.only_run_tasks:
      supervisor_proc.wait()

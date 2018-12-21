#!/usr/bin/env python3

import os
import logging
import subprocess
import argparse
from time import sleep
from shlex import quote
from gvm_client import GVM_client, Task

env_ov_passwd = 'OV_PASSWD'
env_ov_run_tasks = 'OV_AUTORUN_TASKS'
env_ov_save_reports = 'OV_AUTOSAVE_REPORTS'
redis_conf = '/etc/openvas-redis.conf'
redis_socket = '/tmp/redis.sock'
gvm_socket = '/var/run/gvmd.sock'
supervisor_conf = '/etc/openvas-supervisor.conf'
ov_user = 'admin'

overrides_path = '/overrides'
reports_path = '/reports'
configs_path = '/configs'
targets_path = '/targets'
tasks_path = '/tasks'
openvassd_wait_secs = 60
gvmd_wait_secs = 6
gvmd_connect_tries = 10
task_wait_secs = 15

loglevel = logging.INFO

def create_user(username, password):
  logging.log(logging.INFO, 'Creating user {}...'.format(username))
  command = 'gvmd --create-user {} --password={}'.format(quote(username), quote(password))
  os.system(command)

def delete_user(username):
  logging.log(logging.INFO, 'Deleting user {}...'.format(username))
  command = 'gvmd --delete-user {}'.format(quote(username))
  os.system(command)

def ping_postgres():
  try:
    subprocess.check_call(['pg_isready', '-h', 'localhost', '-p', '5432'])
    logging.info('Postgres is running')
    return True
  except:
    logging.error('Unable to reach Postgres')
    return False

def run_postgres():
  if not ping_postgres():
    subprocess.Popen(['/etc/init.d/postgresql', 'start']).wait()
    while not ping_postgres():
      logging.info('Waiting for postgres to start...')
      sleep(1)

def stop_postgres():
  if ping_postgres():
    subprocess.Popen(['/etc/init.d/postgresql', 'stop']).wait()
    while ping_postgres():
      logging.info('Waiting for Postgres to stop...')
      sleep(1)

def ping_redis():
  try:
    response = subprocess.check_output(['redis-cli','-s', redis_socket, 'ping']).decode('utf-8')
    logging.info('Ping redis: {}'.format(response))
    return response == 'PONG\n'
  except:
    logging.error('Unable to reach Redis')
    return False

def run_redis():
  if not ping_redis():
    subprocess.Popen(['redis-server', redis_conf])
    while not ping_redis():
      logging.info('Waiting for redis...')
      sleep(1)

def stop_redis():
  try:
    logging.info('Shutdown Redis: {}'.format(subprocess.check_output(['redis-cli','-s', redis_socket, 'SHUTDOWN', 'SAVE']).decode('utf-8')))
  except Exception as ex:
    logging.error('Shutdown Redis error: {}'.format(ex))

def stop_process(process:subprocess.Popen):
  try:
    process.send_signal(subprocess.signal.SIGINT)
    process.wait()
  except:
    pass

def task_can_be_runned(task: Task):
  return task != None and task.status in ['New', 'Done', 'Stopped']

def task_runned(task: Task):
  return task != None and task.status in ['Running', 'Requested']

if __name__ == '__main__':
  logging.basicConfig(level=loglevel)

  parser = argparse.ArgumentParser()
  parser.add_argument('--create-cache', dest='create_cache', default=False, action='store_true')
  parser.add_argument('--only-run-tasks', dest='only_run_tasks', default=False, action='store_true')
  args = parser.parse_args()

  if args.create_cache:
    run_postgres()
    run_redis()

    openvassd_proc = subprocess.Popen(['openvassd', '-f'])
    sleep(openvassd_wait_secs)

    # Prepare DB
    subprocess.Popen(['gvmd', '-u', '-v']).wait()

    # Sync feeds
    subprocess.Popen(['greenbone-nvt-sync']).wait()
    sleep(openvassd_wait_secs)
    subprocess.Popen(['greenbone-certdata-sync']).wait()
    sleep(openvassd_wait_secs)
    subprocess.Popen(['greenbone-scapdata-sync']).wait()

    # Update DB
    subprocess.Popen(['gvmd', '-u', '-v']).wait()

    # Run gvm and check updates
    gvmd_proc = subprocess.Popen(['gvmd', '-f', '-c', gvm_socket])

    admin_pass = 'cache'
    create_user(ov_user, admin_pass)

    processor = GVM_client(
      socket_path=gvm_socket,
      user=ov_user,
      password=admin_pass,
      loglevel=loglevel)

    processor.wait_connection(connection_tries=gvmd_connect_tries, secs_before_attempt=gvmd_wait_secs)
    processor.wait_sync(interval=20)

    delete_user(ov_user)

    stop_process(openvassd_proc)
    stop_process(gvmd_proc)
    stop_postgres()
    stop_redis()
  else:
    admin_pass = os.environ.get(env_ov_passwd)
    if not args.only_run_tasks:
      run_postgres()
      run_redis()

      if admin_pass != None:
        create_user(ov_user, admin_pass)
      else:
        print('Admin password hasn\'t specified')
        print('Please pass admin password via {} env variable'.format(env_ov_passwd))
        exit(1)

      supervisor_proc = subprocess.Popen(['supervisord','-n', '-c', supervisor_conf])

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
          for run_try in range(1, 4):
            _task = processor.get_task(task.id)
            if task_can_be_runned(_task):
              logging.info('#{} try to run task: {}'.format(run_try, task.name))
              if task_runned(_task) or processor.run_task(task.id):
                logging.info('Waiting for task: {}'.format(task.name))
                while True:
                  sleep(task_wait_secs)
                  _task = processor.get_task(task.id)
                  if _task != None and _task.status == 'Done':
                    if os.environ.get(env_ov_save_reports, '') and _task.last_report != None:
                      try:
                        processor.save_report(_task.last_report.id, reports_path)
                      except Exception as ex:
                        logging.error('Saving report error: {}'.format(ex))
                    break
                  elif _task != None and not task_runned(_task):
                    logging.error('Ignoring stopped/crashed task: {}'.format(task.name))
                    break
                break
              else:
                logging.error('Error running task: {}'.format(task.name))
                sleep(5)
            else:
              logging.error('Wrong task status: {}'.format(task.name))
              sleep(5)

    except Exception as ex:
      logging.error('GVM_client error: {}'.format(ex))

    if not args.only_run_tasks:
      supervisor_proc.wait()

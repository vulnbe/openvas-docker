#!/usr/bin/env python3

import logging
import glob
import io
import os
import threading
import xml.etree.ElementTree as ET
from time import sleep
from gvm.connections import UnixSocketConnection, DebugConnection
from gvm.protocols.latest import Gmp
from gvm.transforms import EtreeTransform, EtreeCheckCommandTransform
from gvm.xml import pretty_print
from gvm.errors import GvmError

logging.basicConfig(level=logging.DEBUG)

gvm_socket = '/var/run/gvmd.sock'
ov_user = 'admin'
env_ov_passwd = 'OV_PASSWD'

reports_path = '/reports'
configs_path = '/configs'
targets_path = '/targets'
tasks_path = '/tasks'

gvmd_wait_secs = 6
gvmd_connect_tries = 10

class GVM_processor:
  def __init__(self, socket_path, user, password):
    self.connection_errors = 0
    self.container_tasks = {}
    self.password = password
    self.user = user
    self.socketconnection = UnixSocketConnection(path=socket_path, timeout=10)
    self.connection = DebugConnection(self.socketconnection)
    self.transform = EtreeCheckCommandTransform()
    self.gmp = Gmp(connection=self.connection, transform=self.transform)
    self.test_connection()

  def test_connection(self):
    try:
      with self.gmp:
        self.gmp.authenticate(self.user, self.password)
        self.connected = self.gmp._connected
      return True
    except:
      self.connection_errors += 1
      return False

  def get_xmls(self, directory):
    results = []
    for file_name in os.listdir(directory):
      if file_name.lower().endswith(".xml"):
        file_path = os.path.join(directory, file_name)
        logging.log(logging.DEBUG, 'Processing file {}'.format(file_path))
        with io.open(file_path, 'r', encoding='utf-8') as file:
          results.append(''.join(file.readlines()))
    return results

  def import_configs(self, directory):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)
      for config in self.get_xmls(directory):
        self.gmp.import_config(config)

  def import_targets(self, directory):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)
      for target_config in self.get_xmls(directory):
        try:
          root = ET.fromstring(target_config)
          name = root.find('target/name').text
          logging.log(logging.DEBUG, 'Importing target - name: {}'.format(name))
          comment = root.find('target/comment').text
          logging.log(logging.DEBUG, 'Importing target - comment: {}'.format(comment))
          hosts = root.find('target/hosts').text.split(', ')
          logging.log(logging.DEBUG, 'Importing target - hosts: {}'.format(', '.join(hosts)))
          exclude_hosts = root.find('target/exclude_hosts').text

          if exclude_hosts is not None:
            logging.log(logging.DEBUG, 'Importing target - exclude_hosts: {}'.format(exclude_hosts))
            exclude_hosts = exclude_hosts.split(', ')

          alive_tests = root.find('target/alive_tests').text
          logging.log(logging.DEBUG, 'Importing target - alive_tests: {}'.format(alive_tests))
          reverse_lookup_only = bool(int(root.find('target/reverse_lookup_only').text))
          reverse_lookup_unify = bool(int(root.find('target/reverse_lookup_unify').text))
          port_range = root.find('target/port_range')

          if port_range is not None:
            port_range = port_range.text
            logging.log(logging.DEBUG, 'Importing target - port_range: {}'.format(port_range))
          port_list_id = root.find('target/port_list_id')

          if port_list_id is not None:
            port_list_id = port_list_id.text
            logging.log(logging.DEBUG, 'Importing target - port_list_id: {}'.format(port_list_id))

          self.gmp.create_target(name=name,
            make_unique=True, 
            hosts=hosts, 
            exclude_hosts=exclude_hosts, 
            comment=comment, 
            alive_tests=alive_tests,
            reverse_lookup_only=reverse_lookup_only,
            reverse_lookup_unify=reverse_lookup_unify,
            port_range=port_range,
            port_list_id=port_list_id,
            asset_hosts_filter=None,
            ssh_credential_id=None,
            ssh_credential_port=None,
            smb_credential_id=None,
            snmp_credential_id=None,
            esxi_credential_id=None)

        except Exception as ex:
          logging.log(logging.ERROR, 'Importing target error: {}'.format(ex))
          continue

  def import_tasks(self, directory):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)

      for task_config in self.get_xmls(directory):
        try:
          root = ET.fromstring(task_config)
          task_name = root.find('task/name').text
          logging.log(logging.DEBUG, 'Importing task - name: {}'.format(task_name))
          target_id = None
          targets = self.gmp.get_targets().xpath('target')

          for target in targets:
            target_name = target.find('name').text 
            if target_name == task_name:
              target_id = target.attrib['id']
              logging.log(logging.DEBUG, 'Importing task - target_id: {}'.format(target_id))

          if target_id == None:
            logging.log(logging.DEBUG, 'Importing task - {}. No target_id found'.format(task_name))
            continue

          comment = root.find('task/comment').text
          logging.log(logging.DEBUG, 'Importing task - comment: {}'.format(comment))
          scanner_id = root.find('task/scanner').attrib['id']
          logging.log(logging.DEBUG, 'Importing task - scanner_id: {}'.format(scanner_id))
          config_id = root.find('task/config').attrib['id']
          logging.log(logging.DEBUG, 'Importing task - config_id: {}'.format(config_id))
          alterable = bool(int(root.find('task/alterable').text))
          self.gmp.create_task(name=task_name,
            target_id=target_id,
            scanner_id=scanner_id,
            config_id=config_id,
            comment=comment,
            alterable=alterable,
            alert_ids=None,
            hosts_ordering=None,
            schedule_id=None,
            schedule_periods=None,
            observers=None)

        except Exception as ex:
          logging.log(logging.ERROR, 'Importing task error: {}'.format(ex))
          continue

  def import_reports(self, directory):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)

      for report_config in self.get_xmls(directory):
        try:
          root = ET.fromstring(report_config)
          task_name = root.find('report/task/name').text
          logging.log(logging.DEBUG, 'Importing report - task_name: {}'.format(task_name))
          task_comment = root.find('report/task/comment').text
          logging.log(logging.DEBUG, 'Importing report - task_comment: {}'.format(task_comment))

          if task_name not in self.container_tasks.keys():
            response = self.gmp.import_report(report_config,
              task_name=task_name,
              task_comment=task_comment)

            if response.attrib['status'] == '201':
              self.container_tasks[task_name] = response.attrib['id']
          else:
            self.gmp.import_report(report_config,
              task_id=self.container_tasks[task_name])

        except Exception as ex:
          logging.log(logging.ERROR, 'Importing report error: {}'.format(ex))
          continue

  def get_targets(self):
    with self.gmp:
      targets = []
      self.gmp.authenticate(self.user, self.password)
      gmp_targets = self.gmp.get_targets()
      targets = gmp_targets.xpath('target')
      logging.log(logging.DEBUG, 'Targets found in DB: {}'.format(', '.join([target.find('name').text for target in targets])))

if __name__ == '__main__':
  processor = GVM_processor(socket_path=gvm_socket, 
    user=ov_user,
    password=os.environ.get(env_ov_passwd))
  
  while not processor.test_connection():
    if processor.connection_errors <= gvmd_connect_tries:
      sleep(gvmd_wait_secs)
    else:
      logging.log(logging.ERROR, 'Can\'t connect to gvmd for {} sec'.format(gvmd_connect_tries*gvmd_wait_secs))
      exit(1)
  
  processor.import_configs(configs_path)
  processor.import_targets(targets_path)
  processor.import_tasks(tasks_path)
  processor.import_reports(reports_path)

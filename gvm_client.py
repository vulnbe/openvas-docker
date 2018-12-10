import glob
import io
import os
import logging
import xml.etree.ElementTree as ET

from gvm.connections import UnixSocketConnection, DebugConnection
from gvm.protocols.gmpv8 import Gmp
from gvm.transforms import EtreeTransform, EtreeCheckCommandTransform
from gvm.xml import pretty_print
from gvm.errors import GvmError

class GVM_client:
  def __init__(self, password, socket_path='/var/run/gvmd.sock', user='admin', timeout=10, loglevel=logging.ERROR):
    logging.basicConfig(level=loglevel)
    self.connection_errors = 0
    self.container_tasks = {}
    self.password = password
    self.user = user
    self.socketconnection = UnixSocketConnection(path=socket_path, timeout=timeout)
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
        try:
          response = self.gmp.import_config(config)

          if response.attrib['status'] == '201':
            config_root = ET.fromstring(config)
            config_name = config_root.find('config/name').text
            logging.log(logging.INFO, 'Importing config OK: {}'.format(config_name))

        except Exception as ex:
          logging.log(logging.ERROR, 'Importing config error: {}'.format(ex))

  def import_targets(self, directory):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)
      for target_config in self.get_xmls(directory):
        try:
          target_root = ET.fromstring(target_config)

          target_name = target_root.find('target/name').text
          logging.log(logging.DEBUG, 'Importing target - name: {}'.format(target_name))

          comment = target_root.find('target/comment').text
          logging.log(logging.DEBUG, 'Importing target - comment: {}'.format(comment))

          hosts = target_root.find('target/hosts').text.split(', ')
          logging.log(logging.DEBUG, 'Importing target - hosts: {}'.format(', '.join(hosts)))

          exclude_hosts = target_root.find('target/exclude_hosts').text
          if exclude_hosts is not None:
            logging.log(logging.DEBUG, 'Importing target - exclude_hosts: {}'.format(exclude_hosts))
            exclude_hosts = exclude_hosts.split(', ')

          alive_tests = target_root.find('target/alive_tests').text
          logging.log(logging.DEBUG, 'Importing target - alive_tests: {}'.format(alive_tests))

          reverse_lookup_only = bool(int(target_root.find('target/reverse_lookup_only').text))
          reverse_lookup_unify = bool(int(target_root.find('target/reverse_lookup_unify').text))

          port_range = target_root.find('target/port_range')
          if port_range is not None:
            port_range = port_range.text
            logging.log(logging.DEBUG, 'Importing target - port_range: {}'.format(port_range))
          port_list_id = target_root.find('target/port_list_id')

          if port_list_id is not None:
            port_list_id = port_list_id.text
            logging.log(logging.DEBUG, 'Importing target - port_list_id: {}'.format(port_list_id))

          response = self.gmp.create_target(name=target_name,
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

          if response.attrib['status'] == '201':
            logging.log(logging.INFO, 'Importing target OK: {}'.format(target_name))

        except Exception as ex:
          logging.log(logging.ERROR, 'Importing target error: {}'.format(ex))

  def import_tasks(self, directory):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)

      for task_config in self.get_xmls(directory):
        try:
          task_root = ET.fromstring(task_config)

          task_name = task_root.find('task/name').text
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

          comment = task_root.find('task/comment').text
          logging.log(logging.DEBUG, 'Importing task - comment: {}'.format(comment))

          scanner_id = task_root.find('task/scanner').attrib['id']
          logging.log(logging.DEBUG, 'Importing task - scanner_id: {}'.format(scanner_id))

          config_id = None
          configs = self.gmp.get_configs().xpath('config')
          for config in configs:
            if config.find('name').text == task_root.find('task/config/name').text:
              config_id = config.attrib['id']
              break

          logging.log(logging.DEBUG, 'Importing task - config_id: {}'.format(config_id))

          alterable = bool(int(task_root.find('task/alterable').text))
          response = self.gmp.create_task(name=task_name,
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

          if response.attrib['status'] == '201':
            logging.log(logging.INFO, 'Importing task OK: {}'.format(task_name))

        except Exception as ex:
          logging.log(logging.ERROR, 'Importing task error: {}'.format(ex))

  def import_reports(self, directory):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)

      for report_config in self.get_xmls(directory):
        try:
          report_root = ET.fromstring(report_config)

          task_name = report_root.find('report/task/name').text
          logging.log(logging.DEBUG, 'Importing report - task_name: {}'.format(task_name))

          task_comment = report_root.find('report/task/comment').text
          logging.log(logging.DEBUG, 'Importing report - task_comment: {}'.format(task_comment))
          if task_name not in self.container_tasks.keys():
            response = self.gmp.import_report(report_config,
              task_name=task_name,
              task_comment=task_comment)

            if response.attrib['status'] == '201':
              logging.log(logging.INFO, 'Importing report OK: {}'.format(task_name))
              tasks = self.gmp.get_tasks().xpath('task')
              for task in tasks:
                if task.find('name').text == task_name and self._is_container_task(task):
                  logging.log(logging.DEBUG, 'Found container task: {}[{}]'.format(task_name, task.attrib['id']))
                  self.container_tasks[task_name] = task.attrib['id']
                  break
          else:
            response = self.gmp.import_report(report_config,
              task_id=self.container_tasks[task_name])
            if response.attrib['status'] == '201':
              logging.log(logging.INFO, 'Importing report OK: {}'.format(task_name))
        except Exception as ex:
          logging.log(logging.ERROR, 'Importing report error: {}'.format(ex))

  def get_task_status(self, task_id):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)
      try:
        response = self.gmp.get_task(task_id=task_id)
        if response.attrib['status'] == '200':
          task_status = response.find('task/status').text
          logging.log(logging.INFO, 'Get task status OK: {} [{}]'.format(task_id, task_status))
          return task_status
        else:
          return None
      except Exception as ex:
        logging.log(logging.ERROR, 'Get task status error: {}'.format(ex))

  def run_task(self, task_id):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)
      try:
        response = self.gmp.start_task(task_id=task_id)
        if response.attrib['status'] == '200':
          logging.log(logging.INFO, 'Running task OK: {}'.format(task_id))
          return True
        else:
          return False
      except Exception as ex:
        logging.log(logging.ERROR, 'Running task  error: {}'.format(ex))
        return False

  def _is_container_task(self, task):
    return task.find('target').attrib['id'] == ''

  def get_targets(self):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)
      targets = self.gmp.get_targets().xpath('target')
      logging.log(logging.DEBUG, 'Targets found in DB: {}'.format(', '.join([target.find('name').text for target in targets])))
      return targets

  def get_tasks(self, exclude_containers=True):
    with self.gmp:
      self.gmp.authenticate(self.user, self.password)
      tasks = self.gmp.get_tasks().xpath('task')
      logging.log(logging.DEBUG, 'Tasks found in DB: {}'.format(', '.join(['{}[id:{}][reports:{}]'.format(task.find('name').text, task.attrib['id'], task.find('report_count').text) for task in tasks])))
      if exclude_containers:
        return [task for task in tasks if not self._is_container_task(task)]
      else:
        return tasks

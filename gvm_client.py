import glob
import io
import os
import datetime
import decimal
import logging
import lxml.etree as ET
from time import sleep
from gvm.connections import UnixSocketConnection, DebugConnection
from gvm.protocols.latest import Gmp
from gvm.transforms import EtreeCheckCommandTransform
from gvm.errors import GvmError

def objectify(element):
  result = {}
  items = []

  for key in element.keys():
    items.append((key, element.attrib[key]))

  for child_element in element:
    if len(child_element) == 0:
      for key in child_element.keys():
        items.append((key, child_element.attrib[key]))
      items.append((child_element.tag, child_element.text))
    else:
      items.append((child_element.tag, objectify(child_element)))

  for key, value in items:
    if key not in result.keys():
      result[key] = value
    else:
      if isinstance(result[key], list):
        result[key].append(value)
      else:
        _result = []
        _result.append(result[key])
        _result.append(value)
        result[key] = _result
  return result

def get_root(tree, root_name):
  if isinstance(tree, ET._ElementTree):
    return tree.find(root_name)
  elif isinstance(tree, ET._Element):
    if tree.tag == root_name:
      return tree
    else:
      return tree.find(root_name)
  elif isinstance(tree, str):
    root = ET.fromstring(tree)
    if root.tag == root_name:
      return root
    else:
      return root.find(root_name)
  else:
    return None

class Filter:
  def __init__(self, filter_root=None):
    if filter_root != None:
      root = get_root(filter_root, 'filter')

      self.name = root.findtext('name')
      self.type = root.findtext('type')
      self.term = root.findtext('term')
      self.comment = root.findtext('comment', None)

  @classmethod
  def new(cls, name:str, term:str, filter_type:str, comment=None):
    self = cls()

    self.name = name
    self.term = term
    self.type = filter_type
    self.comment = comment

class Override:
  text = None
  nvt_oid = None
  port = None
  hosts= None
  comment = None
  threat = None
  new_threat = None
  severity = None
  new_severity = None
  result_id = None
  task_id = None
  seconds_active = None

  def __init__(self, override_root=None):
    if override_root != None:
      root = get_root(override_root, 'override')

      for key, val in objectify(root).items():
        setattr(self, key, val)

      for field, attr in [('nvt','oid'), ('result','id'), ('task','id')]:
        try:
          attr_val = root.find(field).attrib[attr]
          if attr_val != '':
            setattr(self, '{}_{}'.format(field, attr), attr_val)
        except:
          pass
      try:
        self.hosts = root.findtext('hosts').split(', ')
      except:
        self.hosts = None

      try:
        end_time = root.findtext('end_time', None)
        span = datetime.datetime.strptime(end_time, r'%Y-%m-%dT%H:%M:%SZ') - datetime.datetime.now()
        if span.total_seconds() > 0:
          self.seconds_active = int(span.total_seconds())
      except:
        pass

  @classmethod
  def new(cls, text:str, nvt_oid:str, hosts=None, port=None, comment=None, threat=None, new_threat=None,
    severity=None, new_severity=None, result_id=None, task_id=None, seconds_active=None):

    self = cls()

    self.text=text
    self.nvt_oid=nvt_oid
    self.hosts=hosts
    self.port=port
    self.comment=comment
    self.threat=threat
    self.new_threat=new_threat
    self.severity=severity
    self.new_severity=new_severity
    self.result_id=result_id
    self.task_id=task_id
    self.seconds_active=seconds_active

class Report:
  def __init__(self, report_root=None):
    if report_root != None:
      root = get_root(report_root, 'report')
      if root != None:
        try:
          self.id = root.attrib['id']
        except:
          return None
        try:
          self.name = root.findtext('name', None)
        except:
          pass
        try:
          self.task_name = root.findtext('task/name', None)
        except:
          pass
        try:
          self.task_comment = root.findtext('task/comment', None)
        except:
          pass
        self.raw = ET.tostring(root)
      else:
        return None

class Task:
  name = None
  config_id = None
  target_id = None
  scanner_id = None
  hosts_ordering = None
  schedule_id = None
  schedule_periods = None
  comment = None
  alert_ids = None
  observers = None
  alterable = True
  status = None
  progress = None
  last_report = None
  config = None

  def __init__(self, task_root=None):
    if task_root != None:
      root = get_root(task_root, 'task')

      self.raw = ET.tostring(root)

      for key, val in objectify(root).items():
        setattr(self, key, val)

      for field, attr in [('config','id'), ('target','id'), ('scanner','id'), ('schedule','id')]:
        try:
          attr_val = getattr(self, field, '')[attr]
          if attr_val != '':
            setattr(self, '{}_{}'.format(field, attr), attr_val)
        except:
          pass

      if self.schedule_periods != None:
        try:
          self.schedule_periods = int(self.schedule_periods)
        except:
          self.schedule_periods = None

      for field, attr in [('alert','id')]:
        result = []
        for field_el in root.findall(field):
          try:
            attr_val = field_el.attrib[attr]
            if attr_val != None and attr_val != '':
              result.append(attr_val)
          except:
            pass
        if len(result) > 0:
          setattr(self, '{}_{}s'.format(field, attr), result)

      for field in ['observers']:
        field_value = getattr(self, field, None)
        if isinstance(field_value, str):
          if field_value != '':
            setattr(self, field, field_value.split(', '))
          else:
            setattr(self, field, None)

      try:
        current_report = root.find('current_report/report')
        self.current_report = Report(current_report)
      except:
        pass

      try:
        last_report = root.find('last_report/report')
        self.last_report = Report(last_report)
      except:
        pass

  def __str__(self):
    return 'Task stance: name={}, config={}, target={}, scanner={}'.format(
      self.name,
      self.config_id,
      self.target_id,
      self.scanner_id)

  @classmethod
  def new(cls, name:str, config_id:str, scanner_id:str, target_id:str,
    hosts_ordering=None, schedule_id=None, schedule_periods=None, comment=None,
    alert_ids=None, observers=None, alterable=True):

    self = cls()

    self.name = name
    self.config_id = config_id
    self.scanner_id = scanner_id
    self.target_id = target_id
    self.hosts_ordering = hosts_ordering
    self.schedule_id = schedule_id
    self.schedule_periods = schedule_periods
    self.comment = comment
    self.alert_ids = alert_ids
    self.observers = observers
    self.alterable = alterable

class Target:
  # required
  name = None
  # optional
  hosts = []
  exclude_hosts = []
  port_range = None
  port_list_id = None
  ssh_credential_id = None
  smb_credential_id = None
  snmp_credential_id = None
  esxi_credential_id = None
  make_unique = True
  asset_hosts_filter = None
  ssh_credential_port = None
  alive_tests = None
  reverse_lookup_only = None
  reverse_lookup_unify = None
  comment = None

  def __init__(self, target_root=None):
    if target_root != None:
      root = get_root(target_root, 'target')

      for key, val in objectify(root).items():
        setattr(self, key, val)

      for field in ['reverse_lookup_only', 'reverse_lookup_unify']:
        try:
          setattr(self, field, bool(int(getattr(self,field))))
        except:
          pass

      for field in ['hosts', 'exclude_hosts']:
        try:
          field_val = getattr(self, field)
          if field_val != None and field_val != '':
            setattr(self, field, field_val.split(', '))
          else:
            setattr(self, field, [])
        except:
          pass

      for field, attr in [('port_list','id'), ('ssh_credential','id'), ('smb_credential','id'),
        ('snmp_credential','id'), ('esxi_credential','id')]:
        try:
          attr_val = getattr(self, field)[attr]
          if attr_val != '':
            setattr(self, '{}_{}'.format(field, attr), attr_val)
        except:
          pass

  @classmethod
  def new(cls, name, hosts=None, exclude_hosts=None, port_range=None,
    port_list_id=None, ssh_credential_id=None, ssh_credential_port=None,
    smb_credential_id=None, snmp_credential_id=None, esxi_credential_id=None,
    make_unique=True, asset_hosts_filter=None, alive_tests=None, reverse_lookup_only=None,
    reverse_lookup_unify=None, comment=None):

    self = cls()

    self.name = name
    self.hosts = hosts
    self.exclude_hosts = exclude_hosts
    self.port_range = port_range
    self.port_list_id = port_list_id
    self.ssh_credential_id = ssh_credential_id
    self.ssh_credential_port = ssh_credential_port
    self.smb_credential_id = smb_credential_id
    self.snmp_credential_id = snmp_credential_id
    self.esxi_credential_id = esxi_credential_id
    self.make_unique = make_unique
    self.asset_hosts_filter = asset_hosts_filter
    self.alive_tests = alive_tests
    self.reverse_lookup_only = reverse_lookup_only
    self.reverse_lookup_unify = reverse_lookup_unify
    self.comment = comment
    return self

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
    self.connect()

  def authenticate(self):
    try:
      self.gmp.authenticate(self.user, self.password)
    except Exception as ex:
      logging.error('Unable to authenticate: {}'.format(ex))

  def connect(self):
    try:
      self.authenticate()
      return self.gmp._connected
    except Exception as ex:
      self.connection_errors += 1
      logging.error('Can\'t connect to service: {}'.format(ex))
      return False

  def get_xmls(self, directory):
    results = []
    for file_name in os.listdir(directory):
      if file_name.lower().endswith(".xml"):
        file_path = os.path.join(directory, file_name)
        logging.info('Reading file {}'.format(file_path))

        with io.open(file_path, 'r', encoding='utf-8') as file:
          results.append(''.join(file.readlines()))
    return results

  def sync_wait(self):
    while True:
      if self.connect():
        families = self.gmp.get_nvt_families().xpath('families/family')
        if len(families) != 0:
          break
        else:
          logging.info('Waiting for syncing NVTs finished')
          sleep(15)

  def import_configs(self, directory):
    for config in self.get_xmls(directory):
      if self.connect():
        try:
          response = self.gmp.import_config(config)
          if response.attrib['status'] == '201':
            config_root = ET.fromstring(config)
            config_name = config_root.findtext('config/name')
            logging.info('Importing config OK: {}'.format(config_name))

        except Exception as ex:
          logging.error('Importing config error: {}'.format(ex))

  def create_target(self, target:Target):
    if self.connect():
      try:
        response = self.gmp.create_target(
          name=target.name,
          make_unique=target.make_unique,
          hosts=target.hosts,
          exclude_hosts=target.exclude_hosts,
          comment=target.comment,
          alive_tests=target.alive_tests,
          reverse_lookup_only=target.reverse_lookup_only,
          reverse_lookup_unify=target.reverse_lookup_unify,
          port_range=target.port_range,
          port_list_id=target.port_list_id,
          asset_hosts_filter=target.asset_hosts_filter,
          ssh_credential_id=target.ssh_credential_id,
          ssh_credential_port=target.ssh_credential_port,
          smb_credential_id=target.smb_credential_id,
          snmp_credential_id=target.snmp_credential_id,
          esxi_credential_id=target.esxi_credential_id)

        if response.attrib['status'] == '201':
          logging.info('Importing target OK: {}'.format(target.name))

      except Exception as ex:
        logging.error('Importing target error: {}'.format(ex))

  def import_targets(self, directory:str):
    '''
      directory: path to exported targets in XML
    '''
    for target_config in self.get_xmls(directory):
      if self.connect():
        try:
          target = Target(target_config)
          self.create_target(target)
        except Exception as ex:
          logging.error('Importing target error: {}'.format(ex))

  def create_task(self, task:Task):
    if self.connect():
      try:
        response = self.gmp.create_task(
          name=task.name,
          target_id=task.target_id,
          scanner_id=task.scanner_id,
          config_id=task.config_id,
          comment=task.comment,
          alterable=task.alterable,
          alert_ids=task.alert_ids,
          hosts_ordering=task.hosts_ordering,
          schedule_id=task.schedule_id,
          schedule_periods=task.schedule_periods,
          observers=task.observers)

        if response.attrib['status'] == '201':
          logging.info('Importing task OK: {}'.format(task.name))

      except Exception as ex:
        logging.error('Importing task error: {}'.format(ex))

  def create_override(self, override:Override):
    if self.connect():
      try:
        response = self.gmp.create_override(
          text=override.text,
          nvt_oid=override.nvt_oid,
          seconds_active=override.seconds_active,
          comment=override.comment,
          hosts=override.hosts,
          port=override.port,
          result_id=override.result_id,
          severity=override.severity,
          new_severity=override.new_severity,
          task_id=override.task_id,
          threat=override.threat,
          new_threat=override.new_threat)

        if response.attrib['status'] == '201':
          logging.info('Creating override OK: {}'.format(override.text))

      except Exception as ex:
        logging.error('Creating override error: {}'.format(ex))

  def import_overrides(self, directory:str):
    for override_xml in self.get_xmls(directory):
      if self.connect():
        try:
          override = Override(override_xml)
          self.create_override(override)

        except Exception as ex:
          logging.error('Importing override error: {}'.format(ex))

  def import_tasks(self, directory:str):
    for task_config in self.get_xmls(directory):
      if self.connect():
        try:
          task = Task(task_config)

          task.target_id = None
          for target in self.gmp.get_targets().xpath('target'):
            target_name = target.find('name').text
            if target_name == task.name:
              task.target_id = target.attrib['id']
              logging.log(logging.DEBUG, 'Importing task - target_id: {}'.format(task.target_id))

          if task.target_id == None:
            logging.log(logging.DEBUG, 'Importing task - {}. No target_id found'.format(task.name))
            continue

          task.config_id = None
          for config in self.gmp.get_configs().xpath('config'):
            if config.find('name').text == task.config['name']:
              task.config_id = config.attrib['id']
              logging.log(logging.DEBUG, 'Importing task - config_id: {}'.format(task.config_id))
              break

          self.create_task(task)

        except Exception as ex:
          logging.error('Importing task error: {}'.format(ex))

  def import_reports(self, directory):
    for report_xml in self.get_xmls(directory):
      if self.connect():
        try:
          report = Report(report_xml)

          if report.task_name not in self.container_tasks.keys():
            response = self.gmp.import_report(report_xml, task_name=report.task_name, task_comment=report.task_comment)

            if response.attrib['status'] == '201':
              logging.info('Importing report OK: {}'.format(report.task_name))
              tasks = self.gmp.get_tasks().xpath('task')
              for task in tasks:
                if task.find('name').text == report.task_name and self._is_container_task(task):
                  logging.log(logging.DEBUG, 'Found container task: {}[{}]'.format(report.task_name, task.attrib['id']))
                  self.container_tasks[report.task_name] = task.attrib['id']
                  break
          else:
            response = self.gmp.import_report(report_xml, task_id=self.container_tasks[report.task_name])
            if response.attrib['status'] == '201':
              logging.info('Importing report OK: {}'.format(report.task_name))
        except Exception as ex:
          logging.error('Importing report error: {}'.format(ex))

  def get_task(self, task_id):
    if self.connect():
      try:
        response = self.gmp.get_task(task_id=task_id)
        if response.attrib['status'] == '200':
          task = Task(response.find('task'))
          logging.info('Get task OK: {} [{}]'.format(task.name, task_id))
          return task
        else:
          return None
      except Exception as ex:
        logging.error('Get task error: {}'.format(ex))

  def get_task_status(self, task_id):
    if self.connect():
      try:
        response = self.gmp.get_task(task_id=task_id)
        if response.attrib['status'] == '200':
          task_status = response.find('task/status').text
          logging.info('Get task status OK: {} [{}]'.format(task_id, task_status))
          return task_status
        else:
          return None
      except Exception as ex:
        logging.error('Get task status error: {}'.format(ex))

  def run_task(self, task_id:str):
    if self.connect():
      try:
        response = self.gmp.start_task(task_id=task_id)
        if response.attrib['status'] == '202':
          logging.info('Running task OK: {}'.format(task_id))
          return True
        else:
          return False
      except Exception as ex:
        logging.error('Running task  error: {}'.format(ex))
        return False

  def _is_container_task(self, task):
    return task.find('target').attrib['id'] == ''

  def get_targets(self):
    if self.connect():
      try:
        targets = [Target(target) for target in self.gmp.get_targets().xpath('target')]
        logging.info('Targets found in DB: {}'.format(', '.join([target.name for target in targets])))
        return targets
      except Exception as ex:
        logging.error('Get targets error: {}'.format(ex))
        return False

  def get_tasks(self, exclude_containers=True):
    if self.connect():
      try:
        tasks = self.gmp.get_tasks().xpath('task')
        logging.info('Tasks found in DB: {}'.format(', '.join([task.find('name').text for task in tasks])))
        if exclude_containers:
          return [Task(task) for task in tasks if not self._is_container_task(task)]
        else:
          return [Task(task) for task in tasks]
      except Exception as ex:
        logging.error('Get tasks error: {}'.format(ex))
        return False

  def save_report(self, report_id:str, directory:str):
    if self.connect():
      try:
        raw_report = self.gmp.get_report(report_id).find('report')
        report = Report(raw_report)
        logging.info('Got report: {}'.format(report.name))

        file_name = '{}-{}.xml'.format(report.task_name, report.name)
        file_path = os.path.join(directory, file_name)
        logging.info('Saving report to file {}'.format(file_path))

        if os.path.isfile(file_path):
          raise Exception('File exists: {}'.format(file_path))

        with io.open(file_path, 'wb') as file:
          file.write(ET.tostring(raw_report, encoding='utf-8', method='xml', pretty_print=True))

        return True
      except Exception as ex:
        logging.error('Get targets error: {}'.format(ex))
        return False

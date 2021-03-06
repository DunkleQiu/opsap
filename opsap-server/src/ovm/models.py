# -*- coding:utf8 -*-

import json,ssl
import warnings
from datetime import datetime, timedelta
from os import system

from django.db import models
from pyVim.connect import SmartConnect
from pyVmomi import vim

from opsap.api import logger
from ouser.models import User, UserGroup


# Create your models here.
class SheetField(models.Model):
    sheet_name = models.CharField(max_length=255)
    field_name = models.CharField(max_length=255)
    option = models.CharField(max_length=255, null=True)
    option_display = models.CharField(max_length=255, null=True)

    def get_sheet_brand(self):
        sheet_full = str(self.sheet_name)
        for i in range(1, len(sheet_full) - 1)[::-1]:
            if sheet_full[i] == '_':
                tail = sheet_full[i + 1:]
                head = sheet_full[:i]
                qset = type(self).objects.filter(field_name=head, option=tail)
                if qset.exists():
                    brand_display = str(qset[0].option_display)
                    return tail, brand_display
        else:
            return '', ''

    sheet_brand = property(get_sheet_brand)

    @classmethod
    def get_options(cls, field, sheet='global'):
        if not sheet:
            return cls.objects.filter(field_name=field)
        return cls.objects.filter(sheet_name=sheet, field_name=field)

    @classmethod
    def add_field(cls, field, fld_display, sheet='global'):
        pre_check_field = cls.objects.filter(sheet_name='field', field_name=sheet, option=field)
        if pre_check_field.exists():
            raise Exception("Field already exists!")
        else:
            cls.objects.create(sheet_name='field', field_name=sheet, option=field, option_display=fld_display)
            return {'sheet': sheet, 'field': field}

    @classmethod
    def add_option(cls, option, opt_display, field, sheet='global'):
        pre_check_field = cls.objects.filter(sheet_name='field', field_name=sheet, option=field)
        if not pre_check_field.exists():
            raise Exception("Field doesn't exist" + str(sheet) + " : " + str(field))
        pre_check_option = cls.get_options(field, sheet).filter(option=option)
        if pre_check_option.exists():
            raise Exception("Option already exists!")
        else:
            new_opt = cls.objects.create(sheet_name=sheet, field_name=field, option=option, option_display=opt_display)
            return new_opt

    def __str__(self):
        return self.option_display


_sis = {}


def GetSiByVCid(vcid):
    if _sis.has_key(vcid):
        return _sis[vcid]
    else:
        return None


def SetSiByVCid(vcid, si):
    global _sis
    _sis[vcid] = si


def env_type2json(env_type):
    qs_envtype = SheetField.get_options('env_type')
    env_type_dict = {}
    if isinstance(env_type, list) and qs_envtype.exists():
        for opt in qs_envtype:
            env_type_dict[opt.option] = (opt.option in env_type)
    return json.dumps(env_type_dict)


def os_type2json(os_type):
    qs_ostype = SheetField.get_options('os_type')
    env_type_dict = {}
    if isinstance(os_type, list) and qs_ostype.exists():
        for opt in qs_ostype:
            env_type_dict[opt.option] = (opt.option in os_type)
    return json.dumps(env_type_dict)


context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
context.verify_mode = ssl.CERT_NONE

class VCenter(models.Model):
    uuid = models.CharField(max_length=50, unique=True)
    version = models.CharField(max_length=30)
    ip = models.GenericIPAddressField(protocol='ipv4')
    port = models.PositiveIntegerField()
    env_type = models.CharField(max_length=255)
    user = models.CharField(max_length=30)
    password = models.CharField(max_length=30)
    last_connect = models.DateTimeField(null=True)
    last_sync = models.DateTimeField(null=True)

    def get_env_type(self):
        envs_map = json.loads(self.env_type)
        return [k for k, v in envs_map.items() if v]

    env_type_list = property(get_env_type)

    @classmethod
    def discover(cls, ip='localhost', port=443, env_type=None, user='root', pwd='vmware'):
        si = SmartConnect(host=ip, user=user, pwd=pwd, port=port, sslContext=context)
        if not si:
            return None
        # Disconnect(si)
        content = si.RetrieveContent()
        new_uuid = content.about.instanceUuid
        new_version = content.about.apiVersion
        vc = cls(ip=ip, port=port, env_type=env_type2json(env_type), user=user, password=pwd, uuid=new_uuid,
                 version=new_version, last_connect=datetime.now())
        vc.save()
        SetSiByVCid(vc.id, si)
        return vc

    def modify(self, ip=None, port=None, env_type=None, user=None, pwd=None):
        logger.debug("begin modeify")
        if env_type:
            self.env_type = env_type2json(env_type)
        re_check = ip or port or user or pwd
        if not re_check:
            self.save(update_fields=['env_type'])
            return True
        ip = ip or str(self.ip)
        port = port or self.port
        user = user or str(self.user)
        pwd = pwd or str(self.password)
        logger.debug("begin connect")
        si = SmartConnect(host=ip, user=user, pwd=pwd, port=port, sslContext=context)
        logger.debug(si)
        if not si:
            logger.warning('Cannot connect to the new instance after change, vc is left unchanged!')
            return False
        content = si.RetrieveContent()
        new_uuid = content.about.instanceUuid
        if new_uuid != self.uuid:
            logger.warning('New instance\'s uuid differs from the old one, vc is left unchanged!')
            return False
        self.ip = ip
        self.port = port
        self.user = user
        self.password = pwd
        self.save()
        return True

    def connect(self):
        si = GetSiByVCid(self.id)
        try:
            content = si.RetrieveContent()
            curSession = content.sessionManager.currentSession
            if curSession and isinstance(curSession, vim.UserSession):
                logger.debug("Get session: VCenter " + str(self.ip) + ", session ID:" + curSession.key)
                return content
            else:
                curSession = content.sessionManager.Login(self.user, self.password)
                logger.debug("ReLogin session: VCenter " + str(self.ip) + ", session ID:" + curSession.key)
        except:
            try:
                warnings.filterwarnings("ignore")
                si = SmartConnect(host=self.ip, user=self.user, pwd=self.password, port=self.port, sslContext=context)
                logger.debug("Get session failed: VCenter " + str(self.ip) + ", reconnectted")
                SetSiByVCid(self.id, si)
            except:
                logger.debug("Cannot get a session from VCenter " + str(self.ip))
                return None
        finally:
            content = si.RetrieveContent()
            uuid = content.about.instanceUuid
            if uuid != self.uuid:
                logger.warning("UUID of VCenter changed, it might be another VCenter!!")
                return None
            self.last_connect = datetime.now()
            self.save(update_fields=['last_connect'])
        return content


class VMObject(models.Model):
    vcenter = models.ForeignKey('VCenter')
    moid = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    hash_value = models.CharField(max_length=255, editable=False, default='')

    class Meta:
        abstract = True
        unique_together = ('vcenter', 'moid')

    def _sum_hash(self):
        return (
            hash(self.vcenter_id) + hash(self.moid) + hash(self.name)
        )

    def __str__(self):
        return self.moid + " : " + self.name

    def save(self, *args, **kwargs):
        if not self.hash_value:
            hash_old = 0
        else:
            hash_old = long(self.hash_value)
        hash_new = self._sum_hash()
        if (hash_old == hash_new):
            return
        for k, v in kwargs.items():
            if k == 'update_fields' and ('hash_value' not in v):
                v.append('hash_value')
        self.hash_value = str(hash_new)
        super(VMObject, self).save(*args, **kwargs)

    def getMoid(self):
        return str(self.moid)


class ComputeResource(VMObject):
    is_cluster = models.BooleanField()
    ha = models.NullBooleanField()
    drs = models.NullBooleanField()

    def _sum_hash(self):
        return (
            super(ComputeResource, self)._sum_hash() +
            hash(self.is_cluster) + hash(self.ha) + hash(self.drs)
        )

    def update_by_vim(self, vimobj):
        if not isinstance(vimobj, vim.ComputeResource):
            return
        self.name = vimobj.name
        self.is_cluster = isinstance(vimobj, vim.ClusterComputeResource)
        if self.is_cluster:
            config = vimobj.configuration
            self.ha = config.dasConfig.enabled
            self.drs = config.drsConfig.enabled
        self.save()

    @classmethod
    def create_or_update_by_vim(cls, vimobj, vc):
        new_obj = None
        created = False
        if not isinstance(vimobj, vim.ComputeResource):
            return new_obj, created
        moid = vimobj._GetMoId()
        qset = cls.objects.filter(moid=moid, vcenter=vc)
        if qset.exists():
            new_obj = qset[0]
        else:
            created = True
            new_obj = cls(moid=moid, vcenter=vc)
        new_obj.update_by_vim(vimobj)
        return new_obj, created

    def free_cpu(self):
        """
        :return: cpu_free_percent
        """
        total_cpu = 0
        usage_cpu = 0
        qset = self.hostsystem_set.all()
        if not qset.exists():
            return 0
        for host in qset:
            total_cpu += host.cpu_total()
            usage_cpu += host.usage_cpu_mhz
        return 100 - (float(usage_cpu) * 100 / total_cpu)

    def free_mem(self):
        """
        :return: memory_free_percent
        """
        total_mem = 0
        usage_mem = 0
        qset = self.hostsystem_set.all()
        if not qset.exists():
            return 0
        for host in qset:
            total_mem += host.total_mem_mb
            usage_mem += host.usage_mem_mb
        return 100 - (float(usage_mem) * 100 / total_mem)


class ResourcePool(VMObject):
    share_cpu_level = models.CharField(max_length=30)
    share_mem_level = models.CharField(max_length=30)
    limit_cpu_mhz = models.BigIntegerField()
    limit_mem_mb = models.BigIntegerField()
    env_type = models.CharField(max_length=255)
    # related fields
    owner = models.ForeignKey('ComputeResource', null=True)
    parent = models.ForeignKey('ResourcePool', null=True)

    def _sum_hash(self):
        return (
            super(ResourcePool, self)._sum_hash() +
            hash(self.share_cpu_level) + hash(self.share_mem_level) +
            hash(self.limit_cpu_mhz) + hash(self.limit_mem_mb) +
            hash(self.env_type) +
            hash(self.owner_id) + hash(self.parent_id)
        )

    def update_env_type(self, env_type):
        self.env_type = env_type2json(env_type)
        self.save(update_fields=['env_type'])

    def update_by_vim(self, vimobj, vc, related=False):
        if not isinstance(vimobj, vim.ResourcePool):
            return
        self.name = vimobj.name
        config = vimobj.config
        self.share_cpu_level = config.cpuAllocation.shares.level
        self.share_mem_level = config.memoryAllocation.shares.level
        self.limit_cpu_mhz = config.cpuAllocation.limit
        self.limit_mem_mb = config.memoryAllocation.limit
        if related:
            # update owner
            clus = vimobj.owner
            if isinstance(clus, vim.ComputeResource):
                try:
                    self.owner = ComputeResource.objects.get(vcenter=vc, moid=clus._GetMoId())
                except:
                    pass
            # update parent
            resp = vimobj.parent
            if isinstance(resp, vim.ResourcePool):
                parent = None
                try:
                    parent = ResourcePool.objects.get(vcenter=vc, moid=resp._GetMoId())
                except:
                    parent = ResourcePool.create_by_vim(resp, vc, related)
                finally:
                    self.parent = parent
        self.save()

    @classmethod
    def match(cls, env_type=None):
        result_set = cls.objects.none()
        # match env_type
        if not env_type:
            env_type = []
        elif isinstance(env_type, list):
            pass
        else:
            env_type = [str(env_type)]
        for qry in env_type:
            result_set = result_set | cls.objects.filter(env_type__contains="\"" + qry + "\": true")
        return result_set.distinct()

    @classmethod
    def create_or_update_by_vim(cls, vimobj, vc, related=False):
        new_obj = None
        created = False
        if not isinstance(vimobj, vim.ResourcePool):
            return new_obj, created
        moid = vimobj._GetMoId()
        qset = cls.objects.filter(moid=moid, vcenter=vc)
        if qset.exists():
            new_obj = qset[0]
        else:
            created = True
            new_obj = cls(moid=moid, vcenter=vc, env_type=vc.env_type)
        new_obj.update_by_vim(vimobj, vc, related)
        return new_obj, created


def bin2str(i_bin):
    if len(i_bin) < 32:
        i_bin = i_bin.rjust(32, str(0))
    i_raw = [i_bin[i * 8:i * 8 + 8] for i in range(4)]
    i_str = [str(int(subn, 2)) for subn in i_raw]
    return '.'.join(i_str)


def str2bin(i_str):
    i_raw = [bin(int(subn)) for subn in i_str.split('.')]
    if len(i_raw) != 4:
        return '0' * 32
    i_bin = [subn[2:].rjust(8, str(0)) for subn in i_raw]
    return ''.join(i_bin)


class Network(VMObject):
    net = models.GenericIPAddressField(protocol='ipv4')
    netmask = models.PositiveSmallIntegerField(default=24)
    env_type = models.CharField(max_length=255, null=True)
    os_type = models.CharField(max_length=255, null=True)

    def _sum_hash(self):
        return (
            super(Network, self)._sum_hash() +
            hash(self.net) + hash(self.netmask) +
            hash(self.env_type) + hash(self.os_type)
        )

    def getmask_str(self):
        mask_bin = (self.netmask * '1').ljust(32, str(0))
        return bin2str(mask_bin)

    def update_manual(self, nw=None, mask=None, env_type=None, os_type=None):
        """
        Update network infomations manually
        :param nw: network address,e.g.192.168.1.0
        :type nw:str
        :param mask: netmask as integer,e.g.24
        :type mask:int
        :return:
        """
        if nw:
            self.net = nw
        if isinstance(mask, int):
            self.netmask = mask
        if isinstance(env_type, list):
            self.env_type = env_type2json(env_type)
        if isinstance(os_type, list):
            self.os_type = os_type2json(os_type)
        self.save()

    def update_by_vim(self, vimobj):
        if not isinstance(vimobj, vim.Network):
            return
        name = vimobj.name.strip()
        self.name = name
        if not self.net:
            try:
                self.net = name.split('-')[-1]
            except:
                self.net = "1.1.1.0"
        if not self.netmask:
            self.netmask = 24
        self.save()

    @classmethod
    def match(cls, env_type=None, os_type=None):
        env_match_set = cls.objects.none()
        # match env_type
        if not env_type:
            env_type = []
        elif isinstance(env_type, list):
            pass
        else:
            env_type = [str(env_type)]
        for qry in env_type:
            env_match_set = env_match_set | cls.objects.filter(env_type__contains="\"" + qry + "\": true")
        # match os_type
        result_set = cls.objects.none()
        if not os_type:
            os_type = []
        elif isinstance(os_type, list):
            pass
        else:
            os_type = [str(os_type)]
        for qry in os_type:
            result_set = result_set | env_match_set.filter(os_type__contains="\"" + qry + "\": true")
        return result_set.distinct()

    @classmethod
    def create_or_update_by_vim(cls, vimobj, vc):
        new_obj = None
        created = False
        if not isinstance(vimobj, vim.Network):
            return new_obj, created
        moid = vimobj._GetMoId()
        qset = cls.objects.filter(moid=moid, vcenter=vc)
        if qset.exists():
            new_obj = qset[0]
        else:
            created = True
            new_obj = cls(moid=moid, vcenter=vc)
        new_obj.update_by_vim(vimobj)
        return new_obj, created


class IPUsage(models.Model):
    ipaddress = models.GenericIPAddressField(protocol='ipv4')
    network = models.ForeignKey('Network')
    vm = models.ForeignKey('VirtualMachine', null=True, on_delete=models.SET_NULL)
    used_manage = models.BooleanField(default=False)
    used_manage_app = models.CharField(max_length=255, null=True)
    used_occupy = models.BooleanField(default=False)
    used_unknown = models.BooleanField(default=False)
    lock_until = models.DateTimeField(null=True)

    class Meta:
        unique_together = ('network', 'ipaddress')

    @classmethod
    def create(cls, network, gw_addr=None):
        if not isinstance(network, Network):
            return None, False
        qset = cls.objects.filter(network=network)
        if qset.exists():
            return qset, False
        mask = network.netmask
        net_bin = str2bin(network.net)
        if '1' in net_bin[mask:]:
            return None, False
        iplist_int = range(int(net_bin, 2) + 1,
                           int(net_bin[:mask] + '1' * (32 - mask), 2))
        iplist_bin = [bin(subn)[2:].rjust(32, str(0)) for subn in iplist_int]
        if isinstance(gw_addr, str):
            if str2bin(gw_addr) in iplist_bin:
                iplist_bin.remove(str2bin(gw_addr))
                gw = cls.objects.create(ipaddress=gw_addr, network=network, used_manage=True,
                                        used_manage_app='GW')
            else:
                raise Exception("network doesn't cover the gw address!")
        else:
            gw = cls.objects.create(ipaddress=bin2str(iplist_bin.pop()), network=network, used_manage=True,
                                    used_manage_app='GW')
        for ip_bin in iplist_bin:
            cls.objects.create(ipaddress=bin2str(ip_bin), network=network)
        return gw, len(iplist_int)

    def get_occupy(self):
        self.used_manage = False
        self.used_unknown = False
        self.used_occupy = True
        self.save(update_fields=['used_manage', 'used_unknown', 'used_occupy'])

    def release_occupy(self):
        self.used_occupy = False
        self.save(update_fields=['used_occupy'])

    def manage(self, app):
        self.used_unknown = False
        self.used_occupy = False
        self.used_manage = True
        self.used_manage_app = app
        self.save(update_fields=['used_manage', 'used_manage_app', 'used_unknown', 'used_occupy'])

    def ping(self, count=2):
        status = system("ping -c " + str(count) + " " + self.ipaddress)
        return status == 0

    @classmethod
    def select_ip(cls, network, lock_sec=600, test=False, occupy=False):
        test_list = cls.objects.filter(network=network, used_manage=False, used_occupy=False, used_unknown=False,
                                       vm__isnull=True).order_by('id')
        for ipusage in test_list:
            if ipusage.lock_until and ipusage.lock_until > datetime.now():
                continue
            if test and ipusage.ping():
                ipusage.used_unknown = True
                ipusage.save(update_fields=['used_unknown'])
                continue
            if occupy:
                ipusage.occupy()
            else:
                ipusage.lock_until = datetime.now() + timedelta(seconds=lock_sec)
                ipusage.save(update_fields=['lock_until'])
            return ipusage


class Datastore(VMObject):
    MT_NORM = 'normal'
    MT_INMT = 'inMaintenance'
    MT_TOMT = 'enteringMaintenance'
    MT_MODE_CHOICE = (
        (MT_NORM, 'normal'),
        (MT_INMT, 'in maintenance'),
        (MT_TOMT, 'entering maintenance')
    )
    multi_hosts_access = models.BooleanField()
    url = models.CharField(max_length=255, null=True)
    total_space_mb = models.BigIntegerField(null=True)
    # dynamic field
    accessible = models.BooleanField()
    maintenance_mode = models.CharField(max_length=10, choices=MT_MODE_CHOICE)
    free_space_mb = models.BigIntegerField(null=True)

    def _sum_hash(self):
        return (
            super(Datastore, self)._sum_hash() +
            hash(self.multi_hosts_access) + hash(self.url) + hash(self.total_space_mb) +
            hash(self.accessible) + hash(self.maintenance_mode) + hash(self.free_space_mb)
        )

    def update_by_vim(self, vimobj, dynamic=False):
        if not isinstance(vimobj, vim.Datastore):
            return
        ds_summary = vimobj.summary
        self.accessible = ds_summary.accessible
        self.maintenance_mode = ds_summary.maintenanceMode
        if ds_summary.accessible:
            self.free_space_mb = ds_summary.freeSpace / 1024 ** 2
        if not dynamic:
            self.name = ds_summary.name
            self.multi_hosts_access = ds_summary.multipleHostAccess
            if ds_summary.accessible:
                self.url = ds_summary.url
                self.total_space_mb = ds_summary.capacity / 1024 ** 2
        self.save()

    @classmethod
    def create_or_update_by_vim(cls, vimobj, vc):
        new_obj = None
        created = False
        if not isinstance(vimobj, vim.Datastore):
            return new_obj, created
        moid = vimobj._GetMoId()
        qset = cls.objects.filter(moid=moid, vcenter=vc)
        if qset.exists():
            new_obj = qset[0]
        else:
            created = True
            new_obj = cls(moid=moid, vcenter=vc)
        new_obj.update_by_vim(vimobj)
        return new_obj, created


class HostSystem(VMObject):
    vmotion_enable = models.BooleanField()
    total_cpu_cores = models.PositiveSmallIntegerField()
    total_cpu_mhz = models.PositiveIntegerField()
    total_mem_mb = models.PositiveIntegerField()
    # dynamic fields
    connection_state = models.CharField(max_length=30)
    in_maintenance_mode = models.BooleanField()
    usage_cpu_mhz = models.PositiveIntegerField()
    usage_mem_mb = models.PositiveIntegerField()
    # related fields
    cluster = models.ForeignKey('ComputeResource', null=True)
    networks = models.ManyToManyField('Network')
    datastores = models.ManyToManyField('Datastore')

    def cpu_total(self):
        return self.total_cpu_mhz * self.total_cpu_cores

    def free_mem_mb(self):
        return self.total_mem_mb - self.usage_mem_mb

    def free_mem_percent(self):
        return self.free_mem_mb() / self.total_mem_mb

    def _sum_hash(self):
        return (
            super(HostSystem, self)._sum_hash() +
            hash(self.vmotion_enable) +
            hash(self.total_cpu_cores) + hash(self.total_cpu_mhz) + hash(self.total_mem_mb) +
            hash(self.connection_state) + hash(self.in_maintenance_mode) +
            hash(self.usage_cpu_mhz) + hash(self.usage_mem_mb) +
            hash(self.cluster_id)
        )

    def update_by_vim(self, vimobj, vc, related=False, dynamic=False):
        host_summary = vimobj.summary
        host_runtime = vimobj.runtime
        self.usage_cpu_mhz = host_summary.quickStats.overallCpuUsage
        self.usage_mem_mb = host_summary.quickStats.overallMemoryUsage
        self.connection_state = host_runtime.connectionState
        self.in_maintenance_mode = host_runtime.inMaintenanceMode
        if not dynamic:
            self.name = vimobj.name
            self.vmotion_enable = host_summary.config.vmotionEnabled
            self.total_cpu_cores = host_summary.hardware.numCpuCores
            self.total_cpu_mhz = host_summary.hardware.cpuMhz
            self.total_mem_mb = host_summary.hardware.memorySize / 1024 ** 2
            if related:
                # update cluster
                clus = vimobj.parent
                if isinstance(clus, vim.ComputeResource):
                    try:
                        self.cluster = ComputeResource.objects.get(vcenter=vc, moid=clus._GetMoId())
                    except:
                        pass
        self.save()
        if dynamic or (not related):
            return True
        # update networks
        try:
            for vimnet in vimobj.network:
                net = Network.objects.get(vcenter=vc, moid=vimnet._GetMoId())
                self.networks.add(net)
        except:
            pass
        # update datastores
        try:
            for vimds in vimobj.datastore:
                ds = Datastore.objects.get(vcenter=vc, moid=vimds._GetMoId())
                self.datastores.add(ds)
        except:
            pass

    @classmethod
    def create_or_update_by_vim(cls, vimobj, vc, related=False):
        new_obj = None
        created = False
        if not isinstance(vimobj, vim.HostSystem):
            return new_obj, created
        moid = vimobj._GetMoId()
        qset = cls.objects.filter(moid=moid, vcenter=vc)
        if qset.exists():
            new_obj = qset[0]
        else:
            created = True
            new_obj = cls(moid=moid, vcenter=vc)
        new_obj.update_by_vim(vimobj, vc, related)
        return new_obj, created


class VirtualMachine(VMObject):
    istemplate = models.BooleanField()
    annotation = models.TextField()
    cpu_num = models.PositiveSmallIntegerField()
    cpu_cores = models.PositiveSmallIntegerField()
    memory_mb = models.PositiveIntegerField()
    storage_mb = models.PositiveIntegerField()
    guestos_shortname = models.CharField(max_length=30)
    guestos_fullname = models.CharField(max_length=255)
    hostsystem = models.ForeignKey('HostSystem', null=True)
    resourcepool = models.ForeignKey('ResourcePool', null=True)
    networks = models.ManyToManyField('Network')
    datastores = models.ManyToManyField('Datastore')

    def _sum_hash(self):
        return (
            super(VirtualMachine, self)._sum_hash() +
            hash(self.istemplate) + hash(self.annotation) +
            hash(self.cpu_num) + hash(self.cpu_cores) +
            hash(self.memory_mb) + hash(self.storage_mb) +
            hash(self.guestos_shortname) + hash(self.guestos_fullname) +
            hash(self.hostsystem_id) + hash(self.resourcepool_id)
        )

    def update_ipusage(self, vimobj):
        vm_guest = vimobj.guest
        old_ip = list(self.ipusage_set.all())
        try:
            for vimip in vm_guest.net:
                ipaddress_li = vimip.ipAddress
                for address in ipaddress_li:
                    if str(address).count('.') != 3:
                        ipaddress_li.remove(address)
                for ipaddress in ipaddress_li:
                    qset = IPUsage.objects.filter(network__name=vimip.network.strip(), ipaddress=ipaddress)
                    if not qset.exists():
                        print("IPAddress: " + str(ipaddress) + "-- not initialed")
                        continue
                    ip = qset[0]
                    if ip in old_ip:
                        old_ip.remove(ip)
                    else:
                        ip.used_occupy = False
                        ip.vm = self
                        ip.save(update_fields=['used_occupy', 'vm'])
            for oip in old_ip:
                oip.vm = None
                oip.save(update_fields=['vm'])
        except Exception, e:
            raise e

    def update_by_vim(self, vimobj, related=False):
        vc = self.vcenter
        self.name = vimobj.name
        vm_config = vimobj.config
        vm_sum = vimobj.summary
        self.istemplate = vm_config.template
        self.annotation = vm_config.annotation
        vm_hardware = vm_config.hardware
        self.cpu_num = vm_hardware.numCPU
        self.cpu_cores = vm_hardware.numCoresPerSocket
        self.memory_mb = vm_hardware.memoryMB
        self.storage_mb = vm_sum.storage.committed / 1024 ** 2
        # vm_guest = vimobj.guest
        vm_sumcfg = vm_sum.config
        self.guestos_shortname = vm_sumcfg.guestId
        self.guestos_fullname = vm_sumcfg.guestFullName
        if related:
            # update hostsystem
            host = vimobj.runtime.host
            if host:
                try:
                    self.hostsystem = HostSystem.objects.get(vcenter=vc, moid=host._GetMoId())
                except Exception, e:
                    raise e
            # update resourcepool
            resp = vimobj.resourcePool
            if resp:
                try:
                    self.resourcepool = ResourcePool.objects.get(vcenter=vc, moid=resp._GetMoId())
                except Exception, e:
                    raise e
        self.save()
        if not related:
            return True
        # update networks
        try:
            old_net = list(self.networks.all())
            for vimnet in vimobj.network:
                net = Network.objects.get(vcenter=vc, moid=vimnet._GetMoId())
                if net in old_net:
                    old_net.remove(net)
                else:
                    self.networks.add(net)
            if old_net:
                self.networks.remove(*old_net)
        except:
            pass
        # update datastores
        try:
            old_ds = list(self.datastores.all())
            for vimds in vimobj.datastore:
                ds = Datastore.objects.get(vcenter=vc, moid=vimds._GetMoId())
                if ds in old_ds:
                    old_ds.remove(ds)
                else:
                    self.datastores.add(ds)
            if old_ds:
                self.datastores.remove(*old_ds)
        except:
            pass
        # update ipusage_set
        self.update_ipusage(vimobj)

    @classmethod
    def create_or_update_by_vim(cls, vimobj, vc, related=False):
        new_obj = None
        created = False
        if not isinstance(vimobj, vim.VirtualMachine):
            return new_obj, created
        moid = vimobj._GetMoId()
        qset = cls.objects.filter(moid=moid, vcenter=vc)
        if qset.exists():
            new_obj = qset[0]
        else:
            created = True
            new_obj = cls(moid=moid, vcenter=vc)
        new_obj.update_by_vim(vimobj, related=related)
        return new_obj, created


class Template(models.Model):
    virtualmachine = models.OneToOneField(VirtualMachine)
    env_type = models.CharField(max_length=255)

    def get_env_type(self):
        envs_map = json.loads(self.env_type)
        return [k for k, v in envs_map.items() if v]

    env_type_list = property(get_env_type)

    @classmethod
    def add(cls, vm, env_type):
        if not isinstance(env_type, list):
            raise Exception("arguments type error: env_type must be list")
        return cls.objects.create(virtualmachine=vm, env_type=env_type2json(env_type))

    @classmethod
    def match(cls, env_type=None, os_type=None, os_version=None):
        env_match_set = cls.objects.none()
        # match env_type
        if not env_type:
            env_type = []
        elif isinstance(env_type, list):
            pass
        else:
            env_type = [str(env_type)]
        for qry in env_type:
            env_match_set = env_match_set | cls.objects.filter(env_type__contains="\"" + qry + "\": true")
        # match os_type and os_version
        ovset = SheetField.get_options(field="os_version", sheet='')
        if os_type:
            ovset = ovset.filter(sheet_name="os_type_" + str(os_type))
        if os_version:
            ovset = ovset.filter(option=str(os_version))
        result_set = cls.objects.none()
        for qry in ovset.values('option'):
            result_set = result_set | env_match_set.filter(virtualmachine__guestos_shortname=qry['option'])
        return result_set.distinct()


class CustomSpec(models.Model):
    vcenter = models.ForeignKey('VCenter')
    os_type = models.CharField(max_length=50)
    name = models.CharField(max_length=80)
    os_version = models.CharField(max_length=50, null=True)

    def getSpec(self, ipaddress=None):
        content = self.vcenter.connect()
        custspec = content.customizationSpecManager.Get(str(self.name)).spec
        if ipaddress:
            ipsetting = custspec.nicSettingMap[0].adapter
            fixip = vim.vm.customization.FixedIp()
            fixip.ipAddress = ipaddress
            ipsetting.ip = fixip
        return custspec


class Application(models.Model):
    """用户申请表"""
    APPLY_STATUS_CHOICE = (
        ('SM', 'submit'),
        ('HD', 'hold')
    )

    env_type = models.CharField(max_length=20)
    fun_type = models.CharField(max_length=20)
    # master_type = models.CharField(max_length=80)
    cpu = models.SmallIntegerField()
    memory_gb = models.IntegerField()
    os_type = models.CharField(max_length=20)
    datadisk_gb = models.IntegerField(null=True)
    request_vm_num = models.IntegerField()
    apply_status = models.CharField(max_length=20, choices=APPLY_STATUS_CHOICE)
    app_name = models.CharField(max_length=20)
    apply_reason = models.TextField()
    apply_date = models.DateTimeField()
    user = models.ForeignKey(User)

    # operation_system = models.CharField(max_length=120,unique=True)
    # apply_reason = models.CharField(, max_length=50)

    def __unicode__(self):
        return self.env_type


class Approvel(models.Model):
    """审核表"""
    APPROVE_STATUS = (
        ('AP', 'approved'),
        ('AI', 'approving'),
        ('RB', 'return back')
    )
    application = models.OneToOneField('Application')
    appro_env_type = models.CharField(max_length=20)
    appro_fun_type = models.CharField(max_length=20)
    appro_cpu = models.SmallIntegerField()
    appro_memory_gb = models.IntegerField()
    appro_os_type = models.CharField(max_length=20)
    appro_datadisk_gb = models.IntegerField()
    appro_vm_num = models.IntegerField()
    appro_status = models.CharField(max_length=20, choices=APPROVE_STATUS)
    appro_date = models.DateTimeField()

    def __unicode__(self):
        return self.appro_env_type


class VMOrder(models.Model):
    """生成表"""
    GEN_STATUS = (
        ('FAILED', 'failed'),
        ('SUCCESS', 'success'),
        ('RUNNING', 'running')
    )
    approvel = models.ForeignKey('Approvel', null=True, on_delete=models.SET_NULL)
    src_template = models.ForeignKey('Template', null=True, on_delete=models.SET_NULL)
    loc_hostname = models.CharField(max_length=20)
    loc_ip = models.ForeignKey('IPUsage', null=True, on_delete=models.SET_NULL)
    loc_cluster = models.ForeignKey('ComputeResource', null=True, on_delete=models.SET_NULL)
    loc_resp = models.ForeignKey('ResourcePool', null=True, on_delete=models.SET_NULL)
    loc_storage = models.ForeignKey('Datastore', null=True, on_delete=models.SET_NULL)
    gen_status = models.CharField(max_length=20, choices=GEN_STATUS, null=True)
    gen_log = models.TextField(null=True)
    gen_time = models.DateTimeField(null=True)
    gen_progress = models.PositiveIntegerField(default=0)

    def add_log(self, log):
        genlog = str(log) + '\n'
        if self.gen_log:
            self.gen_log = str(self.gen_log) + genlog
        else:
            self.gen_log = genlog
        self.save(update_fields=['gen_log'])
        return str(self.gen_log)

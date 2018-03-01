#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO: need proper logging and exception handling
# TODO: rewrite everything to support async, might require python 3+
# NOTE: prlsdkapi does not support python 3...
# NOTE: prlsdkapi does have async support, should probably find all the .wait()
#       statements and make a configurable for asynchronous/synchronous

import prlsdkapi
from munge import pickConfig, storageUnits

# TODO: this should probably be a config file
consts = prlsdkapi.prlsdk.consts
storage_unit_size = 5120
vzconfig_string = "vswap.{0}MB"
default_nameservers = ['8.8.8.8', '8.8.4.4']
default_mem_prcnt = 80

class Halt(Exception):
    pass


def search_consts(consts, prefix):
    constants = [item for item in dir(consts) if item.startswith("{0}_".format(prefix))]
    return constants


def loop_job(job):
    while True:
        if job.get_status() == consts.PJS_FINISHED:
            if job.get_ret_code() != 0:
                event = job.get_error()
                print event.get_err_string(True, False)
                raise Halt
            break
    return job.get_result()


def safe_commit(ct):
    try:
        result = ct.commit().wait()
        ct = result.get_param()
        return ct
    except prlsdkapi.PrlSDKError, e:
        print "ct.commit Error: {0}".format(e)
        raise Halt


class API(object):
    def __enter__(self):
        prlsdkapi.init_server_sdk()
    def __exit__(self, exception_type, exception_value, traceback):
        prlsdkapi.deinit_sdk()


class Login(object):
    """
    Class is to be used in a with loop, to properly logoff and deinit prlsdkapi
    returns prlsdkapi.Server and prlsdkapi.Result from login
    """
    def __init__(self, host="localhost", user="", password="", security_level=consts.PSL_HIGH_SECURITY):
        self.host = host
        self.user = user
        self.password = password
        self.security_level = security_level
        self.handle = 0


    def __enter__(self):
        self.server = prlsdkapi.Server()
        if self.host == "localhost":
            try:
                # The call returns a prlsdkapi.Result object on success.
                result = self.server.login_local('', 0, self.security_level).wait()
            except prlsdkapi.PrlSDKError, e:
                print "Login error: %s" % e
                raise Halt
        else:
            try:
                result = self.server.login(self.host, self.user, self.password, security_level=self.security_level).wait()
            except prlsdkapi.PrlSDKError, e:
                print "Login error: %s" % e
                print "Error code: " + str(e.error_code)
                raise Halt
        login_response = result.get_param()
        return self.server, login_response


    def __exit__(self, exception_type, exception_value, traceback):
        self.server.logoff().wait()


class funHelper(object):
    """
    Class is to be used in a with loop, to properly edit and commit instances
    returns same (hopefully updated) instance object that was passed to it
    """
    def __init__(self, ct):
        self.ct = ct

    def __enter__(self):
        print "starting container edit"
        self.ct.begin_edit().wait()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        print "committing container"
        self.ct = safe_commit(self.ct)

    def run(self, fun, *args):
        print "Running function ct.{0}".format(fun)
        job = getattr(self.ct, fun)(*args)
        if hasattr(job, 'get_status'):
            loop_job(job)
        return self.ct


class Instance(object):
    # passing kwargs here seems clunky, only using until figure out final data structure
    def __init__(self, APIHelper, ctname, space=0, template=None, mem=1, disk=10, ip_addresses=None, **kwargs):
        self.server, self.login_result = APIHelper
        self.space = '{space:06d}'.format(space=space)
        self.hostname = ctname
        self.ip_addresses = ip_addresses
        self.handle = 0
        try:
            self.get_ct()
        except:
            try:
                if template is not None:
                    self.template = template
                else:
                    print "Creating a container requires an OS template"
                    raise Halt
                self.mem = int(mem)
                self.assigned_storage, self.disk = storageUnits("{0}G".format(disk), storage_unit_size)
                self.create_ct()
            except Exception as e:
                print e
                raise Halt


    def get_params(self):
        """
        Sets the various self params when finding an existing container
        """
        self.template = self.ct.get_os_template()
        self.mem = self.ct.get_ram_size()
        hdd = self.ct.get_hard_disk(0)
        self.disk = hdd.get_disk_size()
        self.assigned_storage, founddisk = storageUnits("{0}G".format(self.disk), storage_unit_size)
        self.venet0 = self.ct.get_dev_by_type(consts.PDE_GENERIC_NETWORK_ADAPTER, 0)


    def create_ct(self):
        # TODO: make a unified create method for both CT and VM
        """
        Sets the self.ct by creating new container
        """
        # Create a new prlsdkapi.Vm object.
        ct = self.server.create_vm()
        # Set the virtual server type (Container)
        ct.set_vm_type(consts.PVT_CT)
        # Set the Container name and description.
        ct.set_name("{0}-{1}".format(self.space, self.hostname))
        # Set the OS template
        ct.set_os_template(self.template)
        # set resources
        memory = pickConfig(self.mem)
        # should we check if config file exists first?
        if vzconfig_string:
            ct.apply_config_sample(vzconfig_string.format(memory))
    
        # Register the virtual server with the Virtuozzo host. The first 
        # parameter specifies to create the server in the default directory 
        # on the host server. The second parameter specifies that 
        # non-interactive mode should be used.
        print "Creating a container instance"
        try:
            result = ct.reg("", True).wait()
        except prlsdkapi.PrlSDKError as e:
            print e
            raise Halt

        print "Container was registered successfully."
        self.ct = ct
        self.venet0 = self.ct.get_dev_by_type(consts.PDE_GENERIC_NETWORK_ADAPTER, 0)
        with funHelper(self.ct) as Helper:
            Helper.run("set_cpu_count", 0)
            # setting the full requested mem, could be different then vzconfig
            self.resizeMemory(Helper, self.mem)
            mem_prcnt = default_mem_prcnt
            if self.mem >= 64:
                mem_prcnt = 95
            Helper.run("set_mem_guarantee_size", consts.PRL_MEMGUARANTEE_PERCENTS, mem_prcnt)
            self.set_hostname(Helper, self.hostname)
            self.resizeHdd(self.disk)
            if self.ip_addresses:
                self.addIPs(ip_list=self.ip_addresses)
                self.setNameservers(nameserver_list=default_nameservers)

        print "Virtuozzo Container was created successfully."


    def setNameservers(self, nic=None, nameserver_list=None):
        """
        requires running under funHelper.  sets nameserver(s) to nameserver_list
        """
        if not nameserver_list:
            print "No name servers in request"
            raise halt
        if not nic:
            nic = self.venet0
        dns_string = prlsdkapi.StringList()
        for nameserver in nameserver_list:
            dns_string.add_item(u"{}".format(nameserver))

        try:
            nic.set_dns_servers(dns_string)
        except:
            raise Halt            


    def addIPs(self, nic=None, ip_list=None, cidr=32, replace=False):
        """
        requires running under funHelper.  defaults IP cidr to /32
        """
        if not ip_list:
            print "No IP addresses in request"
            raise halt
        if not nic:
            nic = self.venet0

        print "Adding IPs {}".format(ip_list)

        if replace:
            ip_string = prlsdkapi.StringList()
        else:
            ip_string = nic.get_net_addresses()

        for ip in ip_list:
            ip_string.add_item(u"{}/{}".format(ip,cidr))

        nic.set_net_addresses(ip_string)


    def set_hostname(self, Helper, name):
        """
        Force sets both the hostname and name of an instance.
        """
        Helper.run("set_hostname", self.hostname)
        self.hostname = name
        Helper.run("set_name", "{0}-{1}".format(self.space, name))


    def resizeMemory(self, Helper, newsize):
        """
        newsize parameter should be an int in Gb
        """
        if newsize > 128:
            raise Halt
        memory = newsize * 1024
        if Helper.ct.get_ram_size() != memory:
            print "Adjusting memory to {0}".format(memory)
            Helper.run("set_ram_size", memory)
            self.mem = newsize


    def resizeHdd(self, newsize):
        # TODO: support for more then one disk?
        hdd = self.ct.get_hard_disk(0)
        # TODO: need a capacity check to make sure there is space
        if hdd.get_disk_size() != newsize:
            print "Resizing disk to {0}".format(newsize)
            result = hdd.resize_image(newsize, consts.PRIF_RESIZE_LAST_PARTITION).wait()
            self.disk = newsize


    def get_ct(self):
        """
        Sets the self.ct by searching for the instance by name 
        only requires space and ctname vars from self
        """
        try:
            result = self.server.get_vm_config("{0}-{1}".format(self.space, self.hostname), consts.PGVC_SEARCH_BY_NAME).wait()
            ct = result.get_param()
            self.ct = ct
            self.get_params()
        except Exception as e:
            print e
            raise Halt


    def get_actual_state(self):
        states = {}
        statuses = search_consts(consts, "VMS")
        for constant in statuses:
            x = constant.split("_")
            del x[0]
            states[getattr(consts, constant)] = "_".join(x).lower()
        result = self.ct.get_state().wait()
        state = states.get(result.get_param().get_state())
        return state


    def start(self):
        state = self.get_actual_state()
        if state == "running":
            print "container is already running, no action taken"
        elif state == "stopped":
            print "starting container"
            result = self.ct.start().wait()
        else:
            print "unknown state: {0}".format(state)


    def stop(self):
        state = self.get_actual_state()
        if state == "running":
            print "stopping container"
            result = self.ct.stop().wait()
        elif state == "stopped":
            print "container is already stopped, no action taken"
        else:
            print "unknown state: {0}".format(state)


    def destroy(self):
        self.stop()
        print "destroying container"
        result = self.ct.delete().wait()
        return result


class ctTemplates(object):
    def __init__(self, server):
        # no idea what nFlags are...
        self.nFlags = 0
        self.server = server
        self.result = self.server.get_ct_template_list(self.nFlags).wait()
        self.count = self.result.get_params_count()
        self._get_all()

    def _get_all(self):
        os = {}
        apps = {}
        for index in range(self.count):
            if self.result.get_param_by_index(index).get_type() == consts.PCT_TYPE_EZ_OS: 
                os[self.result.get_param_by_index(index).get_name()] = self.result.get_param_by_index(index)
            elif self.result.get_param_by_index(index).get_type() == consts.PCT_TYPE_EZ_APP:
                try:
                    apps[self.result.get_param_by_index(index).get_os_template()]
                except KeyError:
                    apps[self.result.get_param_by_index(index).get_os_template()] = {}
                apps[self.result.get_param_by_index(index).get_os_template()][self.result.get_param_by_index(index).get_name()] = self.result.get_param_by_index(index)
            else:
                print "What is this?"
                print self.result.get_param_by_index(index).get_name()

        self.operatingsystems = os
        self.apps = apps


def vms(host, user="root", passwd="", data=None):
    """
    this function results in a generator which supplies the APIHelper function 
    as well as all the VM objects found/created from data. after the generator 
    is exhausted the connection to API should close

    the data var should be a list of dicts which contain keyword args for 
    finding/creating VMs

    vm_data = [{'space': '000000', ctname: name.com, 'template': 'centos-7-x86_64'}]
    gen = vms('localhost', data=vm_data)
    for data in gen:
      API, vms = data
      vms[0].start()
    """
    results = []
    with API():
        with Login(host, user, passwd) as APIHelper:
            for kwargs in data:
                try:
                    vm = Instance(APIHelper, **kwargs)
                    results.append(vm)
                except:
                    raise
            yield APIHelper, results

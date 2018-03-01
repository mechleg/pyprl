# pyprl
pyprl means to be a helpful Python wrapper around OpenVZ/Virtuozzo 7 libprlsdk.  I created this wrapper mostly so I could manage OpenVZ hosts and virtual environments using Python and JSON data.  

libprlsdk is a client library for connecting to and managing OpenVZ/Virtuozzo hosts.  It can be a little complicated to use if one is not familiar with it.

Only tested connecting to OpenVZ/Virtuozzo 7, though it may work with Virtuozzo 6 (libprlsdk was not included in OpenVZ releases before 7)

Everything here is currently based on Redhat/CentOS/vzlinux, but should be able to run anywhere libprlsdk and its dependencies can be installed

libprlsdk source code is found here:
https://src.openvz.org/projects/OVZ/repos/libprlsdk

The libprlsdk programming documentation is found here:
https://docs.virtuozzo.com/pdf/virtuozzo_7_virtualization_sdk_programmers_guide.pdf

The Python libprlsdk reference documentation is found here:
https://docs.virtuozzo.com/virtuozzo_7_virtualization_sdk_python_api_reference/index.html

## Install libprlsdk and dependencies
#### if using vzlinux/OpenVZ then all this is included in a base install
    # if you have OpenVZ 7 repo configured:
    yum install -y libprlsdk libprlsdk-python libprlcommon libprlxmlmodel
    # if you do not have repo configured:
    yum install -y https://download.openvz.org/virtuozzo/releases/7.0/x86_64/os/Packages/l/libprlsdk-7.0.198-2.vz7.x86_64.rpm https://download.openvz.org/virtuozzo/releases/7.0/x86_64/os/Packages/l/libprlsdk-python-7.0.198-2.vz7.x86_64.rpm https://download.openvz.org/virtuozzo/releases/7.0/x86_64/os/Packages/l/libprlcommon-7.0.116-1.vz7.x86_64.rpm https://download.openvz.org/virtuozzo/releases/7.0/x86_64/os/Packages/l/libprlxmlmodel-7.0.71-1.vz7.x86_64.rpm
    
## Quick examples
### connect to a server and get/create a container and start it
    with API():
        with Login(host, user, passwd) as APIHelper:
            vm = Instance(APIHelper, {'space': 10, 'ctname': 'test02.example.com', 'template': 'ubuntu-16.04-x86_64', 'mem': 4, 'disk': 20})
            vm.start()
                
### create any number of containers from a list of dicts, then start them
    from pyprl import vms
    data = [
        {'space': 10, 'ctname': 'test01.example.com', 'template': 'centos-7-x86_64', 'mem': 2, 'disk': 10},
        {'space': 10, 'ctname': 'test02.example.com', 'template': 'ubuntu-16.04-x86_64', 'mem': 4, 'disk': 20},
    ]
    # the following produces a generator, iterating over the generator will create each instance and then start it
    vms_gen = vms(host, user, passwd, data)
    for results in vms_gen:
        API, vm_data = results
        for vm in vm_data:
            vm.start()

### can also do template stuff
    from libs.pyprl import API, Login, ctTemplates
    with API():
        with Login(host, user, passwd) as APIHelper:
            server, results = APIHelper
            templates = ctTemplates(server)
            a = templates.operatingsystems
            for x in a.keys():
                print a[x].is_cached()

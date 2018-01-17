#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2017, Davis Phillips davis.phillips@gmail.com
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'version': '1.0'}

DOCUMENTATION = '''
---
module: vmware_folder
short_description: Add/remove folders to/from vCenter
description:
    - This module can be used to add/remove a folder to/from vCenter
version_added: 2.3
author: "Davis Phillips (@dav1x)"
notes:
    - Tested on vSphere 6.0 and 6.5
requirements:
    - "python >= 2.6"
    - PyVmomi
options:
    datacenter:
        description:
            - Name of the datacenter to add the folder
        required: True
    folder:
        description:
            - Folder name to manage
        required: True
    folder_type:
        description:
            - Folder type, 'vm_folder' for VMs or 'host_folder' for Hosts
        default: 'vm_folder'
        choices:
            - 'vm_folder'
            - 'host_folder'
    force:
        description:
            - Used with state 'absent'. When set to 'yes' all objects in the folder will be removed recursively. WARNING Setting this to 'yes' will remove any VMs including VMDKs located in the folder and subfolders!!!
        default: 'False'
        choises:
            - 'True'
            - 'False'
    hostname:
        description:
            - ESXi/vCenter hostname to manage
        required: True
    username:
        description:
            - ESXi/vCenter username
        required: True
    password:
        description:
            - ESXi/vCenter password
        required: True
    state:
        description:
            - Add or remove the folder. If set to 'present' all folders in the path will be created if required. If set to 'absent' only the last folder in the path will be removed. Folder will not be removed if it's contain any child objects, use 'force yes' to override.
        default: 'present'
        choices:
            - 'present'
            - 'absent'
extends_documentation_fragment: vmware.documentation
'''

EXAMPLES = '''
# Create a folder
  - name: Add a folder to vCenter
    vmware_folder:
      hostname: vcsa_host
      username: vcsa_user
      password: vcsa_pass
      datacenter: datacenter
      folder: folder
      state: present
'''

RETURN = """
instance:
    descripton: metadata about the new folder
    returned: always
    type: dict
    sample: None
"""

try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

from ansible.module_utils.vmware import get_all_objs, connect_to_api, vmware_argument_spec, find_datacenter_by_name, \
    wait_for_task
from ansible.module_utils.basic import AnsibleModule

class VMwareFolder(object):
    def __init__(self, module):
        self.module = module
        self.datacenter = module.params['datacenter']
        self.folder = module.params['folder']
        self.hostname = module.params['hostname']
        self.username = module.params['username']
        self.password = module.params['password']
        self.state = module.params['state']
        self.folder_type = module.params['folder_type']
        self.force = module.params['force']
        self.dc_obj = None
        self.host_obj = None
        self.folder_obj = None
        self.folder_name = None
        self.folder_expanded = None
        self.folder_full_path = []
        self.content = connect_to_api(module)

    def select_folder(self):
        self.folder_expanded = self.folder.strip('/').split('/')
        if self.folder_type=="vm_folder":
          base_obj = self.dc_obj.vmFolder
        elif self.folder_type=="host_folder":
          base_obj = self.dc_obj.hostFolder
        for f in self.folder_expanded:
            if base_obj.childEntity:
              for y, child_obj in enumerate(base_obj.childEntity):
                if child_obj.name.lower() == f.lower():
                    base_obj = child_obj
                    break
                elif y >= len(base_obj.childEntity)-1:
                    return None
            else:
              return None

        return base_obj

    def get_obj(self, vimtype, name, return_all = False):
        obj = list()
        container = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, vimtype, True)

        for c in container.view:
            if name in [c.name, c._GetMoId()]:
                if return_all is False:
                    return c
                    break
                else:
                    obj.append(c)

        if len(obj) > 0:
            return obj
        else:
            # for backwards-compat
            return None

    def process_state(self):
        self.dc_obj = find_datacenter_by_name(self.content, self.datacenter)
        if self.dc_obj == None:
          self.module.fail_json(msg = "Datacenter '%s' not found!" % (self.datacenter))
        try:
            folder_states = {
                'absent': {
                    'present': self.state_remove_folder,
                    'absent': self.state_exit_unchanged,
                },
                'present': {
                    'present': self.state_exit_unchanged,
                    'absent': self.state_add_folder,
                }
            }

            folder_states[self.state][self.check_folder_state()]()

        except vmodl.RuntimeFault as runtime_fault:
            self.module.fail_json(msg = runtime_fault.msg)
        except vmodl.MethodFault as method_fault:
            self.module.fail_json(msg = method_fault.msg)
        except Exception as e:
            self.module.fail_json(msg = str(e))

    def state_exit_unchanged(self):
        self.module.exit_json(changed = False)

    def state_remove_folder(self):
        changed = True
        result = None

        self.folder_expanded = self.folder.strip('/').split('/')
        if self.folder_type=="vm_folder":
            base_obj = self.dc_obj.vmFolder
        elif self.folder_type=="host_folder":
            base_obj = self.dc_obj.hostFolder
        for f in self.folder_expanded:
            if base_obj.childEntity:
                for y, child_obj in enumerate(base_obj.childEntity):
                    if child_obj.name.lower() == f.lower():
                        base_obj = child_obj
                        break
                    elif y >= len(base_obj.childEntity)-1:
                        # should never get here 
                        break

        # figure out if there is any object in the folder
        if base_obj.childEntity:
            if self.force:
                task = base_obj.Destroy()
            else:
                self.module.fail_json(msg="Specified folder contains child objects!")
        else:
            task = base_obj.Destroy()

        try:
            success, result = wait_for_task(task)

        except:
            self.module.fail_json(msg = "Failed to remove folder '%s' '%s'" % (self.folder,folder))

        self.module.exit_json(changed = changed, result = str(result))

    def mkdir_task(self, base_obj, dir_name):
      try:
        return base_obj.CreateFolder(dir_name)
      except (vim.fault.InvalidName) as e:
        self.module.fail_json(msg = "'%s'" % (e))

    def state_add_folder(self):
        changed = True
        result = None

        self.folder_expanded = self.folder.strip('/').split('/')
        if self.folder_type=="vm_folder":
            base_obj = self.dc_obj.vmFolder
        elif self.folder_type=="host_folder":
            base_obj = self.dc_obj.hostFolder
        for f in self.folder_expanded:
            if base_obj.childEntity:
                for y, child_obj in enumerate(base_obj.childEntity):
                    if child_obj.name.lower() == f.lower():
                        base_obj = child_obj
                        break
                    elif y >= len(base_obj.childEntity)-1:
                        base_obj = self.mkdir_task(base_obj, f)
                        break
                else:
                    base_obj = self.mkdir_task(base_obj, f)

        self.module.exit_json(changed = changed)

    def check_folder_state(self):

        self.folder_obj = self.select_folder()

        if self.folder_obj is None:
            return 'absent'
        else:
            return 'present'


def main():
    argument_spec = vmware_argument_spec()
    argument_spec.update(dict(datacenter = dict(required = True, type = 'str'),
                              folder = dict(required=True, type='str'),
                              folder_type = dict(default = 'vm_folder', choices = ['vm_folder','host_folder'], type = 'str'),
                              force = dict(default = 'no', type = 'bool'),
                              hostname = dict(required = True, type = 'str'),
                              username = dict(required = True, type = 'str'),
                              password = dict(required = True, type = 'str', no_log = True),
                              state = dict(default = 'present', choices = ['present', 'absent'], type = 'str')))

    module = AnsibleModule(argument_spec = argument_spec, supports_check_mode = True)

    if not HAS_PYVMOMI:
        module.fail_json(msg = 'pyvmomi is required for this module')

    vmware_folder = VMwareFolder(module)
    vmware_folder.process_state()


if __name__ == '__main__':
    main()

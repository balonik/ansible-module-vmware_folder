# ansible-module-vmware_folder
This module can be used to add/remove a folder to/from vCenter.

Original code from https://github.com/openshift/openshift-ansible-contrib/blob/master/reference-architecture/vmware-ansible/playbooks/library/vmware_folder.py  

```
- code clean up
- changed folder selection to properly select folders if name is not unique
- removed the 'cluster' option that was not used
- added 'folder_type' for VM/host folder selection
- added 'force' to remove folder if there are any child objects present
```

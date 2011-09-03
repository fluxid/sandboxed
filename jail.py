#coding:utf8

from code import interact

from sandboxed import Jail
from sandboxed.utils import mount_python_lib
from sandboxed.lowlevel import umount

class InteractiveJail(Jail):
    def setup_fs(self, path):
        pylib, pylib_mount = mount_python_lib(path)
        self.pylib_mount = pylib_mount
        self.ignore_mounts = self.ignore_mounts or []
        self.ignore_mounts.append(pylib)

    def teardown_fs(self, path):
        umount(self.pylib_mount)

    def prisoner(self):
        interact()

def main():
    InteractiveJail(2000, 'fluxid', 'fluxid', 'lolnope').run()

if __name__ == '__main__':
    main()


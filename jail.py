import os
import os.path
import grp
import pwd
import sys
from code import interact
import tempfile

from sandboxed.lowlevel import clone, sethostname, getpid, umount, pivot_root
from sandboxed import const
from sandboxed.utils import mount_bind, mount_tmpfs, mount_proc, mount_cgroup, umount_all

WALL = 0x40000000

def main():
    # Get desired gid and uid
    # TODO configurable
    gid = grp.getgrnam('fluxid').gr_gid
    uid = pwd.getpwnam('fluxid').pw_uid

    # Create temporary mountpoint for tmpfs
    tmp = tempfile.mkdtemp()

    # Mount tmpfs for our use
    # TODO configurable size
    mount_tmpfs(2000, tmp)

    # Create directory for old root
    put_old = 'root'
    old_root = os.path.join(tmp, put_old)
    os.mkdir(old_root)

    # Copy stuff to tmpfs
    # TODO

    # Clone and create new namespaces. Note CLONE_NEWUSER is not used (yet?)
    pid = clone(const.CLONE_NEWNS | const.CLONE_NEWPID | const.CLONE_NEWUTS | const.CLONE_NEWNET | const.CLONE_NEWIPC)
    assert pid is not None
    if pid:
        # TODO catch KeyboardInterrupt
        pid, status = os.waitpid(-1, WALL)

        # Umount tmpfs and remove mountpoint
        umount(tmp)
        os.rmdir(tmp)
        
        print('Child {} exited with status {}'.format(pid, status))
        sys.exit(status)
    else:
        # We check if new PID namespace worked
        assert getpid() == 1

        # Monkey-patch os.getpid with syscall
        os.getpid = getpid

        # Set desired hostname
        # TODO configurable
        sethostname('lolnope')

        # Move new root to tmpfs, and old to subdir
        pivot_root(tmp, old_root)
        os.chdir('/')

        # Mount /proc and /cgroup
        mount_proc()
        mount_cgroup()
        
        # Umount all filesystems but those we set up by ourselves
        umount_all(('/', '/proc', '/cgroup'))
        # Remove evidence ;)
        os.rmdir('/' + put_old)

        # Remount tmpfs r/o
        mount_tmpfs(2000, '/', const.MS_REMOUNT | const.MS_RDONLY)

        # Set to desired gid/uid
        os.setgid(gid)
        os.setuid(uid)
        
        # We're ready to go!
        interact()

if __name__ == '__main__':
    main()


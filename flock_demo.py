import argparse
import ctypes
import datetime
import msvcrt
import sys
import time
import typing


LOCKFILE_FAIL_IMMEDIATELY = 1
LOCKFILE_EXCLUSIVE_LOCK = 2


class WriteLockError(Exception):
    pass


class DummyStruct(ctypes.Structure):
    _fields_ = [
        ('Offset', ctypes.c_ulong),
        ('OffsetHigh', ctypes.c_ulong),
    ]


class DummyUnion(ctypes.Union):
    _fields_ = [
        ('DUMMYSTRUCTNAME', DummyStruct),
        ('Pointer', ctypes.c_void_p),
    ]


class Overlapped(ctypes.Structure):
    _fields_ = [
        ('Internal', ctypes.c_ulong),
        ('InternalHigh', ctypes.c_ulong),
        ('DUMMYUNIONNAME', DummyUnion),
        ('hEvent', ctypes.c_void_p),
    ]


def get_user_name():
    name = ctypes.create_string_buffer(16)
    namesize = ctypes.c_ulong(16)
    result = ctypes.windll.advapi32.GetUserNameA(name, ctypes.byref(namesize))
    if result == 0:
        err = ctypes.windll.kernel32.GetLastError()
        raise RuntimeError(f'Error calling GetUserNameA: {err}')
    return name.value.decode()


def lock_and_doc(file_: typing.TextIO):
    handle = msvcrt.get_osfhandle(file_.fileno())
    sizehigh = ctypes.c_ulong(0)
    size = ctypes.windll.kernel32.GetFileSize(handle, ctypes.byref(sizehigh))
    overlapped = Overlapped(hEvent=None)

    # Write lock the size of the file, no offset
    result = ctypes.windll.kernel32.LockFileEx(
        handle,
        LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY,
        0,
        size,
        sizehigh,
        overlapped)

    # Failure: return false
    if result == 0:
        raise WriteLockError('Unable to obtain write lock')

    # Update the file with the current writer record
    user = get_user_name()
    datestamp = datetime.datetime.now()
    record = f'user: {user:>10}, datestamp: {datestamp}\n'
    bytes_written = file_.write(record)
    # Need to flush record before read lock!
    file_.flush()

    # Read lock the writer record, old end of file to new end
    overlapped = Overlapped(hEvent=None)
    overlapped.DUMMYUNIONNAME.DUMMYSTRUCTNAME.Offset = size
    overlapped.DUMMYUNIONNAME.DUMMYSTRUCTNAME.OffsetHigh = sizehigh
    result = ctypes.windll.kernel32.LockFileEx(
        handle,
        LOCKFILE_FAIL_IMMEDIATELY,
        0,
        bytes_written,
        0,
        overlapped)
    if result == 0:
        err = ctypes.windll.kernel32.GetLastError()
        raise RuntimeError(f'Error setting read lock: {err}')


def print_doc(file_: typing.TextIO):
    record_bytes = 56
    end_bytes = file_.seek(0, 2)  # SEEK_END
    file_.seek(end_bytes - record_bytes - 1)
    doc = file_.read()
    print(f'File locked!\n\t{doc.strip()}')


def main(args: typing.List[str] = sys.argv[1:]):
    parser = argparse.ArgumentParser(description='locker')
    parser.add_argument('seconds', type=int, help='Seconds to hold lock')
    namespace = parser.parse_args(args)
    try:
        print('Testing file locking...')
        with open('lock.txt', 'a+') as lockfile:
            try:
                lock_and_doc(lockfile)
                time.sleep(namespace.seconds)
            except WriteLockError:
                print_doc(lockfile)
    except KeyboardInterrupt:
        pass
    finally:
        print('Test complete')


if __name__ == '__main__':
    main()

from os.path import join

from django.core.files.base import ContentFile

from ..models import Upload


class EmptyStorageMixin(object):
    def list_storage_recursively(self, storage, base=''):
        dirs = []
        files = []
        dirnames, filenames = storage.listdir(base)
        for filename in filenames:
            filepath = join(base, filename)
            files.append(filepath)
        for dirname in dirnames:
            dirpath = join(base, dirname)
            dirs.append(dirname)
            descendant_dirs, descendant_files = self.list_storage_recursively(storage, dirpath)
            dirs.extend(descendant_dirs)
            files.extend(descendant_files)
        return dirs, files
    
    def purge_storage(self, storage, base=''):
        dirnames, filenames = storage.listdir(base)
        for filename in filenames:
            filepath = join(base, filename)
            storage.delete(filepath)
        for dirname in dirnames:
            dirpath = join(base, dirname)
            self.purge_storage(storage, dirpath)
            storage.delete(dirpath)
    
    def ensure_empty_storage(self, storage):
        self.purge_storage(storage)
        self.assertEmptyStorage(storage)
    
    def assertEmptyStorage(self, storage, allow_empty_dirs=False, allowed_file_names=tuple()):
        dirnames, filenames = self.list_storage_recursively(storage, '')
        filenames = [f for f in filenames if f not in allowed_file_names]
        contents = dirnames + filenames
        if allow_empty_dirs:
            self.assertFalse(filenames, 'File Results %s' % filenames)
        else:
            self.assertFalse(contents, 'Directory Results %s, File Results %s' % (dirnames, filenames))
    
    def test_assert_empty_storage(self):
        storage = Upload._meta.get_field('file').storage
        self.ensure_empty_storage(storage)
        with storage.open('i.think', 'w') as fp:
            fp.write('i.am')
        with self.assertRaises(AssertionError):
            self.assertEmptyStorage(storage)
        self.assertEmptyStorage(storage, allowed_file_names=['i.think'])
        self.purge_storage(storage)
        self.assertEmptyStorage(storage)
        storage.save('i/think', ContentFile('i.am'))
        storage.delete('i/think')
        with self.assertRaises(AssertionError):
            self.assertEmptyStorage(storage)
        self.assertEmptyStorage(storage, allow_empty_dirs=True)

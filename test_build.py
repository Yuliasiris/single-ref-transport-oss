"""Local distribution regression tests. Never push or download anything."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("candidate_builder",ROOT/"build.py")
builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)

class DistributionTests(unittest.TestCase):
    def test_byte_identical_rebuild(self):
        self.assertEqual(builder.build_bytes(),builder.build_bytes())

    def test_origin_platform_default_is_explicitly_overridden(self):
        real=zipfile.ZipInfo
        def from_platform(system):
            class Info(real):
                def __init__(self,*args,**kwargs):
                    super().__init__(*args,**kwargs); self.create_system=system
            return Info
        with mock.patch.object(builder.zipfile,'ZipInfo',from_platform(0)):
            a=builder.build_bytes()[1]
        with mock.patch.object(builder.zipfile,'ZipInfo',from_platform(3)):
            b=builder.build_bytes()[1]
        self.assertEqual(a,b)

    def test_allowlisted_members_and_manifest(self):
        version,data=builder.build_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names=archive.namelist()
            self.assertEqual(names,sorted(names)); self.assertEqual(len(names),len(set(names)))
            expected=set(builder.FILES)|{'manifest.json'}
            if (ROOT/'NOTICE').exists(): expected.add('NOTICE')
            self.assertEqual(set(names),expected)
            manifest=json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['version'],version)
            for name,metadata in manifest['files'].items():
                raw=archive.read(name)
                self.assertEqual(metadata['bytes'],len(raw)); self.assertEqual(metadata['sha256'],hashlib.sha256(raw).hexdigest())
            for info in archive.infolist():
                self.assertEqual(info.create_system,0); self.assertEqual(info.date_time,(2026,9,21,0,0,0))
                self.assertFalse(info.extra); self.assertFalse(info.comment)
            self.assertIsNone(archive.testzip())

    def test_same_version_cannot_replace_different_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'candidate.zip'; builder.write_once(path,b'original')
            builder.write_once(path,b'original')
            with self.assertRaises(FileExistsError): builder.write_once(path,b'different')
            self.assertEqual(path.read_bytes(),b'original')

    def test_symlink_output_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'target'; target.write_bytes(b'unchanged')
            link=Path(temp)/'link'; link.symlink_to(target)
            with self.assertRaises(ValueError): builder.write_once(link,b'replacement')
            self.assertEqual(target.read_bytes(),b'unchanged')

    def test_symlink_source_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=Path(temp)/'source'; shutil.copytree(ROOT,copy,ignore=shutil.ignore_patterns('.git','dist','__pycache__'))
            readme=copy/'README.md'; real=copy/'actual-readme'; readme.rename(real); readme.symlink_to(real)
            with mock.patch.object(builder,'ROOT',copy):
                with self.assertRaises(ValueError): builder.build_bytes()


    def isolated_source(self, temp):
        copy=Path(temp)/'source'
        shutil.copytree(ROOT,copy,ignore=shutil.ignore_patterns('.git','dist','__pycache__'))
        return copy

    def test_license_status_document_required(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=self.isolated_source(temp); (copy/'LICENSE').unlink()
            with mock.patch.object(builder,'ROOT',copy):
                with self.assertRaises(ValueError): builder.build_bytes()

    def test_notice_is_included_and_hashed(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=self.isolated_source(temp)
            payload=b'Synthetic attribution fixture, not an actual upstream notice.\n'
            (copy/'NOTICE').write_bytes(payload)
            with mock.patch.object(builder,'ROOT',copy):
                data=builder.build_bytes()[1]
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                self.assertEqual(z.read('NOTICE'),payload)
                entry=json.loads(z.read('manifest.json'))['files']['NOTICE']
                self.assertEqual(entry['sha256'],hashlib.sha256(payload).hexdigest())
                self.assertEqual(entry['bytes'],len(payload))

    def test_dangling_notice_symlink_is_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=self.isolated_source(temp)
            (copy/'NOTICE').symlink_to(copy/'absent-notice')
            with mock.patch.object(builder,'ROOT',copy):
                with self.assertRaises(ValueError): builder.build_bytes()

    def test_symlink_ancestor_of_release_input_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=self.isolated_source(temp)
            moved=Path(temp)/'external-docs'; (copy/'docs').rename(moved)
            (copy/'docs').symlink_to(moved, target_is_directory=True)
            with mock.patch.object(builder,'ROOT',copy):
                with self.assertRaises(ValueError): builder.build_bytes()

if __name__=='__main__': unittest.main(verbosity=2)
